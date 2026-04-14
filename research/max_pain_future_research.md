# Max Pain Research - Future Analysis Ideas

**Deferred research directions to revisit later**

---

## 4. OI Concentration Analysis (DEFERRED)

**Theory refinement**: Market makers SOLD options to retail. They profit when options expire worthless. Max pain = strike where most $ of options expire OTM.

**Complex OI landscapes**: If OI is scattered across many strikes, max pain becomes less clear:
- Maybe no single strike makes a big difference
- Trade-offs everywhere (save on calls, lose on puts)
- Harder for MMs to have clear incentive to pin

**Research questions**:
- Is max pain strike usually THE dominant strike by OI?
- Do hits show more concentrated OI distributions?
- What does "concentration" look like? (top strike >20%? Gini coefficient?)
- Does it matter if concentration is on calls vs puts?

**Data available**:
- `top_call_oi`, `top_put_oi`, `top_call_pct_of_total`, `top_put_pct_of_total`
- Could calculate: OI distribution metrics, concentration ratios
- From `option_contracts`: full strike-by-strike OI to build concentration curves

**Need to flesh out**: What metrics actually measure "concentration"? How do we test if it matters?

---

## 5. Market Environment Controls

**Why it matters**: Need to isolate max pain effect from broader market moves.

**Tests to run**:
1. **SPY correlation**:
   - Did SPY move significantly that day?
   - Are hits just following market direction?
   - Compare: Stock move vs SPY move (beta-adjusted)

2. **Sector momentum**:
   - Did all airlines move together?
   - If yes, it's sector flow not max pain
   - Calculate: Correlation of Friday moves across all 6 airlines

3. **IV crush**:
   - Front month IV change Mon→Fri
   - Hits might show more IV crush (options becoming worthless)
   - Expected: Hits have bigger IV drops?

**Data available**:
- `historical_prices` for SPY (if in archive)
- `mon_iv`, `fri_iv` already in view
- Can query all symbols same week for correlation

---

## 6. Time Decay / Expiration Timing

**Hypothesis**: Max pain might work better in certain scenarios.

**Tests**:
- Are hits clustered on actual 0DTE (options expiring THAT day)?
- What if max pain calc uses next week's expiration? (do we have any cases?)
- Monthly vs weekly expiration differences
- Time of day effects (AM vs PM settlement - likely can't test with daily data)

**Need**: Track which expiration date was used for max pain calc (could add to view)

---

## 7. News/Earnings Interference

**Hypothesis**: Max pain works in quiet weeks, fails when news dominates.

**Tests**:
- Check `earnings_events` table for earnings that week
- Check `news_articles` for unusual news volume
- Compare: hits vs misses for presence of catalysts

**Expected**:
- Hits = quiet weeks (no earnings, no major news)
- Misses = catalyst weeks (earnings, guidance, sector news)

**Data available**:
- `earnings_events` table in archives
- `news_articles`, `news_symbol_sentiment` tables
- Can flag weeks with earnings/news and test

---

## 8. Intra-Week Convergence Tracking

**Question**: WHEN does convergence happen?

**Tests**:
- For hits: Track Tue/Wed/Thu prices
- Gradual convergence (Mon→Fri) vs sudden (only Friday)
- For misses: Did they START converging then reverse?

**Why it matters**:
- Gradual = market naturally finding equilibrium
- Sudden Friday spike = possible MM intervention

**Requires**: Expanding view to include Tue/Wed/Thu data (not just Mon/Fri)

---

## 9. Put/Call Ratio Extremes

**Hypothesis**: Extreme directional bias might override max pain.

**Tests**:
- Hits vs misses: Compare put/call ratios
- Do hits have balanced ratios (0.8-1.2)?
- Do misses have extreme ratios (<0.5 or >2.0)?

**Logic**:
- Extreme call buying = bullish pressure overrides max pain
- Extreme put buying = bearish pressure overrides max pain
- Balanced = max pain can dominate

**Data available**: `put_call_ratio` in `option_symbol_summary`

---

## 10. Greeks Exposure Analysis

**Deep dive on hedging mechanics**:

**Delta exposure**:
- Total delta exposure at max pain strike
- Net delta exposure (calls - puts)
- Market makers hedge delta → stock buying/selling

**Gamma exposure**:
- Gamma at max pain strike
- High gamma = amplified hedging activity near that strike
- "Gamma pin" effect

**Why it matters**:
- These measure the ACTUAL hedging pressure
- If theory is true, should correlate with hits

**Complexity**: Requires understanding MM hedging models, may be beyond scope

---

## Priority for Later Sessions

When ready to continue:

**High priority** (next session):
- #3 Volume Analysis (smoking gun test) ← DO THIS NEXT
- #5 Market Environment (SPY correlation, sector momentum)
- #7 News/Earnings (easy to test with existing tables)

**Medium priority**:
- #4 OI Concentration (need to define metrics first)
- #9 Put/Call Ratio (straightforward test)
- #8 Intra-week tracking (requires view expansion)

**Lower priority / Advanced**:
- #6 Time decay effects
- #10 Greeks exposure (complex)

---

**Note**: Focus on finding PATTERNS first, mechanics later. We want to know WHAT works before diving into WHY it works.
