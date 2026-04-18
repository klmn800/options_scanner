# Observation: expected_move_pct Inflated by 0-DTE IV Contamination

**Session:** 001 (2026-04-17)
**Status:** Root cause identified, fix path clear
**Confidence:** High — traced from data through code to mathematical root cause

## The Problem

222 of 763 upcoming earnings events (29%) have `expected_move_pct` > 20%, with 45 above 100%. Example: ENTG at 230%, WMS at 164%. These are impossible values for a stock's expected earnings move.

## Root Cause Chain

1. **`iv_front_month`** is computed in `op_symbol_rollup.py:949-973` as the simple average of all contract IVs with 0-21 DTE
2. **0 DTE contracts** on illiquid names have wildly inflated IV values (9.0-10.0+) because Black-Scholes IV diverges as time → 0 with wide bid-ask spreads
3. **WMS evidence:** 14 front-month contracts, DTE=0, IVs of 9.57-10.0. Average = 9.32. Meanwhile AAPL at DTE=0 has IV = 0.27-0.48 (stable because of extreme liquidity and tight spreads)
4. **`expected_move_pct`** formula in `ei_moves_upcoming.py:230` is: `iv_front_month * sqrt(days/365) * 100`. With iv_front_month = 9.32 and 27 days: 9.32 * 0.272 * 100 = 253%

## Impact Assessment

**Signal system: ISOLATED (2026-04-15 fix)**
- `relative_underpricing_pct` uses straddle-only, no fallback to `expected_move_pct`
- Lines 515-529 in `ei_moves_upcoming.py` explicitly document this isolation
- ~5 symbols with thin option chains get UNKNOWN signal instead of a bad signal

**`expected_move_pct` is still stored and may be displayed:**
- Stored in `earnings_upcoming` table (column still exists)
- Used in `move_difference_pct` calculation (line 508-511) as fallback when straddle is NULL
- May appear in console output or earnings watchlist display
- `ei_post_earnings_calc.py:862` uses the same formula for post-earnings expected move comparison

## Fix Options (for whoever implements)

**Best:** Filter DTE < 1 from IV averaging in `op_symbol_rollup.py:952-961`. Add: `if dte < 1: continue`. Simplest, most defensible — 0 DTE IVs are mathematically unstable for non-mega-cap names.

**Alternative:** Cap IV values at 3.0 (300%) before averaging. Catches extreme outliers while preserving high-but-real IVs.

**Alternative:** Use median instead of mean. Resistant to outliers. Would fix this and any future contamination.

## What I Checked in the Source Code

- `op_symbol_rollup.py:930-973` — `_calculate_iv_by_dte()`: simple average of contract IVs bucketed by DTE range. No outlier filtering, no DTE floor.
- `ei_moves_upcoming.py:205-237` — `get_expected_move_from_iv()`: `iv_front_month * sqrt(days/365) * 100`. Assumes IV is decimal. Comment says "IV should already be in decimal form" but doesn't validate.
- `ei_moves_upcoming.py:515-529` — signal isolation: relative_underpricing_pct is straddle-only with NO expected_move_pct fallback. Fixed 2026-04-15 with explanatory comment citing SSNC false STRONG BUY example.
- `ei_post_earnings_calc.py:862` — same formula used for post-earnings expected move. Same bug.
