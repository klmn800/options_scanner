# Feedback on Proposal 001: Signal Quality Bundle

**Date:** 2026-04-18
**From:** Ben (via Claude Code session)
**Status:** Findings acknowledged, partial action taken

---

## Finding 1: False STRONG BUY Signals from Stale Straddles

**Verdict: Good catch. Root cause confirmed and fixed.**

You were right about the symptoms — 5 of 10 STRONG BUY signals were garbage. The root cause was narrower than you suspected: these were **offboarded symbols with orphaned `earnings_upcoming` entries**. EXAS, AL, SEE, and HOLX aren't even in `symbol_metadata` anymore — they were removed before the lifecycle tool (PRD 0013) existed.

**Action taken (2026-04-18):**
- Swept `earnings_upcoming` for all symbols with no `symbol_metadata` row
- Found 5 orphans: EXAS (9,082% underpricing), AL (442%), SEE (216%), HOLX (201%), ABEV (no signal)
- Deleted all 5 from production `datalake.db`
- The lifecycle tool (`tools/symbol_lifecycle.py --offboard`) already deletes `earnings_upcoming` entries during offboarding, so this won't recur for future offboards

**On the staleness guard idea:** The going-forward path is handled by the lifecycle tool's cleanup. If you still think a staleness guard in `get_straddle_expected_move()` adds value as defense-in-depth, feel free to design a proper proposal for it — but it's no longer critical.

**On APLS:** APLS is still active (`daily_only`). Its straddle issue is the illiquid ATM strike you flagged (last_price=$0.05, bid=$0.00). This is a different problem from the orphans — a genuine data quality edge case. Worth revisiting if you want to propose a fix for illiquid strike handling.

Thank you for finding this. Those false STRONG BUYs were actively misleading during earnings season.

---

## Finding 2: Alert Scoring Predicts Reliability, Not Magnitude

**Verdict: Good research. Carry forward for v3 review.**

This is a genuine insight. The score-magnitude inverse relationship makes structural sense (more premium = higher score = smaller % swings). Right now the score is really just a threshold to get on a watchlist — not an indicator of signal quality. That could change as v3 develops.

Your DTE-controlled analysis was well done — ruling out the market regime confound strengthened the finding significantly.

**No action needed now.** Feed this into your v3 scoring review work (A14 on your agenda). The v3 review is scheduled for May 2026 and this finding should inform the design discussion. Specifically, your point about DTE deserving more weight than +0.25/+0.5 is worth developing further.

---

## Finding 3: expected_move_pct 0-DTE IV Contamination

**Verdict: Acknowledged, low priority.**

You correctly identified this and correctly noted it's already isolated from the signal system. No action needed. If you want to bundle it into a future cleanup proposal, that's fine, but don't spend more time investigating it.

---

## Overall Notes

Your analysis was thorough and the false STRONG BUY finding was the most immediately valuable discovery across all 4 proposals — it was actively misleading during live earnings season and is now fixed. The research-report format on this proposal was noted (you've already self-corrected in 004). Future proposals in work-order format preferred.
