# OID Stealth Accumulation Alert System

**Status:** Proposed (Not Implemented)
**Date Created:** 2025-10-13
**Priority:** Deferred to next month

---

## Problem Statement

The OID strategy collects rich time-series data showing how options positions build over multiple days, but we currently lack logic to surface these "stealth accumulation" patterns to the morning_view discovery list.

**Gap:** Flow Monitor catches explosive single-day moves, but misses:
- Multi-day quiet accumulation (positions building over 3-10 days)
- Strike clustering (coordinated positioning across multiple strikes)
- Low-volume OI growth (positions being held, not day-traded)
- Symbol-level conviction shifts (from NEUTRAL to BULLISH/BEARISH)

**Example Case:**
- **MU 172.5C (exp 2025-10-03)**: Built from 20 OI → 6,792 OI over 9 days (340x growth)
- **Symbol Level**: MU shifted from NEUTRAL/LOW conviction to BULLISH/HIGH conviction
- **Stealth Factor**: Multi-day accumulation rather than single explosive day
- **Current Status**: Not surfaced in morning_view (no alert logic exists)

---

## Available Data

### Contract-Level Fields (daily_analysis_options_curated)
```
Time Series Data:
- open_interest, oi_change_1d, oi_change_3d, oi_change_5d
- building_unwinding (BUILDING/STABLE/UNWINDING)
- oi_momentum_contract_specific
- concentration_ratio (% of total symbol OI)
- days_tracked

Volume Context:
- total_volume, volume_vs_avg_5d, volume_vs_avg_20d
- volume_surge_factor
- liquidity_score

Greeks & Pricing:
- delta, gamma, theta, vega, implied_volatility
- close_price, bid_ask_spread_percent

Catalyst Context:
- earnings_proximity_days
- pre_earnings_iv_expansion_phase
```

### Symbol-Level Fields (daily_analysis_symbol_curated)
```
Directional Signals:
- direction_bias (BULLISH/BEARISH/NEUTRAL)
- conviction_level (LOW/MEDIUM/HIGH)
- put_call_oi_ratio, oi_bias_percent

Time Bucket Distribution:
- oi_0_7_days_percent, oi_8_21_days_percent, etc.
- dominant_time_bucket
- short_vs_long_bias

Volume Context:
- volume_vs_20d_avg, volume_surge_factor
- active_alerts_count
```

---

## Proposed Scoring System

### Contract-Level Scoring (0-100 points)

#### 1. Persistent Accumulation (40 points)
**What it detects:** Multi-day OI growth without massive single-day spikes

```python
def score_persistent_accumulation(contract_history):
    """
    Criteria:
    - 3+ consecutive days with building_unwinding='BUILDING'
    - Each day adds ≥100 contracts OR ≥10% growth
    - No single day exceeds 50% of total growth (avoids flow overlap)

    Scoring:
    - 3+ consecutive BUILDING days: +20 points
    - 5+ consecutive BUILDING days: +20 points (total 40)
    - True stealth (max single day <50% of total): +20 bonus
    """
    score = 0
    if consecutive_building_days >= 3:
        score += 20
    if consecutive_building_days >= 5:
        score += 20
    if max_single_day_pct < 50% and total_growth_pct > 100%:
        score += 20  # True stealth bonus
    return min(score, 40)
```

#### 2. Absolute OI Magnitude (20 points)
**What it detects:** Large positions indicating institutional interest

```python
if current_oi >= 5000:
    score += 20
elif current_oi >= 2000:
    score += 15
elif current_oi >= 1000:
    score += 10
elif current_oi >= 500:
    score += 5
```

#### 3. Strike Clustering (15 points)
**What it detects:** Coordinated positioning across multiple strikes

```python
# Check: Do 3+ strikes within ±5% all show BUILDING status?
# Same expiration, same option_type
if strikes_building_in_cluster >= 3:
    score += 15
elif strikes_building_in_cluster >= 2:
    score += 10
```

**Implementation note:** Query all contracts for same symbol/expiration/type, group by strike proximity.

#### 4. High Concentration Ratio (10 points)
**What it detects:** Significant % of symbol's total OI in single contract

```python
# concentration_ratio = this contract's OI / total symbol OI
if concentration_ratio >= 0.05:  # 5%+ of total
    score += 10
elif concentration_ratio >= 0.03:
    score += 7
elif concentration_ratio >= 0.02:
    score += 5
```

#### 5. Low Volume / High OI Ratio (15 points)
**What it detects:** Positions being held (conviction) vs day-traded

```python
# Compare recent avg daily volume vs OI change
volume_vs_oi_ratio = avg_daily_volume_5d / abs(oi_change_3d)

if volume_vs_oi_ratio < 1.5 and oi_change_3d > 0:
    score += 15  # Very stealthy - OI growing without much volume
elif volume_vs_oi_ratio < 3.0:
    score += 10
```

---

### Symbol-Level Filters (Qualification Gates)

**Contract must pass ONE of these to be eligible for scoring:**

```python
# 1. Conviction shift (past 5 days)
if conviction_level changed from 'LOW' to 'MEDIUM'+ in last 5 days:
    eligible = True

# 2. Directional bias flip
if direction_bias changed from 'NEUTRAL' to 'BULLISH'/'BEARISH':
    eligible = True

# 3. Put/Call ratio shift
if abs(put_call_oi_ratio_5d_change) >= 0.15:  # e.g., 0.95 → 0.65
    eligible = True

# 4. High absolute call or put OI (large symbols)
if total_call_oi >= 100000 OR total_put_oi >= 100000:
    eligible = True

# If none of above met, skip contract (no alert)
```

---

### Alert Thresholds

```python
ALERT_THRESHOLD = 60  # Minimum score for morning_view inclusion

if oid_score >= 80:
    priority = "HIGH"
elif oid_score >= 70:
    priority = "MEDIUM"
elif oid_score >= 60:
    priority = "LOW"
else:
    priority = None  # No alert
```

---

## Example Scoring: MU 172.5C

**Contract:** MU $172.50 Call, exp 2025-10-03
**Period:** 2025-09-16 to 2025-09-26

### Time Series Data
```
Date       | OI    | Change | Status
-----------|-------|--------|----------
2025-09-16 | 20    | --     | STABLE
2025-09-17 | 86    | +66    | BUILDING
2025-09-18 | 144   | +58    | BUILDING
2025-09-19 | 4,733 | +4,589 | BUILDING  ← Large spike
2025-09-22 | 4,781 | +48    | STABLE
2025-09-23 | 5,375 | +594   | BUILDING
2025-09-24 | 5,714 | +339   | STABLE
2025-09-25 | 6,792 | +1,078 | BUILDING
2025-09-26 | 6,771 | -21    | STABLE
```

### Score Breakdown

**1. Persistent Accumulation: 35/40**
- ✅ 6 consecutive BUILDING days: +20
- ✅ 5+ days: +20 (total 40)
- ❌ Stealth penalty: Largest day (9/19) = 4,589/6,792 = 68% of total growth
- **Issue:** Single large day (9/19) exceeds 50% threshold

**2. Absolute Magnitude: 20/20**
- ✅ Final OI = 6,792 (well above 5,000 threshold)

**3. Strike Clustering: TBD/15**
- Need to check neighboring strikes (170, 175, etc.) for same expiration

**4. Concentration Ratio: TBD/10**
- Need: MU total_call_oi on those dates to calculate ratio

**5. Low Volume/High OI: 15/15** (estimated)
- OI building over 9 days suggests holding vs day-trading

### Symbol-Level Qualification: ✅ PASSED
- Conviction: LOW → HIGH
- Direction: NEUTRAL → BULLISH
- P/C Ratio: 0.96 → 0.65 (30% shift)

### Estimated Total Score: **70-85**
**Priority:** MEDIUM to HIGH (would appear in morning_view)

---

## Open Questions for Implementation

### 1. Single-Day Spike Handling
**Question:** Should we penalize or exclude contracts with one massive day?
- **Pro exclusion:** MU's +4,589 day likely would've triggered Flow Monitor
- **Pro inclusion:** Flow Monitor might have missed it (worth double-checking)
- **Suggested approach:** Check if `active_alerts_count` increased on spike day. If yes = Flow caught it, reduce score. If no = Flow missed it, keep full score.

### 2. Minimum Tracking Period
**Question:** How many days of history before alerting?
- **Option A:** Require 3+ days (avoid premature alerts)
- **Option B:** Require 5+ days (only well-established patterns)
- **Trade-off:** Longer = fewer false positives, but later entry prices

### 3. Expiration Proximity Weighting
**Question:** Should near-term expirations score differently?
- **Option A:** Boost score for <7 DTE (urgency factor)
- **Option B:** Reduce score for <3 DTE (too late for entry)
- **Option C:** Treat all DTE equally (just detect the pattern)

### 4. Price Action Alignment
**Question:** Should stock direction matter?
- **Require alignment:** Calls + stock up, Puts + stock down
- **Allow divergence:** Sometimes OI builds *before* the move
- **Suggested approach:** Track as context (show in UI) but don't filter

### 5. Morning View Capacity
**Question:** How many OID alerts per day is useful?
- **Top 5:** Only highest conviction
- **Top 10:** Balanced discovery list
- **Top 20:** Comprehensive but noisy
- **Dynamic:** Top N based on scores ≥80?

### 6. Deduplication with Flow Monitor
**Question:** How to handle overlaps?
- **Option A:** Suppress OID alert if contract already has active Flow alert
- **Option B:** Show both, but tag as "Also caught by Flow"
- **Option C:** Merge into single alert with dual tags

---

## Implementation Roadmap (When Ready)

### Phase 1: Data Validation
1. Verify all required fields populated in `daily_analysis_options_curated`
2. Check `oi_change_1d`, `oi_change_3d`, `oi_change_5d` calculation accuracy
3. Confirm `building_unwinding` logic is reliable
4. Validate `concentration_ratio` calculations

### Phase 2: Scoring Module
1. Create `strategies/oi_delta/oid_alert_scorer.py`
2. Implement contract-level scoring functions
3. Implement symbol-level qualification gates
4. Add unit tests with known examples (like MU case)

### Phase 3: Integration
1. Add scoring step to OID morning pipeline
2. Insert alerts into `flow_alerts` table (or new `oid_alerts` table?)
3. Tag alerts with `alert_source='OID_STEALTH'`
4. Update morning_view to display OID alerts

### Phase 4: Tuning
1. Run scoring on historical data (Sept-Oct 2025)
2. Review top 20 alerts per day - do they make sense?
3. Adjust thresholds based on false positive rate
4. Decide on final answers to open questions

---

## Data Requirements Check

### Required Fields (verify populated)
- [ ] `daily_analysis_options_curated.oi_velocity` - **Currently NULL** (0/11,260 rows)
- [x] `daily_analysis_options_curated.oi_momentum_contract_specific` - Populated (10,405/11,260)
- [x] `daily_analysis_options_curated.building_unwinding` - Populated
- [x] `daily_analysis_options_curated.concentration_ratio` - Populated
- [x] `daily_analysis_symbol_curated.conviction_level` - Populated
- [x] `daily_analysis_symbol_curated.direction_bias` - Populated

**Note:** `oi_velocity` field is not currently populated. May need to calculate or determine if needed for scoring.

---

## Related Files

**Existing OID Strategy:**
- `strategies/oi_delta/oid_main.py` - Main entry point
- `strategies/oi_delta/oid_config.py` - Configuration
- `strategies/oi_delta/curate/` - Data curation pipeline

**Flow Monitor (for comparison):**
- `strategies/flow_monitor/fm_alert_detector.py` - Alert detection logic
- `strategies/flow_monitor/fm_scoring.py` - Significance scoring

**Morning View (consumer):**
- `morning_view/mv_main.py` - TUI application
- `morning_view/mv_discovery_tab.py` - Discovery list rendering

---

## Next Steps (When Resuming)

1. **Review this document** and answer open questions
2. **Validate data quality** - check if required fields are reliably populated
3. **Create scoring module** with example cases
4. **Test on historical data** (Sept-Oct 2025) to tune thresholds
5. **Integrate into morning pipeline** and morning_view
6. **Monitor for 1-2 weeks** and adjust based on real-world usage

---

**Last Updated:** 2025-10-13
**Author:** Claude (via Ben's request)
**Status:** Documented and ready for future implementation
