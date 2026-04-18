# Observation: expected_move_pct Has Widespread Data Quality Issues

**Session:** 001 (2026-04-17)
**Status:** Bug identified, needs root cause analysis
**Confidence:** High — the data is clearly wrong

## The Data

Of 763 upcoming earnings events (as of 2026-04-17):
- 222 have `expected_move_pct` > 20% (29%)
- 127 have values > 50% (17%)
- 45 have values > 100% (6%)

Example outliers:
| Symbol | expected_move_pct | straddle_expected_move_pct | historical_avg_move_pct |
|--------|------------------|---------------------------|------------------------|
| ENTG | 230.1 | 12.68 | 6.58 |
| GEN | 228.93 | 8.81 | 5.85 |
| ACM | 180.64 | 7.53 | 3.82 |
| CROX | 140.03 | 12.3 | 14.24 |

The straddle values are reasonable. The expected_move_pct values are nonsensical — no stock has a 230% implied expected move for earnings.

## Impact Assessment

**Needs investigation:**
- What function calculates `expected_move_pct`? (Likely in `ei_moves_upcoming.py`)
- What else uses this field? If it only feeds `relative_underpricing_pct` with straddle as fallback, and straddle is usually populated, the impact may be minimal
- Does the earnings watchlist display show this value to Ben?

## Signal System Isolation

From CLAUDE.md: `relative_underpricing_pct` uses straddle as denominator, falls back to expected_move when straddle is NULL. So signals are ONLY affected for symbols where:
1. `straddle_expected_move_pct` is NULL, AND
2. `expected_move_pct` is wildly wrong

Need to check: how many symbols have NULL straddle but non-NULL expected_move?
