#!/usr/bin/env python3
"""
Test combined filters to see if we can achieve 40-50%+ win rate
"""

import sqlite3

DB_PATH = "../data/datalake_query.db"

def test_filter_combination(filters):
    """Test a specific filter combination"""
    conn = sqlite3.connect(DB_PATH)

    # Build WHERE clause from filters
    conditions = [
        "ask >= 0.03 AND ask <= 0.10",
        "dte >= 20 AND dte <= 60",
        "trade_date >= '2025-09-01'",
        "symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')",
        "bid > 0 AND ask > 0",
        "vega IS NOT NULL",
        "delta IS NOT NULL"
    ]

    # Add custom filters
    if 'ask_min' in filters and 'ask_max' in filters:
        conditions[0] = f"ask >= {filters['ask_min']} AND ask <= {filters['ask_max']}"

    if 'dte_min' in filters and 'dte_max' in filters:
        conditions[1] = f"dte >= {filters['dte_min']} AND dte <= {filters['dte_max']}"

    if 'vega_min' in filters:
        conditions.append(f"vega >= {filters['vega_min']}")

    if 'vega_max' in filters:
        conditions.append(f"vega <= {filters['vega_max']}")

    if 'option_type' in filters:
        conditions.append(f"option_type = '{filters['option_type']}'")

    where_clause = " AND ".join(conditions)

    # Get entries
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
        iv,
        MIN(scan_timestamp) as entry_time,
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

    # Sample for speed (every 5th entry)
    sampled = entries[::5]

    # Check outcomes
    winners = 0
    total = 0

    for entry in sampled:
        contract_hash, trade_date, symbol, strike, opt_type, dte, delta, vega, iv, entry_time, entry_ask = entry

        if entry_ask is None or entry_ask == 0:
            continue

        # Check if won
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

            if max_sellable >= target:
                winners += 1

        total += 1

    conn.close()

    win_rate = (winners / total * 100) if total > 0 else 0
    return {
        'total_entries': len(entries),
        'sampled': total,
        'winners': winners,
        'win_rate': win_rate
    }

def main():
    print("=== Testing Combined Filter Strategies ===\n")

    # Test 1: Optimal filters based on Phase 3
    print("Test 1: OPTIMAL FILTERS (Cheap + Short DTE + Vega)")
    print("-" * 60)
    result = test_filter_combination({
        'ask_min': 0.03,
        'ask_max': 0.05,
        'dte_min': 20,
        'dte_max': 28,
        'vega_min': 0.015,
        'vega_max': 0.035
    })
    print(f"Total opportunities: {result['total_entries']}")
    print(f"Sampled: {result['sampled']}")
    print(f"Winners: {result['winners']}")
    print(f"Win Rate: {result['win_rate']:.2f}%")
    print()

    # Test 2: Ultra-cheap only
    print("Test 2: ULTRA-CHEAP ($0.03-0.04)")
    print("-" * 60)
    result = test_filter_combination({
        'ask_min': 0.03,
        'ask_max': 0.04,
        'dte_min': 20,
        'dte_max': 28
    })
    print(f"Total opportunities: {result['total_entries']}")
    print(f"Sampled: {result['sampled']}")
    print(f"Winners: {result['winners']}")
    print(f"Win Rate: {result['win_rate']:.2f}%")
    print()

    # Test 3: Moderate cheap with best DTE
    print("Test 3: MODERATE CHEAP ($0.03-0.06) + Best DTE (20-25)")
    print("-" * 60)
    result = test_filter_combination({
        'ask_min': 0.03,
        'ask_max': 0.06,
        'dte_min': 20,
        'dte_max': 25,
        'vega_min': 0.015
    })
    print(f"Total opportunities: {result['total_entries']}")
    print(f"Sampled: {result['sampled']}")
    print(f"Winners: {result['winners']}")
    print(f"Win Rate: {result['win_rate']:.2f}%")
    print()

    # Test 4: Calls only with optimal params
    print("Test 4: CALLS ONLY + Optimal Params")
    print("-" * 60)
    result = test_filter_combination({
        'ask_min': 0.03,
        'ask_max': 0.05,
        'dte_min': 20,
        'dte_max': 28,
        'vega_min': 0.015,
        'option_type': 'CALL'
    })
    print(f"Total opportunities: {result['total_entries']}")
    print(f"Sampled: {result['sampled']}")
    print(f"Winners: {result['winners']}")
    print(f"Win Rate: {result['win_rate']:.2f}%")
    print()

    # Test 5: Baseline (no extra filters, just base criteria)
    print("Test 5: BASELINE (for comparison)")
    print("-" * 60)
    result = test_filter_combination({})
    print(f"Total opportunities: {result['total_entries']}")
    print(f"Sampled: {result['sampled']}")
    print(f"Winners: {result['winners']}")
    print(f"Win Rate: {result['win_rate']:.2f}%")
    print()

    print("=== Testing Complete ===")

if __name__ == "__main__":
    main()
