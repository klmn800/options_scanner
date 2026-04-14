#!/usr/bin/env python3
"""
Verify original methodology on full sample
"""

import sqlite3

DB_PATH = "../data/datalake_query.db"

def main():
    conn = sqlite3.connect(DB_PATH)

    # EXACT original filters
    query = """
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
    WHERE ask >= 0.03 AND ask <= 0.05
      AND dte >= 20 AND dte <= 28
      AND vega >= 0.015 AND vega <= 0.035
      AND trade_date >= '2025-09-01'
      AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')
      AND bid > 0 AND ask > 0
      AND vega IS NOT NULL
      AND delta IS NOT NULL
    GROUP BY contract_hash, trade_date
    """

    cursor = conn.cursor()
    cursor.execute(query)
    entries = cursor.fetchall()

    print(f"Total opportunities: {len(entries)}")

    winners = 0
    total = 0

    for entry in entries:
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

            if max_sellable >= target:
                winners += 1

        total += 1

    conn.close()

    win_rate = (winners / total * 100) if total > 0 else 0

    print(f"\nRESULTS:")
    print(f"Total tested: {total}")
    print(f"Winners: {winners}")
    print(f"Win rate: {win_rate:.2f}%")

if __name__ == "__main__":
    main()
