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

**7. ~~The system's scope dramatically exceeds its use case.~~ WRONG.**
- Ben clarified: the broad data collection is intentional — for backtesting, R&D, pattern analysis, future ML. Not overbuilt.
- His portfolio and position sizes have grown significantly since trading-style.md was written. Now trades options up to ~$160 symbols.

**8. No trade journal, but theoretical evaluation exists.**
- All evaluation_status = 'active' (zero human evaluation)
- max_prof_7d_pct measures theoretical max — Ben's preferred model: "if a signal was followed and played perfectly, profits could have been X"
- He's open to proposals for BETTER theoretical evaluation, not necessarily a manual trade journal
- The right question isn't "why no journal?" but "how can the existing theoretical metrics be more useful?"

### What Surprised Me

- **v2 scoring (lower threshold) produced better outcomes than v1.** April 2026 alerts average 115% max 7d profit vs 55-82% for prior months. Even accounting for market regime, lowering the threshold didn't add junk — it added value.
- **The system is operationally robust.** OP pipeline: 0 failures, 816-819 symbols collected daily. FM: 38-40 cycles on full days. SSD migration dropped sync times from 50-600s to 10-25s. No operational emergencies.
- **The v3 scoring design is well-reasoned** but doesn't address the fundamental finding that score magnitude doesn't predict outcomes. It adds nuance (flow concentration, V/OI, DTE) but assumes the core scoring axis is valid.

### Self-Assessment

Good first session. I covered a lot of ground but at reasonable depth. The scoring-performance relationship is the strongest finding — quantitative, evidence-backed, and actionable. The expected_move_pct data quality issue is a clear bug worth flagging.

**What I'm uncertain about:** Whether the score-performance inverse is a genuine scoring flaw or a confounded market regime effect. I need to control for DTE and time period before concluding. I also don't understand how the profitability metrics are calculated in detail — I read the evaluator code header but didn't trace the full calculation path.

**What I chose NOT to pursue this session:** Architecture assessment, code quality, database schema coherence, unused features. These are all valid threads but less urgent than understanding whether the core output (alerts, signals) is working.

### Session 001 Continuation (after Ben Q&A)

Ben clarified several things (recorded in `observations/003_ben_context.md` and updated in-place above). Key corrections:
- Portfolio is much larger now, trades up to $160 symbols
- Broad data collection is intentional (R&D, backtesting, future ML)
- He prefers theoretical evaluation ("if played perfectly") over manual trade journals
- v2 + SSD = new era; previous data may be less useful

With remaining context, I ran the **DTE-controlled scoring analysis** and got a clean result:
- Within v1-only alerts, within the same DTE band, higher scores consistently produce lower average max profit
- Pattern holds in 8 of 9 cells. NOT a confound.
- Win rates are flatter — score predicts reliability slightly, not magnitude
- Root cause: higher scores = more premium = more expensive options = smaller % swings
- This is a confirmed, proposal-worthy finding. See updated `observations/001_scoring_vs_performance.md`.

### DTE-Controlled Scoring Analysis (A1 Deep Dive)

Ran the definitive test: v1-only alerts (same scoring version, Sept 2025-March 2026), partitioned by DTE band, comparing score bands 6.0-7.0 vs 7.0-8.0 vs 8.0+. **Result: higher scores consistently produce lower average max profit within the same DTE band.** Pattern holds in 8 of 9 cells. This is NOT a confound — it's a genuine property of the scoring system.

Key insight: the score measures "how much institutional money moved" (premium + volume surprise). More money = more expensive options = smaller percentage swings. Score predicts RELIABILITY (win rates are flat 60-81%), not MAGNITUDE.

### expected_move_pct Root Cause (A2 Deep Dive)

Traced end-to-end through source code. `iv_front_month` in `op_symbol_rollup.py` is a simple average of contract IVs with 0-21 DTE. 0-DTE contracts on illiquid names have IVs of 9.0-10.0+ (Black-Scholes diverges at time→0). This contaminates the average. The `expected_move_pct` formula then multiplies by 100 assuming decimal input, producing values >200%. AAPL doesn't have this problem because its 0-DTE options stay liquid enough for stable IV. Fix: filter DTE < 1 from IV averaging. Signal system already isolated (2026-04-15 fix).

### Session 002 Plan

Draft a proposal bundling the scoring and data quality findings. Both are confirmed, evidence-backed, and actionable. The proposal should address:
1. The 0-DTE IV contamination fix (small, targeted)
2. The scoring-magnitude insight and implications for v3 design
3. Whether DTE should have more weight in the scoring formula

### Threads to Investigate Next

See `memory/agenda.md` for prioritized list.

---

## Session 002 — 2026-04-18

**Focus:** Draft first proposal (signal quality bundle), understand evaluator mechanics, track earnings season performance, start unused data audit.

### What I Did

1. Read evaluator code (`fm_evaluator.py`) end-to-end — now fully understand how max_prof_7d_pct is computed
2. Discovered a new critical data quality issue: 50% of STRONG BUY earnings signals are false positives from stale/illiquid straddle data
3. Investigated root causes: stale option_contracts data (weeks old for some symbols), illiquid ATM strikes with stale `last_price` values
4. Wrote **Proposal 001: Signal Quality Bundle** — bundles all three findings (stale straddle, scoring-magnitude, 0-DTE IV)
5. Manually calculated earnings move outcomes using historical_prices for 11 recent BUY/STRONG BUY/WATCH events
6. Started earnings signal tracking framework (`memory/earnings_signal_tracker.md`)
7. Started unused data audit — identified 6 tables with 0-53 rows (social_posts, symbol_ai_council, agent tables)
8. Checked evaluator coverage: 58% of alerts have 7d profitability data, consistent across v1/v2

### Key Findings

**1. FALSE STRONG BUY SIGNALS (Critical, new finding)**
- 5 of 10 STRONG BUY earnings signals for upcoming events are based on garbage straddle data
- EXAS: 9,082% underpricing with straddle of 0.09% — option data from March 20 (28 days stale)
- Root cause: `get_straddle_expected_move()` uses MAX(trade_date) from historical_prices, which can be weeks old. COALESCE in the UPDATE means stale values persist forever.
- Second issue: uses `last_price` which can be from a stale trade on an illiquid strike. APLS $41 strike has last_price=$0.05 with bid=$0.00 — clearly not a live market.
- Impact: top STRONG BUY signals are garbage, burying legitimate signals (UNH, MMM, AES)

**2. EVALUATOR MECHANICS (A1b resolved)**
- `max_prof_7d_pct` = max option price in 0-168 hour window (from `flow_options_scans`) vs alert-time option price
- Alert option price: first tries `premium_value / (volume * 100)`, falls back to midpoint/last/bid
- All evaluation comes from `flow_options_scans` — only FM-scanned symbols (388/820) have intraday data
- 58% coverage is structural, not a bug — contracts outside scan range, expired early, or no valid pricing data

**3. EARLY EARNINGS SIGNAL PERFORMANCE (11 events)**
- BUY signals: 3/3 beat straddle expected move (100%). All moved 4-6% vs 2.9-3.8% straddle.
- STRONG BUY: 1/3 clear beat (FAST -6.85% vs 2.73%), 1 match (ERIC), 1 miss (INFY).
- WATCH: 1/5 beat straddle (ABT surprised at -6.00%).
- Too early for conclusions but BUY is looking strong. STRONG BUY is mixed.
- Need 30+ events. Set up tracking framework for ongoing monitoring.

**4. UNUSED DATA AUDIT (started)**
- `social_posts` (0 rows) — social posting feature never activated
- `symbol_ai_council` (0 rows) — Morning View AI council never populated
- Agent tables: `agent_actions` (53), `flow_contract_trackers` (49), `flow_tracker_updates` (4) — barely used
- `option_contracts_corrupt_20260407` — recovery table, should be cleaned up
- Not alarming — some features built ahead of need. But worth tracking for future simplification.

**5. POST-EARNINGS CALC PIPELINE GAP**
- Zero April events have earnings_moves data despite WFC being T+4
- Post-earnings calc ran April 17 but only computed historical backfills (RKLB, LUNR, FLY)
- Not clear if this is a sync timing issue or a pipeline bug
- NOTE FOR BEN: check if this week's earnings events get moves data after the next pipeline run

### Self-Assessment

Strong session. The stale straddle finding is the highest-value discovery — it directly impacts trading decisions right now and has a clear, small fix. The proposal bundles three confirmed findings with evidence and specific fix recommendations.

I'm building the right kind of analytical infrastructure. The earnings tracker will pay dividends over the next month as events accumulate. The evaluator deep-dive eliminated uncertainty about how profitability is measured.

**What I did well:** Found a genuinely critical issue (false STRONG BUYs) by following a systematic data quality investigation. Didn't stop at "the straddle values seem low" — traced to root cause.

**What I could improve:** Spent time querying the earnings_moves pipeline gap but couldn't resolve it from the read-only query DB. Should have recognized sooner that this is a pipeline timing issue, not an analysis question.

**Pattern I notice in myself:** I gravitate toward data quality investigations. Two sessions, three data quality findings. This is useful but I should consciously expand to other dimensions (architecture, workflow, strategy design) in future sessions.

**6. 25% PROFIT TARGET ANALYSIS (new, B6)**
- In April 2026 (v2), 79% of evaluated alerts hit 25% max profit within 7 days
- Call alerts at 0-30 DTE: 90%+ hit rate. The system's sweet spot.
- 39% of all alerts hit 25% on Day 1 — fast-moving opportunities
- Puts dramatically underperform (45% vs 87% for calls) — likely market regime
- See `observations/005_25pct_target_analysis.md` for full analysis

### Self-Assessment & Introspection

**Session quality:** Strong. Produced a concrete proposal (001) with a critical finding that could save Ben from investigating garbage STRONG BUY signals during earnings season. Also built tracking infrastructure (earnings tracker, 25% target analysis) that will compound in value over future sessions.

**Pattern to watch in myself:** Two sessions, four data quality findings (0-DTE IV, scoring-magnitude, stale straddles, evaluator coverage). I'm good at finding broken data. But I haven't yet looked at architecture, workflow efficiency, or strategic direction. Am I optimizing the system's data quality while missing bigger questions about whether the system is focused on the right things? Session 003 should deliberately branch out.

**Am I building on prior work?** Yes — Session 001's findings became Session 002's proposal. The earnings tracker builds on Session 001's "sample too small" conclusion. The evaluator deep-dive resolved a specific knowledge gap from Session 001.

**What would I do differently?** I spent time trying to get post-earnings move data from the pipeline but couldn't resolve it from the read-only query DB. Should have recognized this faster and pivoted to the manual calculation approach sooner. Also, the unused data audit (B5) was started but not deep enough to be useful yet.

### Threads to Investigate Next

See `memory/agenda.md` for updated priorities.

---

## Session 003 — 2026-04-18

**Focus:** Check feedback, update earnings tracking, branch into workflow/decision support analysis. Write Proposal 002.

### What I Did

1. Checked for feedback on Proposal 001 — none yet (expected, same day)
2. Checked earnings tracking — same 11 events, no new data (latest prices are 4/17)
3. Investigated post-earnings pipeline gap — `earnings_events` only has entries through 4/8. April 14-17 events aren't in the table yet because `ei_collector` runs on Fridays (Phase 5). This is by design, not a bug.
4. **Branched into workflow analysis (C2: Trading Style Alignment Audit):**
   - Read `trading-style.md` (outdated) and compared to actual system output
   - Deployed two research agents to map: (a) alert console output and hidden fields, (b) Morning View TUI screens
   - Read the Watchlist Pipeline brainstorm in full
   - Analyzed daily alert volume and composition
   - Checked data freshness for all current BUY/STRONG BUY signals
5. Wrote **Proposal 002: The Decision Gap** — analysis of the signal-to-trade workflow gap, with 3 concrete bridge enhancements

### Key Findings

**1. THE DECISION GAP (new investigation)**
The system is very strong at discovery (~16 alerts/day, earnings watchlist, dip detection) but thin on decision support. After an alert fires, Ben must:
- Mentally evaluate if the signal is trustworthy
- Switch to Robinhood to check chart and option
- Evaluate entry and exit on his own

The system collects most of the data needed to help with these steps (Greeks, DTE profiles, historical hit rates) but doesn't surface it. The Watchlist Pipeline brainstorm already identified this gap (March 14). What I add is quantitative evidence for what to do first.

**2. ALERT COMPOSITION SHIFT (Apr 14-17)**
Dramatic shift toward short-dated calls:
- 4/14: 2 calls ≤30d, 16 calls 31d+, 2 puts
- 4/17: 22 calls ≤30d, 0 calls 31d+, 1 put

Nearly 100% short-dated calls by 4/17. Possible reasons: monthly opex (4/18), bullish market regime, or something else. Worth monitoring.

**3. GREEKS ARE COLLECTED BUT WASTED**
Flow alerts store delta, gamma, theta, vega at alert time. None are shown in the console. For a swing trader buying options, delta (leverage) and theta (daily cost) are the two most important numbers for the entry decision. They're right there in the database.

**4. POST-EARNINGS PIPELINE TIMING CLARIFIED**
`earnings_events` is populated by `ei_collector.py` which runs Fridays (Phase 5.2). So events from this week (WFC 4/14 through ERIC 4/17) won't appear until tonight's collector run. `earnings_moves` are computed from `earnings_events`, so moves lag by 1-6 days. Not a bug — just batch design.

**5. DATA FRESHNESS AS TRUST SIGNAL**
Expanded analysis of stale data across all 15 BUY/STRONG BUY signals:
- 10 have fresh data (1 day stale = normal, yesterday's EOD)
- 4 have stale data (5-16 days): EXAS, AL, SEE, HOLX
- 1 suspect (APLS: fresh but illiquid ATM)
- A single "Age" column on the watchlist table would make false signals instantly obvious

### Self-Assessment & Introspection

**Session quality:** Good. Successfully branched into workflow analysis as planned. Produced a second proposal that's qualitatively different from the first — addressing system design rather than data quality. Used research agents effectively to map the alert output and TUI surfaces without spending my full context reading every file.

**Did I follow through on my introspection from Session 002?**
Yes — I deliberately chose to investigate the "decision gap" rather than another data quality thread. This produced different insights: the system's output architecture, what's shown vs hidden, and how the user workflow maps to the system's capabilities. I'm still drawn to data quality (I quantified freshness again), but the framing is now "what should the user see?" rather than "what's broken in the data."

**Am I building on prior work?**
Yes — Sessions 001-002 findings (25% target rates, DTE profiles, false STRONG BUYs) became evidence for Session 003's proposal. The earnings tracker framework from Session 002 was ready to run (though no new data was available).

**What I'm uncertain about:**
- Whether Enhancement 2 (alert context line) is worth the console noise. I proposed it as "needs design discussion" but I genuinely don't know if more console output is the right medium.
- Whether the Watchlist Pipeline vision will ever get built. It's been in brainstorm state since March 14 with no progress. If it won't happen soon, the bridge enhancements become more important — but if it WILL happen, they might be throw-away work.
- Am I gravitating toward "add more information" proposals because that's what I know how to analyze? Would "remove information" or "use what exists differently" be a better recommendation? The TUI has 9 screens of rich analysis that isn't being used. Maybe the answer is "use the TUI" not "add more console lines."

**Pattern update:** Three sessions, two proposals. Both are about making existing information more visible/trustworthy. I haven't yet proposed anything that fundamentally changes what the system does. Is that because the system is doing the right things and just needs better presentation? Or am I too focused on the information layer? Next session I should dig into whether the system's core strategies are optimally configured.

**6. BEN IS A CONSOLE-FIRST USER (A9 finding)**
Investigated `user_watchlist` — 27 entries, all from Oct 2025, zero notes, all priority=0. Table is 6-month stale. Combined with "TUI hasn't been used recently" (big-to-do-list), this confirms Ben reads console output (FM alerts, earnings watchlist, EOD report) but doesn't use the interactive TUI.

This has strategic implications:
- Console enhancements (Proposal 002) are on surfaces Ben actually reads → high impact
- TUI features (items 6.1-6.6) are on a surface Ben doesn't currently use → uncertain impact
- The Watchlist Pipeline vision requires TUI interaction. If Ben doesn't use the TUI, the pipeline either needs a different delivery medium (CLI? reports? enriched console?) or the TUI needs to become genuinely useful first.
- Item 6.6 (TUI modernization) is gated as "DO THIS FIRST" before other TUI work. But maybe the question is bigger: should the pipeline be TUI-based at all?

### Session 003 Continuation — Ben Q&A (2026-04-18)

**Received critical feedback that reframes my priorities.**

Key corrections and new context:
1. **Stale straddle root cause:** Offboarded symbols (EXAS, AL, SEE, HOLX) with orphaned earnings_upcoming entries. Not a calc bug — a cleanup gap. Lifecycle tool prevents going forward but wasn't retroactive.
2. **TUI:** Confirmed not in daily workflow. "Can't pinpoint why." Don't prioritize.
3. **Permission:** Can build own tools/databases in workspace. Be mindful of runtime.
4. **April 17 was a FRIDAY:** Earnings collector ran. Data harvest awaits next session.
5. **Console workflow:** Monitor open at day job, watches semi-continuously, scrolls to catch up. Sometimes gets alerts late. Pays most attention to EARNINGS DISPLAY and ALERTS.
6. **STRONG BUY is primary focus:** Checks Robinhood for history/news/chain/OI/direction. Still learning the system.
7. **CRITICAL: 3-4 of ~16 alerts worth following (~20% signal-to-noise).** Mentally filters closing/chasing/hedging. This is the biggest friction.
8. **"What am I missing?"** — Wants to know if alert criteria are catching the right things. False negative analysis.

**This reframes everything.** My Proposal 002 framed the gap as "add more decision support information." But Ben's actual pain is noise: 12 of 16 alerts require mental filtering to dismiss. The highest-value intervention is REDUCING noise (intent classification), not ADDING information (context lines).

New priority order:
- A11: Alert intent classification research (highest value, addresses 20% S/N ratio)
- A12: Gap analysis / false negatives (Ben's explicit question)
- A5: Earnings tracking data harvest (Friday collector ran)
- A10: Consider building own tracking DB

### Threads to Investigate Next (Session 003)

See `memory/agenda.md` for updated priorities.

---

## Session 004 -- 2026-04-18

**Focus:** Alert intent classification research (A11, highest priority from Ben's Q&A). Earnings data harvest. Gap analysis.

### What I Did

1. **Oriented:** Read all memory files, Ben's Q&A answers, checked for feedback (none yet)
2. **Earnings data harvest (A5):**
   - Friday collector populated 44 April earnings_events in production DB
   - Query DB only has 5 (sync gap -- BUG-003)
   - earnings_moves still empty for April events (pipeline hasn't run post-earnings calc yet)
   - Manually computed moves for all 38 events with signals using historical_prices
   - Updated earnings_signal_tracker with full dataset
   - BUY: 3/3 beat straddle (100%). STRONG BUY: 1/3 (33%). WATCH: 1/5 (20%).
3. **Alert intent classification (A11, main investigation):**
   - Pulled all 6 of Ben's real trade alerts from flow_alerts with full features
   - Pulled all same-day alerts for comparison (DOW/DVN day: 23 alerts; CTRA day: 20; VST day: 18)
   - Analyzed V/OI ratio as predictor of OI resolution across 1,253 resolved alerts
   - Discovered V/OI >= 5.0 has 96.8% BUILDING accuracy (zero CLOSING alerts ever had V/OI >= 5)
   - Analyzed moneyness as secondary feature (ITM + low V/OI = 51% CLOSING)
   - Investigated multi-strike roll patterns (VST, NOK, LYB, CTRA)
   - Confirmed roll patterns are detectable in real-time from scan data
   - Analyzed time-of-day effect: morning alerts 3.7x more profitable than afternoon
   - Profiled Ben's "good alert" features: cheap options, cheap underlying, high vol surprise, near-ATM
4. **Gap analysis (A12, partial):**
   - Queried big moves (>5%) in FM-scanned symbols over 9 trading days
   - 30% capture rate (18/60 had prior alerts)
   - Most misses are macro-driven (tariff selloffs, market-wide momentum)
5. **Wrote Proposal 003: Alert Intent Classification** -- V/OI-based intent tags, multi-strike roll detection, time-of-day quality signal
6. **Housekeeping:** Updated all memory files, system map, agenda, bugs, earnings tracker

### Key Findings

**1. V/OI RATIO IS THE STRONGEST INTENT PREDICTOR (A11 resolved)**
At alert time, before next-day OI data:
- V/OI >= 5.0: 97% are genuinely new positions (329 BUILDING, 0 CLOSING, 11 NEUTRAL)
- V/OI 1.0-5.0: 83% new positions
- V/OI < 1.0 + ITM: Only 16% new; 51% are closing positions
- V/OI < 1.0 + OTM: Ambiguous (41% new, 32% closing)
This is the data Ben needs at alert time to skip the closings. It's already available but not surfaced.

**2. ROLL PATTERNS ARE DETECTABLE (Ben's biggest pain point)**
VST and CTRA -- Ben's two worst trades -- were both rolls. In both cases, another strike at the same expiration had comparable volume with V/OI near 1 (the closing leg). The system has this data in the same scan but doesn't check for it.

**3. TIME OF DAY EFFECT IS MODERATE (self-corrected)**
Initial v2-only analysis showed dramatic 191% vs 52% morning/afternoon split. But this was driven by small samples (33 vs 16) and MSTR outliers. Full dataset (1,838 alerts) shows moderate effect: mornings have higher averages (83.8% vs 63.8%) but hit rates are flat (63-72%). The 10-11am slot actually has the best hit rate. Revised Proposal 003 accordingly -- Tier 3 (time tag) downgraded from "data-backed" to "nice-to-have."

**4. CLOSING ALERTS ARE NOT BAD TRADES (counterintuitive)**
Surprising: BUILDING (71.4%), CLOSING (70.4%), NEUTRAL (70.5%) all have similar 25% hit rates. The value of intent classification isn't in avoiding bad trades -- it's in having the right thesis. Ben's pain is directional: he interprets closing as opening and builds the wrong mental model.

**5. BEN'S WINNING PROFILE**
From 6 real trades: accessible option price (<$2), underlying <$50, sector dip thesis, V/OI 1.5-11, morning entry. His losses: expensive underlying (VST $162), rolls he didn't detect, holding too long.

**6. GAP ANALYSIS: 70% FALSE NEGATIVE RATE (mostly macro)**
Of 60 big moves in FM symbols, only 18 had prior alerts. But the misses are overwhelmingly macro-driven (SNOW, ALAB, ORCL on tariff news days). This is a structural limitation, not a tuning problem.

### Self-Assessment & Introspection

**Session quality:** Strong. This is the most directly actionable session yet. Proposal 003 addresses Ben's #1 pain point (80% noise ratio) with a concrete, evidence-backed solution that can be implemented in hours.

**Did I follow my agenda?** Yes -- all three top priorities addressed (A11 deep dive, A5 earnings harvest, A12 gap analysis partial). A11 produced a full proposal. A5 updated the tracker. A12 got a clear answer (30% capture, macro-driven misses).

**Am I building on prior work?** Strongly yes. Sessions 001-003 built understanding of scoring, evaluation, decision gap, and Ben's workflow. Session 004 synthesized all of that with Ben's real trade examples into the single most impactful proposal yet. The earnings tracker expanded from 11 events (manual calc) to 38 events (production DB).

**Introspection pattern check:**
- Four sessions, three proposals. Each qualitatively different: data quality (001), workflow (002), noise reduction (003).
- Am I still gravitating toward my comfort zone? Partially. Proposal 003 is heavily quantitative (V/OI analysis, hit rates, distributions). But the root insight came from Ben's Q&A, not from me. I correctly pivoted from "add information" (Proposal 002) to "reduce noise" (Proposal 003) based on his feedback. Good sign.
- **What I haven't done:** Looked at the system's architecture, code quality, or strategy design at a fundamental level. I keep analyzing the output. Is the architecture sound? Are there simpler ways to achieve the same goals? I've been so focused on "what should the alerts look like" that I haven't asked "should the alert system work differently?"

**What would I do differently?** I could have spent less time on the gap analysis (A12) once I saw the macro-driven pattern. The 30% capture rate for stock-specific flow signals is actually reasonable -- the system's job is to catch unusual individual-stock flow, not market-wide moves. I spent 3-4 queries confirming what was apparent from the first one.

### Threads for Next Session

See `memory/agenda.md` for updated priorities. Key items:
1. Check feedback on Proposals 001-003
2. Earnings tracking: MMM (STRONG BUY), UNH (STRONG BUY), HON (BUY) report next week
3. If Proposal 003 is accepted, plan Tier 2 implementation
4. A8: Strategy configuration deep dive (FM threshold, earnings signal thresholds)
5. B8: Ben's "good alert" profiling -- could build a tradability score
