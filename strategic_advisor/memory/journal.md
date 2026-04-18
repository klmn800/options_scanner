# Session Journal

## Session 001 — 2026-04-17

**Focus:** Initial system orientation. Understanding what exists, what data is available, and where the value is (or isn't).

### What I Did

1. Read the full big-to-do-list.md, trading-style.md, and the strategic_planning_loop brainstorm
2. Queried performance.db for OP and FM cycle metrics (last 10 trading days)
3. Deep-dived into flow_alerts profitability data (3,183 alerts, 1,838 with 7-day outcomes)
4. Analyzed alert performance by: score level, score band, DTE, option type, month, scoring version
5. Examined earnings signal outcomes (5 BUY/STRONG BUY events with actual results)
6. Investigated expected_move_pct data quality
7. Read the v3 alert scoring design doc

### Key Findings

**1. Alert scoring is inversely correlated with performance.**
- Score 3.5-4.0: 145.9% avg max 7d profit, 76.5% win rate (51 alerts)
- Score 4.0-5.0: 105.9% avg, 82.5% win rate (40 alerts)
- Score 5.0+: 70.1% avg, 67.7% win rate (1,747 alerts)
- HIGH conviction alerts underperform MEDIUM: 54.0% vs 74.4% avg, same downside (~-17.5%)
- **Caveat:** The 3.5-5.0 band is almost entirely v2 (April 2026), while 5.0+ is mostly v1 (Sept 2025-Mar 2026). Could be market regime, not score quality. Need to control for time period and DTE.

**2. DTE is the strongest predictor of 7-day max profit.**
- 0-7 DTE: 150.9% avg, 87.5% win rate
- 8-14 DTE: 117.0%, 78.0%
- 15-30 DTE: 69.4%, 69.5%
- 31-60 DTE: 49.0%, 61.6%
- This makes options-theory sense (gamma effect) but the scoring system doesn't weight DTE at all currently. v3 design adds DTE as an actionability bonus, but positioned as +0.25/+0.5 points — probably too gentle given the magnitude of the effect.

**3. Profit distribution is extremely right-skewed.**
- Q1: 0.2-19.8% (avg 10.5%)
- Q2: 20-44% (avg 31.0%)
- Q3: 44-92% (avg 64.9%)
- Q4: 92-883% (avg 185.8%)
- Median is ~44%, mean is 73%. Averages are misleading. A few 500-800% outliers pull everything up.

**4. `expected_move_pct` has serious data quality issues.**
- 222 of 763 upcoming events have expected_move_pct > 20% (impossible for earnings)
- 45 have values > 100% (e.g., ENTG at 230%, GEN at 229%)
- The straddle-based metric is fine for these same symbols
- The signal system uses straddle-based relative_underpricing_pct, so signals may be unaffected
- But anything displaying or using expected_move_pct is working with garbage data

**5. 40% of older alerts lack profitability data.**
- 1,298 alerts before April 10 have no max_prof_7d_pct
- Coverage is spotty even for old dates (50-70% per day)
- Likely cause: expired options can no longer be priced

**6. Earnings signal performance is unmeasurable (sample too small).**
- Only 5 BUY/STRONG BUY events with outcomes
- Mixed results: KR marginal win, DOCU intraday win / close loss, CCL loss, GME loss, PDD intraday win / close loss
- Signal recalibrated in April 2026 (6Q recency), so old events used different methodology
- Need ~50+ more events. This quarter's earnings season will be the first real test.

**7. The system's scope dramatically exceeds its use case.**
- 820 symbols, 30+ tables, ~100K rows/FM cycle
- Ben: $4K portfolio, <$300/position, primarily <$60 stocks
- Not inherently wrong (data has R&D value) but worth awareness

**8. No feedback loop from actual trades.**
- All evaluation_status = 'active' (zero human evaluation)
- max_prof_7d_pct measures theoretical max, not realized gain
- No trade journal, no position tracking, no outcome recording
- The v3 design doc starts addressing this with actionability scoring, but the core loop (alert → trade → outcome → learning) is still open

### What Surprised Me

- **v2 scoring (lower threshold) produced better outcomes than v1.** April 2026 alerts average 115% max 7d profit vs 55-82% for prior months. Even accounting for market regime, lowering the threshold didn't add junk — it added value.
- **The system is operationally robust.** OP pipeline: 0 failures, 816-819 symbols collected daily. FM: 38-40 cycles on full days. SSD migration dropped sync times from 50-600s to 10-25s. No operational emergencies.
- **The v3 scoring design is well-reasoned** but doesn't address the fundamental finding that score magnitude doesn't predict outcomes. It adds nuance (flow concentration, V/OI, DTE) but assumes the core scoring axis is valid.

### Self-Assessment

Good first session. I covered a lot of ground but at reasonable depth. The scoring-performance relationship is the strongest finding — quantitative, evidence-backed, and actionable. The expected_move_pct data quality issue is a clear bug worth flagging.

**What I'm uncertain about:** Whether the score-performance inverse is a genuine scoring flaw or a confounded market regime effect. I need to control for DTE and time period before concluding. I also don't understand how the profitability metrics are calculated in detail — I read the evaluator code header but didn't trace the full calculation path.

**What I chose NOT to pursue this session:** Architecture assessment, code quality, database schema coherence, unused features. These are all valid threads but less urgent than understanding whether the core output (alerts, signals) is working.

### Threads to Investigate Next

See `memory/agenda.md` for prioritized list.
