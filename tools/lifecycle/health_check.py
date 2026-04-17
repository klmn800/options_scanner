"""
Symbol Health Check (health_check.py)
--------------------------------------
Detects symbols missing from option_contracts for 3+ consecutive trading days.
Runs as Phase 6.2 in the orchestrator, after performance data collection.

Two tiers:
  - Warning (3-4 days): early signal, logged but no lifecycle event
  - Suspect (5+ days): logged as suspect_detected in symbol_lifecycle_events

90% safety gate: if fewer than 90% of active symbols have data on the most
recent trading day, skip the check (likely API outage, not symbol-level issue).

PRD 0013 — Symbol Lifecycle Management (FR-15, FR-16, FR-17)
"""

import os
import sqlite3
import sys
from collections import namedtuple

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.lifecycle.audit import log_lifecycle_event, is_suspect_already_logged

HealthResult = namedtuple('HealthResult', ['symbol', 'last_data_date', 'consecutive_missing_days'])


def run_health_check(db_path):
    """Check for symbols missing from option_contracts.

    Queries the last 10 distinct trading dates from option_contracts,
    then finds symbols in the active universe that are missing from
    the most recent 5 trading dates.

    Args:
        db_path: Path to datalake.db

    Returns:
        dict with keys:
            - warnings: list[HealthResult] — symbols missing 3-4 days
            - suspects: list[HealthResult] — symbols missing 5+ days
            - safety_gate_tripped: bool — True if <90% coverage
            - safety_gate_message: str or None
            - active_count: int — total active symbols
            - covered_count: int — symbols with data on most recent day
    """
    result = {
        'warnings': [],
        'suspects': [],
        'safety_gate_tripped': False,
        'safety_gate_message': None,
        'active_count': 0,
        'covered_count': 0,
    }

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()

        # Get active universe symbols
        cursor.execute("""
            SELECT symbol FROM symbol_metadata
            WHERE universe_tier IN ('fm_universe', 'daily_only')
        """)
        active_symbols = {row[0] for row in cursor.fetchall()}
        result['active_count'] = len(active_symbols)

        if not active_symbols:
            return result

        # Get the last 10 distinct trading dates from option_contracts
        cursor.execute("""
            SELECT DISTINCT trade_date FROM option_contracts
            ORDER BY trade_date DESC LIMIT 10
        """)
        recent_dates = [row[0] for row in cursor.fetchall()]

        if len(recent_dates) < 5:
            result['safety_gate_tripped'] = True
            result['safety_gate_message'] = f'Insufficient trading dates ({len(recent_dates)} < 5)'
            return result

        most_recent_date = recent_dates[0]
        last_5_dates = set(recent_dates[:5])

        # Safety gate: check coverage on most recent date
        cursor.execute("""
            SELECT COUNT(DISTINCT symbol) FROM option_contracts
            WHERE trade_date = ?
        """, (most_recent_date,))
        covered = cursor.fetchone()[0]
        result['covered_count'] = covered

        coverage_pct = covered / len(active_symbols) if active_symbols else 0
        if coverage_pct < 0.90:
            result['safety_gate_tripped'] = True
            result['safety_gate_message'] = (
                f'Only {covered}/{len(active_symbols)} ({coverage_pct:.0%}) symbols have data on '
                f'{most_recent_date} — likely API outage, skipping health check'
            )
            return result

        # For each active symbol, find most recent trade_date in option_contracts
        # and count consecutive missing days from the end of the last_5_dates
        cursor.execute("""
            SELECT symbol, MAX(trade_date) as last_date
            FROM option_contracts
            WHERE symbol IN ({})
            GROUP BY symbol
        """.format(','.join('?' * len(active_symbols))), list(active_symbols))

        symbol_last_dates = {row[0]: row[1] for row in cursor.fetchall()}

        for symbol in sorted(active_symbols):
            last_date = symbol_last_dates.get(symbol)

            if last_date is None:
                # No data at all — count as missing all 5 days
                missing = 5
            else:
                # Count how many of the last 5 trading dates are missing
                missing = sum(1 for d in last_5_dates if d > (last_date or ''))

            if missing >= 5:
                result['suspects'].append(HealthResult(symbol, last_date, missing))
            elif missing >= 3:
                result['warnings'].append(HealthResult(symbol, last_date, missing))

    return result


def log_suspects(db_path, health_result):
    """Log suspect_detected events for symbols missing 5+ days.

    Idempotent: skips symbols that already have an unresolved suspect event.

    Args:
        db_path: Path to datalake.db
        health_result: Dict returned by run_health_check()

    Returns:
        int: Number of new suspect events logged
    """
    logged = 0
    for suspect in health_result.get('suspects', []):
        if is_suspect_already_logged(db_path, suspect.symbol):
            continue

        log_lifecycle_event(
            db_path=db_path,
            symbol=suspect.symbol,
            event_type='suspect_detected',
            tier=None,
            reason=(
                f'No option_contracts data for {suspect.consecutive_missing_days} '
                f'consecutive trading days (last: {suspect.last_data_date or "never"})'
            ),
            operator='health_check',
            metadata_dict={
                'last_data_date': suspect.last_data_date,
                'consecutive_missing_days': suspect.consecutive_missing_days,
            }
        )
        logged += 1

    return logged
