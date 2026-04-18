# Investigation Agenda

Prioritized threads to pull on. Updated each session.

---

## Priority A -- Next Session

### A5. Earnings Signal Tracking -- ONGOING, Check Pipeline
**Status:** 11 events tracked (Session 004). Friday collector populated earnings_events (44 April events in prod DB), but earnings_moves still empty for April. Also query DB didn't get the collector data yet (sync gap).
**Next session:**
- Check if earnings_moves have been computed for April events
- Re-run tracking query for MMM (STRONG BUY, 4/21), UNH (STRONG BUY, 4/21), HON (BUY, 4/23) -- key signals reporting next week
- Check query DB sync status
- Track cumulative BUY vs STRONG BUY performance curve

### A7. Check Proposal Feedback + Apply Session 003 Corrections
**Ben's verbal feedback (Session 003):**
- Stale straddle root cause = offboarded symbols (not calc bug). Lifecycle tool prevents going forward but wasn't retroactive.
- TUI confirmed not in daily workflow. Don't prioritize.
**Still pending:**
- Check `strategic_advisor/reviews/feedback/` for written responses to Proposals 001, 002, 003

### A13. Intent Classification -- Implementation Planning (NEW, from Proposal 003)
**If Proposal 003 is accepted:**
- Tier 1 (V/OI tag) is ready for implementation (~1 hour)
- Tier 2 (roll detection) needs scan query design
- Validate heuristic against new v2 alerts as they get resolved
- Track accuracy: does the V/OI tag match next-day resolution?

### A8. Strategy Configuration Deep Dive
Four sessions focused on data quality, decision support, and intent classification. Time to look at core strategy config:
- FM threshold (3.5): Ben is seeing ~16 alerts/day. Is this the right volume?
- Earnings signal thresholds: BUY 3/3, STRONG BUY 1/3 -- should thresholds be adjusted?
- v3 scoring: does the DTE finding + intent classification proposal change the v3 design priorities?

### A12. Gap Analysis -- PARTIALLY DONE
**Ben's question:** "Am I missing things that should be alerts?"
**Session 004 finding:** 30% capture rate for FM-scanned symbols with >5% moves. Most misses are macro-driven (tariff selloffs), not stock-specific flow signals. This is structural.
**Remaining:**
- Check whether adjusting FM parameters (lower threshold?) would catch more moves
- Investigate if some misses had unusual flow BELOW the current threshold
- Look at daily-only symbols (432 not scanned by FM) -- any with big moves?

---

## Priority B -- Following Sessions

### B1. Theoretical Evaluation Enhancement
Ben prefers theoretical validation. Current max_prof_7d_pct is good but could be enriched:
- Realistic exit modeling (25% target achievability within specific windows)
- Risk-adjusted returns (drawdown path)
- Session 002 already produced 25% target analysis. Formalize into a metric.

### B4. v3 Alert Scoring Design Review
Now informed by: scoring-magnitude finding, DTE-as-predictor, V/OI intent classification.
- DTE bonus needs to be larger (+1.0 not +0.25)
- Intent classification (V/OI band) could replace or supplement flow concentration
- Consider splitting score into "intelligence value" vs "trade actionability"

### B5. Unused Data & Feature Audit (continued)
Started in Session 002. Found 6 empty/near-empty tables. Next steps:
- Check which features are still in Ben's plans
- Dead code paths
- `option_contracts_corrupt_20260407` cleanup

### B7. Post-April Alert Regime Analysis
April 14-17 showed dramatic shift to short-dated calls. Monitor May data.

### B8. Ben's "Good Alert" Profiling (NEW)
From Session 004 trade examples: Ben's winning trades share specific features (cheap options, cheap underlying, sector thesis, V/OI 1.5-11, morning alerts). Could build a "Ben's Profile" score that highlights alerts matching his actual trading pattern. Different from significance_score -- this would be a "tradability" score.

### B9. Earnings Signal Threshold Recalibration Planning (NEW)
BUY is 3/3. STRONG BUY is 1/3. Early evidence suggests BUY (30-50% underpricing) may be the sweet spot. If this holds at 30+ events, consider:
- Lowering STRONG BUY threshold or renaming BUY as the priority signal
- Investigating whether STRONG BUY is contaminated by data quality (stale straddles)
- Relationship between underpricing % and actual move magnitude

---

## Priority C -- Longer Term

### C1. System Architecture Assessment
Map data flow end-to-end. Identify structural risks or simplification.

### C3. Self-Assessment Framework
After 5-10 sessions, evaluate my own recommendations' quality.

### C5. Time-of-Day Analysis Deep Dive (NEW)
Morning alerts (9:30-10am) have 3.7x avg profit and 91% hit rate vs afternoon (52%, 63%). Worth investigating: Is this a sampling bias (morning alerts are mostly from the first scan cycle which catches overnight accumulation) or a genuine signal? Could the system prioritize morning alerts differently?

---

## Completed

### A1. Score-Performance Relationship -- RESOLVED (Session 001)
Higher scores predict reliability, not magnitude. Confirmed.

### A1b. Understand the Evaluator -- RESOLVED (Session 002)
58% coverage is structural.

### A2. expected_move_pct Data Quality -- RESOLVED (Session 001)
0-DTE IV contamination.

### A3. Draft Proposal 001 -- COMPLETED (Session 002)
Written as `reviews/001_signal_quality_bundle.md`.

### A4. Check Proposal 001 Feedback -- CHECKED (Session 003)
No feedback yet.

### A6. Post-Earnings Pipeline Check -- RESOLVED (Session 003)
Not a bug. Batch design.

### A3b. Draft Proposal 002 -- COMPLETED (Session 003)
Written as `reviews/002_decision_gap.md`.

### A9. Investigate "Is the System Used?" -- RESOLVED (Sessions 003-004)
Ben is a console-first user. TUI not in workflow. Console is the primary delivery surface.

### A11. Alert Intent Classification Research -- COMPLETED (Session 004)
V/OI predicts intent with high accuracy. Written as Proposal 003.
Multi-strike roll detection algorithm designed. Time-of-day effect quantified.
False negative analysis: 30% capture rate (structural, mostly macro misses).

---

*Last updated: Session 004, 2026-04-18*
