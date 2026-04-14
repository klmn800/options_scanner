"""
Establish proper baselines and analyze market/sector context for max pain hits/misses.
"""

import sqlite3
import sys
from datetime import datetime

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/sector_archive/airlines.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 100)
print("BASELINE STATISTICS")
print("=" * 100)

# Volume baseline
cursor.execute("""
    WITH volume_analysis AS (
        SELECT
            ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100) as abs_vol_change
        FROM max_pain_analysis m
        JOIN historical_prices mon ON m.symbol = mon.symbol AND m.week_start_date = mon.trade_date
        JOIN historical_prices fri ON m.symbol = fri.symbol AND m.week_end_date = fri.trade_date
    )
    SELECT
        ROUND(AVG(abs_vol_change), 2) as avg,
        ROUND(MIN(abs_vol_change), 2) as min,
        ROUND(MAX(abs_vol_change), 2) as max,
        (SELECT ROUND(abs_vol_change, 2) FROM volume_analysis ORDER BY abs_vol_change LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM volume_analysis)) as median
    FROM volume_analysis
""")
vol_stats = cursor.fetchone()
print(f"\nStock Volume Change (Mon->Fri):")
print(f"  Average: {vol_stats[0]}% (NOT 20%!)")
print(f"  Median:  {vol_stats[3]}%")
print(f"  Range:   {vol_stats[1]}% - {vol_stats[2]}%")
print(f"  -> Low volume is <{vol_stats[0]/2:.0f}%, NOT <20%")

# OI baseline
cursor.execute("""
    SELECT
        ROUND(AVG(mon_oi)/1000.0, 1) as avg_k,
        ROUND(MIN(mon_oi)/1000.0, 1) as min_k,
        ROUND(MAX(mon_oi)/1000.0, 1) as max_k
    FROM max_pain_analysis
""")
oi_stats = cursor.fetchone()
print(f"\nOpen Interest (Monday):")
print(f"  Average: {oi_stats[0]:.1f}K")
print(f"  Range:   {oi_stats[1]:.1f}K - {oi_stats[2]:.1f}K")
print(f"  -> Low OI is <{oi_stats[0]/2:.0f}K")

print("\n" + "=" * 100)
print("JETS ETF CORRELATION ANALYSIS")
print("=" * 100)

# JETS correlation
cursor.execute("""
    WITH jets_moves AS (
        SELECT
            m.week_id,
            m.symbol,
            m.hit_max_pain_1pct,
            ROUND((jets_fri.close_price - jets_mon.close_price) / jets_mon.close_price * 100, 2) as jets_move,
            ROUND(m.price_change_pct, 2) as stock_move
        FROM max_pain_analysis m
        JOIN historical_prices jets_mon ON jets_mon.symbol = 'JETS' AND jets_mon.trade_date = m.week_start_date
        JOIN historical_prices jets_fri ON jets_fri.symbol = 'JETS' AND jets_fri.trade_date = m.week_end_date
    )
    SELECT
        hit_max_pain_1pct,
        COUNT(*) as total,
        ROUND(AVG(ABS(jets_move)), 2) as avg_jets_move,
        ROUND(AVG(ABS(stock_move - jets_move)), 2) as avg_divergence
    FROM jets_moves
    GROUP BY hit_max_pain_1pct
""")

print(f"\n{'Result':<10} {'Count':<8} {'Avg JETS Move':<15} {'Avg Divergence':<18}")
print("-" * 60)
for row in cursor.fetchall():
    result = "HIT" if row[0] == 1 else "MISS"
    print(f"{result:<10} {row[1]:<8} {row[2]:.2f}%{'':<10} {row[3]:.2f}%")

print("\n" + "=" * 100)
print("EARNINGS PROXIMITY ANALYSIS")
print("=" * 100)

# Check if any max pain weeks overlap with earnings
cursor.execute("""
    SELECT
        m.symbol,
        m.week_id,
        m.week_start_date,
        m.week_end_date,
        m.hit_max_pain_1pct,
        e.earnings_date,
        julianday(e.earnings_date) - julianday(m.week_start_date) as days_from_monday,
        e.actual_eps,
        e.eps_surprise_pct
    FROM max_pain_analysis m
    JOIN earnings_events e ON m.symbol = e.symbol
    WHERE e.earnings_date BETWEEN date(m.week_start_date, '-7 days') AND date(m.week_end_date, '+7 days')
    ORDER BY m.symbol, m.week_id
""")

earnings_nearby = cursor.fetchall()
if earnings_nearby:
    print(f"\nFound {len(earnings_nearby)} weeks with earnings within ±7 days:")
    print(f"\n{'Symbol':<8} {'Week':<10} {'Hit':<5} {'Earnings Date':<15} {'Days Offset':<12} {'EPS Surprise':<12}")
    print("-" * 80)
    for row in earnings_nearby:
        hit_str = "YES" if row[4] == 1 else "NO"
        surprise = f"{row[8]:.1f}%" if row[8] is not None else "N/A"
        print(f"{row[0]:<8} {row[1]:<10} {hit_str:<5} {row[5]:<15} {row[6]:>4.0f}{'':<8} {surprise:<12}")

    # Stats
    cursor.execute("""
        SELECT
            m.hit_max_pain_1pct,
            COUNT(*) as count
        FROM max_pain_analysis m
        JOIN earnings_events e ON m.symbol = e.symbol
        WHERE e.earnings_date BETWEEN date(m.week_start_date, '-7 days') AND date(m.week_end_date, '+7 days')
        GROUP BY m.hit_max_pain_1pct
    """)
    stats = cursor.fetchall()
    total_earnings_weeks = sum(s[1] for s in stats)
    hits_earnings_weeks = next((s[1] for s in stats if s[0] == 1), 0)
    print(f"\n  Hit rate during earnings weeks: {hits_earnings_weeks}/{total_earnings_weeks} = {hits_earnings_weeks*100.0/total_earnings_weeks:.1f}%")
else:
    print("\nNo weeks found with earnings within ±7 days")

print("\n" + "=" * 100)
print("10TH OF MONTH SUPERSTITION TEST")
print("=" * 100)

# Test 10th of month clustering
cursor.execute("""
    SELECT
        CAST(strftime('%d', week_start_date) AS INTEGER) as day_of_month,
        COUNT(*) as total_weeks,
        SUM(hit_max_pain_1pct) as hits,
        ROUND(SUM(hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate
    FROM max_pain_analysis
    GROUP BY day_of_month
    HAVING total_weeks > 1
    ORDER BY day_of_month
""")

print(f"\n{'Day of Month':<15} {'Total Weeks':<15} {'Hits':<10} {'Hit Rate':<10}")
print("-" * 60)
for row in cursor.fetchall():
    special = " <- NEAR 10TH" if 8 <= row[0] <= 12 else ""
    print(f"{row[0]:<15} {row[1]:<15} {row[2]:<10} {row[3]:.1f}%{special}")

# Specific 10th analysis
cursor.execute("""
    WITH near_10th AS (
        SELECT
            CASE WHEN CAST(strftime('%d', week_start_date) AS INTEGER) BETWEEN 8 AND 12 THEN 1 ELSE 0 END as is_near_10th,
            hit_max_pain_1pct
        FROM max_pain_analysis
    )
    SELECT
        is_near_10th,
        COUNT(*) as total,
        SUM(hit_max_pain_1pct) as hits,
        ROUND(SUM(hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate
    FROM near_10th
    GROUP BY is_near_10th
""")

print(f"\n{'Period':<20} {'Total':<10} {'Hits':<10} {'Hit Rate':<10}")
print("-" * 60)
for row in cursor.fetchall():
    period = "Near 10th (8-12)" if row[0] == 1 else "Other days"
    print(f"{period:<20} {row[1]:<10} {row[2]:<10} {row[3]:.1f}%")

print("\n" + "=" * 100)
print("MARKET REGIME CORRELATION")
print("=" * 100)

# Market regime on Monday
cursor.execute("""
    SELECT
        mds.regime_classification,
        COUNT(*) as total,
        SUM(m.hit_max_pain_1pct) as hits,
        ROUND(SUM(m.hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate,
        ROUND(AVG(mds.spy_change_percent), 2) as avg_spy_move
    FROM max_pain_analysis m
    LEFT JOIN market_daily_summary mds ON mds.trade_date = m.week_start_date
    WHERE mds.regime_classification IS NOT NULL
    GROUP BY mds.regime_classification
    ORDER BY total DESC
""")

print(f"\nMarket Regime on Monday:")
print(f"{'Regime':<20} {'Total':<10} {'Hits':<10} {'Hit Rate':<12} {'Avg SPY Move':<12}")
print("-" * 70)
for row in cursor.fetchall():
    regime = row[0] if row[0] else "Unknown"
    print(f"{regime:<20} {row[1]:<10} {row[2]:<10} {row[3]:.1f}%{'':<6} {row[4]:.2f}%")

# VIX analysis
cursor.execute("""
    SELECT
        CASE
            WHEN mds.vix_close < 15 THEN 'Low VIX (<15)'
            WHEN mds.vix_close < 20 THEN 'Normal VIX (15-20)'
            WHEN mds.vix_close < 30 THEN 'Elevated VIX (20-30)'
            ELSE 'High VIX (>30)'
        END as vix_regime,
        COUNT(*) as total,
        SUM(m.hit_max_pain_1pct) as hits,
        ROUND(SUM(m.hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate
    FROM max_pain_analysis m
    LEFT JOIN market_daily_summary mds ON mds.trade_date = m.week_start_date
    WHERE mds.vix_close IS NOT NULL
    GROUP BY vix_regime
    ORDER BY AVG(mds.vix_close)
""")

print(f"\nVIX Level on Monday:")
print(f"{'VIX Regime':<20} {'Total':<10} {'Hits':<10} {'Hit Rate':<12}")
print("-" * 60)
for row in cursor.fetchall():
    print(f"{row[0]:<20} {row[1]:<10} {row[2]:<10} {row[3]:.1f}%")

print("\n" + "=" * 100)
print("WEEK 2025-38 DEEP DIVE (Both AAL and DAL missed)")
print("=" * 100)

cursor.execute("""
    SELECT
        m.symbol,
        m.week_start_date,
        m.mon_price,
        m.fri_price,
        m.mon_max_pain,
        m.fri_max_pain,
        ROUND(m.price_change_pct, 2) as price_chg,
        jets.close_price as jets_price
    FROM max_pain_analysis m
    LEFT JOIN historical_prices jets ON jets.symbol = 'JETS' AND jets.trade_date = m.week_start_date
    WHERE m.week_id = '2025-38'
    ORDER BY m.symbol
""")

print(f"\n{'Symbol':<8} {'Mon Price':<12} {'Fri Price':<12} {'Price Chg':<12} {'JETS':<10}")
print("-" * 60)
for row in cursor.fetchall():
    jets_str = f"${row[7]:.2f}" if row[7] is not None else "N/A"
    print(f"{row[0]:<8} ${row[2]:<11.2f} ${row[3]:<11.2f} {row[6]:>6.2f}%{'':<5} {jets_str:<10}")

# Check for news/events that week
cursor.execute("""
    SELECT symbol, earnings_date, actual_eps, eps_surprise_pct
    FROM earnings_events
    WHERE earnings_date BETWEEN '2025-09-16' AND '2025-09-27'
    ORDER BY earnings_date
""")
earnings_that_week = cursor.fetchall()
if earnings_that_week:
    print(f"\nEarnings during week 2025-38:")
    for row in earnings_that_week:
        surprise = f"{row[3]:.1f}%" if row[3] is not None else "N/A"
        print(f"  {row[0]}: {row[1]} - EPS surprise: {surprise}")

conn.close()
