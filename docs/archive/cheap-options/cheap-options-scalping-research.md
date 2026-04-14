# Cheap Options Scalping Strategy - Research Plan

**Strategy Overview:** Buy cheap options ($0.03-0.05) with meaningful vega/delta, hold 1-5 days for 25-50%+ gains.

**Research Goal:** Identify optimal parameter thresholds to maximize win rate and profit within 5-day holding period.

**CRITICAL INSIGHT:** For options scalping, what matters is whether **tradeable moments** occur during the holding period. A wide spread at entry is irrelevant if the bid converges to a profitable exit price even briefly. Set limit orders to capture these moments.

---

## Data Sources & Environment

**Primary Database:** `data/datalake_query.db` (2025-08-18 to 2025-10-15, 35 trading days)
- **IMPORTANT:** This is the query-only database - never writes during analysis
- If locked: Wait 2 mins (sync runs every 20 mins)
- Archives available: `data/archive_2025_09.db`, `data/archive_2025_10.db`

**Primary Table:** `flow_options_scans` (28.1M rows)
- **20-minute intraday scans** throughout trading day
- **CRITICAL COLUMNS:** bid, ask, last_price, volume, open_interest, scan_timestamp
- **GREEKS:** delta, gamma, theta, vega, iv (100% populated for cheap options)
- **ADVANTAGE:** Can track intraday price movements and bid-ask convergence
- **USE CASE:** Track when contracts become sellable (bid hits target price)

**Supplementary Table:** `oi_daily` (1.8M rows)
- End-of-day snapshots only
- Longer historical data if needed
- Same greek columns as flow_options_scans

**Market Context Table:** `market_daily_summary`
- Has `regime_classification` field for Bull/Bear/Sideways
- VIX data for volatility regime analysis

**Symbol Metadata:** `symbol_metadata`
- Sector classification for sector-based analysis

---

## Core Research Questions

### 1. Tradeable Moments Analysis ⚠️ MOST CRITICAL
**Question:** Do profitable exit opportunities occur, even if spreads are wide at entry?

**Why This Matters:**
- Static spread analysis is misleading for options
- Need to track: "Did bid price reach 25%+ profit at ANY point in 5 days?"
- Can use limit orders to capture brief convergence moments

**How to Test:**
```sql
-- For each entry contract, track highest bid price in next 5 days
-- Compare to entry ask price (what we paid)
-- Win = max_bid >= entry_ask * 1.25
```

**Measure:**
- % of contracts where tradeable moment occurred (any 20-min window)
- How long did moment last? (1 scan? multiple scans?)
- When did it occur? (Day 1, 2, 3, 4, 5? Morning/afternoon?)
- Did contracts with wide entry spreads still produce tradeable moments?

**THIS IS THE MAKE-OR-BREAK FINDING**

---

### 2. DTE Optimization
**Question:** What's the optimal DTE range for 5-day holds?

**Test Buckets:**
- 7-14 DTE
- 15-21 DTE
- 22-30 DTE
- 31-45 DTE
- 46-60 DTE

**Measure:**
- Win rate (tradeable moment occurred)
- Avg % gain on winners
- Theta decay impact (avg theta * days)
- Time to tradeable moment

**Hypothesis:** 30-45 DTE balances theta decay vs time for movement

---

### 3. Greek Sensitivity Requirements
**Question:** Which greek combinations predict tradeable moments?

**Vega Thresholds:** 0.005, 0.01, 0.015, 0.02, 0.03+
- Higher vega = more IV sensitivity
- But at what threshold does it matter?

**Delta Thresholds:** 0.01, 0.05, 0.10, 0.15, 0.20+
- Need directional bias to respond to underlying moves
- Too low = lottery ticket, too high = expensive

**Theta Tolerance:** -0.01, -0.02, -0.03, -0.05, -0.10
- Daily decay as % of option price
- At $0.04 with theta=-0.02, that's 50% decay per day!

**Vega/Theta Ratio:**
- Higher ratio = more vega bang per theta buck
- Calculate: ABS(vega) / ABS(theta)

**Measure:**
- Win rate by greek bucket
- Avg gain by greek bucket
- Sample size per bucket (need n>30)

---

### 4. Underlying Price Range Impact
**Question:** Do cheaper/expensive underlyings produce better setups?

**Test Buckets:**
- <$20 (penny stocks, high % moves)
- $20-50 (mid-range)
- $50-100 (larger caps)
- $100-200 (blue chips)
- $200+ (FAANG, etc.)

**Measure:**
- Win rate by price bucket
- Volatility of outcomes
- Correlation with spread width

**Why Test:** Cheaper stocks have bigger % moves but worse liquidity. Need data to decide.

---

### 5. Entry Price Level ($0.03 vs $0.04 vs $0.05)
**Question:** Does entry price level matter?

**Test Separately:**
- $0.03 contracts
- $0.04 contracts
- $0.05 contracts

**Measure:**
- Win rate
- Avg theta as % of premium
- Spread width (both absolute and %)
- Likelihood contract is "dead" (no movement)

**Hypothesis:** $0.04-0.05 better (less likely to be complete garbage)

---

### 6. Moneyness (Delta as Proxy)
**Question:** Do ATM, OTM, or deep OTM perform best?

**Use Delta Buckets:**
- Deep OTM: delta < 0.10
- OTM: delta 0.10-0.30
- Near ATM: delta > 0.30

**Measure:**
- Win rate by moneyness
- Avg gain
- Response to underlying movement

---

### 7. Implied Volatility Level at Entry
**Question:** Does IV level predict success?

**Test Buckets:**
- IV < 0.3 (low)
- IV 0.3-0.5 (normal)
- IV 0.5-0.8 (elevated)
- IV > 0.8 (very high)

**Measure:**
- Win rate by IV bucket
- Vega effectiveness (does high vega matter more in high IV?)

**Hypothesis:** Higher IV = more movement = better for scalps

---

### 8. Market Regime Impact ⚠️ IMPORTANT
**Question:** Does VIX level or market direction affect strategy?

**VIX Buckets:**
- <15 (calm)
- 15-20 (normal)
- 20-30 (elevated)
- >30 (crisis)

**Market Direction:** (from `market_daily_summary.regime_classification`)
- Bull
- Bear
- Sideways

**Measure:**
- Win rate by regime
- Avg gain by regime
- Opportunity count by regime
- Strategy viability boundaries (works in X, fails in Y)

**Hypothesis:** Strategy works in elevated IV, fails in calm markets (fewer movements)

---

### 9. Put vs Call Performance
**Question:** Are puts or calls better in this price range?

**Compare:**
- Win rate: puts vs calls
- Avg gain
- Time to target
- Market regime interaction (puts better in bear markets?)

**Hypothesis:** No significant difference (both viable)

---

### 10. Sector Patterns
**Question:** Do certain sectors produce better cheap options?

**Use `symbol_metadata` table for:**
- Financials
- Energy
- Technology
- Utilities
- Real Estate (REITs)
- Consumer
- Healthcare
- Industrials

**Measure:**
- Win rate by sector
- Opportunity count by sector
- Volatility patterns

**Hypothesis:** High-beta sectors (Energy, Financials) have more movement

---

### 11. Intraday Timing Patterns (NEW - enabled by flow_scans)
**Question:** When do tradeable moments occur?

**Time Windows to Test:**
- Market open: 9:30-10:30 AM
- Mid-morning: 10:30-12:00 PM
- Afternoon: 12:00-15:00 PM
- Power hour: 15:00-16:00 PM

**Measure:**
- When do winners hit target? (distribution across day)
- When do losers show deterioration?
- Does entry timing matter? (contracts entered AM vs PM)
- Spread behavior by time of day

**Hypothesis:** Winners hit fast (Day 1-2, unknown time of day - MUST TEST)

---

### 12. Time to Tradeable Moment
**Question:** How quickly does opportunity occur? How long does it last?

**Track:**
- Days until target hit (Day 0, 1, 2, 3, 4, 5)
- Hours/scans when bid >= target price
- Duration of opportunity (1 scan? 5 scans? all day?)

**Measure:**
- Distribution of time-to-target
- Persistence of opportunity
- Practical fill likelihood

**Critical for:** Understanding if limit orders are realistic

---

### 13. Loss Patterns & Stop Loss
**Question:** What characterizes losers? When to cut?

**Test Cut Points:**
- -25%
- -50%
- -75%

**Track:**
- Contracts that never recovered
- Theta decay pattern on losers
- Early warning signs (first day drop, spread widening?)
- Intraday deterioration patterns

**Measure:**
- Optimal stop loss level (maximize total P&L)
- False stop-outs (cut at -50%, then rebounds?)

**Hypothesis:** -50% stop loss balances protection vs false exits

---

### 14. Profit-Taking Strategy
**Question:** Exit at 25%, or let winners run?

**Test Strategies:**
1. Exit at 25% (immediate)
2. Exit at 50%
3. Trailing stop: 10% from peak
4. Trailing stop: 15% from peak
5. Trailing stop: 20% from peak

**Measure:**
- Total P&L per strategy
- Win rate per strategy
- Time in trade
- Max favorable excursion (how high did winners go?)

**Use intraday data to:**
- Detect when contracts "peaked"
- Measure give-back from peak to EOD

**Hypothesis:** 25-50% quick exit beats letting run (theta decay risk)

---

### 15. Liquidity & Volume Requirements
**Question:** Do volume/OI thresholds predict success?

**Test Buckets:**
- Volume: 0-5, 5-10, 10-25, 25-50, 50+
- OI: 0-100, 100-500, 500-1000, 1000-5000, 5000+

**CRITICAL:** Don't assume low liquidity = bad
- Test: Do low-liquidity winners still show tradeable moments?
- Test: Is price movement real or just noise?

**Measure:**
- Win rate by liquidity bucket
- Spread width correlation
- Price continuity (day-to-day gaps?)
- Unique symbols vs correlated strikes

**Hypothesis:** Volume/OI matters less than assumed if moments occur

---

## Research Methodology - REVISED FOR RIGOR

### Phase 1: Universe Definition & Data Quality (30 min)
**Scheduled: 11:00 AM - 11:30 AM**

**AT START OF PHASE:**
1. Create `docs/cheap-options-research-NOTES.md`
2. Create `docs/cheap-options-research-EVIDENCE.md`
3. Log phase start time in NOTES.md

**Base Criteria (Start Here):**
```sql
-- Base universe query
SELECT * FROM flow_options_scans
WHERE trade_date >= '2025-08-18'
  AND last_price >= 0.03 AND last_price <= 0.05
  AND dte >= 30
  AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')
  AND bid > 0 AND ask > 0
  AND vega IS NOT NULL
  AND delta IS NOT NULL
```

**Document:**
1. Total scans, unique contracts, unique symbols, trading days
2. Greek data completeness (verify)
3. Date gaps or missing data
4. Sample sizes per parameter combination
5. Distribution of contracts by date, symbol, price level

**Output:** Evidence Table 1 - Universe Statistics

**BEFORE ENDING PHASE:**
1. Check actual time
2. If before 11:30 AM: Expand analysis (more date breakdowns, symbol analysis, etc.)
3. Document iterations in NOTES.md
4. Only proceed when 11:30 AM or Ben approves early completion

---

### Phase 2: Tradeable Moments Analysis (45 min) ⚠️ CRITICAL
**Scheduled: 11:30 AM - 12:15 PM**

**AT START OF PHASE:**
1. Log phase start time in NOTES.md
2. Review Phase 1 findings before proceeding

**For each contract meeting base criteria:**
1. **Identify entry points:** First scan where criteria met on EACH trading day
   - Not first scan of day, but first scan where contract qualifies
   - If contract meets criteria at 10am and still meets at 2pm = one entry (the 10am)
   - If contract meets criteria Monday and Tuesday = two entries (one each day)
   - Example: XYZ $50C qualifies Sep 23 (11am), Sep 24 (2pm), Sep 25 (10am) = 3 entries
   - Rationale: Simulates realistic monitoring - enter when criteria triggers, once per day max
2. Record entry_ask (what we pay to enter) at that first qualifying scan
3. Track all scans in next 5 trading days FROM THAT ENTRY
4. Find max_bid in that 5-day window
5. Calculate: (max_bid - entry_ask) / entry_ask = peak_return
6. Subtract fees: peak_return - (0.08 / entry_ask) = net_return
7. Define win: net_return >= 0.25 (25% profit after fees)

**Build Analysis Dataset:**
- contract_hash
- entry_date
- entry_scan_timestamp
- entry_ask
- entry_bid
- entry_spread_pct
- max_bid_in_5d
- max_bid_timestamp
- peak_return_pct
- days_to_peak
- scans_at_target (how long opportunity lasted)
- winner (boolean: peak_return >= 0.25)

**Aggregate Statistics:**
- Overall win rate
- Avg return on winners
- Avg return on losers
- Time-to-peak distribution
- Opportunity duration distribution

**Output:** Evidence Table 2 - Tradeable Moments Summary

**BEFORE ENDING PHASE:**
1. Check actual time
2. If before 12:15 PM: Expand analysis (more contract samples, different entry definitions, etc.)
3. Document iterations in NOTES.md
4. Only proceed when 12:15 PM or Ben approves early completion

---

### Phase 3: Parameter Sweep (90 min)
**Scheduled: 12:15 PM - 1:45 PM**

**AT START OF PHASE:**
1. Log phase start time in NOTES.md
2. Review Phase 2 findings to guide parameter testing

**For each parameter (DTE, greeks, underlying price, etc.):**
1. Segment data into buckets
2. Calculate win rate per bucket
3. Calculate avg gain per bucket
4. Calculate sample size per bucket (flag if n<30)
5. Document any patterns or inflection points

**Statistical Tests:**
- Chi-square for win rate differences
- T-tests for mean return differences
- Note: With large sample, most will be "significant" - focus on effect size

**Output:** Evidence Table 3 - Parameter Sensitivity Matrix

**BEFORE ENDING PHASE:**
1. Check actual time
2. If before 1:45 PM: Test more parameters, finer buckets, interaction effects
3. Document iterations in NOTES.md
4. Only proceed when 1:45 PM or Ben approves early completion

---

### Phase 4: Multi-Variate Analysis (45 min)
**Scheduled: 1:45 PM - 2:30 PM**

**AT START OF PHASE:**
1. Log phase start time in NOTES.md
2. Review Phase 3 findings to identify key predictors

**Test Interaction Effects:**
- Vega + DTE combination
- Delta + IV combination
- Underlying price + Volume combination
- Market regime + Greek combination

**Build Simple Scoring Model:**
- Use top 3-5 predictive parameters
- Weight by importance
- Validate on holdout (most recent 2 weeks)

**Output:** Evidence Table 4 - Multi-Factor Model Performance

**BEFORE ENDING PHASE:**
1. Check actual time
2. If before 2:30 PM: Test more combinations, validate on different time periods
3. Document iterations in NOTES.md
4. Only proceed when 2:30 PM or Ben approves early completion

---

### Phase 5: Practical Constraints (30 min)
**Scheduled: 2:30 PM - 3:00 PM**

**AT START OF PHASE:**
1. Log phase start time in NOTES.md
2. Review Phase 4 model to guide filter selection

**Apply Real-World Filters:**
1. What's the tradeable universe size with optimal filters?
2. How many unique symbols? (diversification)
3. How many opportunities per day?
4. What's the capital deployment capacity?

**Test Scenarios:**
- Conservative filters (high confidence)
- Moderate filters (balanced)
- Aggressive filters (more opportunities)

**Output:** Evidence Table 5 - Daily Opportunity Analysis

**BEFORE ENDING PHASE:**
1. Check actual time
2. If before 3:00 PM: Test more filter scenarios, analyze edge cases
3. Document iterations in NOTES.md
4. Only proceed when 3:00 PM or Ben approves early completion

---

### Phase 6: Final Report Writing (60 min)
**Scheduled: 3:00 PM - 4:00 PM**

**AT START OF PHASE:**
1. Log phase start time in NOTES.md
2. Review all EVIDENCE.md tables and NOTES.md entries
3. Create `docs/cheap-options-scalping-research-FINDINGS.md`

**Structure: Narrative First, Evidence in Back**

**Executive Summary (1 page):**
- Is strategy viable? Yes/No with confidence level
- Key findings (3-5 bullets)
- Recommended filters
- Expected performance (win rate, avg gain, opportunities/day)
- Capital requirements

**Findings Narrative (5-10 pages):**
- Tell the story of what the data revealed
- Focus on TRADEABLE MOMENTS as core insight
- Each major finding gets: [Finding + Evidence Citation + Interpretation]
- Use clear language, avoid jargon
- Be honest about limitations and unknowns

**Evidence Appendix (20-30 pages):**
- All data tables referenced in narrative
- Full query results
- Statistical test outputs
- Sample records showing examples
- Each table numbered for citation (Table 1, Table 2, etc.)

**Implementation Guide (2-3 pages):**
- Exact screening SQL query
- Entry rules
- Exit rules
- Position sizing recommendations
- Risk management

**AT 4:00 PM:**
1. Final review of report completeness
2. Ensure all citations reference Evidence tables
3. Log completion time in NOTES.md
4. Report ready for Ben's review

---

## Report Format & Quality Standards

### Writing Standards:
1. **NEVER claim anything without data backing it**
2. **Every assertion must cite an evidence table:** "Win rate was 65% (Table 3)"
3. **Distinguish findings from hypotheses clearly**
4. **Show your work:** Include actual SQL queries used
5. **Be skeptical:** Challenge findings that seem too good

### Narrative Voice:
- Professional but conversational
- Assume reader is skeptical investor
- Focus on "here's what we found" not "here's what we think"
- Acknowledge limitations honestly
- Quantify uncertainty where appropriate

### Citation Format:
```
"Contracts with vega >0.015 showed a 68% win rate compared to
45% for vega <0.01 (Table 3, n=234 vs n=156)."
```

### Evidence Tables Must Include:
- Sample size (n=X)
- Key metrics (win rate, avg gain, etc.)
- Statistical significance where relevant
- Any data quality notes

---

## Success Metrics

**Primary:** Win rate (% of contracts where tradeable moment occurred)

**Secondary:**
- Average return on winners
- Average loss on losers
- Risk-adjusted return: (win% × avg_win) - (loss% × avg_loss)
- Time to tradeable moment (median days)
- Duration of opportunity (can we realistically fill?)
- Daily opportunity count

**Target Thresholds (to be validated with data):**
- Win rate: >60%
- Avg winner: >40%
- Avg loser: <-50%
- Net expectancy: >15% per trade
- Daily setups: 2-5 tradeable contracts

**Minimum Viability:**
- Win rate >55% with tight filters
- At least 10 opportunities/week
- At least 5 unique symbols (diversification)

---

## Known Data Limitations

1. **No actual fill data** - We have bid/ask but not real executions
2. **Spread data is sampled** - 20-min intervals, might miss brief moments
3. **Limited time range** - Only 35 trading days (Aug 18 - Oct 15)
4. **Market regime bias** - What if all data is in one regime?
5. **Survivorship** - Only contracts that made it into flow_scans
6. **Commission impact** - $0.04 per contract on Robinhood (round trip = $0.08)
  - At $0.03 entry: 5.3% of position value
  - At $0.04 entry: 4.0% of position value
  - At $0.05 entry: 3.2% of position value
  - Must factor into profit calculations (need 25% + fees to net 25%)

---

## Next Session Execution Plan

### Start Here:
1. Open `data/datalake_query.db` (if locked, wait 2 min)
2. Run Phase 1: Universe definition query
3. Build Phase 2: Tradeable moments tracking dataset
4. Begin Phase 3: Parameter sweep

### Time Budget & Schedule Discipline:

**Assumed Start Time: 11:00 AM**

**Phase Schedule (MUST FOLLOW):**
- Phase 1: 11:00 AM - 11:30 AM (30 min) - Universe Definition
- Phase 2: 11:30 AM - 12:15 PM (45 min) - Tradeable Moments Analysis
- Phase 3: 12:15 PM - 1:45 PM (90 min) - Parameter Sweep
- Phase 4: 1:45 PM - 2:30 PM (45 min) - Multi-Variate Analysis
- Phase 5: 2:30 PM - 3:00 PM (30 min) - Practical Constraints
- Phase 6: 3:00 PM - 4:00 PM (60 min) - Report Writing
- **Total: 5 hours (end at 4:00 PM)**

**CRITICAL DISCIPLINE RULES:**

1. **Before completing ANY phase:** Check the actual time
2. **If ahead of schedule:** DO NOT move on early. Instead:
   - Re-examine phase with more rigor
   - Test more parameter combinations
   - Increase sample sizes
   - Add more statistical tests
   - Dig deeper into anomalies
   - Document what you expanded and why
3. **If still ahead after expansion:** Pause and report:
   - What you completed
   - How many iterations you did
   - What you expanded in each iteration
   - Why you believe no further expansion is valuable
   - Wait for Ben's review before proceeding
4. **Goal:** Deliver research that survives peer review, not finish quickly

### Working Documents (CREATE IMMEDIATELY):

**1. Research Notes Document:** `docs/cheap-options-research-NOTES.md`
- Created at start of Phase 1
- Track all queries run, results found, patterns observed
- Document each iteration and what changed
- Record anomalies, questions that arise, data quality issues
- **UPDATE CONTINUOUSLY** - memory will fade across context windows
- Structure: Timestamped entries by phase

**2. Evidence Tables Document:** `docs/cheap-options-research-EVIDENCE.md`
- Created during Phase 1-5
- All data tables that will be cited in final report
- Each table numbered (Table 1, Table 2, etc.)
- Include: Query used, sample size, key metrics, notes
- This becomes the appendix in final report

**3. Final Report:** `docs/cheap-options-scalping-research-FINDINGS.md`
- Created in Phase 6
- Narrative + Evidence appendix (from EVIDENCE.md)
- Ready for investor review

**WHY MULTIPLE DOCS:**
- Research spans multiple context windows
- Memory fades - externalize everything
- Notes help assemble final report
- Evidence tables ensure all citations are backed

---

## Research Log

### Session 1: 2025-10-15 - Planning & Discovery

**Major Discoveries:**
1. Found `flow_options_scans` table with bid/ask intraday data
2. Average spread on cheap options = 81% (shocking but testable)
3. Greek data is 100% complete
4. Database has 28M rows spanning 35 trading days

**Initial Validation (9/23-9/30 sample, n=10):**
- Small exploratory sample showed promise
- Mix of winners and losers observed
- Limited by small sample size - need comprehensive analysis

**Critical Insight from Ben:**
"Options scalping is about TIMING. The opportunity to sell doesn't exist until it does. Need to see if those moments occur, how often, how long. Can use limit orders to capture."

This completely reframes the research: Don't focus on entry spread, focus on whether tradeable exit moments occur.

**Analyst Feedback Incorporated:**
- Bid-ask spread is strategy killer (now testing convergence instead)
- Market regime context matters
- Multi-variate combinations are where edge lives
- Count unique symbols, not correlated strikes

**Standards Set:**
- NEVER make claims without data
- Every assertion needs evidence citation
- Distinguish findings/hypotheses/assumptions
- Write for skeptical investor audience

---

## Final Notes for Next Analyst

**You are picking up where planning left off. Here's what you need to know:**

1. **The core question:** Not "what's the spread?" but "do tradeable moments occur?"

2. **Your job:** Run rigorous data analysis to answer 15 research questions, then write professional report

3. **Quality bar is high:** Ben and investors will check your work. Cite everything.

4. **Data is available:** flow_options_scans has everything you need (bid/ask, greeks, intraday)

5. **If db locked:** Wait 2 minutes (sync happens every 20 min)

6. **Come in unbiased:** Let the data reveal the truth - don't assume any target thresholds

7. **Don't speculate:** If you don't have data, say "requires further analysis"

8. **Focus on actionable:** Ben wants a screening tool and clear entry/exit rules

**The data is there. Let it tell you what's real.**
