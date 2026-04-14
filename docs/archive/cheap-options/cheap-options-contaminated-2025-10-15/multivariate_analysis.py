#!/usr/bin/env python3
"""
Phase 4: Multi-variate Analysis
Examine how parameters interact and what separates winners from losers
"""

import sqlite3
from collections import defaultdict

DB_PATH = "../data/datalake_query.db"

def analyze_winners_vs_losers():
    """Compare characteristics of winners vs losers in optimal filter"""
    conn = sqlite3.connect(DB_PATH)

    # Use optimal filter
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
        gamma,
        theta,
        iv,
        bid,
        ask,
        last_price,
        underlying_price,
        scan_timestamp,
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

    print(f"Analyzing {len(entries)} opportunities within optimal filter...")
    print()

    winners = []
    losers = []

    for entry in entries:
        (contract_hash, trade_date, symbol, strike, opt_type, dte, delta, vega,
         gamma, theta, iv, bid, ask, last, underlying, scan_time, entry_ask) = entry

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
                'symbol': symbol,
                'strike': strike,
                'option_type': opt_type,
                'dte': dte,
                'delta': abs(delta) if delta else None,
                'vega': vega,
                'gamma': gamma,
                'theta': theta,
                'iv': iv,
                'entry_ask': entry_ask,
                'underlying': underlying,
                'return': gross_return
            }

            if max_sellable >= target:
                winners.append(record)
            else:
                losers.append(record)

    conn.close()

    print(f"Winners: {len(winners)}")
    print(f"Losers: {len(losers)}")
    print(f"Win Rate: {len(winners)/(len(winners)+len(losers))*100:.2f}%")
    print()

    return winners, losers


def compare_distributions(winners, losers):
    """Compare parameter distributions between winners and losers"""

    def safe_avg(values):
        clean = [v for v in values if v is not None]
        return sum(clean) / len(clean) if clean else None

    def safe_median(values):
        clean = sorted([v for v in values if v is not None])
        if not clean:
            return None
        n = len(clean)
        if n % 2 == 0:
            return (clean[n//2-1] + clean[n//2]) / 2
        return clean[n//2]

    print("="*70)
    print("WINNER vs LOSER CHARACTERISTICS")
    print("="*70)
    print()

    # Delta comparison
    winner_deltas = [w['delta'] for w in winners if w['delta']]
    loser_deltas = [l['delta'] for l in losers if l['delta']]
    print(f"DELTA (absolute value):")
    print(f"  Winners: avg={safe_avg(winner_deltas):.4f}, median={safe_median(winner_deltas):.4f}")
    print(f"  Losers:  avg={safe_avg(loser_deltas):.4f}, median={safe_median(loser_deltas):.4f}")
    print()

    # Vega comparison
    winner_vegas = [w['vega'] for w in winners]
    loser_vegas = [l['vega'] for l in losers]
    print(f"VEGA:")
    print(f"  Winners: avg={safe_avg(winner_vegas):.4f}, median={safe_median(winner_vegas):.4f}")
    print(f"  Losers:  avg={safe_avg(loser_vegas):.4f}, median={safe_median(loser_vegas):.4f}")
    print()

    # DTE comparison
    winner_dte = [w['dte'] for w in winners]
    loser_dte = [l['dte'] for l in losers]
    print(f"DTE:")
    print(f"  Winners: avg={safe_avg(winner_dte):.1f}, median={safe_median(winner_dte):.1f}")
    print(f"  Losers:  avg={safe_avg(loser_dte):.1f}, median={safe_median(loser_dte):.1f}")
    print()

    # IV comparison
    winner_iv = [w['iv'] for w in winners if w['iv']]
    loser_iv = [l['iv'] for l in losers if l['iv']]
    print(f"IMPLIED VOLATILITY:")
    print(f"  Winners: avg={safe_avg(winner_iv):.4f}, median={safe_median(winner_iv):.4f}")
    print(f"  Losers:  avg={safe_avg(loser_iv):.4f}, median={safe_median(loser_iv):.4f}")
    print()

    # Gamma comparison
    winner_gamma = [w['gamma'] for w in winners if w['gamma']]
    loser_gamma = [l['gamma'] for l in losers if l['gamma']]
    print(f"GAMMA:")
    print(f"  Winners: avg={safe_avg(winner_gamma):.4f}, median={safe_median(winner_gamma):.4f}")
    print(f"  Losers:  avg={safe_avg(loser_gamma):.4f}, median={safe_median(loser_gamma):.4f}")
    print()

    # Entry price comparison
    winner_entry = [w['entry_ask'] for w in winners]
    loser_entry = [l['entry_ask'] for l in losers]
    print(f"ENTRY ASK:")
    print(f"  Winners: avg=${safe_avg(winner_entry):.3f}, median=${safe_median(winner_entry):.3f}")
    print(f"  Losers:  avg=${safe_avg(loser_entry):.3f}, median=${safe_median(loser_entry):.3f}")
    print()

    # Option type breakdown (handle both lowercase and uppercase)
    winner_calls = sum(1 for w in winners if w.get('option_type', '').upper() == 'CALL')
    winner_puts = sum(1 for w in winners if w.get('option_type', '').upper() == 'PUT')
    loser_calls = sum(1 for l in losers if l.get('option_type', '').upper() == 'CALL')
    loser_puts = sum(1 for l in losers if l.get('option_type', '').upper() == 'PUT')

    winner_total = len(winners)
    loser_total = len(losers)

    print(f"OPTION TYPE:")
    if winner_total > 0:
        print(f"  Winners: {winner_calls} calls ({winner_calls/winner_total*100:.1f}%), {winner_puts} puts ({winner_puts/winner_total*100:.1f}%)")
    if loser_total > 0:
        print(f"  Losers:  {loser_calls} calls ({loser_calls/loser_total*100:.1f}%), {loser_puts} puts ({loser_puts/loser_total*100:.1f}%)")
    print()


def analyze_moneyness(winners, losers):
    """Analyze performance by moneyness (delta buckets)"""

    print("="*70)
    print("PERFORMANCE BY MONEYNESS (Delta)")
    print("="*70)
    print()

    # Bucket by delta
    buckets = {
        'Deep OTM (0-0.15)': (0, 0.15),
        'OTM (0.15-0.30)': (0.15, 0.30),
        'Near ATM (0.30-0.45)': (0.30, 0.45),
        'ATM+ (0.45+)': (0.45, 1.0)
    }

    for bucket_name, (min_delta, max_delta) in buckets.items():
        bucket_winners = [w for w in winners if w['delta'] and min_delta <= w['delta'] < max_delta]
        bucket_losers = [l for l in losers if l['delta'] and min_delta <= l['delta'] < max_delta]

        total = len(bucket_winners) + len(bucket_losers)
        if total == 0:
            continue

        win_rate = len(bucket_winners) / total * 100

        avg_winner_return = sum(w['return'] for w in bucket_winners) / len(bucket_winners) if bucket_winners else 0
        avg_loser_return = sum(l['return'] for l in bucket_losers) / len(bucket_losers) if bucket_losers else 0

        print(f"{bucket_name}:")
        print(f"  Total: {total} opportunities")
        print(f"  Win Rate: {win_rate:.2f}% ({len(bucket_winners)}/{total})")
        print(f"  Avg Winner Return: {avg_winner_return:+.2f}%")
        print(f"  Avg Loser Return: {avg_loser_return:+.2f}%")
        print()


def analyze_iv_environment(winners, losers):
    """Analyze performance by IV levels"""

    print("="*70)
    print("PERFORMANCE BY IV ENVIRONMENT")
    print("="*70)
    print()

    # Bucket by IV
    buckets = {
        'Low IV (0-0.50)': (0, 0.50),
        'Moderate IV (0.50-0.80)': (0.50, 0.80),
        'High IV (0.80-1.20)': (0.80, 1.20),
        'Very High IV (1.20+)': (1.20, 10.0)
    }

    for bucket_name, (min_iv, max_iv) in buckets.items():
        bucket_winners = [w for w in winners if w['iv'] and min_iv <= w['iv'] < max_iv]
        bucket_losers = [l for l in losers if l['iv'] and min_iv <= l['iv'] < max_iv]

        total = len(bucket_winners) + len(bucket_losers)
        if total == 0:
            continue

        win_rate = len(bucket_winners) / total * 100

        avg_winner_return = sum(w['return'] for w in bucket_winners) / len(bucket_winners) if bucket_winners else 0
        avg_loser_return = sum(l['return'] for l in bucket_losers) / len(bucket_losers) if bucket_losers else 0

        print(f"{bucket_name}:")
        print(f"  Total: {total} opportunities")
        print(f"  Win Rate: {win_rate:.2f}% ({len(bucket_winners)}/{total})")
        print(f"  Avg Winner Return: {avg_winner_return:+.2f}%")
        print(f"  Avg Loser Return: {avg_loser_return:+.2f}%")
        print()


def analyze_top_symbols(winners, losers):
    """Analyze which symbols appear most in winners vs losers"""

    print("="*70)
    print("TOP SYMBOLS")
    print("="*70)
    print()

    # Count by symbol
    winner_symbols = defaultdict(int)
    loser_symbols = defaultdict(int)

    for w in winners:
        winner_symbols[w['symbol']] += 1

    for l in losers:
        loser_symbols[l['symbol']] += 1

    # Combine and calculate win rates
    all_symbols = set(list(winner_symbols.keys()) + list(loser_symbols.keys()))
    symbol_stats = []

    for symbol in all_symbols:
        wins = winner_symbols[symbol]
        losses = loser_symbols[symbol]
        total = wins + losses
        win_rate = wins / total * 100 if total > 0 else 0
        symbol_stats.append((symbol, wins, losses, total, win_rate))

    # Sort by total opportunities
    symbol_stats.sort(key=lambda x: x[3], reverse=True)

    print("Top 15 Symbols by Opportunity Count:")
    print(f"{'Symbol':<8} {'Wins':<6} {'Losses':<8} {'Total':<7} {'Win Rate':<10}")
    print("-" * 60)

    for i, (symbol, wins, losses, total, win_rate) in enumerate(symbol_stats[:15]):
        print(f"{symbol:<8} {wins:<6} {losses:<8} {total:<7} {win_rate:>6.2f}%")

    print()
    print("Top 10 Symbols by Win Rate (min 3 opportunities):")
    print(f"{'Symbol':<8} {'Wins':<6} {'Losses':<8} {'Total':<7} {'Win Rate':<10}")
    print("-" * 60)

    high_win_rate = [s for s in symbol_stats if s[3] >= 3]
    high_win_rate.sort(key=lambda x: x[4], reverse=True)

    for i, (symbol, wins, losses, total, win_rate) in enumerate(high_win_rate[:10]):
        print(f"{symbol:<8} {wins:<6} {losses:<8} {total:<7} {win_rate:>6.2f}%")

    print()


def main():
    print("="*70)
    print("PHASE 4: MULTI-VARIATE ANALYSIS")
    print("="*70)
    print()
    print("Analyzing winners vs losers within optimal filter:")
    print("  Ask: $0.03-0.05")
    print("  DTE: 20-28 days")
    print("  Vega: 0.015-0.035")
    print()

    # Get winners and losers
    winners, losers = analyze_winners_vs_losers()

    # Run analyses
    compare_distributions(winners, losers)
    analyze_moneyness(winners, losers)
    analyze_iv_environment(winners, losers)
    analyze_top_symbols(winners, losers)

    print("="*70)
    print("PHASE 4 COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
