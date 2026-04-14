#!/usr/bin/env python3
"""
Flow Monitor Social Notifier (fm_social_notifier.py)
-----------------------------------------------------
Integration hook between Flow Monitor alerts and social posting system.

Features:
- Monitors new flow_alerts for social posting eligibility
- Manages 30-minute delay queue for manual context addition
- Processes queued alerts for draft generation
- Integrates with social_poster.py

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
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'tools'))

from tools.timezone_utils import now_eastern, eastern_isoformat


class FMSocialNotifier:
    """Manages social posting workflow for flow alerts"""

    def __init__(self, config, storage):
        """Initialize with config and storage

        Args:
            config: Full configuration dict
            storage: Database storage instance
        """
        self.config = config
        self.storage = storage

        # Social posting config
        self.social_config = self.config.get('social_posting', {})
        self.enabled = self.social_config.get('enabled', False)
        self.delay_minutes = self.social_config.get('timing', {}).get('delay_minutes', 30)

        # Lazy-load social poster
        self._social_poster = None

        logging.info(f"FM Social Notifier initialized (enabled={self.enabled}, delay={self.delay_minutes}min)")

    def check_alert(self, alert_id):
        """Check if newly created alert should be queued for social posting

        Called by fm_alerts.py after saving each alert.

        Args:
            alert_id: ID of newly created alert

        Returns:
            dict: {'queued': bool, 'message': str}
        """
        if not self.enabled:
            return {'queued': False, 'message': 'Social posting disabled'}

        # Get alert data
        alert_data = self._get_alert_data(alert_id)
        if not alert_data:
            return {'queued': False, 'message': 'Alert not found'}

        # Quick eligibility check (detailed check happens in social_poster)
        if not self._quick_eligibility_check(alert_data):
            return {'queued': False, 'message': 'Does not meet criteria'}

        # Check if already queued/posted
        if self._already_queued(alert_id):
            return {'queued': False, 'message': 'Already queued/posted'}

        # Queue for delayed processing
        logging.info(f"🔔 Alert {alert_id} queued for social posting ({self.delay_minutes}min delay)")
        logging.info(f"   Symbol: {alert_data['symbol']}")
        logging.info(f"   Score: {alert_data.get('significance_score', 0):.1f}")
        logging.info(f"   Premium: ${alert_data.get('premium_value', 0)/1e6:.1f}M")
        logging.info(f"   Delay: {self.delay_minutes} minutes for manual context addition")
        logging.info(f"   Use tools/social_poster.py --alert-id {alert_id} to review/post")

        return {
            'queued': True,
            'message': f'Queued for posting in {self.delay_minutes} min'
        }

    def process_queue(self):
        """Process alerts that have passed their delay window

        This would typically be called by a scheduled job or daemon.

        Returns:
            dict: Processing statistics
        """
        if not self.enabled:
            return {'processed': 0, 'message': 'Social posting disabled'}

        # Get social poster
        if not self._social_poster:
            self._init_social_poster()

        # Find eligible alerts past their delay window
        cutoff_time = now_eastern() - timedelta(minutes=self.delay_minutes)

        query = '''
            SELECT id, symbol, significance_score, premium_value, alert_timestamp
            FROM flow_alerts
            WHERE alert_timestamp < ?
                AND social_posted = FALSE
                AND significance_score >= ?
                AND premium_value >= ?
            ORDER BY significance_score DESC, premium_value DESC
            LIMIT 10
        '''

        criteria = self.social_config.get('selection_criteria', {})
        min_score = criteria.get('min_significance_score', 9.0)
        min_premium = criteria.get('min_premium_value', 5000000)

        eligible = self.storage.query_with_params(
            query,
            (cutoff_time.isoformat(), min_score, min_premium)
        )

        if not eligible:
            logging.info("No eligible alerts in queue")
            return {'processed': 0, 'message': 'No eligible alerts'}

        # Process each alert
        results = []
        for alert in eligible:
            alert_id = alert['id']

            logging.info(f"Processing queued alert {alert_id} for social posting...")

            # Process with social poster
            result = self._social_poster.process_alert(alert_id)

            results.append({
                'alert_id': alert_id,
                'symbol': alert['symbol'],
                'result': result
            })

            # Show result
            if result['status'] == 'draft_created':
                logging.info(f"✅ Draft created for alert {alert_id}")
            elif result['status'] == 'posted':
                logging.info(f"✅ Posted alert {alert_id} to social media")
            else:
                logging.warning(f"⚠️  Alert {alert_id} status: {result['status']} - {result['message']}")

        return {
            'processed': len(results),
            'results': results,
            'message': f'Processed {len(results)} alerts'
        }

    def _get_alert_data(self, alert_id):
        """Get alert data from database

        Args:
            alert_id: Alert ID

        Returns:
            dict or None: Alert data
        """
        query = 'SELECT * FROM flow_alerts WHERE id = ?'
        results = self.storage.query_with_params(query, (alert_id,))
        return dict(results[0]) if results else None

    def _quick_eligibility_check(self, alert_data):
        """Quick check if alert might be eligible

        Detailed check happens in social_poster

        Args:
            alert_data: Alert dictionary

        Returns:
            bool: True if potentially eligible
        """
        criteria = self.social_config.get('selection_criteria', {})

        # Check basic thresholds
        score = alert_data.get('significance_score', 0) or 0
        premium = alert_data.get('premium_value', 0) or 0

        min_score = criteria.get('min_significance_score', 9.0)
        min_premium = criteria.get('min_premium_value', 5000000)

        return score >= min_score and premium >= min_premium

    def _already_queued(self, alert_id):
        """Check if alert is already queued or posted

        Args:
            alert_id: Alert ID

        Returns:
            bool: True if already queued
        """
        query = '''
            SELECT COUNT(*) as count
            FROM social_posts
            WHERE alert_id = ?
        '''

        results = self.storage.query_with_params(query, (alert_id,))
        return results[0]['count'] > 0 if results else False

    def _init_social_poster(self):
        """Initialize social poster (lazy load)"""
        from tools.social_poster import SocialPoster

        self._social_poster = SocialPoster(self.config, self.storage)
        logging.info("Social poster initialized")


def main():
    """Test/demo function - process queue manually"""
    import argparse
    import sys
    from pathlib import Path

    # Add project paths
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / 'strategies' / 'flow_monitor'))

    from fm_config import FMConfig
    from fm_storage import FlowMonitorStorage

    parser = argparse.ArgumentParser(description='FM Social Notifier - Process Queue')
    parser.add_argument('--check-alert', type=int,
                       help='Check if specific alert should be queued')
    parser.add_argument('--process-queue', action='store_true',
                       help='Process all eligible alerts in queue')

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
        notifier = FMSocialNotifier(full_config, storage)

        if args.check_alert:
            # Check specific alert
            result = notifier.check_alert(args.check_alert)
            print(f"\n{'='*80}")
            print(f"Alert {args.check_alert} check:")
            print(f"  Queued: {result['queued']}")
            print(f"  Message: {result['message']}")
            print(f"{'='*80}\n")

        elif args.process_queue:
            # Process queue
            print(f"\n{'='*80}")
            print("Processing social posting queue...")
            print(f"{'='*80}\n")

            result = notifier.process_queue()

            print(f"\n{'='*80}")
            print(f"Queue processing complete:")
            print(f"  Processed: {result['processed']} alerts")
            print(f"  Message: {result['message']}")

            if result.get('results'):
                print(f"\nResults:")
                for r in result['results']:
                    print(f"  - Alert {r['alert_id']} ({r['symbol']}): {r['result']['status']}")

            print(f"{'='*80}\n")

        else:
            parser.print_help()
            return 1

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
