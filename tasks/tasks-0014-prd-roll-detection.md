# Tasks: PRD 0014 — Roll Detection in Flow Alerts

**PRD:** `tasks/0014-prd-roll-detection.md`
**Evidence:** `strategic_advisor/reviews/007_roll_detection.md`

## Relevant Files

- `strategies/flow_monitor/fm_config.py` — Add `roll_detection` config block with tunable thresholds
- `strategies/flow_monitor/fm_storage.py` — Schema migration (2 new columns on `flow_alerts`), update INSERT statement
- `strategies/flow_monitor/fm_analyzer.py` — Expose scan contracts list via class attribute after `analyze()`
- `strategies/flow_monitor/fm_alerts.py` — Core roll detection algorithm, alert record enrichment, console tag formatting
- `strategies/flow_monitor/fm_main.py` — Pass scan contracts from analyzer to alerts pipeline (4 call sites)
- `tools/decimal_formatter.py` — Add `roll_counterpart_details` to string-field allowlist so `clean_database_row()` doesn't nullify it

### Notes

- No formal test framework — validation uses known roll examples from evidence doc (VST, NOK, LYB, XYZ)
- Roll detection must use in-memory scan data only — **no queries against `flow_options_scans`** (23M+ rows, missing index)
- Console output follows patterns in `docs/CONSOLE_DEVELOPER_GUIDE.md`
- The analyzer and alerts pipeline are currently decoupled through the database. `analyze()` writes scores to `flow_options_scans`, then `process_alerts()` re-queries for candidates. Roll detection needs the FULL contract set (not just alert candidates), so we thread the data through.

### Implementation Guidance (from code review)

1. **Task 2.1 — Data format:** Check what `_get_contracts_with_baselines()` actually returns. It may be a DataFrame, not a list of dicts. The roll detection function in 3.1 must handle whatever format it gets (or normalize at the storage point in 2.1).
2. **Task 2.3 — Line numbers are approximate.** Grep for `process_alerts(` call sites in `fm_main.py` rather than relying on specific line numbers — they will have shifted.
3. **Bidirectional tagging is natural.** If both legs alert, each independently finds the other as counterpart when `_detect_roll()` runs. Role assignment (higher V/OI = "opening") is deterministic regardless of processing order. No special batching needed.
4. **Task 5.2 — Expiration date formatting:** Source data uses `YYYY-MM-DD` format (e.g., `2026-04-17`). The console tag needs `MM/DD` (e.g., `04/17`). Parse and reformat consistently — don't assume input format by slicing strings.

## Tasks

- [x] 1.0 Configuration & Schema Setup
  - [x] 1.1 Add `get_roll_detection_config()` method to `fm_config.py`. Follow the `get_dip_thresholds()` pattern (lines 152-185): define defaults dict, overlay from `self.flow_monitor_config.get('roll_detection', {})`. Keys: `enabled` (default True), `vol_match_threshold` (default 0.85), `voi_closing_threshold` (default 1.5), `expiration_window_days` (default 30).
  - [x] 1.2 Add schema migration in `fm_storage.py:_ensure_schema()` (lines 56-71). Add two ALTER TABLE statements to the `migrations` list: `ALTER TABLE flow_alerts ADD COLUMN roll_detected BOOLEAN DEFAULT 0` and `ALTER TABLE flow_alerts ADD COLUMN roll_counterpart_details TEXT`. Follow the existing try/except pattern that silently ignores "duplicate column" errors.
  - [x] 1.3 Add `roll_counterpart_details` to the string-field allowlist in `tools/decimal_formatter.py` so `clean_database_row()` doesn't nullify it. Find where other TEXT fields (like `alert_reason`, `moneyness`, `evaluation_status`) are preserved and add `roll_counterpart_details` to that list.
  - [x] 1.4 Update the `save_alert()` INSERT in `fm_storage.py` (lines 356-370) to include `roll_detected` and `roll_counterpart_details` in the column list and VALUES placeholders. Map from alert_record dict keys to columns.

- [x] 2.0 Thread Scan Data Through Pipeline
  - [x] 2.1 In `fm_analyzer.py:analyze()`, after `contracts_data = self._get_contracts_with_baselines(scan_timestamp)` (line 166), store the raw contracts list as a class attribute: `self.last_scan_contracts = contracts_data`. This makes the full scan data (all contracts, not just alert candidates) accessible after `analyze()` returns.
  - [ ] 2.2 In `fm_alerts.py:process_alerts()`, add an optional `scan_contracts=None` parameter. Store it as `self._scan_contracts = scan_contracts` for use by the roll detection function. The parameter is a list of dicts with keys: `symbol`, `strike`, `expiration_date`, `option_type`, `volume`, `open_interest`, `contract_hash`.
  - [ ] 2.3 In `fm_main.py`, update all call sites where `alerts.process_alerts(scan_timestamp)` is called to pass the scan data. There are 4 call sites (lines 683, 865, 1450, 2232). For each, pass `scan_contracts=analyzer.last_scan_contracts` (or `scan_contracts=getattr(analyzer, 'last_scan_contracts', None)` for safety). Example: `alerts.process_alerts(scan_timestamp, test_mode=test_mode, scan_contracts=analyzer.last_scan_contracts)`.

- [ ] 3.0 Core Roll Detection Algorithm
  - [ ] 3.1 Create a new method `_detect_roll()` in `fm_alerts.py`. Signature: `def _detect_roll(self, alert, scan_contracts, config)`. Takes one alert candidate dict, the full scan contracts list, and the roll detection config dict. Returns: `(roll_detected: bool, counterpart_details: dict or None)`.
  - [ ] 3.2 Implement the counterpart search inside `_detect_roll()`. Filter `scan_contracts` for: (a) same `symbol`, (b) same `option_type`, (c) different `strike`, (d) expiration within ±`config['expiration_window_days']` calendar days (use `datetime.strptime` on `expiration_date` strings, compute `abs(delta_days)`), (e) volume within 50-200% of alert's volume (pre-filter: `min(V, V') / max(V, V') >= 0.50`).
  - [ ] 3.3 Implement the scoring and classification. For each candidate counterpart from 3.2: compute `vol_match_ratio = min(V, V') / max(V, V')`. Compute `voi_alert = alert_volume / max(alert_oi, 1)` and `voi_counterpart = counterpart_volume / max(counterpart_oi, 1)`. Flag as roll if: `vol_match_ratio >= config['vol_match_threshold']` AND `min(voi_alert, voi_counterpart) < config['voi_closing_threshold']`.
  - [ ] 3.4 Implement best-match selection. If multiple counterparts qualify, select the one with the highest `vol_match_ratio`. If tied, select the one with the lowest V/OI (strongest closing signal).
  - [ ] 3.5 Build the return dict. When a roll is detected, return: `{'counterpart_strike': float, 'counterpart_expiration': str, 'vol_match_ratio': float (rounded to 2 decimal places), 'alert_voi': float (rounded to 2), 'counterpart_voi': float (rounded to 2), 'role': 'opening' or 'closing'}`. Role assignment: the leg with higher V/OI is `"opening"`, the leg with lower V/OI is `"closing"`. When no roll detected, return `(False, None)`.

- [ ] 4.0 Alert Record & Storage Integration
  - [ ] 4.1 Call `_detect_roll()` during alert processing. In `fm_alerts.py:process_alerts()`, after filters are applied (after line 131) but before notifications (line 155): load roll config via `self.config.get_roll_detection_config()`, then loop through `passed_candidates` and call `_detect_roll(alert, self._scan_contracts, roll_config)` for each. Store results on the alert dict: `alert['roll_detected'] = roll_detected`, `alert['roll_counterpart_details'] = counterpart_details`.
  - [ ] 4.2 Update `alert_reason` in `_save_alerts()`. Where `enhanced_reason` is built (around lines 728-742), if `alert.get('roll_detected')`, prepend the roll tag to the reason string. Format: `v2|ROLL?$170|score: 5.3 (prem=...)` — insert `ROLL?$K'` after the `v2|` prefix and before `score:`. If cross-expiration, use `ROLL?$K' MM/DD`.
  - [ ] 4.3 Add `roll_detected` and `roll_counterpart_details` to the `alert_record` dict in `_save_alerts()` (around lines 745-810). Set `roll_detected` to `1` if `alert.get('roll_detected')` else `0`. Set `roll_counterpart_details` to `json.dumps(alert.get('roll_counterpart_details'))` if present, else `None`. Import `json` at top of file.
  - [ ] 4.4 Guard for missing scan data. If `self._scan_contracts` is None (e.g., called from a code path that doesn't pass scan data), skip roll detection silently — log at debug level and leave `roll_detected = 0` on all alerts.

- [ ] 5.0 Console Output Tagging
  - [ ] 5.1 Modify `_format_console_alert()` in `fm_alerts.py` (lines 381-447). After the `market_cap_display` tag `[MKT]` and before the contract details (`$strike ...`), insert the roll tag if present. Check `alert.get('roll_detected')`: if True, get details from `alert.get('roll_counterpart_details', {})` and build tag string.
  - [ ] 5.2 Format the tag based on role and expiration. Opening leg: `[ROLL? from $K']` (same exp) or `[ROLL? from $K' MM/DD]` (cross-exp). Closing leg: `[ROLL? closing -> $K']` (same exp) or `[ROLL? closing -> $K' MM/DD]` (cross-exp). Determine "same exp" by comparing `alert['expiration_date']` with `counterpart_details['counterpart_expiration']`.
  - [ ] 5.3 Position the tag in the alert line. Currently the format string at line 425 starts with `"{} [{}] ${} {}s..."`. Insert the roll tag after `[{}]` (market_cap_display). Modify to: `"{} [{}]{} ${} {}s..."` where the new `{}` is either `" [ROLL? from $170]"` or `""` (empty string if no roll).

- [ ] 6.0 Validation & Smoke Test
  - [ ] 6.1 Verify the schema migration runs cleanly. Start the FM pipeline (or just instantiate `FlowMonitorStorage`) and confirm both new columns exist on `flow_alerts` without errors. Check via `python tools/direct_db_query.py --schema flow_alerts --db data/datalake.db`.
  - [ ] 6.2 Verify `clean_database_row()` preserves `roll_counterpart_details` as a string. Create a test dict with a JSON string value for `roll_counterpart_details`, run it through `clean_database_row()`, confirm the string is not nullified.
  - [ ] 6.3 Dry-run the algorithm against known roll examples from the evidence doc. Write a small validation script (or inline test) that constructs mock scan data matching the VST 4/9 example (V=2450 at $170, V=2500 at $175, OI divergent) and confirms `_detect_roll()` returns the expected result (roll detected, correct counterpart strike, correct role assignment).
  - [ ] 6.4 Dry-run the algorithm against known NON-roll examples. Construct mock data matching the NVDA 4/2 example (both legs BUILDING, V/OI both > 1.5) and confirm `_detect_roll()` returns `(False, None)`.
  - [ ] 6.5 Run a full FM cycle in test mode (`python strategies/flow_monitor/fm_main.py --pre-market --no-interaction`) or wait for next trading day. Verify: (a) no errors in logs, (b) `roll_detected` column populated (mostly 0s is expected), (c) any `roll_detected = 1` rows have valid JSON in `roll_counterpart_details`, (d) console output shows `[ROLL?]` tags where detected.
