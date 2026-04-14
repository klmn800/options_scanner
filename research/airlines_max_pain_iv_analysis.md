# Implied Volatility (IV) Analysis
**Date**: 2025-11-07
**Dataset**: 50 weeks with complete IV data (out of 67 total), Airlines sector

---

## Data Availability

```sql
SELECT COUNT(*) as total, COUNT(mon_iv) as has_mon_iv, COUNT(fri_iv) as has_fri_iv
FROM max_pain_analysis
```

**Result**: 67 total weeks, 53 with Monday IV, 56 with Friday IV, **50 with both**

17 weeks excluded from analysis due to missing IV data (primarily July 2025 weeks and JBLU early weeks).

---

## Analysis 1: IV Change Pattern (Monday → Friday)

### Query:
```sql
SELECT
    hit_max_pain_1pct as hit,
    COUNT(*) as count,
    ROUND(AVG((fri_iv - mon_iv) * 100), 2) as avg_iv_change,
    ROUND(AVG(mon_iv * 100), 2) as avg_mon_iv,
    ROUND(AVG(fri_iv * 100), 2) as avg_fri_iv
FROM max_pain_analysis
WHERE mon_iv IS NOT NULL AND fri_iv IS NOT NULL
GROUP BY hit_max_pain_1pct
```

### Results:

| Result | Count | Avg IV Change | Avg Mon IV | Avg Fri IV |
|--------|-------|---------------|------------|------------|
| HITS   | 15    | +0.76%        | 46.55%     | 47.32%     |
| MISSES | 35    | +1.75%        | 48.79%     | 50.54%     |

**Finding**: Minimal difference in average IV change between hits and misses.

---

## Analysis 2: Hit Rate by IV Change Bucket

### Query:
```sql
WITH iv_buckets AS (
    SELECT
        hit_max_pain_1pct,
        CASE
            WHEN (fri_iv - mon_iv) * 100 < -10 THEN 'IV Crush (<-10)'
            WHEN (fri_iv - mon_iv) * 100 < 0 THEN 'IV Decline (0 to -10)'
            WHEN (fri_iv - mon_iv) * 100 < 10 THEN 'IV Stable (0 to +10)'
            ELSE 'IV Expansion (>+10)'
        END as iv_bucket
    FROM max_pain_analysis
    WHERE mon_iv IS NOT NULL AND fri_iv IS NOT NULL
)
SELECT
    iv_bucket,
    COUNT(*) as total,
    SUM(hit_max_pain_1pct) as hits,
    ROUND(SUM(hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate
FROM iv_buckets
GROUP BY iv_bucket
```

### Results:

| IV Behavior | Total Weeks | Hits | Hit Rate | vs Baseline |
|-------------|-------------|------|----------|-------------|
| **IV Decline (0 to -10%)** | 18 | 8 | **44.44%** | +14.44% |
| IV Stable (0 to +10%) | 16 | 5 | 31.25% | +1.25% |
| IV Crush (<-10%) | 7 | 1 | 14.29% | -15.71% |
| IV Expansion (>+10%) | 9 | 1 | 11.11% | -18.89% |

**Baseline**: 30% hit rate (15/50 weeks)

**Finding**: Moderate IV decline (0 to -10%) has 44% hit rate, significantly above baseline. Extreme IV moves (crush or expansion) have LOW hit rates (11-14%).

---

## Analysis 3: Hit Rate by Monday IV Level

### Query:
```sql
WITH iv_level_buckets AS (
    SELECT
        hit_max_pain_1pct,
        CASE
            WHEN mon_iv * 100 < 40 THEN 'Low IV (<40%)'
            WHEN mon_iv * 100 < 50 THEN 'Normal IV (40-50%)'
            WHEN mon_iv * 100 < 60 THEN 'Elevated IV (50-60%)'
            ELSE 'High IV (>60%)'
        END as iv_level
    FROM max_pain_analysis
    WHERE mon_iv IS NOT NULL
)
SELECT
    iv_level,
    COUNT(*) as total,
    SUM(hit_max_pain_1pct) as hits,
    ROUND(SUM(hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate
FROM iv_level_buckets
GROUP BY iv_level
```

### Results:

| Monday IV Level | Total Weeks | Hits | Hit Rate | vs Baseline |
|-----------------|-------------|------|----------|-------------|
| **Low IV (<40%)** | 15 | 6 | **40.0%** | +10.0% |
| Normal IV (40-50%) | 17 | 6 | 35.29% | +5.29% |
| Elevated IV (50-60%) | 11 | 3 | 27.27% | -2.73% |
| High IV (>60%) | 10 | 2 | 20.0% | -10.0% |

**Finding**: Inverse correlation - Lower Monday IV correlates with higher hit rate. High IV (>60%) has only 20% hit rate.

---

## Analysis 4: Combined Conditions Test

### Query:
```sql
WITH iv_conditions AS (
    SELECT
        symbol, week_id, hit_max_pain_1pct,
        CASE WHEN mon_iv * 100 < 40 THEN 1 ELSE 0 END as low_iv,
        CASE WHEN (fri_iv - mon_iv) * 100 BETWEEN -10 AND 0 THEN 1 ELSE 0 END as moderate_decline
    FROM max_pain_analysis
    WHERE mon_iv IS NOT NULL AND fri_iv IS NOT NULL
)
SELECT
    CASE
        WHEN low_iv = 1 AND moderate_decline = 1 THEN 'BOTH (Low IV + Decline)'
        WHEN low_iv = 1 THEN 'Low IV only'
        WHEN moderate_decline = 1 THEN 'Decline only'
        ELSE 'Neither'
    END as condition,
    COUNT(*) as total,
    SUM(hit_max_pain_1pct) as hits,
    ROUND(SUM(hit_max_pain_1pct) * 100.0 / COUNT(*), 2) as hit_rate
FROM iv_conditions
GROUP BY condition
```

### Results:

| Condition | Total Weeks | Hits | Hit Rate |
|-----------|-------------|------|----------|
| **BOTH (Low IV + Decline)** | 2 | 2 | **100.0%** |
| Decline only | 17 | 6 | 35.29% |
| Low IV only | 10 | 2 | 20.0% |
| Neither | 21 | 5 | 23.81% |

**The 2 weeks meeting both conditions:**
1. DAL 2025-29 (July 21): 36% IV, -2% change → HIT
2. LUV 2025-37 (Sept 15): 36% IV, -1% change → HIT

**Finding**: Combined conditions show 100% hit rate BUT only 2 samples - not statistically significant.

---

## Conclusions

### Strongest Signal: Moderate IV Decline (0 to -10%)
- **Sample size**: 18 weeks
- **Hit rate**: 44.44%
- **Baseline**: 30%
- **Improvement**: +14.44 percentage points

### Secondary Signal: Low Monday IV (<40%)
- **Sample size**: 15 weeks
- **Hit rate**: 40%
- **Baseline**: 30%
- **Improvement**: +10 percentage points

### Combined Signal: Not Reliable
- Only 2 samples meeting both conditions
- 100% hit rate suggests strong effect but insufficient data

### Anti-Signals (Avoid):
- **IV Crush (<-10%)**: 14% hit rate
- **IV Expansion (>+10%)**: 11% hit rate
- Extreme IV moves reduce max pain effectiveness

### Interpretation:

Max pain convergence appears to favor:
1. **Calm weeks** - moderate IV decline indicates markets settling, not spiking
2. **Lower volatility environments** - starting IV <40% suggests less chaos
3. **Stability over drama** - extreme IV swings (crush or expansion) break max pain effect

This aligns with earlier finding that low stock volume correlates with hits - both point to **quiet, stable weeks** favoring max pain convergence.

---

## Limitations

1. **Missing data**: 17 weeks excluded (25% of dataset)
2. **Small sample for combined test**: Only 2 weeks, not reliable
3. **Sector-specific**: Results apply to Airlines only
4. **Time period**: June-October 2025 only

## Next Steps

Test IV patterns in other sectors with:
- Lower baseline volatility (utilities, consumer staples)
- Different market cap ranges
- Different option liquidity profiles
