#!/usr/bin/env python3
"""
Main Orchestrator Calendar/Timing Utilities (main_calendar.py)
==============================================================
Market calendar and timing utilities for the options scanner orchestrator.

Contains:
- is_trading_day: Check if date is a trading day (uses Tradier API)
- get_next_trading_day_info: Get next trading day with holiday info
- should_skip_morning_option_pipeline: Check if too late for morning Option Pipeline
- calculate_archive_timeout: Calculate archive operation timeout

Used by: main.py (CleanOrchestrator inherits from OrchestratorCalendarMixin)

Dependencies:
- Requires self.tradier_client and self.market_calendar_available (set in __init__)
- Requires self.beautiful_log and self.create_status_box (from OrchestratorUIMixin)
"""

import logging
from datetime import timedelta

# Add project tools to path
import os
import sys
project_root = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern


class OrchestratorCalendarMixin:
    """Mixin class providing calendar/timing methods for the orchestrator"""

    def get_next_trading_day_info(self):
        """Get detailed information about the next trading day"""
        if self.market_calendar_available and self.tradier_client:
            try:
                calendar_data = self.tradier_client.get_trading_calendar(months_ahead=2)

                if calendar_data:
                    today = now_eastern().date()
                    trading_days = calendar_data.get('trading_days', [])
                    holidays = calendar_data.get('holidays', [])

                    # Find next trading day
                    for i in range(1, 30):  # Look ahead up to 30 days
                        check_date = today + timedelta(days=i)
                        check_date_str = check_date.strftime("%Y-%m-%d")

                        if check_date_str in trading_days:
                            # Find any holidays we're skipping
                            skipped_holidays = []
                            for j in range(1, i):
                                skip_date = today + timedelta(days=j)
                                skip_date_str = skip_date.strftime("%Y-%m-%d")
                                for holiday in holidays:
                                    if holiday.get('date') == skip_date_str:
                                        skipped_holidays.append(holiday)

                            return {
                                'date': check_date,
                                'date_str': check_date_str,
                                'days_away': i,
                                'skipped_holidays': skipped_holidays,
                                'calendar_source': 'tradier_api'
                            }

            except Exception as e:
                self.beautiful_log("Error getting next trading day info: {}".format(e), 'warning')

        # Fallback logic
        today = now_eastern().date()
        for i in range(1, 8):  # Look ahead up to a week
            check_date = today + timedelta(days=i)
            if check_date.weekday() < 5:  # Monday-Friday
                return {
                    'date': check_date,
                    'date_str': check_date.strftime("%Y-%m-%d"),
                    'days_away': i,
                    'skipped_holidays': [],
                    'calendar_source': 'weekday_fallback'
                }

        # Should never reach here, but just in case
        return {
            'date': today + timedelta(days=1),
            'date_str': (today + timedelta(days=1)).strftime("%Y-%m-%d"),
            'days_away': 1,
            'skipped_holidays': [],
            'calendar_source': 'emergency_fallback'
        }

    def is_trading_day(self, date=None):
        """Check if given date is a trading day using Tradier market calendar"""
        if date is None:
            date = now_eastern()

        # Quick weekend check first (even holidays don't override weekends)
        if date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False

        # If market calendar is available, use it for holiday checking
        if self.market_calendar_available and self.tradier_client:
            try:
                # Temporarily suppress logging during calendar check
                tradier_logger = logging.getLogger('core.tradier_api')
                original_level = tradier_logger.level
                tradier_logger.setLevel(logging.CRITICAL)

                try:
                    # Get trading calendar (cached for 24 hours)
                    calendar_data = self.tradier_client.get_trading_calendar(months_ahead=2)
                finally:
                    # Restore logging level
                    tradier_logger.setLevel(original_level)

                if calendar_data:
                    date_str = date.strftime("%Y-%m-%d")

                    # Check if it's explicitly listed as a holiday
                    holidays = calendar_data.get('holidays', [])
                    for holiday in holidays:
                        if holiday.get('date') == date_str:
                            self.beautiful_log("Market holiday detected: {} - {}".format(
                                date_str, holiday.get('description', 'Market Holiday')))
                            return False

                    # Check if it's explicitly listed as a trading day
                    trading_days = calendar_data.get('trading_days', [])
                    if date_str in trading_days:
                        return True

                    # If we have calendar data but date isn't found, it might be too far in future
                    # Fall back to weekday check for recent dates
                    if date.date() <= (now_eastern().date() + timedelta(days=60)):
                        # Within 60 days and not in trading days = probably holiday
                        return False

            except Exception as e:
                self.beautiful_log("Market calendar check failed, using weekday fallback: {}".format(e), 'warning')

        # Fallback: assume all weekdays are trading days
        return True

    def should_skip_morning_option_pipeline(self):
        """Determine if morning Option Pipeline should be skipped due to late start (after 8:45 AM)"""
        now = now_eastern()
        return (now.hour > 8 or (now.hour == 8 and now.minute >= 45))

    def calculate_archive_timeout(self):
        """Calculate seconds available for archiving until 5:45 AM next trading day"""
        now = now_eastern()

        # Get next trading day
        next_trading_info = self.get_next_trading_day_info()
        next_trading_date = next_trading_info['date']

        # Target cutoff is 5:45 AM on next trading day
        cutoff_time = now.replace(
            year=next_trading_date.year,
            month=next_trading_date.month,
            day=next_trading_date.day,
            hour=5,
            minute=45,
            second=0,
            microsecond=0
        )

        # Calculate seconds until cutoff
        time_available = (cutoff_time - now).total_seconds()

        # The get_next_trading_day_info() method already handles weekends and holidays correctly
        # Friday night → Monday morning gives extended time automatically

        # Safety margin of 10 minutes before 5:45 AM cutoff
        time_available -= 600

        return max(0, time_available)
