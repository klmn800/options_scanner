# Sector Rotation Strategy - Future Exploration

**Status:** Deferred to 2026
**Last Updated:** 2025-10-13

## Core Concept

A standalone strategy module that tracks money movement across market sectors to provide directional confidence signals for mixed-signal trade setups and potential arbitrage opportunities.

**Use Case Examples:**
- Symbol signals are mixed, but sector rotation is shifting toward that sector → Increased confidence to enter
- Detecting early rotation from Tech to Utilities → Get ahead of the move

## Key Strategic Questions (Unresolved)

### 1. Options Flow vs. Equity Volume - Which Matters?

**Options Flow (Forward-Looking):**
- Pros: Leveraged positioning, potentially anticipatory, we already excel at tracking
- Cons: Can be noise/hedging, not always "real money"
- Use: Early signal detection (T-5 to T-1 before rotation)

**Equity Volume (Confirmatory):**
- Pros: Actual institutional capital deployment, less noisy
- Cons: Lagging indicator, you're not "early" anymore
- Use: Confirmation signal (T-0 to T+2)

**Working hypothesis (untested):**
- Primary: Options flow as leading signal
- Secondary: Equity volume as confirmation
- Edge: Divergence between the two (options hot but equity cold = early positioning)

**Reality check:** This is trading folklore, not backed by cited research. Needs empirical validation.

### 2. Sector ETFs vs. Symbol Aggregation - Which Signal?

**Sector ETFs (XLK, XLF, XLE, etc.):**
- Pros: Clean market consensus view, complete sector coverage, liquid
- Cons: Cap-weighted (XLK = 25% NVDA+AAPL+MSFT), lags individual name moves

**Our 750 Symbols Aggregated:**
- Pros: Early detection (smart money in names first), industry granularity, already tracking flow
- Cons: Sample bias (large-cap only), noisier, aggregation complexity

**Proposed approach:** Hierarchical layering
1. Layer 1: Sector ETF performance & flow (primary signal)
2. Layer 2: Symbol aggregation (confirmation/divergence)
3. Layer 3: Industry-level breakdown (granular intel)

### 3. What Metrics Actually Predict Rotation?

**Candidates to test:**
- Relative strength vs. SPY (5d/20d/60d)
- Volume metrics (sector ETF volume vs. 20d avg, aggregated symbol volume surprise)
- Options flow (calls vs. puts in sector ETFs)
- Momentum (rate of change, new highs/lows)
- Divergence signals (ETF vs. symbols performance gap)

**Unknown:** Which of these actually correlates with sector rotation? Needs data analysis.

## Proposed Exploratory Analysis (Deferred)

### Phase 1: Does Sector Movement Even Exist?
- Pick 3-4 recent market move dates
- Calculate average daily returns by sector
- Confirm sectors cluster as cohesive units vs. random noise

**Decision point:** If no clustering, abandon approach.

### Phase 2: Can We See Rotation Over Time?
- Rolling 5-day sector returns over 2-3 months
- Look for leadership changes and crossovers
- Assess if moves are tradeable magnitude

**Decision point:** If static hierarchy or random noise, not useful.

### Phase 3: Does Options Flow Predict Rotation?
- Identify 2-3 clear rotation events from Phase 2
- Check existing flow_alerts data leading up to events
- Test for timing relationship

**Decision point:** If no relationship, options might not predict sector rotation.

### Implementation Approach
- Single throwaway exploration script using existing data
- No new infrastructure
- Output: Simple report showing obvious patterns (or lack thereof)
- High bar: "See it with eyeballs, not p-values"
- Only proceed to full PRD if patterns are strong and actionable

## What We'd Build (If Validated)

```
strategies/sector_rotation/
├── sr_main.py              # Main orchestrator
├── sr_etf_tracker.py       # Sector ETF data collection
├── sr_symbol_aggregator.py # Aggregate 750 symbols by sector
├── sr_signal_generator.py  # Detect rotation patterns
└── sr_config.py            # Configuration

Database:
├── sector_etf_daily        # ETF OHLCV + volume metrics
├── sector_etf_flow         # Options flow in sector ETFs
├── sector_summary_daily    # Aggregated metrics per sector
└── sector_rotation_signals # Generated rotation signals
```

## Why Deferred

- Requires 8-12 hours of rigorous exploratory analysis
- Risk of weak/noisy correlations that aren't actionable (52% vs. 50% baseline)
- Need to validate basic premise before investing in infrastructure
- Other priorities take precedence for now

## Next Steps (When Ready)

1. Run Phase 1 exploratory analysis (2 hours)
2. If promising, proceed to Phase 2-3
3. If patterns are clear and strong, create full PRD via AI Dev Tasks workflow
4. Implement incrementally with proper testing

## Open Questions

- Do our 750 symbols provide sufficient sector coverage, or do we need sector ETF data?
- What time horizons matter? (Intraday rotation vs. weekly cycles vs. monthly trends?)
- How to weight symbol aggregation? (Equal-weight vs. cap-weight vs. volume-weight?)
- Integration with existing strategies: Filter only? Confidence modifier? Standalone signals?
- Does sector rotation even matter for options trading with 1-3 week horizons?

## Resources Needed

- Historical sector ETF data (if pursuing that route)
- Sector/industry mappings (we have basic sector in symbol_metadata)
- Time to run proper correlation analysis
- Patience to accept "this doesn't work" if analysis shows no edge

---

**Bottom Line:** Fascinating concept, but needs validation before building. Don't fall in love with the idea—let the data decide.
