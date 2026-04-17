"""
Pre-flight Checks for Symbol Onboarding (preflight.py)
-------------------------------------------------------
Validates a symbol before adding it to the universe.
All checks are warn-and-continue — none are hard blocks.

PRD 0013 — Symbol Lifecycle Management
"""

import os
import sqlite3
import sys
from collections import namedtuple

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.lifecycle.routing import determine_archive_db

PreflightResult = namedtuple('PreflightResult', ['check_name', 'passed', 'message'])


def run_preflight_checks(symbol, tradier_data, db_path=None):
    """Run all pre-flight checks for a symbol.

    Args:
        symbol: Stock ticker
        tradier_data: Dict from Tradier API with keys:
            - expirations: list of option expiration dates (or None)
            - avg_volume: average daily volume (or 0)
            - sector: sector classification
            - industry: industry classification
            - earnings_available: bool from Tradier calendars check
        db_path: Path to datalake.db (auto-resolves if None)

    Returns:
        list[PreflightResult]: Results for each check
    """
    if db_path is None:
        db_path = os.path.join(project_root, 'data', 'datalake.db')

    results = []

    # 1. Optionable
    expirations = tradier_data.get('expirations') or []
    if expirations:
        results.append(PreflightResult(
            'Optionable', True,
            f'YES ({len(expirations)} expirations available)'))
    else:
        results.append(PreflightResult(
            'Optionable', False,
            'No option expirations found'))

    # 2. Liquidity
    avg_volume = tradier_data.get('avg_volume') or 0
    if avg_volume >= 10_000_000:
        tier = 'ULTRA LIQUID'
    elif avg_volume >= 1_000_000:
        tier = 'HIGH'
    elif avg_volume >= 100_000:
        tier = 'MODERATE'
    else:
        tier = 'LOW'

    passed = avg_volume >= 100_000
    vol_str = f'{avg_volume:,.0f}' if avg_volume else 'unknown'
    results.append(PreflightResult(
        'Liquidity', passed,
        f'{tier} ({vol_str} avg volume)' + ('' if passed else ' — same bucket as purgatory symbols')))

    # 3. Not already in universe
    try:
        with sqlite3.connect(db_path, timeout=10.0) as conn:
            row = conn.execute(
                'SELECT universe_tier FROM symbol_metadata WHERE symbol = ?',
                (symbol,)).fetchone()
            if row is None:
                results.append(PreflightResult('Not in universe', True, 'New symbol'))
            elif row[0] in ('fm_universe', 'daily_only'):
                results.append(PreflightResult(
                    'Not in universe', False,
                    f'Already active (tier: {row[0]})'))
            elif row[0] == 'purgatory':
                results.append(PreflightResult(
                    'Not in universe', False,
                    'In purgatory — use --restore instead'))
            else:
                results.append(PreflightResult(
                    'Not in universe', True,
                    f'Previously removed (tier: {row[0]})'))
    except Exception as e:
        results.append(PreflightResult('Not in universe', True, f'Could not check: {e}'))

    # 4. Sector resolvable → archive routing
    sector = tradier_data.get('sector', 'N/A')
    industry = tradier_data.get('industry', 'N/A')
    archive_db, is_ambiguous = determine_archive_db(sector, industry)
    if archive_db and not is_ambiguous:
        results.append(PreflightResult(
            'Sector resolvable', True,
            f'{sector} / {industry} -> {archive_db}.db'))
    elif archive_db and is_ambiguous:
        results.append(PreflightResult(
            'Sector resolvable', True,
            f'{sector} / {industry} -> {archive_db}.db (ambiguous — will confirm)'))
    else:
        results.append(PreflightResult(
            'Sector resolvable', False,
            f'Cannot determine archive for sector={sector}, industry={industry}'))

    # 5. Earnings data available
    earnings_available = tradier_data.get('earnings_available', False)
    if earnings_available:
        results.append(PreflightResult(
            'Earnings data', True,
            'Tradier calendars data available'))
    else:
        results.append(PreflightResult(
            'Earnings data', False,
            'No earnings data from Tradier calendars (ADR/REIT may not have standard earnings)'))

    return results
