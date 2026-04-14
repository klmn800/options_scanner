"""
Calculate PROPER baselines from ALL historical data, not just max pain weeks.
"""

import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/sector_archive/airlines.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 100)
print("PROPER BASELINE CALCULATION - ALL MONDAY->FRIDAY WEEKS")
print("=" * 100)

# Get date range
cursor.execute("""
    SELECT MIN(trade_date), MAX(trade_date)
    FROM historical_prices
    WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
""")
date_range = cursor.fetchone()
print(f"\nData range: {date_range[0]} to {date_range[1]}")

# Calculate baseline volume change for ALL weeks
cursor.execute("""
    WITH all_mondays AS (
        SELECT symbol, trade_date, volume
        FROM historical_prices
        WHERE strftime('%w', trade_date) = '1'
        AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    ),
    all_fridays AS (
        SELECT symbol, trade_date, volume
        FROM historical_prices
        WHERE strftime('%w', trade_date) = '5'
        AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    ),
    all_weeks AS (
        SELECT
            mon.symbol,
            mon.trade_date as week_start,
            fri.trade_date as week_end,
            ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100) as vol_change
        FROM all_mondays mon
        JOIN all_fridays fri
            ON mon.symbol = fri.symbol
            AND strftime('%Y-%W', mon.trade_date) = strftime('%Y-%W', fri.trade_date)
    )
    SELECT
        COUNT(*) as total_weeks,
        ROUND(AVG(vol_change), 2) as avg_vol_change,
        ROUND(MIN(vol_change), 2) as min_vol_change,
        ROUND(MAX(vol_change), 2) as max_vol_change,
        (SELECT ROUND(vol_change, 2) FROM all_weeks ORDER BY vol_change LIMIT 1 OFFSET (SELECT COUNT(*)/4 FROM all_weeks)) as percentile_25,
        (SELECT ROUND(vol_change, 2) FROM all_weeks ORDER BY vol_change LIMIT 1 OFFSET (SELECT COUNT(*)/2 FROM all_weeks)) as median,
        (SELECT ROUND(vol_change, 2) FROM all_weeks ORDER BY vol_change LIMIT 1 OFFSET (SELECT COUNT(*)*3/4 FROM all_weeks)) as percentile_75
    FROM all_weeks
""")

baseline = cursor.fetchone()
print(f"\n{'Metric':<20} {'Value':<15}")
print("-" * 40)
print(f"{'Total weeks':<20} {baseline[0]}")
print(f"{'Average':<20} {baseline[1]}%")
print(f"{'Median (50th)':<20} {baseline[5]}%")
print(f"{'25th percentile':<20} {baseline[4]}%")
print(f"{'75th percentile':<20} {baseline[6]}%")
print(f"{'Range':<20} {baseline[2]}% - {baseline[3]}%")

print("\n" + "=" * 100)
print("BASELINE BY SYMBOL")
print("=" * 100)

cursor.execute("""
    WITH all_mondays AS (
        SELECT symbol, trade_date, volume
        FROM historical_prices
        WHERE strftime('%w', trade_date) = '1'
        AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    ),
    all_fridays AS (
        SELECT symbol, trade_date, volume
        FROM historical_prices
        WHERE strftime('%w', trade_date) = '5'
        AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    ),
    all_weeks AS (
        SELECT
            mon.symbol,
            ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100) as vol_change
        FROM all_mondays mon
        JOIN all_fridays fri
            ON mon.symbol = fri.symbol
            AND strftime('%Y-%W', mon.trade_date) = strftime('%Y-%W', fri.trade_date)
    )
    SELECT
        symbol,
        COUNT(*) as weeks,
        ROUND(AVG(vol_change), 2) as avg,
        ROUND(MIN(vol_change), 2) as min,
        ROUND(MAX(vol_change), 2) as max
    FROM all_weeks
    GROUP BY symbol
    ORDER BY symbol
""")

print(f"\n{'Symbol':<10} {'Weeks':<10} {'Avg Vol Chg':<15} {'Min':<10} {'Max':<10}")
print("-" * 60)
for row in cursor.fetchall():
    print(f"{row[0]:<10} {row[1]:<10} {row[2]:<15} {row[3]:<10} {row[4]:<10}")

print("\n" + "=" * 100)
print("MAX PAIN WEEKS VS BASELINE COMPARISON")
print("=" * 100)

# Compare max pain weeks to baseline
cursor.execute("""
    WITH baseline_weeks AS (
        SELECT
            mon.symbol,
            ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100) as vol_change
        FROM historical_prices mon
        JOIN historical_prices fri
            ON mon.symbol = fri.symbol
            AND strftime('%Y-%W', mon.trade_date) = strftime('%Y-%W', fri.trade_date)
            AND strftime('%w', mon.trade_date) = '1'
            AND strftime('%w', fri.trade_date) = '5'
        WHERE mon.symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    ),
    maxpain_weeks AS (
        SELECT
            m.symbol,
            m.hit_max_pain_1pct,
            ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100) as vol_change
        FROM max_pain_analysis m
        JOIN historical_prices mon ON m.symbol = mon.symbol AND m.week_start_date = mon.trade_date
        JOIN historical_prices fri ON m.symbol = fri.symbol AND m.week_end_date = fri.trade_date
    )
    SELECT
        'ALL WEEKS (baseline)' as category,
        COUNT(*) as count,
        ROUND(AVG(vol_change), 2) as avg_vol
    FROM baseline_weeks

    UNION ALL

    SELECT
        'Max pain weeks (all)' as category,
        COUNT(*) as count,
        ROUND(AVG(vol_change), 2) as avg_vol
    FROM maxpain_weeks

    UNION ALL

    SELECT
        'Max pain HITS' as category,
        COUNT(*) as count,
        ROUND(AVG(vol_change), 2) as avg_vol
    FROM maxpain_weeks
    WHERE hit_max_pain_1pct = 1

    UNION ALL

    SELECT
        'Max pain MISSES' as category,
        COUNT(*) as count,
        ROUND(AVG(vol_change), 2) as avg_vol
    FROM maxpain_weeks
    WHERE hit_max_pain_1pct = 0
""")

print(f"\n{'Category':<25} {'Count':<10} {'Avg Vol Change':<20}")
print("-" * 60)
for row in cursor.fetchall():
    print(f"{row[0]:<25} {row[1]:<10} {row[2]}%")

print("\n" + "=" * 100)
print("INTERPRETATION")
print("=" * 100)

# Get the values for interpretation
cursor.execute("""
    WITH baseline_weeks AS (
        SELECT ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100) as vol_change
        FROM historical_prices mon
        JOIN historical_prices fri
            ON mon.symbol = fri.symbol
            AND strftime('%Y-%W', mon.trade_date) = strftime('%Y-%W', fri.trade_date)
            AND strftime('%w', mon.trade_date) = '1'
            AND strftime('%w', fri.trade_date) = '5'
        WHERE mon.symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    )
    SELECT ROUND(AVG(vol_change), 2) FROM baseline_weeks
""")
baseline_avg = cursor.fetchone()[0]

cursor.execute("""
    SELECT ROUND(AVG(ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100)), 2)
    FROM max_pain_analysis m
    JOIN historical_prices mon ON m.symbol = mon.symbol AND m.week_start_date = mon.trade_date
    JOIN historical_prices fri ON m.symbol = fri.symbol AND m.week_end_date = fri.trade_date
    WHERE m.hit_max_pain_1pct = 1
""")
hits_avg = cursor.fetchone()[0]

cursor.execute("""
    SELECT ROUND(AVG(ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100)), 2)
    FROM max_pain_analysis m
    JOIN historical_prices mon ON m.symbol = mon.symbol AND m.week_start_date = mon.trade_date
    JOIN historical_prices fri ON m.symbol = fri.symbol AND m.week_end_date = fri.trade_date
    WHERE m.hit_max_pain_1pct = 0
""")
misses_avg = cursor.fetchone()[0]

print(f"\nBaseline (all weeks): {baseline_avg}%")
print(f"Max pain HITS:        {hits_avg}% ({hits_avg - baseline_avg:+.2f}% vs baseline)")
print(f"Max pain MISSES:      {misses_avg}% ({misses_avg - baseline_avg:+.2f}% vs baseline)")

if hits_avg < baseline_avg:
    print(f"\n[YES] HITS show LOWER volume than baseline ({hits_avg}% vs {baseline_avg}%)")
    print(f"      -> Max pain convergence happens in QUIETER weeks")
else:
    print(f"\n[NO] HITS show HIGHER volume than baseline ({hits_avg}% vs {baseline_avg}%)")

if misses_avg > baseline_avg:
    print(f"[YES] MISSES show HIGHER volume than baseline ({misses_avg}% vs {baseline_avg}%)")
    print(f"      -> Max pain failures happen in MORE ACTIVE weeks")
else:
    print(f"[NO] MISSES show LOWER volume than baseline ({misses_avg}% vs {baseline_avg}%)")

print("\n" + "=" * 100)
print("OPEN INTEREST BASELINE")
print("=" * 100)

# OI baseline - what's typical OI for each symbol on Mondays?
cursor.execute("""
    SELECT
        symbol,
        COUNT(*) as mondays,
        ROUND(AVG(total_open_interest)/1000.0, 1) as avg_oi_k,
        ROUND(MIN(total_open_interest)/1000.0, 1) as min_oi_k,
        ROUND(MAX(total_open_interest)/1000.0, 1) as max_oi_k
    FROM option_symbol_summary
    WHERE strftime('%w', trade_date) = '1'
    AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    GROUP BY symbol
    ORDER BY symbol
""")

print(f"\n{'Symbol':<10} {'Mondays':<10} {'Avg OI':<15} {'Min OI':<15} {'Max OI':<15}")
print("-" * 70)
for row in cursor.fetchall():
    print(f"{row[0]:<10} {row[1]:<10} {row[2]:.1f}K{'':<10} {row[3]:.1f}K{'':<10} {row[4]:.1f}K")

# Compare max pain weeks to baseline
cursor.execute("""
    WITH baseline_oi AS (
        SELECT
            symbol,
            total_open_interest as oi
        FROM option_symbol_summary
        WHERE strftime('%w', trade_date) = '1'
        AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    )
    SELECT
        'ALL MONDAYS (baseline)' as category,
        ROUND(AVG(oi)/1000.0, 1) as avg_oi_k
    FROM baseline_oi

    UNION ALL

    SELECT
        'Max pain weeks (all)' as category,
        ROUND(AVG(mon_oi)/1000.0, 1) as avg_oi_k
    FROM max_pain_analysis

    UNION ALL

    SELECT
        'Max pain HITS' as category,
        ROUND(AVG(mon_oi)/1000.0, 1) as avg_oi_k
    FROM max_pain_analysis
    WHERE hit_max_pain_1pct = 1

    UNION ALL

    SELECT
        'Max pain MISSES' as category,
        ROUND(AVG(mon_oi)/1000.0, 1) as avg_oi_k
    FROM max_pain_analysis
    WHERE hit_max_pain_1pct = 0
""")

print(f"\n{'Category':<25} {'Avg OI':<15}")
print("-" * 45)
for row in cursor.fetchall():
    print(f"{row[0]:<25} {row[1]:.1f}K")

conn.close()
