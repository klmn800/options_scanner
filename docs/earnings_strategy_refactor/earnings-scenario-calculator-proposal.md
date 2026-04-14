# Earnings Scenario Calculator — Proposal

**Date**: 2026-02-10
**Status**: Proposal (not yet implemented)
**Origin**: Discussion while tracking a live TOST 30C position through earnings

---

## Problem Statement

When holding options into an earnings event, the critical decision is: sell before earnings (lock in gains) or hold through (bet on outsized move). Robinhood's "Simulate My Returns" feature does not account for IV crush, making it appear that any post-earnings price increase is pure profit. In reality, IV crush can erase 40-50% of an option's time value overnight, meaning a stock can go UP and the option can go DOWN.

We already collect all the data needed to model this accurately (Greeks, IV, historical IV crush, earnings expected moves). We just don't present it in a decision-useful format.

## What It Does

Given a position (symbol, strike, expiry, option type, cost basis, quantity), produce a scenario table showing estimated option value and P/L across a range of post-earnings stock prices, **accounting for IV crush**.

### Example Output

```
TOST 30C 2/20 | Cost: $1.04 | Current: ~$1.60 | IV: 87.5%
Estimated post-earnings IV: ~48% (median crush: 44%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scenario       | Stock  | Est Value | P/L     | P/L %  | vs Sell Now
───────────────|--------|-----------|---------|--------|───────────
Down 13% (hist)| $25.80 | $0.01     | -$1.03  | -99%   | -$1.59
Down 10% (exp) | $26.69 | $0.05     | -$0.99  | -95%   | -$1.55
Down 5%        | $28.18 | $0.35     | -$0.69  | -66%   | -$1.25
Flat           | $29.66 | $0.72     | -$0.32  | -31%   | -$0.88
Up 5%          | $31.14 | $1.42     | +$0.38  | +37%   | -$0.18
Up 7%          | $31.74 | $1.72     | +$0.68  | +65%   | +$0.12  <-- BREAKEVEN vs sell now
Up 10% (exp)   | $32.63 | $2.20     | +$1.16  | +112%  | +$0.60
Up 13% (hist)  | $33.52 | $2.77     | +$1.73  | +166%  | +$1.17
───────────────|--------|-----------|---------|--------|───────────
SELL NOW       |   —    | ~$1.60    | +$0.56  | +54%   |   —
```

Key columns:
- **Est Value**: Option value after IV crush + stock move + theta decay
- **P/L**: Gain/loss vs cost basis
- **vs Sell Now**: Comparison to just selling before earnings — the actual decision metric

## Core Math

### Option P/L Decomposition (Second-Order)

The standard options P/L model using Greeks:

```
ΔOption ≈ delta × ΔS + 0.5 × gamma × (ΔS)² + vega × ΔIV + theta × Δt
```

Where:
- `ΔS` = stock price change in dollars
- `ΔIV` = change in implied volatility (negative for crush)
- `Δt` = time elapsed in days (typically 1-2 for post-earnings)

The **second-order term** (`0.5 × gamma × ΔS²`) corrects for the fact that delta itself changes as the stock moves. Without it, large moves are underestimated (for winning scenarios) and overestimated (for losing scenarios). We already collect gamma on every contract.

### IV Crush Estimation

From our own data (17 earnings events measured in `option_symbol_summary`):
- **Median IV crush**: 46.2% reduction in `iv_front_month`
- **Average**: 44.3%
- **Range**: -27% to 68% (one outlier where IV rose)
- **Most common bucket**: 35-50% (41% of events)

Default estimate: `post_earnings_iv = pre_earnings_iv × 0.54` (i.e., 46% crush)

As we accumulate more data points, this can be refined per-symbol or per-sector. The `iv_collapse_pct` field in `earnings_moves` is designed for this but currently unpopulated — the EI data pipeline upgrade (separate project) will backfill it.

### Scenario Price Points

Generated from `earnings_upcoming` data:
- `straddle_expected_move_pct` → the "expected" up/down scenarios
- `historical_avg_move_pct` → the "historical" up/down scenarios
- Fixed intervals: ±5%, flat
- Breakeven point: where "hold through" equals "sell now" value

## Data Sources (All Existing)

| Data | Source Table | Field |
|------|-------------|-------|
| Current Greeks | `option_contracts` | delta, gamma, vega, theta |
| Current IV | `option_contracts` or `option_symbol_summary` | iv, iv_front_month |
| Current option price | `option_contracts` | last_price, bid, ask |
| Stock price | `historical_prices` or `option_symbol_summary` | close_price |
| Expected move | `earnings_upcoming` | straddle_expected_move_pct |
| Historical move | `earnings_upcoming` | historical_avg_move_pct |
| IV crush estimate | Computed from `option_symbol_summary` | iv_front_month pre/post |
| Earnings date | `earnings_upcoming` | earnings_date |

No new data collection required. This is purely a presentation/calculation layer on top of existing data.

## Implementation Options

### Option A: CLI Tool (Recommended for Phase 1)

`tools/earnings_scenario.py`

```bash
# Basic usage — looks up current position data automatically
python tools/earnings_scenario.py --symbol TOST --strike 30 --type call --expiry 2026-02-20 --cost 1.04 --qty 2

# Override IV crush estimate
python tools/earnings_scenario.py --symbol TOST --strike 30 --type call --expiry 2026-02-20 --cost 1.04 --crush 50

# Output as JSON (for Morning View integration)
python tools/earnings_scenario.py --symbol TOST --strike 30 --type call --expiry 2026-02-20 --cost 1.04 --output json
```

Pros: Fast to build, immediately useful, no UI dependencies
Cons: Manual invocation, not integrated into workflow

### Option B: Morning View Integration (Phase 2)

Add a panel or screen to the Morning View TUI that:
1. Reads active positions (manually entered or from a positions table)
2. Auto-detects if symbol has upcoming earnings
3. Displays the scenario table inline with existing symbol analysis

Would require a positions tracking mechanism (even a simple JSON file or DB table).

### Option C: Importable Module (Supports Both)

Build the core calculation as an importable function:

```python
from tools.earnings_scenario import calculate_scenarios

scenarios = calculate_scenarios(
    symbol='TOST',
    strike=30.0,
    option_type='call',
    expiry='2026-02-20',
    cost_basis=1.04,
    quantity=2
)
# Returns list of scenario dicts with all values
```

This lets the CLI tool and Morning View both use the same engine.

**Recommendation**: Option C (module) + Option A (CLI wrapper) first. Morning View integration later.

## Known Limitations

1. **Greek-based approximation, not Black-Scholes repricing**: The second-order Taylor expansion is accurate for moves up to ~15-20% but diverges for extreme moves. For earnings, this is usually sufficient since moves beyond 20% are rare. A future enhancement could use full BSM repricing via `scipy`.

2. **IV crush is estimated, not predicted**: We use the median historical crush (~46%) as a default. In reality, crush varies by stock, sector, and market regime. Per-symbol crush estimates would be better (requires backfilling `iv_collapse_pct` in earnings_moves — in progress with EI upgrade).

3. **Greeks are stale by morning**: Our Greeks are from the previous day's close via Option Pipeline. By the time you're making a sell/hold decision on earnings day, intraday movement may have shifted delta/gamma. The tool should note the data timestamp and warn if >1 day old.

4. **No bid-ask spread modeling**: Estimated option values don't account for the spread you'd actually face when selling. For liquid names this is minor; for illiquid names it matters. Could add a spread haircut as a future enhancement.

5. **Single-leg only**: Designed for Ben's trading style (long calls/puts). Does not model spreads, straddles, or multi-leg positions.

## Relationship to Other Work

- **EI Data Pipeline Upgrade** (separate developer): Backfilling `iv_collapse_pct`, `relative_underpricing_pct`, recalibrating signal thresholds. This calculator benefits from that work (better IV crush estimates per symbol) but does not depend on it — the median estimate works fine as a starting point.

- **Flow Monitor Alerts**: When a flow alert triggers on a symbol with upcoming earnings, the scenario calculator could be referenced to assess whether the alert is worth acting on given the earnings risk.

- **Trading Style**: Designed around Ben's approach — long options, swing trading, sell before expiration, 25% profit target, <$300 positions, Robinhood platform. The "vs Sell Now" column is the key decision metric for this style.

## Open Questions

1. **Position tracking**: Currently no mechanism to record "I bought X at Y price." Should this tool accept manual input (CLI args), read from a file, or should we build a simple positions table? A lightweight `active_positions` table or JSON file might be the simplest start.

2. **Historical validation**: Once `iv_collapse_pct` is backfilled, we could run the scenario calculator retroactively on past earnings to see how accurate its estimates would have been. This would build confidence in the tool and help calibrate the IV crush default.

3. **Notification integration**: Should the tool automatically generate a scenario table when a watchlist symbol's earnings date is within N days? Could integrate with the email notification system.
