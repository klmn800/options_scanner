#!/usr/bin/env python3
"""
Flow Monitor Social Notifier (fm_social_notifier.py)
-----------------------------------------------------
Auto-posts qualifying flow_alerts to X (@ThePrintFlow) immediately on save.

Called by fm_alerts.py via check_alert(alert_id) after each alert is persisted.
No delay queue, no manual review — full auto, gated only by the master
`social_posting.enabled` config flag and the eligibility filter.

Filter (all must hold):
- alert not already posted (social_posted = 0/NULL)
- alert is not a roll (roll_detected = 0/NULL)
- volume / open_interest >= min_voi_ratio (default 1.0; closure-resistant)
- daily post cap not exceeded (default 30/day)

On successful post:
- flow_alerts.social_posted = 1
- flow_alerts.social_post_id = tweet_id
- returns {'queued': True, 'tweet_id': int, 'message': str}

When social_posting.dry_run = true, the formatter runs and the result is
logged, but no tweet is posted and no DB write happens. Safe production
toggle for verifying behavior without spamming X.
"""

import sys
import json
import logging
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.social_content_generator import SocialContentGenerator


class FMSocialNotifier:
    """Auto-posts qualifying flow alerts to X."""

    def __init__(self, config, storage):
        """
        Args:
            config: Full config dict (from config.json).
            storage: Database storage with query_with_params() and a way to
                     execute UPDATEs. We use storage.query_with_params() for
                     reads and a direct sqlite3 connection for the UPDATE.
        """
        self.config = config
        self.storage = storage

        social = config.get('social_posting', {})
        self.enabled = bool(social.get('enabled', False))
        self.dry_run = bool(social.get('dry_run', True))

        criteria = social.get('selection_criteria', {})
        self.min_voi_ratio = float(criteria.get('min_voi_ratio', 1.0))
        self.exclude_rolls = bool(criteria.get('exclude_rolls', True))
        self.max_posts_per_day = int(criteria.get('max_posts_per_day', 30))

        self._generator = SocialContentGenerator(storage)
        self._client = None  # tweepy.Client, lazy-init on first real post
        self._credentials = None

        logging.info(
            "FM Social Notifier initialized "
            f"(enabled={self.enabled}, dry_run={self.dry_run}, "
            f"min_voi={self.min_voi_ratio}, daily_cap={self.max_posts_per_day})"
        )

    def check_alert(self, alert_id):
        """Process a freshly-saved alert.

        Args:
            alert_id: ID of the alert just inserted into flow_alerts.

        Returns:
            dict with keys:
                queued (bool): True if we acted on the alert (posted or dry-ran)
                tweet_id (int|None): X tweet ID on real post, None otherwise
                message (str): human-readable status
        """
        if not self.enabled:
            return {'queued': False, 'tweet_id': None, 'message': 'disabled'}

        alert = self._fetch_alert(alert_id)
        if not alert:
            return {'queued': False, 'tweet_id': None, 'message': 'alert not found'}

        ineligible = self._eligibility_reason(alert)
        if ineligible:
            return {'queued': False, 'tweet_id': None, 'message': ineligible}

        if self._daily_cap_reached():
            logging.info(f"Social: daily post cap ({self.max_posts_per_day}) reached — skipping alert {alert_id}")
            return {'queued': False, 'tweet_id': None, 'message': 'daily cap reached'}

        tweet = self._generator.format_for_x(alert)
        if not tweet:
            logging.warning(f"Social: alert {alert_id} could not be formatted within 280 chars")
            return {'queued': False, 'tweet_id': None, 'message': 'format failed'}

        symbol = alert.get('symbol', '?')
        if self.dry_run:
            logging.info(f"Social DRY RUN ({symbol} alert {alert_id}, {len(tweet)} chars):\n{tweet}")
            return {'queued': True, 'tweet_id': None, 'message': 'dry run'}

        tweet_id = self._post_tweet(tweet)
        if tweet_id is None:
            return {'queued': False, 'tweet_id': None, 'message': 'post failed'}

        self._mark_posted(alert_id, tweet_id)
        logging.info(f"Social: posted alert {alert_id} ({symbol}) as tweet {tweet_id}")
        return {'queued': True, 'tweet_id': tweet_id, 'message': 'posted'}

    def _fetch_alert(self, alert_id):
        rows = self.storage.query_with_params(
            'SELECT * FROM flow_alerts WHERE id = ?', (alert_id,)
        )
        return dict(rows[0]) if rows else None

    def _eligibility_reason(self, alert):
        """Return None if eligible, else a short reason string."""
        if alert.get('social_posted'):
            return 'already posted'

        if self.exclude_rolls and alert.get('roll_detected'):
            return 'roll detected'

        oi = alert.get('open_interest') or 0
        vol = alert.get('volume') or 0
        if oi <= 0:
            return 'no open interest'

        voi = vol / oi
        if voi < self.min_voi_ratio:
            return f'v/oi {voi:.2f} < {self.min_voi_ratio}'

        return None

    def _daily_cap_reached(self):
        rows = self.storage.query_with_params(
            '''
            SELECT COUNT(*) AS n FROM flow_alerts
            WHERE social_posted = 1
              AND DATE(alert_timestamp) = DATE('now', 'localtime')
            ''', ()
        )
        if not rows:
            return False
        return rows[0].get('n', 0) >= self.max_posts_per_day

    def _post_tweet(self, text):
        """Post via tweepy. Returns tweet_id (int) on success, None on failure."""
        if self._client is None:
            try:
                import tweepy
                creds = self._load_credentials()
                self._client = tweepy.Client(
                    consumer_key=creds['api_key'],
                    consumer_secret=creds['api_key_secret'],
                    access_token=creds['access_token'],
                    access_token_secret=creds['access_token_secret'],
                )
            except Exception as e:
                logging.error(f"Social: tweepy init failed: {type(e).__name__}: {e}")
                return None

        try:
            resp = self._client.create_tweet(text=text)
            return int(resp.data['id'])
        except Exception as e:
            logging.error(f"Social: post failed: {type(e).__name__}: {e}")
            return None

    def _load_credentials(self):
        if self._credentials is not None:
            return self._credentials
        creds_path = PROJECT_ROOT / 'credentials.json'
        with open(creds_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        twitter = data.get('twitter_api')
        if not twitter:
            raise RuntimeError("'twitter_api' block missing from credentials.json")
        self._credentials = twitter
        return twitter

    def _mark_posted(self, alert_id, tweet_id):
        """UPDATE flow_alerts.social_posted and social_post_id.

        Uses a direct sqlite3 connection because storage's read-only
        query_with_params() is not appropriate for writes.
        """
        import sqlite3
        db_path = PROJECT_ROOT / 'data' / 'datalake.db'
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(
                    'UPDATE flow_alerts SET social_posted = 1, social_post_id = ? WHERE id = ?',
                    (tweet_id, alert_id)
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logging.warning(f"Social: posted to X but failed to mark social_posted in DB: {e}")


def main():
    """CLI utility — manually re-run check_alert against a specific alert ID."""
    import argparse

    parser = argparse.ArgumentParser(description='FM Social Notifier — manual test')
    parser.add_argument('--alert-id', type=int, required=True,
                        help='flow_alerts.id to run check_alert against')
    parser.add_argument('--force-dry-run', action='store_true',
                        help='Override config dry_run=false back to true (for safe testing)')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    sys.path.insert(0, str(PROJECT_ROOT / 'strategies' / 'flow_monitor'))
    from fm_config import FMConfig
    from fm_storage import FlowMonitorStorage

    config_manager = FMConfig()
    with open(config_manager.config_path, 'r', encoding='utf-8') as f:
        full_config = json.load(f)

    if args.force_dry_run:
        full_config.setdefault('social_posting', {})['dry_run'] = True
        full_config.setdefault('social_posting', {})['enabled'] = True

    storage = FlowMonitorStorage(config_manager)
    notifier = FMSocialNotifier(full_config, storage)

    result = notifier.check_alert(args.alert_id)
    print(f"\nResult: {result}")
    return 0 if result['queued'] or result['message'] in ('disabled', 'already posted') else 1


if __name__ == '__main__':
    sys.exit(main())
