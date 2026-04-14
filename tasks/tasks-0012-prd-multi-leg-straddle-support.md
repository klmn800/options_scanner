# Tasks: PRD 0012 — Multi-Leg Position Support (Straddle)

**PRD**: `tasks/0012-prd-multi-leg-straddle-support.md`

## Relevant Files

- `tools/earnings_scenario.py` — Existing file (~950 lines). All implementation changes here. Add 4 new functions, modify ~8 existing functions.
- `core/tradier_api.py` — Existing file. No changes needed (`get_contract_greeks()` works per-leg).
- `docs/earnings-scenario-calculator.md` — Existing file. Add straddle usage docs.
- `CLAUDE.md` — Existing file. Add straddle CLI examples to tool section.

### Notes

- **Critical**: Tradier vega is per percentage point (per 0.01 change in sigma). `dIV_pp = -(iv * crush_pct)` where iv is decimal and crush_pct is percentage. Applied per-leg.
- **Regression gate**: After Phase 1 refactor, single-leg output must be byte-for-byte identical. Capture baseline output before starting.
- **Leg ordering**: For straddle, legs list is always [call, put] regardless of which leg the user provides.
- **Direction field**: Each leg has `direction=+1` (long). Reserved for future short-leg support but not exposed in this PRD.
- **Combined breakeven**: Both quadratic roots are meaningful for straddles. Sum per-leg coefficients: a=sum(0.5*gamma_i), b=sum(delta_i), c=sum(vega_i*dIV_i + theta_i*dt).

## Tasks

- [x] 1.0 Internal Leg Model & Data Layer (Foundation)
  - [x] 1.1 Capture baseline: run `python tools/earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --no-guide` and save output to a temp file for regression comparison after refactor.
  - [x] 1.2 Implement `infer_counterpart(parsed)` function: takes a parsed contract dict (from `parse_contract_hash()`), returns a new dict with `option_type` flipped (CALL<->PUT), all other fields identical. ~10 lines.
  - [x] 1.3 Implement `build_legs()` function that encapsulates all data retrieval logic currently inline in `calculate_scenarios()`. For single mode: fetch one contract, compute mid-price, build one leg dict with `direction=+1`, `cost_basis`, `current_value`. For straddle mode: call `infer_counterpart()`, fetch both contracts, assign costs correctly (call_cost/put_cost), build two leg dicts. Handles: fallback prompt for missing contracts, stale data warning, zero Greeks warning. Returns `(legs_list, position_type, warnings_list)`. ~80 lines.
  - [x] 1.4 Refactor `calculate_scenarios()` to call `build_legs()` instead of inline data retrieval. Add `straddle=False, put_cost=None, call_cost=None` parameters. For single-leg mode, behavior must be identical. Add `position_type` and `legs` to result dict.
  - [x] 1.5 **Regression gate**: run the same command from 1.1 and diff output against baseline. Must be byte-for-byte identical (or functionally identical — whitespace differences OK if unavoidable, but no value changes).

- [x] 2.0 Combined Math Functions
  - [x] 2.1 Implement `estimate_position_value(legs, stock_price, move_pct, crush_pct, days_to_earnings)` that loops over legs, calls `estimate_option_value()` per leg (using that leg's own Greeks/IV), returns `(combined_value, per_leg_list)` where per_leg_list is `[{'option_type': 'CALL', 'est_value': X}, ...]`. ~20 lines.
  - [x] 2.2 Implement `calculate_combined_breakeven(legs, crush_pct, days_to_earnings, stock_price)` that sums per-leg quadratic coefficients (a, b, c), solves the combined quadratic, returns ALL valid roots within +/-30% as a sorted list. For straddle both roots are meaningful. Returns empty list if no solutions. ~35 lines.
  - [x] 2.3 Modify `build_scenario_rows()` to accept `legs` list and `position_type` instead of single `contract_data`. Use `estimate_position_value()` for each row. Add `per_leg` field to each row dict when `position_type != 'single'`. Handle multiple breakeven points from a list of breakeven_pcts. ~40 lines changed.
  - [x] 2.4 Modify `build_crush_matrix()` to accept `legs` list instead of single `contract_data`. Use `calculate_combined_breakeven()` for per-tier breakevens (returns list of roots per tier). Use `estimate_position_value()` for P/L. For straddle, expected-move P/L uses `abs(expected_move)` since straddle profits from movement in either direction. Each tier dict gains `breakeven_pcts` (list) instead of single `breakeven_pct`. ~30 lines changed.
  - [x] 2.5 Wire Phase 2 functions into `calculate_scenarios()`. Result dict: `breakeven_move_pct` becomes a list for straddle (single float for single-leg, backward compatible). Combined Greeks (sum of per-leg) stored in result for reference. `cost_basis` and `current_value` use combined sums for straddle. Populate `position_type` and `legs` keys.

- [x] 3.0 Output Formatting
  - [x] 3.1 Modify `format_header()`: branch on `result['position_type']`. For straddle: Line 1 shows "SYMBOL STRIKE Straddle M/DD | Call: $X | Put: $Y | Combined: $Z". Line 2 shows per-leg current values. Breakeven line shows "move -X% ($P) or +Y% ($Q)" for dual roots, or single root if only one. ~40 lines added.
  - [x] 3.2 Modify `format_scenario_rows()`: for straddle, add Call Est and Put Est columns before Combined column. Read from `row['per_leg']`. SELL NOW footer shows per-leg current values. Handle `--qty` Total P/L column for straddle. ~35 lines added.
  - [x] 3.3 Modify `format_crush_matrix()`: for straddle, show two breakeven columns (BE Down / BE Up) instead of one. Expected-move column label is non-directional ("Exp Move P/L"). Arrow marker logic unchanged. ~30 lines added.
  - [x] 3.4 Add straddle paragraph to `format_guide()` explaining: dual breakevens, combined P/L, per-leg columns, and the exp-move comparison for straddles. ~10 lines.

- [x] 4.0 CLI & End-to-End Validation
  - [x] 4.1 Add `--straddle` (store_true), `--put-cost` (float), `--call-cost` (float) arguments to argparse in `main()`. Validation: `--straddle` with CALL requires `--put-cost`, with PUT requires `--call-cost`. Clear error messages. Update epilog with straddle examples. ~25 lines.
  - [x] 4.2 Wire CLI args through to `calculate_scenarios()`: pass `straddle=args.straddle, put_cost=args.put_cost, call_cost=args.call_cost`. ~5 lines in `main()`.
  - [x] 4.3 End-to-end manual testing: (a) single-leg regression re-check, (b) straddle with CALL primary, (c) straddle with PUT primary, (d) straddle + --crush override, (e) straddle + --qty, (f) straddle with one leg missing from DB, (g) straddle on symbol with no earnings data, (h) hand-verify combined breakeven math for one straddle case.
  - [x] 4.4 Update `docs/earnings-scenario-calculator.md` with straddle usage examples, output interpretation, and updated limitations. Update `CLAUDE.md` tool section with straddle CLI examples.
