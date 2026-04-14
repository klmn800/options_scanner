import sqlite3
import pandas as pd
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/sector_archive/utilities.db')

print('='*70)
print('UTILITIES SECTOR MAX PAIN ANALYSIS')
print('='*70)

# 1. Overall Hit Rates
print('\n1. OVERALL HIT RATES')
print('-' * 50)

overall_query = '''
SELECT
    COUNT(*) as total_observations,
    SUM(hit_max_pain_1pct) as hits_1pct,
    SUM(hit_max_pain_2pct) as hits_2pct,
    SUM(hit_max_pain_3pct) as hits_3pct,
    ROUND(100.0 * SUM(hit_max_pain_1pct) / COUNT(*), 1) as hit_rate_1pct,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct,
    ROUND(100.0 * SUM(hit_max_pain_3pct) / COUNT(*), 1) as hit_rate_3pct
FROM max_pain_analysis
'''
overall = pd.read_sql_query(overall_query, conn)
print(overall.to_string(index=False))

# 2. Hit Rate by Proximity to Max Pain on Monday
print('\n2. HIT RATE BY MONDAY PROXIMITY TO MAX PAIN')
print('-' * 50)

proximity_query = '''
SELECT
    CASE
        WHEN ABS(mon_gap_pct) < 2 THEN '< 2%'
        WHEN ABS(mon_gap_pct) < 5 THEN '2-5%'
        WHEN ABS(mon_gap_pct) < 10 THEN '5-10%'
        ELSE '> 10%'
    END as proximity_range,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM max_pain_analysis
GROUP BY proximity_range
ORDER BY
    CASE proximity_range
        WHEN '< 2%' THEN 1
        WHEN '2-5%' THEN 2
        WHEN '5-10%' THEN 3
        ELSE 4
    END
'''
proximity = pd.read_sql_query(proximity_query, conn)
print(proximity.to_string(index=False))

# 3. Hit Rate by IV Change Pattern
print('\n3. HIT RATE BY IMPLIED VOLATILITY CHANGE')
print('-' * 50)

iv_query = '''
SELECT
    CASE
        WHEN (fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100 < -10 THEN 'Decline > 10%'
        WHEN (fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100 < 0 THEN 'Decline 0-10%'
        WHEN (fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100 < 10 THEN 'Increase 0-10%'
        ELSE 'Increase > 10%'
    END as iv_change_category,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct,
    ROUND(AVG((fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100), 2) as avg_iv_change_pct
FROM max_pain_analysis
WHERE mon_iv IS NOT NULL AND fri_iv IS NOT NULL
GROUP BY iv_change_category
ORDER BY
    CASE iv_change_category
        WHEN 'Decline > 10%' THEN 1
        WHEN 'Decline 0-10%' THEN 2
        WHEN 'Increase 0-10%' THEN 3
        ELSE 4
    END
'''
iv = pd.read_sql_query(iv_query, conn)
print(iv.to_string(index=False))

# 4. Hit Rate by Volume Deviation
print('\n4. HIT RATE BY VOLUME PATTERNS')
print('-' * 50)

volume_query = '''
SELECT
    CASE
        WHEN mon_vol_dev_pct < -20 THEN 'Mon Vol < -20%'
        WHEN mon_vol_dev_pct < 0 THEN 'Mon Vol 0 to -20%'
        WHEN mon_vol_dev_pct < 20 THEN 'Mon Vol 0 to +20%'
        ELSE 'Mon Vol > +20%'
    END as monday_volume_pattern,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM max_pain_analysis
WHERE mon_vol_dev_pct IS NOT NULL
GROUP BY monday_volume_pattern
ORDER BY hit_rate_2pct DESC
'''
volume = pd.read_sql_query(volume_query, conn)
print(volume.to_string(index=False))

# 5. Hit Rate by Open Interest Deviation
print('\n5. HIT RATE BY OPEN INTEREST PATTERNS')
print('-' * 50)

oi_query = '''
SELECT
    CASE
        WHEN mon_oi_dev_pct < -10 THEN 'Mon OI < -10%'
        WHEN mon_oi_dev_pct < 0 THEN 'Mon OI 0 to -10%'
        WHEN mon_oi_dev_pct < 10 THEN 'Mon OI 0 to +10%'
        ELSE 'Mon OI > +10%'
    END as monday_oi_pattern,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM max_pain_analysis
WHERE mon_oi_dev_pct IS NOT NULL
GROUP BY monday_oi_pattern
ORDER BY hit_rate_2pct DESC
'''
oi = pd.read_sql_query(oi_query, conn)
print(oi.to_string(index=False))

# 6. Combined Factors Analysis
print('\n6. COMBINED FACTORS ANALYSIS (Best Conditions)')
print('-' * 50)

combined_query = '''
WITH market_data AS (
    SELECT
        ma.*,
        mds.vix_close as friday_vix
    FROM max_pain_analysis ma
    LEFT JOIN market_daily_summary mds ON ma.week_end_date = mds.trade_date
)
SELECT
    'All observations' as condition,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM market_data
UNION ALL
SELECT
    'Proximity < 5%' as condition,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM market_data
WHERE ABS(mon_gap_pct) < 5
UNION ALL
SELECT
    'IV Decline 0-10%' as condition,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM market_data
WHERE (fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100 BETWEEN -10 AND 0
UNION ALL
SELECT
    'Low VIX < 15' as condition,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM market_data
WHERE friday_vix < 15
UNION ALL
SELECT
    'Proximity < 5% AND IV Decline' as condition,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM market_data
WHERE ABS(mon_gap_pct) < 5
  AND (fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100 BETWEEN -10 AND 0
UNION ALL
SELECT
    'All 3 factors' as condition,
    COUNT(*) as observations,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM market_data
WHERE ABS(mon_gap_pct) < 5
  AND (fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100 BETWEEN -10 AND 0
  AND friday_vix < 15
'''
combined = pd.read_sql_query(combined_query, conn)
print(combined.to_string(index=False))

# 7. Week-by-Week Analysis
print('\n7. WEEK-BY-WEEK HIT RATES')
print('-' * 50)

weekly_query = '''
SELECT
    week_id,
    MIN(week_start_date) as monday,
    MAX(week_end_date) as friday,
    COUNT(*) as symbols,
    SUM(hit_max_pain_2pct) as hits,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate_2pct
FROM max_pain_analysis
GROUP BY week_id
ORDER BY week_id
'''
weekly = pd.read_sql_query(weekly_query, conn)
print(weekly.to_string(index=False))

# 8. Top Performing Symbols
print('\n8. SYMBOL PERFORMANCE')
print('-' * 50)

symbol_query = '''
SELECT
    symbol,
    COUNT(*) as weeks,
    SUM(hit_max_pain_2pct) as hits_2pct,
    ROUND(100.0 * SUM(hit_max_pain_2pct) / COUNT(*), 1) as hit_rate,
    ROUND(AVG(ABS(mon_gap_pct)), 2) as avg_monday_gap
FROM max_pain_analysis
GROUP BY symbol
HAVING SUM(hit_max_pain_2pct) > 0
ORDER BY hit_rate DESC, hits_2pct DESC
LIMIT 15
'''
symbols = pd.read_sql_query(symbol_query, conn)
print(symbols.to_string(index=False))

# 9. Statistical Summary
print('\n9. STATISTICAL SUMMARY')
print('-' * 50)

stats_query = '''
SELECT
    ROUND(AVG(ABS(mon_gap_pct)), 2) as avg_monday_gap_pct,
    ROUND(AVG(ABS(fri_gap_pct)), 2) as avg_friday_gap_pct,
    ROUND(AVG(price_change_pct), 2) as avg_price_change_pct,
    ROUND(STDDEV(price_change_pct), 2) as stddev_price_change,
    ROUND(AVG((fri_iv - mon_iv) / NULLIF(mon_iv, 0) * 100), 2) as avg_iv_change_pct,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(DISTINCT week_id) as unique_weeks
FROM max_pain_analysis
'''
stats = pd.read_sql_query(stats_query, conn)
print(stats.to_string(index=False))

conn.close()

print('\n' + '='*70)
print('END OF UTILITIES SECTOR MAX PAIN ANALYSIS')
print('='*70)