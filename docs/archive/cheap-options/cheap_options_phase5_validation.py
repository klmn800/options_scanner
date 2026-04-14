"""
Phase 5: In-Sample Validation

Test Hypothesis #1 on training data to ensure it captures winners
and calculate in-sample performance metrics.
"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

TRAINING_START = '2025-08-18'
TRAINING_END = '2025-09-30'
UNIVERSE_B_ETF_LIST = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP', 'VIX']

# Hypothesis #1 Criteria
H1_MIN_ASK = 0.08
H1_MAX_ASK = 0.10
H1_MIN_DTE = 21
H1_MAX_DTE = 40
H1_OPTION_TYPE = 'call'
H1_MAX_DELTA = 0.15

def get_db_connection():
    return sqlite3.connect('data/datalake_query.db')

def get_trading_dates():
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

def test_hypothesis():
    """Test H1 on training data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    trading_dates = get_trading_dates()

    entries = []

    print("Testing Hypothesis #1 on training period...")
    print()
    print("CRITERIA:")
    print(f"  Price: ${H1_MIN_ASK}-${H1_MAX_ASK}")
    print(f"  DTE: {H1_MIN_DTE}-{H1_MAX_DTE} days")
    print(f"  Type: {H1_OPTION_TYPE}s only")
    print(f"  Delta: < {H1_MAX_DELTA}")
    print()

    for trade_date in trading_dates:
        cursor.execute("""
            SELECT
                contract_hash, symbol, strike, expiration_date, option_type,
                dte, ask, bid, last_price, iv, delta, gamma, theta, vega,
                underlying_price, MIN(scan_timestamp) as entry_timestamp
            FROM flow_options_scans
            WHERE trade_date = ?
                AND ask >= ? AND ask <= ?
                AND dte >= ? AND dte <= ?
                AND option_type = ?
                AND ABS(delta) < ?
                AND bid > 0
                AND vega IS NOT NULL
                AND symbol NOT IN ({})
            GROUP BY contract_hash
        """.format(','.join(['?'] * len(UNIVERSE_B_ETF_LIST))),
        (trade_date, H1_MIN_ASK, H1_MAX_ASK, H1_MIN_DTE, H1_MAX_DTE,
         H1_OPTION_TYPE, H1_MAX_DELTA, *UNIVERSE_B_ETF_LIST))

        for entry in cursor.fetchall():
            contract_hash = entry[0]
            entry_ask = entry[6]
            target_price = entry_ask * 1.25

            # Get next 5 trading days
            entry_idx = trading_dates.index(trade_date)
            future_dates = trading_dates[entry_idx + 1 : entry_idx + 6]

            if not future_dates:
                continue

            # Check for exits
            placeholders = ','.join(['?'] * len(future_dates))
            cursor.execute(f"""
                SELECT MAX(COALESCE(bid, 0), COALESCE(last_price, 0)) as max_exit
                FROM flow_options_scans
                WHERE contract_hash = ?
                    AND trade_date IN ({placeholders})
            """, (contract_hash, *future_dates))

            result = cursor.fetchone()
            max_exit = result[0] if result else 0

            # Determine outcome
            hit_target = max_exit >= target_price
            actual_return = (max_exit - entry_ask) / entry_ask if max_exit > 0 else -1.0

            entries.append({
                'trade_date': trade_date,
                'symbol': entry[1],
                'contract_hash': contract_hash,
                'entry_ask': entry_ask,
                'max_exit': max_exit,
                'hit_target': hit_target,
                'return': actual_return
            })

    conn.close()

    # Calculate metrics
    total_entries = len(entries)
    winners = [e for e in entries if e['hit_target']]
    losers = [e for e in entries if not e['hit_target']]

    win_rate = 100 * len(winners) / total_entries if total_entries > 0 else 0
    avg_winner_return = sum(w['return'] for w in winners) / len(winners) if winners else 0
    avg_loser_return = sum(l['return'] for l in losers) / len(losers) if losers else 0
    ev = sum(e['return'] for e in entries) / total_entries if total_entries > 0 else 0

    # Print results
    print("=" * 80)
    print("HYPOTHESIS #1 IN-SAMPLE RESULTS (Training Period)")
    print("=" * 80)
    print()
    print(f"Total Entries: {total_entries}")
    print(f"Winners: {len(winners)} ({win_rate:.1f}%)")
    print(f"Losers: {len(losers)} ({100-win_rate:.1f}%)")
    print()
    print(f"Average Winner Return: {avg_winner_return:.1%}")
    print(f"Average Loser Return: {avg_loser_return:.1%}")
    print(f"Expected Value: {ev:.1%}")
    print()

    # Success criteria check
    print("SUCCESS CRITERIA:")
    print("-" * 80)

    success = True

    if total_entries >= 10 and total_entries <= 100:
        print(f"[PASS] Entry count: {total_entries} (target 10-100)")
    else:
        print(f"[FAIL] Entry count: {total_entries} (target 10-100)")
        success = False

    if win_rate >= 30:
        print(f"[PASS] Win rate: {win_rate:.1f}% (target >30%)")
    else:
        print(f"[FAIL] Win rate: {win_rate:.1f}% (target >30%)")
        success = False

    if ev >= 5:
        print(f"[PASS] Expected value: {ev:.1f}% (target >5%)")
    else:
        print(f"[FAIL] Expected value: {ev:.1f}% (target >5%)")
        success = False

    print()

    if success:
        print("RESULT: HYPOTHESIS PASSES in-sample validation")
        print("Ready for Phase 6 holdout test")
    else:
        print("RESULT: HYPOTHESIS FAILS in-sample validation")
        print("Consider refining criteria or testing alternate hypothesis")

    print()

    # Save detailed results
    with open('docs/cheap_options_phase5_results.txt', 'w', encoding='utf-8') as f:
        f.write("PHASE 5: IN-SAMPLE VALIDATION RESULTS\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total Entries: {total_entries}\n")
        f.write(f"Winners: {len(winners)} ({win_rate:.1f}%)\n")
        f.write(f"Losers: {len(losers)}\n")
        f.write(f"Average Winner: {avg_winner_return:.1%}\n")
        f.write(f"Average Loser: {avg_loser_return:.1%}\n")
        f.write(f"Expected Value: {ev:.1%}\n")
        f.write(f"\nStatus: {'PASS' if success else 'FAIL'}\n")

    print("Results saved to: docs/cheap_options_phase5_results.txt")

    return success, {
        'total_entries': total_entries,
        'win_rate': win_rate,
        'ev': ev,
        'avg_winner': avg_winner_return,
        'avg_loser': avg_loser_return
    }

if __name__ == '__main__':
    success, metrics = test_hypothesis()
