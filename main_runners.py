#!/usr/bin/env python3
"""
Main Orchestrator Pipeline Runners (main_runners.py)
====================================================
Pipeline runner methods for the options scanner orchestrator.

Contains all run_* methods that execute individual pipelines:
- run_morning_option_pipeline: Morning Option Pipeline (fresh OI data)
- run_flow_monitor: Flow Monitor daily cycle
- run_evening_option_pipeline: Evening Option Pipeline (volume-enriched data)
- run_metadata_collection: Symbol metadata refresh
- run_earnings_pipeline: Earnings Intelligence daily
- run_earnings_morning_scan: Arbitrage scanner
- run_fm_baseline_update: Friday FM volume baseline recalculation
- run_earnings_weekly_refresh: Friday calendar refresh
- run_database_backup: Daily/weekly backup
- run_batch_mode_review: Autofix batch mode
- run_query_database_sync: Query DB sync
- run_sector_archive: Manual sector archive (--sector-archive flag)
- run_friday_sector_archive: Automated Friday archive with Monday cutoff

Used by: main.py (CleanOrchestrator inherits from OrchestratorRunnersMixin)

Dependencies:
- Requires UI methods from OrchestratorUIMixin
- Requires calendar methods from OrchestratorCalendarMixin
- Requires self.tradier_client (set in __init__)
"""

import os
import re
import sys
import time
import logging
import subprocess
import traceback

# Add project root and tools to path
project_root = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern, eastern_date_string
from tools.autofix import queue_error
from tools.log_utils import log_to_file
from main_ui import _save_sync_performance

# Import strategy components (used by runners)
# Note: OPOrchestrator class name is legacy - it runs the Option Pipeline
from strategies.option_pipeline.op_main import OPOrchestrator
from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market
from strategies.earnings_intel.ei_main import run_daily_pipeline
from strategies.earnings_intel.ei_collector import EarningsCollector
from strategies.flow_monitor.fm_baseline_generator import OptionBaselineGenerator
# News collection is now handled inline by Flow Monitor via tools/news_sentiment.py
# (Old 3-tier nc_main.py deprecated 2026-02-07)

# Subprocess output cleanup patterns (compiled once, used per line)
_SUBPROCESS_TIMESTAMP_RE = re.compile(r'^\d{2}:\d{2}:\d{2}\s*-\s*')
_DECORATIVE_BANNER_RE = re.compile(r'^[=\-]{20,}$')


class SubprocessResult:
    """Lightweight result object compatible with subprocess.CompletedProcess.

    Used by _run_streaming_subprocess to return results that work with
    log_subprocess_error() and display_autofix_output() in main_ui.py.
    """
    def __init__(self, returncode, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class OrchestratorRunnersMixin:
    """Mixin class providing pipeline runner methods for the orchestrator"""

    def _run_streaming_subprocess(self, cmd, cwd=None, timeout=None):
        """Run subprocess with real-time output streaming + capture.

        Unlike subprocess.run(capture_output=True), this displays each line
        to console as it arrives AND captures all output for later analysis.
        This prevents multi-hour archive runs from producing zero visibility.

        Args:
            cmd: Command list (e.g. [sys.executable, script_path, '--flag'])
            cwd: Working directory (defaults to project_root)
            timeout: Max seconds before terminating (None = no limit).
                     Raises subprocess.TimeoutExpired if exceeded.

        Returns:
            SubprocessResult: Object with .returncode, .stdout, .stderr attributes
        """
        if cwd is None:
            cwd = project_root

        # Ensure subprocess inherits UTF-8 encoding
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=cwd,
            env=env
        )

        output_lines = []
        start_time = time.time()

        try:
            while True:
                # Check timeout
                if timeout is not None and (time.time() - start_time) > timeout:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise subprocess.TimeoutExpired(cmd, timeout, output='\n'.join(output_lines))

                line = process.stdout.readline()
                if line == '' and process.poll() is not None:
                    break
                if line:
                    stripped = line.rstrip('\n\r')
                    output_lines.append(stripped)
                    # Stream to console in real-time
                    try:
                        sys.stdout.write(stripped + '\n')
                        sys.stdout.flush()
                    except (ValueError, OSError):
                        pass  # stdout closed
                    # Forward to log file (clean subprocess formatting artifacts)
                    log_line = stripped
                    # Strip full logging-format prefix (e.g. "2026-03-11 07:01:22 - INFO - ...")
                    for sep in (' - INFO - ', ' - WARNING - ', ' - ERROR - ', ' - DEBUG - '):
                        if sep in log_line:
                            log_line = log_line.split(sep, 1)[1]
                            break
                    # Strip subprocess HH:MM:SS timestamp prefix
                    log_line = _SUBPROCESS_TIMESTAMP_RE.sub('', log_line)
                    # Skip decorative banners (pure === or --- lines)
                    if _DECORATIVE_BANNER_RE.match(log_line.strip()):
                        continue
                    if log_line.strip():
                        log_to_file(log_line)

            return_code = process.poll()
            captured = '\n'.join(output_lines)
            return SubprocessResult(returncode=return_code, stdout=captured, stderr='')

        except subprocess.TimeoutExpired:
            raise  # Re-raise for caller to handle
        except Exception as e:
            # If something unexpected happens, try to clean up
            try:
                process.terminate()
            except:
                pass
            captured = '\n'.join(output_lines)
            return SubprocessResult(returncode=-1, stdout=captured, stderr=str(e))

    def _display_session_summary(self, session_stats):
        """Build and display a summary box from FM session stats dict.

        Args:
            session_stats: dict from FMSessionStats.get_summary()
        """
        lines = []

        # Cycle overview
        total = session_stats.get('total_cycles', 0)
        successful = session_stats.get('successful_cycles', 0)
        failed = session_stats.get('failed_cycles', 0)
        lines.append("Cycles: {} ({} successful, {} failed)".format(total, successful, failed))

        # Timing stats
        timing = session_stats.get('timing', {})
        if timing:
            avg = timing.get('avg_cycle', 0)
            fastest = timing.get('min_cycle', 0)
            slowest = timing.get('max_cycle', 0)
            lines.append("Avg cycle: {:.1f}s | Fastest: {:.1f}s | Slowest: {:.1f}s".format(avg, fastest, slowest))

            # Per-phase breakdown (data already in FMSessionStats)
            avg_collection = timing.get('avg_collection', 0)
            avg_storage = timing.get('avg_storage', 0)
            avg_analysis = timing.get('avg_analysis', 0)
            avg_alert = timing.get('avg_alert', 0)
            if avg_collection > 0:
                api_time = avg_collection - avg_storage
                lines.append("  Collection: avg {:.1f}s (API: {:.0f}s + DB: {:.0f}s)".format(
                    avg_collection, api_time, avg_storage))
            avg_query = timing.get('avg_analysis_query', 0)
            avg_scoring = timing.get('avg_analysis_scoring', 0)
            avg_db_write = timing.get('avg_analysis_db_write', 0)
            if avg_analysis > 0 and avg_query > 0:
                lines.append("  Analysis:   avg {:.1f}s (Query: {:.1f}s + Score: {:.1f}s + DB: {:.1f}s)".format(
                    avg_analysis, avg_query, avg_scoring, avg_db_write))
            elif avg_analysis > 0:
                lines.append("  Analysis:   avg {:.1f}s".format(avg_analysis))
            if avg_alert > 0:
                lines.append("  Alerts:     avg {:.1f}s".format(avg_alert))

        # Collection errors
        errors = session_stats.get('errors', {})
        total_errors = errors.get('total', 0)
        if total_errors > 0:
            by_type = errors.get('by_type', {})
            type_parts = []
            for etype in ['timeout', 'rate_limit', 'connection', 'other']:
                count = by_type.get(etype, 0)
                if count > 0:
                    type_parts.append("{} {}".format(count, etype))
            lines.append("")
            lines.append("Collection Errors: {} total ({})".format(total_errors, ", ".join(type_parts)))

        # Missing quotes
        mq = session_stats.get('missing_quotes', {})
        mq_total = mq.get('total_symbols', 0)
        if mq_total > 0:
            always = mq.get('always_missing', [])
            if always:
                lines.append("Missing Quotes: {} symbols (every cycle: {})".format(
                    mq_total, ", ".join(always[:8]) + ("..." if len(always) > 8 else "")))
            else:
                lines.append("Missing Quotes: {} symbols (intermittent)".format(mq_total))

        # Failed options
        fo = session_stats.get('failed_options', {})
        fo_total = fo.get('total_symbols', 0)
        if fo_total > 0:
            lines.append("Failed Options: {} symbols".format(fo_total))

        # News enrichment
        news = session_stats.get('news_enrichment', {})
        news_enriched = news.get('enriched', 0)
        news_skipped = news.get('skipped', 0)
        news_failed = news.get('failed', 0)
        news_total = news_enriched + news_skipped + news_failed
        if news_total > 0:
            lines.append("")
            parts = []
            if news_enriched:
                parts.append("{} enriched".format(news_enriched))
            if news_skipped:
                parts.append("{} skipped".format(news_skipped))
            if news_failed:
                parts.append("{} failed".format(news_failed))
            lines.append("News sentiment: {}".format(", ".join(parts)))

        self.create_status_box("MARKET HOURS SESSION SUMMARY", lines)

    def run_morning_option_pipeline(self, test_mode=False):
        """Run Option Pipeline for morning analysis (fresh Open Interest data)"""
        self.create_status_box(
            "🌅 MORNING OPTION PIPELINE REFRESH",
            [
                "Objective: Refresh Option Contract tables with OI data",
                "Steps: Collection → Rollup → OI Timing → Health Report",
                "Universe: KLMN 800{}".format(" (Test Mode)" if test_mode else ""),
                "Timing: Completes before Flow Monitor starts at 9:15 AM"
            ]
        )

        # Assign trade_date BEFORE the try block so the except handler can always
        # reference it. The OPOrchestrator constructor performs a Tradier
        # connection test that can raise on a transient API failure (e.g. a
        # spurious 401 "Invalid Access Token" that self-heals within minutes). If
        # trade_date were assigned inside the try (after construction), that early
        # failure would make the error handler's handle_error() call throw
        # UnboundLocalError on trade_date — masking the real error and escalating a
        # recoverable blip into a main_fatal_error that kills the orchestrator.
        trade_date = eastern_date_string()

        try:
            # Initialize Option Pipeline orchestrator
            op = OPOrchestrator(no_interaction=True)

            # Run the pipeline
            results = op.run_pipeline(
                trade_date=trade_date,
                symbol=None,  # Full universe
                skip_rollup=False
            )

            if results.get('success'):
                # Show meaningful results
                collection = results.get('collection', {})
                analysis = results.get('analysis', {})
                rollup = results.get('rollup', {})
                timing = results.get('timing', {})

                symbols_ok = collection.get('symbols_collected', 0)
                symbols_failed = collection.get('symbols_failed', 0)
                symbols_total = symbols_ok + symbols_failed
                symbols_pct = (symbols_ok / max(symbols_total, 1)) * 100

                status_lines = [
                    "Trade Date: {}".format(trade_date),
                    "Symbols: {:,}/{:,} ({:.1f}%)".format(symbols_ok, symbols_total, symbols_pct),
                    "Total Contracts: {:,}".format(collection.get('total_contracts', 0)),
                ]

                # Add rollup info if available
                if rollup.get('success'):
                    status_lines.append("Symbol Summaries: {:,}".format(rollup.get('summaries_created', 0)))

                # Add timing info if available
                if timing.get('success'):
                    status_lines.append("OI Timing Calculated: {:,} contracts".format(timing.get('contracts_updated', 0)))

                # Duration
                total_secs = results.get('total_execution_time', 0)
                m, s = int(total_secs // 60), int(total_secs % 60)
                status_lines.append("Duration: {}m {}s".format(m, s))

                # Data quality: OI filter ratio
                total_seen = collection.get('total_options_seen', 0)
                total_filtered = collection.get('total_options_filtered', 0)
                if total_seen > 0:
                    filter_pct = (total_filtered / total_seen) * 100
                    status_lines.append("OI Filter: {:,}/{:,} options filtered ({:.1f}%)".format(
                        total_filtered, total_seen, filter_pct))

                # Failed symbols (conditional)
                if symbols_failed > 0:
                    failed_list = collection.get('failed_symbols', [])
                    if failed_list:
                        preview = ", ".join(failed_list[:8])
                        if len(failed_list) > 8:
                            preview += " ...+{}".format(len(failed_list) - 8)
                        status_lines.append("Failed: {} ({})".format(symbols_failed, preview))
                    else:
                        status_lines.append("Failed: {}".format(symbols_failed))

                # No-contract detail (conditional)
                no_contract_count = collection.get('no_contract_count', 0)
                if no_contract_count > 0:
                    no_contract_list = collection.get('no_contract_symbols', [])
                    preview = ", ".join(no_contract_list[:8])
                    if len(no_contract_list) > 8:
                        preview += " ...+{}".format(len(no_contract_list) - 8)
                    status_lines.append("No Contracts: {} ({})".format(no_contract_count, preview))

                self.create_status_box("🎯 MORNING OPTION PIPELINE COMPLETE", status_lines)

                return results
            else:
                self.beautiful_log("Morning Option Pipeline failed: {}".format(results.get('message', 'Unknown error')), 'error')

                # AUTOFIX INTEGRATION: Option Pipeline returned success: False
                from tools.autofix import handle_error
                handle_error(
                    error_type='op_pipeline_failed',
                    context={
                        'message': results.get('message', 'Unknown error'),
                        'collection': results.get('collection', {}),
                        'analysis': results.get('analysis', {}),
                        'rollup': results.get('rollup', {}),
                        'timing': results.get('timing', {}),
                        'errors': results.get('errors', []),
                        'health_status': results.get('health', {}).get('pipeline_health', {}).get('overall_status', 'UNKNOWN'),
                        'trade_date': trade_date,
                        'main_py_pid': os.getpid(),  # main.py is the parent
                        'performance_db': 'data/performance.db'
                    },
                    severity='CRITICAL'
                )
                # Never reached - handle_error exits
                return {'success': False, 'error': results.get('message', 'Unknown error')}

        except Exception as e:
            queue_error(
                error_type='op_pipeline_fatal_error',
                context={
                    'phase': 'morning',
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("Morning Option Pipeline encountered fatal error: {}".format(e), 'error')

            # AUTOFIX INTEGRATION: Option Pipeline crash
            from tools.autofix import handle_error
            handle_error(
                error_type='op_pipeline_unexpected_error',
                context={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': traceback.format_exc(),
                    'phase': 'morning_option_pipeline',
                    'trade_date': trade_date,
                    'location': 'main.py',
                    'main_py_pid': os.getpid(),
                    'performance_db': 'data/performance.db'
                },
                severity='CRITICAL'
            )
            # Never reached - handle_error exits
            return {'success': False, 'error': str(e)}

    def run_flow_monitor(self):
        """Run complete Flow Monitor daily cycle with clean orchestration"""
        self.create_status_box(
            "📈 FLOW MONITOR PIPELINE",
            [
                "Mission: Complete daily options flow monitoring cycle",
                "Pre-Market: System preparation and setup",
                "Market Hours: Pre-open scan at 9:15, real-time flow 9:30 AM - 4:00 PM",
                "Post-Market (4:30 PM):",
                "  1. Historical backfill    3. Symbol rollup",
                "  2. Market regime summary  4. Evaluation + cleanup"
            ]
        )

        fm_start_time = time.time()

        try:
            # Smart timing logic - check current time to determine where to start
            now = now_eastern()
            current_hour = now.hour
            current_minute = now.minute

            # Determine market phase based on current time
            is_during_market_hours = ((current_hour == 9 and current_minute >= 30) or
                                     (current_hour >= 10 and current_hour < 16))
            is_after_market = current_hour >= 16
            ta_status = "Skipped"

            # Skip pre-market if we're already past it or during market hours
            if is_during_market_hours:
                self.beautiful_log("Market hours detected ({}) - skipping pre-market preparation, jumping straight to market monitoring!".format(
                    now.strftime("%I:%M %p")), 'phase')
                pre_market_result = {'success': True, 'skipped': True, 'alerts_resolved': 0, 'symbols_updated': 0}
            elif is_after_market:
                self.beautiful_log("Post-market hours detected ({}) - market phases already complete".format(
                    now.strftime("%I:%M %p")), 'phase')
                pre_market_result = {'success': True, 'skipped': True, 'alerts_resolved': 0, 'symbols_updated': 0}
                # Skip directly to post-market phase
            else:
                # Pre-market prep runs immediately after Phase 1 (no time gate)
                # Market hours monitoring has its own 9:30 AM wait downstream
                self.create_status_box(
                    "🔍 PRE-MARKET PREPARATION",
                    [
                        "Step 1: Alert Resolution — resolve yesterday's open alerts",
                        "Step 2: Sentiment Update — label watchlist entries",
                        "Step 3: Database Sync — push updates to query database",
                    ]
                )

                pre_market_result = run_pre_market()

                # Build pre-market completion box from return dict
                if isinstance(pre_market_result, dict) and pre_market_result.get('success'):
                    pm_lines = []
                    sub = pre_market_result.get('sub_tasks', {})
                    ar = sub.get('alert_resolution', {})
                    if ar.get('alerts_resolved', 0) > 0:
                        pm_lines.append("Alerts resolved: {} ({} BUILDING, {} CLOSING, {} NEUTRAL)".format(
                            ar['alerts_resolved'], ar.get('building', 0), ar.get('closing', 0), ar.get('neutral', 0)))
                    else:
                        pm_lines.append("Alerts resolved: none pending")
                    su = sub.get('sentiment_update', {})
                    if su.get('symbols_updated', 0) > 0:
                        pm_lines.append("Watchlist updated: {} symbols".format(su['symbols_updated']))
                    sy = sub.get('sync', {})
                    if sy.get('success'):
                        pm_lines.append("Query DB synced ({} alerts, {} watchlist rows)".format(
                            sy.get('alerts_synced', 0), sy.get('watchlist_synced', 0)))
                    else:
                        pm_lines.append("Query DB sync: skipped or failed")
                    duration = pre_market_result.get('duration_seconds', 0)
                    pm_lines.append("Duration: {:.1f}s".format(duration))
                    self.create_status_box("✅ PRE-MARKET PREPARATION COMPLETE", pm_lines)

                # Step 2.2: Trading Advisor Agent (fire-and-forget)
                self.beautiful_log("Step 2.2: Trading Advisor Agent (pilot)", 'phase')
                self.beautiful_log("Loading Trading Advisor morning brief in new window...", 'info')
                ta_status = self._launch_trading_advisor()

            pre_market_success = pre_market_result.get('success', False) if isinstance(pre_market_result, dict) else bool(pre_market_result)

            # Initialize market hours variables (may be skipped if after-hours)
            session_stats = {}
            market_hours_result = None

            # Market hours: Only run if not after market close
            if not is_after_market:
                # Wait until exactly 9:15 AM (pre-open scan starts 15 min early to capture
                # pre-market values; cycle 1 runs at 9:15, then waits until 9:30 for cycle 2)
                print("")
                print("")
                now = now_eastern()
                if now.hour < 9 or (now.hour == 9 and now.minute < 15):
                    target = now.replace(hour=9, minute=15, second=0, microsecond=0)
                    wait_seconds = (target - now).total_seconds()
                    if wait_seconds > 0:
                        self.beautiful_log("Waiting until 9:15 AM for pre-open scan ({:.1f} minutes)".format(wait_seconds / 60), 'info')
                        time.sleep(wait_seconds)

                self.beautiful_log("Running market hours monitoring (collector/analyzer/alerts)", 'phase')
                market_hours_result = run_market_hours(early_start=True)  # Runs until market closes at 4:00 PM

                # Unpack result (dict with success/stats, or bool for backwards compat)
                if isinstance(market_hours_result, dict):
                    market_hours_success = market_hours_result.get('success', False)
                    news_enrichment = market_hours_result.get('news_enrichment', {})
                    total_cycles = market_hours_result.get('total_cycles', 0)

                    # Display session stats summary box
                    session_stats = market_hours_result.get('session_stats', {})
                    if session_stats and session_stats.get('total_cycles', 0) > 0:
                        self._display_session_summary(session_stats)
                else:
                    market_hours_success = bool(market_hours_result)

                # AUTOFIX INTEGRATION: Check market hours success
                if not market_hours_success:
                    from tools.autofix import handle_error
                    handle_error(
                        error_type='fm_pipeline_failed',
                        context={
                            'message': 'Flow Monitor market hours monitoring returned failure',
                            'pre_market_result': pre_market_result if 'pre_market_result' in locals() else None,
                            'market_hours_success': False,
                            'trade_date': now_eastern().strftime('%Y-%m-%d'),
                            'phase': 'market_hours',
                            'location': 'main.py',
                            'main_py_pid': os.getpid(),  # main.py is parent
                            'performance_db': 'data/performance.db'
                        },
                        severity='CRITICAL'
                    )
                    # Never reached - handle_error exits
            else:
                market_hours_success = True  # Skipped after-hours

            # Post-market: Wait until exactly 4:30 PM (allow time for data settlement after market close)
            now = now_eastern()
            if now.hour < 16 or (now.hour == 16 and now.minute < 30):
                target = now.replace(hour=16, minute=30, second=0, microsecond=0)
                wait_seconds = (target - now).total_seconds()
                if wait_seconds > 0:
                    self.beautiful_log("Waiting until 4:30 PM for post-market analysis ({:.1f} minutes)".format(wait_seconds / 60), 'info')
                    time.sleep(wait_seconds)

            self.beautiful_log("Running post-market analysis", 'phase')
            try:
                post_market_result = run_post_market()
            except UnicodeEncodeError as e:
                self.beautiful_log("Post-market analysis had encoding issues (non-critical): {}".format(e), 'warning')
                self.beautiful_log("CONTINUING PIPELINE - encoding errors should not stop evening operations", 'warning')
                post_market_result = {'success': False, 'tasks_successful': 0, 'tasks_total': 5, 'errors': 1, 'sub_tasks': {}}
            except Exception as e:
                self.beautiful_log("Post-market analysis error (continuing pipeline): {}".format(e), 'warning')
                post_market_result = {'success': False, 'tasks_successful': 0, 'tasks_total': 5, 'errors': 1, 'sub_tasks': {}}

            post_market_success = post_market_result.get('success', False) if isinstance(post_market_result, dict) else bool(post_market_result)

            # Show completion status
            # Build pre-market detail lines from dict
            pre_market_lines = []
            if isinstance(pre_market_result, dict) and not pre_market_result.get('skipped'):
                alerts_resolved = pre_market_result.get('alerts_resolved', 0)
                if alerts_resolved > 0:
                    sub = pre_market_result.get('sub_tasks', {}).get('alert_resolution', {})
                    pre_market_lines.append("  Alerts resolved: {} ({} building, {} closing, {} neutral)".format(
                        alerts_resolved, sub.get('building', 0), sub.get('closing', 0), sub.get('neutral', 0)))
                symbols_updated = pre_market_result.get('symbols_updated', 0)
                if symbols_updated > 0:
                    pre_market_lines.append("  Sentiment updated: {} symbols".format(symbols_updated))
                sync_sub = pre_market_result.get('sub_tasks', {}).get('sync', {})
                if sync_sub.get('success'):
                    pre_market_lines.append("  Query DB synced")

            # Build market hours detail lines from session stats
            market_hours_lines = []
            if session_stats and session_stats.get('total_cycles', 0) > 0:
                tc = session_stats.get('total_cycles', 0)
                sc = session_stats.get('successful_cycles', 0)
                fc = session_stats.get('failed_cycles', 0)
                market_hours_lines.append("  Cycles: {} ({} successful{})".format(
                    tc, sc, ", {} failed".format(fc) if fc > 0 else ""))
                timing = session_stats.get('timing', {})
                if timing and timing.get('avg_cycle', 0) > 0:
                    market_hours_lines.append("  Avg cycle: {:.1f}s | Fastest: {:.1f}s | Slowest: {:.1f}s".format(
                        timing.get('avg_cycle', 0), timing.get('min_cycle', 0), timing.get('max_cycle', 0)))

            # Build post-market detail lines from dict
            post_market_lines = []
            if isinstance(post_market_result, dict) and post_market_result.get('sub_tasks'):
                pm_subs = post_market_result['sub_tasks']
                # Backfill details (enriched with duration)
                bf = pm_subs.get('backfill', {})
                if bf.get('success') and bf.get('symbols_updated'):
                    bf_dur = bf.get('duration_seconds', 0)
                    bf_total = bf.get('symbols_total', bf['symbols_updated'])
                    if bf_dur > 0:
                        post_market_lines.append("  Backfill: {}/{} symbols ({:.1f} min)".format(
                            bf['symbols_updated'], bf_total, bf_dur / 60))
                    else:
                        post_market_lines.append("  Backfill: {}/{} symbols".format(
                            bf['symbols_updated'], bf_total))
                # Regime details
                mr = pm_subs.get('market_regime', {})
                if mr.get('success') and mr.get('regime'):
                    spy_pct = mr.get('spy_change_pct', 0) or 0
                    spy_sign = '+' if spy_pct >= 0 else ''
                    post_market_lines.append("  Regime: {} | {} | SPY {}{}% | VIX {}".format(
                        mr['regime'], mr.get('direction', '?'),
                        spy_sign, "{:.2f}".format(spy_pct),
                        mr.get('vix_close', '?')))
                # Rollup details
                rl = pm_subs.get('symbol_rollup', {})
                if rl.get('success') and rl.get('summaries_created'):
                    post_market_lines.append("  Rollup: {} summaries created".format(rl['summaries_created']))
                # Evaluation details
                ev = pm_subs.get('evaluation', {})
                if ev.get('success'):
                    ev_dur = ev.get('duration_seconds', 0)
                    post_market_lines.append("  Evaluation: complete ({:.1f}s)".format(ev_dur))
                # Watchlist cleanup
                wc = pm_subs.get('watchlist_cleanup', {})
                if wc.get('success') and wc.get('entries_archived', 0) > 0:
                    post_market_lines.append("  Cleanup: {} entries archived".format(wc['entries_archived']))

            # Total FM pipeline duration
            total_fm_elapsed = time.time() - fm_start_time

            completion_lines = [
                "Pre-Market: {} {}".format(
                    "✅" if pre_market_success else "⚠️",
                    "Skipped" if (isinstance(pre_market_result, dict) and pre_market_result.get('skipped')) else "Completed"),
            ] + pre_market_lines + [
                "Trading Advisor: {}".format(ta_status),
            ] + [
                "Market Hours: {} {}".format(
                    "✅" if market_hours_success else "⚠️",
                    "Completed" if market_hours_success else "Failed"),
            ] + market_hours_lines + [
                "Post-Market: {} {}/{} tasks completed".format(
                    "✅" if post_market_success else "⚠️",
                    post_market_result.get('tasks_successful', '?'),
                    post_market_result.get('tasks_total', '?')),
            ] + post_market_lines + [
                "Total Duration: {}".format(self._format_duration(total_fm_elapsed)),
            ]

            self.create_status_box("🎯 FLOW MONITOR COMPLETE", completion_lines)

            return {
                'success': pre_market_success and market_hours_success and post_market_success,
                'pre_market': pre_market_result,
                'market_hours': market_hours_result,
                'post_market': post_market_result,
                'session_stats': session_stats,
                'duration_seconds': total_fm_elapsed,
            }

        except KeyboardInterrupt:
            self.beautiful_log("Flow Monitor interrupted by user", 'warning')
            self.create_status_box("🛑 USER INTERRUPTION",
                                 ["Flow Monitor stopped by Ctrl+C",
                                  "Partial daily cycle may have completed",
                                  "Check logs for pipeline status"], success=False)
            logging.info("Flow Monitor interrupted by user")

            return {'success': False, 'error': 'User interrupted (Ctrl+C)'}

        except Exception as e:
            queue_error(
                error_type='flow_monitor_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("Flow Monitor encountered fatal error: {}".format(e), 'error')

            # AUTOFIX INTEGRATION: main.py caught FM orchestrator crash
            from tools.autofix import handle_error
            handle_error(
                error_type='fm_pipeline_unexpected_error',
                context={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': traceback.format_exc(),
                    'phase': 'flow_monitor_pipeline',
                    'trade_date': now_eastern().strftime('%Y-%m-%d'),
                    'location': 'main.py',
                    'main_py_pid': os.getpid(),
                    'performance_db': 'data/performance.db'
                },
                severity='CRITICAL'
            )
            # Never reached - handle_error exits

            self.create_status_box("💥 FATAL ERROR",
                                 ["Flow Monitor failed",
                                  "Error: {}".format(str(e)[:50]),
                                  "Check logs for details"], success=False)
            logging.error("Flow Monitor error: {}".format(e))
            return {'success': False, 'error': str(e)}

    def run_evening_option_pipeline(self):
        """Run Option Pipeline for evening (volume-enriched data update)"""
        self.create_status_box(
            "🌆 EVENING OPTION PIPELINE UPDATE",
            [
                "Objective: Update option data with end-of-day volume",
                "Steps: Collection → Rollup → OI Timing → Health Report",
                "Universe: KLMN 800",
                "Result: Volume-enriched data for overnight analysis"
            ]
        )

        # Assign trade_date BEFORE the try block so the except handlers can always
        # reference it. OPOrchestrator(no_interaction=True) below performs a Tradier
        # connection test that can raise on a transient API failure (e.g. a spurious
        # 401 "Invalid Access Token"). If trade_date were assigned inside the try
        # (after construction), that early failure would make the error handlers'
        # handle_error() calls throw UnboundLocalError on trade_date — masking the
        # real error and escalating a recoverable blip into a main_fatal_error that
        # kills the orchestrator. Mirrors the morning pipeline fix (2026-06-04).
        trade_date = eastern_date_string()

        try:
            # Initialize Option Pipeline orchestrator
            op = OPOrchestrator(no_interaction=True)

            # Run the pipeline
            results = op.run_pipeline(
                trade_date=trade_date,
                symbol=None,  # Full universe
                skip_rollup=False
            )

            if results.get('success'):
                # Show meaningful results
                collection = results.get('collection', {})
                analysis = results.get('analysis', {})
                rollup = results.get('rollup', {})
                timing = results.get('timing', {})

                symbols_ok = collection.get('symbols_collected', 0)
                symbols_failed = collection.get('symbols_failed', 0)
                symbols_total = symbols_ok + symbols_failed
                symbols_pct = (symbols_ok / max(symbols_total, 1)) * 100

                status_lines = [
                    "Trade Date: {}".format(trade_date),
                    "Symbols: {:,}/{:,} ({:.1f}%)".format(symbols_ok, symbols_total, symbols_pct),
                    "Total Contracts: {:,}".format(collection.get('total_contracts', 0)),
                ]

                # Add rollup info if available
                if rollup.get('success'):
                    status_lines.append("Symbol Summaries: {:,}".format(rollup.get('summaries_created', 0)))

                # Add timing info if available
                if timing.get('success'):
                    status_lines.append("OI Timing Calculated: {:,} contracts".format(timing.get('contracts_updated', 0)))

                # Duration
                total_secs = results.get('total_execution_time', 0)
                m, s = int(total_secs // 60), int(total_secs % 60)
                status_lines.append("Duration: {}m {}s".format(m, s))

                # Data quality: OI filter ratio
                total_seen = collection.get('total_options_seen', 0)
                total_filtered = collection.get('total_options_filtered', 0)
                if total_seen > 0:
                    filter_pct = (total_filtered / total_seen) * 100
                    status_lines.append("OI Filter: {:,}/{:,} options filtered ({:.1f}%)".format(
                        total_filtered, total_seen, filter_pct))

                # Failed symbols (conditional)
                if symbols_failed > 0:
                    failed_list = collection.get('failed_symbols', [])
                    if failed_list:
                        preview = ", ".join(failed_list[:8])
                        if len(failed_list) > 8:
                            preview += " ...+{}".format(len(failed_list) - 8)
                        status_lines.append("Failed: {} ({})".format(symbols_failed, preview))
                    else:
                        status_lines.append("Failed: {}".format(symbols_failed))

                # No-contract detail (conditional)
                no_contract_count = collection.get('no_contract_count', 0)
                if no_contract_count > 0:
                    no_contract_list = collection.get('no_contract_symbols', [])
                    preview = ", ".join(no_contract_list[:8])
                    if len(no_contract_list) > 8:
                        preview += " ...+{}".format(len(no_contract_list) - 8)
                    status_lines.append("No Contracts: {} ({})".format(no_contract_count, preview))

                self.create_status_box("🎯 EVENING OPTION PIPELINE COMPLETE", status_lines)
                return results
            else:
                self.beautiful_log("Evening Option Pipeline failed: {}".format(results.get('message', 'Unknown error')), 'error')

                # AUTOFIX INTEGRATION: Option Pipeline returned success: False
                from tools.autofix import handle_error
                handle_error(
                    error_type='op_pipeline_failed',
                    context={
                        'message': results.get('message', 'Unknown error'),
                        'collection': results.get('collection', {}),
                        'analysis': results.get('analysis', {}),
                        'rollup': results.get('rollup', {}),
                        'timing': results.get('timing', {}),
                        'errors': results.get('errors', []),
                        'health_status': results.get('health', {}).get('pipeline_health', {}).get('overall_status', 'UNKNOWN'),
                        'trade_date': trade_date,
                        'phase': 'evening',
                        'main_py_pid': os.getpid(),
                        'performance_db': 'data/performance.db'
                    },
                    severity='CRITICAL'
                )
                # Never reached - handle_error exits
                return {'success': False, 'error': results.get('message', 'Unknown error')}

        except Exception as e:
            queue_error(
                error_type='op_pipeline_fatal_error',
                context={
                    'phase': 'evening',
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("Evening Option Pipeline encountered fatal error: {}".format(e), 'error')

            # AUTOFIX INTEGRATION: Option Pipeline crash
            from tools.autofix import handle_error
            handle_error(
                error_type='op_pipeline_unexpected_error',
                context={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': traceback.format_exc(),
                    'phase': 'evening_option_pipeline',
                    'trade_date': trade_date,
                    'location': 'main_runners.py',
                    'main_py_pid': os.getpid(),
                    'performance_db': 'data/performance.db'
                },
                severity='CRITICAL'
            )
            # Never reached - handle_error exits
            return {'success': False, 'error': str(e)}

    def _launch_trading_advisor(self):
        """Launch Trading Advisor agent in a new console window (fire-and-forget).

        Spawns a Claude Code session with the morning brief prompt.
        The advisor queries the database, builds a morning brief, and
        stays available for interactive discussion throughout the day.

        Note: the Trading Advisor workspace (agents/trading_advisor/) is a
        separate private repo, gitignored here — see agents/README.md. The
        launch is gated by config.json agents.trading_advisor.

        Returns status string for the completion log.
        """
        from tools.agent_toggle import is_agent_enabled
        if not is_agent_enabled('trading_advisor'):
            self.beautiful_log("Trading Advisor disabled in config.json — skipping launch", 'info')
            return "Disabled in config"

        try:
            bat_file = os.path.join(project_root, 'agents', 'trading_advisor', 'trade_morning.bat')
            if not os.path.exists(bat_file):
                self.beautiful_log("Trading Advisor batch file not found", 'warning')
                return "Launch failed (batch file missing)"

            subprocess.Popen(
                'start "Trading Advisor" cmd /k "{}"'.format(bat_file),
                shell=True,
                cwd=project_root,
            )
            self.beautiful_log("Trading Advisor launched in new window", 'success')
            return "Launched in new window"

        except Exception as e:
            self.beautiful_log("Failed to launch Trading Advisor: {}".format(e), 'warning')
            return "Launch failed ({})".format(str(e)[:40])

    def run_metadata_collection(self):
        """
        Refresh metadata for all tracked symbols using Tradier Fundamentals + Quotes.

        Updates company sector, industry, market cap, beta for KLMN 800 universe.
        Uses Tradier's beta fundamentals endpoint for Morningstar sector/industry codes.
        Beta calculated from 60-day covariance with SPY using historical_prices.

        Duration: ~60 seconds (bulk API calls)
        Rate Limits: 120 req/min (Tradier) - well within budget
        """
        self.create_status_box(
            "🏢 SYMBOL METADATA COLLECTION",
            [
                "Mission: Refresh company sector, industry, market cap, beta",
                "Beta: 60-day covariance calculation with SPY",
                "Dependencies: historical_prices for beta calculation",
                "Source: Tradier Fundamentals + Quotes API"
            ]
        )

        meta_start = time.time()
        try:
            # Run standalone script via streaming subprocess (output goes to console + log file)
            script_path = os.path.join(project_root, 'data', 'symbol_metadata.py')
            result = self._run_streaming_subprocess(
                [sys.executable, script_path, '--no-interaction'],
                timeout=300  # 5 minutes max (expected ~60s)
            )
            meta_duration = time.time() - meta_start

            if result.returncode == 0:
                print("")  # Blank line after output
                self.create_status_box("✅ METADATA COLLECTION COMPLETE", [
                    "Status: Metadata refresh completed successfully",
                ])
                return {'success': True, 'duration_seconds': meta_duration, 'stdout': result.stdout or ''}
            else:
                print("")  # Blank line after output
                self.beautiful_log("❌ METADATA COLLECTION FAILED", 'error')
                queue_error(
                    error_type='metadata_collection_script_failed',
                    context={
                        'return_code': result.returncode,
                        'stdout_tail': (result.stdout or '')[-500:],
                        'stderr_tail': (result.stderr or '')[-500:],
                        'performance_db': 'data/performance.db'
                    },
                    severity='CRITICAL'
                )
                self.create_status_box("❌ METADATA COLLECTION FAILED", [
                    "Metadata collection returned failure status",
                    "Impact: Some symbols may have stale metadata",
                    "System: Continuing with next operations"
                ], success=False)
                return {'success': False, 'duration_seconds': meta_duration, 'stdout': result.stdout or ''}

        except subprocess.TimeoutExpired:
            self.beautiful_log("Metadata collection timed out after 5 minutes", 'error')
            queue_error(
                error_type='metadata_collection_timeout',
                context={
                    'timeout_seconds': 300,
                    'expected_duration': '~60 seconds',
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.create_status_box("⏱️ METADATA COLLECTION TIMEOUT", [
                "Metadata collection exceeded 5-minute timeout",
                "Expected: ~60 seconds for all symbols",
                "Impact: Partial metadata may be updated",
                "System: Continuing with next operations"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - meta_start, 'error': 'timeout'}

        except Exception as e:
            queue_error(
                error_type='metadata_collection_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("Metadata collection encountered fatal error: {}".format(e), 'error')
            self.create_status_box("💥 METADATA COLLECTION FATAL ERROR", [
                "Metadata collection operation crashed",
                "Error: {}".format(str(e)[:60]),
                "Impact: Symbols retain stale metadata",
                "System: Continuing with next operations"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - meta_start, 'error': str(e)}

    def run_trade_ingest(self):
        """Run Trade Ingest Pipeline — parse Robinhood execution emails from Gmail.

        Fast step (~10-30s): searches Gmail for unread execution confirmations,
        parses trade details, inserts into trade_executions table.

        Reads: Gmail API (Robinhood forwarded emails)
        Writes: data/datalake.db (trade_executions)
        """
        self.create_status_box(
            "📋 TRADE INGEST",
            [
                "Mission: Parse Robinhood execution emails from Gmail",
                "Source: klmn800alerts@gmail.com (auto-forwarded)",
                "Output: trade_executions table (dedup by email_message_id)"
            ]
        )

        ingest_start = time.time()
        try:
            script_path = os.path.join(project_root, 'tools', 'trade_ingest.py')
            result = self._run_streaming_subprocess(
                [sys.executable, script_path],
                timeout=120  # 2 minutes max (expected ~10-30s)
            )
            ingest_duration = time.time() - ingest_start

            if result.returncode == 0:
                print("")
                self.create_status_box("✅ TRADE INGEST COMPLETE", [
                    "Duration: {:.0f}s".format(ingest_duration),
                ])
                return {'success': True, 'duration_seconds': ingest_duration, 'stdout': result.stdout or ''}
            else:
                print("")
                self.beautiful_log("Trade ingest returned failure status", 'error')
                self.create_status_box("❌ TRADE INGEST FAILED", [
                    "Trade ingest returned non-zero exit code",
                    "Impact: Recent trades may not be recorded",
                    "System: Continuing with next operations"
                ], success=False)
                return {'success': False, 'duration_seconds': ingest_duration, 'stdout': result.stdout or ''}

        except subprocess.TimeoutExpired:
            self.beautiful_log("Trade ingest timed out after 2 minutes", 'error')
            self.create_status_box("⏱️ TRADE INGEST TIMEOUT", [
                "Trade ingest exceeded 2-minute timeout",
                "System: Continuing with next operations"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - ingest_start, 'error': 'timeout'}

        except Exception as e:
            self.beautiful_log("Trade ingest error: {}".format(e), 'error')
            self.create_status_box("💥 TRADE INGEST ERROR", [
                "Error: {}".format(str(e)[:60]),
                "System: Continuing with next operations"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - ingest_start, 'error': str(e)}

    def run_earnings_intelligence(self):
        """Run unified Earnings Intelligence pipeline (PRD 0008)

        Replaces both run_earnings_pipeline() and run_earnings_morning_scan().
        Calls the 8-sub-step run_daily_pipeline() which handles lite refresh,
        snapshots, archive, post-earnings calc, expected moves, watchlist,
        news, and arbitrage.
        """
        self.create_status_box(
            "📈 EARNINGS INTELLIGENCE",
            [
                "Step 1: Lite earnings refresh (near-term date verification)",
                "Step 2: IV/price snapshot collection (T-7 to T+5 window)",
                "Step 3: Archive past earnings to events",
                "Step 4: Post-earnings calculation (price moves, IV crush)",
                "Step 5: Expected moves & signal recalculation",
                "Step 6: Earnings watchlist population",
                "Step 7: News sentiment enrichment (Alpha Vantage)",
                "Step 8: Sector sympathy arbitrage scan",
                "Output: earnings_watchlist, earnings_moves, alerts"
            ]
        )

        try:
            result = run_daily_pipeline()
        except Exception as e:
            result = {
                'success': False, 'failure_reason': str(e), 'errors': 1,
                'snapshots_created': 0, 'moves_calculated': 0,
                'alerts_triggered': 0, 'alert_details': [],
                'watchlist_count': 0, 'watchlist_new': 0,
                'watchlist_symbols': [], 'signals_updated': 0,
                'watchlist_breakdown': {}, 'news_enriched': 0,
                'arb_opportunities': 0,
            }

        if result.get('success'):
            box_lines = []

            # Sub-step summaries (always show — zero is informative for this pipeline)
            box_lines.append("Snapshots collected: {}".format(result.get('snapshots_created', 0)))
            box_lines.append("Moves calculated: {}".format(
                result.get('moves_calculated', 0)))
            box_lines.append("Signals updated: {}".format(
                result.get('signals_updated', 0)))

            # Watchlist summary
            wl_count = result.get('watchlist_count', 0)
            wl_new = result.get('watchlist_new', 0)
            if wl_count > 0:
                # Signal breakdown (top-level per PRD Req 10)
                breakdown = result.get('watchlist_breakdown', {})
                parts = []
                for sig in ('STRONG BUY', 'BUY', 'WATCH'):
                    cnt = breakdown.get(sig, 0)
                    if cnt > 0:
                        parts.append("{} {}".format(cnt, sig))
                bkdn_str = " ({})".format(", ".join(parts)) if parts else ""
                box_lines.append("Watchlist: {} symbols ({} new){}".format(
                    wl_count, wl_new, bkdn_str))
            else:
                box_lines.append("Watchlist: 0 symbols")

            # News enrichment
            news_enriched = result.get('news_enriched', 0)
            if news_enriched > 0:
                box_lines.append("News enriched: {} symbols".format(news_enriched))

            # Arbitrage
            arb = result.get('arb_opportunities', 0)
            if arb > 0:
                box_lines.append("Arbitrage opportunities: {}".format(arb))

            # Earnings alerts
            alerts_triggered = result.get('alerts_triggered', 0)
            alert_details = result.get('alert_details', [])

            if alerts_triggered > 0 and alert_details:
                signal_counts = {}
                for detail in alert_details:
                    signal = detail.get('signal', 'UNKNOWN')
                    signal_counts[signal] = signal_counts.get(signal, 0) + 1

                signal_parts = []
                for sig in ['STRONG BUY', 'BUY', 'WATCH']:
                    count = signal_counts.get(sig, 0)
                    if count > 0:
                        signal_parts.append("{} {}".format(count, sig))
                for sig, count in signal_counts.items():
                    if sig not in ('STRONG BUY', 'BUY', 'WATCH'):
                        signal_parts.append("{} {}".format(count, sig))

                breakdown_str = ", ".join(signal_parts) if signal_parts else str(alerts_triggered)
                box_lines.append("Earnings alerts: {} ({})".format(
                    alerts_triggered, breakdown_str))

                # Top symbols by relative underpricing
                sorted_details = sorted(alert_details,
                    key=lambda d: d.get('relative_underpricing_pct') or 0,
                    reverse=True)
                show_count = min(5, len(sorted_details))
                top_symbols = []
                for detail in sorted_details[:show_count]:
                    sym = detail.get('symbol', '?')
                    days = detail.get('days_ahead')
                    underpricing = detail.get('relative_underpricing_pct')
                    days_str = "{}d".format(days) if days is not None else "?d"
                    if underpricing is not None:
                        top_symbols.append("{} ({}, {:.0f}%)".format(
                            sym, days_str, underpricing))
                    else:
                        top_symbols.append("{} ({})".format(sym, days_str))
                top_line = "  Top: {}".format(", ".join(top_symbols))
                if alerts_triggered > show_count:
                    top_line += " ...+{} more".format(alerts_triggered - show_count)
                box_lines.append(top_line)
            else:
                box_lines.append("Earnings alerts: {}".format(alerts_triggered))

            box_lines.append("Status: ✅ Pipeline successful")
            self.create_status_box("✅ EARNINGS INTELLIGENCE COMPLETE", box_lines)

            # Watchlist table display
            self._render_earnings_watchlist(result.get('watchlist_symbols', []))

            return result
        else:
            queue_error(
                error_type='earnings_intelligence_failure',
                context={**result, 'performance_db': 'data/performance.db'},
                severity='ERROR'
            )
            failure_reason = result.get('failure_reason', 'Pipeline returned failure status')
            self.create_status_box("❌ EARNINGS INTELLIGENCE FAILED", [
                "Error: {}".format(str(failure_reason)[:80]),
                "Impact: Earnings intelligence incomplete",
                "System: Continuing to next phase"
            ], success=False)
            return result

    def _render_earnings_watchlist(self, watchlist_symbols):
        """Render earnings watchlist as box-drawing tables via print().

        Splits rows into pre-earnings (UPCOMING/TODAY) and post-earnings (T+1/T+2/T+3)
        tables with different column layouts. Post-earnings table shows outcome data
        enriched from earnings_events. Season scorecard shown below post-earnings table.

        Uses double-line box characters matching the status boxes.

        Args:
            watchlist_symbols: List of row dicts from earnings_watchlist
        """
        if not watchlist_symbols:
            print("  No earnings watchlist entries")
            return

        # Split into pre and post earnings
        pre_rows = []
        post_rows = []
        for row in watchlist_symbols:
            status = (row.get('status') or '').upper()
            if status.startswith('T+'):
                post_rows.append(row)
            else:
                pre_rows.append(row)

        # ── Pre-earnings table (existing 12-column layout) ──
        if pre_rows:
            self._render_pre_earnings_table(pre_rows)

        # ── Post-earnings table (8-column outcome layout) ──
        if post_rows:
            self._render_post_earnings_table(post_rows)

    def _render_pre_earnings_table(self, rows):
        """Render pre-earnings table (UPCOMING/TODAY) with decision-focused columns."""
        print("")

        cols = [
            ("Sym",      6, "<"),
            ("Days",     4, ">"),
            ("Time",     4, "<"),
            ("Signal",  10, "<"),
            ("Undr%",    7, ">"),
            ("HistMv",   6, ">"),
            ("StrdMv",   6, ">"),
            ("IV%",      4, ">"),
            ("IVΔ5d",    6, ">"),
            ("Price",    8, ">"),
            ("OI Bal",   8, "<"),
            ("Vol Bal",  8, "<"),
        ]
        _oi_abbrev = {
            'Clear Call Bias': 'Clr Call',
            'Heavy Call': 'Hvy Call',
            'Balanced': 'Balanced',
            'Leans Put': 'Lns Put',
            'Heavy Put': 'Hvy Put',
            'Clear Put Bias': 'Clr Put',
        }
        _vol_abbrev = {
            'Clear Call Vol': 'Clr Call',
            'Heavy Call Vol': 'Hvy Call',
            'Balanced Vol': 'Balanced',
            'Heavy Put Vol': 'Hvy Put',
            'Clear Put Vol': 'Clr Put',
        }
        widths = [w for _, w, _ in cols]

        def hline(left, mid, right):
            return left + mid.join("\u2550" * (w + 2) for w in widths) + right

        def trow(values):
            cells = []
            for val, (_, w, align) in zip(values, cols):
                if align == "<":
                    cells.append(" {:<{}} ".format(val, w))
                else:
                    cells.append(" {:>{}} ".format(val, w))
            return "\u2551" + "\u2551".join(cells) + "\u2551"

        print(hline("\u2554", "\u2566", "\u2557"))
        print(trow([h for h, _, _ in cols]))
        print(hline("\u2560", "\u256c", "\u2563"))

        for row in rows:
            days = row.get('days_to_earnings')
            days_str = "{}d".format(days) if days is not None else "-"
            time_str = (row.get('earnings_time') or '-')[:4]
            signal = (row.get('earnings_play_signal') or '-')[:10]
            undr = row.get('relative_underpricing_pct')
            undr_str = "{:.1f}%".format(undr) if undr is not None else "-"
            hist = row.get('historical_avg_move_pct')
            hist_str = "{:.1f}%".format(hist) if hist is not None else "-"
            strd = row.get('straddle_expected_move_pct')
            strd_str = "{:.1f}%".format(strd) if strd is not None else "-"
            iv_pct = row.get('iv_percentile_30d')
            iv_str = "{:.0f}".format(iv_pct) if iv_pct is not None else "-"
            iv_chg = row.get('iv_front_month_change_5d')
            iv_chg_str = "{:+.0f}%".format(iv_chg) if iv_chg is not None else "-"
            price = row.get('current_price')
            price_str = "{:.2f}".format(price) if price else "-"
            oi_raw = row.get('oi_balance_text') or '-'
            oi_str = _oi_abbrev.get(oi_raw, oi_raw[:8])
            vol_raw = row.get('vol_balance_text') or '-'
            vol_str = _vol_abbrev.get(vol_raw, vol_raw[:8])

            print(trow([
                (row.get('symbol') or '?')[:6],
                days_str, time_str, signal, undr_str,
                hist_str, strd_str, iv_str, iv_chg_str,
                price_str, oi_str, vol_str]))

        print(hline("\u255a", "\u2569", "\u255d"))
        print("{} upcoming".format(len(rows)))
        print("")

    def _render_post_earnings_table(self, rows):
        """Render post-earnings table (T+1/T+2/T+3) with outcome-focused columns.

        Enriches rows with outcome data from earnings_events via LEFT JOIN on
        symbol + earnings_date. Shows scorecard summary below the table.
        """
        import sqlite3

        # Enrich with outcome data from earnings_events
        outcome_map = {}
        try:
            db_path = os.path.join('data', 'datalake.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build lookup: (symbol, earnings_date) -> outcome dict
            symbols = [r.get('symbol') for r in rows if r.get('symbol')]
            if symbols:
                placeholders = ','.join('?' for _ in symbols)
                cursor.execute("""
                    SELECT symbol, earnings_date,
                           actual_move_1day_pct, actual_max_move_pct,
                           move_vs_expected_pct, iv_collapse_pct,
                           move_vs_straddle_pct, move_vs_historical_pct,
                           straddle_outcome, signal_accuracy,
                           historical_avg_move_pct
                    FROM earnings_events
                    WHERE symbol IN ({})
                    AND earnings_date >= date('now', '-10 days')
                """.format(placeholders), symbols)
                for erow in cursor.fetchall():
                    key = (erow['symbol'], erow['earnings_date'])
                    outcome_map[key] = dict(erow)

            # Season scorecard query — current quarter
            quarter_month = ((now_eastern().month - 1) // 3) * 3 + 1
            quarter_start = "{}-{:02d}-01".format(now_eastern().year, quarter_month)
            cursor.execute("""
                SELECT earnings_play_signal,
                       COUNT(*) as total,
                       SUM(CASE WHEN ABS(actual_move_1day_pct) >=
                           COALESCE(straddle_expected_move_pct, 999)
                           THEN 1 ELSE 0 END) as beat
                FROM earnings_events
                WHERE earnings_date >= ?
                AND earnings_play_signal IN ('BUY', 'STRONG BUY', 'WATCH')
                AND actual_move_1day_pct IS NOT NULL
                GROUP BY earnings_play_signal
            """, (quarter_start,))
            scorecard_rows = [dict(r) for r in cursor.fetchall()]

            conn.close()
        except Exception as e:
            logging.debug("Post-earnings enrichment error: {}".format(e))
            scorecard_rows = []

        # Merge outcome data into row dicts
        for row in rows:
            key = (row.get('symbol'), row.get('earnings_date'))
            if key in outcome_map:
                outcome = outcome_map[key]
                for col in ('actual_move_1day_pct', 'actual_max_move_pct',
                            'move_vs_expected_pct', 'iv_collapse_pct',
                            'move_vs_straddle_pct', 'move_vs_historical_pct',
                            'straddle_outcome', 'signal_accuracy',
                            'historical_avg_move_pct'):
                    row[col] = outcome.get(col)

        # Post-earnings column layout
        # identity → signal → expectations → outcome → verdicts
        cols = [
            ("Sym",      6, "<"),
            ("T+",       3, ">"),
            ("Signal",  10, "<"),
            ("HistMv",   6, ">"),
            ("StrdMv",   6, ">"),
            ("Actual",   7, ">"),
            ("Peak",     6, ">"),
            ("IVCrsh",   6, ">"),
            ("Trade",    6, "<"),
            ("SigAcc",   7, "<"),
        ]
        widths = [w for _, w, _ in cols]

        def hline(left, mid, right):
            return left + mid.join("\u2550" * (w + 2) for w in widths) + right

        def trow(values):
            cells = []
            for val, (_, w, align) in zip(values, cols):
                if align == "<":
                    cells.append(" {:<{}} ".format(val, w))
                else:
                    cells.append(" {:>{}} ".format(val, w))
            return "\u2551" + "\u2551".join(cells) + "\u2551"

        print(hline("\u2554", "\u2566", "\u2557"))
        print(trow([h for h, _, _ in cols]))
        print(hline("\u2560", "\u256c", "\u2563"))

        for row in rows:
            # T+ number from status
            status = row.get('status') or ''
            t_plus = status.replace('T+', '') if status.startswith('T+') else status

            signal = (row.get('earnings_play_signal') or '-')[:10]

            hist = row.get('historical_avg_move_pct')
            hist_str = "{:.1f}%".format(hist) if hist is not None else "-"

            strd = row.get('straddle_expected_move_pct')
            strd_str = "{:.1f}%".format(strd) if strd is not None else "-"

            actual = row.get('actual_move_1day_pct')
            actual_str = "{:+.1f}%".format(actual) if actual is not None else "PEND"

            peak = row.get('actual_max_move_pct')
            if peak is not None:
                peak_str = "{:.1f}%".format(abs(peak))
            else:
                peak_str = "PEND"

            iv_crush = row.get('iv_collapse_pct')
            if iv_crush is not None:
                iv_crush_str = "{:+.0f}%".format(iv_crush)
            else:
                iv_crush_str = "PEND"

            # Trade outcome: actual vs straddle (was the trade profitable?)
            trade_str = row.get('straddle_outcome') or ''
            if not trade_str and actual is not None and strd and strd > 0:
                # Compute inline if DB column not yet populated
                pct = (abs(actual) / strd) * 100
                if pct >= 110:
                    trade_str = 'PROFIT'
                elif pct >= 95:
                    trade_str = 'FLAT'
                else:
                    trade_str = 'LOSS'
            trade_str = trade_str or 'PEND'

            # Signal accuracy: actual vs our historical prediction
            sig_acc_str = row.get('signal_accuracy') or ''
            if not sig_acc_str and actual is not None and hist and hist > 0:
                pct = (abs(actual) / hist) * 100
                if pct >= 100:
                    sig_acc_str = 'CONFIRM'
                elif pct >= 80:
                    sig_acc_str = 'CLOSE'
                elif pct >= 60:
                    sig_acc_str = 'OVER'
                else:
                    sig_acc_str = 'WAY OFF'
            sig_acc_str = sig_acc_str or 'PEND'

            print(trow([
                (row.get('symbol') or '?')[:6],
                t_plus, signal, hist_str, strd_str,
                actual_str, peak_str, iv_crush_str,
                trade_str, sig_acc_str]))

        print(hline("\u255a", "\u2569", "\u255d"))
        print("{} post-earnings".format(len(rows)))

        # Season scorecard
        if scorecard_rows:
            parts = []
            for srow in scorecard_rows:
                sig = srow['earnings_play_signal']
                total = srow['total']
                beat = srow['beat']
                label = sig
                if sig == 'STRONG BUY':
                    label = 'STR BUY'
                pct = beat * 100 // total if total > 0 else 0
                parts.append("{} {}/{} ({}%)".format(label, beat, total, pct))
            print("Signal Scorecard: {}".format(" | ".join(parts)))

        print("")

    # ─── End-of-Day Market Report ──────────────────────────────────────────

    def _print_end_of_day_report(self, results, step_durations, trade_date=None):
        """Print comprehensive end-of-day market report.

        Called after _print_day_summary(). Queries datalake_query.db for fresh
        data and reads daily_state.json for FM session metrics.

        Args:
            results: Dict of step_name -> result dict from today's run
            step_durations: Dict of step_name -> duration_seconds
            trade_date: Trading day date string (YYYY-MM-DD). Critical for
                        after-midnight runs (e.g. Friday sessions ending Saturday 1 AM).
                        Falls back to now_eastern() if not provided.

        Sections: Market Summary, Flow Activity, Earnings Outlook, System Performance.
        Each section is wrapped in try/except so one failure doesn't block the rest.
        """
        import sqlite3
        import json
        from datetime import datetime

        if trade_date is None:
            trade_date = now_eastern().strftime('%Y-%m-%d')

        # Format day name from the trade_date, not from current time
        try:
            td = datetime.strptime(trade_date, '%Y-%m-%d')
            try:
                day_name = td.strftime('%A, %B %#d, %Y')
            except ValueError:
                day_name = td.strftime('%A, %B %d, %Y')
        except Exception:
            day_name = trade_date

        print("")
        print("")
        self.beautiful_log("END OF DAY REPORT", 'phase')
        print("")

        # Open query DB connection (shared across sections)
        query_db = os.path.join('data', 'datalake_query.db')
        conn = None
        try:
            conn = sqlite3.connect(query_db)
            conn.row_factory = sqlite3.Row
        except Exception as e:
            self.beautiful_log("Cannot open query DB for EOD report: {}".format(e), 'warning')
            return

        try:
            # ── Section 1: Market Summary ──
            self._eod_market_summary(conn, trade_date, day_name)
        except Exception as e:
            self.beautiful_log("Market summary section error: {}".format(e), 'warning')

        try:
            # ── Section 2: Flow Activity ──
            self._eod_flow_activity(conn, trade_date)
        except Exception as e:
            self.beautiful_log("Flow activity section error: {}".format(e), 'warning')

        try:
            # ── Section 3: Earnings Outlook ──
            self._eod_earnings_outlook(conn)
        except Exception as e:
            self.beautiful_log("Earnings outlook section error: {}".format(e), 'warning')

        try:
            # ── Section 4: System Performance ──
            # Load daily_state directly with trade_date matching (not now_eastern())
            # because after midnight the date has rolled over
            daily_state = {}
            try:
                daily_state_path = os.path.join('logs', 'daily_state.json')
                with open(daily_state_path, 'r') as f:
                    state = json.load(f)
                if state.get('date') == trade_date:
                    daily_state = state
            except (FileNotFoundError, json.JSONDecodeError, KeyError):
                pass
            self._eod_system_performance(daily_state)
        except Exception as e:
            self.beautiful_log("System performance section error: {}".format(e), 'warning')

        try:
            # ── Section 5: Symbol Health (conditional) ──
            self._eod_symbol_health(results)
        except Exception as e:
            self.beautiful_log("Symbol health section error: {}".format(e), 'warning')

        if conn:
            conn.close()

    def _eod_market_summary(self, conn, trade_date, day_name):
        """Section 1: Market Summary — regime, indices, breadth, sectors."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM market_daily_summary WHERE trade_date = ?",
            (trade_date,))
        row = cursor.fetchone()

        if not row:
            self.beautiful_log("No market data for {} — skipping market summary".format(trade_date), 'info')
            return

        regime = row['regime_classification'] or '?'
        direction = row['market_direction'] or '?'

        # Format index lines
        def _idx(close, pct):
            if close is None:
                return "   -      "
            sign = '+' if (pct or 0) >= 0 else ''
            return "{:>7.2f} ({}{:.2f}%)".format(close, sign, pct or 0)

        lines = [
            "Regime: {} | {}".format(regime.title(), direction),
            "",
            "SPY {}    QQQ {}".format(
                _idx(row['spy_close'], row['spy_change_percent']),
                _idx(row['qqq_close'], row['qqq_change_percent'])),
            "IWM {}    VIX {}".format(
                _idx(row['iwm_close'], row['iwm_change_percent']),
                _idx(row['vix_close'], row['vix_change_percent'])),
            "TLT {}    GLD {}".format(
                _idx(row['tlt_close'], row['tlt_change_percent']),
                _idx(row['gld_close'], row['gld_change_percent'])),
        ]

        # Breadth
        adv = row['advancing_stocks'] or 0
        dec = row['declining_stocks'] or 0
        highs = row['new_highs'] or 0
        lows = row['new_lows'] or 0
        if adv or dec:
            lines.append("")
            lines.append("Breadth: {} \u25b2 / {} \u25bc | {} new highs, {} new lows".format(
                adv, dec, highs, lows))

        # Fixed-position sector grid (4 columns × 3 rows)
        # Positions are FIXED for visual memory — only values change
        sector_grid = [
            ('XLK', 'xlk_change_percent'),
            ('XLF', 'xlf_change_percent'),
            ('XLV', 'xlv_change_percent'),
            ('XLE', 'xle_change_percent'),
            ('XLY', 'xly_change_percent'),
            ('XLI', 'xli_change_percent'),
            ('XLP', 'xlp_change_percent'),
            ('XLU', 'xlu_change_percent'),
            ('XLB', 'xlb_change_percent'),
            ('XLRE', 'xlre_change_percent'),
        ]

        def _spct(col):
            val = row[col]
            if val is None:
                return "   -  "
            sign = '+' if val >= 0 else ''
            return "{}{:.1f}%".format(sign, val)

        lines.append("")
        lines.append("Sectors:")
        # Row 1: Tech  Fin  Health  Energy
        lines.append("  {:<6} {:>6}    {:<6} {:>6}    {:<6} {:>6}    {:<6} {:>6}".format(
            'Tech', _spct('xlk_change_percent'),
            'Fin', _spct('xlf_change_percent'),
            'Health', _spct('xlv_change_percent'),
            'Energy', _spct('xle_change_percent')))
        # Row 2: Discr  Indust  Staple  Util
        lines.append("  {:<6} {:>6}    {:<6} {:>6}    {:<6} {:>6}    {:<6} {:>6}".format(
            'Discr', _spct('xly_change_percent'),
            'Indust', _spct('xli_change_percent'),
            'Staple', _spct('xlp_change_percent'),
            'Util', _spct('xlu_change_percent')))
        # Row 3: Matrls  RlEst  Jets  Nuclr
        lines.append("  {:<6} {:>6}    {:<6} {:>6}    {:<6} {:>6}    {:<6} {:>6}".format(
            'Matrls', _spct('xlb_change_percent'),
            'RlEst', _spct('xlre_change_percent'),
            'Jets', _spct('jets_change_percent'),
            'Nuclr', _spct('nlr_change_percent')))

        self.create_status_box(
            "\U0001f4ca MARKET SUMMARY \u2014 {}".format(day_name), lines)

    def _eod_flow_activity(self, conn, trade_date):
        """Section 2: Flow Activity — alerts grouped by symbol, watchlist stats."""
        cursor = conn.cursor()

        # Get today's alerts grouped by symbol
        cursor.execute("""
            SELECT symbol, COUNT(*) as alert_count,
                   MAX(significance_score) as max_sig,
                   SUM(CASE WHEN UPPER(option_type) = 'CALL' THEN 1 ELSE 0 END) as calls,
                   SUM(CASE WHEN UPPER(option_type) = 'PUT' THEN 1 ELSE 0 END) as puts
            FROM flow_alerts
            WHERE trade_date = ?
            GROUP BY symbol
            ORDER BY alert_count DESC, max_sig DESC
        """, (trade_date,))
        symbol_groups = cursor.fetchall()

        total_alerts = sum(r['alert_count'] for r in symbol_groups) if symbol_groups else 0
        total_calls = sum(r['calls'] for r in symbol_groups) if symbol_groups else 0
        total_puts = sum(r['puts'] for r in symbol_groups) if symbol_groups else 0

        if total_alerts == 0:
            self.create_status_box("\U0001f525 FLOW ACTIVITY", ["No flow alerts today"])
            return

        # For each top symbol, get the top alert details
        lines = []
        show_count = min(8, len(symbol_groups))
        for i, sg in enumerate(symbol_groups[:show_count]):
            sym = sg['symbol']
            count = sg['alert_count']

            # Get the top alert for this symbol (highest significance)
            cursor.execute("""
                SELECT strike, option_type, expiration_date,
                       significance_score, volume, iv, underlying_price
                FROM flow_alerts
                WHERE trade_date = ? AND symbol = ?
                ORDER BY significance_score DESC
                LIMIT 1
            """, (trade_date, sym))
            top = cursor.fetchone()

            if top:
                # Format: NVDA  (5)  Top: 85C 03/20   Sig 9.2  Vol 12,450  IV 62%  $92
                strike = top['strike']
                otype = 'C' if (top['option_type'] or '').upper() == 'CALL' else 'P'
                exp = top['expiration_date']
                # Format expiration as MM/DD
                try:
                    exp_short = "{}/{}".format(exp[5:7], exp[8:10])
                except (IndexError, TypeError):
                    exp_short = exp or '?'
                sig = top['significance_score'] or 0
                vol = top['volume'] or 0
                iv_val = (top['iv'] or 0) * 100  # Convert decimal to percent
                ul = top['underlying_price'] or 0

                contract_str = "{}{} {}".format(
                    int(strike) if strike == int(strike) else strike,
                    otype, exp_short)

                lines.append("{:<5} ({})  Top: {:<12} Sig {:<4.1f}  Vol {:>6,}  IV {:>3.0f}%  ${:.0f}".format(
                    sym, count, contract_str, sig, vol, iv_val, ul))
            else:
                lines.append("{:<5} ({})".format(sym, count))

        remaining = len(symbol_groups) - show_count
        if remaining > 0:
            lines.append("... +{} more symbol{}".format(remaining, 's' if remaining > 1 else ''))

        # Watchlist stats
        cursor.execute("""
            SELECT COUNT(*) as active,
                   SUM(CASE WHEN dip_detected = 1 THEN 1 ELSE 0 END) as dips
            FROM flow_watchlist_daily
        """)
        wl = cursor.fetchone()
        wl_active = wl['active'] if wl else 0
        wl_dips = wl['dips'] if wl else 0

        lines.append("")
        wl_parts = ["{} active entries".format(wl_active)]
        if wl_dips > 0:
            wl_parts.append("{} dip{} detected".format(wl_dips, 's' if wl_dips > 1 else ''))
        lines.append("Watchlist: {}".format(" | ".join(wl_parts)))

        self.create_status_box(
            "\U0001f525 FLOW ACTIVITY \u2014 {} Alerts ({} Call / {} Put)".format(
                total_alerts, total_calls, total_puts), lines)

    def _eod_earnings_outlook(self, conn):
        """Section 3: Earnings Outlook — reuses _render_earnings_watchlist with fresh data."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM earnings_watchlist
            ORDER BY
                CASE status
                    WHEN 'TODAY' THEN 0
                    WHEN 'T+1' THEN 1
                    WHEN 'T+2' THEN 2
                    WHEN 'T+3' THEN 3
                    WHEN 'UPCOMING' THEN 4
                    ELSE 5
                END,
                days_to_earnings ASC,
                relative_underpricing_pct DESC
        """)
        rows = [dict(r) for r in cursor.fetchall()]

        if not rows:
            self.create_status_box("\U0001f4c5 EARNINGS OUTLOOK",
                                  ["No active earnings watchlist entries"])
            return

        # Count by signal for the header
        signal_counts = {}
        for r in rows:
            sig = r.get('earnings_play_signal', 'UNKNOWN')
            signal_counts[sig] = signal_counts.get(sig, 0) + 1

        signal_parts = []
        for sig in ['STRONG BUY', 'BUY', 'WATCH']:
            if signal_counts.get(sig, 0) > 0:
                signal_parts.append("{} {}".format(signal_counts[sig], sig))

        header = "\U0001f4c5 EARNINGS OUTLOOK \u2014 {} symbols".format(len(rows))
        if signal_parts:
            header += " ({})".format(", ".join(signal_parts))

        self.create_status_box(header, [])
        self._render_earnings_watchlist(rows)

    def _eod_system_performance(self, daily_state):
        """Section 4: System Performance — FM cycle stats, sync, errors, news API."""
        fm_session = daily_state.get('fm_session', {})

        if not fm_session:
            self.create_status_box("\u2699\ufe0f SYSTEM PERFORMANCE",
                                  ["No FM session data available"])
            return

        lines = []

        # Cycle overview
        total = fm_session.get('total_cycles', 0)
        successful = fm_session.get('successful_cycles', 0)
        failed = fm_session.get('failed_cycles', 0)
        lines.append("FM Cycles: {} successful, {} failed".format(successful, failed))

        # Cycle time stats (avg/best/worst)
        timing = fm_session.get('timing', {})
        cycle_times = fm_session.get('cycle_times', [])
        if cycle_times:
            avg_cycle = timing.get('avg_cycle', sum(cycle_times) / len(cycle_times))
            min_cycle = min(cycle_times)
            max_cycle = max(cycle_times)
            lines.append("Cycle Time:  avg {}  |  best {}  |  worst {}".format(
                self._format_duration(avg_cycle),
                self._format_duration(min_cycle),
                self._format_duration(max_cycle)))

        # Quick sync stats (avg/best/worst)
        sync_times = fm_session.get('sync_times', [])
        if sync_times:
            # Filter out zeros (cycles where sync didn't run)
            real_syncs = [s for s in sync_times if s > 0]
            if real_syncs:
                avg_sync = sum(real_syncs) / len(real_syncs)
                min_sync = min(real_syncs)
                max_sync = max(real_syncs)
                lines.append("Quick Sync:  avg {}  |  best {}  |  worst {}".format(
                    self._format_duration(avg_sync),
                    self._format_duration(min_sync),
                    self._format_duration(max_sync)))

        # Phase breakdown
        if timing:
            parts = []
            avg_collection = timing.get('avg_collection', 0)
            avg_analysis = timing.get('avg_analysis', 0)
            avg_alert = timing.get('avg_alert', 0)
            if avg_collection > 0:
                parts.append("Collection: avg {}".format(self._format_duration(avg_collection)))
            if avg_analysis > 0:
                parts.append("Analysis: avg {:.1f}s".format(avg_analysis))
            if avg_alert > 0:
                parts.append("Alerts: avg {:.1f}s".format(avg_alert))
            if parts:
                lines.append("")
                lines.append(" | ".join(parts))

        # Data volume
        contracts = fm_session.get('contracts_collected', [])
        alerts = fm_session.get('alerts_generated', [])
        total_contracts = sum(contracts) if contracts else 0
        total_alerts = sum(alerts) if alerts else 0
        if total_contracts > 0 or total_alerts > 0:
            lines.append("Data: {:,} contracts collected | {} alerts generated".format(
                total_contracts, total_alerts))

        # Errors
        errors = fm_session.get('errors', {})
        total_errors = errors.get('total', 0)
        if total_errors > 0:
            by_type = errors.get('by_type', {})
            type_parts = []
            for etype in ['timeout', 'rate_limit', 'connection', 'other']:
                count = by_type.get(etype, 0)
                if count > 0:
                    type_parts.append("{} {}".format(count, etype))
            lines.append("Errors: {} ({})".format(total_errors, ", ".join(type_parts)))

        # News API usage
        news_api = daily_state.get('news_api_usage', {})
        if news_api:
            calls_total = (news_api.get('calls_ei', 0) +
                          news_api.get('calls_fm', 0) +
                          news_api.get('calls_other', 0))
            remaining = 25 - calls_total  # 25/day budget
            if calls_total > 0:
                lines.append("News API: {}/25 calls used ({} remaining)".format(
                    calls_total, max(0, remaining)))

        self.create_status_box("\u2699\ufe0f SYSTEM PERFORMANCE", lines)

    def _eod_symbol_health(self, results):
        """Section 5: Symbol Health — only shown when there are warnings/suspects/changes."""
        health = results.get('6.2 Symbol Health', {})
        if not health or not health.get('success'):
            return

        if health.get('safety_gate_tripped'):
            return  # Already warned during execution, don't repeat in report

        warnings = health.get('warnings', [])
        suspects = health.get('suspects', [])

        # Also check for recent lifecycle events
        recent_events = []
        try:
            from tools.lifecycle.audit import get_recent_events, get_default_db_path
            recent_events = get_recent_events(get_default_db_path(), days=1)
        except Exception:
            pass

        # Only show section if there's something to report
        if not warnings and not suspects and not recent_events:
            return

        lines = []

        if warnings:
            lines.append("Warnings (3-4 days no data):")
            for sym, last_date, days in warnings:
                lines.append("  {}  last data: {}".format(sym, last_date or 'never'))

        if suspects:
            if lines:
                lines.append("")
            lines.append("Suspects (5+ days no data):")
            for sym, last_date, days in suspects:
                flagged = " [flagged]" if health.get('new_suspects_logged', 0) > 0 else ""
                lines.append("  {}  last data: {}{}".format(sym, last_date or 'never', flagged))

        if recent_events:
            if lines:
                lines.append("")
            lines.append("Recent changes (last 24h):")
            for evt in recent_events[:5]:
                lines.append("  {} {} ({}) — {}".format(
                    evt.get('symbol', '?'),
                    evt.get('event_type', '?'),
                    evt.get('operator', '?'),
                    evt.get('reason', '')[:60]))

        self.create_status_box("SYMBOL HEALTH", lines)

    def run_fm_baseline_update(self):
        """Run Flow Monitor baseline update (Fridays)

        Recalculates option volume baselines for FM universe symbols using
        21-day lookback of flow_options_scans data. Writes to symbol_baselines
        table in production datalake.db.

        Returns:
            dict: {success, duration_seconds, symbols_processed, baselines_created,
                   baselines_updated, error_count, failed_symbols}
        """
        self.create_status_box(
            "FM BASELINE UPDATE",
            [
                "Mission: Recalculate option volume baselines for FM universe",
                "Source: flow_options_scans (21-day lookback)",
                "Target: symbol_baselines table (388 FM symbols)",
                "Schedule: Friday before earnings refresh and sector archive"
            ]
        )

        step_start = time.time()
        try:
            generator = OptionBaselineGenerator()
            raw_result = generator.generate_baselines(lookback_days=21)
            duration = time.time() - step_start

            error_count = len(raw_result.get('errors', []))
            result = {
                'success': raw_result.get('symbols_processed', 0) > 0,
                'duration_seconds': duration,
                'symbols_processed': raw_result.get('symbols_processed', 0),
                'baselines_created': raw_result.get('baselines_created', 0),
                'baselines_updated': raw_result.get('baselines_updated', 0),
                'error_count': error_count,
                'failed_symbols': raw_result.get('errors', []),
            }

        except Exception as e:
            duration = time.time() - step_start
            logging.error("FM baseline generator crashed: {}".format(e))
            result = {
                'success': False,
                'failure_reason': str(e),
                'duration_seconds': duration,
                'symbols_processed': 0,
                'baselines_created': 0,
                'baselines_updated': 0,
                'error_count': 1,
                'failed_symbols': [],
            }

        if result['success']:
            self.create_status_box("FM BASELINE UPDATE COMPLETE", [
                "Symbols processed: {}".format(result['symbols_processed']),
                "Baselines created: {}".format(result['baselines_created']),
                "Baselines updated: {}".format(result['baselines_updated']),
                "Errors: {}".format(result['error_count']),
                "Duration: {:.0f}s".format(result['duration_seconds']),
            ])
        else:
            queue_error(
                error_type='fm_baseline_update_error',
                context={**result, 'performance_db': 'data/performance.db'},
                severity='ERROR'
            )
            failure_reason = result.get('failure_reason', 'No symbols processed')
            self.create_status_box("FM BASELINE UPDATE FAILED", [
                "Error: {}".format(str(failure_reason)[:80]),
                "Symbols processed: {}".format(result['symbols_processed']),
                "Impact: Using existing baselines (volume surprise may be stale)",
                "System: Continuing with Friday operations"
            ], success=False)

        return result

    def run_earnings_weekly_refresh(self):
        """Run Earnings Intelligence weekly refresh (Fridays)"""
        self.create_status_box(
            "📅 EARNINGS WEEKLY REFRESH",
            [
                "Mission: Refresh earnings calendar for the coming week",
                "Step 1: Archive past events (earnings_upcoming -> earnings_events)",
                "Step 2: Cleanup old records (7+ days past earnings)",
                "Step 3: Fetch next 90 days (Finnhub per-symbol, ~780 stocks)",
                "Schedule: Friday evenings before sector archive"
            ]
        )

        try:
            collector = EarningsCollector()
            result = collector.collect_weekly_earnings()
        except Exception as e:
            # Safety net for unhandled crashes
            logging.error("Earnings collector crashed: {}".format(e))
            result = {'success': False, 'failure_reason': str(e), 'errors': 1,
                      'earnings_found': 0, 'events_archived': 0,
                      'records_cleaned': 0, 'upcoming_count': 0,
                      'duration_seconds': 0,
                      'sub_tasks': {
                          'archive': {'duration_seconds': 0},
                          'cleanup': {'duration_seconds': 0},
                          'fetch': {'duration_seconds': 0},
                      }}

        if result.get('success'):
            self.create_status_box("✅ EARNINGS WEEKLY REFRESH COMPLETE", [
                "Earnings found: {}".format(result.get('earnings_found', 0)),
                "Events archived: {}".format(result.get('events_archived', 0)),
                "Records cleaned: {}".format(result.get('records_cleaned', 0)),
                "Upcoming earnings: {}".format(result.get('upcoming_count', 0)),
                "Status: ✅ Calendar refreshed for coming week"
            ])
            return result
        else:
            # Queue error with full result context
            queue_error(
                error_type='weekly_refresh_error',
                context={**result, 'performance_db': 'data/performance.db'},
                severity='ERROR'
            )
            failure_reason = result.get('failure_reason', 'Refresh returned failure status')
            self.create_status_box("⚠️ WEEKLY REFRESH FAILED", [
                "Error: {}".format(str(failure_reason)[:80]),
                "Impact: Using existing earnings calendar",
                "System: Continuing with Friday operations"
            ], success=False)
            return result  # Non-blocking, result already has success: False

    def run_database_backup(self, backup_type="daily", tag=""):
        """Run database backup with enhanced theming

        Args:
            backup_type: 'daily' for datalake_backup.db or 'weekly' for datalake_backup_weekly.db
            tag: optional label (e.g. "5.1 BG") prefixed onto every status-box title
                 and log line so this backup's output stays identifiable when it
                 runs on a background thread interleaved with other steps' output.

        Returns:
            dict: {'success': bool, 'duration_seconds': float, 'stdout': str}
        """
        prefix = "[{}] ".format(tag) if tag else ""

        if backup_type == "weekly":
            title = "💾 WEEKLY DATABASE BACKUP"
            target = "datalake_backup_weekly.db"
            frequency = "Weekly (Friday post-archive)"
            purpose = "Week-end recovery point (preserved until next Friday)"
        else:
            title = "💾 DATABASE BACKUP OPERATION"
            target = "datalake_backup.db"
            frequency = "Daily after all data collection complete"
            purpose = "Data protection and disaster recovery"

        if backup_type == "weekly":
            method = "File copy from today's daily backup"
        else:
            method = "SQLite native backup API with progress tracking"

        self.create_status_box(
            prefix + title,
            [
                "Mission: Create secure backup of datalake.db",
                "Target: {} (overwrites existing)".format(target),
                "Method: {}".format(method),
                "Frequency: {}".format(frequency),
                "Purpose: {}".format(purpose)
            ]
        )

        try:
            backup_script = os.path.join(project_root, 'data', 'health', 'db_backup.py')
            if not os.path.exists(backup_script):
                self.beautiful_log(prefix + "❌ BACKUP FAILED: Script not found: {}".format(backup_script), 'error')
                self.create_status_box(prefix + "💥 BACKUP SCRIPT MISSING", [
                    "Cannot locate backup script",
                    "Expected: {}".format(backup_script),
                    "⚠️ No backup protection available"
                ], success=False)
                return {'success': False, 'duration_seconds': 0, 'error': 'Script not found'}

            # For weekly backups, copy the daily backup file instead of running script again
            backup_start = time.time()
            if backup_type == "weekly":
                import shutil
                source_backup = os.path.join(project_root, 'data', 'datalake_backup.db')
                weekly_backup = os.path.join(project_root, 'data', 'datalake_backup_weekly.db')

                if not os.path.exists(source_backup):
                    self.beautiful_log(prefix + "❌ WEEKLY BACKUP FAILED: Daily backup not found", 'error')
                    self.create_status_box(prefix + "❌ WEEKLY BACKUP FAILED", [
                        "Daily backup not found: {}".format(source_backup),
                        "Weekly backup requires successful daily backup first",
                        "⚠️ Weekly recovery point not created"
                    ], success=False)
                    return {'success': False, 'duration_seconds': 0, 'error': 'Daily backup not found'}

                # Chunked copy with progress reporting
                source_size = os.path.getsize(source_backup)
                source_size_gb = source_size / (1024 ** 3)
                self.beautiful_log(prefix + "Copying {:.1f} GB: {} -> {}".format(
                    source_size_gb, os.path.basename(source_backup), os.path.basename(weekly_backup)), 'info')

                chunk_size = 64 * 1024 * 1024  # 64 MB chunks
                bytes_copied = 0
                next_report_gb = 1  # Report every 1 GB

                with open(source_backup, 'rb') as src, open(weekly_backup, 'wb') as dst:
                    while True:
                        chunk = src.read(chunk_size)
                        if not chunk:
                            break
                        dst.write(chunk)
                        bytes_copied += len(chunk)
                        copied_gb = bytes_copied / (1024 ** 3)
                        if copied_gb >= next_report_gb:
                            logging.info(prefix + "  Progress: {:.1f} / {:.1f} GB ({:.0f}%)".format(
                                copied_gb, source_size_gb, (bytes_copied / source_size) * 100))
                            next_report_gb += 1

                # Preserve file metadata (copy2 does this automatically, manual copy doesn't)
                shutil.copystat(source_backup, weekly_backup)

                # Create a fake result object for consistency
                class FakeResult:
                    returncode = 0
                    stdout = "Weekly backup created from daily backup"
                result = FakeResult()
                backup_size = "{:.1f} GB".format(source_size_gb)
            else:
                # Run backup script with streaming output (creates daily backup)
                result = self._run_streaming_subprocess([
                    sys.executable, backup_script, '--disaster', '--auto'
                ])
            backup_wall_clock = time.time() - backup_start

            if result.returncode == 0:
                backup_duration = None

                if backup_type == "weekly":
                    # backup_size already set during chunked copy above
                    pass
                else:
                    # Parse subprocess output for completion details (daily backup)
                    backup_size = None
                    output_lines = result.stdout.strip().split('\n') if result.stdout else []

                    import re
                    for line in output_lines:
                        # Match: "Backup completed: 1.4 GB in 3.0 minutes"
                        if 'Backup completed' in line:
                            size_match = re.search(r'completed:\s+([\d.]+\s+(?:GB|MB))', line)
                            if size_match:
                                backup_size = size_match.group(1)
                            dur_match = re.search(r'in\s+([\d.]+)\s+minutes', line)
                            if dur_match:
                                backup_duration = dur_match.group(1)

                # Fall back to wall-clock duration if parsing failed
                if backup_duration is None:
                    backup_duration = "{:.1f}".format(backup_wall_clock / 60)

                # Build enriched completion box
                box_lines = []
                if backup_size:
                    box_lines.append("Backup: {} in {} min".format(backup_size, backup_duration))
                else:
                    box_lines.append("Backup completed in {} min".format(backup_duration))
                box_lines.append("Target: {}".format(target))

                self.create_status_box(prefix + "✅ BACKUP OPERATION COMPLETE", box_lines)
                return {'success': True, 'duration_seconds': backup_wall_clock, 'stdout': result.stdout or ''}
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown backup error"
                self.beautiful_log(prefix + "❌ DATABASE BACKUP FAILED: {}".format(error_msg), 'error')
                self.log_subprocess_error('db_backup.py', result)
                self.create_status_box(prefix + "❌ BACKUP OPERATION FAILED", [
                    "Backup process unsuccessful",
                    "Error: {}".format(error_msg[:60]),
                    "⚠️ Proceeding without backup protection",
                    "Check logs for detailed error information"
                ], success=False)
                return {'success': False, 'duration_seconds': backup_wall_clock, 'stdout': result.stdout or ''}

        except Exception as e:
            queue_error(
                error_type='database_backup_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log(prefix + "❌ DATABASE BACKUP FATAL ERROR: {}".format(e), 'error')
            self.create_status_box(prefix + "💥 BACKUP PROCESS CRASHED", [
                "Backup operation encountered fatal error",
                "Error: {}".format(str(e)[:60]),
                "⚠️ No backup available - manual intervention may be needed"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - backup_start, 'error': str(e)}

    def run_batch_mode_review(self):
        """Review immediate mode's work via batch mode spawning"""
        self.create_status_box(
            "🤖 BATCH MODE AUTO-FIX REVIEW",
            [
                "Mission: QA check on immediate mode sessions from today",
                "Source: autofix/errors/errors_YYYY-MM-DD.json",
                "Approach: Spawn one Claude session per error (SEQUENTIAL)",
                "Focus: Verify quick fixes, apply proper long-term solutions",
                "Pattern Detection: Review past 30 days for recurring issues"
            ]
        )

        batch_start = time.time()
        try:
            from tools.autofix import get_error_queue, process_error_queue

            # Phase 1: Read and display error queue BEFORE processing
            queue = get_error_queue(max_sessions=5)

            # Handle skipped batch mode (Friday archive running)
            if queue.get('skipped'):
                self.beautiful_log("⏭️ Batch mode skipped: {}".format(queue.get('skip_reason', 'Unknown reason')), 'info')
                return {'success': True, 'duration_seconds': time.time() - batch_start, 'skipped': True,
                        'skip_reason': queue.get('skip_reason', 'Unknown reason')}

            errors_to_fix = queue.get('errors_to_fix', [])

            if not errors_to_fix:
                self.beautiful_log("No errors in queue - batch mode not needed", 'info')
                return {'success': True, 'duration_seconds': time.time() - batch_start,
                        'errors_found': 0, 'sessions_spawned': 0}

            # Display error queue BEFORE spawning sessions
            queue_lines = [
                "Total Errors Today: {}".format(queue['total_errors']),
                "Unique Error Types: {}".format(queue['unique_errors']),
                ""
            ]

            if queue['error_summary']:
                queue_lines.append("Errors to Fix:")
                for error in queue['error_summary']:
                    occurrence = " (x{})".format(error['occurrence_count']) if error['occurrence_count'] > 1 else ""
                    queue_lines.append("  • {}{} - {}".format(
                        error['error_type'],
                        occurrence,
                        error['severity']
                    ))

            self.create_status_box("📋 ERROR QUEUE", queue_lines)

            # Phase 2: Process errors (spawns Claude Code sessions sequentially)
            sessions_spawned = process_error_queue(errors_to_fix)

            # Phase 3: Show results
            if sessions_spawned > 0:
                self.create_status_box("🤖 BATCH MODE COMPLETE", [
                    "Sessions Spawned: {}".format(sessions_spawned),
                    "Total Errors: {}".format(queue['total_errors']),
                    "Review Type: Sequential (one at a time)",
                    "Check logs for batch mode results"
                ])

            return {'success': True, 'duration_seconds': time.time() - batch_start,
                    'errors_found': queue.get('total_errors', 0), 'sessions_spawned': sessions_spawned}
        except Exception as e:
            queue_error(
                error_type='batch_mode_review_failed',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            return {'success': False, 'duration_seconds': time.time() - batch_start, 'error': str(e)}

    def _recreate_query_views(self):
        """Recreate Morning Views SQL views in datalake_query.db after sync.

        Sync overwrites the entire query database file, destroying any views
        that Morning Views created. This method recreates them by instantiating
        MorningViews (whose __init__ calls _ensure_views_exist()).
        """
        try:
            from morning_view.morning_views import MorningViews
            mv = MorningViews()
            mv.close()
            self.beautiful_log("Query database views recreated successfully", 'info')
        except Exception as e:
            self.beautiful_log("View recreation failed (non-critical): {}".format(e), 'warning')

    def run_query_database_sync(self):
        """Sync query database from primary database for safe analysis"""
        # Check for partial sync files from previous failed attempts
        data_dir = os.path.join(project_root, 'data')
        partial_files = []
        if os.path.exists(data_dir):
            for filename in os.listdir(data_dir):
                if filename.startswith('datalake_query_partial_') and filename.endswith('.db'):
                    partial_files.append(os.path.join(data_dir, filename))

        if partial_files:
            # Found partial sync files - attempt recovery
            self.beautiful_log("🔍 Detected {} partial sync file(s) from previous attempts".format(len(partial_files)), 'info')

            # Sort by modification time (newest first)
            partial_files.sort(key=os.path.getmtime, reverse=True)
            newest_partial = partial_files[0]

            self.create_status_box("🔧 QUERY SYNC RECOVERY", [
                "Found partial sync from previous attempt",
                "File: {}".format(os.path.basename(newest_partial)),
                "Age: {:.1f} hours".format((time.time() - os.path.getmtime(newest_partial)) / 3600),
                "Attempting automatic recovery..."
            ])

            # Try to complete the rename now (analysis tools may have closed)
            target = os.path.join(data_dir, 'datalake_query.db')
            try:
                # Remove old target if it exists
                if os.path.exists(target):
                    os.remove(target)
                # Rename partial to target
                os.rename(newest_partial, target)

                self.beautiful_log("✅ Recovery successful - partial sync completed", 'success')
                self.create_status_box("✅ RECOVERY COMPLETE", [
                    "Successfully recovered partial sync",
                    "Query database: datalake_query.db",
                    "Cleaned up {} old partial file(s)".format(len(partial_files) - 1) if len(partial_files) > 1 else "No cleanup needed"
                ])

                # Clean up other partial files if any
                for old_partial in partial_files[1:]:
                    try:
                        os.remove(old_partial)
                    except:
                        pass

                # Recreate Morning Views SQL views (destroyed by sync)
                self._recreate_query_views()

                return {'success': True, 'duration_seconds': 0, 'stdout': '', 'sync_type': 'full', 'recovered': True}

            except (OSError, PermissionError) as e:
                self.beautiful_log("⚠️ Recovery failed (file still locked): {}".format(e), 'warning')
                self.create_status_box("⚠️ RECOVERY DELAYED", [
                    "Cannot complete recovery (file locked)",
                    "Will retry during normal sync operation",
                    "Continuing with scheduled sync..."
                ], success=False)
                # Continue with normal sync below

        self.create_status_box(
            "🔄 QUERY DATABASE SYNC",
            [
                "Mission: Sync query database from primary datalake.db",
                "Target: datalake_query.db (read-only for analysis)",
                "Purpose: Prevent database locking during analysis operations",
                "Schedule: After Morning and Evening Option Pipelines"
            ]
        )

        try:
            backup_script = os.path.join(project_root, 'data', 'health', 'db_backup.py')
            if not os.path.exists(backup_script):
                self.beautiful_log("❌ QUERY SYNC FAILED: Script not found: {}".format(backup_script), 'error')
                self.create_status_box("💥 SYNC SCRIPT MISSING", [
                    "Cannot locate backup/sync script",
                    "Expected: {}".format(backup_script),
                    "⚠️ Query database will not be updated"
                ], success=False)
                return {'success': False, 'duration_seconds': 0, 'sync_type': 'full', 'error': 'Script not found'}

            # Run sync script with streaming output (automated mode, no user prompts)
            sync_start = time.time()
            result = self._run_streaming_subprocess([
                sys.executable, backup_script, '--sync', '--auto'
            ])
            sync_wall_clock = time.time() - sync_start

            if result.returncode == 0:
                # Parse subprocess output for completion details
                output_lines = result.stdout.strip().split('\n') if result.stdout else []
                sync_duration = None
                sync_size = None
                sync_tables = None
                sync_pages = None

                import re
                for line in output_lines:
                    # Match: "Sync completed: 1,878,109 pages (7.16 GB) in 5.2 minutes"
                    if 'Sync completed' in line:
                        pages_match = re.search(r'([\d,]+)\s+pages', line)
                        if pages_match:
                            sync_pages = int(pages_match.group(1).replace(',', ''))
                        size_match = re.search(r'\(([^)]*(?:GB|MB))\)', line)
                        if size_match:
                            sync_size = size_match.group(1)
                        dur_match = re.search(r'in\s+([\d.]+)\s+minutes', line)
                        if dur_match:
                            sync_duration = dur_match.group(1)
                    # Match: "Verified: 28 tables, data fresh (latest: 2026-02-19 ...)"
                    if 'Verified' in line and 'tables' in line:
                        tbl_match = re.search(r'(\d+)\s+tables', line)
                        if tbl_match:
                            sync_tables = tbl_match.group(1)

                # Fall back to wall-clock duration if parsing failed
                if sync_duration is None:
                    sync_duration = "{:.1f}".format(sync_wall_clock / 60)

                # Recreate Morning Views SQL views (destroyed by sync)
                self._recreate_query_views()

                # Record sync performance to daily_state.json
                _save_sync_performance(
                    sync_type='full',
                    duration_seconds=sync_wall_clock,
                    size_display=sync_size,
                    pages=sync_pages,
                    tables=sync_tables,
                    success=True
                )

                # Build enriched completion box
                box_lines = []
                if sync_size and sync_tables:
                    box_lines.append("Synced: {} ({} tables) in {} min".format(sync_size, sync_tables, sync_duration))
                elif sync_size:
                    box_lines.append("Synced: {} in {} min".format(sync_size, sync_duration))
                else:
                    box_lines.append("Synced in {} min".format(sync_duration))
                box_lines.append("Target: datalake_query.db ready for analysis")

                self.create_status_box("✅ QUERY SYNC OPERATION COMPLETE", box_lines)
                return {'success': True, 'duration_seconds': sync_wall_clock, 'stdout': result.stdout or '', 'sync_type': 'full'}
            elif result.returncode == 2:
                # User cancelled (shouldn't happen in auto mode, but handle it)
                _save_sync_performance('full', sync_wall_clock, success=False)
                self.beautiful_log("⚠️ QUERY SYNC CANCELLED", 'warning')
                self.create_status_box("⚠️ SYNC CANCELLED", [
                    "Query sync was cancelled",
                    "Query database may have stale data",
                    "System: Continuing with operations"
                ], success=False)
                return {'success': False, 'duration_seconds': sync_wall_clock, 'stdout': result.stdout or '', 'sync_type': 'full', 'error': 'cancelled'}
            elif result.returncode == 3:
                # Partial success: copy succeeded but rename failed
                self.beautiful_log("⚠️ PARTIAL SYNC: Copy succeeded, rename failed", 'warning')

                # Parse output to find preserved file path
                output_lines = result.stdout.strip().split('\n') if result.stdout else []
                preserved_file = None
                for line in output_lines:
                    if 'datalake_query_partial_' in line and '.db' in line:
                        preserved_file = line.strip()
                        break

                self.create_status_box("⚠️ QUERY SYNC PARTIAL SUCCESS", [
                    "Database copy completed successfully",
                    "Rename operation failed (file locked)",
                    "Fresh data preserved: {}".format(preserved_file if preserved_file else "check logs"),
                    "Recovery: Close analysis tools and retry sync",
                    "System: Continuing with current query database"
                ], success=False)

                # Log as warning, not error - operation is recoverable
                _save_sync_performance('full', sync_wall_clock, success=False)
                logging.warning("Query sync partial success - copy OK but rename failed (exit code 3)")
                return {'success': False, 'duration_seconds': sync_wall_clock, 'stdout': result.stdout or '', 'sync_type': 'full', 'error': 'partial_rename_failed'}
            else:
                # Try stderr first, then stdout, since db_backup.py writes errors to both
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else "Unknown sync error"

                # Log the full output for debugging
                if result.stdout:
                    logging.info("Sync stdout: {}".format(result.stdout[-500:]))  # Last 500 chars
                if result.stderr:
                    logging.error("Sync stderr: {}".format(result.stderr[-500:]))

                self.beautiful_log("❌ QUERY SYNC FAILED: {}".format(error_msg[:100]), 'error')
                self.log_subprocess_error('db_backup.py --sync --auto', result)
                _save_sync_performance('full', sync_wall_clock, success=False)
                self.create_status_box("❌ QUERY SYNC FAILED", [
                    "Sync process unsuccessful",
                    "Error: {}".format(error_msg[:60]),
                    "⚠️ Query database may have stale data",
                    "Check logs for detailed error information"
                ], success=False)
                return {'success': False, 'duration_seconds': sync_wall_clock, 'stdout': result.stdout or '', 'sync_type': 'full', 'error': error_msg[:200]}

        except Exception as e:
            queue_error(
                error_type='query_sync_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("❌ QUERY SYNC FATAL ERROR: {}".format(e), 'error')
            self.create_status_box("💥 SYNC PROCESS CRASHED", [
                "Query sync operation encountered fatal error",
                "Error: {}".format(str(e)[:60]),
                "⚠️ Query database not updated - may have stale data"
            ], success=False)
            return {'success': False, 'duration_seconds': 0, 'sync_type': 'full', 'error': str(e)}

    def run_sector_archive(self):
        """Run sector-based database archive (manual invocation via --sector-archive flag)

        Runs db_archive_sector.py --all-tiers without timeout constraints.
        For automated Friday workflow, use run_friday_sector_archive() instead.
        """
        self.create_status_box(
            "📦 SECTOR DATABASE ARCHIVE",
            [
                "🎯 Mission: Archive old data to sector-specific databases",
                "📊 Tiers: T1 (15d), T2 (30d), T3 (90d) retention",
                "🗂️ Output: data/sector_archive/{sector}.db files",
                "⏳ Duration: May take several hours for full archive"
            ]
        )

        archive_start = time.time()
        try:
            archive_script = os.path.join(project_root, 'data', 'health', 'db_archive_sector.py')
            if not os.path.exists(archive_script):
                self.beautiful_log("❌ ARCHIVE FAILED: Script not found: {}".format(archive_script), 'error')
                self.create_status_box("💥 ARCHIVE SCRIPT MISSING", [
                    "Cannot locate sector archive script",
                    "Expected: {}".format(archive_script),
                    "⚠️ Manual database cleanup may be needed"
                ], success=False)
                return {'success': False, 'duration_seconds': 0, 'error': 'Script not found'}

            # Run archive script with real-time output streaming
            result = self._run_streaming_subprocess([
                sys.executable, archive_script, '--all-tiers'
            ], cwd=project_root)
            archive_duration = time.time() - archive_start

            if result.returncode == 0:
                self.create_status_box("✅ SECTOR ARCHIVE COMPLETE", [
                    "Archive status: Completed successfully",
                    "All tiers processed (T1, T2, T3)",
                ])
                return {'success': True, 'duration_seconds': archive_duration, 'stdout': result.stdout or ''}
            else:
                self.log_subprocess_error('db_archive_sector.py', result)
                self.beautiful_log("❌ SECTOR ARCHIVE FAILED: Return code {}".format(result.returncode), 'error')
                self.create_status_box("❌ SECTOR ARCHIVE FAILED", [
                    "Archive process unsuccessful",
                    "Error: Return code {}".format(result.returncode),
                    "Check logs for detailed error information"
                ], success=False)
                return {'success': False, 'duration_seconds': archive_duration, 'stdout': result.stdout or ''}

        except Exception as e:
            queue_error(
                error_type='sector_archive_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("❌ SECTOR ARCHIVE FATAL ERROR: {}".format(e), 'error')
            self.create_status_box("💥 SECTOR ARCHIVE CRASHED", [
                "Archive operation encountered fatal error",
                "Error: {}".format(str(e)[:60])
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - archive_start, 'error': str(e)}

    def run_friday_sector_archive(self):
        """Run Friday sector archive with timeout until Monday 5:45 AM cutoff

        Used by the automated Friday workflow. Calculates available time until
        Monday 5:45 AM and runs sector archive with that time limit.
        For manual runs without timeout, use run_sector_archive() instead.
        """
        timeout_seconds = self.calculate_archive_timeout()

        if timeout_seconds <= 0:
            self.beautiful_log("Insufficient time for archive before 5:45 AM cutoff", 'warning')
            self.create_status_box("⏰ ARCHIVE SKIPPED - INSUFFICIENT TIME", [
                "Current time too close to 5:45 AM cutoff",
                "Archive requires minimum time buffer",
                "Will attempt again next trading day"
            ], success=False)
            return {'success': True, 'duration_seconds': 0, 'skipped': True}  # Not an error - just insufficient time

        # Convert to hours for display
        timeout_hours = timeout_seconds / 3600
        now = now_eastern()

        self.create_status_box(
            "📦 FRIDAY SECTOR ARCHIVE OPERATION",
            [
                "🎯 Mission: Archive old data to sector-specific databases",
                "⏰ Time Available: {:.1f} hours (until Monday 5:45 AM cutoff)".format(timeout_hours),
                "📅 Tiers: T1 (15d), T2 (30d), T3 (90d)",
                "🔄 Runs to completion unless Monday cutoff reached",
                "📊 Process: Three-tier retention with sector routing"
            ]
        )

        fri_archive_start = time.time()
        try:
            archive_script = os.path.join(project_root, 'data', 'health', 'db_archive_sector.py')
            if not os.path.exists(archive_script):
                self.beautiful_log("❌ ARCHIVE FAILED: Script not found: {}".format(archive_script), 'error')
                self.create_status_box("💥 ARCHIVE SCRIPT MISSING", [
                    "Cannot locate archive script",
                    "Expected: {}".format(archive_script),
                    "⚠️ Manual database cleanup may be needed"
                ], success=False)
                return {'success': False, 'duration_seconds': 0, 'error': 'Script not found'}

            # Run archive script with real-time streaming + time limit
            # The script's internal --time-limit handles graceful shutdown;
            # the subprocess timeout is a safety net (2 min buffer)
            timeout_for_subprocess = timeout_seconds - 120  # 2 minute buffer

            result = self._run_streaming_subprocess([
                sys.executable, archive_script,
                '--all-tiers',  # Run Tier 1 + Tier 2 + Tier 3
                '--time-limit', str(int(timeout_seconds))
            ], cwd=project_root, timeout=timeout_for_subprocess)

            if result.returncode == 0:
                # Parse subprocess output for archive metrics
                import re
                archive_lines = result.stdout.strip().split('\n') if result.stdout else []
                rows_archived = None
                rows_deleted = None
                space_reclaimed = None
                archive_duration = None

                for line in archive_lines:
                    if 'Total rows archived:' in line:
                        m = re.search(r'Total rows archived:\s+([\d,]+)', line)
                        if m:
                            rows_archived = m.group(1)
                    elif 'Total rows deleted:' in line:
                        m = re.search(r'Total rows deleted:\s+([\d,]+)', line)
                        if m:
                            rows_deleted = m.group(1)
                    elif 'Space reclaimed:' in line:
                        m = re.search(r'Space reclaimed:\s+([\d.]+\s+\w+)\s+\(([^)]+)\)', line)
                        if m:
                            space_reclaimed = "{} ({})".format(m.group(1), m.group(2))
                    elif 'Total Duration:' in line:
                        m = re.search(r'Total Duration:\s+([\d.]+)\s+seconds', line)
                        if m:
                            archive_duration = self._format_duration(float(m.group(1)))

                box_lines = []
                if rows_archived:
                    box_lines.append("Archived: {} rows across 15 sectors".format(rows_archived))
                if rows_deleted:
                    box_lines.append("Deleted: {} rows from production".format(rows_deleted))
                if space_reclaimed:
                    box_lines.append("VACUUM: {} reclaimed".format(space_reclaimed))
                if archive_duration:
                    box_lines.append("Duration: {}".format(archive_duration))
                box_lines.append("Status: Finished before Monday cutoff")

                self.create_status_box("✅ FRIDAY ARCHIVE COMPLETE", box_lines)
                return {'success': True, 'duration_seconds': time.time() - fri_archive_start, 'stdout': result.stdout or ''}
            elif result.returncode == 124:  # Timeout return code
                self.beautiful_log("⏰ DATABASE ARCHIVE TIMED OUT (EXPECTED)", 'warning')
                self.create_status_box("⏰ ARCHIVE TIMED OUT - PARTIAL SUCCESS", [
                    "Archive ran for maximum available time (until Monday 5:45 AM)",
                    "Process stopped gracefully before cutoff",
                    "Partial progress made - will resume next Friday",
                    "Database integrity maintained"
                ])
                return {'success': True, 'duration_seconds': time.time() - fri_archive_start, 'stdout': result.stdout or '', 'timed_out': True}
            else:
                # Use log_subprocess_error so log analyzer can detect this
                self.log_subprocess_error('db_archive_sector.py --all-tiers', result)
                self.beautiful_log("❌ DATABASE ARCHIVE FAILED: Return code {}".format(result.returncode), 'error')
                self.create_status_box("❌ FRIDAY SECTOR ARCHIVE FAILED", [
                    "Archive process unsuccessful",
                    "Error: Return code {}".format(result.returncode),
                    "⚠️ Will retry next Friday",
                    "Check logs for detailed error information"
                ], success=False)
                return {'success': False, 'duration_seconds': time.time() - fri_archive_start, 'stdout': result.stdout or ''}

        except subprocess.TimeoutExpired:
            self.beautiful_log("⏰ DATABASE ARCHIVE TIMEOUT (GRACEFUL)", 'warning')
            self.create_status_box("⏰ ARCHIVE TIMEOUT - EXPECTED BEHAVIOR", [
                "Archive reached Monday 5:45 AM cutoff",
                "Process terminated gracefully",
                "Partial work completed successfully",
                "Will resume next Friday automatically"
            ])
            return {'success': True, 'duration_seconds': time.time() - fri_archive_start, 'timed_out': True}

        except Exception as e:
            queue_error(
                error_type='friday_archive_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("❌ DATABASE ARCHIVE FATAL ERROR: {}".format(e), 'error')
            self.create_status_box("💥 FRIDAY ARCHIVE CRASHED", [
                "Archive operation encountered fatal error",
                "Error: {}".format(str(e)[:60]),
                "⚠️ Will retry next Friday"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - fri_archive_start, 'error': str(e)}

    def run_performance_collection(self, results, step_durations):
        """Write end-of-day performance data to performance.db (Phase 6).

        Reads FM session data and sync performance from daily_state.json,
        then writes all 13 tables in a single transaction.

        Args:
            results: Dict of step_name → result dict from today's run
            step_durations: Dict of step_name → duration_seconds

        Returns:
            dict: {'success': bool, 'rows_written': int} or {'success': False, 'error': str}
        """
        self.create_status_box(
            "📊 PERFORMANCE DATA COLLECTION",
            [
                "Mission: Record today's operational metrics to performance.db",
                "Tables: 13 (daily context, OP, EI, FM cycles, sync, subprocesses)",
                "Purpose: Autofix baseline detection and degradation trending",
            ]
        )

        perf_start = time.time()
        try:
            from tools.performance_writer import write_daily_performance
            from main_ui import _load_daily_state

            # Read daily state for FM session data, sync entries, and news API usage
            daily_state = _load_daily_state() or {}
            fm_session_data = daily_state.get('fm_session', {})
            sync_entries = daily_state.get('sync_performance', [])
            news_api_data = daily_state.get('news_api_usage', {})

            # Get today's trade date
            trade_date = now_eastern().strftime('%Y-%m-%d')

            # Write all performance data (ensure_schema called internally)
            result = write_daily_performance(
                trade_date=trade_date,
                results=results,
                step_durations=step_durations,
                fm_session_data=fm_session_data,
                sync_entries=sync_entries,
                news_api_data=news_api_data,
            )

            rows_written = result.get('rows_written', 0) if isinstance(result, dict) else 0
            perf_duration = time.time() - perf_start
            self.create_status_box("✅ PERFORMANCE DATA COLLECTED", [
                "Rows written: {}".format(rows_written),
                "Database: data/performance.db",
                "Duration: {:.1f}s".format(perf_duration),
            ])
            return {'success': True, 'duration_seconds': perf_duration, 'rows_written': rows_written}

        except Exception as e:
            perf_duration = time.time() - perf_start
            self.beautiful_log("Performance collection failed (non-critical): {}".format(e), 'warning')
            logging.warning("Performance collection error: {}".format(traceback.format_exc()))
            return {'success': False, 'duration_seconds': perf_duration, 'error': str(e)}

    def run_symbol_health_check(self):
        """Run symbol health check and log suspects (Phase 6.2).

        Queries option_contracts for symbols missing data, logs lifecycle
        events for suspects (5+ days missing), and returns structured
        results for the end-of-day report.

        Returns:
            dict: {'success': bool, 'warnings': list, 'suspects': list,
                   'new_suspects_logged': int, 'safety_gate_tripped': bool}
        """
        health_start = time.time()
        try:
            from tools.lifecycle.health_check import run_health_check, log_suspects

            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'datalake.db')
            health_result = run_health_check(db_path)

            if health_result['safety_gate_tripped']:
                self.beautiful_log(
                    "Health check skipped: {}".format(health_result['safety_gate_message']),
                    'warning'
                )
                return {
                    'success': True,
                    'warnings': [],
                    'suspects': [],
                    'new_suspects_logged': 0,
                    'safety_gate_tripped': True,
                    'safety_gate_message': health_result['safety_gate_message'],
                    'duration_seconds': time.time() - health_start,
                }

            # Log new suspects idempotently
            new_logged = log_suspects(db_path, health_result)

            warn_count = len(health_result['warnings'])
            suspect_count = len(health_result['suspects'])
            if warn_count or suspect_count:
                self.beautiful_log(
                    "Symbol health: {} warnings, {} suspects ({} newly logged)".format(
                        warn_count, suspect_count, new_logged),
                    'warning' if suspect_count else 'info'
                )
            else:
                self.beautiful_log("Symbol health: all clear", 'info')

            return {
                'success': True,
                'warnings': [(h.symbol, h.last_data_date, h.consecutive_missing_days)
                             for h in health_result['warnings']],
                'suspects': [(h.symbol, h.last_data_date, h.consecutive_missing_days)
                             for h in health_result['suspects']],
                'new_suspects_logged': new_logged,
                'safety_gate_tripped': False,
                'duration_seconds': time.time() - health_start,
            }

        except Exception as e:
            self.beautiful_log("Symbol health check failed (non-critical): {}".format(e), 'warning')
            logging.warning("Health check error: {}".format(traceback.format_exc()))
            return {
                'success': False,
                'warnings': [],
                'suspects': [],
                'new_suspects_logged': 0,
                'safety_gate_tripped': False,
                'duration_seconds': time.time() - health_start,
                'error': str(e),
            }
