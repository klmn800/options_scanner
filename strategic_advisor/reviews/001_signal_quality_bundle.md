# Proposal 001: Signal Quality Bundle — Three Findings

**Date:** 2026-04-18 (Session 002)
**Status:** Proposal
**Scope:** Data quality fixes + signal interpretation guidance
**Effort:** Finding 1: ~2 hours. Finding 2: design discussion. Finding 3: ~30 minutes.

---

## Finding 1: 50% of STRONG BUY Earnings Signals Are False Positives

**Priority: CRITICAL — affects trading decisions NOW**

### What I Found

Of the 10 current STRONG BUY earnings signals for events from April 18 onward, 5 are based on garbage straddle data:

| Symbol | Earnings | Straddle % | Underpricing % | Latest OC Data | Verdict |
|--------|----------|-----------|----------------|----------------|---------|
| EXAS | May 7 | 0.09% | 9,082% | Apr 2 (16d stale) | FALSE |
| APLS | May 7 | 1.29% | 454% | Apr 17 (fresh) | SUSPECT — illiquid ATM strike |
| AL | May 4 | 0.59% | 442% | Apr 13 (5d stale) | FALSE |
| SEE | May 5 | 1.61% | 216% | Apr 9 (9d stale) | FALSE |
| HOLX | Apr 30 | 1.17% | 201% | Apr 9 (9d stale) | FALSE |
| UNH | Apr 21 | 5.23% | 107% | Apr 17 (fresh) | REAL |
| WBD | May 7 | 3.01% | 97% | Apr 17 (fresh) | REAL |
| AES | Apr 30 | 2.64% | 86% | Apr 17 (fresh) | REAL |
| GMED | May 7 | 8.16% | 76% | Apr 17 (fresh) | REAL |
| MMM | Apr 21 | 5.22% | 68% | Apr 17 (fresh) | REAL |

### Root Cause

`get_straddle_expected_move()` in `ei_moves_upcoming.py:259` has two weaknesses:

**1. No staleness detection.** The function gets the stock price from `MAX(trade_date)` in `historical_prices`, then queries `option_contracts` on that same trade_date. If that date is weeks old (EXAS: March 20), the straddle uses ancient data. Worse: the stored value persists forever because the UPDATE uses `COALESCE(?, straddle_expected_move_pct)` — a NULL new value never overwrites a stale stored value.

**2. Uses `last_price` on illiquid ATM strikes.** APLS at $40.90: the $41 strike has last_price=$0.05 for the call (bid=$0.00, ask=$0.05). That "last price" could be from days ago. The $40 strike has call=$1.05 with actual bids — much more reliable. But the function picks the closest strike ($41) and trusts whatever `last_price` it finds.

### Impact

Anyone looking at the earnings signal list sees EXAS at 9,082% underpricing at the top. The real signals (UNH, MMM, AES) are buried below garbage. If someone investigated or traded EXAS based on this signal, the underpricing is an artifact, not a real market mispricing.

### Recommended Fix

**Minimum viable (30 min):** Add a staleness guard and straddle floor.

In `get_straddle_expected_move()`:
1. After getting `trade_date` from `historical_prices`, check if it's more than 5 trading days old. If so, return `None`.
2. Require `bid > 0` on at least one leg (call or put) — `last_price > 0` with `bid = 0` indicates a stale trade, not a live market.

**Better (1-2 hours):** Additionally:
3. Use `(bid + ask) / 2` instead of `last_price` when both are available and bid > 0. Midpoint reflects the current market, not the last trade.
4. Add a sanity check: if `straddle_expected_move_pct < 1.0%`, log a warning and return `None`. No stock has a straddle implying <1% earnings move — that's data noise, not signal.
5. Cap `relative_underpricing_pct` at a reasonable maximum (e.g., 300%). Even if a straddle is genuinely low, 9,082% underpricing is not actionable information.

### What I'm Uncertain About

- Whether the staleness is caused by symbols falling out of the OP scan (offboarded, purgatory) or just data freshness delays. If these symbols stopped being collected, the staleness guard alone might not be enough — they'd perpetually show `None` signals, which is fine but worth understanding.
- Whether `bid > 0` is too strict for small-cap option chains that genuinely have wide spreads. Might need testing on the KLMN universe.

---

## Finding 2: Alert Scoring Predicts Reliability, Not Magnitude

**Priority: IMPORTANT — design implication for v3 scoring**

### What I Found (Session 001, confirmed with controlled analysis)

Higher alert significance scores consistently produce LOWER average max profit at 7 days. This is not a confound — tested within the same scoring version (v1 only), within the same DTE bands. The pattern holds in 8 of 9 tested cells.

**DTE-controlled results (v1 only, same DTE band, different scores):**

| DTE Band | Score 6.0-7.0 | Score 7.0-8.0 | Score 8.0+ |
|----------|:-------------|:-------------|:-----------|
| 0-14d | 120.5% (81% WR) | 111.3% (77% WR) | 93.9% (79% WR) |
| 15-30d | 69.4% (69% WR) | 77.5% (71% WR) | 49.2% (62% WR) |
| 31d+ | 49.9% (61% WR) | 45.0% (63% WR) | 40.5% (64% WR) |

Higher scores mean bigger premiums (more expensive options), which move less in percentage terms. The score answers "how much institutional money moved?" — not "how much can a retail swing trader make?"

Win rates are much flatter across score bands (60-81%), meaning score predicts slightly more reliable outcomes but with smaller percentage gains.

### Implications for v3 Design

The v3 design doc (`docs/alert_scoring_v3_design.md`) is heading in the right direction with its Tier 2 actionability bonuses (V/OI, DTE sweet spot, contract affordability, IV context). These address the exact problem: making the score reflect "opportunity for Ben" alongside "institutional importance."

**Concern:** The proposed bonuses are small (+0.25 to +0.5 each) while the fundamental score spans 0-10. Given how powerful the inverse effect is, the actionability dimension may need more weight. A few suggestions:

1. **DTE bonus should be larger.** DTE is the single strongest predictor of 7-day max profit I found — stronger than score, stronger than option type, stronger than month. The +0.25/+0.5 DTE bonus in v3 is too gentle. Consider +1.0 for the sweet spot (15-30 DTE, where gamma amplifies moves without excessive theta decay).

2. **Consider displaying actionability separately** rather than mixing it into one number. "Score 6.2 (Actionability: HIGH)" is more informative than "Score 7.0". The intelligence value (Tier 1) and trading opportunity (Tier 2) serve different purposes — collapsing them into one number loses information.

3. **Don't try to make score predict magnitude.** It can't — the inverse relationship is structural (premium = numerator of score, denominator of return). Instead, clearly label what the score DOES predict: "this is unusual enough to watch." The actionability tier then answers the separate question: "is this worth trading?"

### What I'm Uncertain About

- **v2 vs v1 comparison.** April 2026 (v2) alerts average 114.9% max 7d profit vs 55-82% for v1 months. Is this v2 scoring doing better, or is it April 2026's market? I can't separate these yet with only 2-3 weeks of v2 data. Will revisit after more data accumulates.
- **Whether the inverse relationship holds in v2.** v2 alerts cluster in the 3.5-5.0 range (lower threshold), so the score distribution is different. Need more v2 data to test.

---

## Finding 3: expected_move_pct Contaminated by 0-DTE IV

**Priority: LOW — signal system already isolated from this bug**

### What I Found (Session 001)

222 of 763 upcoming earnings events (29%) have `expected_move_pct` > 20%, with 45 above 100%. Example: ENTG at 230%, WMS at 164%. These are impossible values.

**Root cause:** `iv_front_month` in `op_symbol_rollup.py:949-973` is a simple average of all contract IVs with 0-21 DTE. 0-DTE contracts on illiquid names have wildly inflated IV (Black-Scholes diverges at time=0 with wide bid-ask spreads). This contaminates the average. The `expected_move_pct` formula then amplifies it.

### Current State

**Already isolated.** As of 2026-04-15, `relative_underpricing_pct` (the signal driver) uses only `straddle_expected_move_pct`, with no fallback to `expected_move_pct`. Lines 515-529 in `ei_moves_upcoming.py` document this explicitly.

### Recommended Fix

**When convenient (30 min):** In `op_symbol_rollup.py:952-961`, filter out contracts with DTE < 1 from the IV averaging. Add: `if dte < 1: continue`. This is mathematically defensible — 0-DTE IVs are unstable for any name that isn't AAPL/SPY-level liquid.

**Alternatively:** Cap individual IV values at 3.0 (300%) before averaging, or use median instead of mean.

This is not urgent because the signal system doesn't use this value, but it cleans up a column that may be displayed in console output, watchlists, or the Morning View TUI.

---

## Summary

| # | Finding | Priority | Effort | Impact |
|---|---------|----------|--------|--------|
| 1 | False STRONG BUY signals from stale straddles | CRITICAL | 1-2 hours | Directly affects which symbols Ben investigates for earnings |
| 2 | Scoring predicts reliability, not magnitude | IMPORTANT | Design discussion | Shapes v3 scoring approach |
| 3 | expected_move_pct 0-DTE contamination | LOW | 30 min | Cosmetic — signal already isolated |

**My recommendation:** Fix Finding 1 before this earnings season progresses further. Findings 2 and 3 can wait.
