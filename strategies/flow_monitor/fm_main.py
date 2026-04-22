#!/usr/bin/env python3
"""
Flow Monitor Orchestrator (fm_main.py)
-------------------------------------
Enhanced Flow Monitor pipeline with integrated task scheduling.
Supports test mode, single-run execution, and analysis-only for a given scan timestamp.

ENHANCEMENT: Added task scheduling framework for daily data collection tasks
- Pre-market tasks (8:00-9:25 AM)
- Post-market tasks (4:15-6:00 PM) 
- Coffee breaks between task phases
- Modular task registration system

Created: 2025-06-29
Author: Ben (with assistance from Chatty) <- Oh thats interesting I used ChatGPT here, probably out of usage haha
Enhanced: 2025-07-22 (with assistance from Claude)
"""

import argparse
import logging
import signal
import threading
import sys
import time
import os
import traceback
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from pathlib import Path

from strategies.flow_monitor.fm_config import FMConfig, shutdown_event
from strategies.flow_monitor.fm_storage import FlowMonitorStorage
from strategies.flow_monitor.fm_collector import FMCollector, MAG7_SYMBOLS, get_symbols_klmn800
from strategies.flow_monitor.fm_analyzer import FMAnalyzer
from strategies.flow_monitor.fm_alerts import FMAlerts
from strategies.flow_monitor.fm_symbol_rollup import SymbolSummaryBuilder
from strategies.flow_monitor.fm_health_reporter import FMHealthReporter
from strategies.flow_monitor import fm_watchlist
from strategies.flow_monitor import fm_alert_resolver
from tools.log_utils import beautiful_log, create_status_box
from strategies.flow_monitor.fm_session_stats import FMSessionStats
from tools.timezone_utils import now_eastern, eastern_isoformat

import subprocess
import json


# Global shutdown event
shutdown_event = threading.Event()

# Global health tracking replaced by class instances
# See FMHealthReporter class


def display_market_snapshot(collector):
    """Display live market conditions (SPY/QQQ/VIX) and persist to market_daily_summary.

    Uses collector's Tradier client for a single 3-symbol quote call.
    SPY/QQQ/VIX are not in FM universe, so cache always misses = fresh data.

    Also writes/updates today's market_daily_summary row with core fields
    (SPY/QQQ/VIX prices, change %, regime, direction). The post-market
    collect_market_data() overwrites this with the full-fat version (breadth,
    sector ETFs, highs/lows). Quick sync copies the row to the query DB each cycle.
    """
    try:
        quotes = collector.tradier_client.get_quotes(['SPY', 'QQQ', 'VIX'], max_age_seconds=60)
        if not quotes:
            logging.debug("Market snapshot: no quotes returned")
            return

        parts = []
        for sym in ['SPY', 'QQQ', 'VIX']:
            q = quotes.get(sym)
            if not q:
                continue
            price = q.get('last', 0)
            change_pct = q.get('change_percentage', 0) or 0
            arrow = '🟢' if change_pct > 0 else '🔴' if change_pct < 0 else '⚪'
            sign = '+' if change_pct > 0 else ''
            parts.append('{} {}  ${:.2f} ({}{}%)'.format(arrow, sym, price, sign, change_pct))

        if parts:
            print('   📊 ' + '  |  '.join(parts))

        # Persist to market_daily_summary so query DB gets fresh regime data
        _persist_market_snapshot(quotes)
    except Exception as e:
        logging.debug("Market snapshot failed: {}".format(e))


def _persist_market_snapshot(quotes):
    """Write/update today's market_daily_summary row with core market fields.

    Uses INSERT OR REPLACE on trade_date (PK). Only populates SPY/QQQ/VIX
    columns + regime + direction. The post-market collect_market_data() run
    overwrites with the complete row (breadth, sector ETFs, etc.).

    Writes to production datalake.db. Quick sync carries it to query DB.
    """
    import sqlite3
    from tools.decimal_formatter import clean_database_row

    try:
        spy = quotes.get('SPY', {})
        qqq = quotes.get('QQQ', {})
        vix = quotes.get('VIX', {})

        spy_last = spy.get('last', 0) or 0
        spy_change = spy.get('change_percentage', 0) or 0
        vix_last = vix.get('last', 0) or 0
        vix_change = vix.get('change_percentage', 0) or 0

        # VIX regime classification (CBOE standards, matches market_daily_summary.py)
        regime = None
        multiplier = None
        if vix_last > 0:
            if vix_last < 15:
                regime, multiplier = 'low_vol', 0.8
            elif vix_last < 20:
                regime, multiplier = 'normal', 1.0
            elif vix_last < 30:
                regime, multiplier = 'elevated', 1.2
            else:
                regime, multiplier = 'panic', 1.5

        # Market direction (matches market_daily_summary.py logic)
        if spy_change > 1.0 and vix_change < -5.0:
            direction = "Strong Bull"
        elif spy_change > 0.5 and vix_change < 0:
            direction = "Bull"
        elif spy_change < -1.0 and vix_change > 5.0:
            direction = "Strong Bear"
        elif spy_change < -0.5 and vix_change > 0:
            direction = "Bear"
        else:
            direction = "Neutral"

        trade_date = now_eastern().strftime('%Y-%m-%d')

        row = {
            'spy_close': spy_last,
            'spy_change_percent': spy_change,
            'spy_open': spy.get('open', None),
            'spy_high': spy.get('high', None),
            'spy_low': spy.get('low', None),
            'spy_volume': spy.get('volume', None),
            'vix_close': vix_last,
            'vix_change_percent': vix_change,
            'vix_open': vix.get('open', None),
            'vix_high': vix.get('high', None),
            'vix_low': vix.get('low', None),
            'qqq_close': qqq.get('last', None),
            'qqq_change_percent': qqq.get('change_percentage', None),
            'regime_classification': regime,
            'regime_multiplier': multiplier,
            'market_direction': direction,
        }
        row = clean_database_row(row)

        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'datalake.db')
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            # INSERT if no row exists; UPDATE only our columns if row already exists.
            # This preserves breadth/sector data if post-market has already written the full row.
            conn.execute("""
                INSERT INTO market_daily_summary (
                    trade_date, spy_close, spy_change_percent, spy_open, spy_high, spy_low, spy_volume,
                    vix_close, vix_change_percent, vix_open, vix_high, vix_low,
                    qqq_close, qqq_change_percent,
                    regime_classification, regime_multiplier, market_direction,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_date) DO UPDATE SET
                    spy_close = excluded.spy_close,
                    spy_change_percent = excluded.spy_change_percent,
                    spy_open = excluded.spy_open,
                    spy_high = excluded.spy_high,
                    spy_low = excluded.spy_low,
                    spy_volume = excluded.spy_volume,
                    vix_close = excluded.vix_close,
                    vix_change_percent = excluded.vix_change_percent,
                    vix_open = excluded.vix_open,
                    vix_high = excluded.vix_high,
                    vix_low = excluded.vix_low,
                    qqq_close = excluded.qqq_close,
                    qqq_change_percent = excluded.qqq_change_percent,
                    regime_classification = excluded.regime_classification,
                    regime_multiplier = excluded.regime_multiplier,
                    market_direction = excluded.market_direction,
                    created_at = excluded.created_at
            """, (
                trade_date,
                row.get('spy_close'), row.get('spy_change_percent'),
                row.get('spy_open'), row.get('spy_high'), row.get('spy_low'), row.get('spy_volume'),
                row.get('vix_close'), row.get('vix_change_percent'),
                row.get('vix_open'), row.get('vix_high'), row.get('vix_low'),
                row.get('qqq_close'), row.get('qqq_change_percent'),
                row.get('regime_classification'), row.get('regime_multiplier'),
                row.get('market_direction'),
                eastern_isoformat(),
            ))
            conn.commit()
        finally:
            conn.close()
        logging.debug("Market snapshot persisted to market_daily_summary")
    except Exception as e:
        logging.debug("Failed to persist market snapshot: {}".format(e))


def get_dynamic_symbol_count():
    """Get actual current symbol count"""
    try:
        symbols = get_symbols_klmn800()
        return len(symbols)
    except:
        return 0

# =============================================================================
# TASK SCHEDULING FRAMEWORK
# =============================================================================




def coffee_break(duration=60, message="Taking a coffee break", context='default', next_task=None):
    """Timed pause with visual feedback using standard log_utils formatting"""
    from tools.log_utils import create_status_box

    context_messages = {
        'backfill_complete': "Data refreshed — all symbols have current pricing",
        'backfill_partial': "Data partially refreshed — some symbols failed",
        'rollup_complete': "Symbol analysis complete — daily metrics calculated",
        'pre_evaluation': "Running performance evaluation",
        'task_complete': "Task complete",
        'tasks_complete': "All daily tasks completed successfully",
        'pipeline_transition': "Pipeline complete — preparing for next phase",
        'sync_complete': "Query DB synced",
        'default': "Quick coffee break"
    }
    msg = context_messages.get(context, context_messages['default'])

    lines = [msg, "Duration: {} seconds".format(duration)]
    if next_task:
        lines.append("Up Next: {}".format(next_task))
    create_status_box("☕ Coffee Break", lines)

    # Interruptible sleep - check shutdown every 5 seconds
    for i in range(duration // 5):
        if shutdown_event.is_set():
            logging.info("Coffee break interrupted - shutting down gracefully")
            break
        time.sleep(5)
    remaining = duration % 5
    if remaining > 0 and not shutdown_event.is_set():
        time.sleep(remaining)

def is_pre_market_window():
    """Check if we're in pre-market task window (9:15-9:25 AM)"""
    now = now_eastern()
    return (now.hour == 9 and 15 <= now.minute < 25)

def is_post_market_window():
    """Check if we're in post-market task window (4:15 PM or later)"""
    now = now_eastern()
    return now.hour >= 16 and now.minute >= 15  # 4:15 PM or later




# =============================================================================
# TASK IMPLEMENTATIONS
# =============================================================================

import subprocess

def run_subprocess_task(task_name, command, timeout=300, max_retries=2, health_reporter=None):
    """Universal subprocess runner with logging, error handling, and retry logic
    
    Args:
        task_name: Display name for logging
        command: List of command arguments to run
        timeout: Timeout in seconds (default 300)
        max_retries: Maximum retry attempts (default 2)
        
    Returns:
        bool: True if successful, False otherwise
    """
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait_time = 30 * (2 ** (attempt - 1))  # 30s, 60s
            logging.info("Retry {} of {} for {} (waiting {}s)".format(
                attempt, max_retries, task_name, wait_time))
            time.sleep(wait_time)

        logging.debug("Running {}...".format(task_name))

        try:
            # Execute with timeout and capture output - force UTF-8 encoding
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                env=env
            )

            if result.returncode == 0:
                # Check for "already exists" scenarios (not a failure)
                if "already exists" in result.stderr or "already exists" in result.stdout:
                    logging.info("{}: Data already current".format(task_name))
                else:
                    logging.debug("{} completed successfully".format(task_name))
                if health_reporter:
                    health_reporter.update_health_status(task_name, "success")
                return True
            else:
                # Enhanced error reporting - show more context
                logging.warning("{} failed (attempt {})".format(task_name, attempt + 1))

                # Show stderr if present
                if result.stderr:
                    error_lines = result.stderr.strip().split('\n')
                    # Show last 5 lines of error output for better context
                    relevant_errors = error_lines[-5:]
                    for line in relevant_errors:
                        if line.strip():
                            logging.error("   {}".format(line))

                # Also check stdout for error messages
                if result.stdout and "error" in result.stdout.lower():
                    output_lines = result.stdout.strip().split('\n')
                    for line in output_lines[-3:]:
                        if "error" in line.lower():
                            logging.error("   {}".format(line))

                if health_reporter:
                    health_reporter.update_health_status(task_name, "failed", error=True)

        except subprocess.TimeoutExpired:
            logging.error("{} timed out after {} seconds (attempt {})".format(
                task_name, timeout, attempt + 1))
            if health_reporter:
                health_reporter.update_health_status(task_name, "timeout", error=True)
        except Exception as e:
            logging.error("{} error (attempt {}): {}".format(task_name, attempt + 1, e))
            if health_reporter:
                health_reporter.update_health_status(task_name, "failed", error=True)

    logging.error("{} failed after {} attempts".format(task_name, max_retries + 1))
    return False

def run_historical_backfill(health_reporter=None):
    """Execute historical backfill with progress tracking and beautiful display

    Component: subprocess (data.tradier_historical_backfill)
    Returns dict with: success, duration_seconds, symbols_updated, symbols_total,
                       partial (True if exit code 2), return_code
    Exit codes: 0=perfect, 1=catastrophic, 2=partial success
    Parses stdout for 'Symbols with data: N/M' to extract metrics.
    """
    start_time = time.time()

    try:
        # Execute backfill with real-time output streaming
        process = subprocess.Popen(
            [sys.executable, '-m', 'data.tradier_historical_backfill', '--no-interaction'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # Stream output line by line and capture for parsing
        output_lines = []
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                output_lines.append(output.strip())
                # Strip subprocess logging prefix (e.g., "2026-02-19 16:30:00,975 - INFO - ")
                line_text = output.strip()
                if ' - INFO - ' in line_text:
                    line_text = line_text.split(' - INFO - ', 1)[1]
                elif ' - WARNING - ' in line_text:
                    line_text = line_text.split(' - WARNING - ', 1)[1]
                elif ' - ERROR - ' in line_text:
                    line_text = line_text.split(' - ERROR - ', 1)[1]
                # Skip init noise and completion stats (redundant with beautiful_log summary)
                if any(skip in line_text for skip in ['initialized', 'Estimated time',
                        'Historical update completed', 'Symbols with data',
                        'Total records', 'API calls made', 'Total time:']):
                    continue
                logging.info("   {}".format(line_text))

        return_code = process.poll()

        # Parse actual results from output
        success_count = None
        total_symbols = None
        for line in output_lines:
            if 'Symbols with data:' in line:
                # Parse "Symbols with data: 750/759 (98.8%)"
                try:
                    parts = line.split('Symbols with data:')[1].strip().split('/')
                    success_count = int(parts[0])
                    total_symbols = int(parts[1].split()[0])
                except:
                    pass

        duration = time.time() - start_time

        # Handle exit codes: 0=perfect, 1=catastrophic, 2=partial success
        if return_code == 0:
            # Check if we finished early and need to wait
            now = now_eastern()
            if now.hour < 9:  # Before 9:00 AM
                wait_until = now.replace(hour=9, minute=0, second=0, microsecond=0)
                wait_seconds = (wait_until - now).total_seconds()
                if wait_seconds > 0:
                    logging.info("Backfill completed early. Waiting {:.0f} minutes until 9:00 AM...".format(wait_seconds / 60))

                    # Interruptible wait
                    for i in range(int(wait_seconds) // 30):
                        if shutdown_event.is_set():
                            return {'success': False, 'duration_seconds': time.time() - start_time,
                                    'symbols_updated': success_count, 'symbols_total': total_symbols,
                                    'partial': False, 'return_code': return_code}
                        time.sleep(30)

                    # Handle remainder
                    remainder = int(wait_seconds) % 30
                    if remainder > 0 and not shutdown_event.is_set():
                        time.sleep(remainder)

            beautiful_log("Backfill complete: {}/{} symbols ({:.1f} min)".format(
                success_count if success_count is not None else '?',
                total_symbols if total_symbols is not None else '?',
                duration / 60), 'success')

            # Coffee break after backfill
            coffee_break(60, context='backfill_complete', next_task='Market Regime Summary')
            return {
                'success': True,
                'duration_seconds': duration,
                'symbols_updated': success_count,
                'symbols_total': total_symbols,
                'partial': False,
                'return_code': return_code,
            }

        elif return_code == 2:
            # Partial success - some failures but below 15% threshold
            logging.warning("Historical backfill completed with failures")
            if success_count and total_symbols:
                logging.warning("   {} of {} symbols updated ({} failed)".format(
                    success_count, total_symbols, total_symbols - success_count))
            logging.warning("   Failures shown above - may need symbol updates")

            beautiful_log("Backfill complete: {}/{} symbols ({:.1f} min)".format(
                success_count if success_count is not None else '?',
                total_symbols if total_symbols is not None else '?',
                duration / 60), 'success')

            # Still continue pipeline - data is mostly good
            coffee_break(60, context='backfill_partial', next_task='Market Regime Summary')
            return {
                'success': True,
                'duration_seconds': duration,
                'symbols_updated': success_count,
                'symbols_total': total_symbols,
                'partial': True,
                'return_code': return_code,
            }

        else:
            # Catastrophic failure (exit code 1 or other)
            logging.error("Historical backfill failed with return code: {}".format(return_code))
            return {
                'success': False,
                'duration_seconds': duration,
                'symbols_updated': success_count,
                'symbols_total': total_symbols,
                'partial': False,
                'return_code': return_code,
            }

    except Exception as e:
        if 'process' in locals():
            try:
                process.terminate()
            except:
                pass
        logging.error("Historical backfill error: {}".format(e))
        return {
            'success': False,
            'duration_seconds': time.time() - start_time,
            'symbols_updated': None,
            'symbols_total': None,
            'partial': False,
            'return_code': -1,
        }


def run_quick_sync():
    """Execute quick database sync to keep query DB current during market hours

    Syncs flow_alerts, flow_options_scans, flow_watchlist_daily, and
    market_daily_summary from datalake.db to datalake_query.db using
    watermark approach. Non-blocking if fails.

    Returns:
        tuple: (success: bool, sync_time: float, row_count: int)
    """
    try:
        start_time = time.time()
        logging.info("Syncing flow_alerts, flow_options_scans, flow_watchlist_daily, market_daily_summary to query database")

        # Execute quick-sync subprocess
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            [sys.executable, 'data/health/db_backup.py', '--quick-sync'],
            capture_output=True,
            text=True,
            timeout=None,  # No timeout - let quick-sync run to completion (prevents DB corruption)
            encoding='utf-8',
            errors='replace',
            env=env
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            # Parse output to extract row count
            row_count = 0
            for line in result.stdout.split('\n'):
                if 'Total new rows added:' in line:
                    try:
                        row_count = int(line.split(':')[1].strip())
                    except:
                        pass

            if row_count > 0:
                beautiful_log("Quick-sync completed: {:,} rows in {:.1f}s".format(
                    row_count, elapsed), 'success')
            else:
                beautiful_log("Quick-sync completed: already up to date ({:.1f}s)".format(
                    elapsed), 'success')

            return (True, elapsed, row_count)
        else:
            # Sync failed - log but don't crash
            logging.warning("Quick-sync failed (non-critical) - took {:.1f}s".format(elapsed))

            # Show comprehensive error details from both stdout and stderr
            error_output = (result.stdout or '') + (result.stderr or '')
            if error_output:
                # Extract ALL diagnostic information
                diagnostic_lines = []
                error_lines = []

                for line in error_output.split('\n'):
                    line_stripped = line.strip()
                    # Capture error messages
                    if any(keyword in line for keyword in ['❌ ERROR:', 'Error:', 'UNIQUE constraint', 'Cause:', 'Fix:', 'Failed on table:']):
                        error_lines.append(line_stripped)
                    # Capture diagnostic data (watermarks, row counts, table info)
                    elif any(keyword in line for keyword in ['Watermark:', 'Rows to sync:', '- Table:', 'Sync Diagnostics:', 'Table: flow_', 'Table: oi_']):
                        diagnostic_lines.append(line_stripped)

                # Show diagnostics first (context)
                if diagnostic_lines:
                    logging.warning("   Diagnostic info:")
                    for line in diagnostic_lines[:10]:  # Show up to 10 diagnostic lines
                        if line:
                            logging.warning("   {}".format(line))

                # Then show error messages
                if error_lines:
                    for line in error_lines[:8]:  # Show up to 8 error lines
                        if line:
                            logging.warning("   {}".format(line))
                elif not diagnostic_lines:
                    # Fallback: show last few lines if no structured data found
                    all_lines = error_output.strip().split('\n')
                    for line in all_lines[-8:]:
                        if line.strip() and not line.startswith('='):
                            logging.warning("   {}".format(line.strip()))

            return (False, elapsed, 0)

    except subprocess.TimeoutExpired as e:
        logging.warning("Quick-sync timeout (>5min) - query DB may lag")

        # Try to capture any output that was generated before timeout
        try:
            partial_output = e.stdout if hasattr(e, 'stdout') else None
            if partial_output:
                logging.warning("   Partial output before timeout:")
                # Look for diagnostic info (watermark, rows to sync)
                for line in partial_output.split('\n'):
                    if any(keyword in line for keyword in ['Watermark:', 'Rows to sync:', 'Syncing ', 'Table:']):
                        logging.warning("   {}".format(line.strip()))
        except:
            pass

        logging.warning("   Likely cause: Too many rows to sync or database locked")
        logging.warning("   Try: Run full sync manually to reset state")
        return (False, 300.0, 0)

    except Exception as e:
        logging.warning("Quick-sync error: {} - query DB may lag".format(e))
        return (False, 0.0, 0)


# =============================================================================
# EXISTING FUNCTIONALITY (PRESERVED)
# =============================================================================

def handle_shutdown(signum, frame):
    logging.info("Ctrl+C detected. Will shut down after current cycle completes.")
    shutdown_event.set()

def setup_logging(debug=False, log_to_file=True):
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    level = logging.DEBUG if debug else logging.INFO

    import io
    stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    handlers = [logging.StreamHandler(stream)]

    if log_to_file:
        # CHANGED: Centralized logs directory at project root
        logs_dir = Path(__file__).parent.parent.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime

        # CHANGED: Renamed from fm_main to flow_monitor
        logfile_name = f"flow_monitor_{datetime.now().strftime('%Y-%m-%d')}.log"
        logfile = logs_dir / logfile_name
        rotating_handler = TimedRotatingFileHandler(
            filename=logfile,
            when='midnight',
            interval=1,
            backupCount=7,  # Keep 7 days of logs
            encoding='utf-8',
            delay=False,
            utc=False
        )
        handlers.append(rotating_handler)

    logging.basicConfig(level=level, format=log_format, datefmt=date_format, handlers=handlers)

    # Suppress milliseconds on console handler for clean HH:MM:SS display
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.formatter.default_msec_format = None

def setup_diagnostic_logging():
    """Set up separate diagnostic log for high-level summaries only"""
    logs_dir = Path(__file__).parent.parent.parent / "logs" / "diagnostic"
    logs_dir.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    logfile_name = f"flow_monitor_{datetime.now().strftime('%Y-%m-%d')}.log"
    logfile = logs_dir / logfile_name

    # Create dedicated diagnostic logger
    diag_logger = logging.getLogger('flow_monitor_diagnostic')
    diag_logger.setLevel(logging.INFO)
    diag_logger.propagate = False  # Don't send to root logger

    # Clear any existing handlers
    diag_logger.handlers = []

    # File handler only (no console spam)
    file_handler = logging.FileHandler(logfile, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Simple format: just timestamp and message
    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)

    diag_logger.addHandler(file_handler)

    return diag_logger

def log_diagnostic_summary(diag_logger, storage, scan_timestamp, symbols_attempted, collection_time, analysis_time, alert_time, sync_time, sync_rows, storage_time=0):
    """Write high-level diagnostic summary for this scan

    Args:
        diag_logger: Diagnostic logger instance
        storage: FlowMonitorStorage instance for queries
        scan_timestamp: Timestamp of this scan
        symbols_attempted: Number of symbols attempted
        collection_time: Collection duration in seconds
        analysis_time: Analysis duration in seconds
        alert_time: Alert processing duration in seconds
        sync_time: DB sync duration in seconds
        sync_rows: Number of rows synced
        storage_time: DB write duration in seconds (subset of collection_time)
    """
    try:
        # Query contract counts
        contracts_query = "SELECT COUNT(*) as count FROM flow_options_scans WHERE scan_timestamp = ?"
        contracts_result = storage.query_with_params(contracts_query, (scan_timestamp,))
        contracts_count = contracts_result[0]['count'] if contracts_result else 0

        # Query alert counts by score level
        alerts_query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN significance_score >= 5.0 THEN 1 ELSE 0 END) as high,
                SUM(CASE WHEN significance_score >= 3.5 AND significance_score < 5.0 THEN 1 ELSE 0 END) as med,
                SUM(CASE WHEN significance_score < 3.5 THEN 1 ELSE 0 END) as low
            FROM flow_alerts
            WHERE scan_timestamp = ?
        """
        alerts_result = storage.query_with_params(alerts_query, (scan_timestamp,))
        alerts_total = alerts_result[0]['total'] if alerts_result else 0
        alerts_high = alerts_result[0]['high'] if alerts_result else 0
        alerts_med = alerts_result[0]['med'] if alerts_result else 0
        alerts_low = alerts_result[0]['low'] if alerts_result else 0

        # Query unique symbols with data
        symbols_query = "SELECT COUNT(DISTINCT symbol) as count FROM flow_options_scans WHERE scan_timestamp = ?"
        symbols_result = storage.query_with_params(symbols_query, (scan_timestamp,))
        symbols_with_data = symbols_result[0]['count'] if symbols_result else 0

        # Get actual alerts for display (limit to HIGH conviction)
        alert_details_query = """
            SELECT symbol, strike, option_type, expiration_date, significance_score,
                   volume, open_interest, last_price, underlying_price, iv,
                   iv_percentile_30d
            FROM flow_alerts
            WHERE scan_timestamp = ? AND significance_score >= 5.0
            ORDER BY significance_score DESC
            LIMIT 5
        """
        alert_details = storage.query_with_params(alert_details_query, (scan_timestamp,))

        # Format diagnostic log entry
        diag_logger.info(f"[{scan_timestamp}] Collection: {collection_time:.1f}s | Symbols: {symbols_attempted} attempted, {symbols_with_data} returned data | Contracts: {contracts_count:,}")
        diag_logger.info(f"[{scan_timestamp}] Analysis: {analysis_time:.1f}s | Alerts: {alerts_total} sent ({alerts_high} HIGH, {alerts_med} MED, {alerts_low} LOW)")
        diag_logger.info(f"[{scan_timestamp}] Performance: Collection {collection_time:.1f}s (API {collection_time - storage_time:.1f}s + DB Write {storage_time:.1f}s), Analysis {analysis_time:.1f}s, Alerts {alert_time:.1f}s, Sync {sync_time:.1f}s")

        # Log HIGH conviction alerts with details
        if alert_details:
            for alert in alert_details:
                # Calculate premium (volume * last_price * 100)
                premium = alert['volume'] * alert['last_price'] * 100 if alert['volume'] and alert['last_price'] else 0
                vol_oi_ratio = alert['volume'] / alert['open_interest'] if alert['open_interest'] and alert['open_interest'] > 0 else 0

                ivp = alert['iv_percentile_30d']
                ivp_str = "{:.0f}".format(ivp) if ivp is not None else "--"

                diag_logger.info(
                    f"[{scan_timestamp}] ALERT: {alert['symbol']} ${alert['strike']} {alert['option_type']}s "
                    f"({alert['expiration_date']}) | Score: {alert['significance_score']:.1f} | "
                    f"Vol: {alert['volume']:,} | V/OI: {vol_oi_ratio:.1f} | "
                    f"Premium: ${premium:,.0f} | IV: {alert['iv']:.0f}% | IVP: {ivp_str}"
                )

    except Exception as e:
        # Don't crash on diagnostic logging errors
        logging.error(f"Error writing diagnostic summary: {e}")

# Memory logging removed (FMPerformanceTracker deprecated 2026-02-23, PRD 0007)

# Health status tracking moved to FMHealthReporter class

def check_task_disabled(task_name):
    """Check if task is disabled via emergency override in config
    
    Args:
        task_name: Name of task to check
        
    Returns:
        bool: True if task should be skipped
    """
    # Emergency task override removed - config key no longer exists
    # If needed in future, add 'disabled_tasks' list to flow_monitor config
    return False
        
def run_pipeline(collector, analyzer, alerts, storage, symbols, force=False, test_mode=False):
    """Simple dispatcher to appropriate pipeline based on context
    
    Maintains backward compatibility with existing entry points while
    routing to the clean three-pipeline architecture.
    """
    # Handle test mode - just run collection/analysis/alerts once
    if test_mode or force:
        if force:
            scan_timestamp = collector.run_once_forced(symbols)
        else:
            scan_timestamp = collector.run_once(symbols)
            
        if scan_timestamp:
            logging.info("Collection complete: {}".format(scan_timestamp))
            analyzer.analyze(scan_timestamp, test_mode=test_mode)
            alerts.process_alerts(scan_timestamp, test_mode=test_mode,
                                  scan_contracts=getattr(analyzer, 'last_scan_contracts', None))
            # Memory logging handled by performance tracker if available
        else:
            logging.warning("Collection failed or aborted.")
        
        # Summary feature removed - no longer supported
        
        return
    
    # For normal operation, this shouldn't be called directly anymore
    # Use --pre-market, --market-hours, or --post-market entry points
    logging.warning("run_pipeline called in normal mode - this is deprecated")
    logging.warning("   Use --pre-market, --market-hours, or --post-market instead")

def run_evening_market_regime_summary(health_reporter=None):
    """Execute evening market regime summary with combined Tradier + FMP data

    Component: subprocess (data.market_daily_summary) via run_subprocess_task()
    Returns dict with: success, duration_seconds, direction, regime, spy_close, spy_change_pct, vix_close
    Subprocess boundary — exit code is the only signal available.
    Regime data fetched via post-subprocess DB query on market_daily_summary.
    """
    start_time = time.time()
    if check_task_disabled("Evening Market Regime Summary"):
        return {'success': True, 'duration_seconds': 0.0, 'skipped': True}

    subprocess_success = run_subprocess_task(
        "Evening Market Summary",
        [sys.executable, '-m', 'data.market_daily_summary', '--no-interaction'],
        timeout=600,
        health_reporter=health_reporter
    )

    # Query actual regime results from the database
    regime_data = {}
    if subprocess_success:
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'datalake.db')
            trade_date = now_eastern().strftime('%Y-%m-%d')

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT market_direction, regime_classification, spy_close, spy_change_percent, vix_close
                FROM market_daily_summary
                WHERE trade_date = ?
            """, (trade_date,))
            row = cursor.fetchone()
            conn.close()

            if row:
                regime_data = {
                    'direction': row['market_direction'],
                    'regime': row['regime_classification'],
                    'spy_close': row['spy_close'],
                    'spy_change_pct': row['spy_change_percent'],
                    'vix_close': row['vix_close'],
                }
        except Exception as e:
            logging.debug("Could not fetch regime results: {}".format(e))

    if regime_data:
        spy_pct = regime_data.get('spy_change_pct', 0) or 0
        spy_sign = '+' if spy_pct >= 0 else ''
        beautiful_log("Regime: {} | {} | SPY {}{}% | VIX {}".format(
            regime_data.get('regime', '?'),
            regime_data.get('direction', '?'),
            spy_sign, "{:.2f}".format(spy_pct),
            regime_data.get('vix_close', '?')), 'info')

    return {
        'success': bool(subprocess_success),
        'duration_seconds': time.time() - start_time,
        **regime_data,
    }

def run_symbol_rollup_task(health_reporter=None):
    """Run symbol rollup as a task

    Component: SymbolSummaryBuilder.populate_daily_summary() returns bool.
    Stats available via rollup.stats: symbols_processed, summaries_created, errors.
    Returns dict with: success, duration_seconds, symbols_processed, summaries_created, errors.
    """
    logging.debug("Running end-of-day symbol summary rollup...")

    start_time = time.time()
    try:
        # Get storage from current context - we'll need to pass this as a parameter
        # For now, recreate it locally
        from strategies.flow_monitor.fm_config import FMConfig
        from strategies.flow_monitor.fm_storage import FlowMonitorStorage

        config = FMConfig()
        storage = FlowMonitorStorage(config)

        # Get today's date for rollup
        trade_date = now_eastern().strftime('%Y-%m-%d')

        rollup = SymbolSummaryBuilder(storage)
        rollup_success = rollup.populate_daily_summary(trade_date)
        duration = time.time() - start_time

        # Read stats from the component's stats attribute
        stats = rollup.stats

        if rollup_success:
            beautiful_log("Rollup complete: {} summaries from {} symbols ({:.1f}s)".format(
                stats.get('summaries_created', 0),
                stats.get('symbols_processed', 0),
                duration), 'success')
            return {
                'success': True,
                'duration_seconds': duration,
                'symbols_processed': stats.get('symbols_processed', 0),
                'summaries_created': stats.get('summaries_created', 0),
                'errors': stats.get('errors', 0),
            }
        else:
            logging.warning("Symbol summary rollup failed")
            return {
                'success': False,
                'duration_seconds': duration,
                'symbols_processed': stats.get('symbols_processed', 0),
                'summaries_created': stats.get('summaries_created', 0),
                'errors': stats.get('errors', 0),
            }

    except Exception as e:
        logging.error("Symbol summary rollup error: {}".format(e))
        return {
            'success': False,
            'duration_seconds': time.time() - start_time,
            'symbols_processed': 0,
            'summaries_created': 0,
            'errors': 1,
        }


def run_analysis_backfill_task():
    """Run comprehensive analysis backfill for all today's scans"""
    logging.info("Running comprehensive analysis backfill...")
    
    try:
        from strategies.flow_monitor.fm_config import FMConfig
        from strategies.flow_monitor.fm_storage import FlowMonitorStorage
        from strategies.flow_monitor.fm_analyzer import FMAnalyzer
        
        config = FMConfig()
        storage = FlowMonitorStorage(config)
        analyzer = FMAnalyzer(storage)
        
        # Get all scan timestamps from today
        trade_date = now_eastern().strftime('%Y-%m-%d')
        
        query = '''
            SELECT DISTINCT scan_timestamp 
            FROM flow_options_scans 
            WHERE trade_date = ?
            ORDER BY scan_timestamp
        '''
        
        scan_results = storage.query_with_params(query, (trade_date,))
        
        if not scan_results:
            logging.warning("No scans found for today - nothing to backfill")
            return True
        
        scan_count = len(scan_results)
        logging.info("Found {} scans from today to backfill".format(scan_count))
        
        successful_scans = 0
        
        for i, scan_row in enumerate(scan_results, 1):
            scan_timestamp = scan_row['scan_timestamp']
            
            logging.info("   Scan {}/{}: {} (backfill mode)".format(i, scan_count, scan_timestamp))
            
            try:
                # Run analysis in backfill mode (no filtering, comprehensive scoring)
                results = analyzer.analyze(scan_timestamp, test_mode=False, backfill_mode=True)
                
                if results and results.get('contracts_updated', 0) > 0:
                    logging.info("     Updated {} contracts".format(results['contracts_updated']))
                    successful_scans += 1
                else:
                    logging.warning("     No updates applied")
                    
            except Exception as e:
                logging.error("     Scan failed: {}".format(e))
                logging.error("Backfill analysis failed for scan {}: {}".format(scan_timestamp, e))
        
        if successful_scans == scan_count:
            logging.info("Analysis backfill completed - all {} scans processed".format(scan_count))
            return True
        else:
            logging.warning("Analysis backfill partial success - {}/{} scans processed".format(successful_scans, scan_count))
            return successful_scans > 0  # Return true if at least some succeeded
            
    except Exception as e:
        logging.error("Analysis backfill task failed: {}".format(str(e)))
        logging.error("Analysis backfill task error: {}".format(e))
        return False

def run_daily_evaluation_task(health_reporter=None):
    """Run daily alert evaluation with enhanced error handling and real-time progress

    Component: subprocess (strategies.flow_monitor.evaluation.run_daily_evaluation)
    Returns dict with: success, duration_seconds, return_code
    Subprocess boundary — exit code is the only signal available.
    """
    start_time = time.time()
    try:
        # Execute with real-time output streaming (like historical backfill)
        process = subprocess.Popen(
            [sys.executable, '-m', 'strategies.flow_monitor.evaluation.run_daily_evaluation', '--automated'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            universal_newlines=True
        )

        # Stream output line by line
        skip_patterns = ['initialized', 'Daily Evaluation', '====', '---', 'Schema',
                         'Database:', 'Trade date:', 'Starting evaluation',
                         'Checking for running', 'No conflicting', 'Initializing',
                         'Log file:', 'Verifying database', '[OK]', 'Current time:',
                         'Automated nightly', 'evaluation run starting',
                         'Processing alerts in', 'EVALUATION RUNNER']
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # Strip subprocess logging prefix (e.g., "2026-02-19 16:30:00 - INFO - ")
                line_text = output.strip()
                if ' - INFO - ' in line_text:
                    line_text = line_text.split(' - INFO - ', 1)[1]
                elif ' - WARNING - ' in line_text:
                    line_text = line_text.split(' - WARNING - ', 1)[1]
                elif ' - ERROR - ' in line_text:
                    line_text = line_text.split(' - ERROR - ', 1)[1]
                # Skip blank lines (empty after prefix stripping)
                if not line_text.strip():
                    continue
                # Skip init noise and banner lines
                if any(skip in line_text for skip in skip_patterns):
                    continue
                logging.info("   {}".format(line_text))

        return_code = process.poll()
        duration = time.time() - start_time

        if return_code == 0:
            beautiful_log("Evaluation complete ({:.1f}s)".format(duration), 'success')
            if health_reporter:
                health_reporter.update_health_status("Daily Evaluation", "success")
            return {'success': True, 'duration_seconds': duration, 'return_code': return_code}
        else:
            logging.error("Daily Evaluation failed with return code: {}".format(return_code))
            if health_reporter:
                health_reporter.update_health_status("Daily Evaluation", "failed", error=True)
            return {'success': False, 'duration_seconds': duration, 'return_code': return_code}

    except UnicodeEncodeError as e:
        logging.warning("Daily Evaluation encoding error (non-critical): {}".format(str(e).replace('\u274c', 'X')))
        logging.warning("Evaluation failed due to console encoding - continuing post-market pipeline")
        if health_reporter:
            health_reporter.update_health_status("Daily Evaluation", "encoding_error", error=True)
        return {'success': False, 'duration_seconds': time.time() - start_time, 'return_code': -1}
    except Exception as e:
        if 'process' in locals():
            try:
                process.terminate()
            except:
                pass
        logging.error("Daily Evaluation error: {}".format(str(e)))
        if health_reporter:
            health_reporter.update_health_status("Daily Evaluation", "failed", error=True)
        return {'success': False, 'duration_seconds': time.time() - start_time, 'return_code': -1}

# Summary feature removed - this function is deprecated and no longer used

# OLD PIPELINE FUNCTIONS REMOVED - Replaced with simple execution functions above

# =============================================================================
# NEW: SIMPLE EXECUTION FUNCTIONS (NO DAEMON PATTERN)
# =============================================================================

def _step_header(step_num, total, label):
    """Print a fixed-width step header: ── Step 1/3: Label ──────────────"""
    prefix = "── Step {}/{}: {} ".format(step_num, total, label)
    padding = max(0, 60 - len(prefix))
    print("\n" + prefix + "─" * padding)


def _display_resolution_details(details, today_date):
    """Display per-alert resolution details in a 3-line format per contract.

    Each alert gets:
      Line 1: Contract header (symbol, strike, type, exp) + resolution + score
      Line 2: Alert-day data (UL, OI, Vol, IV, Last)
      Line 3: Today data (UL, OI, OI delta, IV, Last)

    Uses print()+log_to_file() for clean output without timestamp/emoji clutter.
    """
    from tools.log_utils import log_to_file

    if not details:
        return

    # Sort alphabetically by symbol, then by strike
    details_sorted = sorted(details, key=lambda d: (d['symbol'], d['strike']))

    # Count totals for header
    building = sum(1 for d in details_sorted if d['resolution'] == 'BUILDING')
    closing = sum(1 for d in details_sorted if d['resolution'] == 'CLOSING')
    neutral = sum(1 for d in details_sorted if d['resolution'] == 'NEUTRAL')
    total = len(details_sorted)

    def _out(line):
        """Print to console and log file."""
        print(line)
        log_to_file(line)

    # Section header
    header = "── Alert Resolution Details: {} alerts ({} BUILDING, {} CLOSING, {} NEUTRAL) ".format(
        total, building, closing, neutral)
    header += "─" * max(0, 78 - len(header))
    _out("")
    _out(header)

    # Format helpers
    def _fmt_price(val):
        """Format a price value: $123.45 or --"""
        if val is None:
            return "--"
        return "${:.2f}".format(val)

    def _fmt_iv(val):
        """Format IV: .4521 or --"""
        if val is None:
            return "--"
        return ".{:04d}".format(int(val * 10000))

    def _fmt_int(val):
        """Format integer with commas: 12,300 or --"""
        if val is None:
            return "--"
        return "{:,}".format(int(val))

    def _fmt_delta(val):
        """Format OI delta with sign: +3,500 or -1,200"""
        if val is None:
            return "--"
        return "{:+,}".format(int(val))

    def _fmt_date(date_str):
        """Format YYYY-MM-DD as MM/DD"""
        if not date_str or len(date_str) < 10:
            return date_str or "--"
        return "{}/{}".format(date_str[5:7], date_str[8:10])

    # Resolution indicators
    res_indicators = {
        'BUILDING': '\u25b2 BUILDING',   # ▲
        'CLOSING': '\u25bc CLOSING',      # ▼
        'NEUTRAL': '\u2500 NEUTRAL',      # ─
    }

    for detail in details_sorted:
        symbol = detail['symbol']
        strike = detail['strike']
        opt_type = detail['option_type'].upper()[0]  # C or P
        exp = _fmt_date(detail['expiration_date'])
        score = detail.get('significance_score') or 0
        resolution = detail['resolution']
        alert_count = detail.get('alert_count', 1)
        alert_date = _fmt_date(detail.get('alert_date', ''))
        today = _fmt_date(today_date)

        # Header line: NVDA $140C 03/21                    (x2) ▲ BUILDING  Score: 7.10  IVP: 75
        # Format strike: drop trailing .0 for round numbers (230.0 → 230, 62.5 → 62.5)
        strike_str = "{:g}".format(strike) if strike == int(strike) else "{:.2f}".format(strike)
        contract_label = "  {} ${}{} {}".format(symbol, strike_str, opt_type, exp)
        count_tag = "(x{}) ".format(alert_count) if alert_count > 1 else ""
        res_label = res_indicators.get(resolution, resolution)
        ivp = detail.get('iv_percentile_30d')
        ivp_tag = "  IVP: {:.0f}".format(ivp) if ivp is not None else ""
        right_side = "{}{}  Score: {:.2f}{}".format(count_tag, res_label, score, ivp_tag)
        # Pad contract label to align right side
        gap = max(1, 72 - len(contract_label) - len(right_side))
        _out(contract_label + " " * gap + right_side)

        # Alert row: 03/07 alert │ UL $134.50 │ OI 12,300 │ Vol  3,100 │ IV .4521 │ Last $7.10
        alert_line = "  {} alert {} UL {:>8s} {} OI {:>7s} {} Vol  {:>7s} {} IV {:>5s} {} Last {:>7s}".format(
            alert_date,
            "\u2502",  # │
            _fmt_price(detail.get('alert_ul')),
            "\u2502",
            _fmt_int(detail.get('alert_oi')),
            "\u2502",
            _fmt_int(detail.get('alert_vol')),
            "\u2502",
            _fmt_iv(detail.get('alert_iv')),
            "\u2502",
            _fmt_price(detail.get('alert_last')),
        )
        _out(alert_line)

        # Today row: 03/10 today │ UL $138.20 │ OI 15,800 │ OI Δ +3,500 │ IV .4103 │ Last $9.50
        today_line = "  {} today {} UL {:>8s} {} OI {:>7s} {} OI \u0394 {:>7s} {} IV {:>5s} {} Last {:>7s}".format(
            today,
            "\u2502",
            _fmt_price(detail.get('today_ul')),
            "\u2502",
            _fmt_int(detail.get('today_oi')),
            "\u2502",
            _fmt_delta(detail.get('oi_change')),
            "\u2502",
            _fmt_iv(detail.get('today_iv')),
            "\u2502",
            _fmt_price(detail.get('today_last')),
        )
        _out(today_line)
        _out("")  # Blank line between entries


def run_pre_market():
    """Execute pre-market tasks (no timing logic - main.py handles orchestration)

    Order: (1) Alert Resolution → (2) Sentiment Update → (3) Query DB Sync
    Sync is last so it captures both resolution and sentiment writes.

    Returns:
        dict: {
            'success': bool,
            'duration_seconds': float,
            'sub_tasks': {
                'alert_resolution': {'success': bool, 'alerts_resolved': int, 'building': int, 'closing': int, 'neutral': int, 'not_found': int},
                'sentiment_update': {'success': bool, 'symbols_updated': int},
                'sync': {'success': bool, 'alerts_synced': int, 'watchlist_synced': int},
            },
            'alerts_resolved': int,
            'symbols_updated': int,
        }
    """
    start_time = time.time()

    # Initialize components
    config = FMConfig()
    storage = FlowMonitorStorage(config)

    # Initialize stats for failure path
    resolution_stats = {'alerts_resolved': 0, 'building': 0, 'closing': 0, 'neutral': 0, 'not_found': 0}
    sentiment_stats = {'symbols_updated': 0, 'building': 0, 'closing': 0, 'neutral': 0}
    sync_result = {'success': False, 'alerts_synced': 0, 'watchlist_synced': 0, 'elapsed': 0.0}
    resolution_success = True
    sentiment_success = True
    sync_success = False

    try:
        trade_date = now_eastern().strftime('%Y-%m-%d')

        # Need access to Option Pipeline storage for option_contracts table
        from strategies.option_pipeline.op_config import OIDConfig
        from strategies.option_pipeline.op_storage import OIDStorage

        op_config = OIDConfig()
        op_storage = OIDStorage(op_config)

        # ── Step 1/3: Alert Resolution ──────────────────────────────
        _step_header(1, 3, "Alert Resolution")

        beautiful_log("Resolving yesterday's flow alerts", 'info')
        beautiful_log("   Using fresh OI data from morning Option Pipeline", 'info')

        resolution_stats = fm_alert_resolver.resolve_yesterday_alerts(
            trade_date, storage, op_storage
        )

        if resolution_stats['alerts_resolved'] > 0:
            beautiful_log("Alert resolution complete: {} resolved ({} BUILDING, {} CLOSING, {} NEUTRAL)".format(
                resolution_stats['alerts_resolved'],
                resolution_stats['building'],
                resolution_stats['closing'],
                resolution_stats['neutral']
            ), 'success')

            # Display per-alert resolution details
            if resolution_stats.get('details'):
                _display_resolution_details(resolution_stats['details'], trade_date)

            if resolution_stats['not_found'] > 0:
                beautiful_log("{} contracts not found in today's OI data".format(
                    resolution_stats['not_found']), 'warning')
        else:
            beautiful_log("No unresolved alerts from yesterday", 'info')

        # ── Step 2/3: Sentiment Update ──────────────────────────────
        _step_header(2, 3, "Sentiment Update")

        sentiment_stats = fm_alert_resolver.update_watchlist_sentiment(trade_date, storage)

        if sentiment_stats['symbols_updated'] > 0:
            beautiful_log("Watchlist sentiment updated: {} symbols ({} BUILDING, {} CLOSING, {} NEUTRAL)".format(
                sentiment_stats['symbols_updated'],
                sentiment_stats.get('building', 0),
                sentiment_stats.get('closing', 0),
                sentiment_stats.get('neutral', 0)
            ), 'success')
        else:
            beautiful_log("No watchlist symbols to update", 'info')

        # ── Step 3/3: Query Database Sync ───────────────────────────
        _step_header(3, 3, "Query Database Sync")

        try:
            from data.health.db_backup import sync_pre_market_updates
            sync_result = sync_pre_market_updates()
            sync_success = sync_result.get('success', False)

            if sync_success:
                beautiful_log("Pre-market updates synced to query database ({} alerts, {} watchlist rows)".format(
                    sync_result.get('alerts_synced', 0),
                    sync_result.get('watchlist_synced', 0)
                ), 'success')
            else:
                beautiful_log("Pre-market sync to query DB failed (non-critical)", 'warning')
        except Exception as sync_err:
            beautiful_log("Pre-market sync error: {} (non-critical)".format(sync_err), 'warning')

    except Exception as e:
        beautiful_log("Pre-market tasks failed (non-critical): {}".format(e), 'warning')
        logging.error("Pre-market error: {}".format(e))
        resolution_success = False
        sentiment_success = False

    return {
        'success': True,  # Pre-market never fails the pipeline (alert resolution is non-critical)
        'duration_seconds': time.time() - start_time,
        'sub_tasks': {
            'alert_resolution': {
                'success': resolution_success,
                'alerts_resolved': resolution_stats.get('alerts_resolved', 0),
                'building': resolution_stats.get('building', 0),
                'closing': resolution_stats.get('closing', 0),
                'neutral': resolution_stats.get('neutral', 0),
                'not_found': resolution_stats.get('not_found', 0),
            },
            'sentiment_update': {
                'success': sentiment_success,
                'symbols_updated': sentiment_stats.get('symbols_updated', 0),
                'building': sentiment_stats.get('building', 0),
                'closing': sentiment_stats.get('closing', 0),
                'neutral': sentiment_stats.get('neutral', 0),
            },
            'sync': {
                'success': sync_success,
                'alerts_synced': sync_result.get('alerts_synced', 0),
                'watchlist_synced': sync_result.get('watchlist_synced', 0),
            },
        },
        'alerts_resolved': resolution_stats.get('alerts_resolved', 0),
        'symbols_updated': sentiment_stats.get('symbols_updated', 0),
    }

def run_market_hours():
    """Execute market hours monitoring (no wait for 9:30 - main.py handles timing)

    Returns:
        dict: {'success': bool, 'total_cycles': int, 'news_enrichment': dict, 'session_stats': dict}
              news_enrichment has keys: enriched, skipped, failed (accumulated across all cycles)
              session_stats has keys: total_cycles, successful_cycles, failed_cycles, timing,
                  errors, missing_quotes, failed_options, news_enrichment
    """
    # Initialize components
    config = FMConfig()
    storage = FlowMonitorStorage(config)
    collector = FMCollector()
    analyzer = FMAnalyzer(storage)
    alerts = FMAlerts(config, storage)
    symbols = get_symbols_klmn800()
    health_reporter = FMHealthReporter()
    diag_logger = setup_diagnostic_logging()  # Initialize diagnostic logging

    # Earnings signal tracker (optional — config toggle)
    earnings_tracker = None
    est_config = config.flow_monitor_config.get('earnings_signal_tracking', {})
    if est_config.get('enabled', False):
        from strategies.flow_monitor.fm_earnings_signals import FMEarningsSignalTracker
        earnings_tracker = FMEarningsSignalTracker(storage, config.config)

    now = now_eastern()

    # Log diagnostic startup
    diag_logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Flow Monitor market hours started | Symbols: {len(symbols)}")

    # Market hours intro box — shows once at startup as a runtime reference
    create_status_box(
        "🔍 FLOW MONITOR — MARKET HOURS ENGINE",
        [
            "",
            "Real-time monitoring to detect large relative changes in option activity.",
            "Runs continuous cycles identified by scan_timestamp.",
            "Cycles are intended to be quick (< 30 min) to identify bursts of activity.",
            "Runs continuously from 9:30 AM to 4:00 PM ET.",
            "",
            "Universe: KLMN 800 with {} symbols.".format(len(symbols)),
            "",
            "CYCLE: Collect → Analyze → Alert → Watchlist → News → Dip → Earnings → Sync",
            "",
            "📡 Collector",
            "  Gathers option contract data within reasonable ranges.",
            "  Strike: ±20% of UL | DTE: 0-60d (stocks), 8-60d (ETFs)",
            "  Expirations cached 8hr (first cycle fetches, rest use cache)",
            "",
            "🔬 Analyzer (Unified Algorithm)",
            "  Reviews collected option contracts and compares to previous scans.",
            "  Focuses on changes in volume, relative to baselines.",
            "  Score = Premium (0-6) + Volume Surprise (0-4) + Smart Money (0-2)",
            "  Premium thresholds by cap: Mega $400K / Large $300K / Mid $200K",
            "  Volume minimum: 3x normal | Institutional delta filter: >0.85",
            "",
            "🚨 Alerts",
            "  Flags option contracts with significant flow activity.",
            "  Score >= 6.0 (alert) | >= 8.0 (high conviction)",
            "  Delta filter: 0.25-0.75 (excludes deep ITM/OTM) | ETFs excluded",
            "",
            "📋 Watchlist",
            "  One entry per symbol per day | 7-day expiration | Tracks OI Change",
            "",
            "📰 News (Alpha Vantage)",
            "  25 calls/day budget | 3-day lookback | New watchlist entries only",
            "  Determines public sentiment for the symbol.",
            "",
            "📉 Dip Detection",
            "  Looks for changes in underlying price for symbols in watchlist.",
            "  Alerts on modest drops to avoid catching falling knives. Call/Put aware.",
            "  Z-score range: -0.10 to -0.20 | BUILDING sentiment required",
            "  Fallback: -1.5% to -3.5% drop | Email notification on detection",
            "",
            "📈 Earnings Signals{}".format(
                " (every {} cycles)".format(earnings_tracker.check_interval) if earnings_tracker else " (disabled)"),
            "  Recomputes straddle underpricing from live scan data.",
            "  Logs signal upgrades/downgrades vs morning baseline (console only).",
            "",
            "🔄 Quick Sync",
            "  Incremental sync of new scans to datalake_query.db after each cycle",
            "",
        ]
    )

    # Session stats accumulator — restore from daily_state.json if restarted mid-day
    stats = FMSessionStats.load_from_daily_state()

    cycle = 1
    closing_scan_done = False
    last_cycle_start_time = None

    # Market hours monitoring loop
    while not shutdown_event.is_set():
        if not collector.is_market_open():
            if closing_scan_done:
                beautiful_log("Closing scan complete. Ending market hours pipeline.", 'warning')
                break
            # Check if the last cycle already captured near-close data
            if last_cycle_start_time and last_cycle_start_time.hour == 15 and last_cycle_start_time.minute >= 55:
                beautiful_log("Market closed. Last cycle started at {} — close enough for EOD data.".format(
                    last_cycle_start_time.strftime('%H:%M:%S')), 'warning')
                break
            # Market just closed — run one final scan to capture end-of-day positioning
            beautiful_log("Market closed — running closing scan to capture EOD activity", 'info')
            closing_scan_done = True

        cycle_start = time.time()
        current_time = now_eastern()
        last_cycle_start_time = current_time
        
        cycle_prefix = "── Cycle {} | {} | {} symbols ".format(
            cycle, current_time.strftime('%H:%M:%S'), len(symbols))
        print("\n" + cycle_prefix + "─" * max(0, 60 - len(cycle_prefix)))
        
        # Execute core collection/analysis/alert cycle
        collection_elapsed = 0  # Initialize outside try block
        storage_elapsed = 0
        analysis_elapsed = 0
        analysis_query_elapsed = 0
        analysis_scoring_elapsed = 0
        analysis_db_write_elapsed = 0
        alert_elapsed = 0
        watchlist_elapsed = 0
        sync_elapsed = 0
        sync_success = False
        sync_rows = 0
        earnings_signal_elapsed = 0
        scan_timestamp = None  # Initialize to track success
        alerts_stored = 0  # Tracks alerts written this cycle (for performance DB)
        cycle_news_stats = None  # Per-cycle news enrichment results

        try:
            # Collection phase
            collection_start = time.time()
            scan_timestamp = collector.run_once(symbols, closing_scan=closing_scan_done)
            collection_elapsed = time.time() - collection_start
            storage_elapsed = getattr(collector, 'last_storage_elapsed', 0.0)

            if scan_timestamp:
                api_elapsed = collection_elapsed - storage_elapsed
                beautiful_log("Collection complete ({:.1f}s — API: {:.1f}s + DB Write: {:.1f}s)".format(
                    collection_elapsed, api_elapsed, storage_elapsed), 'success')

                # AUTOFIX INTEGRATION: Detect silent failure (zero alerts stored)
                # Query database to verify alerts were actually stored
                try:
                    verify_query = "SELECT COUNT(*) as alert_count FROM flow_alerts WHERE scan_timestamp = ?"
                    verify_result = storage.query_with_params(verify_query, (scan_timestamp,))
                    alerts_stored = verify_result[0]['alert_count'] if verify_result else 0

                    # Also check flow_options_scans for raw contracts
                    scans_query = "SELECT COUNT(*) as scan_count FROM flow_options_scans WHERE scan_timestamp = ?"
                    scans_result = storage.query_with_params(scans_query, (scan_timestamp,))
                    scans_stored = scans_result[0]['scan_count'] if scans_result else 0

                    # Silent failure: API calls succeeded but no data stored
                    if alerts_stored == 0 and scans_stored == 0 and len(symbols) > 0:
                        from tools.autofix import handle_error
                        handle_error(
                            error_type='fm_collection_zero_alerts',
                            context={
                                'symbols_attempted': len(symbols),
                                'scan_timestamp': scan_timestamp,
                                'cycle_number': cycle,
                                'alerts_stored': alerts_stored,
                                'scans_stored': scans_stored,
                                'collection_time_seconds': collection_elapsed,
                                'trade_date': now_eastern().strftime('%Y-%m-%d'),
                                'market_phase': 'market_hours',
                                'monitor_active': True,
                                'cycle_type': 'real_time_monitoring',
                                'location': 'orchestrator',
                                'main_py_pid': os.getppid()
                            },
                            severity='CRITICAL'
                        )
                        # Never reached - handle_error exits with sys.exit(1)
                except Exception as verify_error:
                    logging.error("Error verifying alert storage: {}".format(verify_error))
                    # Don't crash on verification error - continue monitoring

                # Analysis phase
                print("")  # Visual separation after collection heartbeat
                beautiful_log("Starting FM Analyzer", 'info')
                analysis_start = time.time()
                analyzer.analyze(scan_timestamp)
                analysis_elapsed = time.time() - analysis_start
                analysis_query_elapsed = getattr(analyzer, 'last_query_elapsed', 0.0)
                analysis_scoring_elapsed = getattr(analyzer, 'last_scoring_elapsed', 0.0)
                analysis_db_write_elapsed = getattr(analyzer, 'last_db_write_elapsed', 0.0)

                # Alert phase
                print("")
                beautiful_log("Starting FM Alerts", 'info')
                alert_start = time.time()
                alerts.process_alerts(scan_timestamp,
                                      scan_contracts=getattr(analyzer, 'last_scan_contracts', None))
                alert_elapsed = time.time() - alert_start

                # Count alerts actually generated this cycle (after process_alerts creates them)
                try:
                    alert_count_result = storage.query_with_params(
                        "SELECT COUNT(*) as cnt FROM flow_alerts WHERE scan_timestamp = ?",
                        (scan_timestamp,))
                    alerts_stored = alert_count_result[0]['cnt'] if alert_count_result else 0
                except Exception:
                    pass  # Keep whatever alerts_stored was before

                # Watchlist phase
                print("")
                beautiful_log("Starting FM Watchlist", 'info')
                watchlist_start = time.time()
                try:
                    # Build current prices dict from collected data (single batch query)
                    current_prices = {}
                    price_query = """
                        SELECT symbol, underlying_price FROM flow_options_scans
                        WHERE scan_timestamp = ?
                        GROUP BY symbol
                    """
                    price_results = storage.query_with_params(price_query, (scan_timestamp,))
                    for row in price_results:
                        current_prices[row['symbol']] = row['underlying_price']

                    # Update watchlist from new alerts
                    trade_date = now_eastern().strftime('%Y-%m-%d')
                    watchlist_result = fm_watchlist.update_daily_watchlist(trade_date, storage, scan_timestamp)

                    # News enrichment phase (only when new watchlist entries created)
                    created_symbols = watchlist_result.get('created_symbols', [])
                    cycle_news_stats = None
                    if created_symbols:
                        print("")
                        beautiful_log("Starting FM News Enrichment", 'info')
                        try:
                            from tools.news_sentiment import enrich_watchlist_batch
                            cycle_news_stats = enrich_watchlist_batch(created_symbols, storage)
                            if cycle_news_stats.get('enriched', 0) > 0 or cycle_news_stats.get('failed', 0) > 0:
                                beautiful_log("News enrichment complete: {} enriched, {} skipped, {} failed".format(
                                    cycle_news_stats.get('enriched', 0), cycle_news_stats.get('skipped', 0), cycle_news_stats.get('failed', 0)), 'success')

                                # Display per-symbol sentiment results
                                from tools.log_utils import log_to_file
                                for detail in cycle_news_stats.get('details', []):
                                    sym = detail['symbol']
                                    score = detail['score']
                                    label = detail['label']
                                    articles = detail['articles']
                                    if score is not None:
                                        # Color-code: positive=green, negative=red, neutral=yellow
                                        if score > 0.1:
                                            sentiment_indicator = "\033[92m{:+.2f}\033[0m".format(score)
                                        elif score < -0.1:
                                            sentiment_indicator = "\033[91m{:+.2f}\033[0m".format(score)
                                        else:
                                            sentiment_indicator = "\033[93m{:+.2f}\033[0m".format(score)
                                        line = "     {} │ {} │ {} ({} articles)".format(
                                            sym.ljust(6), sentiment_indicator, label, articles)
                                    else:
                                        line = "     {} │ No relevant articles".format(sym.ljust(6))
                                    print(line)
                                    log_to_file("     {} | score={} | {} | {} articles".format(
                                        sym, score, label, articles))

                            # Persist API usage counters to daily_state.json
                            fm_api_calls = cycle_news_stats.get('enriched', 0) + cycle_news_stats.get('failed', 0)
                            if fm_api_calls > 0:
                                try:
                                    from main_ui import _save_news_api_usage
                                    _save_news_api_usage(
                                        source='fm',
                                        api_calls=fm_api_calls,
                                        symbols_enriched=cycle_news_stats.get('enriched', 0),
                                        zero_article_calls=cycle_news_stats.get('failed', 0),
                                    )
                                except Exception as usage_err:
                                    logging.debug("Could not save news API usage: {}".format(usage_err))
                        except Exception as news_error:
                            logging.warning("News enrichment failed (non-critical): {}".format(news_error))
                            from tools.autofix import queue_error
                            queue_error(
                                error_type='news_enrichment_module_error',
                                context={
                                    'exception_type': type(news_error).__name__,
                                    'error_message': str(news_error),
                                    'symbols_attempted': created_symbols,
                                    'trade_date': trade_date,
                                },
                                severity='WARNING'
                            )

                    # Dip detection phase
                    print("")
                    beautiful_log("Starting FM Dip Detection", 'info')
                    fm_watchlist.update_prices_and_detect(storage, current_prices)

                except Exception as watchlist_error:
                    logging.error("Watchlist update error (non-critical): {}".format(watchlist_error))

                watchlist_elapsed = time.time() - watchlist_start

                # Earnings signal tracking (intraday signal change detection)
                earnings_signal_elapsed = 0
                if earnings_tracker and scan_timestamp and cycle >= 2 and (cycle - 2) % earnings_tracker.check_interval == 0:
                    print("")
                    beautiful_log("Checking Earnings Signals (every {} cycles)".format(
                        earnings_tracker.check_interval), 'info')
                    est_start = time.time()
                    try:
                        signal_stats = earnings_tracker.track_signals(scan_timestamp)
                        if signal_stats['upgrades'] > 0 or signal_stats['downgrades'] > 0:
                            beautiful_log("Earnings signals: {} checked, {} upgrades, {} downgrades".format(
                                signal_stats['symbols_checked'], signal_stats['upgrades'],
                                signal_stats['downgrades']), 'success')
                        else:
                            beautiful_log("Earnings signals: {} checked, no changes".format(
                                signal_stats['symbols_checked']), 'info')
                    except Exception as e:
                        logging.warning("Earnings signal tracking error (non-critical): {}".format(e))
                    earnings_signal_elapsed = time.time() - est_start

                # Quick-sync phase
                print("")
                beautiful_log("Starting Quick Sync", 'info')
                sync_success, sync_elapsed, sync_rows = run_quick_sync()

            else:
                logging.warning("⚠️ Collection failed - skipping analysis")

                # AUTOFIX INTEGRATION: Collection returned False/None
                from tools.autofix import handle_error
                handle_error(
                    error_type='fm_collection_failed',
                    context={
                        'symbols_attempted': len(symbols),
                        'scan_timestamp': 'N/A',
                        'cycle_number': cycle,
                        'collection_time_seconds': collection_elapsed,
                        'trade_date': now_eastern().strftime('%Y-%m-%d'),
                        'market_phase': 'market_hours',
                        'monitor_active': True,
                        'cycle_type': 'real_time_monitoring',
                        'location': 'orchestrator',
                        'main_py_pid': os.getppid()
                    },
                    severity='CRITICAL'
                )
                # Never reached - handle_error exits with sys.exit(1)

        except Exception as e:
            logging.error("❌ Market cycle error: {}".format(e))

            # AUTOFIX INTEGRATION: Unexpected collection error
            from tools.autofix import handle_error
            handle_error(
                error_type='fm_collection_unexpected_error',
                context={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': traceback.format_exc(),
                    'cycle_number': cycle,
                    'symbols_attempted': len(symbols),
                    'collection_elapsed': collection_elapsed if 'collection_elapsed' in locals() else 0,
                    'scan_timestamp': scan_timestamp if 'scan_timestamp' in locals() else 'N/A',
                    'trade_date': now_eastern().strftime('%Y-%m-%d'),
                    'market_phase': 'market_hours',
                    'monitor_active': True,
                    'cycle_type': 'real_time_monitoring',
                    'phase': 'market_hours_monitoring',
                    'main_py_pid': os.getppid()
                },
                severity='CRITICAL'
            )
            # Never reached - handle_error exits with sys.exit(1)

        elapsed = time.time() - cycle_start

        # Record cycle into session stats (replaces manual tracker accumulation)
        stats.record_cycle(
            cycle_num=cycle,
            collector=collector,
            timings={
                'collection': collection_elapsed,
                'storage': storage_elapsed,
                'analysis': analysis_elapsed,
                'analysis_query': analysis_query_elapsed,
                'analysis_scoring': analysis_scoring_elapsed,
                'analysis_db_write': analysis_db_write_elapsed,
                'alert': alert_elapsed,
                'watchlist': watchlist_elapsed,
                'sync': sync_elapsed,
                'sync_rows': sync_rows,
                'cycle': elapsed,
                'scan_ok': scan_timestamp is not None,
                'scan_timestamp': scan_timestamp or '',
                'contracts_collected': getattr(collector, 'last_contracts_collected', 0),
                'alerts_generated': alerts_stored,
                'symbols_attempted': len(symbols),
                'symbols_with_data': getattr(collector, 'last_symbols_with_data', 0),
            },
            news_stats=cycle_news_stats,
        )

        # Persist stats for restart resilience
        stats.save_to_daily_state()

        # Prepare performance data
        performance_data = {
            'collection_time': collection_elapsed,
            'storage_time': storage_elapsed,
            'analysis_time': analysis_elapsed,
            'alert_time': alert_elapsed,
            'cycle_time': elapsed
        }

        # Update health status with performance data
        cycle_success = scan_timestamp is not None
        if cycle_success:
            health_reporter.update_health_status("Market Cycle", "success", performance_data=performance_data)
        else:
            health_reporter.update_health_status("Market Cycle", "failed", error=True, performance_data=performance_data)

        # Show detailed performance metrics
        print("")
        beautiful_log("Cycle {} complete - Performance Breakdown:".format(cycle), 'success')
        if storage_elapsed > 0:
            logging.info("   📊 Collection: {:.1f}s (API: {:.1f}s + DB Write: {:.1f}s)".format(
                collection_elapsed, collection_elapsed - storage_elapsed, storage_elapsed))
        else:
            logging.info("   📊 Collection: {:.1f}s".format(collection_elapsed))
        if analysis_db_write_elapsed > 0:
            logging.info("   🔍 Analysis: {:.1f}s (Query: {:.1f}s + Scoring: {:.1f}s + DB Write: {:.1f}s)".format(
                analysis_elapsed, analysis_query_elapsed, analysis_scoring_elapsed, analysis_db_write_elapsed))
        else:
            logging.info("   🔍 Analysis: {:.1f}s".format(analysis_elapsed))
        logging.info("   🚨 Alerts: {:.1f}s".format(alert_elapsed))
        if watchlist_elapsed > 0:
            logging.info("   🎯 Watchlist: {:.1f}s".format(watchlist_elapsed))
        if earnings_signal_elapsed > 0:
            logging.info("   📈 Earnings Signals: {:.1f}s".format(earnings_signal_elapsed))
        if sync_elapsed > 0:
            logging.info("   🔄 DB Sync: {:.1f}s ({:,} rows)".format(sync_elapsed, sync_rows))
        logging.info("   ⏱️ Total: {:.1f}s".format(elapsed))

        # Live market snapshot
        display_market_snapshot(collector)

        # Flow activity dashboard (running daily alert summary)
        if scan_timestamp:
            try:
                from strategies.flow_monitor.fm_alert_summary import FMAlertSummary
                alert_summary = FMAlertSummary()
                alert_summary.display(storage, now_eastern().strftime('%Y-%m-%d'))
            except Exception as e:
                logging.debug("Alert summary display failed: {}".format(e))

        # Write diagnostic summary (if scan successful)
        if scan_timestamp:
            log_diagnostic_summary(
                diag_logger, storage, scan_timestamp, len(symbols),
                collection_elapsed, analysis_elapsed, alert_elapsed,
                sync_elapsed, sync_rows, storage_elapsed
            )

        # Show averages every 10 cycles (driven from stats data)
        if cycle >= 2 and len(stats.cycle_times) >= 2:
            print("")
            logging.info("📈 PERFORMANCE SUMMARY (Last {} cycles):".format(len(stats.cycle_times)))
            logging.info("   Average cycle time: {:.1f}s".format(sum(stats.cycle_times) / len(stats.cycle_times)))
            logging.info("   Average collection: {:.1f}s".format(sum(stats.collection_times) / len(stats.collection_times)))
            if stats.storage_times:
                logging.info("   Average DB write (collection): {:.1f}s".format(sum(stats.storage_times) / len(stats.storage_times)))
            logging.info("   Average analysis: {:.1f}s".format(sum(stats.analysis_times) / len(stats.analysis_times)))
            if stats.analysis_db_write_times:
                logging.info("     Avg query: {:.1f}s | scoring: {:.1f}s | DB write: {:.1f}s".format(
                    sum(stats.analysis_query_times) / len(stats.analysis_query_times),
                    sum(stats.analysis_scoring_times) / len(stats.analysis_scoring_times),
                    sum(stats.analysis_db_write_times) / len(stats.analysis_db_write_times)))
            logging.info("   Average alerts: {:.1f}s".format(sum(stats.alert_times) / len(stats.alert_times)))
            if any(t > 0 for t in stats.watchlist_times):
                logging.info("   Average watchlist: {:.1f}s".format(sum(stats.watchlist_times) / len(stats.watchlist_times)))
            if any(t > 0 for t in stats.sync_times):
                sync_avg = sum(stats.sync_times) / len(stats.sync_times)
                rows_avg = sum(stats.sync_rows) / len(stats.sync_rows)
                logging.info("   Average DB sync: {:.1f}s ({:,.0f} rows)".format(sync_avg, rows_avg))
            logging.info("   Slowest cycle: {:.1f}s".format(max(stats.cycle_times)))
            logging.info("   Fastest cycle: {:.1f}s".format(min(stats.cycle_times)))

        # 60-second interruptible sleep with context-aware message
        coffee_context = 'sync_complete' if sync_success else 'default'
        coffee_break(60, context=coffee_context)

        cycle += 1

    # Log diagnostic shutdown
    now = now_eastern()
    total_cycles = stats.total_cycles
    diag_logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Flow Monitor market hours complete | Total cycles: {total_cycles}")

    # End-of-day summary (driven by session stats)
    eod_lines = stats.format_end_of_day_lines()
    for line in eod_lines:
        if line and not line.startswith(" "):
            logging.info("📊 {}".format(line))
        else:
            logging.info(line)

    # Diagnostic log lines
    diag_missing = stats.get_diagnostic_missing_quotes_line()
    if diag_missing:
        diag_logger.info(diag_missing)
    diag_failed = stats.get_diagnostic_failed_options_line()
    if diag_failed:
        diag_logger.info(diag_failed)

    # Persist symbol gaps for end-of-day analysis
    gaps_data = stats.get_symbol_gaps_data()
    if gaps_data:
        try:
            tracker_file = Path(__file__).parent.parent.parent / "logs" / "symbol_gaps_{}.json".format(
                now.strftime('%Y-%m-%d'))
            with open(tracker_file, 'w') as f:
                json.dump(gaps_data, f, indent=2)
            logging.info("   Saved to {}".format(tracker_file.name))
        except Exception as e:
            logging.warning("Failed to save symbol gaps tracker: {}".format(e))

    return {
        'success': True,
        'total_cycles': total_cycles,
        'news_enrichment': stats.news_enrichment,
        'session_stats': stats.get_summary(),
    }

def run_post_market():
    """Execute post-market tasks (no timing logic - main.py handles orchestration)

    Returns dict with:
        success: bool - True if all tasks successful
        duration_seconds: float - total elapsed time
        tasks_successful: int - count of successful tasks
        tasks_total: int - total task count (5)
        errors: int - sum of errors across sub-tasks
        sub_tasks: dict - per-task result dicts:
            backfill: {success, duration_seconds, symbols_updated, symbols_total, partial, return_code}
            market_regime: {success, duration_seconds}
            symbol_rollup: {success, duration_seconds, symbols_processed, summaries_created, errors}
            evaluation: {success, duration_seconds, return_code}
            watchlist_cleanup: {success, duration_seconds, entries_archived, entries_deleted}
    """
    post_market_start = time.time()

    # Initialize components
    health_reporter = FMHealthReporter()
    diag_logger = setup_diagnostic_logging()  # Initialize diagnostic logging

    # Log diagnostic startup
    now = now_eastern()
    diag_logger.info(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Post-market analysis started")

    # Run tasks directly (no scheduler needed)
    tasks_successful = 0
    total_tasks = 5  # backfill, regime, rollup, evaluation, watchlist cleanup
    total_errors = 0

    # Collect sub-task results
    sub_tasks = {}

    create_status_box(
        "\U0001f306 POST-MARKET ANALYSIS",
        [
            "Task 1: Historical Backfill \u2014 Update price data for all symbols",
            "Task 2: Market Regime Summary \u2014 Classify today's market behavior",
            "Task 3: Symbol Rollup \u2014 Aggregate contract data to symbol level",
            "Task 4: Daily Evaluation \u2014 Score and evaluate today's scans",
            "Task 5: Watchlist Cleanup \u2014 Archive expired watchlist entries",
        ]
    )

    # Task 1: Historical backfill (moved from pre-market for fresh data)
    _step_header(1, 5, "Historical Backfill")
    backfill_result = run_historical_backfill(health_reporter)
    sub_tasks['backfill'] = backfill_result

    if backfill_result['success']:
        tasks_successful += 1
        diag_logger.info("[{}] Backfill: {:.1f}min | {} symbols | Status: Complete".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            backfill_result['duration_seconds'] / 60,
            backfill_result.get('symbols_updated') or 'N/A'))
    else:
        logging.warning("Historical backfill failed - market summary will use existing data")
        diag_logger.info("[{}] Backfill: {:.1f}min | Status: FAILED".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            backfill_result['duration_seconds'] / 60))
        total_errors += 1

    # Task 2: Market regime summary (now runs after backfill)
    _step_header(2, 5, "Market Regime Summary")
    regime_result = run_evening_market_regime_summary(health_reporter)
    sub_tasks['market_regime'] = regime_result

    if regime_result['success']:
        logging.debug("Market regime summary completed")
        tasks_successful += 1
        diag_logger.info("[{}] Market Regime: Complete ({:.1f}s)".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            regime_result['duration_seconds']))

        coffee_break(60, context='task_complete', next_task='Symbol Rollup')
    else:
        logging.warning("Market regime summary failed")
        diag_logger.info("[{}] Market Regime: FAILED ({:.1f}s)".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            regime_result['duration_seconds']))
        total_errors += 1

    # Task 3: Symbol rollup
    _step_header(3, 5, "Symbol Rollup")
    rollup_result = run_symbol_rollup_task(health_reporter)
    sub_tasks['symbol_rollup'] = rollup_result

    if rollup_result['success']:
        logging.debug("Symbol rollup completed")
        tasks_successful += 1
        diag_logger.info("[{}] Symbol Rollup: {} symbols processed | {} summaries created | {:.1f}s".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            rollup_result.get('symbols_processed', 0),
            rollup_result.get('summaries_created', 0),
            rollup_result['duration_seconds']))

        coffee_break(60, context='task_complete', next_task='Daily Evaluation')
    else:
        logging.warning("Symbol rollup failed")
        diag_logger.info("[{}] Symbol Rollup: FAILED ({:.1f}s)".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            rollup_result['duration_seconds']))
        total_errors += rollup_result.get('errors', 1)

    # Task 4: Daily evaluation
    _step_header(4, 5, "Daily Evaluation")
    eval_result = run_daily_evaluation_task(health_reporter)
    sub_tasks['evaluation'] = eval_result

    if eval_result['success']:
        logging.debug("Daily evaluation completed")
        tasks_successful += 1
        diag_logger.info("[{}] Daily Evaluation: Complete ({:.1f}s)".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            eval_result['duration_seconds']))
    else:
        logging.warning("Daily evaluation failed")
        diag_logger.info("[{}] Daily Evaluation: FAILED ({:.1f}s)".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            eval_result['duration_seconds']))
        total_errors += 1

    # Optional: Flow Tracker Agent Analysis (only if --run-agent flag is set)
    import __main__
    run_agent = False  # Default: DISABLED (enable with --run-agent flag)

    if hasattr(__main__, 'args'):
        args = __main__.args
        # Only run agent if explicitly requested with --run-agent flag
        run_agent = args.run_agent and not args.no_agent

    if run_agent:
        logging.info("Running Flow Tracker Agent analysis...")
        agent_start = time.time()

        try:
            from strategies.flow_monitor.fm_agent import run_agent_analysis

            today = now_eastern().strftime('%Y-%m-%d')
            agent_results = run_agent_analysis(trade_date=today)
            agent_elapsed = time.time() - agent_start

            logging.info(f"Agent analysis complete ({agent_elapsed:.1f}s)")
            logging.info(f"   Processed: {agent_results['alerts_processed']} alerts")
            logging.info(f"   Created: {agent_results['trackers_created']} trackers")
            logging.info(f"   Updated: {agent_results['trackers_updated']} trackers")
            logging.info(f"   Cost: ${agent_results['total_cost']:.4f}")

            diag_logger.info("[{}] Agent Analysis: {} alerts | {} created | {} updated | ${:.4f} | {:.1f}s".format(
                now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
                agent_results['alerts_processed'], agent_results['trackers_created'],
                agent_results['trackers_updated'], agent_results['total_cost'], agent_elapsed))

        except Exception as e:
            # Don't crash FM if agent fails - just log and continue
            logging.warning(f"Agent analysis failed: {e}")
            diag_logger.info("[{}] Agent Analysis: FAILED - {}".format(
                now_eastern().strftime('%Y-%m-%d %H:%M:%S'), str(e)))
            logging.error(f"Agent analysis error: {e}")

            # Queue error for autofix but don't exit
            from tools.autofix import queue_error
            queue_error(
                error_type='fm_agent_failed',
                context={
                    'task': 'flow_tracker_agent',
                    'error': str(e),
                    'trade_date': now_eastern().strftime('%Y-%m-%d'),
                    'phase': 'post_market'
                },
                severity='WARNING'  # Non-critical - FM still succeeded
            )
    else:
        diag_logger.info("[{}] Agent Analysis: SKIPPED (--no-agent flag)".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S')))

    # Task 5: Watchlist Cleanup (archive expired entries)
    _step_header(5, 5, "Watchlist Cleanup")
    cleanup_start = time.time()
    cleanup_result = {'success': False, 'duration_seconds': 0.0, 'entries_archived': 0, 'entries_deleted': 0}

    try:
        # Shared storage instance (avoid redundant init)
        try:
            pm_config = FMConfig()
            pm_storage = FlowMonitorStorage(pm_config)
        except Exception as e:
            logging.warning("Could not initialize storage for cleanup: {}".format(e))
            pm_storage = None

        cleanup_storage = pm_storage if pm_storage else FlowMonitorStorage(FMConfig())

        cleanup_stats = fm_watchlist.archive_expired_entries(cleanup_storage)
        cleanup_elapsed = time.time() - cleanup_start

        cleanup_result = {
            'success': True,
            'duration_seconds': cleanup_elapsed,
            'entries_archived': cleanup_stats.get('entries_archived', 0),
            'entries_deleted': cleanup_stats.get('entries_deleted', 0),
        }

        if cleanup_stats['entries_archived'] > 0:
            logging.debug("Watchlist cleanup complete: {} entries archived".format(
                cleanup_stats['entries_archived']))
            diag_logger.info("[{}] Watchlist Cleanup: {} entries archived | {:.1f}s".format(
                now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
                cleanup_stats['entries_archived'], cleanup_elapsed))
        else:
            logging.debug("Watchlist cleanup complete: no expired entries")
            diag_logger.info("[{}] Watchlist Cleanup: No expired entries | {:.1f}s".format(
                now_eastern().strftime('%Y-%m-%d %H:%M:%S'), cleanup_elapsed))

        # Structured completion line
        if cleanup_result['success']:
            archived = cleanup_result.get('entries_archived', 0)
            if archived > 0:
                beautiful_log("Cleanup: {} entries archived".format(archived), 'success')
            else:
                beautiful_log("Cleanup: no expired entries", 'info')

        # Backfill NULL news sentiment with remaining API budget
        # Runs after archive so we only spend calls on entries that will survive
        backfill_result = fm_watchlist.backfill_missing_news(cleanup_storage)
        cleanup_result['news_backfilled'] = backfill_result.get('backfilled', 0)
        cleanup_result['news_backfill_failed'] = backfill_result.get('failed', 0)

        if backfill_result.get('backfilled', 0) > 0:
            beautiful_log("News backfill: {} symbols enriched ({} budget remaining)".format(
                backfill_result['backfilled'], backfill_result['budget_remaining']), 'success')
        elif backfill_result.get('failed', 0) > 0:
            beautiful_log("News backfill: 0 enriched, {} failed ({} budget remaining)".format(
                backfill_result['failed'], backfill_result['budget_remaining']), 'warning')

        tasks_successful += 1

    except Exception as e:
        cleanup_result['duration_seconds'] = time.time() - cleanup_start
        logging.warning("Watchlist cleanup error (non-critical): {}".format(e))
        diag_logger.info("[{}] Watchlist Cleanup: ERROR - {}".format(
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'), str(e)))
        logging.error("Watchlist cleanup error: {}".format(e))
        total_errors += 1
        # Don't fail the pipeline for cleanup errors

    sub_tasks['watchlist_cleanup'] = cleanup_result

    # Log diagnostic completion
    post_market_duration = time.time() - post_market_start
    now = now_eastern()
    diag_logger.info("[{}] Post-market analysis complete | Tasks: {}/{} successful".format(
        now.strftime('%Y-%m-%d %H:%M:%S'), tasks_successful, total_tasks))

    # Build result dict
    result = {
        'success': tasks_successful == total_tasks,
        'duration_seconds': post_market_duration,
        'tasks_successful': tasks_successful,
        'tasks_total': total_tasks,
        'errors': total_errors,
        'sub_tasks': sub_tasks,
    }

    # Build completion summary box
    completion_lines = []

    # Backfill
    bf = sub_tasks.get('backfill', {})
    if bf.get('success'):
        completion_lines.append("Backfill: {}/{} symbols ({:.1f} min)".format(
            bf.get('symbols_updated', '?'), bf.get('symbols_total', '?'),
            bf.get('duration_seconds', 0) / 60))
    else:
        completion_lines.append("Backfill: FAILED")

    # Regime
    rg = sub_tasks.get('market_regime', {})
    if rg.get('success'):
        if rg.get('direction'):
            spy_pct = rg.get('spy_change_pct', 0) or 0
            spy_sign = '+' if spy_pct >= 0 else ''
            completion_lines.append("Regime: {} | {} | SPY {}{}% | VIX {}".format(
                rg.get('regime', '?'), rg.get('direction', '?'),
                spy_sign, "{:.2f}".format(spy_pct), rg.get('vix_close', '?')))
        else:
            completion_lines.append("Regime: complete ({:.1f}s)".format(rg.get('duration_seconds', 0)))
    else:
        completion_lines.append("Regime: FAILED")

    # Rollup
    rl = sub_tasks.get('symbol_rollup', {})
    if rl.get('success'):
        completion_lines.append("Rollup: {} summaries ({:.1f}s)".format(
            rl.get('summaries_created', 0), rl.get('duration_seconds', 0)))
    else:
        completion_lines.append("Rollup: FAILED ({} errors)".format(rl.get('errors', 0)))

    # Evaluation
    ev = sub_tasks.get('evaluation', {})
    if ev.get('success'):
        completion_lines.append("Evaluation: complete ({:.1f}s)".format(ev.get('duration_seconds', 0)))
    else:
        completion_lines.append("Evaluation: FAILED")

    # Cleanup
    cl = sub_tasks.get('watchlist_cleanup', {})
    if cl.get('success'):
        archived = cl.get('entries_archived', 0)
        backfilled = cl.get('news_backfilled', 0)
        parts = []
        if archived > 0:
            parts.append("{} archived".format(archived))
        if backfilled > 0:
            parts.append("{} news backfilled".format(backfilled))
        if parts:
            completion_lines.append("Cleanup: {} ({:.1f}s)".format(', '.join(parts), cl.get('duration_seconds', 0)))
        else:
            completion_lines.append("Cleanup: no expired entries")
    else:
        completion_lines.append("Cleanup: FAILED")

    # Footer
    completion_lines.append("")
    completion_lines.append("Total: {:.1f} min | Tasks: {}/{} successful".format(
        post_market_duration / 60, tasks_successful, total_tasks))

    create_status_box("\u2705 POST-MARKET ANALYSIS COMPLETE", completion_lines)

    return result

def main():
    """Main entry point for Flow Monitor CLI"""
    parser = argparse.ArgumentParser(description="Flow Monitor CLI")
    parser.add_argument('--pre-market', action='store_true', 
                       help='Run pre-market tasks (9:15 AM)')
    parser.add_argument('--market-hours', action='store_true',
                       help='Run market hours monitoring (9:30 AM - 4:00 PM)')
    parser.add_argument('--post-market', action='store_true',
                       help='Run post-market tasks (4:15 PM)')
    parser.add_argument('--test-mode', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--analyze-only', action='store_true')
    parser.add_argument('--scan-timestamp', help='Scan timestamp for analyze-only mode')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--no-interaction', action='store_true')
    parser.add_argument('--run-agent', action='store_true',
                       help='Run Flow Tracker Agent analysis after scans')
    parser.add_argument('--no-agent', action='store_true',
                       help='Skip agent analysis (for testing FM only)')
    parser.add_argument('--agent-only', action='store_true',
                       help='Skip scans, only run agent on existing alerts')

    args = parser.parse_args()
    setup_logging(debug=args.debug)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Store args in __main__ for access by run_post_market()
    import __main__
    __main__.args = args

    # Handle agent-only mode (check first, before other modes)
    if args.agent_only:
        logging.info("AGENT-ONLY MODE: Processing today's alerts")
        from strategies.flow_monitor.fm_agent import run_agent_analysis

        try:
            results = run_agent_analysis()

            # Print summary
            print("\n" + "="*70)
            print("AGENT ANALYSIS SUMMARY")
            print("="*70)
            print(f"Alerts processed: {results['alerts_processed']}")
            print(f"Trackers created: {results['trackers_created']}")
            print(f"Trackers updated: {results['trackers_updated']}")
            print(f"Errors: {results['errors']}")
            print(f"Cost: ${results['total_cost']:.4f}")
            if results.get('session_log_dir'):
                print(f"Session logs: {results['session_log_dir']}")
            print("="*70)

            return 0 if results['errors'] == 0 else 1

        except Exception as e:
            logging.error(f"❌ Agent analysis failed: {e}")
            traceback.print_exc()
            return 1

    # Handle entry points
    if args.pre_market:
        logging.info("PRE-MARKET EXECUTION MODE")
        success = run_pre_market()
        return 0 if success else 1
        
    elif args.market_hours:
        logging.info("MARKET HOURS EXECUTION MODE")
        success = run_market_hours()
        return 0 if success else 1
        
    elif args.post_market:
        logging.info("POST-MARKET EXECUTION MODE")
        result = run_post_market()
        success = result.get('success', False) if isinstance(result, dict) else bool(result)
        return 0 if success else 1
    
    # Handle existing test/analysis modes
    elif args.test_mode:
        # Initialize core components for test mode
        config = FMConfig()
        storage = FlowMonitorStorage(config)
        collector = FMCollector()
        analyzer = FMAnalyzer(storage)
        alerts = FMAlerts(config, storage)
        
        symbols = MAG7_SYMBOLS
        logging.info("TEST MODE: Using MAG7 symbols")
        run_pipeline(collector, analyzer, alerts, storage, symbols, force=True, test_mode=True)
    
    elif args.once:
        # Initialize core components for once mode
        config = FMConfig()
        storage = FlowMonitorStorage(config)
        collector = FMCollector()
        analyzer = FMAnalyzer(storage)
        alerts = FMAlerts(config, storage)
        
        symbols = get_symbols_klmn800()
        logging.info("ONE-TIME MODE: Using KLMN800 symbols")
        run_pipeline(collector, analyzer, alerts, storage, symbols)

    elif args.analyze_only:
        # Initialize core components for analysis mode
        config = FMConfig()
        storage = FlowMonitorStorage(config)
        analyzer = FMAnalyzer(storage)
        alerts = FMAlerts(config, storage)
        
        ts = args.scan_timestamp or storage.get_latest_scan_timestamp()
        if not ts:
            logging.error("No scan timestamp provided and none found in DB.")
            return
        logging.info("ANALYZE ONLY MODE: Timestamp {}".format(ts))
        analyzer.analyze(ts)
        alerts.process_alerts(ts,
                              scan_contracts=getattr(analyzer, 'last_scan_contracts', None))

    else:
        parser.print_help()
        return

    if not args.no_interaction:
        input("\nPress ENTER to exit...")

if __name__ == '__main__':
    main()