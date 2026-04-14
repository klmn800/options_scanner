"""
Phase 3: Pattern Discovery

Analyze the training winners directly from database to find common characteristics.
Look for 70%+ concentration in specific attributes.
"""

import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

TRAINING_START = '2025-08-18'
TRAINING_END = '2025-09-30'
MIN_ASK = 0.03
MAX_ASK = 0.10
MIN_DTE = 15
MAX_DTE = 60
UNIVERSE_B_ETF_LIST = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP', 'VIX']

def get_db_connection():
    return sqlite3.connect('data/datalake_query.db')

def get_trading_dates():
    """Get list of all trading dates"""
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

def find_all_winners():
    """Re-run winner identification to get full data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    trading_dates = get_trading_dates()

    winners = []

    for trade_date in trading_dates:
        # Get Universe B entries for this date
        cursor.execute("""
            SELECT
                contract_hash, symbol, strike, expiration_date, option_type,
                dte, ask, bid, last_price, iv, delta, gamma, theta, vega,
                underlying_price, volume, open_interest,
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

        entries = cursor.fetchall()

        for entry in entries:
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

            # Winner if hit target
            if max_exit >= target_price:
                winners.append({
                    'contract_hash': entry[0],
                    'symbol': entry[1],
                    'strike': entry[2],
                    'expiration_date': entry[3],
                    'option_type': entry[4],
                    'dte': entry[5],
                    'ask': entry[6],
                    'bid': entry[7],
                    'last_price': entry[8],
                    'iv': entry[9],
                    'delta': entry[10],
                    'gamma': entry[11],
                    'theta': entry[12],
                    'vega': entry[13],
                    'underlying_price': entry[14],
                    'volume': entry[15],
                    'open_interest': entry[16],
                    'trade_date': trade_date,
                    'entry_ask': entry_ask,
                    'max_exit': max_exit,
                    'return': (max_exit - entry_ask) / entry_ask
                })

    conn.close()
    return winners

def analyze_patterns(winners):
    """Analyze winner patterns"""

    total = len(winners)
    print("=" * 80)
    print("PHASE 3: PATTERN DISCOVERY")
    print("=" * 80)
    print()
    print(f"Analyzing {total} training winners")
    print()

    # 3.1: Symbol Concentration
    print("3.1 SYMBOL CONCENTRATION")
    print("-" * 80)
    symbol_counts = Counter([w['symbol'] for w in winners])

    print(f"{'Symbol':<10} {'Count':>8} {'% of Winners':>12}")
    print("-" * 80)
    for symbol, count in symbol_counts.most_common(20):
        pct = 100 * count / total
        print(f"{symbol:<10} {count:>8} {pct:>11.1f}%")

    top_5_pct = sum(c for _, c in symbol_counts.most_common(5)) / total * 100
    print()
    print(f"Top 5 symbols: {top_5_pct:.1f}% of winners")
    print()

    # 3.2: Entry Price Distribution
    print("3.2 ENTRY PRICE DISTRIBUTION")
    print("-" * 80)
    price_buckets = defaultdict(int)
    for w in winners:
        ask = w['ask']
        if ask <= 0.03:
            price_buckets['$0.03'] += 1
        elif ask <= 0.05:
            price_buckets['$0.04-0.05'] += 1
        elif ask <= 0.07:
            price_buckets['$0.06-0.07'] += 1
        elif ask <= 0.10:
            price_buckets['$0.08-0.10'] += 1

    print(f"{'Price Range':<15} {'Count':>8} {'% of Winners':>12}")
    print("-" * 80)
    for price_range in ['$0.03', '$0.04-0.05', '$0.06-0.07', '$0.08-0.10']:
        count = price_buckets[price_range]
        pct = 100 * count / total
        print(f"{price_range:<15} {count:>8} {pct:>11.1f}%")
    print()

    # 3.3: DTE Distribution
    print("3.3 DTE DISTRIBUTION")
    print("-" * 80)
    dte_buckets = {'15-20': 0, '21-25': 0, '26-30': 0, '31-40': 0, '41-60': 0}

    for w in winners:
        dte = w['dte']
        if 15 <= dte <= 20:
            dte_buckets['15-20'] += 1
        elif 21 <= dte <= 25:
            dte_buckets['21-25'] += 1
        elif 26 <= dte <= 30:
            dte_buckets['26-30'] += 1
        elif 31 <= dte <= 40:
            dte_buckets['31-40'] += 1
        elif 41 <= dte <= 60:
            dte_buckets['41-60'] += 1

    print(f"{'DTE Range':<15} {'Count':>8} {'% of Winners':>12}")
    print("-" * 80)
    for bucket, count in dte_buckets.items():
        pct = 100 * count / total
        print(f"{bucket:<15} {count:>8} {pct:>11.1f}%")
    print()

    # 3.4: Greek Characteristics
    print("3.4 GREEK CHARACTERISTICS")
    print("-" * 80)

    deltas = [abs(w['delta']) for w in winners if w['delta'] is not None]
    vegas = [w['vega'] for w in winners if w['vega'] is not None]
    ivs = [w['iv'] for w in winners if w['iv'] is not None]

    if deltas:
        print(f"Delta: min={min(deltas):.4f}, max={max(deltas):.4f}, avg={sum(deltas)/len(deltas):.4f}")
    if vegas:
        print(f"Vega:  min={min(vegas):.4f}, max={max(vegas):.4f}, avg={sum(vegas)/len(vegas):.4f}")
    if ivs:
        print(f"IV:    min={min(ivs):.4f}, max={max(ivs):.4f}, avg={sum(ivs)/len(ivs):.4f}")
    print()

    # 3.5: Option Type
    print("3.5 OPTION TYPE")
    print("-" * 80)
    option_types = Counter([w['option_type'] for w in winners])
    for opt_type, count in option_types.items():
        pct = 100 * count / total
        print(f"{opt_type:>10}: {count:>4} ({pct:.1f}%)")
    print()

    # 3.6: Day of Week
    print("3.6 DAY OF WEEK PATTERN")
    print("-" * 80)
    days = []
    for w in winners:
        dt = datetime.strptime(w['trade_date'], '%Y-%m-%d')
        day_name = dt.strftime('%A')
        days.append(day_name)

    day_counts = Counter(days)
    for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        count = day_counts.get(day, 0)
        pct = 100 * count / total if total > 0 else 0
        print(f"{day:<12}: {count:>4} ({pct:.1f}%)")
    print()

    return {
        'symbol_counts': symbol_counts,
        'price_buckets': price_buckets,
        'dte_buckets': dte_buckets,
        'option_types': option_types,
        'day_counts': day_counts,
        'top_5_pct': top_5_pct
    }

if __name__ == '__main__':
    print("Finding all winners from training period...")
    winners = find_all_winners()
    print(f"Found {len(winners)} winners")
    print()

    patterns = analyze_patterns(winners)

    # Save summary
    with open('docs/cheap_options_phase3_patterns.txt', 'w', encoding='utf-8') as f:
        f.write("PHASE 3: PATTERN DISCOVERY SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total Winners Analyzed: {len(winners)}\n\n")

        f.write("TOP 10 SYMBOLS:\n")
        for symbol, count in patterns['symbol_counts'].most_common(10):
            pct = 100 * count / len(winners)
            f.write(f"  {symbol:<10} {count:>4} ({pct:.1f}%)\n")
        f.write(f"\nTop 5 symbols: {patterns['top_5_pct']:.1f}% of winners\n")

    print("\nPattern analysis saved to: docs/cheap_options_phase3_patterns.txt")
