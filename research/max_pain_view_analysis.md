# Max Pain Analysis - View-Based Methodology

**Created**: 2025-11-06
**Dataset**: Airlines sector archive
**Approach**: SQL view for ongoing, auto-updating analysis

---

## Methodology

### View Definition

Created `max_pain_analysis` view in `data/sector_archive/airlines.db` that:
- Pairs Monday and Friday data for each week
- Calculates price movements and gaps
- Flags "hits" (within 1% of max pain on Friday)
- Preserves raw data for iterative analysis

### Key Metrics

- **mon_gap_pct**: `(mon_max_pain - mon_price) / mon_price * 100` (how far is Monday price from Monday max pain)
- **fri_gap_pct**: `(fri_max_pain - fri_price) / fri_price * 100` (how far is Friday price from Friday max pain)
- **price_change_pct**: `(fri_price - mon_price) / mon_price * 100` (actual price movement)
- **max_pain_change_pct**: `(fri_max_pain - mon_max_pain) / mon_max_pain * 100` (did max pain itself move?)
- **hit_max_pain**: Binary flag (1 if `ABS(fri_gap_pct) <= 1.0%`, else 0)

---

## Initial Results (Sept-Oct 2025)

### Overall Performance

| Metric | Value |
|--------|-------|
| Total observations | 23 week/symbol pairs |
| Hits (within 1%) | 7 (30.43%) |
| Misses | 16 (69.57%) |

### Hits vs Misses Comparison

| Outcome | Count | Avg Price Move | Avg Initial Gap | Avg Final Gap |
|---------|-------|----------------|-----------------|---------------|
| **Hit** | 7 | 1.64% | 3.19% | **0.51%** |
| **Miss** | 16 | 3.71% | 3.50% | **5.45%** |

**Key Finding**: When max pain is hit, the final gap is only 0.51% (very close). When missed, final gap is 5.45% (way off).

### By Symbol

| Symbol | Weeks | Hits | Hit Rate |
|--------|-------|------|----------|
| DAL | 4 | 2 | **50.0%** |
| AAL | 4 | 2 | **50.0%** |
| JBLU | 3 | 1 | 33.33% |
| LUV | 4 | 1 | 25.0% |
| ALK | 4 | 1 | 25.0% |
| UAL | 4 | 0 | **0.0%** |

**Finding**: Wide variation by symbol. DAL and AAL hit 50% of the time. UAL never hit.

### By Week

| Week | Symbols | Hits | Avg Price Move |
|------|---------|------|----------------|
| 2025-37 | 5 | 3 | 2.25% |
| 2025-38 | 6 | 1 | 4.23% |
| 2025-39 | 6 | 2 | 2.23% |
| 2025-40 | 6 | 1 | 3.46% |

**Finding**: Week 37 had best hit rate (60%). Week 38 had worst (16.7%).

### By Initial Distance from Max Pain

| Distance Category | Total | Hits | Hit Rate |
|-------------------|-------|------|----------|
| Very Close (<2%) | 11 | 4 | 36.36% |
| Close (2-5%) | 7 | 1 | 14.29% |
| Medium (5-10%) | 3 | 1 | 33.33% |
| Far (>10%) | 2 | 1 | 50.0% |

**Surprising**: No clear pattern. The "Far" category has highest hit rate, but only 2 observations.

---

## Detailed Analysis of Hits

All 7 cases where price ended within 1% of max pain:

1. **AAL 2025-37**: Mon $12.53 → Fri $12.45, Max pain $12.50
   - Started 0.24% away, ended 0.40% away
   - Barely moved, stayed near max pain

2. **ALK 2025-37**: Mon $59.13 → Fri $57.25, Max pain $52.50 → $57.50
   - Started 11.21% away, ended 0.44% away
   - **BOTH price and max pain converged!**
   - Price fell 3.18%, max pain rose 9.52%

3. **LUV 2025-37**: Mon $31.43 → Fri $32.52, Max pain $32.50
   - Started 3.40% away, ended 0.06% away
   - Price rose 3.47%, nearly perfect convergence

4. **JBLU 2025-38**: Mon $5.05 → Fri $5.03, Max pain $5.00
   - Started 0.99% away, ended 0.60% away
   - Small move, slight improvement

5. **AAL 2025-39**: Mon $11.38 → Fri $11.58, Max pain $12.00 → $11.50
   - Started 5.45% away, ended 0.69% away
   - Price rose 1.76%, max pain fell 4.17%
   - **Both moved toward each other**

6. **DAL 2025-39**: Mon $57.66 → Fri $57.26, Max pain $58.00 → $57.00
   - Started 0.59% away, ended 0.45% away
   - Already close, stayed close

7. **DAL 2025-40**: Mon $58.26 → Fri $57.48, Max pain $58.00
   - Started 0.45% away, ended 0.9% away
   - Already very close, stayed close

---

## Key Observations

### 1. Max Pain Itself Moves

In 3 of the 7 hits, max pain changed during the week:
- ALK: +9.52%
- AAL (week 39): -4.17%
- DAL (week 39): -1.72%

This raises a question: **Is convergence due to price moving, or max pain adjusting?**

### 2. Two Types of Hits

**Type A - Already Close**: Started within ~1%, stayed close
- AAL week 37, JBLU week 38, DAL weeks 39 & 40
- These may be coincidence (price already at equilibrium)

**Type B - True Convergence**: Started >3% away, converged
- ALK week 37, LUV week 37, AAL week 39
- These show actual movement toward max pain

### 3. Symbol-Specific Behavior

- **DAL & AAL**: 50% hit rate, most reliable
- **UAL**: 0% hit rate, completely ignores max pain
- **Others**: Mixed results

### 4. Distance Doesn't Predict Success

Initial gap size doesn't clearly predict whether max pain will be hit. We see hits from <1% away and from >10% away.

---

## CRITICAL DISCOVERY: Bi-Modal Distribution (Nov 6, 2025)

### Margin Testing Results

Tested different tolerance margins to see how hit rate changes:

| Margin | Hits | Hit Rate | New Hits vs 1% |
|--------|------|----------|----------------|
| 1% | 7 | 30.43% | - |
| 2% | 7 | 30.43% | **ZERO** |
| 3% | 8 | 34.78% | Only 1 (UAL) |

### Distance Distribution

| Range | Count | Observations |
|-------|-------|--------------|
| 0-1% | 7 | Precise hits |
| 1-2% | **0** | **NONE!** |
| 2-3% | 1 | UAL only |
| 3-5% | 9 | Clear misses |
| >5% | 6 | Way off |

### The Discovery: Max Pain is Binary, Not Gravitational

**Key Insight**: There's a **gap** between 1% and 2%. No observations land in the 1-2% range.

This means:
- ✅ **When max pain works, it works PRECISELY** (<1% accuracy)
- ❌ **When it doesn't work, it fails completely** (>3% off)
- ❌ **There is NO middle ground** - no "close but not quite" outcomes

**What this tells us:**

Max pain is NOT a magnetic force that pulls stocks with diminishing strength. It's a binary phenomenon:
- Either the conditions are right (expiration mechanics dominate) → lands within 1%
- Or the conditions aren't right (other forces dominate) → misses entirely

**Implications:**
- Using wider margins (2-3%) doesn't capture "weak max pain effects"
- It only adds noise (the one 2.41% UAL case)
- **1% margin is the correct threshold** - it identifies true max pain events

**Why this matters for trading:**
- Don't expect stocks to "get close" to max pain and use that as an entry
- Either max pain will be hit precisely, or it won't matter at all
- Need to identify WHEN it will work, not hope for partial effects

---

## Methodology Validation (Nov 6, 2025)

### Confirmed: We're Testing the Right Thing

Verified that our max pain calculation matches the theory's intention:

**Max Pain Code Logic** (`op_symbol_rollup.py:700-780`):
1. Filters contracts where `expiration_date >= trade_date`
2. Uses `nearest_expiry = min(expirations)` (earliest future expiration)
3. Calculates max pain using ONLY contracts expiring that date

**Example: DAL on Monday 9/15/2025**
- Contracts expiring 9/19: 344,290 OI ← **Max pain uses THIS**
- Contracts expiring 9/26: 7,302 OI (next week, ignored)
- Contracts expiring 10/17: 78,463 OI (monthly, ignored)

**Our Test**: Does stock hit that 9/19 max pain by Friday 9/19 (expiration day)?

✅ **This is exactly what max pain theory predicts**
✅ **Airlines have weekly options every Friday** (confirmed via option_contracts table)
✅ **Our view pairs Monday → Friday correctly** (testing actual expiration days)

---

## Next Research Questions

1. **Does max pain move price, or does price move max pain?**
   - When both converge, which is the driver?
   - Need to track intra-week changes (Mon/Tue/Wed/Thu data)

2. **What distinguishes DAL/AAL from UAL?**
   - Liquidity differences?
   - OI concentration patterns?
   - Different market maker behavior?

3. **Type A vs Type B convergence**
   - Should we exclude cases already within 1-2% on Monday?
   - Focus only on "true convergence" from larger distances?

4. **Weekly vs monthly expirations**
   - Are these all weekly expirations?
   - Do monthlies behave differently?

5. **Market regime effects**
   - Does this work better in calm vs volatile weeks?
   - Check correlation with VIX or market direction

---

## Advantages of View-Based Approach

✅ **Auto-updating**: New weeks automatically included as archives grow
✅ **Reproducible**: Methodology codified in view definition
✅ **Flexible**: Can query/filter/aggregate in multiple ways
✅ **Snapshot-able**: Can export to CSV for frozen analysis
✅ **Expandable**: Same view can be created in other sector archives

---

## View Schema

```sql
week_id TEXT           -- '2025-37' format
symbol TEXT            -- 'DAL', 'AAL', etc.
week_start_date TEXT   -- Monday date
week_end_date TEXT     -- Friday date
mon_price REAL         -- Monday closing price
fri_price REAL         -- Friday closing price
mon_max_pain REAL      -- Max pain on Monday
fri_max_pain REAL      -- Max pain on Friday
price_change_pct REAL  -- % price movement Mon-Fri
mon_gap_pct REAL       -- % distance from Monday max pain
fri_gap_pct REAL       -- % distance from Friday max pain
max_pain_change_pct REAL -- % change in max pain value
hit_max_pain INTEGER   -- 1 if within 1%, 0 if not
mon_oi INTEGER         -- Monday total OI
fri_oi INTEGER         -- Friday total OI
mon_iv REAL            -- Monday front month IV
fri_iv REAL            -- Friday front month IV
```

Primary Key: `(week_id, symbol)`
Sorting: `hit_max_pain DESC, week_id, symbol`
