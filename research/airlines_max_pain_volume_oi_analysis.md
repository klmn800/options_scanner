# Volume and OI Baseline Analysis
**Date**: 2025-11-07
**Dataset**: 67 observations, 13 weeks, Airlines sector (June-October 2025)

---

## Methodology

### Baseline Calculation

**Purpose**: Determine if max pain hits/misses correlate with abnormal volume or OI levels.

**Baseline Definition**: For each symbol, calculate average Monday volume and Friday volume across the analysis period (June 24 - October 15, 2025). Same for OI.

**SQL Query for Volume Baseline**:
```sql
monday_volume_baseline AS (
    SELECT
        symbol,
        AVG(volume) as baseline_mon_vol
    FROM historical_prices
    WHERE strftime('%w', trade_date) = '1'
    AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    AND trade_date >= (SELECT MIN(trade_date) FROM option_symbol_summary WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL'))
    AND trade_date <= (SELECT MAX(trade_date) FROM option_symbol_summary WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL'))
    GROUP BY symbol
)
```

**Deviation Calculation**:
```
deviation_pct = (actual_value - baseline_value) / baseline_value * 100
```

Positive = above baseline, Negative = below baseline

---

## Volume Analysis Results

### Query Run:
```sql
SELECT symbol, week_id, week_start_date, mon_vol_dev_pct, fri_vol_dev_pct,
       price_change_pct, ROUND(ABS(mon_gap_pct), 2) as abs_init_dist, hit_max_pain_1pct
FROM max_pain_analysis
ORDER BY symbol, week_start_date
```

### Summary Statistics (67 observations total, 17 hits)

**Volume Deviation Distribution for Hits:**

| Symbol | Hits | Mon Vol Range | Fri Vol Range |
|--------|------|---------------|---------------|
| AAL    | 4    | +2% to +47%   | +2% to +24%   |
| ALK    | 3    | -29% to +81%  | -32% to +86%  |
| DAL    | 5    | -28% to -7%   | -32% to +53%  |
| JBLU   | 1    | -16%          | -33%          |
| LUV    | 3    | -22% to +4%   | -34% to +108% |
| UAL    | 1    | +3%           | +17%          |

**Cross-Symbol Pattern Analysis:**

Monday volume deviation for all 17 hits:
- Below baseline (<-10%): 7 hits (41%)
- Above baseline (>+10%): 6 hits (35%)
- Near baseline (-10% to +10%): 4 hits (24%)

Friday volume deviation for all 17 hits:
- Below baseline (<-10%): 7 hits (41%)
- Above baseline (>+10%): 7 hits (41%)
- Near baseline (-10% to +10%): 3 hits (18%)

**Key Finding**: No consistent pattern. Hits occur with both high and low volume deviations.

---

## OI Analysis Results

### Query Run:
```sql
SELECT symbol, week_id, week_start_date, mon_oi_dev_pct, fri_oi_dev_pct,
       price_change_pct, ROUND(ABS(mon_gap_pct), 2) as abs_init_dist, hit_max_pain_1pct
FROM max_pain_analysis
ORDER BY symbol, week_start_date
```

### Summary Statistics

**OI Deviation Distribution for Hits:**

| Symbol | Hits | Mon OI Range       | Fri OI Range       |
|--------|------|--------------------|--------------------|
| AAL    | 4    | -80% to +76%       | -78% to +382%      |
| ALK    | 3    | -38% to +163%      | -61% to +127%      |
| DAL    | 5    | -86% to +588%      | -100% to +442%     |
| JBLU   | 1    | -3%                | -22%               |
| LUV    | 3    | -69% to +202%      | -100% to -67%      |
| UAL    | 1    | +94%               | +447%              |

**Cross-Symbol Pattern Analysis:**

Monday OI deviation for all 17 hits:
- Very low (<-50%): 8 hits (47%)
- Very high (>+100%): 5 hits (29%)
- Moderate (-50% to +100%): 4 hits (24%)

Friday OI deviation for all 17 hits:
- Very low (<-50%): 8 hits (47%)
- Very high (>+100%): 5 hits (29%)
- Moderate (-50% to +100%): 4 hits (24%)

**Key Finding**: Extreme variance in OI. Hits occur with OI ranging from -100% (essentially zero) to +588% (6x baseline).

---

## Baseline Methodology Validation

### Initial Error: Wrong Time Period

**Original baseline calculation** (incorrect):
```sql
-- Used ALL historical data (2021-2025, 213 weeks)
AVG(volume) FROM historical_prices WHERE strftime('%w', trade_date) = '1'
```

**Result**:
- DAL Monday baseline: 10.6M shares
- Recent weeks (June-Oct 2025) averaged 8.4M
- Made 11 of 13 weeks appear "below baseline"
- Created false signal

**Corrected baseline calculation**:
```sql
-- Uses ONLY analysis period (June-Oct 2025, 15 weeks)
AVG(volume) FROM historical_prices
WHERE strftime('%w', trade_date) = '1'
AND trade_date >= (SELECT MIN(trade_date) FROM option_symbol_summary ...)
```

**Result**:
- DAL Monday baseline: 8.4M shares (accurate for this period)
- Weeks distributed evenly: 8 below, 5 above
- No systematic bias

### Why Day-Specific Baselines Matter

**Tested**: Monday average vs Friday average vs All-Week average

**Results** (15-week period):

| Symbol | Mon Avg (M) | Fri Avg (M) | Mon-Fri Diff |
|--------|-------------|-------------|--------------|
| AAL    | 76.05       | 70.78       | 7.0%         |
| ALK    | 3.36        | 2.69        | 24.4%        |
| DAL    | 7.38        | 8.65        | 15.6%        |
| JBLU   | 14.79       | 20.49       | 29.9%        |
| LUV    | 8.79        | 10.13       | 14.9%        |
| UAL    | 4.78        | 5.81        | 19.3%        |

**Finding**: Monday and Friday volumes differ by 7-30% depending on symbol. Using all-week average would introduce systematic bias.

**Same pattern for OI**:

| Symbol | Mon OI (K) | Fri OI (K) | Mon-Fri Diff |
|--------|------------|------------|--------------|
| AAL    | 2,058      | 2,209      | 7.0%         |
| ALK    | 126        | 183        | 36.6%        |
| DAL    | 1,239      | 1,088      | 12.3%        |
| JBLU   | 53         | 79         | 39.9%        |
| LUV    | 599        | 652        | 8.2%         |
| UAL    | 609        | 481        | 22.4%        |

**Decision**: Use Monday-specific and Friday-specific baselines to avoid weekly pattern bias.

---

## Conclusions

1. **No volume pattern**: Max pain hits occur with both high volume (+108%) and low volume (-34%) weeks. No correlation detected.

2. **No OI pattern**: Max pain hits occur with OI ranging from -100% (zero) to +588% (6x normal). Extreme variance, no predictive signal.

3. **Baseline methodology matters**: Using wrong time period (4 years vs 15 weeks) creates false signals. Must align baseline period with analysis period.

4. **Day-specific baselines required**: Monday and Friday have different typical volumes/OI (7-40% difference). Using all-week average introduces bias.

5. **Symbol-specific behavior**: Each airline has different baseline levels and different patterns. Cannot apply one-size-fits-all threshold.

**Overall**: For airlines sector (June-October 2025), volume and OI deviations do NOT reliably predict max pain convergence.

---

## Files Created

1. `create_max_pain_view_with_baselines.sql` - Updated view with baseline calculations
2. `apply_view_update.py` - Script to apply view changes
3. `proper_baseline_calculation.py` - Validation script showing baseline methodology
4. `baseline_volume_oi_analysis.md` - This document
