# Observation: False STRONG BUY Signals from Stale/Illiquid Straddle Data

**Session:** 002 (2026-04-18)
**Status:** Root cause identified, fix path clear
**Confidence:** High — traced from data through code, verified with specific symbols
**Proposal:** 001_signal_quality_bundle.md (Finding 1)

## Summary

50% of STRONG BUY earnings signals (5 of 10) are based on garbage straddle data. Root causes: stale option_contracts data and illiquid ATM strikes with stale `last_price` values.

## Evidence

| Symbol | Straddle % | Underpricing % | Latest Option Data | Verdict |
|--------|-----------|----------------|-------------------|---------|
| EXAS | 0.09% | 9,082% | Mar 20 (28d stale) | FALSE |
| APLS | 1.29% | 454% | Apr 17 (fresh but illiquid ATM) | SUSPECT |
| AL | 0.59% | 442% | Apr 13 (5d stale) | FALSE |
| SEE | 1.61% | 216% | Apr 9 (9d stale) | FALSE |
| HOLX | 1.17% | 201% | Apr 9 (9d stale) | FALSE |

## Root Cause Details

### Staleness
`get_straddle_expected_move()` at `ei_moves_upcoming.py:259` gets stock price from `MAX(trade_date)` in `historical_prices`, then queries `option_contracts` on that same date. EXAS had latest historical_prices from March 20 and option_contracts from April 2 — data was already old when the straddle was calculated.

The UPDATE uses `COALESCE(?, straddle_expected_move_pct)` (line 567), so a NULL new value never overwrites an existing stale value. Once a stale straddle is stored, it persists until a fresh, non-NULL value replaces it.

### Illiquidity (APLS case)
Even with fresh data (April 17), the $41 ATM strike had:
- Call: last_price=$0.05, bid=$0.00, ask=$0.05
- Put: last_price=$0.57, bid=$0.00, ask=$0.75

The `last_price` for the call ($0.05) is from some historical trade, not the current market. The actual market (bid/ask midpoint) would give a very different straddle estimate. Meanwhile, the $40 strike had call=$1.05 with bid=$0.50 — much more reliable but wasn't selected because $41 is closer to $40.90 stock price.

## Impact

The signal list ranks EXAS at the top with 9,082% underpricing, followed by APLS at 454% and AL at 442%. The legitimate STRONG BUY signals (UNH 107%, WBD 97%, AES 86%) are buried below the garbage. Anyone scanning the signal list top-to-bottom gets misled.

## Fix

See Proposal 001, Finding 1 for detailed fix options. Minimum viable: staleness guard + bid>0 requirement. Better: midpoint pricing + sanity floor on straddle values.
