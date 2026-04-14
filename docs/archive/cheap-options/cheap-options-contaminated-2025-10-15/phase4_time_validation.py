#!/usr/bin/env python3
"""
Phase 4 Extension: Validate findings across time periods
Check if win rates are stable or trending over Sept-Oct period
"""

import sqlite3
from datetime import datetime

DB_PATH = "../data/datalake_query.db"

def analyze_by_time_period():
    """Break optimal filter results into time periods"""
    conn = sqlite3.connect(DB_PATH)

    # Get all opportunities with dates
    query = """
    SELECT
        contract_hash,
        trade_date,
        symbol,
        strike,
        option_type,
        dte,
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
    ORDER BY trade_date
    """

    cursor = conn.cursor()
    cursor.execute(query)
    entries = cursor.fetchall()

    print("="*70)
    print("TIME PERIOD VALIDATION")
    print("="*70)
    print()

    # Group by time periods
    periods = {
        'Early Sept (9/1-9/15)': ('2025-09-01', '2025-09-15'),
        'Late Sept (9/16-9/30)': ('2025-09-16', '2025-09-30'),
        'Early Oct (10/1-10/15)': ('2025-10-01', '2025-10-15')
    }

    for period_name, (start_date, end_date) in periods.items():
        period_entries = [e for e in entries if start_date <= e[1] <= end_date]

        print(f"{period_name}:")
        print(f"  Opportunities: {len(period_entries)}")

        if len(period_entries) == 0:
            print("  (No data)")
            print()
            continue

        # Check outcomes for this period
        winners = 0
        losers = 0

        for entry in period_entries:
            contract_hash, trade_date, symbol, strike, opt_type, dte, entry_ask = entry

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
                else:
                    losers += 1

        total = winners + losers
        win_rate = (winners / total * 100) if total > 0 else 0

        print(f"  Winners: {winners}")
        print(f"  Losers: {losers}")
        print(f"  Win Rate: {win_rate:.2f}%")
        print()

    conn.close()


def analyze_xli_vs_xlf():
    """Deep dive comparing XLI vs XLF performance"""
    conn = sqlite3.connect(DB_PATH)

    print("="*70)
    print("XLI vs XLF DETAILED COMPARISON")
    print("="*70)
    print()

    for symbol in ['XLI', 'XLF']:
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
            iv,
            underlying_price,
            (SELECT ask FROM flow_options_scans f2
             WHERE f2.contract_hash = f1.contract_hash
             AND f2.trade_date = f1.trade_date
             ORDER BY scan_timestamp LIMIT 1) as entry_ask
        FROM flow_options_scans f1
        WHERE symbol = ?
          AND ask >= 0.03 AND ask <= 0.05
          AND dte >= 20 AND dte <= 28
          AND vega >= 0.015 AND vega <= 0.035
          AND trade_date >= '2025-09-01'
          AND bid > 0 AND ask > 0
          AND vega IS NOT NULL
          AND delta IS NOT NULL
        GROUP BY contract_hash, trade_date
        """

        cursor = conn.cursor()
        cursor.execute(query, (symbol,))
        entries = cursor.fetchall()

        print(f"\n{symbol} ({symbol == 'XLI' and 'Industrial' or 'Financial'} ETF):")
        print(f"  Total opportunities: {len(entries)}")

        if len(entries) == 0:
            continue

        # Calculate stats
        winners = []
        losers = []

        for entry in entries:
            (contract_hash, trade_date, sym, strike, opt_type, dte, delta,
             vega, iv, underlying, entry_ask) = entry

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

                record = {
                    'delta': abs(delta) if delta else None,
                    'vega': vega,
                    'iv': iv,
                    'entry_ask': entry_ask,
                    'underlying': underlying,
                    'return': gross_return,
                    'strike': strike
                }

                if max_sellable >= target:
                    winners.append(record)
                else:
                    losers.append(record)

        total = len(winners) + len(losers)
        win_rate = (len(winners) / total * 100) if total > 0 else 0

        print(f"  Win Rate: {win_rate:.2f}% ({len(winners)}/{total})")

        if winners:
            avg_winner_return = sum(w['return'] for w in winners) / len(winners)
            avg_winner_delta = sum(w['delta'] for w in winners if w['delta']) / len([w for w in winners if w['delta']])
            avg_winner_iv = sum(w['iv'] for w in winners if w['iv']) / len([w for w in winners if w['iv']])
            avg_winner_price = sum(w['entry_ask'] for w in winners) / len(winners)

            print(f"  Winners:")
            print(f"    Avg return: {avg_winner_return:.2f}%")
            print(f"    Avg delta: {avg_winner_delta:.4f}")
            print(f"    Avg IV: {avg_winner_iv:.4f}")
            print(f"    Avg entry: ${avg_winner_price:.3f}")

        if losers:
            avg_loser_return = sum(l['return'] for l in losers) / len(losers)
            avg_loser_delta = sum(l['delta'] for l in losers if l['delta']) / len([l for l in losers if l['delta']])
            avg_loser_iv = sum(l['iv'] for l in losers if l['iv']) / len([l for l in losers if l['iv']])
            avg_loser_price = sum(l['entry_ask'] for l in losers) / len(losers)

            print(f"  Losers:")
            print(f"    Avg return: {avg_loser_return:.2f}%")
            print(f"    Avg delta: {avg_loser_delta:.4f}")
            print(f"    Avg IV: {avg_loser_iv:.4f}")
            print(f"    Avg entry: ${avg_loser_price:.3f}")

        # Strike distribution
        if entries:
            strikes = {}
            for entry in entries:
                strike = entry[3]
                strikes[strike] = strikes.get(strike, 0) + 1

            print(f"  Strike distribution:")
            for strike, count in sorted(strikes.items(), key=lambda x: -x[1])[:5]:
                print(f"    ${strike:.0f}: {count} opportunities")

    conn.close()


def check_opportunity_clustering():
    """Check if opportunities are evenly distributed or clustered"""
    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT
        trade_date,
        COUNT(DISTINCT contract_hash) as daily_count,
        GROUP_CONCAT(DISTINCT symbol) as symbols
    FROM (
        SELECT
            contract_hash,
            trade_date,
            symbol
        FROM flow_options_scans
        WHERE ask >= 0.03 AND ask <= 0.05
          AND dte >= 20 AND dte <= 28
          AND vega >= 0.015 AND vega <= 0.035
          AND trade_date >= '2025-09-01'
          AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')
          AND bid > 0 AND ask > 0
          AND vega IS NOT NULL
          AND delta IS NOT NULL
        GROUP BY contract_hash, trade_date
    )
    GROUP BY trade_date
    ORDER BY trade_date
    """

    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print("="*70)
    print("OPPORTUNITY CLUSTERING ANALYSIS")
    print("="*70)
    print()

    daily_counts = [row[1] for row in rows]
    avg_daily = sum(daily_counts) / len(daily_counts) if daily_counts else 0

    print(f"Daily Opportunity Distribution:")
    print(f"  Average per day: {avg_daily:.1f}")
    print(f"  Max: {max(daily_counts)} opportunities")
    print(f"  Min: {min(daily_counts)} opportunities")
    print()

    # Show days with unusually high/low counts
    print("Days with High Opportunity Count (>2):")
    for date, count, symbols in rows:
        if count > 2:
            symbol_list = symbols.split(',') if symbols else []
            print(f"  {date}: {count} opportunities ({', '.join(set(symbol_list))})")

    print()
    print("Days with Low/Zero Opportunities:")
    for date, count, symbols in rows:
        if count <= 1:
            symbol_list = symbols.split(',') if symbols else []
            print(f"  {date}: {count} opportunities ({', '.join(set(symbol_list))})")

    print()


def main():
    print("\n")
    print("="*70)
    print("PHASE 4 EXPANSION: TIME VALIDATION & DEEPER ANALYSIS")
    print("="*70)
    print("\n")

    analyze_by_time_period()
    analyze_xli_vs_xlf()
    check_opportunity_clustering()

    print("="*70)
    print("PHASE 4 EXPANSION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
