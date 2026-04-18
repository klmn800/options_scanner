# Investigation Agenda

Prioritized threads to pull on. Updated each session.

---

## Priority A — Next Session

### A5. Earnings Signal Tracking — FRIDAY COLLECTOR RAN (HIGH PRIORITY)
**April 17 was a FRIDAY.** The `ei_collector` (Phase 5.2) ran last night. This means:
- `earnings_events` should now have entries for WFC/MS/ABT/INFY/MRSH/MAN/PLD/TFC/ERIC
- `earnings_moves` should be computed for events with T+1 data (WFC at T+3, MS at T+2, etc.)
- The query DB sync should have the latest data by now (Saturday)
- **First priority next session:** Run tracking query, check earnings_moves, compare to my manual calculations
- Also track: CLF (4/20 — this Sunday? or Monday?), HAL/MMM/UNH (4/21), PM/TSLA (4/22)
- UNH (STRONG BUY, 107%) and MMM (STRONG BUY, 68%) report Monday — first REAL test of fresh STRONG BUY signals

### A7. Check Proposal 001 & 002 Feedback + Apply Ben's Session 003 Corrections
Read `strategic_advisor/reviews/feedback/` for written responses.
**Ben's verbal feedback (Session 003 Q&A):**
- Stale straddle root cause = offboarded symbols with orphaned earnings_upcoming data. Not a calc bug — a cleanup gap. Lifecycle tool (PRD 0013) prevents going forward but wasn't retroactive.
- TUI confirmed not in daily workflow. "Can't pinpoint why." Agrees: don't prioritize developing unused system.
- Permission granted to build own tools/databases in workspace for analytical purposes. Be mindful of runtime.
- **Revise Proposal 001 Finding 1:** The "staleness guard" fix should be reframed as "clean up orphaned earnings_upcoming for offboarded symbols + lifecycle offboarding should clear earnings_upcoming." The root cause isn't the straddle calculation — it's that offboarded symbols still have active entries.

### A10. Consider Building Tracking Database (NEW — Ben permission granted)
Ben gave permission to create own tables/database in workspace for analytical purposes. Options:
- SQLite DB at `strategic_advisor/data/advisor_tracking.db`
- Tables: earnings_signal_results (season tracking), alert_profile_stats (DTE/type hit rates), session_metrics
- Value: persistent tracking without re-running queries each session
- Risk: minimal (read-only from system, writes only to own workspace)
- Decision: do this if the manual tracking in `earnings_signal_tracker.md` becomes unwieldy

### A11. Alert Intent Classification Research (NEW — HIGHEST PRIORITY from Ben Q&A)
Ben reports 3-4 of ~16 daily alerts are worth following (~20% signal-to-noise). He mentally filters for closing/chasing/hedging. This is the biggest friction point.
**Research approach:**
1. Query resolved alerts (next-day OI) — what % are BUILDING vs CLOSING vs NEUTRAL? Does this correlate with alert-time features?
2. Check if V/OI ratio, stock price change, option type vs direction, moneyness, or DTE predict intent
3. Look at the 3-4 "good" alerts vs the 12 "noise" alerts — what distinguishes them? (Need Ben to flag some examples, or use profitability as proxy)
4. Test classification heuristics against historical data
**Goal:** A proposal for alert intent tagging that reduces mental filtering without losing good signals.

### A12. Gap Analysis — What Are We Missing? (NEW — Ben's question)
Ben asked: "What if I'm missing things that should be alerts?"
**Research approach:**
1. Find stocks that moved >5% in a day (historical_prices)
2. Check if flow_alerts existed in the 1-3 days prior
3. If no alert: query flow_options_scans for unusual activity that didn't reach threshold
4. Identify patterns that should have been flagged but weren't
**Goal:** Understand false negative rate and identify criteria gaps.

### A8. Strategy Configuration Deep Dive
Three sessions focused on data quality and information display. Time to go deeper — are the system's core strategies optimally configured?
- FM threshold (3.5): is this producing more noise or more signal?
- Earnings signal thresholds (15%/30%/50%): early data suggests BUY is the sweet spot, not STRONG BUY
- v3 scoring: is it still being planned? Does the DTE finding change the design?
- FM scan parameters: ±20% strike range, 388 symbols — are these right?

### A9. Investigate "Is the System Used?"
The TUI has 9 screens of rich analysis but "hasn't been used recently" (big-to-do-list). The workflow tracking week (March 17-21) was planned but it's unclear if it happened. Understanding what Ben actually uses daily vs what exists would inform whether to build more views or make existing ones more accessible.

---

## Priority B — Following Sessions

### B1. Theoretical Evaluation Enhancement
Ben prefers theoretical validation ("if played perfectly"). Current max_prof_7d_pct is good but could be enriched:
- Realistic exit modeling (not just max — what about a disciplined 25% target?)
- "% of alerts where 25% target was achievable within 7 days" by profile
- Risk-adjusted returns: was the drawdown path acceptable?
- Session 002 already produced the 25% target analysis (observation 005). Next step: formalize into a metric.

### B4. v3 Alert Scoring Design Review
Now informed by the scoring-magnitude finding AND the DTE-as-predictor finding. After feedback on Proposals 001-002, consider a dedicated proposal. Key points:
- DTE bonus needs to be larger (+1.0 not +0.25)
- Consider displaying actionability separately from intelligence value
- Flow concentration penalty calibration

### B5. Unused Data & Feature Audit (continued)
Started in Session 002. Found 6 empty/near-empty tables. Next steps:
- Check which features (social posting, AI council, agent system) are still in Ben's plans
- Look for dead code paths — features wired in code but never called from orchestrator
- `option_contracts_corrupt_20260407` cleanup — flag for deletion

### B7. Post-April Alert Regime Analysis (NEW)
April 14-17 showed dramatic shift to short-dated calls (0 puts on 4/16-4/17). Is this:
- Monthly opex effect (4/18 expiration)?
- Market regime (extreme bullishness)?
- v2 scoring bias toward short DTE?
Worth checking when May data accumulates.

---

## Priority C — Longer Term

### C1. System Architecture Assessment
Map the data flow end-to-end. Identify structural risks or simplification opportunities. The sector archive split (6 DB files created) and orchestrator modularization suggest good structure, but worth verifying.

### C2. Trading Style Alignment Audit (PARTIALLY DONE)
Session 003 investigated the decision support surface. `trading-style.md` is outdated. Key remaining question: does Ben's actual daily workflow use the TUI, console output, Robinhood, or some combination? The workflow tracking week may have happened — check.

### C3. Self-Assessment Framework
After 5-10 sessions, build a way to evaluate my own recommendations' quality.

### C4. Earnings Signal Threshold Recalibration
After accumulating 50+ events. BUY looks like the sweet spot early on (3/3 vs STRONG BUY's 1/3). Could the thresholds be wrong? Or is STRONG BUY contaminated by the stale-data false positives?

---

## Completed

### A1. Score-Performance Relationship — RESOLVED (Session 001)
Higher scores predict reliability, not magnitude. Confirmed within v1-only data, within same DTE bands.

### A1b. Understand the Evaluator — RESOLVED (Session 002)
max_prof_7d_pct = max option midpoint within 168-hour window from flow_options_scans. 58% coverage is structural.

### A2. expected_move_pct Data Quality — RESOLVED (Session 001)
0-DTE IV contamination. Signal system isolated.

### A3. Draft Proposal 001 — COMPLETED (Session 002)
Written as `reviews/001_signal_quality_bundle.md`.

### A4. Check Proposal 001 Feedback — CHECKED (Session 003)
No feedback yet. Normal — same day.

### A6. Post-Earnings Pipeline Check — RESOLVED (Session 003)
Not a bug. `earnings_events` populated by Friday `ei_collector` run. April 14-17 events will appear after tonight's Phase 5. `earnings_moves` computed from events, so they lag by 1-6 days.

### A3b. Draft Proposal 002 — COMPLETED (Session 003)
Written as `reviews/002_decision_gap.md`. The Decision Gap — bridging signals to trades.

---

*Last updated: Session 003, 2026-04-18*
