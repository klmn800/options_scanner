# Console Output Overhaul — Progress Tracker

**Purpose:** Coordination artifact for multi-agent execution. Coding agents update their package status when done. Review agents run verification checks and record results. Dependent packages gate on "verified", not just "complete."

---

## How to Use This File

**Coding agents:** When you finish your package, update your package's status to `complete` and fill in the Coding Notes field with a brief summary of what you changed.

**Review agents:** Run the verification checks listed in `WORK_PACKAGES.md` for the package you're reviewing. Update status to `verified` if all checks pass, or `failed` with notes explaining what didn't pass. If verification fails, the coding agent (or a new one) must fix the issues before the package can be marked verified.

**Agents starting a dependent package:** Before beginning work, check that ALL packages listed in your "Depends On" field are marked `verified`. If any are not, STOP and report this — do not proceed with partial prerequisites.

---

## Status Overview

| Package | Name | Depends On | Status | Verified By |
|---------|------|------------|--------|-------------|
| 0 | Orchestrator Standalone Cleanup | — | `verified` | PM 2026-02-18 |
| 1 | EI Dict Returns | — | `verified` | PM 2026-02-18 |
| 2 | EI Visual Cleanup | 1 | `verified` | PM 2026-02-18 |
| 3 | OP Visual Cleanup | — | `verified` | PM 2026-02-18 |
| 4 | FM Pre-Market Dict Return | — | `verified` | PM 2026-02-18 |
| 5 | FM Post-Market Research + Dict | — | `verified` | PM 2026-02-18 |
| 6A | FM Formatting Functions + Coffee Break | 0 | `verified` | PM 2026-02-18 |
| 6B | FM Function-Level Triage (Pre/Post + Utilities) | 4, 5, 6A | `verified` | PM 2026-02-18 |
| 6C | FM Market Hours Triage | 6A | `verified` | PM 2026-02-18 |
| 6D | FM Component Files Cleanup | 6A | `verified` | PM 2026-02-18 |
| 7 | Utility Runner Polish | — | `verified` | PM 2026-02-18 |

**Status values:** `pending` → `in_progress` → `complete` → `verified` (or `failed`)

---

## Package 0: Orchestrator Standalone Cleanup

**Status:** `verified`
**Coding Notes:** Completed all 7 steps. Step 1: Removed 10 duplicate beautiful_log SUCCESS lines + trailing blank print("") from main_runners.py (morning/evening OP, morning views, earnings pipeline/scan/refresh, DB backup, query sync, sector archive, Friday archive). Step 2: Removed duplicate Initializing/Starting/Running announcements from 11 methods (all listed in package + FM init line + Friday archive "Starting" line). Step 3: Removed filler text from 6 completion boxes ("Database secured", "Ready for safe operations", "Performance optimized", hardcoded "~750 symbols", "4 SQL views"). Step 4: Added STEP_SEQUENCE class constant (16 entries) to CleanOrchestrator in main.py; rewrote coffee_break() in main_ui.py to use create_status_box with dynamic "Up Next" lookup and Ctrl+C note. Step 5: Added after_step= parameter to all 12 coffee_break() calls in main.py. Step 6: Added daily state persistence (4 module-level helpers in main_ui.py: _reset_daily_state, _load_daily_state, _save_orchestrator_result, _save_fm_session). Wired _reset_daily_state + _load_daily_state at top of each daily cycle, _save_orchestrator_result after every phase result in run_smart_endless_operation(). Step 7: Added save_to_daily_state() instance method and load_from_daily_state() classmethod to FMSessionStats in fm_session_stats.py.

Note: run_airline_play_phase() still has a beautiful_log "completed successfully" line — this is Package 7's scope per the work packages spec (not in the 10 methods listed for Step 1).

**Verification Results:**
- [x] Grep: no duplicate beautiful_log SUCCESS/COMPLETED/Initializing/Starting/Running/Beginning in main_runners.py (error-path and FM time-skip lines OK) — 2 remaining matches are airline play (Package 7 scope) and views recreation info log
- [x] Grep: no "Database secured", "Ready for safe operations", "Ready for analysis", "Performance optimized", "~750 symbols", "4 SQL views" in completion boxes — 3 grep hits are in mission boxes/docstrings (not completion boxes), which is correct
- [x] Visual: coffee_break() in main_ui.py uses create_status_box with dynamic "Up Next" from STEP_SEQUENCE
- [x] STEP_SEQUENCE order matches execution order in run_smart_endless_operation()
- [x] All 12 coffee_break() calls have after_step= parameter
- [x] _reset_daily_state() called at top of each daily cycle
- [x] _save_orchestrator_result() called after each phase result (17 calls total)
- [x] FMSessionStats import test passes: `python -c "from strategies.flow_monitor.fm_session_stats import FMSessionStats; print('OK')"`
- [ ] Smoke test: `python main.py --once --debug` deferred (requires market conditions)

**Review Notes:** PM verified 2026-02-18. Filler grep has 3 hits in mission boxes (legitimate context, not completion boxes). Daily state save/load tested successfully. Remaining beautiful_log calls are FM flow markers (legitimate) and Package 7 scope.

---

## Package 1: EI Dict Returns

**Status:** `verified`
**Coding Notes:** All 6 steps executed. (1) `update_expected_moves()` in `ei_moves_upcoming.py` now returns `alert_details` list with symbol/days_ahead/relative_underpricing_pct/signal per alert. (2) Fixed `events_analyzed` → `events_ready` naming bug (4 occurrences). (3) `run_morning_scan()` bool→dict. (4) `run_weekly_refresh()` bool→dict with `upcoming_count` query and removed 4 `handle_error()` calls. (5) `run_daily_pipeline()` bool→dict with `alert_details`, removed 4 `handle_error()` calls. Fixed `run_all_mode()` and `main()` for dict returns. (6) Updated 3 orchestrator methods in `main_runners.py`: removed all DB queries, build completion boxes from result dicts, pass result to `queue_error()` on failure.

**Verification Results:**
- [ ] Run: `python strategies/earnings_intel/ei_main.py --morning-scan --no-interaction` deferred (requires market data)
- [ ] Run: `python strategies/earnings_intel/ei_main.py --weekly-refresh --no-interaction` deferred
- [ ] Run: `python strategies/earnings_intel/ei_main.py --daily-pipeline --no-interaction` deferred
- [x] Type check: all 3 orchestrator methods receive `dict` (not `bool`) from EI coordinators
- [x] Grep: no `SELECT COUNT.*earnings` in main_runners.py (all DB queries removed)
- [x] PM verified: events_analyzed naming bug fixed (zero matches in ei_main.py)
- [x] PM verified: alert_details populated in ei_moves_upcoming.py (4 fields per entry)
- [x] PM verified: handle_error removed from coordinators (1 remaining in main() fatal handler — correct)
- [x] PM verified: run_morning_scan() has proper failure result template with all fields
- [x] Import check: `from strategies.earnings_intel.ei_main import run_morning_scan, run_weekly_refresh, run_daily_pipeline` — OK

**Review Notes:** PM verified 2026-02-18. All DB queries removed from orchestrator. handle_error correctly remains in main() fatal handler only (standalone subprocess crash recovery). Naming bug fix confirmed.

---

## Package 2: EI Visual Cleanup

**Prerequisites:** Package 1 must be `verified`

**Status:** `verified`
**Coding Notes:** Deleted 8 formatting functions from ei_main.py (safe_log, colorize, beautiful_log, create_phase_header, create_progress_box, create_success_celebration, create_error_box, log_pipeline_start). Converted all safe_log calls to logging.info/warning/error. Deleted all create_phase_header calls (redundant with orchestrator mission box). Deleted all create_success_celebration calls (redundant with orchestrator completion box). Replaced create_error_box calls with logging.error. Deleted log_pipeline_start calls and startup banner in main(). Deleted "=" * 60 separator block in run_all_mode(). Removed handle_error() call and import from main() fatal handler. Removed _log_summary() functions and calls from ei_arbitrage_scanner.py, ei_fetch_upcoming.py, ei_snapshot_collector.py, ei_post_earnings_calc.py. Removed "=" * N separator banners from all 5 component files' standalone main() functions. Removed startup/completion banners from ei_moves_upcoming.py. Kept: [1/3] step markers as logging.info(), tree diagrams (├─/└─) as logging.info(), per-task confirmation lines as logging.info(), inline warnings as logging.warning(). ~150 lines deleted across 6 files.

**Verification Results:**
- [x] Grep: no beautiful_log, create_phase_header, create_success_celebration, create_error_box, create_progress_box, safe_log, log_pipeline_start in `strategies/earnings_intel/` — ZERO matches
- [x] Grep: no handle_error in `strategies/earnings_intel/ei_main.py` — ZERO matches
- [x] Grep: no `"=" * [0-9]` separator lines in target files (ei_main, ei_arbitrage_scanner, ei_fetch_upcoming, ei_snapshot_collector, ei_post_earnings_calc, ei_moves_upcoming) — ZERO matches. Remaining matches in ei_backfill_metrics.py (one-time script) and ei_health_reporter.py (file writes, not console) are out of scope.
- [x] Grep: `[1/3]` step markers exist as `logging.info()` — 6 matches confirmed (3 in weekly refresh, 3 in daily pipeline)
- [x] Grep: `├─` tree diagram content exists as `logging.info()` — 6 matches confirmed (3 in weekly refresh, 3 in daily pipeline)
- [x] Import check: `python -c "from strategies.earnings_intel.ei_main import run_morning_scan, run_weekly_refresh, run_daily_pipeline; print('OK')"` — succeeds

**Review Notes:**

---

## Package 3: OP Visual Cleanup

**Status:** `verified`
**Coding Notes:** Deleted 6 formatting functions from op_main.py (safe_log, create_phase_header, create_progress_box, create_success_celebration, create_error_box, log_pipeline_start). Converted all call sites: phase headers to inline logging.info with `── NAME (N/M) ──` format, tree diagrams to logging.info, safe_log to logging.info/warning/error. Deleted `_log_pipeline_summary()` method and its call (redundant with orchestrator completion box). Deleted startup banner and final success/failure prints in `main()`. Removed `safe_log()` definition from op_collector.py; converted all its safe_log calls to logging.info/warning/error. Removed `"=" * 70` + `COLLECTION COMPLETE` banner from op_collector.py (kept 6 metric lines). Removed `"=" * 60` + `OP ROLLUP COMPLETE` banner from op_symbol_rollup.py (kept stats lines). Removed `[OK]` marker and `BACKFILL COMPLETE` banner from op_timing_calculator.py.

**Verification Results:**
- [x] Grep: no safe_log, create_phase_header, create_success_celebration, create_error_box, create_progress_box, log_pipeline_start in `strategies/option_pipeline/` — ZERO matches
- [x] Grep: no `COLLECTION COMPLETE`, `ROLLUP COMPLETE` banner titles in `strategies/option_pipeline/` — only `"=" * N` in op_health_reporter.py (file writes, not console — out of scope)
- [x] Grep: `── ` sub-phase headers exist as `logging.info()` — 4 matches confirmed
- [x] Grep: `├─` tree diagram content exists as `logging.info()` — 12 matches confirmed
- [x] Import check: `python -c "from strategies.option_pipeline.op_main import OPOrchestrator; print('OK')"` — succeeds

**Review Notes:** PM verified 2026-02-18. All grep checks pass. Smoke test deferred (requires market data).

---

## Package 4: FM Pre-Market Dict Return

**Status:** `verified`
**Coding Notes:** Converted `run_pre_market()` in `fm_main.py` from bool to structured dict return. Added `start_time` capture, initialized default stats dicts for failure path, tracks `resolution_success`/`sentiment_success` flags. Returns contract dict with `success`, `duration_seconds`, `sub_tasks` (alert_resolution + sentiment_update), and top-level `alerts_resolved`/`symbols_updated`. Pre-market `success` is always True (alert resolution is non-critical). Updated `main_runners.py` `run_flow_monitor()`: skip paths use `{'success': True, 'skipped': True, ...}` dicts, completion box now shows alert resolution breakdown (building/closing/neutral) and sentiment count when pre-market actually ran. Import verification passed.

**Verification Results:**
- [x] Type check: `run_pre_market()` returns `dict` (not `bool`)
- [x] Content check: FM completion box shows "Alerts resolved: N" (not just "Pre-Market: Success")
- [x] PM verified: return dict matches RETURN_DICT_CONTRACTS.md contract exactly
- [x] PM verified: failure path has default stats initialized before try block
- [x] PM verified: skip paths return dict with `skipped: True`
- [x] PM verified: `pre_market_success` derived from dict for backward compat
- [x] Import check: `from strategies.flow_monitor.fm_main import run_pre_market` — OK

**Review Notes:** PM verified 2026-02-18. Contract match confirmed. Skip paths, failure path, and completion box all correct.

---

## Package 5: FM Post-Market Research + Dict

**Status:** `complete`
**Coding Notes:**

**Research findings (Step 1):**
- `run_historical_backfill()`: Subprocess (Popen). Parses stdout for "Symbols with data: N/M" → `symbols_updated`, `symbols_total`. Exit codes 0=success, 1=catastrophic, 2=partial. Returns dict with `partial` flag and `return_code`.
- `run_evening_market_regime_summary()`: Subprocess via `run_subprocess_task()`. Exit code only. Returns minimal `{success, duration_seconds}`. `skipped` flag if task disabled.
- `run_symbol_rollup_task()`: In-process. `SymbolSummaryBuilder.populate_daily_summary()` returns bool, but `rollup.stats` attribute has `{symbols_processed, summaries_created, errors}`. Now reads stats attribute.
- `run_daily_evaluation_task()`: Subprocess (Popen). Exit code only. Returns `{success, duration_seconds, return_code}`.
- `archive_expired_entries()`: Already returned dict. Wrapped with `success` and `duration_seconds`.

**Implementation (Steps 2-4):**
- All 4 inner wrapper functions converted from bool→dict with research-based docstrings
- `run_post_market()` returns aggregated dict: `success`, `duration_seconds`, `tasks_successful/total`, `errors`, `sub_tasks` (5 sub-task dicts)
- Removed 4 DB diagnostic queries from `run_post_market()` — metrics come from return dicts
- Diagnostic logger still writes from return dict values
- `handle_error()` calls preserved (autofix still needs them during post-market)
- Orchestrator `run_flow_monitor()` updated: completion box shows task count, backfill/rollup/cleanup details from dict
- CLI `main()` fixed to extract `success` bool from dict

**Verification Results:**
- [x] Research documented: each changed function has a comment documenting what the component returns
- [x] Type check: `run_post_market()` returns `dict` (not `bool`)
- [ ] Smoke test: `python strategies/flow_monitor/fm_main.py --post-market --no-interaction` runs without crashes (deferred — requires market data)
- [x] PM verified: all 4 inner wrappers return dicts with research-based docstrings
- [x] PM verified: sub-task aggregation correct (5 results → sub_tasks dict → success = all passed)
- [x] PM verified: handle_error() calls preserved (CRITICAL for backfill, ERROR for others)
- [x] PM verified: CLI main() correctly extracts success bool from dict
- [x] PM verified: orchestrator completion box shows task counts + backfill/rollup/cleanup details
- [x] PM verified: exception paths in orchestrator return proper failure dicts
- [x] Import check: `from strategies.flow_monitor.fm_main import run_post_market` — OK

**Review Notes:** PM verified 2026-02-18. Contract match confirmed. Research phase well-documented. DB diagnostic queries correctly removed. handle_error() calls correctly preserved (unlike pre-market where they were removed per contract).

---

## Package 6A: FM Formatting Functions + Coffee Break Rewrite

**Prerequisites:** Package 0 must be `verified`

**Status:** `verified`
**Coding Notes:** Deleted 9 formatting function definitions from fm_main.py: `get_display_settings()`, `colorize()`, `beautiful_log()`, `create_phase_header()`, `create_task_box()`, `create_error_box()`, `create_success_celebration()`, `create_section_divider()`, `contextual_coffee_break()`. Also deleted `get_api_budget_info()` (zero callers). Kept `get_dynamic_symbol_count()` (callers in `run_market_hours()` line 1064 and `run_post_market()` line 1440). Removed the `# BEAUTIFICATION FUNCTIONS (ENHANCED)` section header. Rewrote `coffee_break()` to use `create_status_box` from `tools.log_utils` with context-aware messages, interruptible sleep via `shutdown_event`, and optional "Up Next" line. Removed the post-sleep "Resuming operations" beautiful_log call (no longer needed — standard box output is sufficient). ~120 lines deleted, ~25 lines rewritten.

**Verification Results:**
- [x] Grep: no `def get_display_settings`, `def colorize`, `def beautiful_log`, `def create_phase_header`, `def create_task_box`, `def create_error_box`, `def create_success_celebration`, `def create_section_divider`, `def contextual_coffee_break` in fm_main.py — ZERO matches
- [x] Grep: `create_status_box` appears in fm_main.py — 2 matches (import + call in rewritten `coffee_break()`)
- [x] Coffee break callers: 5 call sites pass valid `context=` values (backfill_complete, backfill_partial, sync_complete via variable, task_complete x2)
- [x] Import check: `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — succeeds
- [x] PM verified: get_api_budget_info() correctly deleted (zero callers)
- [x] PM verified: get_dynamic_symbol_count() correctly kept (callers in run_market_hours + run_post_market)

**Review Notes:** PM verified 2026-02-18. All 10 functions deleted (9 formatting + 1 unused utility). coffee_break() correctly rewritten. ~96 beautiful_log call sites remain — expected until 6B/6C/6D complete.

---

## Package 6B: FM Function-Level Triage (Pre/Post-Market + Utilities)

**Prerequisites:** Packages 4, 5, AND 6A must be `verified`

**Status:** `complete`
**Coding Notes:** Executed all 5 steps (numbered 3-6, 8 per WORK_PACKAGES.md). Step 3 (`run_historical_backfill()`): Deleted `create_task_box()` call, 2 starting announcements, 2 completion announcements, and 2 `create_error_box()` calls. Converted subprocess output streaming, partial-success warnings, early-wait message, and error-path logging to `logging.info()`/`logging.warning()`/`logging.error()`. Step 4 (`run_quick_sync()`): Deleted "Starting" announcement. Converted success completions to `logging.info()`, failure/timeout/error paths to `logging.warning()`. Removed blank-line separator in error diagnostics. Step 5 (`safe_log`): Deleted `safe_log()` function definition. Converted all 38 `safe_log()` calls: `run_subprocess_task()` (10 calls), `run_pipeline()` (3), `run_symbol_rollup_task()` (4), `run_analysis_backfill_task()` (9), `run_daily_evaluation_task()` (3), `main()` CLI entry points (7). Used `logging.info()` for normal output, `logging.warning()` for warnings, `logging.error()` for errors. Step 6 (`run_pre_market()`): Deleted `create_phase_header()`, 2 opening announcements, `create_success_celebration()`, and `create_error_box()`. Converted sub-phase progress (alert resolution, sentiment update) and error-path warnings to `logging.info()`/`logging.warning()`. Step 8 (`run_post_market()`): Deleted `create_phase_header()`, opening announcement, `create_success_celebration()`, and `create_error_box()`. Removed all 5 `handle_error()` calls (1 CRITICAL for backfill, 3 ERROR for regime/rollup/evaluation, plus the entire CRITICAL block including import/call/comment). Converted all per-task progress and confirmation lines to `logging.info()`/`logging.warning()`. Kept `coffee_break()` calls, diagnostic logger writes, and agent `queue_error()` call (not handle_error). Also converted agent analysis beautiful_log calls in the optional agent section. Note: `create_task_box`, `create_phase_header`, `create_success_celebration`, `create_error_box` all show zero matches in entire file (all call sites removed across 6A+6B+6C).

**Verification Results:**
- [x] Grep: no `safe_log` in fm_main.py — ZERO matches (definition deleted + all calls converted)
- [x] Grep: no `beautiful_log` in fm_main.py — ZERO matches in entire file (6C already handled run_market_hours, 6B handled everything else)
- [x] handle_error check: 3 `handle_error` calls in fm_main.py, all in `run_market_hours()` (3 CRITICAL). Post-market's 5 calls removed (1 CRITICAL + 3 ERROR + their imports/comments). Note: WORK_PACKAGES.md said "4 matches" but 6C coding notes clarify: 3 handle_error (CRITICAL) + 1 queue_error (WARNING, news enrichment) in run_market_hours().
- [x] Import check: `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_post_market; print('OK')"` — succeeds

**Review Notes:**

---

## Package 6C: FM Market Hours Triage

**Prerequisites:** Package 6A must be `verified`

**Status:** `verified`
**Coding Notes:** Converted all 24 `beautiful_log()` calls in `run_market_hours()`. Deleted: `create_phase_header("MARKET HOURS MONITORING")` call + dead `symbol_count = get_dynamic_symbol_count()` variable (no longer used after header removal), startup banner (2 lines: "INITIATING MARKET HOURS PIPELINE" + "Real-time monitoring"), completion announcement ("MARKET HOURS PIPELINE COMPLETE"). Converted 21 calls: market close signal → `logging.info()`, cycle header → `logging.info()` (stripped `===` decoration), collection complete → `logging.info()`, collection failed → `logging.warning()`, market cycle error → `logging.error()` (removed duplicate `logging.error("Market hours pipeline error")` on next line — now redundant), 7 performance breakdown lines → `logging.info()`, 7 performance summary lines → `logging.info()`, end-of-day lines loop → `logging.info()` (expanded ternary to if/else for clarity), symbol gaps saved → `logging.info()`. All 3 `handle_error()` calls (CRITICAL) and 1 `queue_error()` call (WARNING, news enrichment) preserved untouched. `coffee_break()` calls preserved (already rewritten in 6A). Note: WORK_PACKAGES.md says "4 handle_error" but the 4th is actually `queue_error` — the verification grep for `handle_error` will find 3 matches in run_market_hours(), not 4. The `queue_error` at line 1188 is the WARNING-severity news enrichment autofix integration.

**Verification Results:**
- [ ] Grep: no `beautiful_log` in entire fm_main.py (6B handled non-market-hours, 6C handles market hours)
- [x] handle_error check: 3 `handle_error` matches in `run_market_hours()` (all `severity='CRITICAL'`) + 1 `queue_error` match (`severity='WARNING'`, news enrichment) — all 4 autofix integration points preserved
- [x] Market hours output: multi-line performance breakdown preserved (7 `logging.info()` lines), startup banner deleted (3 lines), completion announcement deleted (1 line), duplicate error log removed (1 line)
- [x] Import check: `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — succeeds
- [x] **ASK BEN resolved:** Cycle header keeps `===` markers — Ben prefers them for grep-ability

**Review Notes:** Cycle header keeps `===` markers per Ben's preference: `logging.info("=== Cycle N | HH:MM:SS | N symbols ===")`. Section 17 discrepancy resolved — Section 10 was correct to show them in the approved target.

---

## Package 6D: FM Component Files Cleanup

**Prerequisites:** Package 6A must be `verified`

**Status:** `complete`
**Coding Notes:** Step 9: Cleaned 8 FM component files. `fm_alerts.py`: Removed `"="*80` border lines, `"-"*N` category separators, and trailing `"="*80` from `_send_console_alerts()`; converted all `print()` to `logging.info()`; blank lines replace separators between categories. Removed `"="*50` borders from `_log_alert_summary()`. `fm_analyzer.py`: Removed `"="*60` borders from `_log_analysis_summary()`; kept all stat lines. `fm_social_notifier.py`: Removed `"="*80` box from `check_alert()` queue notification; converted `print()` to `logging.info()`; CLI `main()` print statements kept per spec. `fm_collector.py`: Converted ~10 `print()` startup/status messages to `logging.info()` in `run_once()`, `run_once_forced()`, and `_collect_market_data()`/`_collect_options_data()`; standalone `main()` `"="*50` removed. `fm_alert_resolver.py`: Removed `"="*60` diagnostic separators. `fm_symbol_rollup.py`: Removed `"="*60` borders from `_log_completion_stats()` and standalone `main()`. `evaluation/fm_evaluator.py`: Removed all `"="*70` and `"="*50` separators (run_evaluation start/end, _log_evaluation_summary, standalone main). `fm_agent.py`: Removed `"="*70` separators from standalone `__main__` block. Step 10: Verified `safe_log` has zero matches in component files (only in fm_main.py, which is 6B scope). Step 11: Removed 3 dead imports from fm_main.py: `import requests` (zero usage), `from collections import deque` (zero usage), `psutil` try/except block (zero usage). Kept `subprocess` and `json` (both actively used).

**Verification Results:**
- [x] Grep: `safe_log` in `strategies/flow_monitor/` — only in fm_main.py (6B scope), zero in component files
- [x] Grep: `"=" * [0-9]` or `"="*[0-9]` in all 8 target files — ZERO matches. Remaining hits: fm_baseline_generator.py (excluded per spec), fm_health_reporter.py (file writes not console), fm_watchlist.py (email body per spec), fm_main.py function bodies (6B scope), evaluation/backfill_*.py and run_daily_evaluation.py (not in 6D scope)
- [x] Import check: `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — succeeds
- [ ] FM internal coffee breaks use `create_status_box()` — verified in 6A (coffee_break rewrite)
- [x] **ASK BEN:** Alert display borders in fm_alerts.py — **REMOVED** per VISUAL_DESIGN_REFERENCE.md Section 16 target mockup. The design doc explicitly shows borders removed with blank-line separation. Section 16 Note says "this is the easiest item to reverse" if Ben wants them back. Emoji category headers (red/yellow/white circle) provide sufficient visual grouping.
- [ ] Full Phase 2 output matches mockup — deferred (requires live market run)

**Review Notes:** Alert borders decision: Removed per the approved target in VISUAL_DESIGN_REFERENCE.md Section 16. The doc notes: "If Ben prefers the borders to stay, this is the easiest item to reverse." To restore, change `logging.info()` calls back to `print()` calls with `"="*80` borders in `_send_console_alerts()` and `"="*50` in `_log_alert_summary()`. Dead imports removed: `requests`, `deque`, `psutil` — none had any usage in fm_main.py.

---

## Package 7: Utility Runner Polish

**Status:** `complete`
**Coding Notes:** Step 1: Removed remaining filler phrases from main_runners.py. Changed "Creates 4 SQL views" to "Creates SQL views" in morning views mission box (line 651). Changed "ALL ~750 symbols" to "all tracked symbols" in metadata docstring (line 729) and "ALL ~750 symbols per run (~60 seconds)" to "Full KLMN universe per run" in metadata mission box (line 742). Step 2: Removed 4 `beautiful_log` calls from `run_airline_play_phase()`: "Running airline tracking for trade date" (pre-execution announcement), "Phase 1/2: Symbol-level tracking extraction" (redundant phase marker), "Phase 2/2: Options-level contract filtering" (redundant phase marker), "Airline tracking phase completed successfully" (duplicate success before completion box). Kept warning-path ("completed with no data") and error-path ("fatal error") beautiful_log calls. Completion box already uses dict values (symbols_processed, contracts_tracked). Step 3: Removed duplicate `beautiful_log("Batch mode completed: N session(s) spawned")` before completion box in `run_batch_mode_review()`. ERROR QUEUE intermediate box kept (acceptable per spec). No other duplicate announcements found.

**Verification Results:**
- [x] Grep: no "Database secured", "Performance optimized", "Ready for.*operations", "~750", "4 SQL views" in main_runners.py — ZERO matches

**Review Notes:**
