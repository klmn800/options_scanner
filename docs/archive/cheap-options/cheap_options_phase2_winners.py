"""
Phase 2: Identify Winners in Training Data

Tracks each cheap options entry in training period (Aug 18 - Sept 30) and determines
if it hit 25% profit target within 5 trading days.

Entry: First scan where contract meets Universe B criteria
Exit: max(bid, last_price) over next 5 trading days
Win: max_exit >= entry_ask * 1.25
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from collections import defaultdict

# Configure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Universe B criteria
UNIVERSE_B_ETF_LIST = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP', 'VIX']
MIN_ASK = 0.03
MAX_ASK = 0.10
MIN_DTE = 15
MAX_DTE = 60

TRAINING_START = '2025-08-18'
TRAINING_END = '2025-09-30'

def get_db_connection():
    """Connect to datalake_query.db"""
    return sqlite3.connect('data/datalake_query.db')

def get_trading_dates():
    """Get list of all trading dates in order"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT trade_date
        FROM flow_options_scans
        WHERE trade_date >= ? AND trade_date <= ?
        ORDER BY trade_date
    """, (TRAINING_START, TRAINING_END))

    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def get_entries_for_date(trade_date):
    """Get all Universe B entries for a specific date (first scan of each contract)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get first scan of each contract on this date that meets Universe B criteria
    cursor.execute("""
        SELECT
            contract_hash,
            symbol,
            strike,
            expiration_date,
            option_type,
            dte,
            ask,
            bid,
            last_price,
            iv,
            delta,
            gamma,
            theta,
            vega,
            underlying_price,
            MIN(scan_timestamp) as entry_timestamp
        FROM flow_options_scans
        WHERE trade_date = ?
            AND ask >= ? AND ask <= ?
            AND dte >= ? AND dte <= ?
            AND bid > 0
            AND vega IS NOT NULL
            AND symbol NOT IN ({})
        GROUP BY contract_hash
    """.format(','.join(['?'] * len(UNIVERSE_B_ETF_LIST))),
    (trade_date, MIN_ASK, MAX_ASK, MIN_DTE, MAX_DTE, *UNIVERSE_B_ETF_LIST))

    columns = [desc[0] for desc in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]

    conn.close()
    return results

def get_exit_opportunities(contract_hash, entry_date, trading_dates):
    """
    Track exit opportunities for next 5 trading days.
    Returns list of (trade_date, max_exit_price) for each day.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get index of entry date
    try:
        entry_idx = trading_dates.index(entry_date)
    except ValueError:
        return []

    # Get next 5 trading dates (or fewer if not available)
    future_dates = trading_dates[entry_idx + 1 : entry_idx + 6]

    if not future_dates:
        return []

    # Query all scans for this contract on future dates
    placeholders = ','.join(['?'] * len(future_dates))
    cursor.execute(f"""
        SELECT
            trade_date,
            MAX(COALESCE(bid, 0), COALESCE(last_price, 0)) as max_exit
        FROM flow_options_scans
        WHERE contract_hash = ?
            AND trade_date IN ({placeholders})
        GROUP BY trade_date
        ORDER BY trade_date
    """, (contract_hash, *future_dates))

    results = cursor.fetchall()
    conn.close()

    return results

def analyze_training_period():
    """Main analysis function"""

    print("=" * 80)
    print("PHASE 2: IDENTIFY WINNERS IN TRAINING DATA")
    print("=" * 80)
    print()
    print(f"Training Period: {TRAINING_START} to {TRAINING_END}")
    print(f"Universe: B (Stock Options)")
    print(f"Criteria: ${MIN_ASK}-${MAX_ASK} ask, {MIN_DTE}-{MAX_DTE} DTE, bid>0, vega not null")
    print(f"Win Definition: Exit >= Entry Ask * 1.25 within 5 trading days")
    print()

    # Get all trading dates
    trading_dates = get_trading_dates()
    print(f"Trading dates in period: {len(trading_dates)}")
    print(f"Dates: {trading_dates[0]} to {trading_dates[-1]}")
    print()

    # Track results
    all_entries = []
    winners = []
    losers = []

    # Process each trading date
    for i, trade_date in enumerate(trading_dates, 1):
        print(f"Processing {trade_date} ({i}/{len(trading_dates)})...", end=' ')
        sys.stdout.flush()

        entries = get_entries_for_date(trade_date)
        print(f"{len(entries)} entries", end='')

        for entry in entries:
            contract_hash = entry['contract_hash']
            entry_ask = entry['ask']
            target_price = entry_ask * 1.25

            # Track exit opportunities
            exit_data = get_exit_opportunities(contract_hash, trade_date, trading_dates)

            # Find if target was hit
            hit_target = False
            days_to_target = None
            max_exit = 0

            for day_num, (exit_date, exit_price) in enumerate(exit_data, 1):
                max_exit = max(max_exit, exit_price)
                if not hit_target and exit_price >= target_price:
                    hit_target = True
                    days_to_target = day_num

            # Calculate actual return
            if max_exit > 0:
                actual_return = (max_exit - entry_ask) / entry_ask
            else:
                actual_return = -1.0  # No exit data = assume total loss

            # Store result
            result = {
                **entry,
                'entry_date': trade_date,
                'entry_ask': entry_ask,
                'target_price': target_price,
                'max_exit': max_exit,
                'actual_return': actual_return,
                'hit_target': hit_target,
                'days_to_target': days_to_target,
                'exit_scans': len(exit_data)
            }

            all_entries.append(result)

            if hit_target:
                winners.append(result)
            else:
                losers.append(result)

        print()

    # Calculate statistics
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    print(f"Total Entries: {len(all_entries)}")
    print(f"Winners: {len(winners)} ({100 * len(winners) / len(all_entries):.1f}%)")
    print(f"Losers: {len(losers)} ({100 * len(losers) / len(all_entries):.1f}%)")
    print()

    if winners:
        avg_winner_return = sum(w['actual_return'] for w in winners) / len(winners)
        avg_days_to_target = sum(w['days_to_target'] for w in winners) / len(winners)
        print(f"Average Winner Return: {avg_winner_return:.1%}")
        print(f"Average Days to Target: {avg_days_to_target:.1f}")
        print()

    if losers:
        avg_loser_return = sum(l['actual_return'] for l in losers) / len(losers)
        print(f"Average Loser Return: {avg_loser_return:.1%}")
        print()

    # Calculate EV
    if all_entries:
        ev = sum(e['actual_return'] for e in all_entries) / len(all_entries)
        print(f"Expected Value (Baseline): {ev:.1%}")
        print()

    # Check if we have enough winners to proceed
    if len(winners) < 15:
        print("WARNING: Fewer than 15 winners found. May not be enough to find patterns.")
        print("Consider expanding universe or adjusting criteria.")
    else:
        print(f"SUCCESS: Found {len(winners)} winners - sufficient for pattern discovery (Phase 3)")

    print()

    # Write results to file
    output_file = 'docs/cheap_options_phase2_results.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("PHASE 2 RESULTS: TRAINING WINNERS\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total Entries: {len(all_entries)}\n")
        f.write(f"Winners: {len(winners)}\n")
        f.write(f"Losers: {len(losers)}\n\n")

        f.write("WINNERS:\n")
        f.write("-" * 80 + "\n")
        for w in winners:
            f.write(f"{w['entry_date']} | {w['symbol']:6s} | {w['contract_hash']:30s} | "
                   f"Entry: ${w['entry_ask']:.2f} | Exit: ${w['max_exit']:.2f} | "
                   f"Return: {w['actual_return']:6.1%} | Days: {w['days_to_target']}\n")

    print(f"Detailed results written to: {output_file}")
    print()

    return all_entries, winners, losers

if __name__ == '__main__':
    analyze_training_period()
