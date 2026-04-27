#!/usr/bin/env python3
"""
Twitter Post Alert (twitter_post_alert.py)
-------------------------------------------
Manually post a single flow_alerts row to X (@ThePrintFlow).

Usage:
    python tools/twitter_post_alert.py --alert-id 1234              # post specific alert
    python tools/twitter_post_alert.py --alert-id 1234 --dry-run    # preview, no post
    python tools/twitter_post_alert.py --latest                     # post most recent eligible
    python tools/twitter_post_alert.py --latest --dry-run           # preview most recent

Eligibility filter for --latest:
    - social_posted = 0 (or NULL)        - not already published
    - roll_detected = 0 (or NULL)        - exclude rolls
    - volume / open_interest >= 1.0      - high v/oi (closure-resistant)

On successful post:
    - Updates flow_alerts.social_posted = 1
    - Updates flow_alerts.social_post_id = <tweet_id>
    in data/datalake.db (primary database).

Exit codes:
    0 - success (or dry run)
    1 - alert not found / no eligible alert / DB missing
    2 - tweet too long for max_chars
    3 - X API post failed
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import tweepy
except ImportError:
    print("ERROR: tweepy not installed. Run: pip install tweepy")
    sys.exit(1)

from tools.social_content_generator import SocialContentGenerator


class _SqliteShim:
    """Minimal storage shim with query_with_params() for SocialContentGenerator."""

    def __init__(self, db_path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row

    def query_with_params(self, query, params):
        cur = self._conn.cursor()
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def execute_with_commit(self, query, params):
        cur = self._conn.cursor()
        cur.execute(query, params)
        self._conn.commit()

    def close(self):
        self._conn.close()


def _load_credentials():
    creds_path = PROJECT_ROOT / 'credentials.json'
    with open(creds_path, 'r', encoding='utf-8') as f:
        creds = json.load(f)
    twitter = creds.get('twitter_api')
    if not twitter:
        raise RuntimeError("'twitter_api' block missing from credentials.json")
    return twitter


def _fetch_alert(shim, alert_id=None):
    if alert_id is not None:
        rows = shim.query_with_params(
            'SELECT * FROM flow_alerts WHERE id = ?', (alert_id,)
        )
    else:
        rows = shim.query_with_params(
            '''
            SELECT * FROM flow_alerts
            WHERE (social_posted = 0 OR social_posted IS NULL)
              AND (roll_detected = 0 OR roll_detected IS NULL)
              AND open_interest > 0
              AND CAST(volume AS REAL) / open_interest >= 1.0
            ORDER BY alert_timestamp DESC
            LIMIT 1
            ''', ()
        )
    return rows[0] if rows else None


def main():
    parser = argparse.ArgumentParser(
        description="Manually post a flow_alerts row to X (@ThePrintFlow)."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--alert-id', type=int, help='Specific flow_alerts.id')
    target.add_argument('--latest', action='store_true',
                        help='Most recent eligible alert (high v/oi, not rolled, unposted)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print formatted tweet without posting')
    parser.add_argument('--max-chars', type=int, default=280,
                        help='Tweet character limit (default 280)')
    args = parser.parse_args()

    db_path = PROJECT_ROOT / 'data' / 'datalake.db'
    if not db_path.exists():
        print(f"ERROR: {db_path} not found")
        return 1

    shim = _SqliteShim(db_path)
    try:
        alert = _fetch_alert(shim, args.alert_id)
        if not alert:
            print("No matching alert found.")
            return 1

        alert_id = alert['id']
        generator = SocialContentGenerator(shim)
        tweet = generator.format_for_x(alert, max_chars=args.max_chars)

        if not tweet:
            print(f"ERROR: alert {alert_id} could not be formatted within {args.max_chars} chars")
            return 2

        print(f"--- Tweet for alert {alert_id} ({len(tweet)} chars) ---")
        print(tweet)
        print("--- end ---")

        if args.dry_run:
            print("\n(dry run - not posting)")
            return 0

        twitter = _load_credentials()
        client = tweepy.Client(
            consumer_key=twitter['api_key'],
            consumer_secret=twitter['api_key_secret'],
            access_token=twitter['access_token'],
            access_token_secret=twitter['access_token_secret'],
        )

        try:
            resp = client.create_tweet(text=tweet)
        except tweepy.Unauthorized as e:
            print(f"ERROR: 401 Unauthorized - check credentials.\n{e}")
            return 3
        except tweepy.Forbidden as e:
            print(f"ERROR: 403 Forbidden - app permission or duplicate-content issue.\n{e}")
            return 3
        except Exception as e:
            print(f"ERROR: post failed: {type(e).__name__}: {e}")
            return 3

        tweet_id = int(resp.data['id'])
        print("\nSUCCESS - posted")
        print(f"Tweet ID: {tweet_id}")
        print(f"URL: https://x.com/i/status/{tweet_id}")

        try:
            shim.execute_with_commit(
                'UPDATE flow_alerts SET social_posted = 1, social_post_id = ? WHERE id = ?',
                (tweet_id, alert_id)
            )
            print(f"Marked alert {alert_id} social_posted=1 in flow_alerts")
        except Exception as e:
            print(f"WARNING: posted to X but failed to mark social_posted in DB: {e}")

        return 0

    finally:
        shim.close()


if __name__ == '__main__':
    sys.exit(main())
