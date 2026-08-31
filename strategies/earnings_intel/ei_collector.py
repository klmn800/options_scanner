#!/usr/bin/env python3
"""
Earnings Collector (ei_earnings_collector.py)
---------------------------------------------
Standalone weekly earnings collector for KLMN 800 stocks.
Dual-source: yfinance for dates + estimates, Finnhub for BMO/AMC timing.

Three-step workflow:
  1. Archive past earnings -> earnings_events (preserving signal columns)
  2. Cleanup old records (7+ days past) from earnings_upcoming
  3. Fetch per-symbol from yfinance + Finnhub -> upsert into earnings_upcoming

Date update rule: yfinance is the trusted source. If yfinance provides a
valid future date that differs from the stored date, the stored date is
updated. Conflicts are logged. Finnhub dates are used only as fallback
for new symbols with no yfinance date. See docs/_local/earnings_strategy_refactor/EARNINGS_DATE_REWIRE_PLAN.md.

Called by: main_runners.py (Phase 5, Step 5.2 -- Friday evenings)
Reads: earnings_upcoming, config.json
Writes: earnings_upcoming, earnings_events, performance.db (earnings_date_sources)

Author: Ben (with Claude)
Date: 2026-02-27 (yfinance rewire: 2026-03-05)
"""

import os
import sys
import io
import json
import time
import logging
import sqlite3
import contextlib
import traceback
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from core.finnhub_api import FinnhubAPI
from core.symbols_klmn800 import get_specialty_list
from tools.timezone_utils import now_eastern, eastern_isoformat
from tools.log_utils import beautiful_log
from tools.decimal_formatter import clean_database_row
from tools.autofix import queue_error
from strategies.earnings_intel.ei_health_reporter import EIHealthReporter


# Diagnostic logging (file-only, no console spam)
def _setup_diagnostic_logger():
    """Create diagnostic logger for weekly-refresh summaries."""
    logs_dir = Path(project_root) / "logs" / "diagnostic"
    logs_dir.mkdir(parents=True, exist_ok=True)

    date_str = now_eastern().strftime('%Y-%m-%d')
    logfile = logs_dir / 'earnings_collector_{}.log'.format(date_str)

    logger = logging.getLogger('earnings_collector_diagnostic')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers = []

    handler = logging.FileHandler(logfile, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)

    return logger


# 8 signal columns preserved during archive
SIGNAL_COLUMNS = [
    'earnings_play_signal',
    'relative_underpricing_pct',
    'straddle_expected_move_pct',
    'historical_avg_move_pct',
    'historical_avg_move_alltime_pct',
    'historical_quarters_used',
    'eps_estimate',
    'revenue_estimate',
]

# ETFs to exclude (no earnings data) — DB-backed via is_etf=1 (includes JETS)
ETF_EXCLUSIONS = set(get_specialty_list('etf'))


class EarningsCollector:
    """Standalone weekly earnings collector -- dual-source fetch + archive + cleanup.

    Fetches earnings data from yfinance (dates + estimates) and Finnhub (timing)
    for every KLMN 800 stock symbol (excluding ETFs) and upserts into
    earnings_upcoming. Existing dates are never auto-overwritten; conflicts
    are logged for manual review.

    Usage:
        collector = EarningsCollector()
        result = collector.collect_weekly_earnings()
    """

    def __init__(self, db_path=None, config_path=None):
        """Initialize earnings collector.

        Args:
            db_path: Path to datalake.db (default: data/datalake.db)
            config_path: Path to config.json (default: config.json)
        """
        if db_path is None:
            db_path = os.path.join(project_root, 'data', 'datalake.db')
        if config_path is None:
            config_path = os.path.join(project_root, 'config.json')

        self.db_path = db_path

        # Load Finnhub config
        with open(config_path, 'r') as f:
            config = json.load(f)

        finnhub_config = config.get('finnhub', {})
        api_key = finnhub_config.get('api_key', '')
        if not api_key:
            raise ValueError("No Finnhub API key found in config.json")

        self.api = FinnhubAPI(
            api_key=api_key,
            base_url=finnhub_config.get('base_url', 'https://finnhub.io/api/v1'),
            rate_limit_per_minute=finnhub_config.get('rate_limit_per_minute', 60),
        )

        # KLMN stocks only (exclude ETFs)
        all_symbols = set(get_specialty_list('klmn_800'))
        self.stock_symbols = sorted(all_symbols - ETF_EXCLUSIONS)

        # Health reporter + diagnostic logger
        self.health_reporter = EIHealthReporter('weekly-refresh')
        self.diag = _setup_diagnostic_logger()

    def _get_connection(self):
        """Create a database connection with appropriate settings."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def collect_weekly_earnings(self):
        """Execute the three-step collection workflow.

        Returns:
            dict: Structured result matching performance_writer contract.
        """
        start = time.time()
        now = now_eastern().strftime('%Y-%m-%d %H:%M:%S')
        self.diag.info("[{}] Weekly Earnings Collection Started".format(now))
        self.diag.info("  Symbols: {} stocks (excluding {} ETFs)".format(
            len(self.stock_symbols), len(ETF_EXCLUSIONS)))

        errors = 0

        # Step 1: Archive past earnings
        beautiful_log("  [1/3] Archiving past earnings...", level='info')
        archive_result = self._archive_past_earnings()
        if not archive_result['success']:
            errors += 1
        beautiful_log("  Archived {} past events to earnings_events".format(
            archive_result['rows']), level='info')

        # Step 2: Cleanup old records
        beautiful_log("  [2/3] Cleaning up old records...", level='info')
        cleanup_result = self._cleanup_old_records()
        if not cleanup_result['success']:
            errors += 1
        beautiful_log("  Cleaned up {} records (7+ days past)".format(
            cleanup_result['rows']), level='info')

        # Step 3: Fetch from yfinance + Finnhub
        beautiful_log("  [3/3] Fetching earnings (yfinance + Finnhub, {} stocks)...".format(
            len(self.stock_symbols)), level='info')
        fetch_result = self._fetch_and_upsert_earnings()
        if not fetch_result['success']:
            errors += 1

        # Timing breakdown
        tb = fetch_result['timing_breakdown']
        beautiful_log("  Timing coverage: {} bmo, {} amc, {} dmh, {} unknown".format(
            tb['bmo'], tb['amc'], tb['dmh'], tb['unknown']), level='info')

        # Date source summary
        dsc = fetch_result.get('date_source_counts', {})
        beautiful_log("  Date sources: {} new (yfinance) | {} new (finnhub fallback) | {} updated (yfinance) | {} preserved | {} conflicts".format(
            dsc.get('yfinance_new', 0), dsc.get('finnhub_fallback', 0),
            dsc.get('yfinance_updated', 0), dsc.get('preserved', 0), dsc.get('conflicts', 0)), level='info')

        # Query final state
        upcoming_count = self._query_upcoming_count()

        total_time = time.time() - start
        all_success = (errors == 0)

        # Health report
        self.health_reporter.generate_health_report(all_success)

        # Diagnostic summary
        now = now_eastern().strftime('%Y-%m-%d %H:%M:%S')
        self.diag.info("[{}] Archive: {} events archived | {:.1f}s".format(
            now, archive_result['rows'], archive_result['duration_seconds']))
        self.diag.info("[{}] Cleanup: {} records deleted | {:.1f}s".format(
            now, cleanup_result['rows'], cleanup_result['duration_seconds']))
        self.diag.info("[{}] Fetch: {} found | {} no data | {} errors | {} API calls | {:.1f}s".format(
            now, fetch_result['earnings_found'], fetch_result['no_data_count'],
            fetch_result['errors'], fetch_result['api_calls'],
            fetch_result['duration_seconds']))
        self.diag.info("[{}] Timing: {} bmo | {} amc | {} dmh | {} unknown".format(
            now, tb['bmo'], tb['amc'], tb['dmh'], tb['unknown']))
        self.diag.info("[{}] Date sources: {} yf_new | {} fh_fallback | {} yf_updated | {} preserved | {} conflicts".format(
            now, dsc.get('yfinance_new', 0), dsc.get('finnhub_fallback', 0),
            dsc.get('yfinance_updated', 0), dsc.get('preserved', 0), dsc.get('conflicts', 0)))
        no_data_syms = fetch_result.get('no_data_symbols', [])
        if no_data_syms:
            self.diag.info("[{}] No-data symbols ({}): {}".format(
                now, len(no_data_syms), json.dumps(no_data_syms)))
        self.diag.info("[{}] Complete | Total: {:.1f}s | Upcoming: {} | Success: {}".format(
            now, total_time, upcoming_count, all_success))

        return {
            'success': all_success,
            'duration_seconds': total_time,
            'errors': errors + fetch_result.get('errors', 0),
            'earnings_found': fetch_result['earnings_found'],
            'events_archived': archive_result['rows'],
            'records_cleaned': cleanup_result['rows'],
            'upcoming_count': upcoming_count,
            'no_data_count': fetch_result['no_data_count'],
            'timing_breakdown': tb,
            'date_source_counts': dsc,
            'sub_tasks': {
                'archive': {
                    'success': archive_result['success'],
                    'duration_seconds': archive_result['duration_seconds'],
                    'events_archived': archive_result['rows'],
                },
                'cleanup': {
                    'success': cleanup_result['success'],
                    'duration_seconds': cleanup_result['duration_seconds'],
                    'records_deleted': cleanup_result['rows'],
                },
                'fetch': {
                    'success': fetch_result['success'],
                    'duration_seconds': fetch_result['duration_seconds'],
                    'earnings_found': fetch_result['earnings_found'],
                    'no_data_count': fetch_result['no_data_count'],
                    'api_calls': fetch_result['api_calls'],
                    'errors': fetch_result['errors'],
                },
            },
        }

    # --- Step 1: Archive -------------------------------------------------

    def _archive_past_earnings(self):
        """Move past-date earnings_upcoming rows to earnings_events.

        Preserves 7 signal/analysis columns. Uses INSERT OR IGNORE to
        avoid duplicates (earnings_events has unique index on symbol+date).
        """
        start = time.time()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Ensure earnings_events has signal columns (idempotent migration)
            self._migrate_earnings_events_columns(cursor)

            cursor.execute("""
                INSERT OR IGNORE INTO earnings_events
                    (symbol, earnings_date, fiscal_year, fiscal_quarter,
                     estimated_eps, actual_eps, earnings_time, source, is_backfilled,
                     earnings_play_signal, relative_underpricing_pct,
                     straddle_expected_move_pct,
                     historical_avg_move_pct, historical_avg_move_alltime_pct,
                     historical_quarters_used, eps_estimate, revenue_estimate)
                SELECT
                    symbol, earnings_date, NULL, NULL,
                    NULL, NULL, earnings_time, 'earnings_upcoming', 0,
                    earnings_play_signal, relative_underpricing_pct,
                    straddle_expected_move_pct,
                    historical_avg_move_pct, historical_avg_move_alltime_pct,
                    historical_quarters_used, eps_estimate, revenue_estimate
                FROM earnings_upcoming
                WHERE earnings_date < DATE('now')
                AND earnings_date IS NOT NULL
            """)
            archived = cursor.rowcount
            conn.commit()
            conn.close()

            self.health_reporter.track_task_result(
                'Archive Past Events', True,
                events_archived=archived,
                duration=time.time() - start)

            return {'success': True, 'duration_seconds': time.time() - start, 'rows': archived}

        except Exception as e:
            logging.error("Archive failed: {}".format(e))
            self.health_reporter.track_task_result('Archive Past Events', False, error=str(e))
            queue_error(
                error_type='earnings_collector_archive_failed',
                context={'error': str(e), 'step': 'archive', 'db_path': self.db_path},
                severity='ERROR')
            return {'success': False, 'duration_seconds': time.time() - start, 'rows': 0}

    def _migrate_earnings_events_columns(self, cursor):
        """Add signal columns to earnings_events if missing (idempotent)."""
        existing = {row[1] for row in cursor.execute("PRAGMA table_info(earnings_events)")}
        for col in SIGNAL_COLUMNS:
            if col not in existing:
                if col == 'earnings_play_signal':
                    col_type = 'TEXT'
                elif col == 'historical_quarters_used':
                    col_type = 'INTEGER'
                else:
                    col_type = 'REAL'
                cursor.execute("ALTER TABLE earnings_events ADD COLUMN {} {}".format(col, col_type))
                logging.debug("Added column {} to earnings_events".format(col))

    # --- Step 2: Cleanup -------------------------------------------------

    def _cleanup_old_records(self):
        """Delete earnings_upcoming records 7+ days past their earnings_date."""
        start = time.time()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM earnings_upcoming
                WHERE earnings_date < DATE('now', '-7 days')
                AND earnings_date IS NOT NULL
            """)
            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            self.health_reporter.track_task_result(
                'Cleanup Old Records', True,
                records_deleted=deleted,
                duration=time.time() - start)

            return {'success': True, 'duration_seconds': time.time() - start, 'rows': deleted}

        except Exception as e:
            logging.error("Cleanup failed: {}".format(e))
            self.health_reporter.track_task_result('Cleanup Old Records', False, error=str(e))
            queue_error(
                error_type='earnings_collector_cleanup_failed',
                context={'error': str(e), 'step': 'cleanup', 'db_path': self.db_path},
                severity='ERROR')
            return {'success': False, 'duration_seconds': time.time() - start, 'rows': 0}

    # --- Step 3: Fetch + Upsert (dual-source) ----------------------------

    def _yf_fetch_inner(self, symbol):
        """Inner yfinance call — runs inside ThreadPoolExecutor for timeout.

        Suppresses yfinance's internal stderr/stdout noise.
        Returns the calendar dict or None.
        """
        with contextlib.redirect_stderr(io.StringIO()), \
             contextlib.redirect_stdout(io.StringIO()):
            ticker = yf.Ticker(symbol)
            return ticker.calendar

    def _fetch_yfinance_data(self, symbol):
        """Fetch earnings date and estimates from yfinance for a single symbol.

        Uses ThreadPoolExecutor with 5s timeout to prevent hangs on bad symbols.
        yfinance 0.2.64 uses curl_cffi internally, so we can't control the HTTP
        timeout via session — the thread pool provides the ceiling instead.

        Args:
            symbol: Stock ticker symbol

        Returns:
            dict: {date: str|None, eps_estimate: float|None, revenue_estimate: float|None}
                  date is None if yfinance has no data or returns a stale past-quarter date.
        """
        result = {'date': None, 'eps_estimate': None, 'revenue_estimate': None}

        try:
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(self._yf_fetch_inner, symbol)
            try:
                calendar = future.result(timeout=5)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            if not calendar or 'Earnings Date' not in calendar:
                return result

            earnings_dates = calendar['Earnings Date']
            if not earnings_dates or len(earnings_dates) == 0:
                return result

            next_date = earnings_dates[0]
            if hasattr(next_date, 'strftime'):
                date_str = next_date.strftime('%Y-%m-%d')
            else:
                date_str = str(next_date)

            # Stale detection: if date is in the past, treat as no data
            # (yfinance returns last quarter's date for symbols 60+ days out)
            try:
                if date.fromisoformat(date_str) < date.today():
                    return result
            except (ValueError, TypeError):
                return result

            result['date'] = date_str

            # EPS and revenue estimates
            eps_avg = calendar.get('Earnings Average')
            rev_avg = calendar.get('Revenue Average')
            if eps_avg is not None:
                result['eps_estimate'] = float(eps_avg)
            if rev_avg is not None:
                result['revenue_estimate'] = float(rev_avg)

        except TimeoutError:
            logging.debug("yfinance timeout (5s) for {}".format(symbol))
        except Exception as e:
            logging.debug("yfinance fetch failed for {}: {}".format(symbol, e))

        return result

    def _fetch_and_upsert_earnings(self):
        """Fetch earnings per-symbol from yfinance + Finnhub, upsert into earnings_upcoming.

        Dual-source strategy:
        - yfinance: dates (primary) + EPS/revenue estimates
        - Finnhub: BMO/AMC timing + fallback dates/estimates for new symbols

        Date update rule: yfinance is the trusted source. If yfinance provides
        a valid future date, it replaces the stored date. Conflicts are logged.
        """
        start = time.time()
        today = date.today()
        today_str = today.isoformat()
        end_date = today + timedelta(days=90)

        # Pre-fetch existing dates from earnings_upcoming
        existing_dates = {}
        try:
            conn = self._get_connection()
            for row in conn.execute("SELECT symbol, earnings_date FROM earnings_upcoming"):
                existing_dates[row[0]] = row[1]
            conn.close()
        except Exception as e:
            logging.warning("Could not pre-fetch existing dates: {}".format(e))

        records = []          # (symbol, earnings_date, days_ahead, timing, eps_est, rev_est, updated_at)
        perf_records = []     # For earnings_date_sources performance table
        no_data_symbols = []  # Symbols with no data from either source
        error_log = []        # Sample errors for autofix context
        timing_counts = {'bmo': 0, 'amc': 0, 'dmh': 0, 'unknown': 0}

        # Date source counters
        source_counts = {
            'yfinance_new': 0,     # New symbols with yfinance date
            'finnhub_fallback': 0, # New symbols with Finnhub fallback date
            'preserved': 0,        # Existing symbols with stored date unchanged
            'yfinance_updated': 0, # Existing symbols updated to yfinance date
            'conflicts': 0,        # Existing symbols where sources disagree (logged only)
        }

        # Passive drift detections on date_confirmed=1 rows (Proposal 021).
        # Each entry: {'symbol', 'stored_date', 'yfinance_date'}. Logged to
        # earnings_date_disputes at end of method; never writes earnings_upcoming.
        confirmed_disputes = []

        # Load confirmed symbols — skip these entirely (date locked by human or agent)
        confirmed_symbols = set()
        try:
            conn = self._get_connection()
            for row in conn.execute("SELECT symbol FROM earnings_upcoming WHERE date_confirmed = 1"):
                confirmed_symbols.add(row[0])
            conn.close()
        except Exception:
            pass

        total = len(self.stock_symbols)
        found_count = 0
        no_data_count = 0
        api_calls = 0
        fetch_errors = 0
        now_ts = eastern_isoformat()

        for i, symbol in enumerate(self.stock_symbols, 1):
            if symbol in confirmed_symbols:
                source_counts['confirmed_skip'] = source_counts.get('confirmed_skip', 0) + 1

                # Passive drift detection (Proposal 021). Fetch yfinance only;
                # never write earnings_upcoming. If yfinance returns a future-
                # relevant date that disagrees with the stored confirmed date,
                # log for human review via earnings_date_disputes.
                try:
                    yf_probe = self._fetch_yfinance_data(symbol)
                    yf_probe_date = yf_probe.get('date') if yf_probe else None
                    stored_date = existing_dates.get(symbol)

                    if yf_probe_date and stored_date and yf_probe_date != stored_date:
                        try:
                            is_future = date.fromisoformat(stored_date) >= today
                        except (ValueError, TypeError):
                            is_future = False

                        if is_future:
                            confirmed_disputes.append({
                                'symbol': symbol,
                                'stored_date': stored_date,
                                'yfinance_date': yf_probe_date,
                            })
                            beautiful_log(
                                "  CONFIRMED-ROW DIVERGENCE: {} stored={} (confirmed), yfinance={}".format(
                                    symbol, stored_date, yf_probe_date),
                                level='warning')
                except Exception as e:
                    logging.debug("Confirmed-row drift check failed for {}: {}".format(symbol, e))

                continue
            yf_data = {'date': None, 'eps_estimate': None, 'revenue_estimate': None}
            fh_date = None
            fh_timing = 'Unknown'
            fh_eps = None
            fh_rev = None

            # --- yfinance fetch (first — fills Finnhub rate limiter gap) ---
            try:
                yf_data = self._fetch_yfinance_data(symbol)
            except Exception as e:
                logging.debug("yfinance outer error for {}: {}".format(symbol, e))

            # --- Finnhub fetch (timing + fallback date/estimates) ---
            try:
                releases = self.api.get_earnings_calendar(today, end_date, symbol=symbol)
                api_calls += 1

                if releases:
                    r = releases[0]
                    fh_date = r.get('date')
                    fh_timing = r.get('hour', 'Unknown')
                    fh_eps = r.get('epsEstimate')
                    fh_rev = r.get('revenueEstimate')
            except Exception as e:
                fetch_errors += 1
                if len(error_log) < 10:
                    error_log.append({'symbol': symbol, 'error': str(e)})
                logging.warning("Finnhub fetch failed for {}: {}".format(symbol, e))
                self.health_reporter.track_error()

            # --- Determine record values ---
            yf_date = yf_data['date']
            has_any_date = yf_date or fh_date

            if not has_any_date:
                # No data from either source
                no_data_symbols.append(symbol)
                no_data_count += 1

                # Still record perf data for no-data symbols
                perf_records.append((
                    today_str, symbol,
                    existing_dates.get(symbol),  # stored_date (may be None)
                    None, None, None,            # yf_date, fh_date, fh_timing
                    'no_data', 0
                ))

                # Progress line
                if i % 50 == 0 or i == total:
                    beautiful_log("  {}/{} symbols ({} found, {} no data)".format(
                        i, total, found_count, no_data_count), level='info')
                continue

            # Prefer yfinance estimates, fall back to Finnhub
            eps_est = yf_data['eps_estimate'] if yf_data['eps_estimate'] is not None else fh_eps
            rev_est = yf_data['revenue_estimate'] if yf_data['revenue_estimate'] is not None else fh_rev

            if symbol in existing_dates:
                # EXISTING symbol: yfinance wins if it has a valid future date
                stored_date = existing_dates[symbol]
                conflict = False

                if yf_date and yf_date != stored_date:
                    # yfinance has a different (future) date — update
                    record_date = yf_date
                    date_source = 'yfinance_updated'
                    source_counts['yfinance_updated'] += 1
                    conflict = True
                    beautiful_log("  DATE UPDATED: {} -- stored={} -> yfinance={}{}".format(
                        symbol, stored_date, yf_date,
                        " (finnhub={})".format(fh_date) if fh_date and fh_date != yf_date else ''),
                        level='info')
                else:
                    # No yfinance date, or yfinance agrees with stored — preserve
                    record_date = stored_date
                    date_source = 'preserved'
                    source_counts['preserved'] += 1

                    # Log if Finnhub alone disagrees (informational only, no action)
                    if fh_date and fh_date != stored_date:
                        conflict = True
                        source_counts['conflicts'] += 1
                        beautiful_log("  DATE NOTE: {} -- stored={}, finnhub={} (no yfinance to confirm, keeping stored)".format(
                            symbol, stored_date, fh_date),
                            level='debug')

                # Perf record
                perf_records.append((
                    today_str, symbol, stored_date,
                    yf_date, fh_date, fh_timing,
                    date_source, 1 if conflict else 0
                ))

            else:
                # NEW symbol: pick best available date
                if yf_date:
                    record_date = yf_date
                    date_source = 'yfinance'
                    source_counts['yfinance_new'] += 1
                else:
                    record_date = fh_date
                    date_source = 'finnhub'
                    source_counts['finnhub_fallback'] += 1

                # Perf record
                perf_records.append((
                    today_str, symbol, None,
                    yf_date, fh_date, fh_timing,
                    date_source, 0
                ))

            # Calculate days_ahead from the record_date (stored for existing, chosen for new)
            days_ahead = None
            if record_date:
                try:
                    days_ahead = (date.fromisoformat(record_date) - today).days
                except (ValueError, TypeError):
                    pass

            # Track timing
            timing_key = fh_timing.lower() if fh_timing.lower() in timing_counts else 'unknown'
            timing_counts[timing_key] += 1

            # Clean decimal values
            cleaned = clean_database_row({
                'eps_estimate': eps_est,
                'revenue_estimate': rev_est,
            })

            records.append((
                symbol, record_date, days_ahead, fh_timing,
                cleaned.get('eps_estimate'), cleaned.get('revenue_estimate'), now_ts
            ))
            found_count += 1

            # Progress line every 50 symbols
            if i % 50 == 0 or i == total:
                beautiful_log("  {}/{} symbols ({} found, {} no data)".format(
                    i, total, found_count, no_data_count), level='info')

        # Batch upsert records (date preserved for existing via ON CONFLICT)
        upsert_errors = self._batch_upsert(records)
        if upsert_errors:
            fetch_errors += 1

        # Write date source comparison records to performance.db
        self._write_date_source_records(perf_records)

        # Proposal 021: write any passive drift detections on confirmed rows
        self._write_confirmed_disputes(confirmed_disputes, today_str)

        # Queue autofix if high failure rate (fetch errors only, not no-data)
        if fetch_errors > (total * 0.1):
            queue_error(
                error_type='earnings_collector_high_failure_rate',
                context={
                    'total_symbols': total,
                    'fetch_errors': fetch_errors,
                    'no_data_count': no_data_count,
                    'failure_rate_pct': round((fetch_errors / total) * 100, 1),
                    'sample_errors': error_log[:5],
                },
                severity='WARNING')

        self.health_reporter.track_task_result(
            'Fetch and Upsert', fetch_errors == 0,
            earnings_found=found_count,
            no_data=no_data_count,
            api_calls=api_calls,
            errors=fetch_errors,
            duration=time.time() - start)

        overall_success = not upsert_errors and fetch_errors < (total * 0.1)

        return {
            'success': overall_success,
            'duration_seconds': time.time() - start,
            'earnings_found': found_count,
            'no_data_count': no_data_count,
            'no_data_symbols': no_data_symbols,
            'errors': fetch_errors,
            'api_calls': api_calls,
            'timing_breakdown': timing_counts,
            'date_source_counts': source_counts,
        }

    def _batch_upsert(self, records):
        """Batch upsert earnings records in a single transaction.

        No-data symbols are intentionally skipped -- their stale updated_at
        makes coverage gaps obvious.

        ON CONFLICT: earnings_date IS updated (yfinance-sourced dates flow
        through for existing symbols). The date selection logic in
        _fetch_and_upsert_dates() already decides the correct record_date
        before building the record tuple.

        Args:
            records: List of tuples (symbol, date, days_ahead, timing, eps, rev, updated_at)

        Returns:
            bool: True if errors occurred, False if clean
        """
        if not records:
            return False

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.executemany("""
                INSERT INTO earnings_upcoming
                    (symbol, earnings_date, earnings_days_ahead, earnings_time,
                     eps_estimate, revenue_estimate, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    earnings_date = excluded.earnings_date,
                    earnings_days_ahead = excluded.earnings_days_ahead,
                    earnings_time = COALESCE(
                        NULLIF(excluded.earnings_time, 'Unknown'),
                        earnings_upcoming.earnings_time
                    ),
                    eps_estimate = COALESCE(excluded.eps_estimate, earnings_upcoming.eps_estimate),
                    revenue_estimate = COALESCE(excluded.revenue_estimate, earnings_upcoming.revenue_estimate),
                    updated_at = excluded.updated_at
            """, records)

            conn.commit()
            conn.close()
            return False  # No errors

        except Exception as e:
            logging.error("Batch upsert failed: {}".format(e))
            queue_error(
                error_type='earnings_collector_upsert_failed',
                context={
                    'error': str(e),
                    'records_count': len(records),
                    'db_path': self.db_path,
                },
                severity='ERROR')
            return True  # Errors occurred

    def _write_date_source_records(self, perf_records):
        """Write date source comparison records to performance.db.

        Args:
            perf_records: List of tuples (trade_date, symbol, stored_date,
                          yfinance_date, finnhub_date, finnhub_timing,
                          date_source, conflict)
        """
        if not perf_records:
            return

        try:
            perf_db_path = os.path.join(project_root, 'data', 'performance.db')
            from tools.performance_writer import ensure_schema
            ensure_schema(perf_db_path)

            conn = sqlite3.connect(perf_db_path, timeout=10)
            conn.executemany("""
                INSERT OR REPLACE INTO earnings_date_sources
                    (trade_date, symbol, stored_date, yfinance_date, finnhub_date,
                     finnhub_timing, date_source, conflict)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, perf_records)
            conn.commit()
            conn.close()

            logging.debug("Wrote {} date source records to performance.db".format(len(perf_records)))

        except Exception as e:
            logging.warning("Could not write date source records to performance.db: {}".format(e))

    def _write_confirmed_disputes(self, disputes, trade_date):
        """Write confirmed-row drift detections to performance.db.earnings_date_disputes.

        Proposal 021: when a date_confirmed=1 row's stored date diverges from
        yfinance's current value, log to the existing disputes table with
        dispute_reason='confirmed_row_diverged'. Detection only — no auto-correct.

        Args:
            disputes: List of dicts with keys symbol, stored_date, yfinance_date
            trade_date: Today's date string (PK component)
        """
        if not disputes:
            return

        try:
            perf_db_path = os.path.join(project_root, 'data', 'performance.db')
            # Ensure the table exists (canonical schema lives in
            # performance_writer.ensure_schema; this self-heals on a rebuilt DB
            # before Phase 6 runs).
            from tools.performance_writer import ensure_schema
            ensure_schema(perf_db_path)
            conn = sqlite3.connect(perf_db_path, timeout=30)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            for d in disputes:
                conn.execute("""
                    INSERT OR REPLACE INTO earnings_date_disputes
                        (trade_date, symbol, db_date, db_time, yfinance_date, finnhub_date,
                         dispute_reason, resolution)
                    VALUES (?, ?, ?, NULL, ?, NULL, 'confirmed_row_diverged', 'unresolved')
                """, (trade_date, d['symbol'], d['stored_date'], d['yfinance_date']))
            conn.commit()
            conn.close()
            beautiful_log("  Logged {} confirmed-row divergences to earnings_date_disputes".format(
                len(disputes)), level='info')
        except Exception as e:
            logging.warning("Failed to write confirmed-row disputes: {}".format(e))

    # --- Helpers ---------------------------------------------------------

    def _query_upcoming_count(self):
        """Count earnings_upcoming rows with future earnings dates."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM earnings_upcoming
                WHERE earnings_date >= DATE('now')
            """)
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logging.warning("Could not query upcoming count: {}".format(e))
            return 0


if __name__ == '__main__':
    """Standalone execution for testing."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("Earnings Collector -- Standalone Test Run")
    print("=" * 60)

    try:
        collector = EarningsCollector()
        print("Initialized: {} stock symbols".format(len(collector.stock_symbols)))
        result = collector.collect_weekly_earnings()
        print("\n" + "=" * 60)
        print("Result: {}".format('SUCCESS' if result['success'] else 'FAILED'))
        print("  Earnings found: {}".format(result['earnings_found']))
        print("  No data: {}".format(result['no_data_count']))
        print("  Archived: {}".format(result['events_archived']))
        print("  Cleaned: {}".format(result['records_cleaned']))
        print("  Upcoming: {}".format(result['upcoming_count']))
        print("  Duration: {:.1f}s".format(result['duration_seconds']))
        tb = result['timing_breakdown']
        print("  Timing: {} bmo | {} amc | {} dmh | {} unknown".format(
            tb['bmo'], tb['amc'], tb['dmh'], tb['unknown']))
        dsc = result.get('date_source_counts', {})
        print("  Sources: {} yf_new | {} fh_fallback | {} yf_updated | {} preserved | {} conflicts | {} confirmed_skip".format(
            dsc.get('yfinance_new', 0), dsc.get('finnhub_fallback', 0),
            dsc.get('yfinance_updated', 0), dsc.get('preserved', 0), dsc.get('conflicts', 0),
            dsc.get('confirmed_skip', 0)))
    except Exception as e:
        print("FATAL: {}".format(e))
        traceback.print_exc()
