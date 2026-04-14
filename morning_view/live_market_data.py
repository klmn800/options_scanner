#!/usr/bin/env python3
"""
Live Market Data Module for Morning View TUI

Fetches and formats real-time market snapshot data from flow_options_scans table.
Updates every ~60 seconds during market hours.

Data includes:
- SPY price and change %
- VIX price and change %
- Advance/Decline ratio and market direction (BULL/BEAR/NEUTRAL)
- Volatility regime (LOW/NORMAL/ELEVATED/HIGH)
- Data freshness (staleness warnings if >5 minutes old)

Author: Ben
Date: 2025-10-14
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

# Configure UTF-8 output for Windows
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.timezone_utils import now_eastern


def get_live_market_snapshot(db_path: str) -> Optional[Dict]:
    """
    Fetch live market snapshot data from v_live_market_snapshot view + sector ETFs.

    Args:
        db_path: Path to database

    Returns:
        Dict with snapshot data or None if no data available

    Structure:
        {
            'last_updated': '2025-10-14 14:35:22',
            'trade_date': '2025-10-14',
            'spy_price': 580.25,
            'spy_change_pct': 0.85,
            'vix_price': 16.34,
            'vix_change_pct': -2.15,
            'advancing_stocks': 657,
            'declining_stocks': 70,
            'adv_dec_ratio': 9.39,
            'market_direction': 'BULL',
            'volatility_regime': 'NORMAL',
            'sectors': {
                'XLF': {'price': 41.25, 'change_pct': 1.2},
                'XLE': {'price': 89.50, 'change_pct': -0.5},
                ...
            }
        }
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query the view for SPY/VIX/breadth data
        cursor.execute("SELECT * FROM v_live_market_snapshot LIMIT 1")
        row = cursor.fetchone()

        # Check if we have valid live data (row exists and has SPY/trade_date)
        if not row or row['spy_price'] is None or row['trade_date'] is None:
            # No live data - try to get last close data from market_daily_summary as fallback
            data = _get_last_close_fallback(cursor)
            conn.close()
            return data

        # Convert to dict
        data = dict(row)
        trade_date = data.get('trade_date')

        # Get sector ETF data from flow_options_scans
        sectors = _get_sector_etf_data(cursor, trade_date)
        data['sectors'] = sectors

        conn.close()
        return data

    except Exception as e:
        print(f"ERROR: Failed to fetch live market snapshot: {e}")
        return None


def _get_last_close_fallback(cursor) -> Optional[Dict]:
    """
    Fallback to last close data from market_daily_summary when no live data available.
    Used when market is closed (after hours, weekends).

    Args:
        cursor: Database cursor

    Returns:
        Dict with last close data or None
    """
    try:
        # Get most recent market_daily_summary entry
        cursor.execute("""
            SELECT
                trade_date,
                spy_close as spy_price,
                spy_change_percent as spy_change_pct,
                vix_close as vix_price,
                vix_change_percent as vix_change_pct,
                advancing_stocks,
                declining_stocks,
                ROUND(CAST(advancing_stocks AS REAL) / NULLIF(declining_stocks, 0), 2) as adv_dec_ratio,
                market_direction,
                regime_classification as volatility_regime,
                xlf_close, xlf_change_percent,
                xle_close, xle_change_percent,
                xlk_close, xlk_change_percent,
                xlv_close, xlv_change_percent,
                xli_close, xli_change_percent,
                xlp_close, xlp_change_percent,
                xly_close, xly_change_percent,
                xlu_close, xlu_change_percent,
                xlb_close, xlb_change_percent,
                xlre_close, xlre_change_percent
            FROM market_daily_summary
            WHERE regime_classification IS NOT NULL
            ORDER BY trade_date DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        if not row:
            return None

        data = dict(row)

        # Map regime classification to display format
        regime_map = {
            'low_vol': 'LOW',
            'normal': 'NORMAL',
            'elevated': 'ELEVATED',
            'panic': 'PANIC'
        }
        data['volatility_regime'] = regime_map.get(data.get('volatility_regime', 'normal'), 'NORMAL')

        # Map market_direction to uppercase
        direction = data.get('market_direction', 'Neutral')
        if 'bull' in direction.lower():
            data['market_direction'] = 'BULL'
        elif 'bear' in direction.lower():
            data['market_direction'] = 'BEAR'
        else:
            data['market_direction'] = 'NEUTRAL'

        # Build sectors dict from close data
        sectors = {}
        sector_mappings = {
            'XLF': ('xlf_close', 'xlf_change_percent'),
            'XLE': ('xle_close', 'xle_change_percent'),
            'XLK': ('xlk_close', 'xlk_change_percent'),
            'XLV': ('xlv_close', 'xlv_change_percent'),
            'XLI': ('xli_close', 'xli_change_percent'),
            'XLP': ('xlp_close', 'xlp_change_percent'),
            'XLY': ('xly_close', 'xly_change_percent'),
            'XLU': ('xlu_close', 'xlu_change_percent'),
            'XLB': ('xlb_close', 'xlb_change_percent'),
            'XLRE': ('xlre_close', 'xlre_change_percent')
        }

        for symbol, (price_col, change_col) in sector_mappings.items():
            price = data.get(price_col)
            change_pct = data.get(change_col)
            if price is not None:
                sectors[symbol] = {
                    'price': price,
                    'change_pct': change_pct
                }

        data['sectors'] = sectors
        data['is_last_close'] = True  # Flag to indicate this is fallback data

        return data

    except Exception as e:
        print(f"ERROR: Failed to get last close fallback: {e}")
        return None


def _get_sector_etf_data(cursor, trade_date: str) -> Dict:
    """
    Get sector ETF prices and changes from flow_options_scans.

    Args:
        cursor: Database cursor
        trade_date: Current trade date

    Returns:
        Dict mapping sector symbols to price/change data
    """
    try:
        sector_symbols = ['XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU', 'XLB', 'XLRE']

        # Get latest scan for each sector ETF (one row per symbol)
        cursor.execute("""
            SELECT
                symbol,
                underlying_price as price,
                underlying_change_pct as change_pct
            FROM flow_options_scans
            WHERE symbol IN ({})
            AND trade_date = ?
            AND scan_timestamp = (
                SELECT MAX(scan_timestamp)
                FROM flow_options_scans
                WHERE trade_date = ?
            )
            GROUP BY symbol
        """.format(','.join(['?'] * len(sector_symbols))),
            sector_symbols + [trade_date, trade_date])

        sectors = {}
        for row in cursor.fetchall():
            symbol = row[0]
            sectors[symbol] = {
                'price': row[1],
                'change_pct': row[2]
            }

        return sectors

    except Exception as e:
        print(f"ERROR: Failed to get sector ETF data: {e}")
        return {}


def format_market_snapshot(snapshot: Dict) -> str:
    """
    Format market snapshot for Rich markup display in TUI.

    Args:
        snapshot: Dict from get_live_market_snapshot()

    Returns:
        Formatted text string with Rich markup
    """
    if not snapshot:
        return "[dim]Live market data unavailable\\n(No data for today)[/dim]"

    # Format date with market status indicator
    trade_date = snapshot.get('trade_date', 'Unknown')
    is_last_close = snapshot.get('is_last_close', False)

    # Build header based on market status
    if is_last_close:
        header = f"[bold cyan]Last Close: {trade_date}[/bold cyan]\n[dim](Market currently closed)[/dim]"
    else:
        header = ""  # No header duplication - panel title already shows "Live Market Snapshot"

    # Format SPY
    spy_price = snapshot.get('spy_price')
    spy_change = snapshot.get('spy_change_pct')
    if spy_price is not None:
        if spy_change is not None:
            spy_color = 'green' if spy_change >= 0 else 'red'
            spy_arrow = '▲' if spy_change >= 0 else '▼'
            spy_line = f"[bold]SPY:[/bold] ${spy_price:.2f} [{spy_color}]{spy_arrow} {spy_change:+.2f}%[/{spy_color}]"
        else:
            spy_line = f"[bold]SPY:[/bold] ${spy_price:.2f} [dim](no change data)[/dim]"
    else:
        spy_line = f"[bold]SPY:[/bold] [dim]N/A[/dim]"

    # Format VIX (no color - just direction arrow)
    vix_price = snapshot.get('vix_price')
    vix_change = snapshot.get('vix_change_pct')
    if vix_price is not None:
        if vix_change is not None:
            vix_arrow = '▲' if vix_change >= 0 else '▼'
            vix_line = f"[bold]VIX:[/bold] ${vix_price:.2f} {vix_arrow} {vix_change:+.2f}%"
        else:
            vix_line = f"[bold]VIX:[/bold] ${vix_price:.2f} [dim](no change data)[/dim]"
    else:
        vix_line = f"[bold]VIX:[/bold] [dim]N/A[/dim]"

    # Format market breadth
    advancing = snapshot.get('advancing_stocks', 0)
    declining = snapshot.get('declining_stocks', 0)
    breadth_line = f"[bold]Breadth:[/bold] {advancing} adv / {declining} dec"

    # Format market direction
    direction = snapshot.get('market_direction', 'NEUTRAL')
    if direction == 'BULL':
        direction_emoji = '🐮'
        direction_color = 'bold green'
    elif direction == 'BEAR':
        direction_emoji = '🐻'
        direction_color = 'bold red'
    else:
        direction_emoji = '⚖️'
        direction_color = 'yellow'
    direction_line = f"[bold]Direction:[/bold] [{direction_color}]{direction_emoji} {direction}[/{direction_color}]"

    # Format volatility regime (CBOE standards)
    regime = snapshot.get('volatility_regime', 'NORMAL')
    if regime == 'PANIC':
        regime_color = 'bold red'
    elif regime == 'ELEVATED':
        regime_color = 'yellow'
    elif regime == 'LOW':
        regime_color = 'green'
    else:  # NORMAL
        regime_color = 'white'
    regime_line = f"[bold]Volatility:[/bold] [{regime_color}]{regime}[/{regime_color}]"

    # Format sector ETFs (compact 2-column layout)
    sectors = snapshot.get('sectors', {})
    sector_lines = _format_sector_etfs(sectors)

    # Build output
    summary = f"""{header}

{spy_line}
{vix_line}

{breadth_line}
{direction_line}
{regime_line}

{sector_lines}"""

    return summary.strip()


def _format_sector_etfs(sectors: Dict) -> str:
    """
    Format sector ETFs in 2-column x 5-row layout with expanded names.

    Layout:
        Sectors:
        Materials    +0.1%   Energy       +0.0%
        Financials   +0.0%   Technology   +0.1%
        Industrials  +0.1%   Staples     -0.1%
        Real Estate   N/A    Utilities    +0.1%
        Healthcare   -0.0%   Consumer    -0.1%

    Args:
        sectors: Dict mapping symbols to {'price': float, 'change_pct': float}

    Returns:
        Formatted string with sector data in 2-column layout
    """
    if not sectors:
        return "[dim]Sectors: No data[/dim]"

    # Expanded sector names for display
    sector_names = {
        'XLB': 'Materials',
        'XLE': 'Energy',
        'XLF': 'Financials',
        'XLI': 'Industrials',
        'XLK': 'Technology',
        'XLP': 'Staples',
        'XLRE': 'Real Estate',
        'XLU': 'Utilities',
        'XLV': 'Healthcare',
        'XLY': 'Consumer'
    }

    # Define display order (left column, right column)
    left_column = ['XLB', 'XLF', 'XLI', 'XLRE', 'XLV']
    right_column = ['XLE', 'XLK', 'XLP', 'XLU', 'XLY']

    def format_sector(symbol):
        """Format single sector with name and change %"""
        name = sector_names.get(symbol, symbol)
        data = sectors.get(symbol)

        if data and data.get('change_pct') is not None:
            change_pct = data['change_pct']
            color = 'green' if change_pct >= 0 else 'red'
            # Name (11 chars left-aligned) + 2 spaces + colored percentage
            return f"{name:11s}  [{color}]{change_pct:+.1f}%[/{color}]"
        else:
            # Name (11 chars) + N/A
            return f"{name:11s}  [dim]N/A[/dim]"

    # Build 2-column rows
    lines = ["[bold]Sectors:[/bold]"]
    for left_sym, right_sym in zip(left_column, right_column):
        left_formatted = format_sector(left_sym)
        right_formatted = format_sector(right_sym)
        # 3 spaces between columns
        lines.append(f"{left_formatted}   {right_formatted}")

    return "\n".join(lines)


def main():
    """CLI entry point for testing live market data module."""
    import argparse

    parser = argparse.ArgumentParser(description="Test live market data module")
    parser.add_argument('--db', default='data/datalake_query.db', help='Database path')

    args = parser.parse_args()

    # Get and display snapshot
    snapshot = get_live_market_snapshot(args.db)
    if snapshot:
        formatted = format_market_snapshot(snapshot)
        print("\n" + "="*60)
        print(formatted)
        print("="*60)
    else:
        print("No live market data available")


if __name__ == '__main__':
    main()
