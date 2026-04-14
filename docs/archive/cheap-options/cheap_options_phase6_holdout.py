"""
Phase 6: Holdout Test

Apply Hypothesis #1 to Oct 1-15 holdout data WITHOUT modification.
This is the ONE SHOT test - no iteration allowed.
"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

HOLDOUT_START = '2025-10-01'
HOLDOUT_END = '2025-10-15'
UNIVERSE_B_ETF_LIST = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP', 'VIX']

# Hypothesis #1 Criteria (LOCKED - no changes from Phase 5)
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
    """, (HOLDOUT_START, HOLDOUT_END))
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def test_holdout():
    """Test H1 on holdout period - ONE SHOT, NO ITERATION"""
    conn = get_db_connection()
    cursor = conn.cursor()
    trading_dates = get_trading_dates()

    entries = []

    print("=" * 80)
    print("PHASE 6: HOLDOUT TEST (Oct 1-15, 2025)")
    print("=" * 80)
    print()
    print("HYPOTHESIS #1 CRITERIA (LOCKED):")
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

    # Calculate holdout metrics
    total_entries = len(entries)
    winners = [e for e in entries if e['hit_target']]
    losers = [e for e in entries if not e['hit_target']]

    win_rate = 100 * len(winners) / total_entries if total_entries > 0 else 0
    avg_winner_return = sum(w['return'] for w in winners) / len(winners) if winners else 0
    avg_loser_return = sum(l['return'] for l in losers) / len(losers) if losers else 0
    ev = sum(e['return'] for e in entries) / total_entries if total_entries > 0 else 0

    # Print results
    print("=" * 80)
    print("HOLDOUT RESULTS (Oct 1-15)")
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

    # Compare to training
    print("=" * 80)
    print("COMPARISON TO TRAINING")
    print("=" * 80)
    print()
    training_win_rate = 11.3
    training_ev = -10.9
    print(f"Win Rate:       Training {training_win_rate:.1f}% | Holdout {win_rate:.1f}% | Diff {win_rate - training_win_rate:+.1f}pp")
    print(f"Expected Value: Training {training_ev:.1f}% | Holdout {ev:.1f}% | Diff {ev - training_ev:+.1f}pp")
    print()

    # Validation outcome
    print("=" * 80)
    print("VALIDATION OUTCOME")
    print("=" * 80)
    print()

    if ev > 0 and abs(win_rate - training_win_rate) <= 10:
        print("RESULT: PASS - Strategy validated")
        print("- Holdout EV > 0")
        print("- Win rate within 10pp of training")
        outcome = "PASS"
    elif ev > 0:
        print("RESULT: MARGINAL - Possible edge but weak")
        print("- Holdout EV > 0 but performance diverged from training")
        outcome = "MARGINAL"
    else:
        print("RESULT: FAIL - No systematic edge")
        print("- Holdout EV <= 0")
        print("- Hypothesis rejected")
        outcome = "FAIL"

    print()

    # Save results
    with open('docs/cheap_options_phase6_holdout.txt', 'w', encoding='utf-8') as f:
        f.write("PHASE 6: HOLDOUT TEST RESULTS\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Holdout Period: {HOLDOUT_START} to {HOLDOUT_END}\n\n")
        f.write(f"Total Entries: {total_entries}\n")
        f.write(f"Winners: {len(winners)} ({win_rate:.1f}%)\n")
        f.write(f"Losers: {len(losers)}\n")
        f.write(f"Average Winner: {avg_winner_return:.1%}\n")
        f.write(f"Average Loser: {avg_loser_return:.1%}\n")
        f.write(f"Expected Value: {ev:.1%}\n\n")
        f.write(f"Comparison to Training:\n")
        f.write(f"  Win Rate: Training {training_win_rate:.1f}% | Holdout {win_rate:.1f}%\n")
        f.write(f"  EV: Training {training_ev:.1f}% | Holdout {ev:.1f}%\n\n")
        f.write(f"Outcome: {outcome}\n")

    print("Results saved to: docs/cheap_options_phase6_holdout.txt")
    print()

    return outcome, {
        'total_entries': total_entries,
        'win_rate': win_rate,
        'ev': ev,
        'avg_winner': avg_winner_return,
        'avg_loser': avg_loser_return
    }

if __name__ == '__main__':
    outcome, metrics = test_holdout()
