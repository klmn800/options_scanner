#!/usr/bin/env python3
"""
Tradeable Moments Analysis for Cheap Options Research
Tracks whether profitable exit opportunities occur within 5-day holding period
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# Database path
DB_PATH = "../data/datalake_query.db"

# Constants
MIN_ASK = 0.03
MAX_ASK = 0.10
MIN_DTE = 20  # Changed from 30 to 20
MAX_DTE = 60  # System's upper limit
EXCLUDED_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'DIA', 'VIX']
TARGET_RETURN = 0.25  # 25% GROSS profit target (ignore fees)

# Date range for sampling (to keep processing manageable)
MIN_DATE = '2025-09-01'  # Focus on Sept-Oct data (ensures 5-day forward windows)

def connect_db():
    """Connect to query database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_all_scans(conn):
    """Get all qualifying scans from database"""
    query = """
    SELECT
        contract_hash,
        trade_date,
        scan_timestamp,
        symbol,
        strike,
        expiration_date,
        option_type,
        bid,
        ask,
        dte,
        delta,
        vega,
        theta,
        iv,
        underlying_price
    FROM flow_options_scans
    WHERE ask >= ? AND ask <= ?
      AND dte >= ? AND dte <= ?
      AND trade_date >= ?
      AND symbol NOT IN ({})
      AND bid > 0 AND ask > 0
      AND vega IS NOT NULL
      AND delta IS NOT NULL
    ORDER BY contract_hash, trade_date, scan_timestamp
    """.format(','.join(['?'] * len(EXCLUDED_SYMBOLS)))

    params = [MIN_ASK, MAX_ASK, MIN_DTE, MAX_DTE, MIN_DATE] + EXCLUDED_SYMBOLS

    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.fetchall()

def parse_date(date_str):
    """Parse date string to date object"""
    return datetime.strptime(date_str, '%Y-%m-%d').date()

def parse_timestamp(ts_str):
    """Parse timestamp string to datetime object"""
    return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')

def get_trading_days_forward(start_date, all_dates, num_days=5):
    """Get next N trading days from start date"""
    future_dates = [d for d in all_dates if d > start_date]
    return future_dates[:num_days]

def analyze_tradeable_moments(scans):
    """
    Core analysis: For each entry point, track if profitable exit occurred

    Entry Definition: First scan of each trading day where contract meets criteria
    Exit Target: Bid price >= entry_ask * (1 + target_return + fees/entry_ask)
    """
    print("Processing scans...")

    # Group scans by contract_hash and trade_date
    contract_date_scans = defaultdict(list)
    all_trade_dates = set()

    for scan in scans:
        contract_hash = scan['contract_hash']
        trade_date = scan['trade_date']
        contract_date_scans[(contract_hash, trade_date)].append(dict(scan))
        all_trade_dates.add(parse_date(trade_date))

    all_trade_dates = sorted(all_trade_dates)
    print(f"Loaded {len(scans)} scans across {len(all_trade_dates)} trading days")

    # Identify entry points (first scan of each day for each contract)
    entries = []

    for (contract_hash, trade_date), day_scans in contract_date_scans.items():
        # Sort by timestamp to get first scan of day
        day_scans.sort(key=lambda x: x['scan_timestamp'])
        first_scan = day_scans[0]

        entries.append({
            'contract_hash': contract_hash,
            'entry_date': trade_date,
            'entry_timestamp': first_scan['scan_timestamp'],
            'entry_ask': first_scan['ask'],
            'entry_bid': first_scan['bid'],
            'symbol': first_scan['symbol'],
            'strike': first_scan['strike'],
            'option_type': first_scan['option_type'],
            'dte': first_scan['dte'],
            'delta': first_scan['delta'],
            'vega': first_scan['vega'],
            'theta': first_scan['theta'],
            'iv': first_scan['iv']
        })

    print(f"Identified {len(entries)} entry points")

    # For each entry, track tradeable moments in next 5 days
    results = []

    for i, entry in enumerate(entries):
        if i % 100 == 0:
            print(f"Processing entry {i+1}/{len(entries)}...")

        contract_hash = entry['contract_hash']
        entry_date_obj = parse_date(entry['entry_date'])
        entry_ask = entry['entry_ask']

        # Calculate target price (25% gross, ignore fees)
        target_price = entry_ask * (1 + TARGET_RETURN)

        # Get next 5 trading days
        future_days = get_trading_days_forward(entry_date_obj, all_trade_dates, 5)

        if len(future_days) == 0:
            continue  # Entry too recent, no future data

        # Track max sellable price (max of bid or last_price) in 5-day window
        max_sellable = 0
        max_sellable_timestamp = None
        max_sellable_type = None  # 'bid' or 'last'
        days_to_target = None
        scans_at_target = 0

        for future_date in future_days:
            future_date_str = future_date.strftime('%Y-%m-%d')
            day_scans = contract_date_scans.get((contract_hash, future_date_str), [])

            for scan in day_scans:
                bid = scan['bid']
                last = scan.get('last_price', 0) or 0

                # Track whichever is higher (bid or last_price)
                sellable_price = max(bid, last)

                if sellable_price > max_sellable:
                    max_sellable = sellable_price
                    max_sellable_timestamp = scan['scan_timestamp']
                    max_sellable_type = 'last' if last > bid else 'bid'

                if sellable_price >= target_price:
                    scans_at_target += 1
                    if days_to_target is None:
                        days_diff = (future_date - entry_date_obj).days
                        days_to_target = days_diff

        # Calculate returns (gross only, ignore fees)
        gross_return = (max_sellable - entry_ask) / entry_ask if entry_ask > 0 else 0
        is_winner = gross_return >= TARGET_RETURN

        results.append({
            **entry,
            'target_price': target_price,
            'max_sellable_5d': max_sellable,
            'max_sellable_timestamp': max_sellable_timestamp,
            'max_sellable_type': max_sellable_type,
            'gross_return_pct': gross_return * 100,
            'is_winner': is_winner,
            'days_to_peak': days_to_target,
            'scans_at_target': scans_at_target
        })

    return results

def calculate_summary_stats(results):
    """Calculate aggregate statistics"""
    total = len(results)
    winners = [r for r in results if r['is_winner']]
    losers = [r for r in results if not r['is_winner']]

    win_count = len(winners)
    loss_count = len(losers)
    win_rate = (win_count / total * 100) if total > 0 else 0

    avg_winner_return = sum(r['gross_return_pct'] for r in winners) / win_count if win_count > 0 else 0
    avg_loser_return = sum(r['gross_return_pct'] for r in losers) / loss_count if loss_count > 0 else 0
    avg_return = sum(r['gross_return_pct'] for r in results) / total if total > 0 else 0

    # Days to target (for winners only)
    winners_with_target = [r for r in winners if r['days_to_peak'] is not None]
    avg_days_to_target = sum(r['days_to_peak'] for r in winners_with_target) / len(winners_with_target) if winners_with_target else 0

    # Scans at target (opportunity duration)
    avg_scans_at_target = sum(r['scans_at_target'] for r in winners) / win_count if win_count > 0 else 0

    return {
        'total_entries': total,
        'winners': win_count,
        'losers': loss_count,
        'win_rate_pct': win_rate,
        'avg_winner_return_pct': avg_winner_return,
        'avg_loser_return_pct': avg_loser_return,
        'avg_return_pct': avg_return,
        'avg_days_to_target': avg_days_to_target,
        'avg_scans_at_target': avg_scans_at_target
    }

def main():
    print("=== Cheap Options Tradeable Moments Analysis ===\n")

    # Connect and load data
    conn = connect_db()
    print("Loading scans from database...")
    scans = get_all_scans(conn)
    conn.close()

    if not scans:
        print("No qualifying scans found!")
        return

    # Run analysis
    print("\nAnalyzing tradeable moments...")
    results = analyze_tradeable_moments(scans)

    print(f"\nCompleted analysis of {len(results)} entries\n")

    # Calculate stats
    stats = calculate_summary_stats(results)

    # Print summary
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    print(f"Total Entry Points: {stats['total_entries']:,}")
    print(f"Winners: {stats['winners']:,}")
    print(f"Losers: {stats['losers']:,}")
    print(f"Win Rate: {stats['win_rate_pct']:.2f}%")
    print(f"Average Return (All): {stats['avg_return_pct']:.2f}%")
    print(f"Average Winner Return: {stats['avg_winner_return_pct']:.2f}%")
    print(f"Average Loser Return: {stats['avg_loser_return_pct']:.2f}%")
    print(f"Average Days to Target: {stats['avg_days_to_target']:.1f} days")
    print(f"Average Scans at Target: {stats['avg_scans_at_target']:.1f} scans")
    print("=" * 60)

    # Sample winners
    print("\nSAMPLE WINNERS (First 10):")
    winners = [r for r in results if r['is_winner']][:10]
    for w in winners:
        print(f"  {w['symbol']} ${w['strike']} {w['option_type']} | "
              f"Entry: ${w['entry_ask']:.2f} | Max: ${w['max_sellable_5d']:.2f} ({w['max_sellable_type']}) | "
              f"Return: {w['gross_return_pct']:.1f}% | Days: {w['days_to_peak']}")

    # Sample losers
    print("\nSAMPLE LOSERS (First 10):")
    losers = [r for r in results if not r['is_winner']][:10]
    for l in losers:
        print(f"  {l['symbol']} ${l['strike']} {l['option_type']} | "
              f"Entry: ${l['entry_ask']:.2f} | Max: ${l['max_sellable_5d']:.2f} ({l['max_sellable_type']}) | "
              f"Return: {l['gross_return_pct']:.1f}%")

    print("\nAnalysis complete. Results ready for evidence tables.")

if __name__ == "__main__":
    main()
