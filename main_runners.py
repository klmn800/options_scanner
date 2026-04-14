#!/usr/bin/env python3
"""
Main Orchestrator Pipeline Runners (main_runners.py)
====================================================
Pipeline runner methods for the options scanner orchestrator.

Contains all run_* methods that execute individual pipelines:
- run_morning_option_pipeline: Morning Option Pipeline (fresh OI data)
- run_flow_monitor: Flow Monitor daily cycle
- run_evening_option_pipeline: Evening Option Pipeline (volume-enriched data)
- run_morning_views: Daily watchlist email
- run_metadata_collection: Symbol metadata refresh
- run_earnings_pipeline: Earnings Intelligence daily
- run_earnings_morning_scan: Arbitrage scanner
- run_earnings_weekly_refresh: Friday calendar refresh
- run_airline_play_phase: Airline tracking extraction
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

        try:
            # Initialize Option Pipeline orchestrator
            op = OPOrchestrator(no_interaction=True)

            # Run the pipeline
            trade_date = eastern_date_string()
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
                "Pre-Market: System preparation and setup (9:15 AM)",
                "Market Hours: Real-time flow monitoring (9:30 AM - 4:00 PM)",
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
            is_before_pre_market = current_hour < 9 or (current_hour == 9 and current_minute < 15)
            is_during_pre_market = (current_hour == 9 and current_minute >= 15 and current_minute < 30)
            is_during_market_hours = ((current_hour == 9 and current_minute >= 30) or
                                     (current_hour >= 10 and current_hour < 16))
            is_after_market = current_hour >= 16

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
                # Pre-market: Wait until exactly 9:15 AM (system preparation)
                if is_before_pre_market:
                    target = now.replace(hour=9, minute=15, second=0, microsecond=0)
                    wait_seconds = (target - now).total_seconds()
                    if wait_seconds > 0:
                        self.beautiful_log("Waiting until 9:15 AM for pre-market preparation ({:.1f} minutes)".format(wait_seconds / 60), 'info')
                        time.sleep(wait_seconds)

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

            pre_market_success = pre_market_result.get('success', False) if isinstance(pre_market_result, dict) else bool(pre_market_result)

            # Initialize market hours variables (may be skipped if after-hours)
            session_stats = {}
            market_hours_result = None

            # Market hours: Only run if not after market close
            if not is_after_market:
                # Wait until exactly 9:30 AM if before market open
                print("")
                print("")
                now = now_eastern()
                if now.hour < 9 or (now.hour == 9 and now.minute < 30):
                    target = now.replace(hour=9, minute=30, second=0, microsecond=0)
                    wait_seconds = (target - now).total_seconds()
                    if wait_seconds > 0:
                        self.beautiful_log("Waiting until 9:30 AM for market open collector/analyzer ({:.1f} minutes)".format(wait_seconds / 60), 'info')
                        time.sleep(wait_seconds)

                self.beautiful_log("Running market hours monitoring (collector/analyzer/alerts)", 'phase')
                market_hours_result = run_market_hours()  # Runs until market closes at 4:00 PM

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

        try:
            # Initialize Option Pipeline orchestrator
            op = OPOrchestrator(no_interaction=True)

            # Run the pipeline
            trade_date = eastern_date_string()
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

    def run_morning_views(self):
        """Run Morning Views for daily watchlist (with email delivery)

        CRITICAL TIMING: Must run AFTER query database sync.
        Morning Views creates SQL views in datalake_query.db.
        If sync runs after, views are destroyed.
        """
        self.create_status_box(
            "📊 MORNING VIEWS GENERATION",
            [
                "Mission: Generate and email daily options watchlist",
                "Source: datalake_query.db (fresh from sync)",
                "Views: Creates SQL views with hybrid data",
                "Data: TODAY's OI + YESTERDAY's volume/greeks/price",
                "Output: Markdown log + .docx email attachment"
            ]
        )

        mv_start = time.time()
        try:
            self.beautiful_log("Initializing Morning Views generation", 'phase')
            self.beautiful_log("Running morning views (console output suppressed - use TUI)...", 'info')

            # Ensure subprocess inherits UTF-8 encoding
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'

            # Run subprocess with output captured but not displayed
            process = subprocess.Popen(
                [sys.executable, "morning_view/morning_views.py", "--email"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',  # Replace undecodable bytes instead of crashing
                universal_newlines=True,
                env=env
            )

            # Capture output for error checking — console suppressed, log file gets it
            output_lines = []
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    stripped = output.strip()
                    output_lines.append(stripped)
                    # Forward to log file (clean subprocess formatting artifacts)
                    log_line = stripped
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
            captured_output = '\n'.join(output_lines)
            mv_duration = time.time() - mv_start

            if return_code == 0:
                self.beautiful_log("Morning Views completed successfully", 'success')
                self.create_status_box("✅ MORNING VIEWS COMPLETE", [
                    "Watchlist: Generated from today's OI data",
                    "Email: Process completed (check email delivery)",
                    "Status: ✅ Morning views finished"
                ])
                return {'success': True, 'duration_seconds': mv_duration, 'stdout': captured_output}
            else:
                print("")  # Blank line after script output
                self.beautiful_log("❌ MORNING VIEWS FAILED", 'error')
                self.create_status_box("❌ MORNING VIEWS FAILED", [
                    "Return code: {}".format(return_code),
                    "Error: See output above for details",
                    "Impact: No watchlist email sent",
                    "System: Continuing with flow monitor"
                ], success=False)
                return {'success': False, 'duration_seconds': mv_duration, 'stdout': captured_output}

        except Exception as e:
            if 'process' in locals():
                try:
                    process.terminate()
                except:
                    pass
            queue_error(
                error_type='morning_views_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("Morning Views encountered fatal error: {}".format(e), 'error')
            self.create_status_box("💥 MORNING VIEWS FATAL ERROR", [
                "Morning Views operation crashed",
                "Error: {}".format(str(e)[:60]),
                "Impact: No watchlist available",
                "System: Continuing with flow monitor anyway"
            ], success=False)
            return {'success': False, 'duration_seconds': time.time() - mv_start, 'error': str(e)}

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

    def run_earnings_intelligence(self):
        """Run unified Earnings Intelligence pipeline (PRD 0008)

        Replaces both run_earnings_pipeline() and run_earnings_morning_scan().
        Calls the 6-sub-step run_daily_pipeline() which handles snapshots,
        post-earnings calc, expected moves, watchlist, news, and arbitrage.
        """
        self.create_status_box(
            "📈 EARNINGS INTELLIGENCE",
            [
                "Step 1: IV/price snapshot collection (T-7 to T+3 window)",
                "Step 2: Post-earnings calculation (price moves, IV crush)",
                "Step 3: Expected moves & signal recalculation",
                "Step 4: Earnings watchlist population",
                "Step 5: News sentiment enrichment (Alpha Vantage)",
                "Step 6: Sector sympathy arbitrage scan",
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
        """Render earnings watchlist as box-drawing table via print().

        Uses double-line box characters (╔═╦╗║╠╬╣╚═╩╝) matching the status boxes.
        Fits within 120-char terminal width (~105 chars with indent).

        Args:
            watchlist_symbols: List of row dicts from earnings_watchlist
        """
        if not watchlist_symbols:
            print("  No earnings watchlist entries")
            return

        print("")

        # Column definitions: (header, width, align)
        cols = [
            ("Sym",        6, "<"),
            ("Status",     8, "<"),
            ("Price",      8, ">"),
            ("Days",       4, ">"),
            ("Time",       4, "<"),
            ("Signal",    10, "<"),
            ("IV%",        5, ">"),
            ("Undr%",      7, ">"),
            ("ExpMv",      6, ">"),
            ("OI Bal",     8, "<"),
            ("Sentiment", 14, "<"),
        ]
        # OI balance abbreviations (full values are 10-15 chars)
        _oi_abbrev = {
            'Clear Call Bias': 'Clr Call',
            'Heavy Call': 'Hvy Call',
            'Balanced': 'Balanced',
            'Leans Put': 'Lns Put',
            'Heavy Put': 'Hvy Put',
            'Clear Put Bias': 'Clr Put',
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

        # Top border
        print(hline("\u2554", "\u2566", "\u2557"))
        # Header row
        print(trow([h for h, _, _ in cols]))
        # Header separator
        print(hline("\u2560", "\u256c", "\u2563"))

        for row in watchlist_symbols:
            status = row.get('status', '?')
            price = row.get('current_price')
            price_str = "{:.2f}".format(price) if price else "-"
            days = row.get('days_to_earnings')
            days_str = "{}d".format(days) if days is not None else "-"
            time_str = (row.get('earnings_time') or '-')[:4]
            signal = (row.get('earnings_play_signal') or '-')[:10]
            iv_pct = row.get('iv_percentile_30d')
            iv_str = "{:.0f}".format(iv_pct) if iv_pct is not None else "-"
            undr = row.get('relative_underpricing_pct')
            undr_str = "{:.1f}%".format(undr) if undr is not None else "-"
            exp_mv = row.get('expected_move_pct')
            exp_str = "{:.1f}%".format(exp_mv) if exp_mv is not None else "-"
            oi_raw = row.get('oi_balance_text') or '-'
            oi_str = _oi_abbrev.get(oi_raw, oi_raw[:8])
            sent = (row.get('news_sentiment_label') or '-')[:14]

            # For post-earnings rows, show actual move instead of expected
            if status in ('T+1', 'T+2', 'T+3'):
                actual = row.get('actual_move_pct')
                direction = row.get('move_direction', '')
                crush = row.get('iv_crush_severity', '')
                if actual is not None:
                    exp_str = "{}{:.1f}%".format(
                        "+" if direction == 'UP' else "-", abs(actual))
                if crush:
                    sent = crush[:14]

            print(trow([
                (row.get('symbol') or '?')[:6],
                status[:8], price_str, days_str, time_str,
                signal, iv_str, undr_str, exp_str, oi_str, sent]))

        # Bottom border
        print(hline("\u255a", "\u2569", "\u255d"))
        print("{} symbols on watchlist".format(len(watchlist_symbols)))
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

    def run_airline_play_phase(self):
        """Run airline tracking extraction phase"""
        self.create_status_box(
            "🛫 AIRLINE PLAY TRACKING PHASE",
            [
                "Mission: Extract airline-specific data into dedicated tables",
                "Symbols: 7 airline stocks (DAL, UAL, AAL, LUV, JBLU, ALK, JETS)",
                "Tables: airline_symbol_tracking + airline_options_tracking",
                "Filters: Primary ±10% / Secondary ±5% strike range, ≤60 DTE",
                "Dependencies: Requires Evening Option Pipeline + historical prices"
            ]
        )

        airline_start = time.time()
        try:
            # Import airline play tracking modules
            from strategies.airline_play import ap_symbol_tracking, ap_options_tracking

            # Get current trade date
            trade_date = eastern_date_string()

            # Run symbol-level tracking
            symbol_result = ap_symbol_tracking.run_symbol_tracking(trade_date=trade_date)

            symbols_processed = symbol_result.get('symbols_processed', 0)
            symbols_failed = symbol_result.get('symbols_failed', 0)

            # Run options-level tracking
            options_result = ap_options_tracking.run_options_tracking(trade_date=trade_date)

            contracts_tracked = options_result.get('total_contracts_tracked', 0)
            airline_duration = time.time() - airline_start

            # Check for success
            if symbols_processed > 0 or contracts_tracked > 0:
                self.create_status_box("🎯 AIRLINE TRACKING COMPLETE", [
                    "Trade Date: {}".format(trade_date),
                    "Symbols Tracked: {} of 7".format(symbols_processed),
                    "Contracts Tracked: {}".format(contracts_tracked),
                    "Tables: airline_symbol_tracking + airline_options_tracking",
                    "Status: ✅ Tracking updated successfully"
                ])
                return {'success': True, 'duration_seconds': airline_duration,
                        'symbols_processed': symbols_processed, 'symbols_failed': symbols_failed,
                        'contracts_tracked': contracts_tracked}
            else:
                self.beautiful_log("Airline tracking phase completed with no data", 'warning')
                self.create_status_box("⚠️ AIRLINE TRACKING - NO DATA", [
                    "Trade Date: {}".format(trade_date),
                    "Symbols Tracked: 0 of 7",
                    "Contracts Tracked: 0",
                    "Likely Cause: Weekend or missing source data",
                    "System: Continuing to next phase"
                ], success=False)
                return {'success': False, 'duration_seconds': airline_duration, 'error': 'no data'}

        except Exception as e:
            queue_error(
                error_type='airline_tracking_fatal_error',
                context={
                    'exception_type': type(e).__name__,
                    'error_message': str(e),
                    'performance_db': 'data/performance.db'
                },
                severity='ERROR'
            )
            self.beautiful_log("Airline tracking phase encountered fatal error: {}".format(e), 'error')
            self.create_status_box("💥 AIRLINE TRACKING FATAL ERROR", [
                "Airline tracking operation crashed",
                "Error: {}".format(str(e)[:60]),
                "Impact: No airline-specific data available",
                "System: Continuing to next phase"
            ], success=False)
            traceback.print_exc()
            return {'success': False, 'duration_seconds': time.time() - airline_start, 'error': str(e)}

    def run_database_backup(self, backup_type="daily"):
        """Run database backup with enhanced theming

        Args:
            backup_type: 'daily' for datalake_backup.db or 'weekly' for datalake_backup_weekly.db

        Returns:
            dict: {'success': bool, 'duration_seconds': float, 'stdout': str}
        """
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
            title,
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
                self.beautiful_log("❌ BACKUP FAILED: Script not found: {}".format(backup_script), 'error')
                self.create_status_box("💥 BACKUP SCRIPT MISSING", [
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
                    self.beautiful_log("❌ WEEKLY BACKUP FAILED: Daily backup not found", 'error')
                    self.create_status_box("❌ WEEKLY BACKUP FAILED", [
                        "Daily backup not found: {}".format(source_backup),
                        "Weekly backup requires successful daily backup first",
                        "⚠️ Weekly recovery point not created"
                    ], success=False)
                    return {'success': False, 'duration_seconds': 0, 'error': 'Daily backup not found'}

                # Chunked copy with progress reporting
                source_size = os.path.getsize(source_backup)
                source_size_gb = source_size / (1024 ** 3)
                self.beautiful_log("Copying {:.1f} GB: {} -> {}".format(
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
                            logging.info("  Progress: {:.1f} / {:.1f} GB ({:.0f}%)".format(
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

                self.create_status_box("✅ BACKUP OPERATION COMPLETE", box_lines)
                return {'success': True, 'duration_seconds': backup_wall_clock, 'stdout': result.stdout or ''}
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown backup error"
                self.beautiful_log("❌ DATABASE BACKUP FAILED: {}".format(error_msg), 'error')
                self.log_subprocess_error('db_backup.py', result)
                self.create_status_box("❌ BACKUP OPERATION FAILED", [
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
            self.beautiful_log("❌ DATABASE BACKUP FATAL ERROR: {}".format(e), 'error')
            self.create_status_box("💥 BACKUP PROCESS CRASHED", [
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
