# Tasks: PRD 0011 — Earnings Scenario Calculator

**PRD**: `tasks/0011-prd-earnings-scenario-calculator.md`
**Proposal**: `docs/earnings-scenario-calculator-proposal.md`

## Relevant Files

- `tools/earnings_scenario.py` — New file (created). Core calculation engine, output formatter, and CLI entry point. ~550 lines.
- `core/tradier_api.py` — Modified. Added `get_contract_greeks()` method to `TradierDataClient` class for live mode (~50 lines added).
- `data/datalake_query.db` — Existing database. Source for option_contracts, earnings_upcoming queries (read-only).
- `tools/technical_levels.py` — Reference file. Existing CLI tool pattern (argparse, sqlite3, formatting) followed.
- `tools/volume_profile_calculator.py` — Reference file. Another CLI tool pattern example.
- `strategies/earnings_intel/ei_post_earnings_calc.py` — Reference file. Contains the 5-tier IV crush severity scale.

### Notes

- No formal test framework in this project. Validation is manual (run the tool, check output).
- Database queries use direct `sqlite3.connect()`, not an ORM or wrapper.
- `option_contracts` table has a `contract_hash` primary key in `SYMBOL|STRIKE|EXPIRATION|TYPE` format — matches the CLI input format exactly.
- Tradier API returns `"greeks": null` (not missing) for some contracts. Always use `(option.get('greeks') or {}).get()` pattern.
- **Critical**: Tradier vega is per percentage point (per 0.01 change in sigma), NOT per unit of sigma. ΔIV must be in pp before multiplying by vega. Formula: `dIV_pp = -(iv * crush_pct)` where iv is decimal and crush_pct is percentage.

## Tasks

- [x] 1.0 CLI Infrastructure & Contract Hash Parsing
  - [x] 1.1 Create `tools/earnings_scenario.py` with file scaffolding: imports (sqlite3, argparse, sys, os, math), module docstring describing the tool's purpose, and `if __name__ == '__main__'` block.
  - [x] 1.2 Implement `parse_contract_hash(contract_str)` function that splits a `SYMBOL|STRIKE|EXPIRY|TYPE` string into a dict with keys `symbol` (str), `strike` (float), `expiration` (str, YYYY-MM-DD), `option_type` (str, uppercased). Raise `ValueError` with descriptive message if format is wrong (not 4 parts, strike not numeric, type not CALL/PUT).
  - [x] 1.3 Set up argparse with: positional `contract` argument (the hash string), required `--cost` (float), optional `--qty` (int, default 1), optional `--crush` (float, default None — None means use 46% default), optional `--live` (store_true flag). Include usage examples in epilog.
  - [x] 1.4 Wire the `__main__` block to parse args, call `parse_contract_hash()`, and call `calculate_scenarios()` → `format_scenario_table()` → `print()`. Handle KeyboardInterrupt and top-level exceptions gracefully.

- [x] 2.0 Data Retrieval Layer
  - [x] 2.1 Implement `get_contract_from_db(contract_hash, db_path='data/datalake_query.db')` that queries `option_contracts` for the most recent row matching the contract hash. Return a dict with keys: `delta`, `gamma`, `vega`, `theta`, `iv`, `bid`, `ask`, `last_price`, `underlying_price`, `trade_date`. Return `None` if not found. Use `ORDER BY trade_date DESC LIMIT 1`.
  - [x] 2.2 Implement `get_earnings_data(symbol, db_path='data/datalake_query.db')` that queries `earnings_upcoming` for the symbol. Return a dict with keys: `earnings_date`, `earnings_time`, `straddle_expected_move_pct`, `historical_avg_move_pct`. Return `None` if symbol not in table or no upcoming earnings.
  - [x] 2.3 Add `get_contract_greeks(symbol, strike, expiration, option_type)` method to `TradierDataClient` class in `core/tradier_api.py`. Fetch the chain via existing `get_option_chain(symbol, expiration)`, iterate results to find matching strike + option_type, extract Greeks using safe `(greeks or {}).get()` pattern. Return dict with `delta`, `gamma`, `vega`, `theta`, `iv` (from smv_vol), `bid`, `ask`, `last_price`, `underlying_price` (from `underlying` field), or `None` if contract not found.
  - [x] 2.4 Implement `get_contract_live(symbol, strike, expiration, option_type)` in `earnings_scenario.py` that instantiates `TradierDataClient` from config, calls `get_contract_greeks()`, and returns the result in the same dict format as `get_contract_from_db()` (with `trade_date` set to current date/time string).
  - [x] 2.5 Implement the fallback prompt logic: if `get_contract_from_db()` returns `None` and `--live` was not specified, print `"Contract not found in database. Fetch live from Tradier? (y/n): "` and read input. If 'y', call `get_contract_live()`. If 'n', exit with error message. (Wired into calculate_scenarios in task 3.5)

- [x] 3.0 Scenario Calculation Engine
  - [x] 3.1 Implement `estimate_option_value()` — second-order Greek approximation with corrected vega convention (per percentage point, not per decimal). Floors at $0.00.
  - [x] 3.2 Implement `calculate_breakeven()` — quadratic solver for breakeven stock move. Handles degenerate (gamma≈0) case, caps at ±30%.
  - [x] 3.3 Implement `build_scenario_rows()` — generates scenario list with ±historical, ±expected, ±5%, flat, breakeven. Consolidates within 1%, deduplicates within 0.3%, sorts by move_pct.
  - [x] 3.4 Implement `build_crush_matrix()` — 5-tier sensitivity (20/32/46/57/70%), returns breakeven + flat P/L + expected-move P/L per tier.
  - [x] 3.5 Implement `calculate_scenarios()` — full orchestrator with DB/live fallback prompt (FR-6), stale data warning (FR-7), zero Greeks warning, >15% extreme move warning.

- [x] 4.0 Output Formatting
  - [x] 4.1 Implement `format_header()` — contract desc with clean strike formatting, cost/current/IV, data source, earnings date, post-earnings IV, breakeven summary.
  - [x] 4.2 Implement `format_scenario_rows()` — aligned scenario table with SELL NOW footer, breakeven arrow, optional Total P/L column for --qty.
  - [x] 4.3 Implement `format_crush_matrix()` — 5-tier sensitivity table with closest-tier arrow marker, direction-aware column headers (Up/Down for calls/puts).
  - [x] 4.4 Implement `format_footnotes()` — stale data, >15% move, and other warnings.
  - [x] 4.5 Implement `format_scenario_table()` — top-level concatenation of all sections.

- [x] 5.0 End-to-End Wiring & Edge Cases
  - [x] 5.1 Handle missing earnings data gracefully: tested with IWM (ETF, no earnings). Fixed intervals ±3/5/10%, "Exp Move P/L" shows N/A, warning footnote displayed, earnings line omitted from header.
  - [x] 5.2 Handle zero/null Greeks: tested with AA 50P (all Greeks zero). Breakeven shows "not achievable", warning displayed, output still produced.
  - [x] 5.3 Handle --crush override: tested with --crush 60. Main table uses 60%, matrix uses fixed 5 tiers, closest tier (High 57%) gets arrow marker.
  - [x] 5.4 Live mode wiring validated (imports, config read, TradierDataClient instantiation). Full live test requires market hours.
  - [x] 5.5 Manual validation: hand-verified flat scenario (3.30 → 1.14, vega=-0.80, theta=-1.36) and breakeven (dS=2.65, +9.7%, $29.96). Both match tool output exactly.
