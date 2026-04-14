# Phase 4: Hypothesis Formation

## Observations from 449 Training Winners

### Key Patterns (>70% concentration):
- **Price Range**: 79.7% of winners were at $0.08-0.10 ask (high end of "cheap")
- **DTE Clustering**: 40.3% at 21-25 DTE, 24.5% at 31-40 DTE (combined 65%)
- **Option Type**: 65.7% calls

### Weak Patterns (<30%):
- **Symbol Concentration**: Top 5 symbols only 15.1% (highly diversified)
- **Day of Week**: Monday slightly elevated (30%) but not dominant

### Greek Characteristics:
- Average Delta: 0.0645 (deep OTM, lottery tickets)
- Average IV: 0.3269 (32.7% - moderate volatility)

## Hypothesis #1: "High-End Cheap Calls on Monthly Cycle"

**Theory:**
The edge exists because cheap options at the $0.08-0.10 price point have just enough premium to maintain liquidity, while being affordable for retail scalpers. Calls dominate because retail traders chase upside momentum. The 21-25 DTE sweet spot catches the monthly options cycle while avoiding rapid theta decay.

**Observable Conditions:**
1. **Price**: Ask between $0.08 and $0.10
2. **Option Type**: Calls only (65.7% of winners)
3. **DTE**: 21-40 days (65% of winners combined)
4. **Delta**: < 0.15 (deep OTM, based on avg 0.0645)
5. **Symbol**: Any stock (diversified, no concentration needed)
6. **Entry**: Any day (no clear day-of-week edge)

**Exit Strategy:**
- Target: 25% gross profit
- Stop: End of day 5 or -50%, whichever first

**Expected In-Sample Performance:**
- Capture rate: ~70% of training winners (315 of 449)
- Win rate: Unknown until Phase 5 testing
- EV: TBD

## Hypothesis #2: "21-25 DTE Sweet Spot"

**Theory:**
The tightest clustering is around 21-25 DTE (40% of winners). This suggests the edge might be in the specific timing window rather than price. Options in this range have enough time for moves but are approaching the accelerated theta decay zone, creating opportunity for quick scalps before time decay dominates.

**Observable Conditions:**
1. **DTE**: 21-25 days only (tight focus)
2. **Price**: $0.06-0.10 (include 90% of winners)
3. **Option Type**: Calls preferred but include puts
4. **Delta**: < 0.20
5. **Symbol**: Any stock

**Exit Strategy:**
- Target: 25% gross profit
- Stop: End of day 5 or -50%, whichever first

**Expected In-Sample Performance:**
- Capture rate: ~50% of training winners (181 of 449)
- Win rate: Potentially higher than H1 due to tighter focus
- EV: TBD

## Decision: Test Hypothesis #1

**Reasoning:**
- H1 captures more winners (broader criteria)
- $0.08-0.10 price filter is the strongest single pattern (80%)
- Call-only filter adds conviction (66% of winners)
- DTE 21-40 range balances opportunity and decay
- If H1 fails, H2 can be tested on fresh holdout data later

**Next Step:** Phase 5 - Test H1 on training data to validate capture rate and calculate in-sample win rate/EV.
