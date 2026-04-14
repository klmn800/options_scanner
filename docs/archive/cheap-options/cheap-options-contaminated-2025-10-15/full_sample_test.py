#!/usr/bin/env python3
"""
Full sample test of optimal filters - all 78 opportunities
"""

import sqlite3

DB_PATH = "../data/datalake_query.db"

def test_full_sample(filters, description):
    """Test all opportunities matching filters"""
    conn = sqlite3.connect(DB_PATH)

    # Build WHERE clause
    conditions = [
        f"ask >= {filters['ask_min']} AND ask <= {filters['ask_max']}",
        f"dte >= {filters['dte_min']} AND dte <= {filters['dte_max']}",
        "trade_date >= '2025-09-01'",
        "symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')",
        "bid > 0 AND ask > 0",
        "vega IS NOT NULL",
        "delta IS NOT NULL"
    ]

    if 'vega_min' in filters:
        conditions.append(f"vega >= {filters['vega_min']}")
    if 'vega_max' in filters:
        conditions.append(f"vega <= {filters['vega_max']}")

    where_clause = " AND ".join(conditions)

    # Get all entries
    query = f"""
    SELECT
        contract_hash,
        trade_date,
        symbol,
        strike,
        option_type,
        dte,
        delta,
        vega,
        (SELECT ask FROM flow_options_scans f2
         WHERE f2.contract_hash = f1.contract_hash
         AND f2.trade_date = f1.trade_date
         ORDER BY scan_timestamp LIMIT 1) as entry_ask
    FROM flow_options_scans f1
    WHERE {where_clause}
    GROUP BY contract_hash, trade_date
    """

    cursor = conn.cursor()
    cursor.execute(query)
    entries = cursor.fetchall()

    print(f"\n{'='*70}")
    print(f"TEST: {description}")
    print(f"{'='*70}")
    print(f"Total opportunities found: {len(entries)}")

    # Check ALL of them
    winners = 0
    losers = 0
    winner_returns = []
    loser_returns = []

    for i, entry in enumerate(entries):
        contract_hash, trade_date, symbol, strike, opt_type, dte, delta, vega, entry_ask = entry

        if entry_ask is None or entry_ask == 0:
            continue

        # Check outcome
        check_query = """
        SELECT MAX(CASE WHEN bid > last_price THEN bid ELSE COALESCE(last_price, bid) END) as max_sellable
        FROM flow_options_scans
        WHERE contract_hash = ?
          AND trade_date > ?
          AND trade_date <= date(?, '+5 days')
        """

        cursor.execute(check_query, (contract_hash, trade_date, trade_date))
        result = cursor.fetchone()

        if result and result[0]:
            max_sellable = result[0]
            target = entry_ask * 1.25
            gross_return = ((max_sellable - entry_ask) / entry_ask) * 100

            if max_sellable >= target:
                winners += 1
                winner_returns.append(gross_return)
                if i < 10:  # Show first 10 winners
                    print(f"  WIN  {i+1:3}: {symbol:6} ${strike:6.1f} {opt_type:4} | Entry=${entry_ask:.2f} Max=${max_sellable:.2f} | +{gross_return:.1f}%")
            else:
                losers += 1
                loser_returns.append(gross_return)
                if i < 10 and len([l for l in loser_returns]) <= 3:  # Show first 3 losers
                    print(f"  LOSS {i+1:3}: {symbol:6} ${strike:6.1f} {opt_type:4} | Entry=${entry_ask:.2f} Max=${max_sellable:.2f} | {gross_return:.1f}%")

    total = winners + losers
    win_rate = (winners / total * 100) if total > 0 else 0

    avg_winner = sum(winner_returns) / len(winner_returns) if winner_returns else 0
    avg_loser = sum(loser_returns) / len(loser_returns) if loser_returns else 0
    avg_overall = (sum(winner_returns) + sum(loser_returns)) / total if total > 0 else 0

    ev = (winners / total * avg_winner / 100) + (losers / total * avg_loser / 100) if total > 0 else 0

    print(f"\n{'='*70}")
    print(f"RESULTS:")
    print(f"  Total Tested: {total}")
    print(f"  Winners: {winners} ({win_rate:.2f}%)")
    print(f"  Losers: {losers}")
    print(f"  Avg Winner Return: {avg_winner:.2f}%")
    print(f"  Avg Loser Return: {avg_loser:.2f}%")
    print(f"  Avg Overall Return: {avg_overall:.2f}%")
    print(f"  Expected Value: {ev*100:.2f}%")
    print(f"{'='*70}\n")

    conn.close()

    return {
        'total': total,
        'winners': winners,
        'win_rate': win_rate,
        'avg_winner': avg_winner,
        'avg_loser': avg_loser,
        'ev': ev * 100
    }

def main():
    print("="*70)
    print("FULL SAMPLE TESTING - All Opportunities")
    print("="*70)

    # Test 1: Original optimal (ask $0.03-0.05, DTE 20-28, vega 0.015-0.035)
    test_full_sample({
        'ask_min': 0.03,
        'ask_max': 0.05,
        'dte_min': 20,
        'dte_max': 28,
        'vega_min': 0.015,
        'vega_max': 0.035
    }, "Original Optimal: ask $0.03-0.05, DTE 20-28, vega 0.015-0.035")

    # Test 2: Stricter (ask $0.03-0.04, DTE 20-25, vega 0.01-0.03)
    test_full_sample({
        'ask_min': 0.03,
        'ask_max': 0.04,
        'dte_min': 20,
        'dte_max': 25,
        'vega_min': 0.01,
        'vega_max': 0.03
    }, "Data-Pure: ask $0.03-0.04, DTE 20-25, vega 0.01-0.03")

    # Test 3: Moderate (ask $0.03-0.05, DTE 20-25, vega 0.01-0.03)
    test_full_sample({
        'ask_min': 0.03,
        'ask_max': 0.05,
        'dte_min': 20,
        'dte_max': 25,
        'vega_min': 0.01,
        'vega_max': 0.03
    }, "Balanced: ask $0.03-0.05, DTE 20-25, vega 0.01-0.03")

if __name__ == "__main__":
    main()
