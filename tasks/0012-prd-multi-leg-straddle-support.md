# PRD 0012: Multi-Leg Position Support (Straddle)

**Date**: 2026-02-28
**Status**: Complete
**Depends on**: PRD 0011 (Earnings Scenario Calculator — complete)

---

## Context

The Earnings Scenario Calculator (PRD 0011) models single-leg options through earnings.
Ben identified that straddles — buying both a call and put at the same strike — are where
IV crush modeling is *more* valuable, because traders often underestimate how much crush
erodes both legs simultaneously. A stock can move in the expected direction and the
straddle still loses money.

This PRD adds straddle support to the existing tool by refactoring the internals to work
with a list of "legs" (the multi-leg foundation), then adding `--straddle` as the first
consumer of that foundation. Single-leg mode stays backward-compatible.

---

## 1. Goals

1. **Multi-leg foundation**: Refactor internals so `calculate_scenarios()` works with a list of legs. Single-leg = one-element list. No behavioral change for existing usage.
2. **Straddle mode**: `--straddle` flag infers the opposite leg at same strike/expiry. Per-leg costs provided via `--put-cost` or `--call-cost`.
3. **Combined + per-leg visibility**: Scenario table shows Call Est, Put Est, and Combined columns (Option A from design discussion). User sees what each leg is doing.
4. **Dual breakeven**: Straddle can break even in either direction. Show both: "stock needs to move -7.2% or +7.8%." Always show both roots; flag with >15% disclaimer if either is extreme.
5. **Future extensibility**: The legs model trivially supports strangle, custom multi-leg, and short legs later — no re-architecture needed.

## 2. User Stories

**US-1**: As a trader holding a straddle into earnings, I want to see the combined P/L across both legs accounting for IV crush, so I can decide whether to sell the straddle or hold through.

**US-2**: As a trader comparing straddle cost to expected move, I want to see whether the expected/historical move exceeds my combined breakeven, so I can assess whether the straddle is fairly priced.

**US-3**: As a trader evaluating a straddle, I want to see what each leg is doing individually within the combined scenario table, so I understand which leg carries the position in each scenario.

## 3. Functional Requirements

### 3.1 CLI Input

**FR-1**: New `--straddle` flag (store_true). When set, tool infers the opposite leg at the same symbol/strike/expiry.

**FR-2**: New `--put-cost FLOAT` arg — cost of the put leg when the provided contract is a CALL.

**FR-3**: New `--call-cost FLOAT` arg — cost of the call leg when the provided contract is a PUT.

**FR-4**: Validation:
- `--straddle` with a CALL contract requires `--put-cost`
- `--straddle` with a PUT contract requires `--call-cost`
- `--put-cost` / `--call-cost` without `--straddle` → ignored (or warning)

**FR-5**: Usage examples:
```bash
# Straddle: provide call, tool infers put
python tools/earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --straddle --put-cost 0.50

# Straddle: provide put, tool infers call
python tools/earnings_scenario.py "TOST|25|2026-04-17|PUT" --cost 0.50 --straddle --call-cost 1.04
```

### 3.2 Internal Leg Model (Foundation)

**FR-6**: A "leg" is a dict containing: contract identity (symbol, strike, expiration, option_type), Greeks (delta, gamma, vega, theta), IV, pricing (bid, ask, last_price, underlying_price), trade_date, cost_basis, current_value, and direction (+1 for long, reserved for future short-leg support).

**FR-7**: `calculate_scenarios()` gains optional `straddle=False, put_cost=None, call_cost=None` parameters. The external API for single-leg is unchanged (backward compatible).

**FR-8**: Internally, a new `build_legs()` function encapsulates all data retrieval. For single mode: fetches one contract, returns `[leg]`. For straddle: fetches both contracts, returns `[call_leg, put_leg]` (always call-first order).

**FR-9**: The result dict gains two new keys:
- `position_type`: `'single'` or `'straddle'`
- `legs`: list of leg dicts (one for single, two for straddle)

Existing result dict keys remain populated (using combined values for straddle where appropriate).

### 3.3 Combined Scenario Math

**FR-10**: For each scenario row, compute per-leg estimated values via the existing `estimate_option_value()`, then sum for the combined value. Each row gains a `per_leg` list field (omitted for single-leg mode).

**FR-11**: Combined breakeven uses summed quadratic coefficients across legs:
```
a = sum(0.5 * gamma_i)
b = sum(delta_i)
c = sum(vega_i * dIV_i + theta_i * dt)
```
Both roots of the quadratic are meaningful for straddles. Return as a sorted list.

**FR-12**: For straddle, the result dict's `breakeven_move_pct` is a list (e.g., `[-7.2, 7.8]`) instead of a single float. Formatters check `isinstance(..., list)` to handle both cases. Always show both roots; if either exceeds 15%, the existing extreme-move disclaimer applies.

**FR-13**: Crush matrix uses the same combined math. For straddle, two breakeven columns (BE Down / BE Up). Expected-move P/L uses `abs(expected_move)` since the straddle profits from movement in either direction.

### 3.4 Output Formatting

**FR-14**: Straddle header:
```
TOST 25 Straddle 4/17 | Call: $1.04 | Put: $0.50 | Combined: $1.54
Current: $4.28 ($3.30 call + $0.98 put) | Stock: $27.31 | IV: 51.6%
Data: 2026-02-28 (Option Pipeline) | Earnings: 2026-05-07
Estimated post-earnings IV: ~28% (46% crush)
Breakeven vs sell now: stock needs to move -7.2% ($25.34) or +7.8% ($29.44)
```

**FR-15**: Straddle scenario table adds per-leg columns:
```
Scenario            |  Stock   | Call Est | Put Est | Combined |    P/L |  P/L % | vs Sell Now
----------------------------------------------------------------------------------------------
Down 11.9% (hist)   |  $24.07  |   $0.00 |  $2.90  |   $2.90  | +$1.36 |   +88% |     -$1.38
Flat                |  $27.31  |   $1.14 |  $0.00  |   $1.14  | -$0.40 |   -26% |     -$3.14
Up 11.9% (hist)     |  $30.55  |   $3.84 |  $0.00  |   $3.84  | +$2.30 |  +149% |     -$0.44
```

**FR-16**: SELL NOW footer shows per-leg current values:
```
SELL NOW            |       -- |   $3.30 |  $0.98  |   $4.28  | +$2.74 |  +178% |         --
```

**FR-17**: Straddle crush matrix has two breakeven columns:
```
Crush Sensitivity:
Crush              | BE Down  |   BE Up  | Flat P/L | Exp Move P/L
-------------------------------------------------------------------
Minimal    (20%)   |   -5.8%  |   +6.2%  |   +$0.12 |       +$2.80
Normal     (46%)   |   -7.2%  |   +7.8%  |   -$0.40 |       +$1.36  <-- default
Severe     (70%)   |   -9.4%  |  +10.1%  |   -$0.88 |       +$0.22
```

**FR-18**: Guide section gains a straddle paragraph explaining dual breakevens, combined P/L, and the exp-move comparison.

### 3.5 Edge Cases

**FR-19**: If one leg is not found in DB, show a clear error identifying which leg: "Put leg TOST|25|2026-04-17|PUT not found in database." Then offer the fallback live prompt.

**FR-20**: Different IVs per leg are expected (put-call parity doesn't mandate equal IV). Each leg uses its own IV for crush calculation. Header shows the call leg's IV (or average).

**FR-21**: `--qty` applies to the combined position (both legs x quantity x 100).

**FR-22**: `--crush` override applies to both legs equally.

## 4. Non-Goals (Out of Scope)

- **Strangle mode** — different call/put strikes. Future extension of the same architecture.
- **Custom multi-leg** (`--legs` syntax) — arbitrary N-leg positions. Future.
- **Short legs / spreads** — `direction=-1` is in the data model but not exposed. Future.
- **Position persistence** — still no saved positions, still CLI-only.
- **Automatic straddle pricing** — no fetching both legs' costs from the market.

## 5. Design Considerations

### Output Example (Full Straddle)

```
TOST 25 Straddle 4/17 | Call: $1.04 | Put: $0.50 | Combined: $1.54
Current: $4.28 ($3.30 call + $0.98 put) | Stock: $27.31 | IV: 51.6%
Data: 2026-02-27 (Option Pipeline) | Earnings: 2026-05-07
Estimated post-earnings IV: ~28% (46% crush)
Breakeven vs sell now: stock needs to move -7.2% ($25.34) or +7.8% ($29.44)
==============================================================================
Scenario            |  Stock   | Call Est | Put Est | Combined |    P/L |  P/L % | vs Sell Now
----------------------------------------------------------------------------------------------
Down 11.9% (hist)   |  $24.07  |   $0.00 |  $2.90  |   $2.90  | +$1.36 |   +88% |     -$1.38
Down 7.2%           |  $25.34  |   $0.58 |  $3.70  |   $4.28  | +$2.74 |  +178% |     +$0.00  <-- BREAKEVEN
Down 5%             |  $25.94  |   $0.21 |  $0.85  |   $1.06  | -$0.48 |   -31% |     -$3.22
Flat                |  $27.31  |   $1.14 |  $0.00  |   $1.14  | -$0.40 |   -26% |     -$3.14
Up 5%               |  $28.68  |   $2.20 |  $0.00  |   $2.20  | +$0.66 |   +43% |     -$2.08
Up 7.8%             |  $29.44  |   $3.05 |  $0.00  |   $4.28  | +$2.74 |  +178% |     +$0.00  <-- BREAKEVEN
Up 11.9% (hist)     |  $30.55  |   $3.84 |  $0.00  |   $3.84  | +$2.30 |  +149% |     -$0.44
----------------------------------------------------------------------------------------------
SELL NOW            |       -- |   $3.30 |   $0.98 |   $4.28  | +$2.74 |  +178% |         --

Crush Sensitivity:
Crush              | BE Down  |   BE Up  | Flat P/L | Exp Move P/L
-------------------------------------------------------------------
Minimal    (20%)   |   -5.8%  |   +6.2%  |   +$0.12 |       +$2.80
Mild       (32%)   |   -6.4%  |   +6.9%  |   -$0.14 |       +$2.10
Normal     (46%)   |   -7.2%  |   +7.8%  |   -$0.40 |       +$1.36  <-- default
High       (57%)   |   -8.0%  |   +8.6%  |   -$0.62 |       +$0.85
Severe     (70%)   |   -9.4%  |  +10.1%  |   -$0.88 |       +$0.22
```

### Console Output Pattern

Same as PRD 0011 — direct `print()` to stdout, not through `log_utils.py`. Standalone CLI tool.

## 6. Technical Considerations

### Dependencies
No new dependencies. Same stdlib math.

### Key Functions (New/Modified)

| Function | Status | Purpose |
|----------|--------|---------|
| `infer_counterpart(parsed)` | New | Flip CALL<->PUT on a parsed contract dict |
| `build_legs(contract, cost, straddle, put_cost, call_cost, live)` | New | Encapsulate all data retrieval, return legs list |
| `estimate_position_value(legs, stock_price, move_pct, crush_pct, dte)` | New | Per-leg estimates + combined sum |
| `calculate_combined_breakeven(legs, crush_pct, dte, stock_price)` | New | Multi-leg quadratic, returns all valid roots |
| `calculate_scenarios()` | Modified | Add straddle/cost params, call build_legs, use combined math |
| `build_scenario_rows()` | Modified | Accept legs list, produce per_leg detail per row |
| `build_crush_matrix()` | Modified | Accept legs list, dual breakeven columns |
| `format_header()` | Modified | Branch on position_type for straddle header |
| `format_scenario_rows()` | Modified | Per-leg columns for straddle |
| `format_crush_matrix()` | Modified | Dual breakeven columns for straddle |
| `format_guide()` | Modified | Add straddle paragraph |
| `main()` | Modified | Add --straddle, --put-cost, --call-cost args |

### Unchanged Functions
- `parse_contract_hash()` — called once per leg, no changes
- `get_contract_from_db()` — per-leg, no changes
- `get_earnings_data()` — per-symbol, no changes
- `get_contract_live()` — per-leg, no changes
- `estimate_option_value()` — single-leg math, called by new `estimate_position_value()`
- `calculate_breakeven()` — still used for single-leg; combined function is new

### Critical Math Note

Tradier vega is per percentage point (per 0.01 change in sigma). The formula for IV change in percentage points is: `dIV_pp = -(iv * crush_pct)` where `iv` is decimal (e.g. 0.516) and `crush_pct` is percentage (e.g. 46). This convention applies per-leg.

### Critical Gate

After Phase 1 (internal refactor), single-leg output must be **byte-for-byte identical** to current output. This validates the refactor before any straddle logic is added.

## 7. Success Metrics

1. **Single-leg regression**: Output is identical before and after refactor.
2. **Straddle math check**: For an ATM straddle, combined delta ~ 0 and breakevens are approximately symmetric. Verify by hand.
3. **Decision utility**: The dual-breakeven vs expected-move comparison answers "is this straddle fairly priced?"
4. **Speed**: Straddle mode completes in <3 seconds (DB mode).

## 8. Open Questions

1. **Strangle timing**: When to add `--strangle` support? The architecture supports it from day one, but it needs its own CLI design (two contract hashes or `--call-strike`/`--put-strike` overrides).
2. **Dynamic crush per leg**: Currently both legs share the same crush %. In reality, the call and put might experience slightly different crush. Not enough data to model this yet.
