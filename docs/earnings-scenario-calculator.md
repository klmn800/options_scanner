# Earnings Scenario Calculator

**File**: `tools/earnings_scenario.py`
**Added**: 2026-02-28
**PRD**: `tasks/0011-prd-earnings-scenario-calculator.md`

## What It Does

Models post-earnings option values accounting for IV crush — the phenomenon where implied volatility drops sharply after an earnings announcement, erasing time value even when the stock moves in your favor. Produces a scenario table showing estimated option value, P/L, and a "vs Sell Now" comparison across a range of stock price outcomes.

The core question it answers: **"How much does the stock need to move in my favor for holding through earnings to beat selling now?"**

This is the information Robinhood's "Simulate My Returns" doesn't give you. Their tool assumes IV stays constant; this one models what actually happens.

## Usage

```bash
# Basic — uses Greeks from last Option Pipeline run (previous close)
python tools/earnings_scenario.py "SYMBOL|STRIKE|EXPIRY|TYPE" --cost PRICE

# Examples
python tools/earnings_scenario.py "MRVL|85|2026-03-20|CALL" --cost 4.60
python tools/earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --live
python tools/earnings_scenario.py "DAY|62.5|2026-02-20|CALL" --cost 2.15 --qty 2 --crush 60

# Straddle mode — model both call and put at same strike
python tools/earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --straddle --put-cost 0.50
python tools/earnings_scenario.py "TOST|25|2026-04-17|PUT" --cost 0.50 --straddle --call-cost 1.04
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `contract` | Yes | Contract hash: `SYMBOL\|STRIKE\|EXPIRY\|TYPE` (positional) |
| `--cost` | Yes | Cost basis per contract in dollars |
| `--qty N` | No | Number of contracts (default: 1). Adds Total P/L column |
| `--crush N` | No | Override IV crush % (default: 46%). Affects main table only, not sensitivity matrix |
| `--live` | No | Fetch current Greeks from Tradier API instead of database |
| `--no-guide` | No | Suppress the interpretive guide section at the bottom |
| `--straddle` | No | Model a straddle (infer opposite leg at same strike/expiry) |
| `--put-cost N` | No | Cost of the put leg (required with `--straddle` when primary is CALL) |
| `--call-cost N` | No | Cost of the call leg (required with `--straddle` when primary is PUT) |

### Data Modes

- **Database mode** (default): Reads Greeks and pricing from `option_contracts` in `datalake_query.db`. Data is from the previous close (Option Pipeline runs in the evening). Displays the data timestamp and warns if stale.
- **Live mode** (`--live`): Fetches current Greeks from Tradier API. Works during and after market hours. Uses the existing chain endpoint with 5-minute caching. Adds one quote API call for the underlying stock price.
- **Fallback**: If the contract isn't found in the database, the tool prompts whether to try Tradier live.

## How to Read the Output

### Header

```
MRVL 85C 3/20 | Cost: $4.60 | Current: $4.70 | Stock: $81.69 | IV: 78.0%
Data: 2026-02-27 (Option Pipeline) | Earnings: 2026-03-05 amc
Estimated post-earnings IV: ~42% (46% crush) | Underpricing: 16.2%
Breakeven vs sell now: stock needs to move +7.9% ($88.17)
```

- **Current**: Option mid-price (bid+ask)/2 right now
- **Stock**: Current underlying stock price
- **IV**: Current implied volatility (will crush after earnings)
- **Estimated post-earnings IV**: What IV drops to after the crush
- **Underpricing**: How much the market is underestimating the stock's typical earnings move (primarily a buy/entry signal; 15%+ = WATCH, 30%+ = BUY, 50%+ = STRONG BUY)
- **Breakeven**: The single most important number — the minimum stock move for holding through earnings to beat selling now

### Scenario Table

Each row shows a different stock price outcome after earnings:

- **Scenario**: The stock move. "exp" = market-expected move (from straddle pricing). "hist" = average move from past earnings. If hist > exp, the market may be underpricing the move; if they're close, it's fairly priced.
- **Stock**: The stock price at that scenario
- **Est Value**: Estimated option value after IV crush + stock move + theta decay
- **P/L**: Gain/loss vs your cost basis
- **P/L %**: Same as P/L, as a percentage
- **vs Sell Now**: How much better or worse holding through is compared to selling now. **This is the decision column.** Negative = selling now wins. Positive = holding wins.

The `SELL NOW` row at the bottom shows what you'd get by selling before earnings — the baseline for comparison.

### Crush Sensitivity Matrix

Shows how your breakeven and key scenarios shift across different IV crush levels:

| Tier | Crush % | Description |
|------|---------|-------------|
| Minimal | 20% | Unusual — stock moved enough to maintain IV |
| Mild | 32% | Below average crush |
| Normal | 46% | Median from available data (default) |
| High | 57% | Common when stock doesn't move much |
| Severe | 70% | Worst case — flat or small move |

These tiers match the Earnings Intelligence 5-tier IV crush severity scale used throughout the system.

The `<-- default` marker shows which tier is closest to your chosen crush setting. If you override with `--crush 60`, the marker moves to "High (57%)" as the closest tier.

### Straddle Mode

When using `--straddle`, the tool fetches both the call and put at the same strike/expiry and models them independently with their own Greeks and IV. The output adds:

- **Header**: Shows per-leg costs (Call: $X / Put: $Y / Combined: $Z) and per-leg current values
- **Dual breakevens**: "stock needs to move -X% or +Y%" — both directions where holding beats selling
- **Call Est / Put Est columns**: What each leg is worth in each scenario
- **Combined column**: Sum of both legs — the position value
- **Crush sensitivity**: Two breakeven columns (BE Down / BE Up) showing both roots

The straddle is always arranged as [call, put] regardless of which leg you provide as the primary. Providing the call or the put as the primary contract produces identical output.

**When is the straddle underpriced?** Compare the expected/historical move to your breakeven. If both exceed the breakeven in either direction, the straddle is paying you for what historically happens. If the breakevens are wider than expected moves, IV crush erodes more than the position gains.

## The Math

Second-order Greek approximation:

```
new_value = current_value + delta*dS + 0.5*gamma*(dS)^2 + vega*dIV + theta*dt
```

- **delta x dS**: How the option value changes with the stock move
- **0.5 x gamma x dS^2**: Correction for large moves (delta itself changes)
- **vega x dIV**: The IV crush impact (always negative — this is what Robinhood ignores)
- **theta x dt**: Time decay until earnings

The breakeven is found by solving this as a quadratic equation for dS (the stock move that makes the whole expression equal zero).

### Accuracy

Validated against 9,324 historical earnings events:
- 92.7% of moves stay below 15%, where the approximation is accurate
- Scenarios with moves >15% display a disclaimer
- Math was hand-verified during development (flat scenario and breakeven both match manual calculation)

### Vega Convention

Tradier's vega is per percentage point of IV change (per 0.01 change in sigma). The calculator handles this correctly: `dIV = -(iv_decimal * crush_percent)`, giving the change in percentage points.

## Data Sources

| Data | Source |
|------|--------|
| Greeks (delta, gamma, vega, theta) | `option_contracts` or Tradier API |
| Implied Volatility | `option_contracts.iv` or Tradier `smv_vol` |
| Option price (bid/ask) | `option_contracts` or Tradier API |
| Stock price | `option_contracts.underlying_price` or Tradier quotes |
| Expected move | `earnings_upcoming.straddle_expected_move_pct` |
| Historical move | `earnings_upcoming.historical_avg_move_pct` (recent 6Q avg; all-time in `historical_avg_move_alltime_pct`) |
| Underpricing | `earnings_upcoming.relative_underpricing_pct` |
| Earnings date/time | `earnings_upcoming.earnings_date` / `earnings_time` |

All database reads use `datalake_query.db` (never production).

## Known Limitations

1. **Greek approximation, not Black-Scholes repricing**: Accurate for moves under ~15% (92.7% of earnings). For extreme moves, estimates may diverge. Full BSM repricing via `scipy` is a potential future enhancement.

2. **IV crush is estimated, not predicted**: The 46% default is the median from available data (27 events). Actual crush varies by stock, sector, and market conditions. The sensitivity matrix shows the range of possibilities.

3. **Database Greeks are from previous close**: Option Pipeline runs in the evening, so database mode Greeks are ~12-18 hours old by morning. Use `--live` for current data.

4. **No bid-ask spread modeling**: Estimated values are theoretical mid-prices. Illiquid names may see 5-15% slippage when actually selling.

5. **Single-leg and straddle only**: Long calls, puts, and straddles (same-strike call+put). No spreads, strangles, or arbitrary multi-leg positions yet.

## Files

- `tools/earnings_scenario.py` — Calculator module and CLI (~580 lines)
- `core/tradier_api.py` — `get_contract_greeks()` method for live mode
- `docs/_local/earnings-scenario-calculator-proposal.md` (parked) — Original proposal with research findings
- `tasks/0011-prd-earnings-scenario-calculator.md` — PRD with all functional requirements
- `tasks/tasks-0011-prd-earnings-scenario-calculator.md` — Implementation task list (22 sub-tasks, all complete)

## Future Enhancements

- **Dynamic IV crush estimates**: Per-symbol or per-sector defaults once `iv_collapse_pct` accumulates in `earnings_moves` (~Q2 2026)
- **Full BSM repricing**: For extreme move scenarios (>15%)
- **Morning View TUI integration**: Scenario table panel for positions near earnings
- **Position persistence**: Track open positions for automatic scenario generation
- **Historical move context**: "In the last N earnings, MRVL moved more than X% only Y times"
- **Bid-ask spread haircut**: Apply estimated spread cost to output values
- **Non-earnings scenarios**: General IV-change modeling (not just earnings)
