#!/usr/bin/env python3
"""
Social Poster (social_poster.py)
---------------------------------
Posts flow alerts to Reddit and Twitter with intelligent draft management.

Features:
- Reddit posting via PRAW
- Twitter posting via tweepy (optional)
- Draft generation with manual review
- Post deduplication and rate limiting
- Engagement tracking
- Error handling and retry logic

Author: Ben (with assistance from Claude)
Date: 2025-10-06
"""

import sys
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta

# Configure UTF-8 output for Windows
sys.stdout.reconfigure(encoding='utf-8')

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'tools'))

from tools.timezone_utils import now_eastern, eastern_isoformat
from tools.social_content_generator import SocialContentGenerator


class SocialPoster:
    """Posts flow alerts to social media platforms"""

    def __init__(self, config, storage):
        """Initialize with config and database storage

        Args:
            config: Configuration object with social_posting section
            storage: Database storage instance
        """
        self.config = config
        self.storage = storage
        self.content_generator = SocialContentGenerator(storage)

        # Load social posting config
        self.social_config = self.config.get('social_posting', {})
        self.enabled = self.social_config.get('enabled', False)
        self.auto_post = self.social_config.get('auto_post', False)

        # Platform configs
        self.reddit_enabled = self.social_config.get('platforms', {}).get('reddit', {}).get('enabled', False)
        self.twitter_enabled = self.social_config.get('platforms', {}).get('twitter', {}).get('enabled', False)

        # Selection criteria
        self.criteria = self.social_config.get('selection_criteria', {})
        self.min_score = self.criteria.get('min_significance_score', 9.0)
        self.min_premium = self.criteria.get('min_premium_value', 5000000)
        self.max_posts_per_day = self.criteria.get('max_posts_per_day', 3)

        # Timing
        self.timing = self.social_config.get('timing', {})
        self.delay_minutes = self.timing.get('delay_minutes', 30)
        self.max_age_minutes = self.timing.get('max_age_minutes', 60)

        # Initialize Reddit client (lazy load)
        self._reddit_client = None
        self._twitter_client = None

        logging.info(f"Social Poster initialized (enabled={self.enabled}, auto_post={self.auto_post})")

    def process_alert(self, alert_id, manual_context=None):
        """Process an alert for social posting

        Args:
            alert_id: ID from flow_alerts table
            manual_context: Optional manual analysis to include

        Returns:
            dict: Result with status and details
        """
        if not self.enabled:
            return {'status': 'disabled', 'message': 'Social posting is disabled'}

        # Get alert data
        alert_data = self._get_alert_data(alert_id)
        if not alert_data:
            return {'status': 'error', 'message': f'Alert {alert_id} not found'}

        # Check if already posted
        if alert_data.get('social_posted'):
            return {'status': 'skipped', 'message': 'Already posted to social media'}

        # Check selection criteria
        eligible = self._check_eligibility(alert_data)
        if not eligible['eligible']:
            return {'status': 'not_eligible', 'message': eligible['reason']}

        # Check rate limits
        rate_limit = self._check_rate_limits()
        if not rate_limit['allowed']:
            return {'status': 'rate_limited', 'message': rate_limit['reason']}

        # Generate content
        try:
            post_content = self.content_generator.generate_post(alert_data, manual_context)
        except Exception as e:
            logging.error(f"Content generation failed: {e}")
            return {'status': 'error', 'message': f'Content generation failed: {e}'}

        # Create draft record
        draft_id = self._create_draft(alert_id, post_content, manual_context)

        if self.auto_post:
            # Auto-post to platforms
            result = self._post_to_platforms(draft_id, post_content)
            return result
        else:
            # Save draft for manual review
            return {
                'status': 'draft_created',
                'message': f'Draft created (ID: {draft_id}). Review and approve to post.',
                'draft_id': draft_id,
                'preview': post_content['title']
            }

    def publish_draft(self, draft_id, manual_edits=None):
        """Publish a previously created draft

        Args:
            draft_id: ID from social_posts table
            manual_edits: Optional dict with edited title/content

        Returns:
            dict: Result with status and post URLs
        """
        # Get draft
        draft = self._get_draft(draft_id)
        if not draft:
            return {'status': 'error', 'message': f'Draft {draft_id} not found'}

        if draft['status'] != 'draft':
            return {'status': 'error', 'message': f'Draft already {draft["status"]}'}

        # Apply manual edits if provided
        if manual_edits:
            if 'title' in manual_edits:
                draft['post_title'] = manual_edits['title']
            if 'content' in manual_edits:
                draft['post_content'] = manual_edits['content']

        # Post to platforms
        return self._post_to_platforms(draft_id, draft)

    def _get_alert_data(self, alert_id):
        """Get alert data from database

        Args:
            alert_id: ID from flow_alerts

        Returns:
            dict or None: Alert data
        """
        query = 'SELECT * FROM flow_alerts WHERE id = ?'
        results = self.storage.query_with_params(query, (alert_id,))
        return dict(results[0]) if results else None

    def _check_eligibility(self, alert_data):
        """Check if alert meets posting criteria

        Args:
            alert_data: Alert dictionary

        Returns:
            dict: {'eligible': bool, 'reason': str}
        """
        # Check significance score
        score = alert_data.get('significance_score', 0) or 0
        if score < self.min_score:
            return {
                'eligible': False,
                'reason': f'Significance score {score:.1f} below threshold {self.min_score}'
            }

        # Check premium value
        premium = alert_data.get('premium_value', 0) or 0
        if premium < self.min_premium:
            return {
                'eligible': False,
                'reason': f'Premium ${premium/1e6:.1f}M below threshold ${self.min_premium/1e6:.1f}M'
            }

        # Check alert age
        alert_time = datetime.fromisoformat(alert_data['alert_timestamp'].replace(' ', 'T'))
        age_minutes = (now_eastern() - alert_time).total_seconds() / 60

        if age_minutes > self.max_age_minutes:
            return {
                'eligible': False,
                'reason': f'Alert too old ({age_minutes:.0f} min, max {self.max_age_minutes} min)'
            }

        # Check earnings day exclusion
        if self.criteria.get('exclude_earnings_day', True):
            # TODO: Check earnings_calendar table
            pass

        return {'eligible': True, 'reason': 'Meets all criteria'}

    def _check_rate_limits(self):
        """Check if we've hit daily posting limits

        Returns:
            dict: {'allowed': bool, 'reason': str}
        """
        today = now_eastern().strftime('%Y-%m-%d')

        query = '''
            SELECT COUNT(*) as count
            FROM social_posts
            WHERE DATE(posted_at) = ?
                AND status = 'posted'
        '''

        results = self.storage.query_with_params(query, (today,))
        posted_today = results[0]['count'] if results else 0

        if posted_today >= self.max_posts_per_day:
            return {
                'allowed': False,
                'reason': f'Daily limit reached ({posted_today}/{self.max_posts_per_day})'
            }

        return {'allowed': True, 'reason': 'Within rate limits'}

    def _create_draft(self, alert_id, post_content, manual_context):
        """Create draft record in database

        Args:
            alert_id: Alert ID
            post_content: Generated post content dict
            manual_context: Optional manual context

        Returns:
            int: Draft ID
        """
        insert_query = '''
            INSERT INTO social_posts (
                alert_id, platform, post_title, post_content,
                draft_generated_at, status, manual_context, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        '''

        current_time = eastern_isoformat()

        params = (
            alert_id,
            post_content.get('platform', 'reddit'),
            post_content['title'],
            post_content['content'],
            current_time,
            'draft',
            manual_context,
            current_time
        )

        with self.storage.get_connection() as conn:
            cursor = conn.execute(insert_query, params)
            conn.commit()
            draft_id = cursor.lastrowid

        logging.info(f"Draft created: ID {draft_id} for alert {alert_id}")
        return draft_id

    def _get_draft(self, draft_id):
        """Get draft from database

        Args:
            draft_id: ID from social_posts

        Returns:
            dict or None: Draft data
        """
        query = 'SELECT * FROM social_posts WHERE id = ?'
        results = self.storage.query_with_params(query, (draft_id,))
        return dict(results[0]) if results else None

    def _post_to_platforms(self, draft_id, content):
        """Post content to enabled platforms

        Args:
            draft_id: Draft ID from social_posts
            content: Post content dict

        Returns:
            dict: Result with URLs and status
        """
        results = []
        all_success = True

        # Post to Reddit
        if self.reddit_enabled:
            reddit_result = self._post_to_reddit(content)
            results.append(reddit_result)
            if not reddit_result.get('success'):
                all_success = False

        # Post to Twitter
        if self.twitter_enabled:
            twitter_result = self._post_to_twitter(content)
            results.append(twitter_result)
            if not twitter_result.get('success'):
                all_success = False

        # Update draft status
        if all_success:
            self._update_draft_status(draft_id, 'posted', results)
            # Update flow_alerts
            self._mark_alert_posted(content.get('alert_id', 0), draft_id)

            return {
                'status': 'posted',
                'message': 'Successfully posted to all platforms',
                'results': results
            }
        else:
            self._update_draft_status(draft_id, 'failed', results)
            return {
                'status': 'partial_failure',
                'message': 'Some platforms failed',
                'results': results
            }

    def _post_to_reddit(self, content):
        """Post to Reddit

        Args:
            content: Post content dict

        Returns:
            dict: Result with URL and status
        """
        try:
            if not self._reddit_client:
                self._init_reddit_client()

            subreddit_name = self.social_config['platforms']['reddit']['subreddits'][0]
            subreddit = self._reddit_client.subreddit(subreddit_name)

            # Submit as text post
            submission = subreddit.submit(
                title=content['title'],
                selftext=content['content']
            )

            logging.info(f"Posted to Reddit: {submission.url}")

            return {
                'success': True,
                'platform': 'reddit',
                'post_id': submission.id,
                'post_url': submission.url,
                'message': 'Posted successfully'
            }

        except Exception as e:
            logging.error(f"Reddit posting failed: {e}")
            return {
                'success': False,
                'platform': 'reddit',
                'error': str(e),
                'message': f'Failed: {e}'
            }

    def _post_to_twitter(self, content):
        """Post to Twitter/X

        Args:
            content: Post content dict

        Returns:
            dict: Result with URL and status
        """
        try:
            if not self._twitter_client:
                self._init_twitter_client()

            # Format for Twitter (280 char limit)
            tweet_text = self._format_for_twitter(content)

            # Post tweet
            response = self._twitter_client.create_tweet(text=tweet_text)

            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/user/status/{tweet_id}"

            logging.info(f"Posted to Twitter: {tweet_url}")

            return {
                'success': True,
                'platform': 'twitter',
                'post_id': tweet_id,
                'post_url': tweet_url,
                'message': 'Posted successfully'
            }

        except Exception as e:
            logging.error(f"Twitter posting failed: {e}")
            return {
                'success': False,
                'platform': 'twitter',
                'error': str(e),
                'message': f'Failed: {e}'
            }

    def _init_reddit_client(self):
        """Initialize Reddit PRAW client"""
        import praw

        reddit_config = self.config.get('reddit_api', {})

        self._reddit_client = praw.Reddit(
            client_id=reddit_config['client_id'],
            client_secret=reddit_config['client_secret'],
            username=reddit_config['username'],
            password=reddit_config['password'],
            user_agent=reddit_config['user_agent']
        )

        logging.info("Reddit client initialized")

    def _init_twitter_client(self):
        """Initialize Twitter tweepy client"""
        import tweepy

        twitter_config = self.config.get('twitter_api', {})

        self._twitter_client = tweepy.Client(
            consumer_key=twitter_config['api_key'],
            consumer_secret=twitter_config['api_secret'],
            access_token=twitter_config['access_token'],
            access_token_secret=twitter_config['access_token_secret']
        )

        logging.info("Twitter client initialized")

    def _format_for_twitter(self, content):
        """Format content for Twitter's character limit

        Args:
            content: Post content dict

        Returns:
            str: Twitter-formatted text
        """
        # Twitter thread would go here
        # For now, just truncate the title
        title = content['title']
        if len(title) > 280:
            title = title[:277] + "..."
        return title

    def _update_draft_status(self, draft_id, status, results):
        """Update draft status in database

        Args:
            draft_id: Draft ID
            status: New status ('posted', 'failed', etc.)
            results: List of platform results
        """
        # Extract URLs and errors
        urls = []
        errors = []
        for r in results:
            if r.get('post_url'):
                urls.append(r['post_url'])
            if r.get('error'):
                errors.append(f"{r['platform']}: {r['error']}")

        post_url = urls[0] if urls else None
        error_msg = '; '.join(errors) if errors else None

        update_query = '''
            UPDATE social_posts
            SET status = ?,
                posted_at = ?,
                post_url = ?,
                error_message = ?,
                updated_at = ?
            WHERE id = ?
        '''

        current_time = eastern_isoformat()

        self.storage._execute_with_retry(
            lambda conn: conn.execute(
                update_query,
                (status, current_time if status == 'posted' else None,
                 post_url, error_msg, current_time, draft_id)
            )
        )

        logging.info(f"Draft {draft_id} status updated to: {status}")

    def _mark_alert_posted(self, alert_id, draft_id):
        """Mark flow_alerts record as posted

        Args:
            alert_id: Alert ID
            draft_id: Draft ID
        """
        update_query = '''
            UPDATE flow_alerts
            SET social_posted = TRUE,
                social_post_id = ?
            WHERE id = ?
        '''

        self.storage._execute_with_retry(
            lambda conn: conn.execute(update_query, (draft_id, alert_id))
        )

        logging.info(f"Alert {alert_id} marked as posted (draft {draft_id})")


def main():
    """Test/demo function"""
    import argparse
    import json
    import sys
    from pathlib import Path

    # Add project paths
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root / 'strategies' / 'flow_monitor'))

    from fm_config import FMConfig
    from fm_storage import FlowMonitorStorage

    parser = argparse.ArgumentParser(description='Social Poster')
    parser.add_argument('--alert-id', type=int, required=True,
                       help='Alert ID from flow_alerts table')
    parser.add_argument('--context',
                       help='Manual context to add')
    parser.add_argument('--publish', action='store_true',
                       help='Publish draft immediately (if auto_post enabled)')
    parser.add_argument('--draft-id', type=int,
                       help='Publish existing draft by ID')

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    try:
        # Initialize
        config_manager = FMConfig()

        # Load full config
        with open(config_manager.config_path, 'r') as f:
            full_config = json.load(f)

        storage = FlowMonitorStorage(config_manager)
        poster = SocialPoster(full_config, storage)

        if args.draft_id:
            # Publish existing draft
            print(f"📤 Publishing draft {args.draft_id}...")
            result = poster.publish_draft(args.draft_id)
        else:
            # Process new alert
            print(f"📝 Processing alert {args.alert_id}...")
            result = poster.process_alert(args.alert_id, args.context)

        # Display result
        print("\n" + "="*80)
        print(f"STATUS: {result['status']}")
        print(f"MESSAGE: {result['message']}")

        if result.get('draft_id'):
            print(f"DRAFT ID: {result['draft_id']}")

        if result.get('results'):
            print("\nPLATFORM RESULTS:")
            for r in result['results']:
                print(f"  - {r['platform']}: {r['message']}")
                if r.get('post_url'):
                    print(f"    URL: {r['post_url']}")

        print("="*80)

        return 0 if result['status'] in ['draft_created', 'posted'] else 1

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
