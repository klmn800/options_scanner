#!/usr/bin/env python3
"""
Lite Daily Earnings Refresh (ei_lite_refresh.py)
-------------------------------------------------
Lightweight daily refresh of near-term earnings dates. Runs as sub-step 1/8
in the EI daily pipeline, before snapshots.

Scope: unconfirmed symbols within 21 days of today (~30-80 symbols during
peak earnings season vs 820 for full Friday refresh).

For each symbol:
  1. Fetch yfinance date + Finnhub date/timing
  2. Update stored date if yfinance changed and not confirmed
  3. Flag disputes: Unknown time, source disagreement, large date shift

If disputes are found, spawns the earnings researcher agent in a visible
window (fire-and-forget).

Author: Ben (with Claude Code)
Created: 2026-04-23
"""

import os
import sys
import io
import time
import sqlite3
import logging
import subprocess
import contextlib
import tempfile
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

# Add project root for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

import yfinance as yf
from core.finnhub_api import FinnhubAPI
from tools.timezone_utils import now_eastern, eastern_date_string, eastern_isoformat
from tools.log_utils import beautiful_log


# ---------------------------------------------------------------------------
# Schema migration (Phase 1A — idempotent)
# ---------------------------------------------------------------------------

def _ensure_confirmation_schema(db_path):
    """Add date_confirmed columns to earnings_upcoming if missing."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    for col_sql in [
        'ALTER TABLE earnings_upcoming ADD COLUMN date_confirmed INTEGER DEFAULT 0',
        'ALTER TABLE earnings_upcoming ADD COLUMN date_confirmed_by TEXT',
        'ALTER TABLE earnings_upcoming ADD COLUMN date_confirmed_at TEXT',
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError as e:
            if 'duplicate column' not in str(e).lower():
                logging.warning("Schema migration issue: {}".format(e))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# yfinance fetch (same logic as ei_collector._fetch_yfinance_data)
# ---------------------------------------------------------------------------

def _yf_fetch_inner(symbol):
    """Inner yfinance call with stdout/stderr suppression."""
    with contextlib.redirect_stderr(io.StringIO()), \
         contextlib.redirect_stdout(io.StringIO()):
        ticker = yf.Ticker(symbol)
        return ticker.calendar


def _fetch_yfinance_date(symbol):
    """Fetch earnings date from yfinance with 5s timeout.

    Returns:
        str or None: date string (YYYY-MM-DD) or None if unavailable/stale
    """
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_yf_fetch_inner, symbol)
        try:
            calendar = future.result(timeout=5)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if not calendar or 'Earnings Date' not in calendar:
            return None

        earnings_dates = calendar['Earnings Date']
        if not earnings_dates or len(earnings_dates) == 0:
            return None

        next_date = earnings_dates[0]
        if hasattr(next_date, 'strftime'):
            date_str = next_date.strftime('%Y-%m-%d')
        else:
            date_str = str(next_date)

        # Stale detection: past dates are not useful
        try:
            if date.fromisoformat(date_str) < date.today():
                return None
        except (ValueError, TypeError):
            return None

        return date_str

    except TimeoutError:
        logging.debug("yfinance timeout (5s) for {}".format(symbol))
        return None
    except Exception as e:
        logging.debug("yfinance fetch failed for {}: {}".format(symbol, e))
        return None


# ---------------------------------------------------------------------------
# Main refresh function
# ---------------------------------------------------------------------------

def run_lite_refresh(db_path=None, perf_db_path=None, days_ahead=21, spawn_agent=True):
    """Run lite daily earnings refresh for near-term unconfirmed symbols.

    Args:
        db_path: Path to datalake.db (default: auto-detect)
        perf_db_path: Path to performance.db (default: auto-detect)
        days_ahead: How many days ahead to look (default: 21)
        spawn_agent: Whether to spawn earnings researcher on disputes (default: True)

    Returns:
        dict: {success, symbols_checked, dates_updated, disputes_flagged, dispute_details, duration_seconds}
    """
    start_time = time.time()
    db = db_path or os.path.join(project_root, 'data', 'datalake.db')
    perf_db = perf_db_path or os.path.join(project_root, 'data', 'performance.db')
    today_str = eastern_date_string()

    # Ensure schema
    _ensure_confirmation_schema(db)

    # Query unconfirmed symbols within window
    conn = sqlite3.connect(db, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    rows = conn.execute("""
        SELECT symbol, earnings_date, earnings_time
        FROM earnings_upcoming
        WHERE date_confirmed = 0
          AND earnings_date >= ?
          AND earnings_date <= DATE(?, '+{} days')
        ORDER BY earnings_date ASC
    """.format(days_ahead), (today_str, today_str)).fetchall()
    conn.close()

    if not rows:
        logging.info("   No unconfirmed symbols within {} days".format(days_ahead))
        return {
            'success': True,
            'symbols_checked': 0,
            'dates_updated': 0,
            'disputes_flagged': 0,
            'dispute_details': [],
            'duration_seconds': time.time() - start_time,
        }

    logging.info("   Scope: {} unconfirmed symbols within {} days".format(len(rows), days_ahead))

    # Initialize Finnhub
    fh_api = None
    try:
        import json
        config_path = os.path.join(project_root, 'config.json')
        with open(config_path, 'r') as f:
            config = json.load(f)
        finnhub_config = config.get('finnhub', {})
        api_key = finnhub_config.get('api_key', '')
        if api_key:
            fh_api = FinnhubAPI(
                api_key=api_key,
                base_url=finnhub_config.get('base_url', 'https://finnhub.io/api/v1'),
                rate_limit_per_minute=finnhub_config.get('rate_limit_per_minute', 60),
            )
    except Exception as e:
        logging.warning("   Could not initialize Finnhub: {}".format(e))

    end_date = date.today() + timedelta(days=90)
    dates_updated = 0
    disputes = []

    for symbol, db_date, db_time in rows:
        # Fetch yfinance
        yf_date = _fetch_yfinance_date(symbol)

        # Fetch Finnhub
        fh_date = None
        fh_timing = None
        if fh_api:
            try:
                releases = fh_api.get_earnings_calendar(date.today(), end_date, symbol=symbol)
                if releases:
                    r = releases[0]
                    fh_date = r.get('date')
                    fh_timing = r.get('hour', 'Unknown')
            except Exception as e:
                logging.debug("Finnhub fetch failed for {}: {}".format(symbol, e))

        # Update stored date if yfinance returned something different and not confirmed
        if yf_date and yf_date != db_date:
            try:
                conn = sqlite3.connect(db, timeout=30)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute(
                    "UPDATE earnings_upcoming SET earnings_date = ?, updated_at = ? WHERE symbol = ? AND date_confirmed = 0",
                    (yf_date, eastern_isoformat(), symbol)
                )
                conn.commit()
                conn.close()
                dates_updated += 1
                logging.debug("   {} date updated: {} -> {}".format(symbol, db_date, yf_date))
            except Exception as e:
                logging.warning("   Failed to update {} date: {}".format(symbol, e))

        # Also update timing from Finnhub if we have it and current is Unknown
        if fh_timing and fh_timing != 'Unknown' and db_time == 'Unknown':
            try:
                conn = sqlite3.connect(db, timeout=30)
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute(
                    "UPDATE earnings_upcoming SET earnings_time = ? WHERE symbol = ? AND date_confirmed = 0",
                    (fh_timing, symbol)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logging.debug("   Failed to update {} timing: {}".format(symbol, e))

        # Flag disputes — only for FUTURE earnings (today's date is moot)
        effective_date = yf_date or db_date
        try:
            is_future = date.fromisoformat(effective_date) > date.today()
        except (ValueError, TypeError):
            is_future = False

        dispute_reason = None
        if is_future:
            effective_time = (fh_timing if fh_timing and fh_timing != 'Unknown' else db_time) or 'Unknown'

            # Dispute: Unknown time
            unknown_time = effective_time == 'Unknown'

            # Dispute: yfinance vs Finnhub disagree (only when both are near-term,
            # not when Finnhub jumped to next quarter)
            date_disagreement = False
            if yf_date and fh_date and yf_date != fh_date:
                try:
                    diff = abs((date.fromisoformat(yf_date) - date.fromisoformat(fh_date)).days)
                    # Only flag if dates are within 45 days of each other —
                    # larger gaps mean Finnhub is showing next quarter, not disagreeing
                    if diff > 1 and diff <= 45:
                        date_disagreement = True
                except (ValueError, TypeError):
                    pass

            # Dispute: yfinance vs stored disagree by >3 days (large shift = suspicious)
            large_shift = False
            if yf_date and db_date and yf_date != db_date:
                try:
                    diff = abs((date.fromisoformat(yf_date) - date.fromisoformat(db_date)).days)
                    if diff > 3:
                        large_shift = True
                except (ValueError, TypeError):
                    pass

            if unknown_time and date_disagreement:
                dispute_reason = 'both'
            elif date_disagreement or large_shift:
                dispute_reason = 'date_disagreement'
            elif unknown_time:
                dispute_reason = 'unknown_time'

        if dispute_reason:
            disputes.append({
                'symbol': symbol,
                'db_date': db_date,
                'db_time': db_time,
                'yfinance_date': yf_date,
                'finnhub_date': fh_date,
                'dispute_reason': dispute_reason,
            })

    # Write disputes to performance.db
    if disputes:
        try:
            conn = sqlite3.connect(perf_db, timeout=30)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            for d in disputes:
                conn.execute("""
                    INSERT OR REPLACE INTO earnings_date_disputes
                        (trade_date, symbol, db_date, db_time, yfinance_date, finnhub_date,
                         dispute_reason, resolution)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'unresolved')
                """, (today_str, d['symbol'], d['db_date'], d['db_time'],
                      d['yfinance_date'], d['finnhub_date'], d['dispute_reason']))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.warning("   Failed to write disputes to performance.db: {}".format(e))

    # Summary
    reason_counts = {}
    for d in disputes:
        reason_counts[d['dispute_reason']] = reason_counts.get(d['dispute_reason'], 0) + 1

    duration = time.time() - start_time
    logging.info("   Refreshed: {} ({} dates updated, {} unchanged)".format(
        len(rows), dates_updated, len(rows) - dates_updated))

    if disputes:
        reason_parts = []
        for reason, count in sorted(reason_counts.items()):
            reason_parts.append('{} {}'.format(count, reason))
        logging.info("   Disputes flagged: {} ({})".format(len(disputes), ', '.join(reason_parts)))
    else:
        logging.info("   Disputes flagged: 0")

    # Spawn earnings researcher agent if disputes exist
    if disputes and spawn_agent:
        _spawn_earnings_researcher(len(disputes))

    return {
        'success': True,
        'symbols_checked': len(rows),
        'dates_updated': dates_updated,
        'disputes_flagged': len(disputes),
        'dispute_details': disputes,
        'duration_seconds': duration,
    }


# ---------------------------------------------------------------------------
# Agent spawning
# ---------------------------------------------------------------------------

def _spawn_earnings_researcher(dispute_count):
    """Spawn earnings researcher agent in a visible window (fire-and-forget).

    Uses a temp batch file to avoid cmd.exe /k quoting issues with multiple
    quoted paths (cmd /k "prog" "arg" mangles the middle quotes).
    """
    launcher_path = os.path.join(project_root, 'agents', 'earnings_researcher', 'launcher.py')
    if not os.path.exists(launcher_path):
        logging.info("   Earnings researcher agent not installed — skipping auto-spawn")
        return

    try:
        python_exe = sys.executable
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
            f.write('@echo off\n')
            f.write('cd /d "{}"\n'.format(project_root))
            f.write('"{}" "{}"\n'.format(python_exe, launcher_path))
            bat_file = f.name

        subprocess.Popen(
            'start "Earnings Researcher" cmd /k "{}"'.format(bat_file),
            shell=True,
            cwd=project_root,
        )
        logging.info("   Spawning earnings date agent for {} symbols...".format(dispute_count))
    except Exception as e:
        logging.warning("   Failed to spawn earnings researcher: {}".format(e))
