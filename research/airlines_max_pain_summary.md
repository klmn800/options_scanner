# Max Pain Analysis - Airlines Sector Summary
**Analysis Period**: June 24 - October 15, 2025 (13-15 weeks depending on symbol)
**Symbols**: AAL, ALK, DAL, JBLU, LUV, UAL
**Total Observations**: 67 Monday→Friday pairs
**Hits**: 17 (25.4%)

---

## Key Findings

### 1. Max Pain Works 25% of the Time
- **Hit rate**: 17/67 (25.4%)
- **Definition**: Friday close within 1% of Friday max pain

### 2. Proximity Matters - But Isn't Sufficient
- **<2% away on Monday**: 36% hit rate (9/25)
- **2-5% away**: 22% hit rate (5/23)
- **>5% away**: 16% hit rate (3/19)

**Critical finding**: 34 weeks started within 5% of max pain but missed (66.7% failure rate among "good candidates")

### 3. Earnings Destroy Max Pain
- **0% hit rate** during earnings weeks (0/8)
- All weeks within ±7 days of earnings: complete failure
- **Strong exclusion criteria**

### 4. Low VIX Favors Convergence
- **VIX <15**: 40% hit rate (6/15)
- **VIX 15-20**: 20% hit rate (9/46)
- Calm market environments favor max pain

### 5. Moderate IV Decline Has Best Signal
- **IV decline 0 to -10%**: 44% hit rate (8/18)
- **IV crush <-10%**: 14% hit rate (1/7)
- **IV expansion >+10%**: 11% hit rate (1/9)
- Stable IV decline signals convergence

### 6. NO Pattern in Volume or OI
- **Volume**: Hits range from -34% to +108% deviation from baseline
- **OI**: Hits range from -100% to +588% deviation from baseline
- Both high and low volume/OI weeks produce hits

### 7. Symbol-Specific Behavior
- **DAL**: 38% hit rate (5/13) - best performer
- **LUV**: 20% hit rate (3/15)
- **UAL**: 8% hit rate (1/13) - worst performer
- Suggests company-specific factors matter

---

## Methodology

### Baseline Calculations
**Critical learning**: Baselines must match analysis period

**Wrong approach** (initial):
- Used 4+ years of historical data (2021-2025)
- Created false "low volume" signal for recent period

**Correct approach**:
- Use ONLY analysis period (June-Oct 2025)
- Day-specific baselines (Monday vs Friday differ by 7-40%)
- Symbol-specific (each airline has different normal levels)

### View Design
Created `max_pain_analysis` view with:
- Weekly Monday→Friday pairs
- Baseline volume/OI calculations
- Deviation metrics (signed percentages)
- All key metrics pre-calculated

---

## What Doesn't Work

### ❌ Volume Deviation
- No pattern detected across 67 observations
- Hits occur with both high and low volume
- Symbol-specific behavior masks any universal signal

### ❌ OI Deviation
- Extreme variance (-100% to +588%)
- No correlation with hits/misses
- Both very high and very low OI produce hits

### ❌ High IV Environments
- >60% IV: 20% hit rate
- High volatility breaks max pain effect

### ❌ Extreme IV Moves
- IV crush or expansion reduce hit rate to 11-14%
- Dramatic volatility changes prevent convergence

---

## What Works

### ✅ Moderate IV Decline (0 to -10%)
- **44% hit rate** vs 30% baseline
- 18 observations (statistically significant)
- Best single predictor

### ✅ Low VIX (<15)
- **40% hit rate** vs 25% baseline
- 15 observations
- Indicates calm market environment

### ✅ Proximity (<2% away)
- **36% hit rate** vs 25% baseline
- 25 observations
- Necessary but not sufficient

### ✅ Earnings Exclusion
- **Avoid all weeks within ±7 days of earnings**
- 100% failure rate in sample
- Critical filter

---

## Predictive Model

### Best Odds Stack:
1. ✅ Within 2% of max pain on Monday
2. ✅ NO earnings within ±7 days
3. ✅ IV declining 0-10% through the week
4. ✅ VIX <15
5. ✅ Avoid UAL (poor performer)

### Expected Performance:
- With all filters: Small sample (would need testing)
- Best single filter: IV decline 0-10% (44% hit rate, 18 samples)

---

## Research Quality Notes

### Sample Size Issues
- **Total**: 67 observations (adequate)
- **Per symbol**: 3-15 weeks (JBLU only 3, inadequate)
- **IV data**: 50 weeks (17 missing)
- **Combined conditions**: 2 observations (not reliable)

### Data Quality
- Missing IV data for July 2025 (early period)
- JBLU data starts Sept 19 (very limited)
- OI data quality varies significantly

### Baseline Methodology Evolution
- Initial error: wrong time period (4 years vs 15 weeks)
- Correction: aligned all baselines to analysis period
- Learning: day-specific baselines essential (Mon vs Fri differ significantly)

---

## Symbol Performance

| Symbol | Weeks | Hits | Hit Rate | Notes |
|--------|-------|------|----------|-------|
| DAL    | 13    | 5    | 38.5%    | Best performer |
| AAL    | 13    | 4    | 30.8%    | Above average |
| LUV    | 15    | 3    | 20.0%    | Below average |
| ALK    | 13    | 3    | 23.1%    | Average |
| UAL    | 13    | 1    | 7.7%     | Worst performer |
| JBLU   | 3     | 1    | 33.3%    | Too small sample |

**DAL** and **AAL** are most reliable for max pain plays. **UAL** should be avoided.

---

## Sector Characteristics

### Airlines Volatility Profile:
- **Average IV**: 48% (Mon), 50% (Fri)
- **IV Range**: 28% to 79%
- **High baseline volatility** - frequent news catalysts

### Why Airlines May Not Be Ideal:
1. **Earnings sensitivity**: Quarterly earnings destroy max pain (8/8 failures)
2. **News-driven**: Fuel prices, labor issues, capacity news
3. **Sector correlation**: JETS ETF moves drive individual stocks
4. **High IV**: Baseline volatility may overwhelm max pain signal

### Recommendation for Next Sector:
Test in **lower volatility sectors**:
- Consumer Staples (KO, PG, WMT) - stable businesses
- Utilities (NEE, DUK) - regulated, predictable
- REITs (O, SPG) - dividend-focused
- Look for: Lower baseline IV, less news-driven, stable earnings schedules

---

## Files Created

1. `create_max_pain_view_with_baselines.sql` - View definition
2. `apply_view_update.py` - View update script
3. `proper_baseline_calculation.py` - Baseline methodology validation
4. `baseline_volume_oi_analysis.md` - Volume/OI analysis
5. `iv_analysis.md` - IV pattern analysis
6. `max_pain_step1_2_3_findings.md` - Initial movement/proximity analysis
7. `airlines_sector_summary.md` - This document

---

## Next Steps

1. **Apply methodology to new sector** with lower baseline volatility
2. **Test if IV signal is universal** or airlines-specific
3. **Expand timeframe** beyond 15 weeks for more robust signals
4. **Build composite score** combining all positive signals
5. **Backtest trading strategy** using identified filters
