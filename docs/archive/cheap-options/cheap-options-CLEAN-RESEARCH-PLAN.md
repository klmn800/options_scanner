# Cheap Options Scalping - CLEAN Research Plan (v2)

**Goal:** Determine if there's a systematic edge in buying cheap options for quick 25% scalps, using proper train/test methodology to avoid data snooping.

**Date:** 2025-10-15
**Previous Attempt:** Failed holdout validation due to optimization on full dataset

---

## CARDINAL RULE

> **OCTOBER DATA IS LOCKED UNTIL FINAL TEST**
>
> Do not query, analyze, or peek at Oct 1-15 data until Phase 6.
> Pretend it doesn't exist.

---

## Data Splits

### Training Period: Aug 18 - Sept 30, 2025
- **Purpose:** Explore, find patterns, form hypotheses
- **Usage:** ALL exploration, parameter analysis, pattern discovery
- **Expected:** ~24 trading days

### Holdout Period: Oct 1 - Oct 15, 2025
- **Purpose:** Validate hypothesis on unseen data
- **Usage:** ONE final test only, no iteration
- **Expected:** ~10 trading days

---

## Phase 1: Define Tradeable Universe (30 min)

**Objective:** Establish broad constraints based on theory, not data.

### Theory-Driven Constraints:
```sql
-- What defines "cheap options" we can realistically trade?
ask >= 0.03 AND ask <= 0.10    -- Cheap but not worthless
dte >= 15 AND dte <= 60        -- Not too close/far from expiry
bid > 0 AND ask > 0            -- Must be tradeable
vega IS NOT NULL               -- Need greeks data
```

### Two Universes To Test:

**Universe A: ETF Options Only**
```sql
symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP')
```

**Universe B: Stock Options Only**
```sql
symbol NOT IN (ETF list above, plus 'VIX')
```

### Tasks:
1. Query training period (Aug 18 - Sept 30) ONLY
2. Count opportunities in each universe
3. Document universe sizes
4. If either universe < 20 entries, abandon that path

### Output:
- Universe A: X entries (Y unique contracts, Z trading days)
- Universe B: X entries (Y unique contracts, Z trading days)
- **DO NOT track outcomes yet** - just count opportunities

**Rule:** If we proceed, focus on whichever universe has more entries.

---

## Phase 2: Identify Winners in Training Data (45 min)

**Objective:** Find all contracts that hit 25% profit target in training period.

### Methodology:
- Entry: First scan each day where contract meets universe criteria
- Exit tracking: Track max(bid, last_price) over next 5 trading days
- Win definition: max_exit >= entry_ask × 1.25 (25% gross)
- **Period:** Aug 18 - Sept 30 ONLY (do not touch October!)

### Tasks:
1. For each entry in training period, track 5-day outcome
2. Classify as winner or loser
3. Calculate basic stats:
   - Win rate
   - Avg winner return
   - Avg loser return
   - Expected value (baseline)

### Output:
- Total entries: N
- Winners: X (W% win rate)
- Losers: Y
- Baseline EV: Z%
- **List of winning contracts** (contract_hash, entry_date, return, days_to_target)

**Success Criteria:**
- Need at least 15 winners to proceed (enough to find patterns)
- If < 15 winners, strategy likely not viable

---

## Phase 3: Pattern Discovery (60 min)

**Objective:** Analyze ONLY the training winners to find common characteristics.

### Do NOT Optimize Parameters

**Instead, answer these questions:**

### 3.1: Symbol Concentration
- Which symbols appear in winners?
- Is there concentration (e.g., 70%+ in 2-3 symbols)?
- Create table: Symbol | Winner Count | % of Winners

### 3.2: Entry Price Distribution
- How many winners at $0.03, $0.04, $0.05, etc?
- Is there a pattern? (cheaper = better? or U-shaped?)
- Create histogram

### 3.3: DTE Distribution
- Bucket winners: 15-20, 21-25, 26-30, 31-40, 41-60
- Where do most winners cluster?
- Create histogram

### 3.4: Greek Characteristics
- Min/max/avg delta of winners
- Min/max/avg vega of winners
- Min/max/avg IV of winners
- Are winners low-delta lottery tickets or higher-delta?

### 3.5: Market Context (CRITICAL - NEW)

For each training winner, query:
- **Underlying price action that entry day:**
  - Open, high, low, close
  - Daily % change
  - Volume vs 20-day average
- **VIX level and change:**
  - VIX at entry
  - VIX 1-day change
- **Market direction:**
  - SPY direction that day (up/down/flat)
  - Was it a trending day or choppy?
- **Day of week**
- **Time of entry** (morning vs afternoon)

### 3.6: Exit Timing
- When did winners hit target? (Day 0, 1, 2, 3, 4, 5)
- How long did opportunity last? (scans at target)
- Morning exits vs afternoon exits?

### Tasks:
1. Pull all contextual data for training winners
2. Create summary tables for each category
3. Look for concentration/patterns visually
4. **Document observations, not rules**

### Output:
A written summary of patterns observed (example format):
```
Observations from [N] training winners:
- X of N (X%) were in [specific symbols or categories]
- X of N (X%) occurred on [specific market conditions]
- X of N (X%) had [specific timing characteristics]
- X of N (X%) were [specific DTE range]
- X of N (X%) happened when [specific context]
- Most common characteristics: [describe]
```

**Rule:** Look for patterns where 70%+ of winners share a characteristic.

---

## Phase 4: Hypothesis Formation (30 min)

**Objective:** YOU (human) translate patterns into testable hypothesis.

### Hypothesis Template:

**Theory:**
> "The edge exists because [market structure reason]"

**Observable Conditions:**
> "We can identify opportunities when [specific, measurable conditions]"

**Example Hypothesis:**

```
THEORY:
Cheap ETF options become momentarily liquid when the underlying
has a strong directional move, as retail traders pile in.
We can buy before spreads tighten and sell when liquidity arrives.

CONDITIONS:
1. Symbol: SPY, QQQ, or XLI (high retail interest)
2. Underlying moved >0.5% in same direction as option (calls on up days, puts on down days)
3. Entry: Within first 2 hours of trading (9:30-11:30 AM ET)
4. Option: 20-35 DTE, ask $0.03-0.08, delta 0.05-0.20 (deep OTM but not worthless)
5. VIX: Down or flat (not spiking, which indicates fear not greed)

EXIT:
- Target: 25% gross profit
- Stop: End of day 5 or -50%, whichever first
```

### Criteria for Good Hypothesis:
- ✓ Based on market structure logic (not just correlation)
- ✓ Uses conditions observed in 70%+ of training winners
- ✓ Specific enough to code
- ✓ Leaves out conditions that were 50/50 (not predictive)

### Output:
1-3 hypotheses to test, ranked by confidence.

---

## Phase 5: In-Sample Validation (45 min)

**Objective:** Test hypothesis on training data to ensure it captures the winners.

### Process:

For each hypothesis:
1. Code the exact conditions
2. Apply to Aug 18 - Sept 30 (training data)
3. Measure:
   - How many entries does it produce?
   - How many of the original 24 winners does it capture?
   - How many new losers does it introduce?
   - What's the win rate?
   - What's the expected value?

### Success Criteria:

**Hypothesis is viable if:**
- Captures 15+ of the original 24 winners (60%+ capture rate)
- Win rate >30% (better than baseline)
- Expected value >5% (positive edge)
- Produces 10-40 entries in training period (not too sparse, not too loose)

**If hypothesis fails:**
- Refine based on what it missed
- OR go back to Phase 4 with different theory
- Iterate until you find one that works

### Output:
```
Hypothesis Test Results (Training Period):

HYPOTHESIS: [description]

Entries: 35
Winners: 18 (51.4%)
Losers: 17 (48.6%)
Avg Winner: +78%
Avg Loser: -22%
Expected Value: +29.2%

Original Winners Captured: 20 of 24 (83%)
Status: PASSES in-sample test
```

**Rule:** Only proceed if hypothesis achieves success criteria above.

---

## Phase 6: HOLDOUT TEST (15 min)

**Objective:** Apply hypothesis to Oct 1-15 data WITHOUT modification.

### The Moment of Truth:

1. **Unlock October data** (first time querying it)
2. Apply exact same hypothesis code (no changes!)
3. Run analysis on Oct 1-15
4. Measure same metrics

### Critical Rules:
- ❌ DO NOT modify hypothesis based on October results
- ❌ DO NOT iterate on October data
- ❌ DO NOT cherry-pick which hypothesis to test (test the one from Phase 5)
- ✓ Report results honestly, even if they fail

### Output:
```
Hypothesis Test Results (Holdout Period):

HYPOTHESIS: [same description]

Entries: X
Winners: Y (W%)
Losers: Z
Avg Winner: +X%
Avg Loser: -X%
Expected Value: +/-X%

Comparison to Training:
- Win Rate: Training 51.4% | Holdout W% | Diff: +/-X%
- Expected Value: Training +29.2% | Holdout +/-X% | Diff: +/-X%
```

### Validation Outcomes:

**PASS (Strategy Validated):**
- Holdout EV > 0
- Win rate within 10 percentage points of training
- EV within 15 percentage points of training
- **Result:** You may have found real edge

**MARGINAL (Investigate Further):**
- Holdout EV > 0 but much lower than training
- Win rate dropped 10-20 percentage points
- **Result:** Possible edge but weak, requires more data

**FAIL (No Edge):**
- Holdout EV ≤ 0
- Win rate dropped >20 percentage points
- **Result:** No systematic edge, hypothesis rejected

---

## Phase 7: Interpretation & Next Steps (30 min)

### If PASS:
1. Document the validated hypothesis
2. Calculate position sizing (Kelly criterion based on holdout EV)
3. Plan paper trading (forward test on Oct 16+ data)
4. Consider live trading with tiny size

### If MARGINAL:
1. Collect more data (extend holdout to Nov-Dec if available)
2. Investigate what changed between training and holdout
3. Refine hypothesis based on new understanding
4. Re-test on extended holdout

### If FAIL:
1. Document why it failed
2. Form new hypothesis based on Phase 3 patterns
3. **If new hypothesis:** Must test on NEW holdout (Nov-Dec)
4. **Cannot re-test on October** - it's burned
5. If no more holdout data, strategy is dead

---

## Timeline

**Total: ~4 hours (focused work)**

| Phase | Time | Checkpoint |
|-------|------|------------|
| 1. Define Universe | 30 min | Universe sizes documented |
| 2. Find Training Winners | 45 min | List of 15-30 winners |
| 3. Pattern Discovery | 60 min | Observations documented |
| 4. Hypothesis Formation | 30 min | 1-3 testable hypotheses |
| 5. In-Sample Validation | 45 min | Hypothesis passes criteria |
| 6. Holdout Test | 15 min | Final validation result |
| 7. Interpretation | 30 min | Go/no-go decision |

---

## Success Metrics

**What "Success" Looks Like:**

### Minimum Viable Strategy:
- Holdout win rate: >30%
- Holdout EV: >5% per trade
- Opportunities: 5-20 per month
- Hypothesis based on sound market structure

### Stretch Goals:
- Holdout win rate: >40%
- Holdout EV: >10% per trade
- Consistency: Similar performance across different months
- Scalability: Works across multiple ETFs

---

## What's Different This Time

### Previous Attempt (Failed):
- ❌ Optimized parameters on full dataset
- ❌ Then tested on subset of same data
- ❌ Win rate dropped significantly on holdout
- ❌ Overfit to noise

### This Attempt (Rigorous):
- ✓ Split data BEFORE any analysis
- ✓ Form hypothesis from training winners only
- ✓ Test ONE hypothesis on holdout (no iteration)
- ✓ Use market structure logic, not parameter optimization
- ✓ Accept failure if hypothesis doesn't generalize

---

## Documentation Requirements

### After Each Phase, Create:

1. **Evidence file:** All query results, tables, charts
2. **Notes file:** What you learned, decisions made, time spent
3. **Code artifacts:** Scripts used (save for reproducibility)

### Final Deliverable:

**If PASS:**
- `cheap-options-validated-strategy.md` (full writeup)
- `strategy-implementation.py` (production code)
- `backtest-results.json` (all test results)

**If FAIL:**
- `cheap-options-rejection-report.md` (why it failed)
- `lessons-learned.md` (what we learned about the data)

---

## Emergency Stop Conditions

**Abort research if:**
- Universe has < 20 entries in training period (insufficient data)
- Training period has < 15 winners (can't find patterns)
- No hypothesis achieves Phase 5 success criteria after 3 attempts
- Holdout test shows EV < -10% (strategy actively harmful)

**In these cases:** Document failure, move on to different research direction.

---

## Ready to Begin?

When ready, start with Phase 1:
- Query Aug 18 - Sept 30 data only
- Count Universe A (ETFs) and Universe B (stocks)
- Report sizes
- Choose which universe to pursue

**Remember:** October doesn't exist yet. Don't even think about it.
