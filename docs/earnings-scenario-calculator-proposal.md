# Earnings Scenario Calculator — Proposal

**Date**: 2026-02-10 (updated 2026-02-26)
**Status**: Brainstorming → PRD preparation
**Origin**: Discussion while tracking a live TOST 30C position through earnings

---

## Problem Statement

When holding options into an earnings event, the critical decision is: sell before earnings (lock in gains) or hold through (bet on outsized move). Robinhood's "Simulate My Returns" feature does not account for IV crush, making it appear that any post-earnings price increase is pure profit. In reality, IV crush can erase 40-50% of an option's time value overnight, meaning a stock can go UP and the option can go DOWN.

We already collect all the data needed to model this accurately (Greeks, IV, historical IV crush, earnings expected moves). We just don't present it in a decision-useful format.

**Use case**: Pre-market planning before trading day. Ben evaluates open positions (especially those near earnings) and decides whether to sell or hold. Not restricted to earnings day itself — swing trading often means evaluating days before the event. "vs Sell Now" applies any time you're holding.

## What It Does

Given a position (symbol, strike, expiry, option type, cost basis, quantity), produce a scenario table showing estimated option value and P/L across a range of post-earnings stock prices, **accounting for IV crush**.

### Primary Output: Scenario Table

```
TOST 30C 2/20 | Cost: $1.04 | Current: ~$1.60 | IV: 87.5%
Estimated post-earnings IV: ~48% (median crush: 46%)
Breakeven vs sell now: stock needs to move +7.0% ($31.74)
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

### Secondary Output: IV Crush Sensitivity Matrix (v1)

Shows how the breakeven and key scenarios shift across different crush assumptions:

```
Crush Sensitivity (stock move needed to break even vs sell now):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Crush     | Breakeven Move | Flat P/L  | Up 10% P/L
──────────|----------------|-----------|──────────
Mild  25% | +3.2%          | +$0.14    | +$1.85
Normal 46%| +7.0%          | -$0.32    | +$1.16
High  60% | +9.8%          | -$0.61    | +$0.72
Severe 75%| +13.1%         | -$0.88    | +$0.31
```

This answers "how bad is it if crush is worse than expected?" without running the tool multiple times.

### Breakeven Summary Line

Computed and displayed prominently at the top:

```
Breakeven vs sell now: stock needs to move +7.0% ($31.74)
```

This single number captures the entire hold-vs-sell decision. If the stock's expected/historical move exceeds this, holding has positive expected value. If not, sell.

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

**Accuracy validated against historical data (2026-02-26):** 92.7% of earnings moves (8,641 of 9,324 events) stay below 15%, where the second-order approximation is accurate. Only 7.3% exceed 15%, and 3.2% exceed 20%. The approximation is sufficient for v1. Extreme scenario rows (>15% move) should carry a note that estimates may diverge.

### Breakeven Calculation

The breakeven stock move (where hold-through equals sell-now) is found by solving:

```
delta × ΔS + 0.5 × gamma × (ΔS)² + vega × ΔIV + theta × Δt = 0
```

This is a quadratic in ΔS with known coefficients. The positive root (for calls) or negative root (for puts) gives the required stock move. The vega × ΔIV term (always negative for crush) is what makes this non-trivial — without crush, the breakeven is just flat.

### IV Crush Estimation

**Current data (2026-02-26):** Only 27 rows in `earnings_moves` have `iv_collapse_pct` populated (all from Jan-Feb 2026). Mean crush is -48.1%, consistent with the earlier 17-event sample. Far too small for per-symbol or per-sector estimates.

**Default approach:** `post_earnings_iv = pre_earnings_iv × 0.54` (i.e., 46% crush)

**Crush sensitivity tiers** (for the matrix):
- **Mild**: 25% crush — unusually low, happens when stock moves enough to maintain IV
- **Normal**: 46% crush — our median from available data
- **High**: 60% crush — common for stocks that don't move much
- **Severe**: 75% crush — worst case for flat/small moves

As `iv_collapse_pct` accumulates over Q1-Q2 2026, the default can be refined per-sector or per-symbol. The calculator should be designed so the crush estimate is a pluggable parameter.

### Scenario Price Points

Generated from `earnings_upcoming` data:
- `straddle_expected_move_pct` → the "expected" up/down scenarios
- `historical_avg_move_pct` → the "historical" up/down scenarios
- Fixed intervals: ±5%, flat
- Breakeven point: where "hold through" equals "sell now" value

If earnings data isn't available (non-earnings use case), fall back to fixed intervals only (±3%, ±5%, ±10%, flat).

## Data Sources

### Database Mode (pre-market, default)

| Data | Source Table | Field |
|------|-------------|-------|
| Greeks | `option_contracts` | delta, gamma, vega, theta |
| IV | `option_contracts` or `option_symbol_summary` | iv, iv_front_month |
| Option price | `option_contracts` | last_price, bid, ask |
| Stock price | `historical_prices` or `option_symbol_summary` | close_price |
| Expected move | `earnings_upcoming` | straddle_expected_move_pct |
| Historical move | `earnings_upcoming` | historical_avg_move_pct |
| Earnings date | `earnings_upcoming` | earnings_date |

All from `datalake_query.db`. Data is from previous close (Option Pipeline runs evening).

### Live Mode (intraday, `--live` flag)

| Data | Source | Method |
|------|--------|--------|
| Greeks + IV + Price | Tradier API | `get_option_chains()` with `greeks=true` |
| Stock price | Tradier API | Included in chain response or `get_quotes()` |
| Expected/Historical move | Database | Same as above (doesn't change intraday) |

**Implementation cost of live mode**: Minimal. Tradier's chain endpoint already returns Greeks. We fetch the full chain for the expiration (already cached 5 minutes), filter to the requested strike. ~15-20 lines of wrapper code on existing `core/tradier_api.py` infrastructure. No new API endpoints or authentication.

**Greek staleness warning**: In database mode, display the data timestamp and warn if Greeks are >1 day old. In live mode, this isn't an issue.

## Implementation Plan

### Architecture: Importable Module + CLI Wrapper

**`tools/earnings_scenario.py`** — the core module, importable and CLI-capable.

```python
from tools.earnings_scenario import calculate_scenarios, format_scenario_table

# Core calculation — returns structured data
# Contract hash is parsed: "SYMBOL|STRIKE|EXPIRY|TYPE"
result = calculate_scenarios(
    contract='TOST|30|2026-02-20|CALL',
    cost_basis=1.04,
    quantity=2,
    crush_pct=None,       # None = use default 46%, or override
    live=False            # True = fetch live Greeks from Tradier
)
# result = {
#     'scenarios': [...],          # List of scenario dicts
#     'breakeven_move_pct': 7.0,   # Required move to beat sell-now
#     'breakeven_price': 31.74,
#     'crush_matrix': [...],       # Sensitivity across crush levels
#     'data_timestamp': '...',     # When Greeks were last updated
#     'current_value': 1.60,       # Mid-price of option now
#     'warnings': [...]            # Stale data, extreme scenarios, etc.
# }

# Pretty-print for CLI or logging
format_scenario_table(result)
```

### CLI Interface

Contract is identified by a pipe-delimited hash: `SYMBOL|STRIKE|EXPIRY|TYPE` — the same format used in the database. Cost basis is always required (no position tracking in v1).

```bash
# Basic usage — database mode, default crush
python tools/earnings_scenario.py "TOST|30|2026-02-20|CALL" --cost 1.04

# With quantity (affects total P/L display, not per-contract math)
python tools/earnings_scenario.py "TOST|30|2026-02-20|CALL" --cost 1.04 --qty 2

# Override IV crush estimate
python tools/earnings_scenario.py "TOST|30|2026-02-20|CALL" --cost 1.04 --crush 60

# Live Greeks from Tradier API (intraday use)
python tools/earnings_scenario.py "DAY|62.5|2026-02-20|CALL" --cost 2.15 --live
```

### What It Does NOT Do (v1 scope)
- No position tracking / persistence — contract hash + `--cost` only
- No multi-leg / spread support — single long calls/puts only
- No bid-ask spread modeling
- No BSM repricing (Greek approximation only)
- No automatic notifications
- No per-symbol/sector crush estimates (uses fixed default)
- No Morning View integration
- No non-earnings scenarios — earnings-focused only
- No JSON/CSV output — text table to stdout only

## Research Findings (2026-02-26)

### Earnings Move Distribution (9,324 events, 2021–2026)

| Threshold | Count | % of Total |
|-----------|-------|------------|
| < 5%      | 5,379 | 57.7%      |
| 5-10%     | 2,425 | 26.0%      |
| 10-15%    | 837   | 9.0%       |
| **15-20%** | **384** | **4.1%** |
| **20-25%** | **141** | **1.5%** |
| **25%+**   | **158** | **1.7%** |

Mean absolute move: 5.84%. Max: 62.06%.

**Implication**: Greek approximation is safe for 92.7% of events. For the 7.3% with moves >15%, add a warning note but don't block the estimate.

### IV Crush Data Availability

Only 27 of 9,324 `earnings_moves` rows have `iv_collapse_pct` populated (all from Jan-Feb 2026). Mean: -48.1%. The `earnings_snapshots` collector was fixed 2026-02-25, so this will grow organically. Per-symbol estimates need ~2-3 quarters of data.

### Tradier Live Greeks

The `markets/options/chains` endpoint with `greeks=true` already returns delta, gamma, theta, vega, smv_vol for every contract. Chain responses are cached 5 minutes. Fetching live Greeks for a single contract = fetch chain + filter by strike/type. ~15 lines of new code.

## Known Limitations (v1)

1. **Greek approximation diverges for extreme moves (>15-20%)**: Covers 92.7% of events. Extreme scenarios get a disclaimer. Full BSM via `scipy` is a straightforward v2 enhancement.

2. **IV crush is a fixed estimate (46% default)**: Too few data points for dynamic estimates. The sensitivity matrix compensates by showing multiple crush scenarios at once. Dynamic estimates become feasible once `iv_collapse_pct` accumulates (~Q2 2026).

3. **Greeks may be stale in database mode**: Previous day's close via Option Pipeline. Tool displays data timestamp and warns if >1 day old. Live mode (`--live`) solves this entirely.

4. **No bid-ask spread modeling**: Estimated values are theoretical mid-prices. For liquid names this is fine; illiquid names may see 5-15% slippage. Could add a spread haircut in a future version.

5. **Single-leg only**: Long calls and puts. No spreads, straddles, or multi-leg. Matches Ben's trading style.

## Relationship to Other Work

- **EI Data Pipeline** (PRDs 0008-0010, complete): The `earnings_upcoming` table provides expected/historical moves and signals. The `earnings_moves` table will accumulate IV crush data over time. The scenario calculator is a consumer of this data.

- **Flow Monitor Alerts**: When a flow alert triggers on a symbol with upcoming earnings, the scenario calculator could help assess whether the alert is worth acting on given earnings risk.

- **Earnings Watchlist**: Symbols on the `earnings_watchlist` (WATCH/BUY/STRONG BUY) are natural candidates for scenario analysis.

- **Trading Style**: Designed around Ben's approach — long options, swing trading, sell before expiration, 25% profit target, <$300 positions, Robinhood platform. The "vs Sell Now" column and breakeven move are the key decision outputs.

## Open Questions (All Resolved)

1. ~~**Position tracking**~~ → **Resolved**: CLI args for v1. No persistence needed.
2. ~~**Contract input**~~ → **Resolved**: Pipe-delimited contract hash (`SYMBOL|STRIKE|EXPIRY|TYPE`), same format as database. One positional arg + `--cost`.
3. ~~**Non-earnings use case**~~ → **Resolved**: Earnings-focused for v1. General IV-change scenarios deferred.
4. ~~**Output format**~~ → **Resolved**: Text table only for v1. JSON/other formats added when there's a consumer.
5. **Historical validation** (future): Once `iv_collapse_pct` accumulates, we could backtest the calculator against actual earnings outcomes. Would build confidence in the estimates and help calibrate crush defaults.

## Future Enhancements (v2+)

- **Dynamic IV crush estimates**: Per-symbol or per-sector crush defaults based on accumulated `iv_collapse_pct` data
- **Full BSM repricing**: For moves >15%, use `scipy.stats.norm` to reprice via Black-Scholes instead of Greek approximation
- **Morning View integration**: Scenario table panel in TUI for positions near earnings
- **Position persistence**: `active_positions` table or JSON file for tracking open trades
- **Bid-ask spread haircut**: Apply estimated spread cost to output values
- **Notification integration**: Auto-generate scenario table when watchlist symbol's earnings date is within N days
- **Historical move context line**: "In the last N earnings, TOST moved more than X% only Y times" — data exists in `earnings_moves`
- **Multi-leg support**: Model spreads and straddles (different vega/delta profiles)
