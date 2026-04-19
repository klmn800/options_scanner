# Investigation Agenda

Prioritized threads to pull on. Updated each session.

---

## Priority A — Next Session

### A5. Earnings Signal Tracking — ONGOING
**Status:** 38 events tracked (11 with signals). Friday collector populated earnings_events. earnings_moves pipeline status unknown.
**Next session:**
- Check if earnings_moves have been computed for April events
- Track MMM (STRONG BUY 4/21), UNH (STRONG BUY 4/21), HON (BUY 4/23) results
- Check query DB sync status
- Track cumulative BUY vs STRONG BUY performance curve

### A7. Check Proposal Feedback
**Proposals pending:**
- 001: Signal quality bundle (stale straddle fix, scoring insight, 0-DTE IV)
- 002: Decision gap (console enrichments)
- 003: Alert intent classification (V/OI tags, roll detection)
- 004: Tradability highlight ([ACTIONABLE] tag)
**Ben's verbal feedback (Session 003):**
- Stale straddle root cause = offboarded symbols
- TUI not in daily workflow
- Proposal format should be lean work orders, not research papers

### A14. v3 Scoring Design Synthesis (NEW)
**Findings to incorporate into v3 review:**
1. Score-magnitude inverse confirmed in v2 — higher scores = lower returns (structural)
2. DTE is the strongest predictor — v3 bonus should be +1.0 not +0.25
3. Flow concentration penalty correctly targets mega-cap noise (MSTR = 8.4% of alerts)
4. Integration path is clean (fm_analyzer.py has clear insertion points)
5. BUG-005 (dead dedup code) should be fixed before or alongside v3
**Action:** Write a v3 design review as observation (not proposal — the v3 design doc exists and is scheduled for May 2026). Feed findings to Ben for his May review.

### A8. Strategy Configuration — PARTIALLY DONE
**Resolved:** 3.5 threshold is correct (raising it hurts performance). Noise should be addressed through filtering/tagging.
**Remaining:**
- Earnings signal thresholds: BUY 3/3 (100%), STRONG BUY 1/3 (33%). Wait for more data before recommending changes.
- v3 scoring: see A14 above
- DTE minimum (currently 7): could experiment with 5 to catch more gamma plays

---

## Priority B — Following Sessions

### B1. Theoretical Evaluation Enhancement
25% target analysis from Session 002. Could formalize into a metric. Low priority — current evaluation works.

### B4. v3 Alert Scoring Design Review — see A14

### B5. Unused Data & Feature Audit (continued)
Started in Session 002. 6 empty/near-empty tables. Dead TUI screens. Next: check if any are in active plans.

### B7. Post-April Alert Regime Analysis
April 14-17 showed dramatic shift to short-dated calls. Monitor May data for regime persistence.

### B8. Ben's "Good Alert" Profiling — PARTIALLY ADDRESSED
Proposal 004 implements a simple version. Could evolve into a "tradability score" that weights multiple factors (option price, UL price, V/OI, DTE, sector thesis). Deferred until Proposal 004 feedback arrives.

### B9. Earnings Signal Threshold Recalibration
BUY 3/3 > STRONG BUY 1/3. Wait for 30+ events before recommending changes. Key test: MMM (4/21) and UNH (4/21) are both STRONG BUY.

### B10. Alert Deduplication Fix (NEW, from BUG-005)
Dead code in fm_analyzer.py. Could be a standalone bug fix or bundled into v3 scoring work. CLI command ready in bugs.md.

---

## Priority C — Longer Term

### C1. System Architecture Assessment
Broad review: data flow, code organization, unused features, simplification. Haven't started yet.

### C3. Self-Assessment Framework
After 5-10 sessions, evaluate my own recommendations' quality. Now at 5 sessions with 4 proposals — getting close to having enough history.

### C5. Time-of-Day Analysis — RESOLVED
Morning effect is moderate (83.8% vs 63.8% avg, flat hit rates). Not actionable enough for a proposal. Downgraded to Tier 3 in Proposal 003.

---

## Completed

### A1. Score-Performance Relationship — RESOLVED (Session 001)
### A1b. Understand the Evaluator — RESOLVED (Session 002)
### A2. expected_move_pct Data Quality — RESOLVED (Session 001)
### A3. Draft Proposal 001 — COMPLETED (Session 002)
### A4. Check Proposal 001 Feedback — CHECKED (Sessions 003-005, none yet)
### A6. Post-Earnings Pipeline Check — RESOLVED (Session 003)
### A3b. Draft Proposal 002 — COMPLETED (Session 003)
### A9. Investigate "Is the System Used?" — RESOLVED (Sessions 003-004)
### A11. Alert Intent Classification Research — COMPLETED (Session 004)
### A12. Gap Analysis — RESOLVED (Session 004): 30% capture, macro-driven misses
### A13. Intent Classification Implementation Planning — PROPOSAL WRITTEN (Session 004)

---

*Last updated: Session 005, 2026-04-18*
