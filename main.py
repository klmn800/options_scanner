#!/usr/bin/env python3
"""
Options Scanner Clean Orchestrator (main.py)
=============================================
Simple sequential orchestrator for trading strategies.
Runs one complete daily cycle then exits. Launched daily by Task Scheduler.

Clean Architecture:
  6:35 AM  - Morning Option Pipeline (fresh OI for KLMN 800)
           - Earnings Intelligence (signals, watchlist, news, arbitrage)
           - Metadata Collection Pipeline
           - Query Database Sync (morning data + metadata)
           - Morning Views (emailed watchlist)
  9:15 AM  - Flow Monitor Pre-Market (system preparation)
  9:30 AM  - Flow Monitor Market Hours (real-time monitoring)
  4:00 PM  - Flow Monitor Market Close
  4:30 PM  - Flow Monitor Post-Market Analysis (backfill, regime, rollup, evaluation)
           - Evening Option Pipeline (volume-enriched data)
           - Query Database Sync (volume-enriched OI)
           - Airline Play Tracking
           - Query Database Sync (final)
           - Database Backup (datalake_backup.db - daily)
  Friday   - Sector Archive (three-tier retention: 15d/30d/90d)
           - Weekly Backup (datalake_backup_weekly.db - preserved until next Friday)

Friday Night Archive:
  - Three-tier retention strategy (sector-based routing)
  - Tier 1 (15d MOVE): flow_options_scans, flow_alerts (copy mode)
  - Tier 2 (30d MOVE): option_contracts, option_symbol_summary, flow_symbol_summary
  - Tier 3 (90d COPY): historical_prices, earnings_events, news_*, market_daily_summary
  - Output: data/sector_archive/{sector}.db (airlines, technology, etc.)
  - Timeout: Friday 6:30 PM → Monday 5:45 AM cutoff (59 hours)
  - Post-archive: Optimize sector archives (ANALYZE) + VACUUM production

Usage:
  python main.py                      # Full daily cycle (launched by Task Scheduler)
  python main.py --option-morning     # Just morning Option Pipeline
  python main.py --flow-monitor       # Just Flow Monitor
  python main.py --earnings-intel     # Just Earnings Intelligence

Author: Ben (with assistance from Claude)
Date: 2026-01-18
Version: 3.0 - Modular architecture (UI, Calendar, Runners in separate files)
Version: 4.0 - Removed endless loop
"""

import os
import sys
import time
import logging
import argparse

# Set process priority to High (this is the primary function of this computer)
if sys.platform == 'win32':
    import ctypes
    ctypes.windll.kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    ctypes.windll.kernel32.SetPriorityClass.restype = ctypes.c_bool
    _handle = ctypes.windll.kernel32.GetCurrentProcess()
    _result = ctypes.windll.kernel32.SetPriorityClass(_handle, 0x00000080)
    if not _result:
        print("WARNING: Failed to set process priority (error code: {})".format(ctypes.windll.kernel32.GetLastError()))
    else:
        print("Process priority set to HIGH")

# PERMANENT FIX: Force UTF-8 encoding for all operations
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# Add project tools to path
def get_project_root():
    """Get the root directory of the project"""
    return os.path.dirname(os.path.abspath(__file__))

project_root = get_project_root()
tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# Import utilities
from timezone_utils import now_eastern, eastern_date_string, set_simulated_time
from tools.autofix import queue_error

# Import mixin classes for modular orchestrator
from main_ui import OrchestratorUIMixin, _reset_daily_state
from main_calendar import OrchestratorCalendarMixin
from main_runners import OrchestratorRunnersMixin

# Strategy imports (for FMConfig used in __init__)
try:
    from strategies.flow_monitor.fm_config import FMConfig
except ImportError as e:
    try:
        sys.stderr.write("Error importing strategy modules: {}\n".format(e))
        sys.stderr.write("   Make sure you're running from the project root directory\n")
        sys.stderr.flush()
    except:
        pass
    sys.exit(1)


def is_main_already_running():
    """
    Check if another instance of main.py is already running.

    Returns:
        bool: True if another main.py process is found, False otherwise
    """
    import psutil

    current_pid = os.getpid()
    current_script = os.path.abspath(__file__)

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Skip our own process
            if proc.info['pid'] == current_pid:
                continue

            # Check if it's a Python process
            if proc.info['name'] in ['python.exe', 'python3.exe', 'python']:
                cmdline = proc.info.get('cmdline', [])
                if not cmdline:
                    continue

                # Check if main.py is in the command line
                for arg in cmdline:
                    if 'main.py' in arg:
                        # Verify it's the same script path
                        try:
                            arg_path = os.path.abspath(arg)
                            if arg_path == current_script:
                                return True
                        except:
                            # If we can't resolve path, check for simple match
                            if arg.endswith('main.py'):
                                return True

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return False


class CleanOrchestrator(OrchestratorUIMixin, OrchestratorCalendarMixin, OrchestratorRunnersMixin):
    """Sequential orchestrator: runs one complete daily trading cycle then exits.

    Launched by Task Scheduler every weekday. Checks is_trading_day() for holidays.

    Inherits from:
    - OrchestratorUIMixin: Display utilities (beautiful_log, create_status_box, etc.)
    - OrchestratorCalendarMixin: Market calendar (is_trading_day, archive timeout, etc.)
    - OrchestratorRunnersMixin: Pipeline runners (run_morning_option_pipeline, run_flow_monitor, etc.)
    """

    # Single source of truth for daily step order. Used by coffee_break()
    # to dynamically resolve the "Up Next" display. If steps are reordered,
    # only this list needs updating.
    STEP_SEQUENCE = [
        'Morning Option Pipeline',
        'Earnings Intelligence',
        'Metadata Collection',
        'Query Database Sync (Morning)',
        'Morning Views',
        'Flow Monitor',
        'Evening Option Pipeline',
        'Query Database Sync (Evening)',
        'Airline Play Tracking',
        'Query Database Sync (Final)',
        'Daily Backup',
        'Autofix Review',
        # Friday-only (only reached inside `if is_friday:` block)
        'Weekly Backup',
        'Earnings Calendar Refresh',
        'Sector Archive',
        # Phase 6: System Maintenance (always runs last)
        'Performance Collection',
    ]

    def __init__(self):
        """Initialize orchestrator with basic configuration"""
        self.setup_logging()

        # Initialize Tradier client for market calendar
        try:
            from core.tradier_api import TradierDataClient

            # Temporarily suppress logging during initialization
            tradier_logger = logging.getLogger('core.tradier_api')
            config_logger = logging.getLogger('strategies.flow_monitor.fm_config')
            original_tradier_level = tradier_logger.level
            original_config_level = config_logger.level

            tradier_logger.setLevel(logging.CRITICAL)
            config_logger.setLevel(logging.CRITICAL)

            try:
                # Get config for Tradier client
                config = FMConfig()
                cache_dir = os.path.join(project_root, 'cache')
                os.makedirs(cache_dir, exist_ok=True)

                self.tradier_client = TradierDataClient(config.config, cache_dir)
                self.market_calendar_available = True
                self.beautiful_log("Market calendar integration enabled via Tradier API")
            finally:
                # Restore original logging levels
                tradier_logger.setLevel(original_tradier_level)
                config_logger.setLevel(original_config_level)

        except Exception as e:
            self.beautiful_log("Market calendar unavailable - using weekday fallback: {}".format(e), 'warning')
            self.tradier_client = None
            self.market_calendar_available = False

            # Trigger autofix for market calendar initialization failure
            from tools.autofix import handle_error
            handle_error(
                error_type='market_calendar_init_failed',
                context={'error': str(e), 'phase': 'orchestrator_init'},
                severity='ERROR'  # Non-blocking - weekday fallback works
            )

    def setup_logging(self):
        """Configure clean, focused logging with daily file rotation at 6:35 AM"""
        log_dir = os.path.join(project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        # Use date-aware filename for initial file
        log_file = os.path.join(log_dir, 'orchestrator_{}.log'.format(eastern_date_string()))

        # Configure root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # Simple file handler with daily filename
        file_handler = logging.FileHandler(
            log_file,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)

        # Console handler (use stdout directly, no wrapper)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_formatter.default_msec_format = None
        console_handler.setFormatter(console_formatter)

        # Add handlers to root logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # Suppress debug/info messages from other modules during banner display
        logging.getLogger('core.tradier_api').setLevel(logging.WARNING)
        logging.getLogger('strategies.flow_monitor.fm_config').setLevel(logging.WARNING)

    @staticmethod
    def _format_duration(seconds):
        """Format a duration in seconds to a human-readable string.

        Returns:
            Under 1 minute: "42s"
            1-60 minutes: "27.7 min"
            Over 60 minutes: "7h 43m"
        """
        if seconds < 60:
            return "{:.0f}s".format(seconds)
        elif seconds < 3600:
            return "{:.1f} min".format(seconds / 60)
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return "{}h {}m".format(h, m)

    def _print_day_summary(self, results, day_start_time, step_durations=None):
        """Print honest day-end summary from actual collected results.

        Args:
            results: Dict of step_name → result dict/bool/'skipped'
            day_start_time: time.time() when the day started
            step_durations: Dict of step_name → duration_seconds (optional)
        """
        import time as _time
        elapsed = _time.time() - day_start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)

        if step_durations is None:
            step_durations = {}

        # Build per-step status lines
        status_lines = []
        passed = 0
        failed = 0
        skipped = 0

        for step_name, result in results.items():
            if result == 'skipped':
                status_lines.append("  {}: Skipped".format(step_name))
                skipped += 1

            # Expand Flow Monitor into 3 sub-steps (pre-market, market hours, post-market)
            elif step_name == '2. Flow Monitor' and isinstance(result, dict) and 'pre_market' in result:
                fm = result
                fm_total_dur = fm.get('duration_seconds', 0) or step_durations.get(step_name, 0)

                # 2.1 FM Pre-Market
                pm = fm.get('pre_market') or {}
                if isinstance(pm, dict) and pm.get('skipped'):
                    status_lines.append("  2.1 FM Pre-Market: Skipped")
                    skipped += 1
                elif isinstance(pm, dict):
                    pm_ok = pm.get('success', False)
                    pm_dur = " ({})".format(self._format_duration(pm.get('duration_seconds'))) if pm.get('duration_seconds') else ""
                    if pm_ok:
                        status_lines.append("  \u2705 2.1 FM Pre-Market: OK{}".format(pm_dur))
                        passed += 1
                    else:
                        status_lines.append("  \u274c 2.1 FM Pre-Market: FAILED{}".format(pm_dur))
                        failed += 1
                else:
                    status_lines.append("  2.1 FM Pre-Market: Skipped")
                    skipped += 1

                # 2.2 FM Market Hours
                mh = fm.get('market_hours')
                if mh is None:
                    status_lines.append("  2.2 FM Market Hours: Skipped")
                    skipped += 1
                elif isinstance(mh, dict):
                    mh_ok = mh.get('success', False)
                    # Market hours has no direct duration — derive from total minus pre/post
                    pm_dur_s = pm.get('duration_seconds', 0) if isinstance(pm, dict) else 0
                    post_dur_s = fm.get('post_market', {}).get('duration_seconds', 0) if isinstance(fm.get('post_market'), dict) else 0
                    mh_dur_s = fm_total_dur - pm_dur_s - post_dur_s
                    mh_dur_str = " ({})".format(self._format_duration(mh_dur_s)) if mh_dur_s > 0 else ""
                    if mh_ok:
                        status_lines.append("  \u2705 2.2 FM Market Hours: OK{}".format(mh_dur_str))
                        passed += 1
                    else:
                        status_lines.append("  \u274c 2.2 FM Market Hours: FAILED{}".format(mh_dur_str))
                        failed += 1
                else:
                    status_lines.append("  2.2 FM Market Hours: Skipped")
                    skipped += 1

                # 2.3 FM Post-Market
                post = fm.get('post_market') or {}
                if isinstance(post, dict) and post.get('duration_seconds') is not None:
                    post_ok = post.get('success', False)
                    post_dur = " ({})".format(self._format_duration(post.get('duration_seconds')))
                    if post_ok:
                        status_lines.append("  \u2705 2.3 FM Post-Market: OK{}".format(post_dur))
                        passed += 1
                    else:
                        status_lines.append("  \u274c 2.3 FM Post-Market: FAILED{}".format(post_dur))
                        failed += 1
                else:
                    status_lines.append("  2.3 FM Post-Market: Skipped")
                    skipped += 1

            else:
                # Extract success from dict or bool
                success = result.get('success', False) if isinstance(result, dict) else bool(result)
                dur = step_durations.get(step_name)
                dur_str = " ({})".format(self._format_duration(dur)) if dur is not None else ""
                if success:
                    status_lines.append("  \u2705 {}: OK{}".format(step_name, dur_str))
                    passed += 1
                else:
                    status_lines.append("  \u274c {}: FAILED{}".format(step_name, dur_str))
                    failed += 1

        # Summary header
        if failed == 0:
            title = "\U0001f3af TRADING DAY COMPLETE"
        else:
            title = "\U0001f3af TRADING DAY COMPLETE - {} FAILURE{}".format(failed, "S" if failed > 1 else "")

        # Footer lines
        status_lines.append("")
        status_lines.append("Runtime: {}h {}m".format(hours, minutes))
        status_lines.append("Passed: {} | Failed: {} | Skipped: {}".format(passed, failed, skipped))

        self.create_status_box(title, status_lines, success=(failed == 0))

    def run_daily_cycle(self):
        """Run one complete daily trading cycle then exit. Launched by Task Scheduler."""

        # Holiday check — Task Scheduler fires every weekday, skip market holidays
        if not self.is_trading_day():
            self.beautiful_log("Not a trading day (market holiday) — exiting", 'warning')
            self.create_status_box(
                "MARKET HOLIDAY",
                ["Today is not a trading day.", "System will try again next weekday."],
                success=True
            )
            return True

        self.beautiful_log("Starting daily trading cycle", 'phase')

        day_start_time = time.time()

        # Reset daily state for FM session stats, sync performance, news API tracking
        date_str = now_eastern().strftime('%Y-%m-%d')
        results = {}
        step_durations = {}
        _reset_daily_state(date_str)

        # Timing router: Determine where to start based on current time
        now = now_eastern()
        is_friday = now.weekday() == 4

        # After 9:00 AM → Skip directly to Flow Monitor (Phase 2)
        if now.hour >= 9:
            self.beautiful_log("Mid-day start ({}) - skipping to Phase 2".format(now.strftime("%I:%M %p")), 'phase')
            for key in ['1.1 Morning Option Pipeline', '1.2 Earnings Intelligence',
                        '1.3 Metadata Collection', '1.4 Query Sync (Morning)',
                        '1.5 Morning Views']:
                results[key] = 'skipped'

        # Before 9:00 AM → Run morning sequence
        else:
            # ── Phase 1: Pre-Market ──
            self.phase_header("PRE-MARKET OPERATIONS", phase_number=1)

            # Step 1.1: Morning Option Pipeline (with 8:45 AM skip logic)
            if self.should_skip_morning_option_pipeline():
                self.beautiful_log("Skipping Morning Option Pipeline - started after 8:45 AM", 'warning')
                results['1.1 Morning Option Pipeline'] = 'skipped'
            else:
                self.beautiful_log("Step 1.1: Morning Option Pipeline Refresh", 'phase')
                _t0 = time.time()
                results['1.1 Morning Option Pipeline'] = self.run_morning_option_pipeline(test_mode=False)
                step_durations['1.1 Morning Option Pipeline'] = time.time() - _t0

            # Step 1.2: Earnings Intelligence (unified pipeline)
            self.coffee_break(60, "Time for a quick stretch", after_step="Morning Option Pipeline")
            self.beautiful_log("Step 1.2: Earnings Intelligence", 'phase')
            _t0 = time.time()
            results['1.2 Earnings Intelligence'] = self.run_earnings_intelligence()
            step_durations['1.2 Earnings Intelligence'] = time.time() - _t0

            # Step 1.3: Metadata Collection Pipeline (before sync)
            self.coffee_break(60, "Quick coffee break", after_step="Earnings Intelligence")
            self.beautiful_log("Step 1.3: Metadata Collection Pipeline", 'phase')
            _t0 = time.time()
            results['1.3 Metadata Collection'] = self.run_metadata_collection()
            step_durations['1.3 Metadata Collection'] = time.time() - _t0

            # Step 1.4: Query Database Sync (Morning - includes fresh metadata)
            self.beautiful_log("Step 1.4: Query Database Sync (Morning)", 'phase')
            _t0 = time.time()
            results['1.4 Query Sync (Morning)'] = self.run_query_database_sync()
            step_durations['1.4 Query Sync (Morning)'] = time.time() - _t0

            # Brief pause before morning views
            self.coffee_break(60, "Morning cuppa to go with the news", after_step="Query Database Sync (Morning)")

            # Step 1.5: Morning Views Generation
            self.beautiful_log("Step 1.5: Morning Views Generation", 'phase')
            _t0 = time.time()
            results['1.5 Morning Views'] = self.run_morning_views()
            step_durations['1.5 Morning Views'] = time.time() - _t0

        # ── Phase 2: Flow Monitor ──
        self.phase_header("FLOW MONITOR", phase_number=2)
        self.beautiful_log("Step 2: Flow Monitor Pipeline", 'phase')
        _t0 = time.time()
        results['2. Flow Monitor'] = self.run_flow_monitor()
        step_durations['2. Flow Monitor'] = time.time() - _t0

        if not results['2. Flow Monitor']:
            self.beautiful_log("Flow Monitor failed - continuing to evening operations", 'warning')

        # ── Phase 3: Post-Market ──
        self.phase_header("POST-MARKET OPERATIONS", phase_number=3)

        # Step 3.1: Evening Option Pipeline (volume-enriched data)
        self.coffee_break(60, "Taking a well-deserved break", after_step="Flow Monitor")
        self.beautiful_log("Step 3.1: Evening Option Pipeline", 'phase')
        _t0 = time.time()
        results['3.1 Evening Option Pipeline'] = self.run_evening_option_pipeline()
        step_durations['3.1 Evening Option Pipeline'] = time.time() - _t0

        # Step 3.2: Airline Play Tracking Phase
        self.coffee_break(60, "Quick breather before the home stretch", after_step="Evening Option Pipeline")
        self.beautiful_log("Step 3.2: Airline Play Tracking Phase", 'phase')
        _t0 = time.time()
        results['3.2 Airline Play'] = self.run_airline_play_phase()
        step_durations['3.2 Airline Play'] = time.time() - _t0

        # Step 3.3: Query Database Sync (Final)
        self.beautiful_log("Step 3.3: Query Database Sync (Final)", 'phase')
        _t0 = time.time()
        results['3.3 Query Sync (Final)'] = self.run_query_database_sync()
        step_durations['3.3 Query Sync (Final)'] = time.time() - _t0

        # ── Phase 4: Evening Operations ──
        self.phase_header("EVENING OPERATIONS", phase_number=4)

        # Step 4.1: Database Backup - Daily
        self.coffee_break(60, "Final sync complete - waiting for lock release before backup", after_step="Query Database Sync (Final)")
        self.beautiful_log("Step 4.1: Database Backup (Daily)", 'phase')
        _t0 = time.time()
        results['4.1 Daily Backup'] = self.run_database_backup()
        step_durations['4.1 Daily Backup'] = time.time() - _t0

        # Step 4.2: Batch Mode Auto-Fix Review
        self.coffee_break(60, "One more sip before we're done", after_step="Daily Backup")
        self.beautiful_log("Step 4.2: Batch Mode Auto-Fix Review", 'phase')
        _t0 = time.time()
        results['4.2 Autofix Review'] = self.run_batch_mode_review()
        step_durations['4.2 Autofix Review'] = time.time() - _t0

        # ── Phase 5: Friday Operations ──
        if is_friday:
            self.phase_header("FRIDAY OPERATIONS", phase_number=5)

            # Step 5.1: Database Backup - Weekly
            self.coffee_break(60, "Daily backup complete - lock release before weekly backup", after_step="Autofix Review")
            self.beautiful_log("Step 5.1: Database Backup (Weekly)", 'phase')
            _t0 = time.time()
            results['5.1 Weekly Backup'] = self.run_database_backup(backup_type="weekly")
            step_durations['5.1 Weekly Backup'] = time.time() - _t0

            # Step 5.2: FM Baseline Update
            self.coffee_break(60, "Weekly backup complete - lock release before baseline update", after_step="Weekly Backup")
            self.beautiful_log("Step 5.2: FM Baseline Update (Friday)", 'phase')
            _t0 = time.time()
            results['5.2 FM Baseline'] = self.run_fm_baseline_update()
            step_durations['5.2 FM Baseline'] = time.time() - _t0

            # Step 5.3: Weekly Earnings Calendar Refresh
            self.coffee_break(60, "Baseline update complete - lock release before earnings refresh", after_step="FM Baseline Update")
            self.beautiful_log("Step 5.3: Earnings Calendar Refresh (Friday)", 'phase')
            _t0 = time.time()
            results['5.3 Earnings Refresh'] = self.run_earnings_weekly_refresh()
            step_durations['5.3 Earnings Refresh'] = time.time() - _t0

            # Step 5.4: Sector Archive Operations
            self.coffee_break(60, "Earnings refresh complete - lock release before archive", after_step="Earnings Calendar Refresh")
            self.beautiful_log("Step 5.4: Sector Archive Operations (Friday)", 'phase')
            _t0 = time.time()
            results['5.4 Sector Archive'] = self.run_friday_sector_archive()
            step_durations['5.4 Sector Archive'] = time.time() - _t0
        else:
            self.beautiful_log("Phase 5: Weekly operations skipped (not Friday)", 'info')

        # ── Phase 6: System Maintenance ──
        self.phase_header("SYSTEM MAINTENANCE", phase_number=6)

        # Step 6.1: Performance Data Collection
        self.beautiful_log("Step 6.1: Performance Data Collection", 'phase')
        _t0 = time.time()
        results['6.1 Performance Collection'] = self.run_performance_collection(results, step_durations)
        step_durations['6.1 Performance Collection'] = time.time() - _t0

        # ── Day-End Summary ──
        self._print_day_summary(results, day_start_time, step_durations)

        # ── End-of-Day Market Report ──
        self._print_end_of_day_report(results, step_durations, trade_date=date_str)

        self.beautiful_log("Daily cycle complete — process will exit", 'phase')
        return True


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Options Scanner Clean Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                              # Full daily cycle (launched by Task Scheduler)
  python main.py --option-morning             # Just morning Option Pipeline
  python main.py --flow-monitor               # Just Flow Monitor
  python main.py --earnings-intel             # Just Earnings Intelligence pipeline

Testing with Time Simulation (auto-expires after 4 hours by default):
  python main.py --simulate-time "06:35"                  # Simulated 6:35 AM, expires in 4h
  python main.py --simulate-time "17:00" --simulate-ttl 2 # Simulated 5 PM, expires in 2h
  python main.py --simulate-time "09:15" --simulate-ttl 0 # No expiry (persist forever)
        """
    )

    # Execution modes (optional - defaults to full daily cycle)
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument('--option-morning', action='store_true',
                           help='Run morning Option Pipeline only')
    mode_group.add_argument('--option-evening', action='store_true',
                           help='Run evening Option Pipeline only')
    mode_group.add_argument('--flow-monitor', action='store_true',
                           help='Run Flow Monitor only')
    mode_group.add_argument('--earnings-intel', action='store_true',
                           help='Run Earnings Intelligence pipeline only')
    mode_group.add_argument('--morning-views', action='store_true',
                           help='Run morning views generation only')
    mode_group.add_argument('--sector-archive', action='store_true',
                           help='Run sector-based database archive only')
    mode_group.add_argument('--database-backup', action='store_true',
                           help='Run database backup only')
    mode_group.add_argument('--airline-play', action='store_true',
                           help='Run Airline Play tracking only')

    # Additional options
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    parser.add_argument('--simulate-time', type=str, metavar='HH:MM',
                       help='Simulate specific time for testing (e.g., "06:35" for morning Option Pipeline trigger)')
    parser.add_argument('--simulate-ttl', type=float, metavar='HOURS', default=4.0,
                       help='Auto-expire simulated time after N hours (default: 4.0, use 0 for no expiry)')

    return parser.parse_args()


def main():
    """Main entry point"""
    # ===== INSTANCE CHECK =====
    # Check if main.py is already running before doing anything else
    if is_main_already_running():
        print("main.py is already running. This instance will exit.")
        print("  (This is expected behavior when started via Task Scheduler)")
        return 0

    print("No existing main.py instance detected. Starting orchestrator...")
    print()

    try:
        args = parse_arguments()

        # Set simulated time if requested (must be before orchestrator initialization)
        if args.simulate_time:
            try:
                time_parts = args.simulate_time.split(':')
                if len(time_parts) != 2:
                    raise ValueError("Time must be in HH:MM format")
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError("Hour must be 0-23 and minute must be 0-59")
                ttl_hours = args.simulate_ttl if args.simulate_ttl > 0 else None
                set_simulated_time(hour, minute, ttl_hours=ttl_hours)
                print("TIME SIMULATION ENABLED: {}:{:02d}".format(hour, minute))
                if ttl_hours:
                    print("   Auto-expires after {:.1f} hours → reverts to real time".format(ttl_hours))
                else:
                    print("   No TTL set — simulation will persist indefinitely")
                print("   All scheduling logic will use simulated time")
                print()
            except ValueError as e:
                print("Invalid --simulate-time format: {}".format(e))
                print("   Expected format: HH:MM (e.g., '06:35', '17:00')")
                return 1

        # Initialize orchestrator
        orchestrator = CleanOrchestrator()

        # Set debug logging if requested
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        # Handle specific component flags, or default to endless operation
        if args.option_morning:
            orchestrator.print_banner("option-morning")
            success = orchestrator.run_morning_option_pipeline(test_mode=False)
        elif args.option_evening:
            orchestrator.print_banner("option-evening")
            success = orchestrator.run_evening_option_pipeline()
        elif args.flow_monitor:
            orchestrator.print_banner("flow-monitor")
            success = orchestrator.run_flow_monitor()
        elif args.earnings_intel:
            orchestrator.print_banner("earnings-intel")
            success = orchestrator.run_earnings_intelligence()
        elif args.morning_views:
            orchestrator.print_banner("morning-views")
            success = orchestrator.run_morning_views()
        elif args.sector_archive:
            orchestrator.print_banner("sector-archive")
            success = orchestrator.run_sector_archive()
        elif args.database_backup:
            orchestrator.print_banner("database-backup")
            success = orchestrator.run_database_backup()
        elif args.airline_play:
            orchestrator.print_banner("airline-play")
            success = orchestrator.run_airline_play_phase()
        else:
            # Default: Run one complete daily cycle
            orchestrator.print_banner("full")
            success = orchestrator.run_daily_cycle()

        # Exit with appropriate code
        if success:
            try:
                sys.stdout.write("\nOrchestrator completed successfully\n")
                sys.stdout.flush()
            except:
                logging.info("Orchestrator completed successfully")
            return 0
        else:
            try:
                sys.stdout.write("\nOrchestrator completed with errors\n")
                sys.stdout.flush()
            except:
                logging.error("Orchestrator completed with errors")
            return 1

    except KeyboardInterrupt:
        try:
            sys.stdout.write("\nOrchestrator interrupted by user\n")
            sys.stdout.flush()
        except:
            pass
        logging.info("Orchestrator interrupted by user")
        return 0
    except Exception as e:
        queue_error(
            error_type='main_fatal_error',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e)
            },
            severity='ERROR'
        )
        try:
            sys.stderr.write("\nFATAL ERROR: {}\n".format(e))
            sys.stderr.flush()
        except:
            pass
        logging.error("Main fatal error: {}".format(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
