# PRD 0011: Earnings Scenario Calculator

**Date**: 2026-02-26
**Status**: Draft
**Proposal**: `docs/earnings-scenario-calculator-proposal.md`

---

## 1. Introduction / Overview

When holding options into an earnings event, the critical decision is: sell before earnings (lock in gains) or hold through (bet on outsized move). Robinhood's "Simulate My Returns" feature does not account for IV crush, making it appear that any post-earnings price increase is pure profit. In reality, IV crush can erase 40-50% of an option's time value overnight, meaning a stock can go UP and the option can go DOWN.

The Earnings Scenario Calculator is a CLI tool and importable module that takes a position (contract hash + cost basis), models post-earnings option values across a range of stock price scenarios accounting for IV crush, and presents a clear decision framework: **should I sell now or hold through earnings?**

The system already collects all necessary data (Greeks, IV, historical moves, expected moves). This tool is a pure calculation and presentation layer — no new data collection required.

## 2. Goals

1. **Accurate IV-crush-aware scenario modeling**: Produce estimated post-earnings option values that account for delta, gamma, vega (IV crush), and theta decay — not just stock price movement.
2. **Clear sell-vs-hold decision metric**: The "vs Sell Now" column and breakeven summary line should make the hold-through-earnings decision obvious at a glance.
3. **IV crush sensitivity visibility**: Show how scenarios change across different crush severities (using the existing EI 5-tier scale) so the user understands risk across assumptions.
4. **Two data modes**: Database mode (pre-market, using previous close data from Option Pipeline) and live mode (intraday, fetching current Greeks from Tradier API).
5. **Zero friction**: Single command, one positional arg (contract hash) + cost basis. No setup, no configuration, no position tracking.

## 3. User Stories

**US-1**: As a swing trader holding a call option on a stock reporting earnings tomorrow, I want to see what my option would be worth across a range of post-earnings stock prices (accounting for IV crush) so I can decide whether to sell before earnings or hold through.

**US-2**: As a trader evaluating a position several days before earnings, I want to see the breakeven stock move — the minimum move needed for holding through earnings to beat selling now — so I can compare it to the stock's historical and expected earnings moves.

**US-3**: As a trader who is uncertain about how severe IV crush will be, I want to see a sensitivity matrix showing how my breakeven changes across mild, normal, high, and severe crush scenarios so I understand my risk range.

**US-4**: As a trader making intraday decisions, I want to fetch live Greeks from Tradier (instead of stale previous-close data) so my scenario estimates reflect current market conditions.

## 4. Functional Requirements

### 4.1 Input

**FR-1**: The tool accepts a contract hash as a positional argument in the format `SYMBOL|STRIKE|EXPIRY|TYPE` (e.g., `"TOST|30|2026-02-20|CALL"`). This is the same pipe-delimited format used in the database.

**FR-2**: The tool requires `--cost` (cost basis per contract, in dollars). This is always manual input — no position tracking.

**FR-3**: The tool accepts optional arguments:
- `--qty N` — quantity of contracts (default: 1). Affects total P/L display only, not per-contract math.
- `--crush N` — override default IV crush percentage (default: 46%). Overrides the default used in the main scenario table but does NOT affect the sensitivity matrix (which always shows all tiers).
- `--live` — fetch current Greeks from Tradier API instead of database. Requires market hours / active API.

### 4.2 Data Retrieval

**FR-4**: In **database mode** (default), the tool queries `datalake_query.db` for:
- Contract Greeks (delta, gamma, vega, theta) and IV from `option_contracts` — most recent `trade_date` for the matching contract
- Current option price (mid of bid/ask, or last_price) from the same row
- Underlying stock price from `option_contracts` (underlying_price) or `historical_prices`
- Expected move (`straddle_expected_move_pct`) and historical move (`historical_avg_move_pct`) from `earnings_upcoming` for the symbol
- Earnings date from `earnings_upcoming`

**FR-5**: In **live mode** (`--live`), the tool calls Tradier API:
- Fetches the option chain for the symbol + expiration with `greeks=true`
- Filters to the matching strike and type
- Extracts delta, gamma, vega, theta, IV (smv_vol), bid, ask, last price
- Still queries database for earnings data (expected/historical moves, earnings date) since those don't change intraday

**FR-6**: If the contract is not found in the database, the tool prompts the user: `"Contract not found in database. Fetch live from Tradier? (y/n)"`. If yes, switches to live mode. If no, exits with a descriptive error.

**FR-7**: In database mode, the tool displays the data timestamp (trade_date from the option_contracts row) and warns if it is more than 1 calendar day old.

### 4.3 Scenario Calculation

**FR-8**: The tool generates scenario rows using the second-order Greek approximation:

```
ΔOption ≈ delta × ΔS + 0.5 × gamma × (ΔS)² + vega × ΔIV + theta × Δt
```

Where:
- `ΔS` = stock price change in dollars (from scenario percentage × current stock price)
- `ΔIV` = change in implied volatility (current IV × crush fraction, always negative)
- `Δt` = days until earnings (from earnings_date minus current date, minimum 1)

**FR-9**: The tool generates the following scenario rows:
- Down by historical average move (labeled "Down X% (hist)")
- Down by expected move (labeled "Down X% (exp)")
- Down 5%
- Flat (0%)
- Up 5%
- Breakeven vs sell-now (calculated, labeled with exact %)
- Up by expected move (labeled "Up X% (exp)")
- Up by historical average move (labeled "Up X% (hist)")
- If historical and expected moves are within 1% of each other, consolidate into one row

If earnings data is not available for the symbol (not in `earnings_upcoming`), omit the expected/historical rows and use fixed intervals only: ±3%, ±5%, ±10%, flat, breakeven.

**FR-10**: The "SELL NOW" row at the bottom shows the current option value (mid-price) and P/L vs cost basis, with no "vs Sell Now" value.

**FR-11**: All estimated option values are floored at $0.00. Options cannot have negative value.

**FR-12**: Scenario rows where the absolute stock move exceeds 15% should display a footnote marker (e.g., `*`) with a note: "* Estimates for moves >15% may be less accurate (Greek approximation limits)."

### 4.4 Breakeven Calculation

**FR-13**: The tool calculates the exact breakeven stock move percentage where "hold through" equals "sell now" by solving the quadratic:

```
delta × ΔS + 0.5 × gamma × (ΔS)² + vega × ΔIV + theta × Δt = 0
```

The positive root (for calls) or negative root (for puts) gives the required stock move. This is displayed both:
- As a prominent summary line at the top: `"Breakeven vs sell now: stock needs to move +7.0% ($31.74)"`
- As an interpolated row in the scenario table

**FR-14**: If the breakeven move is unreachable (e.g., option is so deep OTM that no reasonable move saves it), display: `"Breakeven vs sell now: not achievable within ±30% move"`.

### 4.5 IV Crush Sensitivity Matrix

**FR-15**: Below the main scenario table, display a sensitivity matrix showing how key outputs change across the existing EI 5-tier IV crush severity scale:

| Tier | Representative Crush % |
|------|----------------------|
| Minimal | 20% |
| Mild | 32% |
| Normal | 46% (default) |
| High | 57% |
| Severe | 70% |

These representative values are the midpoints of each EI tier (minimal <25%, mild 25-40%, normal 40-50%, high 50-65%, severe >65%).

**FR-16**: The matrix shows, for each crush tier:
- Breakeven move % needed
- P/L if stock is flat
- P/L at the expected move (up, for calls; down, for puts)

**FR-17**: The `--crush` override affects the main scenario table's default crush but does NOT change the sensitivity matrix, which always shows all 5 tiers for comparison.

### 4.6 Output

**FR-18**: Output is a formatted text table printed to stdout. The layout includes:
1. Header line: contract description, cost basis, current value, current IV
2. Crush estimate line: estimated post-earnings IV
3. Breakeven summary line
4. Separator
5. Scenario table with columns: Scenario, Stock Price, Est Value, P/L, P/L %, vs Sell Now
6. SELL NOW row
7. Separator
8. Crush sensitivity matrix
9. Footnotes (stale data warning, >15% move disclaimer if applicable)

**FR-19**: If `--qty` is provided and > 1, add a "Total P/L" column showing per-contract P/L × quantity × 100 (options multiplier).

### 4.7 Architecture

**FR-20**: The tool is implemented as `tools/earnings_scenario.py` with:
- An importable `calculate_scenarios(contract, cost_basis, ...)` function that returns a structured dict
- An importable `format_scenario_table(result)` function that returns a formatted string
- A `__main__` CLI block using argparse

**FR-21**: For live mode, add a `get_contract_greeks(symbol, strike, expiration, option_type)` helper to `core/tradier_api.py` that fetches the chain and filters to the matching contract. Uses existing chain caching (5-minute TTL).

## 5. Non-Goals (Out of Scope)

- **Position tracking or persistence** — no database tables, no JSON files, no saved positions
- **Multi-leg / spread support** — single long calls and puts only
- **Bid-ask spread modeling** — estimates are theoretical mid-prices
- **Full Black-Scholes repricing** — Greek approximation only (covers 92.7% of earnings moves)
- **Per-symbol or per-sector crush estimates** — fixed default + manual override only (insufficient data for dynamic estimates until Q2 2026)
- **Morning View TUI integration** — no screens, no panels, no hotkeys
- **Automatic notifications** — no email, no scheduled runs
- **Non-earnings scenarios** — tool is earnings-focused; general IV-change modeling deferred
- **JSON / CSV / HTML output** — text table to stdout only

## 6. Design Considerations

### Output Example

```
DAY 62.5C 2/20 | Cost: $2.15 | Current: $3.40 | IV: 94.2%
Data: 2026-02-19 (Option Pipeline) | Earnings: 2026-02-20 BMO
Estimated post-earnings IV: ~51% (46% crush)
Breakeven vs sell now: stock needs to move +6.3% ($66.54)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Scenario        | Stock   | Est Value | P/L     | P/L %  | vs Sell Now
────────────────|---------|-----------|---------|--------|────────────
Down 11.2% (hist)| $55.58 | $0.00     | -$2.15  | -100%  | -$3.40
Down 8.5% (exp) | $57.27 | $0.02     | -$2.13  | -99%   | -$3.38
Down 5%         | $59.46 | $0.18     | -$1.97  | -92%   | -$3.22
Flat            | $62.59 | $1.05     | -$1.10  | -51%   | -$2.35
Up 5%           | $65.72 | $2.48     | +$0.33  | +15%   | -$0.92
Up 6.3%         | $66.54 | $3.40     | +$1.25  | +58%   |  $0.00  ← BREAKEVEN
Up 8.5% (exp)   | $67.91 | $4.22     | +$2.07  | +96%   | +$0.82
Up 11.2% (hist) | $69.60 | $5.30     | +$3.15  | +147%  | +$1.90
────────────────|---------|-----------|---------|--------|────────────
SELL NOW        |    —    | $3.40     | +$1.25  | +58%   |    —

Crush Sensitivity:
────────────────|---------|-----------|---------|────────────
Crush           | Brkeven | Flat P/L  | Up 8.5% P/L
────────────────|---------|-----------|────────────
Minimal   (20%) | +2.8%   | +$0.32    | +$3.15
Mild      (32%) | +4.4%   | -$0.35    | +$2.10
Normal    (46%) | +6.3%   | -$1.10    | +$2.07  ← default
High      (57%) | +8.0%   | -$1.68    | +$0.95
Severe    (70%) | +10.2%  | -$2.01    | +$0.22
```

### Console Output Patterns

This tool prints directly to stdout (not through `log_utils.py` or `beautiful_log`). It's a standalone CLI tool, not part of the orchestrator pipeline. No logging infrastructure needed — just `print()`.

## 7. Technical Considerations

### Dependencies

- **No new dependencies**. All math is basic arithmetic (quadratic formula). No `scipy`, no `numpy`.
- Uses existing `core/tradier_api.py` for live mode
- Uses existing `tools/direct_db_query.py` patterns (or direct sqlite3) for database queries
- Queries `datalake_query.db` (never production `datalake.db`)

### Data Sources

| Data | Database Mode Source | Live Mode Source |
|------|---------------------|-----------------|
| Greeks (delta, gamma, vega, theta) | `option_contracts` | Tradier chain API |
| IV | `option_contracts.iv` | Tradier chain API (`smv_vol`) |
| Option price | `option_contracts` (bid/ask/last) | Tradier chain API |
| Stock price | `option_contracts.underlying_price` | Tradier chain API |
| Expected move | `earnings_upcoming` | `earnings_upcoming` (same) |
| Historical move | `earnings_upcoming` | `earnings_upcoming` (same) |
| Earnings date/time | `earnings_upcoming` | `earnings_upcoming` (same) |

### Contract Hash Parsing

Input format: `"SYMBOL|STRIKE|EXPIRY|TYPE"`
- `SYMBOL`: string (e.g., `DAY`, `TOST`, `NVDA`)
- `STRIKE`: float (e.g., `62.5`, `30`, `150`)
- `EXPIRY`: date string `YYYY-MM-DD` (e.g., `2026-02-20`)
- `TYPE`: `CALL` or `PUT` (case-insensitive)

### Database Query for Contract Matching

```sql
SELECT delta, gamma, vega, theta, iv, bid, ask, last_price,
       underlying_price, trade_date
FROM option_contracts
WHERE symbol = ?
  AND strike = ?
  AND expiration_date = ?
  AND option_type = ?
ORDER BY trade_date DESC
LIMIT 1
```

### Tradier Live Greeks

Add to `core/tradier_api.py`:

```python
def get_contract_greeks(self, symbol, strike, expiration, option_type):
    """Fetch current Greeks for a single option contract.
    Fetches full chain (cached 5min) and filters to matching contract.
    Returns dict with delta, gamma, theta, vega, iv, bid, ask, last_price
    or None if not found.
    """
```

This is ~15-20 lines wrapping the existing `get_option_chains()` method with strike/type filtering and the safe `(greeks or {}).get()` pattern.

### Math Notes

**Second-order Greek approximation:**
```
new_value = current_value + delta*ΔS + 0.5*gamma*(ΔS)² + vega*ΔIV + theta*Δt
```

**IV crush calculation:**
```
ΔIV = -(current_iv × crush_fraction)
# e.g., current_iv=0.942, crush=46% → ΔIV = -(0.942 × 0.46) = -0.4333
```

**Breakeven (quadratic solve):**
```
0.5*gamma*(ΔS)² + delta*(ΔS) + (vega*ΔIV + theta*Δt) = 0
# Standard quadratic: a=0.5*gamma, b=delta, c=(vega*ΔIV + theta*Δt)
# ΔS = (-b ± sqrt(b² - 4ac)) / 2a
# Take positive root for calls, negative for puts
```

**Theta Δt calculation:**
```
Δt = max(1, (earnings_date - today).days)
# Minimum 1 day — even on earnings day itself, there's overnight theta
```

## 8. Success Metrics

1. **Accuracy check**: Run the calculator on a position before earnings, then compare the "flat" scenario estimate to the actual post-earnings option price when the stock barely moves. If within 15% of estimated value, the model is working.
2. **Decision utility**: Ben uses the tool at least once before an earnings event and finds the breakeven / vs-sell-now information useful for the sell/hold decision.
3. **Speed**: Calculator produces output in <2 seconds (database mode) or <5 seconds (live mode).

## 9. Open Questions

1. **Historical validation** (future, not blocking): Once `iv_collapse_pct` accumulates in `earnings_moves` (~Q2 2026), backtest the calculator against actual outcomes to calibrate the default crush estimate and validate accuracy.
2. **Crush tier representative values**: The 5-tier midpoints (20%, 32%, 46%, 57%, 70%) are reasonable defaults. After accumulating real crush data, these could be replaced with actual percentile values from the distribution.
