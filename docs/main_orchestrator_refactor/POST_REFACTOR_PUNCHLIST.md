# Post-Refactor Punchlist

**Created:** 2026-02-18
**Purpose:** Issues found during live validation of the console output refactor. Each item discovered by running `main.py --simulate-time "06:35"` and comparing output against VISUAL_DESIGN_REFERENCE.md specs.

**Status:** Phase 5 Friday review complete (2026-02-22). P-001 through P-053 done. P-054–P-057 open (FM audits + session accumulators). P-058–P-070 done. 4 items remain open.

---

## Instructions for Analysts

This is a living document. The PM session (Claude Code) adds items during review; coding analysts implement them and mark completion.

### Picking up an item
1. Read the item's **Problem** and **Fix** sections completely
2. Read any referenced files before making changes
3. If an item says "depends on P-XXX", check that P-XXX is marked `DONE` first
4. Items in P-006's subprocess list depend on their corresponding print→logging conversion (P-010, P-018, P-020) being done first

### Marking an item complete
Add a **Status** line at the end of the item block:

```
**Status:** `DONE` — [your name/session], [date]. [One sentence summary of what you did.]
```

Example:
```
**Status:** `DONE` — Analyst session, 2026-02-19. Changed `% 500` to `% 100` on line 111, verified output shows 8 progress lines.
```

### If an item needs adjustment
If the fix described doesn't quite work or you discover something new:

```
**Status:** `PARTIAL` — [your name/session], [date]. [What you did + what remains or what you found.]
```

### Do NOT
- Delete or rewrite existing item descriptions (the PM session uses them for context)
- Renumber items (P-XXX numbers are permanent, even if items are closed or reordered)
- Add new items (only the PM review session adds items — if you find something new, note it in your status line and the PM will create a proper item)
- Change the Recurring Patterns or Future Consideration sections

### Reference docs
- `VISUAL_DESIGN_REFERENCE.md` — what the output should look like (mockups + specs)
- `WORK_PACKAGES.md` — original refactor scope and architecture decisions
- `CONSOLE_OUTPUT_STANDARD.md` — target architecture
- `RETURN_DICT_CONTRACTS.md` — strategy return dict schemas

---

## Items

### P-001: Banner border misalignment on emoji lines
**Location:** `main_ui.py:124` — `row()` function inside `print_banner()`
**Severity:** Visual
**Problem:** Python's `{:<65}` string formatting counts emojis as 1 character, but terminals render them as 2 columns wide. Every line with an emoji pushes the right `║` border 1 char too far right. Lines without emojis align correctly.
**Fix:** Replace `{:<{}}` formatting with display-width-aware padding using `unicodedata.east_asian_width()`. Calculate true display width, then pad with explicit spaces.
**Affected lines:** All `row()` calls containing emojis: `🚀📅⏰🏭🌟🎯` (6 lines in full mode, plus single-step modes).
**Status:** `DONE` — Analyst session, 2026-02-18. Added `_display_width()` and `_pad_to_width()` helpers to `log_utils.py`. Replaced `{:<{}}` in `row()` with `_pad_to_width()`. Verified all emoji and non-emoji lines align to same column.

### P-002: Log rotation line uses raw logging.info() instead of beautiful_log()
**Location:** `main.py:295`
**Severity:** Visual consistency
**Problem:** Three operational lines appear after the startup banner. Two use `beautiful_log()` (emoji + simulated time format), but the log rotation message uses `logging.info()` (full date + INFO level format). This breaks visual uniformity.
**Before:** `2026-02-18 20:02:51 - INFO - Daily log rotation complete: orchestrator_2026-02-18.log`
**After:** `ℹ️ 06:35:00 - Daily log rotation complete: orchestrator_2026-02-18.log`
**Fix:** Change `logging.info(...)` to `self.beautiful_log(...)` at main.py:295.
**Status:** `DONE` — Analyst session, 2026-02-18. Changed `logging.info(...)` to `self.beautiful_log(..., 'info')` at main.py:295.

### P-003: Mission box step label missing "Refresh"
**Location:** `main_runners.py` — `run_morning_option_pipeline()` beautiful_log call
**Severity:** Copy tweak
**Problem:** Step announcement says `"Step 1.1: Morning Option Pipeline"` — should say `"Step 1.1: Morning Option Pipeline Refresh"` to match the schedule in the banner.
**Fix:** Append "Refresh" to the step label string.
**Status:** `DONE` — Analyst session, 2026-02-18. Changed `beautiful_log` at `main.py:390` to include "Refresh". Dict keys and `_save_orchestrator_result` key left unchanged (programmatic identifiers).

### P-004: Mission box "Steps" line wording
**Location:** `main_runners.py` — `run_morning_option_pipeline()` mission box lines
**Severity:** Copy tweak
**Problem:** `"Steps: Collection → Rollup → OI Timing Analysis → Report"` is wordy.
**Fix:** Change to `"Steps: Collection → Rollup → OI Timing → Health Report"`
**Status:** `DONE` — Analyst session, 2026-02-18. Updated both morning and evening OP mission boxes (lines 224, 567) for consistency.

### P-005: Emoji width issue in mission boxes (same root cause as P-001)
**Location:** `tools/log_utils.py` — `create_status_box()` function
**Severity:** Visual
**Problem:** The mission box `🌅 MORNING OPTION PIPELINE REFRESH` line pushes the right `║` border out, same as P-001. The `create_status_box()` function likely uses the same `{:<width}` pattern that doesn't account for emoji display width.
**Fix:** Apply the same display-width-aware padding fix from P-001 to `create_status_box()` in `log_utils.py`. This fixes ALL boxes system-wide (mission, completion, coffee break, failure).
**Status:** `DONE` — Analyst session, 2026-02-18. Replaced `len()` with `_display_width()` in width calculation and `{:<{}}` with `_pad_to_width()` in title and content line formatting. Verified with mission box, coffee break box, and failure box (incl. ⚠️ content).

### P-006: Shorten strategy subprocess console log format
**Location:** Strategy logging configuration (StreamHandler formatter)
**Severity:** Visual consistency
**Problem:** Strategy subprocesses use `'%(asctime)s - %(levelname)s - %(message)s'` with full datetime, producing noisy console lines like `2026-02-18 20:02:53 - INFO - ├─ Universe: 746 symbols`. The date is always today (useless) and the level is almost always INFO (noise).
**Before:** `2026-02-18 20:02:55 - INFO - Fetching option expirations for A`
**After:** `06:35:05 - Fetching option expirations for A`
**Fix:** Split formatter by handler — StreamHandler gets short format (`'%(asctime)s - %(message)s'`, `datefmt='%H:%M:%S'`), FileHandler keeps full format (`'%(asctime)s - %(levelname)s - %(message)s'`) for greppable log files.
**Confirmed subprocess(es):**
- `strategies/option_pipeline/op_main.py` (op_collector.py, op_symbol_rollup.py, op_timing_calculator.py progress lines)
- `strategies/earnings_intel/ei_main.py` (arbitrage scanner progress lines)
- `data/symbol_metadata.py` (all 5 phases use print(), no timestamps at all — needs logging.info conversion first via P-018)
- `data/health/db_backup.py` (sync function uses print() exclusively — needs logging.info conversion first via P-020)

*(Add other subprocesses here as we encounter them during review)*
**Status:** `DONE` — Partial fix: Analyst session, 2026-02-18 (in-process strategies via main.py root logger). Completed: 2026-02-19 — split formatters in both remaining subprocesses: `symbol_metadata.py` (basicConfig with separate console/file handlers) and `db_backup.py` (console_formatter short, file_formatter full). Also added `logger.propagate = False` to db_backup logger to fix P-053 (duplicate log line).

### P-007: OP Rollup progress reporting interval is 500, spec says 100
**Location:** `strategies/option_pipeline/op_symbol_rollup.py:111`
**Severity:** Functional (spec mismatch)
**Problem:** Progress is reported every 500 symbols (`batch_end_idx % 500 == 0`), but batch size is 100 and VISUAL_DESIGN_REFERENCE spec says "Per 100". Result: user sees nothing between start and 500/746, then jumps to 746/746. Feels like it hung.
**Fix:** Change `% 500` to `% 100` on line 111.
**Status:** `DONE` — Analyst session, 2026-02-18. Changed `% 500` to `% 100` on line 111. User will now see 8 progress lines for 746 symbols.

### P-008: Add 2 blank lines between OP sub-phase steps
**Location:** `strategies/option_pipeline/op_main.py` — between each sub-phase (DATA COLLECTION, SYMBOL ROLLUP, OI TIMING, HEALTH REPORT)
**Severity:** Visual (readability)
**Problem:** Sub-phases run together with no visual breathing room. Each step's completion stats bleed directly into the next `── 📈 SYMBOL ROLLUP (2/4) ──` header.
**Fix:** Add 2 blank lines (via `logging.info("")` x2, or `print("")` x2) at the end of each sub-phase, before the next header. Apply consistently across all 4 OP sub-phases.
**Status:** `DONE` — Analyst session, 2026-02-18. Converted existing `logging.info("")` to `print("")` (decorative, no log file value) and added a second `print("")` before each of the 4 sub-phase headers for 2 blank lines of visual separation.

### P-009: Redundant rollup confirmation lines from two layers
**Location:** `strategies/option_pipeline/op_storage.py:1224` and `op_symbol_rollup.py:121`
**Severity:** Noise
**Problem:** Two intermediate "I did it" lines print before the completion stats block, which already covers the same info:
- `"OP: Inserted 746 symbol summary records"` (storage layer)
- `"OP Rollup: Successfully created 746 symbol summaries"` (rollup layer)
- Then `_log_completion_stats()` prints Total symbols: 746, Summaries created: 746, etc.
**Fix:** Delete both intermediate lines. The completion stats block is the single source of truth.
**Status:** `DONE` — Analyst session, 2026-02-18. Removed `logging.info()` from `op_storage.py:1224` and `op_symbol_rollup.py:121`. Completion stats via `_log_completion_stats()` remains as the single source of truth.

### P-010: OI Timing progress uses print() instead of logging.info()
**Location:** `strategies/option_pipeline/op_timing_calculator.py` — lines 108, 122, 155, 160
**Severity:** Inconsistency
**Problem:** All progress lines in OI Timing use raw `print()` (no timestamp prefix), while collector and rollup use `logging.info()`. Result: some lines have timestamps, some don't, within the same pipeline. Also, `print()` lines don't reach the log file.
**Fix:** Convert all `print()` calls to `logging.info()`. Once P-006 shortens the format, these will look clean.
**Status:** `DONE` — Analyst session, 2026-02-18. Converted 4 print() calls to logging.info() (lines 108, 122, 155, 160). Added `import logging`. Line 108 split into `print("")` (decorative blank) + `logging.info()` to preserve visual spacing without a timestamped blank line.

### P-011: OI Timing progress interval is 100, spec says 1,000
**Location:** `strategies/option_pipeline/op_timing_calculator.py:154`
**Severity:** Spec mismatch
**Problem:** Reports every 100 contracts (`processed % 100 == 0`), but VISUAL_DESIGN_REFERENCE spec says "Per 1,000" for contract-scale operations (~13K items). At 100 intervals, this produces ~139 progress lines — way too noisy.
**Fix:** Change `% 100` to `% 1000` on line 154.
**Status:** `DONE` — Analyst session, 2026-02-18. Changed `% 100` to `% 1000` on line 154. ~13K contracts now produce ~13 progress lines instead of ~139.

### P-012: OP completion box missing duration and showing filler status line
**Location:** `main_runners.py:250-265` — morning OP completion box builder
**Severity:** Content (spec violation)
**Problem:** The completion box is missing duration (spec says "Include: key counts, duration, error count if > 0") and ends with `"Status: ✅ Complete pipeline executed"` which is filler — the box title already says COMPLETE.
**Available in return dict but not shown:**
- `total_execution_time` — total pipeline duration (seconds)
- `collection.symbols_failed` + `collection.failed_symbols` — error count and list
- `health` — health report status (PASS/WARN/UNKNOWN)
**Fix:** Remove the `"Status: ✅ Complete pipeline executed"` line. Add:
- `"Duration: {m}m {s}s"` (from `results['total_execution_time']`)
- `"Health: {status}"` (from `results['health']`)
- `"Failed Symbols: N (SYM1, SYM2)"` (conditional, only if `collection.symbols_failed > 0`)
**Status:** `DONE` — Analyst session, 2026-02-18. Removed filler "Status" line. Added Duration (from `total_execution_time`), Health (from `health.pipeline_health.overall_status` — HEALTHY/DEGRADED/CRITICAL), and conditional Failed line (count + up to 8 symbol names, only when `symbols_failed > 0`).

### P-013: Coffee break "Duration: 1 minutes" — singular/plural grammar
**Location:** `main_ui.py` — `coffee_break()` duration formatting
**Severity:** Grammar nit
**Problem:** `"Duration: 1 minutes"` should be `"Duration: 1 minute"` (singular).
**Fix:** Add singular/plural logic: `"Duration: {} minute{}".format(m, "" if m == 1 else "s")`
**Status:** `DONE` — Analyst session, 2026-02-18. Added singular/plural logic to both minutes and seconds branches in `coffee_break()`.

### P-014: Metadata mission box — remove "Quota" line
**Location:** `main_runners.py` — `run_metadata_collection()` mission box lines
**Severity:** Copy tweak
**Problem:** `"Quota: Full KLMN universe per run"` is no longer meaningful.
**Fix:** Remove the Quota line.
**Status:** `DONE` — Analyst session, 2026-02-18. Removed "Quota" line from metadata mission box.

### P-015: Metadata — rename "Phase" to "Part" in progress labels
**Location:** `data/symbol_metadata.py` — lines 904, 932, 966, 998, 1094
**Severity:** Terminology consistency
**Problem:** "Phase" is reserved for macro orchestrator phases (Pre-Market, Flow Monitor, Post-Market). Metadata sub-steps should use "Part" to avoid confusion.
**Fix:** Change `"Phase 1:"` → `"Part 1:"` through `"Phase 5:"` → `"Part 5:"` in all 5 section headers.
**Status:** `DONE` — Analyst session, 2026-02-18. Changed all 5 print labels and their corresponding code comments from "Phase" to "Part".

### P-016: Metadata fundamentals — reduce reporting granularity from 75 batches to match quotes rhythm
**Location:** `data/symbol_metadata.py:941` — fundamentals batch progress
**Severity:** Noise / visual consistency
**Problem:** Fundamentals API requires batch size of 10 (API constraint, can't change), producing 75 batch lines with a single symbol hint (`Batch 47/75: M... 10/10 OK`). Quotes uses batches of 100, producing 8 clean lines. The 75-line wall is noisy and the single symbol hint adds no value.
**Fix:** Keep `FUNDAMENTALS_BATCH_SIZE = 10` for the API calls, but only print progress every 10 batches (every 100 symbols). Format: `"  Progress: 100/746 symbols... 100/100 OK"` to mirror quotes style. Show the final completion line always.
**Status:** `DONE` — 2026-02-19. Added `batch_num % 10 == 0 or batch_num == total_batches` guard. 75 lines → 8 lines (7 at intervals of 100 + final batch). Format: `"Progress: 100/746 symbols... 100/100 OK"`.

### P-017: Metadata beta progress format doesn't mirror quotes format
**Location:** `data/symbol_metadata.py:986` — beta progress
**Severity:** Visual consistency
**Problem:** Beta shows `"Progress: 100/746 symbols..."` but quotes shows `"Batch 1/8: 100 symbols... 100/100 OK"`. Beta has no success/total indicator.
**Fix:** Align to a common format: `"  Progress: 100/746 symbols... 100/100 OK"` — mirrors the consolidated quotes/fundamentals pattern.
**Status:** `DONE` — Analyst session, 2026-02-18. Moved progress print after beta calculation so success count is current, added `{success}/{processed} OK` suffix to match quotes format.

### P-018: Metadata print() lines don't reach the text log
**Location:** `data/symbol_metadata.py` — all `print()` calls (lines 831-1148)
**Severity:** Forensic gap
**Problem:** Nearly all metadata progress uses raw `print()`, which doesn't reach the log file (`data/logs/symbol_metadata_collector.log`). Only `logging.info/error/warning` calls do. If batch 47 fails silently, there's no trace in the log. The clean console output comes at the cost of zero log file forensics.
**Fix:** Convert progress `print()` calls to `logging.info()`. With P-006's short StreamHandler format, console stays clean. FileHandler captures everything. The structural header and `====` borders can stay as `print()` since they're purely decorative. See P-019 for the pattern.
**Status:** `DONE` — Analyst session, 2026-02-18. Converted ~30 print() calls to logging.info/error(). Kept as print(): title block (pre-logging, decorative), `===` borders, blank separator lines, KeyboardInterrupt message. Fatal config errors → logging.error(). Batch `end=" "` patterns (quotes, fundamentals) combined into single logging.info() after batch completes. Leading `\n` on Part headers split to `print("")` + `logging.info()`. Redundant `print("Collection failed")` consolidated with existing logging.error(). P-006 subprocess list update still needed for console format shortening.

### P-019: Metadata completion box — accepted as-is
**Location:** `main_runners.py` — `run_metadata_collection()` completion box
**Severity:** ~~Content gap~~ Accepted
**Decision:** The strategy's own `COLLECTION SUMMARY` block is sufficient. The orchestrator box stays minimal. No JSON summary file needed. The real fix is P-018 (get progress into log files) and P-006 (clean timestamps on console).

### P-021: Morning Views — too sparse, restore 3 context lines
**Location:** `main_runners.py` — `run_morning_views()`
**Severity:** Content (over-stripped)
**Problem:** Package 0 correctly removed duplicate announcements, but the result is too bare — mission box then silence then completion box, with no indication of what's happening during the ~2 minute wait.
**Fix:** Add 3 `beautiful_log` lines between mission box and subprocess call:
```
🔥 07:57:21 - Initializing Morning Views generation
🔄 Running morning views (console output suppressed - use TUI)...
✅ 07:59:47 - Morning Views Completed Successfully
```
- Line 1: `self.beautiful_log("Initializing Morning Views generation", 'highlight')` — before subprocess starts
- Line 2: `self.beautiful_log("Running morning views (console output suppressed - use TUI)...", 'info')` — explains the silence
- Line 3: `self.beautiful_log("Morning Views Completed Successfully", 'success')` — after subprocess returns, before completion box
**Note:** These are orchestrator-level context lines (beautiful_log), not strategy output. They frame the subprocess gap.
**Status:** `DONE` — Analyst session, 2026-02-18. Added 3 `beautiful_log` calls: 'phase' + 'info' before subprocess, 'success' after successful return (before completion box). Used 'phase' level (🔥) for line 1 since 'highlight' isn't a defined level.

### P-020: DB Backup sync — key forensic lines don't reach the text log
**Location:** `data/health/db_backup.py` — sync function (~lines 1096-1610)
**Severity:** Forensic gap
**Problem:** The sync function uses `print()` for nearly everything. The orchestrator text log captures only the mission box and completion box — nothing from the 14-minute sync itself. No source/target sizes, no page count, no duration, no verification results.
**Fix:** Convert these 8 key lines from `print()` to `logging.info()`:
| Line | Content | Why |
|------|---------|-----|
| ~1121 | `Source: data/datalake.db (10.40 GB)` | What we synced, how big |
| ~1127 | `Target: data/datalake_query.db (10.40 GB) - EXISTS` | Target state before sync |
| ~1400 | `✅ Backup completed: 2726175 pages (10.40 GB)` | Backup outcome |
| ~1454 | `✅ Sync completed successfully in 14.0 minutes` | Duration |
| ~1522 | `Data verified: ✅ YES (latest timestamp: ...)` | Freshness proof |
| ~1559 | `Schema match: ✅ YES (29 tables)` | Integrity check |
| ~1564 | `Data match: ✅ YES` | Integrity check |
| ~1605 | `🔓 Sync lock file removed` | Lock lifecycle complete |

Keep as `print()`: `======` borders, header, `Timestamp:`, all ~90 `Progress: N/M pages` heartbeat lines, `Verifying data freshness...` headers, redundant `✅ QUERY DATABASE SYNC SUCCESSFUL` line.
**Also add to P-006 subprocess list** for console format shortening once logging.info is in place.
**Status:** `DONE` — Analyst session, 2026-02-18. Converted 8 key forensic lines from `print()` to `logger.info()` (named logger `'db_backup'`): source/target sizes, backup page count, sync duration, data freshness verification, schema match, data match, lock file removal. All other ~100+ print() calls kept as-is (decorative, heartbeat, error diagnostics). P-006 subprocess list update still needed for console format shortening.

### P-022: FM pre-market output cleanup — diagnostic suppression, boxes, beautiful_log
**Location:** `strategies/flow_monitor/fm_main.py` (`run_pre_market()`), `fm_alert_resolver.py`, `data/health/db_backup.py` (resolution sync), `main_runners.py` (`run_flow_monitor()`)
**Severity:** Visual (noise + duplication + missing structure)
**Problem:** Pre-market output is ~30 lines when it should be ~8. Three categories:

1. **Diagnostic noise**: FlowMonitorStorage init line, 8-line `ALERT RESOLUTION DIAGNOSTIC` block, batch progress (`Processed 10/22...`), `Preparing batch update`, `Executing batch UPDATE` — forensic detail, text-log only.

2. **Duplication**: Alert result × 2 (strategy line + coordinator line). Sync result × 3 (db_backup `======` decorated block + `db_backup` named logger line + coordinator summary). Sentiment × 3 (starting + detailed result + coordinator summary).

3. **Missing structure**: No mission/completion boxes wrapping pre-market. No step indicators for the three sub-tasks (resolution, sentiment, sync).

**Enabler:** `beautiful_log()` is already standalone in `tools/log_utils.py:127`. Any module can `from tools.log_utils import beautiful_log`. No extraction needed.

**Target output:**
```
╔═════════════════════════════════════════════════════════════╗
║ 🔍 PRE-MARKET PREPARATION                                   ║
╠═════════════════════════════════════════════════════════════╣
║ Step 1: Alert Resolution — resolve yesterday's open alerts  ║
║ Step 2: Sentiment Update — label watchlist entries           ║
║ Step 3: Database Sync — push updates to query database      ║
╚═════════════════════════════════════════════════════════════╝

── Step 1/3: Alert Resolution ─────────────────────────────────

🔍 09:15:01 - Resolving Yesterday's Flow Alerts
ℹ️ 09:15:01 -    Using fresh OI data from morning Option Pipeline
✅ 09:15:02 - Alert resolution complete: 22 resolved (18 BUILDING, 1 CLOSING, 3 NEUTRAL)

── Step 2/3: Sentiment Update ─────────────────────────────────

🔍 09:15:02 - Updating sentiment for 79 watchlist symbols
✅ 09:15:03 - Watchlist sentiment updated: 79 symbols (58 BUILDING, 9 CLOSING, 12 NEUTRAL)

── Step 3/3: Query Database Sync ──────────────────────────────

✅ 09:15:03 - Pre-market updates synced to query database

╔═════════════════════════════════════════════════════════════╗
║ ✅ PRE-MARKET PREPARATION COMPLETE                           ║
╠═════════════════════════════════════════════════════════════╣
║ Alerts resolved: 22 (18 BUILDING, 1 CLOSING, 3 NEUTRAL)    ║
║ Watchlist updated: 79 symbols                               ║
║ Query DB synced                                             ║
╚═════════════════════════════════════════════════════════════╝
```

**Fix:**
1. **Orchestrator** (`main_runners.py:run_flow_monitor`): Draw pre-market intro box (after the 9:15 wait completes, before calling `run_pre_market()`). Draw success box from return dict after it returns. Add two blank lines before/after the 9:30 AM wait message.
2. **FM pre-market** (`fm_main.py:run_pre_market`): Convert kept lines to `beautiful_log()` with appropriate levels ('info' for context, 'success' for results). Add `── Step N/3: Name ──` headers before each sub-task (plain `print()` — decorative). Suppress the duplicate coordinator summary lines (the indented ones) — the strategy's detailed versions are more informative. Reorder: resolution → sentiment → sync (see P-023).
3. **FM alert resolver** (`fm_alert_resolver.py`): Demote the `ALERT RESOLUTION DIAGNOSTIC` block and all batch-progress lines to `logging.debug()`. Remove `FlowMonitorStorage initialized` line or demote to debug.
4. **DB backup resolution sync** (`db_backup.py`): Suppress the `======` decorated block and the `db_backup` named logger line when called for resolution sync. The coordinator's `beautiful_log("Pre-market updates synced...")` is sufficient.
5. **FM watchlist/sentiment**: Suppress duplicate sentiment lines; keep the detailed strategy result via `beautiful_log`.

**Depends on:** P-023 (sync reordering)
**Related:** P-023 (operational change), this item (visual change) — can be implemented together
**Cross-references:**
- **P-006 (PARTIAL)**: Remaining subprocess formatters for metadata/db_backup still needed for their `logging.info()` lines, but less critical — key user-facing lines can use `beautiful_log()` directly, bypassing formatter config entirely.
- **Future FM items**: Same `beautiful_log` pattern will apply to market hours and post-market output (items TBD as we review those sections).
- **Future strategy modules**: Any new strategy can `from tools.log_utils import beautiful_log` — no formatter plumbing needed.
**Status:** `DONE` — Analyst session, 2026-02-19. Implemented with P-023. Orchestrator (`main_runners.py`) draws intro box and completion box around `run_pre_market()`. FM pre-market (`fm_main.py`) restructured with `_step_header()` for fixed-width 60-char step separators, `beautiful_log()` for milestones. Alert resolver diagnostics demoted to `logging.debug()`. DB backup sync print decorations deleted. `beautiful_log` imported at module level in `fm_main.py`.

### P-023: Move pre-market sync to after sentiment, extend scope
**Location:** `strategies/flow_monitor/fm_main.py` — `run_pre_market()`, `data/health/db_backup.py` — `sync_resolutions()`
**Severity:** Operational (data freshness gap)
**Problem:** The current pre-market order is: (1) resolve alerts → (2) sync resolutions to query DB → (3) update watchlist sentiment. The sync happens *before* sentiment, so the 79 watchlist label updates (BUILDING/CLOSING/NEUTRAL) written to `flow_watchlist_daily` in datalake.db don't reach datalake_query.db until the evening sync at ~5:45 PM — an 8+ hour gap.
**Fix:**
1. **Reorder**: resolution → sentiment → sync (sync becomes the final pre-market step)
2. **Extend sync scope**: The current `--sync-resolutions` only syncs `flow_alerts` resolution columns. Extend it to also sync `flow_watchlist_daily` rows updated during pre-market (sentiment labels, resolution-derived fields). This keeps it targeted (not a full DB sync) but covers all pre-market writes.
3. **Update return dict**: Sync result should reflect the broader scope (rows from both tables).
**Note:** Out of scope for the console output refactor, but simple enough to bundle with P-022 since both touch `run_pre_market()`.
**Status:** `DONE` — Analyst session, 2026-02-19. Reordered `run_pre_market()` to Resolution → Sentiment → Sync. Renamed `sync_alert_resolutions()` → `sync_pre_market_updates()` in `db_backup.py` (alias preserved). Extended sync to also sync `flow_watchlist_daily` sentiment columns (`alert_sentiment`, `building_alerts_count`, `closing_alerts_count`). Function now returns dict with per-table counts. CLI `--sync-resolutions` path updated to handle dict return. Return dict from `run_pre_market()` now includes `sync` sub_task.

### P-024: Flow Monitor Market Hours intro box
**Location:** `strategies/flow_monitor/fm_main.py` — `run_market_hours()`, early in function before first cycle
**Severity:** Visual (missing context)
**Problem:** When market hours start, the system dumps 5 diagnostic init lines (`FlowMonitorStorage initialized`, `FM Collector initialized`, `FM Analyzer initialized`, `FM Alerts initialized`) that describe components in developer language, then jumps straight into `=== Cycle 1 ===`. There's no user-facing explanation of what the Flow Monitor market hours engine actually does, how cycles work, or what the components are for.
**Fix:** Add a `create_status_box()` intro box that displays once at market hours startup (not between cycles). This replaces the diagnostic init lines, which should be demoted to `logging.debug()`.

**Draft structure (refine with Ben before implementing):**
```
╔══════════════════════════════════════════════════════════════════════════╗
║ 🔍 FLOW MONITOR — MARKET HOURS ENGINE                                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║ Real-time monitoring to detect large relative changes in option activity. ║
║ Runs continuous cycles identified by scan_timestamp.                     ║
║ Cycles are intended to be quick (< 30 min) to identify bursts.          ║
║ Runs continuously from market open (9:30 AM) to close (4:00 PM).        ║
║                                                                          ║
║ Universe: [source name] with [N] symbols.                                ║
║                                                                          ║
║ CYCLE: Collect → Analyze → Alert → Watchlist → News → Sync → Repeat     ║
║                                                                          ║
║ 📡 Collector                                                             ║
║   [Strike filter, DTE filter, what it captures — verify from config]     ║
║                                                                          ║
║ 🔬 Analyzer (Unified Algorithm)                                          ║
║   [Algorithm details, scoring factors, regime classification — verify]   ║
║                                                                          ║
║ 🚨 Alerts                                                                ║
║   [Score thresholds, delta threshold, ETF exclusion — verify]            ║
║                                                                          ║
║ 📋 Watchlist                                                             ║
║   [Watchlist creation rules, tracking purpose — verify]                  ║
║                                                                          ║
║ 📰 News Sentiment                                                        ║
║   [API source, budget, scoring method, labels — verify]                  ║
║                                                                          ║
║ 🔄 DB Sync                                                               ║
║   [Quick-sync purpose and target — verify]                               ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

**Intent:** This box should be detailed and technical — it's a personal-use reference, not marketing copy. The implementing analyst should research the actual parameters from config and code (fm_collector.py, fm_analyzer.py, fm_alerts.py, fm_config.py, news_sentiment.py), fill in real values (strike range, DTE window, scoring algorithm details, alert thresholds, delta filters, etc.), and **confirm the final content with Ben before committing**. Ben wants to review the layout and discuss what else could be added to make it maximally useful as a runtime reference.

**Also suppress:** The 5 diagnostic init lines (`FlowMonitorStorage initialized` × 2, `FM Collector initialized`, `FM Analyzer initialized`, `FM Alerts initialized`) — demote to `logging.debug()`. The intro box covers this information in user-facing language.
**Status:** `DONE` — Analyst session, 2026-02-19. Added `create_status_box()` intro box in `run_market_hours()` after component init, before cycle loop. Content reviewed and approved by Ben — 42 content lines covering all 7 cycle phases with real config values. Universe line dynamic (`len(symbols)`). Demoted 5 init lines to `logging.debug()` across fm_storage.py:52, fm_collector.py:112, fm_analyzer.py:87, fm_alerts.py:75 (FlowMonitorStorage ×2 since it's instantiated twice). Also demoted stray "Fetching quotes for N symbols" in tradier_api.py:455 to debug (redundant with collector's "Fetching underlying prices" beautiful_log).

### P-025: FM market hours per-cycle cleanup — collection through analyzer handoff
**Location:** `strategies/flow_monitor/fm_main.py` (`run_market_hours()`), `fm_collector.py`, `fm_analyzer.py`
**Severity:** Visual (noise + formatting + phase transitions)
**Problem:** Each cycle has diagnostic noise at the start, no visual separation between collection and analysis phases, redundant validation lines, and a bare `Collection complete` duplicate. The cycle needs clear phase framing with consistent `beautiful_log` for milestones.

**Suppress (demote to `logging.debug()`):**
- `Market is OPEN` — obvious during market hours
- `Collecting data for 746 symbols` — redundant with cycle header
- `✓ No duplicates found in batch - proceeding with 101300 contracts` — redundant with validation line above
- `Collection complete` (bare) — redundant with the detailed `Collection complete (Ns)` line
- `Starting unified algorithm analysis for scan: ... (live production mode)` — replaced by clearer beautiful_log lines

**Upgrade cycle header** from `=== Cycle 1 | 09:30:01 | 746 symbols ===` to `── Cycle 1 | 09:30:01 | 746 symbols ──` (consistent `──` separator style).

**Target output — full cycle collection through analyzer start:**
```
── Cycle 1 | 09:30:01 | 746 symbols ────────────────────────────

🔍 09:30:01 - Starting FM Collector
🔍 09:30:01 - Scan timestamp: 2026-02-19 09:30:01
🔍 09:30:01 - Fetching underlying prices for 746 symbols
🔍 09:30:02 - Fetching quotes for 746 symbols
✅ 09:30:16 - Prices received for 746 symbols
✅ 09:30:16 - Symbol list validated: 746 unique, no duplicates

09:30:16 - Fetching option expirations for A
09:30:18 - Option chains collected for A — 42 contracts
...
09:49:49 - Option chains collected for JBLU — 52 contracts
09:49:52 - Option chains collected for JETS — 185 contracts

✅ 09:49:52 - Batch validated: 101,300 contracts, no duplicates
✅ 09:52:53 - Stored 101,300 contracts (scan: 09:30:01)
✅ 09:52:53 - Collection complete (1371.9s)
```

**Pattern:** Each cycle sub-phase gets a `🔍 Starting FM [Component]` header via `beautiful_log('info')`. Milestone results (validation, storage, completion) use `beautiful_log('success')`. Per-symbol/per-contract progress stays as `logging.info()`. Blank lines separate the three zones: setup → per-symbol heartbeat → milestones/handoff.
**Status:** `DONE` — Analyst session, 2026-02-19. Cycle header changed to `──` fixed-width 60-char style. Collector: `beautiful_log` for Starting/Scan timestamp/Fetching prices/Prices received/Symbol validated/Batch validated/Stored. Demoted to debug: Market is OPEN, Collecting data for N symbols, bare Collection complete, No duplicates in batch (fm_storage.py). Analyzer: demoted "Starting unified algorithm" to debug, added `beautiful_log('info')` "Starting FM Analyzer" in fm_main.py. Added `beautiful_log('info')` "Starting FM Alerts" before alerts phase. Added `print('')` after symbol validation and before analyzer for visual separation. Store line moved after `_store_options()` and converted to beautiful_log('success').

### P-026: FM Analyzer output cleanup — suppress diagnostics, keep stats block
**Location:** `strategies/flow_monitor/fm_analyzer.py` (unified algorithm analysis)
**Severity:** Visual (noise + debug leaks)
**Problem:** Analyzer dumps ~25 lines including DEBUG-level calls, redundant DB confirmation, a full summary header block, and internal algorithm stats. Console should show the key stats a user needs to assess the cycle while keeping full detail in the text log.

**Suppress (demote to `logging.debug()` or remove from console):**
- `DEBUG: About to call _get_all_symbol_daily_totals_for_scan...` — literal debug, should not be INFO
- `DEBUG: _get_all_symbol_daily_totals_for_scan completed, found 625 symbols` — same
- `Retrieved 101300 contracts for unified analysis` — redundant (contract count already shown in collection and analyzer intro)
- `Batch update completed: 101300 rows affected` — forensic DB operation
- `Successfully updated 101300 contracts` — redundant with "Contracts updated"
- `UNIFIED ALGORITHM ANALYSIS SUMMARY` header — not needed when we're keeping select lines
- `Enhanced statistics tracking:` header + `Early day fallbacks: 7237` + `Running total used: 12193` — internal algorithm diagnostics
- `Smart money alerts (1.5+): 0` — zero-value noise
- `Starting unified algorithm analysis for scan: ... (live production mode)` — replaced by beautiful_log lines

**Target output (collection end → analyzer → alerts handoff):**
```
✅ 09:52:53 - Collection complete (1371.9s)

🔍 09:52:53 - Starting FM Analyzer
🔍 09:52:53 - Analyzing 101,300 contracts for significant flow activity
ℹ️ 09:52:55 - Market regime: normal

09:53:04 - Contracts updated: 101,300
09:53:04 - Missing baselines: 187
09:53:04 - Data quality issues detected:
09:53:04 -   Missing price data: 76
09:53:04 -   Bad tick data (ask < bid): 0
09:53:04 -   Total data quality warnings: 76
09:53:04 - Premium filtered: 101,066
09:53:04 - Volume filtered: 101,176
09:53:04 - High conviction alerts (8.0+): 2
09:53:04 - Unified alerts (6.0+): 10
09:53:04 - Total analysis time: 10.82 seconds
09:53:04 - Total significant flows detected: 12

🔍 09:53:04 - Starting FM Alerts
```

**Notes for implementing analyst:**
- Market regime gets `beautiful_log('info')` — important one-liner that colors the whole cycle, should be scannable.
- Stats block stays as `logging.info()` — cohesive block, don't mix beautiful_log within it.
- **Discuss with Ben**: Premium/volume filter lines currently show how many were filtered OUT. Ben wants the inverse added — how many PASSED. Proposed format: `Premium filter: 234 passed (101,066 filtered)`. Discuss exact wording.
- **Discuss with Ben**: Missing baselines and data quality block kept for now (building baseline intuition). May be tightened later once normal ranges are established.
**Status:** `DONE` — Analyst session, 2026-02-19. Demoted to debug: "Retrieved N contracts" (line 164), two "DEBUG:" leaked lines (167, 169), "Successfully updated N contracts" (264). Removed from summary: "UNIFIED ALGORITHM ANALYSIS SUMMARY" header, "Contracts processed" (redundant with "updated"), "Enhanced statistics tracking" block (early_day_fallbacks, running_total_used → debug). Market regime → `beautiful_log('info')`. Added `beautiful_log('info')` "Analyzing N contracts for significant flow activity". Premium/volume filters now show passed counts: "Premium filter: 234 passed (101,066 filtered)". Smart money alerts line suppressed when 0. "No significant institutional flows" line removed (zero-value). "Batch update completed" in fm_storage.py demoted to debug (lines 476, 487).

### P-027: FM Alerts output cleanup — truncation fix, timestamp dedup, suppress redundancy
**Location:** `strategies/flow_monitor/fm_alerts.py`, `fm_alert_display.py` (or wherever alert formatting lives)
**Severity:** Visual (truncation bug + noise + redundant summary)
**Problem:** Alert display truncates the scoring breakdown (`unified_score: 6.6 (prem=$1506160, vo...`), the `🚨 FLOW MONITOR ALERTS` header has a double timestamp (formatter adds one + message contains a hardcoded one), "alerts sent" language is stale (nothing gets "sent" anymore — they're saved), and the ALERT PROCESSING SUMMARY block repeats data already shown.

**Fix:**

1. **Alert truncation**: Ensure full alert line is displayed without `...` cutoff. Check if this is a logging line-length limit, string formatting truncation, or console width issue. Full scoring breakdown should be visible.

2. **Double timestamp**: The `🚨 FLOW MONITOR ALERTS - 09:53:05` line hardcodes a timestamp in the message. Remove the hardcoded timestamp from the message string. Convert to `beautiful_log`: `🚨 09:53:05 - FLOW MONITOR ALERTS`. (Use 'warning' level or whichever maps to 🚨 — may need to add a level to the emoji_map.)

3. **"sent" → "saved"**: Change `📊 SUMMARY: 2 alerts sent` to `📊 SUMMARY: 2 alerts saved (0 HIGH, 2 MEDIUM, 0 LOW) to flow_alerts`. Adds table name for context.

4. **Suppress (text-log only):**
   - `Updating 5 filtered contracts with filter reasons` — forensic DB write
   - `Processing 2 unique alerts after delta filter` — redundant with filter line
   - `ALERT PROCESSING SUMMARY` block (all 6 lines: Candidates found, Filters applied, Alerts sent, Console notifications, Email notifications, Database saves) — redundant with kept lines

**Target output:**
```
🔍 09:53:04 - Starting FM Alerts
09:53:04 - Processing alerts for scan: 2026-02-19 09:30:01
09:53:04 - Found 7 alert candidates from scan
09:53:04 - Filters applied: 2 passed, 5 filtered (4 ETFs, 1 delta)

🚨 09:53:05 - FLOW MONITOR ALERTS

09:53:05 - 🟡 MEDIUM ALERTS (Score 6.0-7.9)
09:53:05 - SMCI [LAR] $32.0 calls (8d) | Vol: 10,720 (21.4x) | OI: 2,996 | V/OI: 3.6 | Last: $1.36 | Underlying: $31.63 | IV: 68% | Score: 6.7 | Flow: 17.1% | unified_score: 6.6 (prem=$1506160, vol_ratio=21.4x, oi=2996, delta=0.62)
09:53:05 - OXY [LAR] $50.0 calls (29d) | Vol: 2,743 (5.5x) | OI: 17,614 | V/OI: 0.2 | Last: $2.94 | Underlying: $50.10 | IV: 37% | Score: 6.1 | Flow: 7.6% | unified_score: 6.1 (prem=$806442, vol_ratio=5.5x, oi=17614, delta=0.51)

📊 09:53:05 - 2 alerts saved (0 HIGH, 2 MEDIUM, 0 LOW) to flow_alerts
09:53:05 - Complete alert saved for SMCI 32.0 with score 6.65
09:53:05 - Complete alert saved for OXY 50.0 with score 6.10
09:53:05 - Alert persistence complete: 2 saved, 0 failures

09:53:32 - Watchlist updated: 2 created, 0 updated from 2 alerts
```

**Logging type assignments:**
- `🔍 Starting FM Alerts` — `beautiful_log('info')` — phase header
- `Processing alerts for scan` / `Found 7 candidates` / `Filters applied` — `logging.info()` — funnel stats block
- `🚨 FLOW MONITOR ALERTS` — `beautiful_log` (remove hardcoded timestamp) — section header
- `🟡 MEDIUM ALERTS` + per-alert lines — `logging.info()` — alert display content
- `📊 2 alerts saved...` — `logging.info()` — summary (emoji in message text)
- Per-save confirmations / persistence complete — `logging.info()` — forensic
- `Watchlist updated` — `logging.info()` — transition line (watchlist cleanup covered in next item)

**Note for implementing analyst:** The alert lines (SMCI, OXY) are the core product of Flow Monitor. Full, untruncated display is non-negotiable. Investigate the truncation source — could be string slicing in the formatter, a `%.200s` format spec, or a logging handler maxBytes setting.
**Status:** `DONE` — Analyst session, 2026-02-19. Truncation source was `_format_console_alert()` line 436: `reason[:37] + "..."` hard-truncated `alert_reason` at 40 chars. Removed truncation for console (email digest truncation preserved). Double timestamp fixed: replaced `logging.info("🚨 FLOW MONITOR ALERTS - {}".format(current_time))` with `beautiful_log("🚨 FLOW MONITOR ALERTS", level='warning')` — stutter prevention handles the emoji. "alerts sent" → "alerts saved ... to flow_alerts". Demoted to debug: "Processing N unique alerts after delta filter", "Updating N filtered contracts", "Saving N alerts to flow_alerts table", entire `_log_alert_summary()` body (ALERT PROCESSING SUMMARY block). Promoted per-save confirmations from debug to info with reworded format: "Complete alert saved for {symbol} {strike} with score {score:.2f}".

### P-028: FM Watchlist / News Enrichment / Dip Detection — cleanup and formatting
**Location:** `strategies/flow_monitor/fm_main.py` (cycle loop), `fm_watchlist.py`, `tools/news_sentiment.py`, `core/alphavantage_api.py`
**Severity:** Visual (duplicate lines, format inconsistencies, missing phase headers)
**Problem:** Three post-alert cycle steps (watchlist, news, dip detection) have duplicate log lines from multiple layers, a format-breaking `[INFO]` line from the AV client, and no phase headers to frame them. Also, the full cycle is Collect → Analyze → Alert → Watchlist → News → **Dip Detection** → Sync — dip detection was missing from our cycle documentation.

**Suppress:**
- `Fetching news for SMCI (limit=50)` — duplicate of the caller's fetch announcement (API layer echo)
- `(date=2026-02-19)` suffix on enrichment result lines — today's date, obvious
- `News enrichment batch: 2 enriched, 0 skipped, 0 failed, budget_exhausted=False` — duplicate summary from utility layer
- `News enrichment: 2 enriched, 0 skipped, 0 failed` — replaced by beautiful_log completion line
- `✅ Email sent successfully to owner@example.com` — no timestamp, and email address shouldn't appear every cycle. The `Email notification sent for 3 dip(s)` line covers it.

**Fix:**
1. **Add phase headers**: `🔍 Starting FM Watchlist`, `🔍 Starting FM News Enrichment`, `🔍 Starting FM Dip Detection` — beautiful_log('info'), consistent with P-025/P-026 pattern.
2. **Watchlist line**: Add table name — `Watchlist updated: 2 created, 0 updated from 2 alerts in flow_watchlist_daily`. Consider whether additional detail lines make sense (discuss with Ben).
3. **AV counter reset**: Keep — first-cycle-only, useful to know budget is fresh. Fix the `[INFO]` format to proper `beautiful_log` or `logging.info`: e.g. `ℹ️ 09:53:33 - Alpha Vantage daily request counter reset (25 calls available)` (include budget count if accessible).
4. **News completion**: `beautiful_log('success')` — `✅ News enrichment complete: 2 enriched, 0 skipped, 0 failed`.
5. **Dip email**: `beautiful_log('success')` — `✅ Email notification sent for 3 dip(s)`. Fix the bare `print()` in the email module that produces the timestamp-less `✅ Email sent...` line.

**Target output:**
```
🔍 09:53:04 - Starting FM Watchlist
09:53:32 - Watchlist updated: 2 created, 0 updated from 2 alerts in flow_watchlist_daily

🔍 09:53:33 - Starting FM News Enrichment
ℹ️ 09:53:33 - Alpha Vantage daily request counter reset (25 calls available)
09:53:33 - Fetching news for SMCI (lookback: 3 days, limit: 50)
09:53:33 - Retrieved 18 articles for SMCI
09:53:33 - News enrichment for SMCI: score=0.04, label='Bullish 6/Bearish 4/Neutral 8', articles=18
09:53:33 - Fetching news for OXY (lookback: 3 days, limit: 50)
09:53:45 - Retrieved 22 articles for OXY
09:53:45 - News enrichment for OXY: score=0.24, label='Bullish 13/Bearish 4/Neutral 5', articles=22
✅ 09:53:45 - News enrichment complete: 2 enriched, 0 skipped, 0 failed

🔍 09:53:47 - Starting FM Dip Detection
09:53:47 - Dip detected: VST (CALL) via zscore - $170.59->$168.25 (-1.37%)
09:53:47 - Dip detected: PLTR (CALL) via zscore - $135.60->$132.37 (-2.38%)
09:53:47 - Dip detected: SOFI (CALL) via zscore - $19.75->$19.27 (-2.43%)
09:53:47 - Buy-the-dip opportunities: 3 detected (zscore: 3, fallback: 0)
✅ 09:53:48 - Email notification sent for 3 dip(s)
```

**Note:** The AV counter reset line only appears on cycle 1. On subsequent cycles, news enrichment goes straight to fetching (or skips entirely if no new watchlist entries were created). Per-symbol news lines only fire for NEW watchlist entries (0-5 symbols typically, not 746).

**Also update P-024:** Add Dip Detection to the intro box cycle list and component descriptions. Full cycle is: **Collect → Analyze → Alert → Watchlist → News → Dip Detection → Sync → Repeat**.
**Status:** `DONE` — Analyst session, 2026-02-19. Phase headers added in fm_main.py: `beautiful_log("Starting FM Watchlist/News Enrichment/Dip Detection", 'info')`. News header+completion conditional on `created_symbols` non-empty; completion line also gated on enriched>0 or failed>0. Watchlist line appended "in flow_watchlist_daily". Dip email `logging.info` → `beautiful_log('success')` in fm_watchlist.py. Suppressed: AV API layer "Fetching news" echo → debug (alphavantage_api.py:484), batch summary → debug (news_sentiment.py:581), `(date=...)` suffix removed (news_sentiment.py:502), bare `print("✅ Email sent to...")` → `logging.debug()` (email_notifier.py:112, added `import logging`). AV counter reset: `print("[INFO]...")` → `logging.info()` with budget count (alphavantage_api.py:94, legacy comment removed). P-024 intro box already had Dip Detection (lines 1035, 1061-1065) — no change needed.

### P-029: FM Quick Sync — add phase header and progress logging
**Location:** `strategies/flow_monitor/fm_main.py` (cycle loop, quick-sync call), quick-sync implementation
**Severity:** Visual (missing phase header, no progress during 60s+ operation)
**Problem:** Quick sync starts silently and produces only a completion line. During normal runs (~60s) this is fine, but when the sync takes longer there's no visibility into progress or where it might be hanging. No phase header to match the pattern established by P-025/P-026/P-027/P-028.

**Fix:**
1. **Phase header**: `🔍 Starting Quick Sync` — beautiful_log('info'), consistent with other cycle phases.
2. **Context line**: Brief info about what's being synced — tables, row count target. Plain `logging.info()`.
3. **Progress logging**: Add periodic progress during the sync. Interval TBD — discuss with Ben based on how the sync works internally (batch copy? page backup? single statement?). Rough target: ~5 progress lines for a typical 60s sync.
4. **Completion line stays**: `Quick-sync completed: 101,383 rows in 60.8s` — already good.

**Target output:**
```
🔍 09:53:49 - Starting Quick Sync
09:53:49 - Targeted quick-sync: [table(s)] ([row count] rows)
[progress lines at TBD interval]
✅ 09:54:49 - Quick-sync completed: 101,383 rows in 60.8s
```

**Note for implementing analyst:** Also consider: should the `✅ Cycle 1 complete - Performance Breakdown:` line be converted to beautiful_log('success') for consistency? The sub-lines (📊 Collection, 🔍 Analysis, etc.) stay as logging.info() — they're content in a block. The cycle completion header is a milestone line that would benefit from the emoji-before-timestamp format.

**Performance breakdown and coffee break:** No changes needed — both look correct per spec.

### P-032: Quick Sync progress logging during operation
**Location:** `data/health/db_backup.py` (`create_quick_sync()` or equivalent), `strategies/flow_monitor/fm_main.py` (`run_quick_sync()`)
**Severity:** Visual (no visibility during 60s+ operation)
**Problem:** Quick sync runs as a subprocess with `capture_output=True`. Internal progress (`print()` lines per table — watermark, row counts, insert status) is captured but not visible. During normal ~60s runs this is tolerable, but longer syncs give no indication of progress or where things might be hanging.
**Fix (two approaches, pick one):**
1. **Switch to streaming subprocess**: Use `_run_streaming_subprocess()` pattern from `main_runners.py`. Requires cleaning up the subprocess's internal `print()` output to match our design language (currently has `===` banners and per-step diagnostics).
2. **Refactor to in-process call**: Make `create_quick_sync()` callable directly from `fm_main.py` instead of via subprocess. Enables `beautiful_log` progress and eliminates the subprocess boundary entirely.

Either approach is a larger change than the P-029 phase header/completion fix. Deferred until quick sync duration becomes a pain point or we revisit the subprocess architecture.
**Target:** ~5 progress lines for a typical 60s sync (e.g., per-table progress or row count milestones).
**Status:** `DONE` — Analyst session, 2026-02-19. Phase header added at cycle loop call site: `beautiful_log("Starting Quick Sync", 'info')`. Context line added in `run_quick_sync()`: `logging.info("Syncing flow_alerts, flow_options_scans, flow_watchlist_daily to query database")`. Completion lines upgraded from `logging.info` to `beautiful_log('success')`. Progress logging deferred — subprocess boundary makes streaming impractical for ~60s of visibility; header+context+completion is sufficient.

### P-030: Extend expiration cache TTL from 1 hour to 8 hours
**Location:** `core/tradier_api.py:482` — `get_option_expirations(symbol, max_age_seconds=3600)`
**Severity:** Performance (unnecessary API calls + ~200s per affected cycle)
**Problem:** Expiration dates are cached with a 1-hour TTL. Since expirations are set by the exchange and never change intraday, the cache expires mid-day and forces ~746 redundant API calls on the next cycle, adding ~200 seconds to collection time. This happens 5-6 times per trading day for zero new information.
**Fix:** Change `max_age_seconds=3600` to `max_age_seconds=28800` (8 hours). Cache fills on Cycle 1 at market open and stays warm for the entire trading day (9:30 AM - 4:00 PM = 6.5 hours). Fresh data every morning automatically.
**Note:** Out of scope for the console output refactor, but a one-line fix with immediate performance benefit (~1000s saved per day across 5-6 cache-miss cycles). Also note in P-024 intro box: *"Expiration dates cached for the trading day — first cycle fetches per symbol, subsequent cycles use cache."*
**Status:** `DONE` — Analyst session, 2026-02-19. Changed `max_age_seconds=3600` to `max_age_seconds=28800` at `tradier_api.py:482`.

### P-031: Performance summary should appear every cycle, not every 10th
**Location:** `strategies/flow_monitor/fm_main.py:1242`
**Severity:** Spec mismatch (feature works, wrong frequency)
**Problem:** The running performance summary (`📈 PERFORMANCE SUMMARY`) only appears every 10th cycle (`cycle % 10 == 0 and len(stats.cycle_times) >= 10`). A typical trading day has ~15-20 cycles, so this fires once or twice. Intent was to show running averages on every cycle from Cycle 2 onwards so performance trends are visible throughout the day.
**Fix:** Change the condition from `if cycle % 10 == 0 and len(stats.cycle_times) >= 10:` to `if cycle >= 2 and len(stats.cycle_times) >= 2:`. The summary block (average cycle, collection, analysis, alerts, slowest, fastest) appears after every cycle starting from Cycle 2.
**Also update VISUAL_DESIGN_REFERENCE.md:** The spec shows the summary at Cycle 10 and 20 only. Update to reflect the new frequency.
**Status:** `DONE` — Analyst session, 2026-02-19. Changed condition at `fm_main.py:1242` from `cycle % 10 == 0 and len(stats.cycle_times) >= 10` to `cycle >= 2 and len(stats.cycle_times) >= 2`.

### P-033: FM cycle end-of-cycle cleanup — duplicates, zero-value noise, dangling headers, spacing
**Location:** `strategies/flow_monitor/fm_main.py` (cycle loop), `fm_collector.py`, `fm_analyzer.py`, `fm_alerts.py`, `fm_storage.py`, `fm_watchlist.py`
**Severity:** Visual (duplicates, noise, inconsistent conditional output, spacing)
**Problem:** End-of-cycle output has several issues found during live Cycle 1 review:

1. **Duplicate storage line**: `Stored 106674 option contracts with scan_timestamp...` (unformatted, from storage layer) immediately followed by `✅ Stored 106,674 contracts in 438.8s...` (formatted beautiful_log from collector). Storage layer line should be debug.

2. **Zero-value data quality line**: `Bad tick data (ask < bid): 0` prints even when zero. The entire `Data quality issues detected:` sub-block should suppress zero-value items. If ALL sub-items are zero, skip the header too.

3. **Double "no alerts" message**: `Found 0 alert candidates from scan` then `No alert candidates found for scan` — same fact twice. Keep the funnel stat (`Found 0 candidates`), suppress the narrative duplicate.

4. **Watchlist header with no result**: `Starting FM Watchlist` header appears, then silence — no result line when there are 0 alerts to process. News enrichment is already conditional (header only shows when `created_symbols` is non-empty), but watchlist and dip detection headers are unconditional.

5. **Dip detection header with cache noise**: `Starting FM Dip Detection` header appears, then only `Cache cleanup: purged 8 stale files (>24h old)` — housekeeping noise, should be debug. No outcome line for actual dip detection results.

6. **Missing line breaks**: No blank line before `Starting FM Alerts` (analyzer stats block runs directly into alerts header). No blank line before `✅ Cycle N complete - Performance Breakdown`.

7. **Cycle complete line format**: `15:16:40 - ✅ Cycle 1 complete` has emoji *in* the message (logging.info), giving `timestamp - ✅ message`. Should be `beautiful_log('success')` for `✅ timestamp - message` consistency with all other milestones.

**Fix:**

1. **Storage duplicate**: Demote the raw storage confirmation (`fm_storage.py` — the `Stored N option contracts with scan_timestamp...` line) to `logging.debug()`. The collector's beautiful_log line is the single source of truth.

2. **Data quality zero-value**: In `fm_analyzer.py` `_log_analysis_summary()`, make each data quality sub-item conditional on > 0. If no sub-items are non-zero, skip the `Data quality issues detected:` header entirely.

3. **Double no-alerts**: In `fm_alerts.py`, suppress the `No alert candidates found for scan` line. The `Found 0 alert candidates` funnel stat is sufficient.

4. **Watchlist + Dip conditional output**: Two options (discuss with Ben):
   - **Option A (suppress headers)**: Make watchlist and dip detection headers conditional, same pattern as news enrichment. Header only shows when there's work to do. Silence = nothing happened.
   - **Option B (add "nothing to do" lines)**: Keep headers unconditional, add brief result lines: `No new watchlist entries this cycle` and `No dip opportunities detected`. Headers always show so the user sees every phase accounted for.

   **Recommendation:** Option B — keeping headers visible makes it clear the system checked and found nothing, rather than leaving ambiguity about whether the step ran at all. This matches the alerts pattern (`Found 0 candidates`). News enrichment is different because it depends on a prerequisite (new symbols); watchlist and dip detection always run.

5. **Cache cleanup**: Demote to `logging.debug()` in `fm_watchlist.py`. This is housekeeping, not dip detection output.

6. **Line breaks**: Add `print("")` before `beautiful_log("Starting FM Alerts")` in `fm_main.py` cycle loop (after analyzer finishes). Add `print("")` before the cycle complete / performance breakdown block.

7. **Cycle complete format**: Convert the `logging.info("✅ Cycle N complete - Performance Breakdown:")` line to `beautiful_log("Cycle {} complete - Performance Breakdown:".format(cycle), 'success')` in `fm_main.py`.

**Target output (zero-alert cycle):**
```
✅ 15:04:33 - Stored 106,674 contracts in 438.8s (scan: 2026-02-19 14:40:25)
✅ 15:04:34 - Collection complete (1448.9s — API: 1010.1s + DB Write: 438.8s)

ℹ️ 15:04:34 - Starting FM Analyzer
ℹ️ 15:04:35 - Analyzing 106,674 contracts for significant flow activity
ℹ️ 15:06:20 - Market regime: normal

15:13:30 - Contracts updated: 106,674
15:13:30 - Missing baselines: 212
15:13:30 - Data quality issues detected:
15:13:30 -   Missing price data: 60
15:13:30 - Premium filter: 2,899 passed (103,775 filtered)
15:13:30 - Volume filter: 40 passed (106,634 filtered)
15:13:30 - High conviction alerts (8.0+): 13
15:13:30 - Unified alerts (6.0+): 28
15:13:30 - Total analysis time: 536.72 seconds
15:13:30 - Total significant flows detected: 41

ℹ️ 15:13:30 - Starting FM Alerts
15:13:30 - Processing alerts for scan: 2026-02-19 14:40:25
15:13:32 - Found 0 alert candidates from scan

ℹ️ 15:13:32 - Starting FM Watchlist
15:13:32 - No new watchlist entries this cycle

ℹ️ 15:14:22 - Starting FM Dip Detection
15:14:23 - No dip opportunities detected

ℹ️ 15:14:25 - Starting Quick Sync
15:14:25 - Syncing flow_alerts, flow_options_scans, flow_watchlist_daily to query database
✅ 15:16:40 - Quick-sync completed: 106,766 rows in 135.1s

✅ 15:16:40 - Cycle 1 complete - Performance Breakdown:
15:16:40 -    📊 Collection: 1448.9s (API: 1010.1s + DB Write: 438.8s)
15:16:40 -    🔍 Analysis: 536.9s
15:16:40 -    🚨 Alerts: 2.1s
15:16:40 -    🎯 Watchlist: 52.1s
15:16:40 -    🔄 DB Sync: 135.1s (106,766 rows)
15:16:40 -    ⏱️ Total: 2175.1s
```

**Notes for implementing analyst:**
- For fix #4, go with Option B (keep headers, add "nothing to do" lines) unless Ben says otherwise.
- The "No new watchlist entries" line comes from `fm_watchlist.py` — add a log when `update_daily_watchlist()` creates 0 entries.
- The "No dip opportunities" line comes from `fm_watchlist.py` `update_prices_and_detect()` — add a log when no dips found.
- The existing `Watchlist updated: N created, M updated from K alerts` line is already good when there ARE results. This is about the zero case.

**Status:** `DONE` — Analyst session, 2026-02-19. All 7 fixes implemented (Option B for fix #4):
1. Storage duplicate: `fm_storage.py:274-276` — both raw storage confirmation and DB write breakdown demoted to `logging.debug()`.
2. Data quality zero-value: `fm_analyzer.py:1230-1236` — each sub-item (`missing_price_data`, `bad_tick_data`) now conditional on > 0. "Total data quality warnings" line removed (redundant with header).
3. Double no-alerts: `fm_alerts.py:100` — "No alert candidates found for scan" demoted to `logging.debug()`. Funnel stat "Found 0 candidates" (line 220) is the single source of truth.
4. Watchlist + Dip "nothing to do" lines: `fm_watchlist.py:216-220` — when 0 created and 0 updated, logs "No new watchlist entries this cycle" instead of verbose zeros. `fm_watchlist.py:603-604` — added else branch: "No dip opportunities detected" when dips_detected == 0.
5. Cache cleanup: `core/tradier_api.py:100` — demoted to `logging.debug()` (was misattributed to fm_watchlist.py in problem description; actual source is Tradier client init).
6. Line breaks: `fm_main.py:1168` — `print("")` before "Starting FM Alerts". `fm_main.py:1327` — `print("")` before cycle complete performance breakdown.
7. Cycle complete format: `fm_main.py:1328` — converted from `logging.info("✅ Cycle N complete...")` to `beautiful_log("Cycle N complete...", 'success')` for consistent `✅ HH:MM:SS - message` format.

### P-034: FM cycle output — duplicate logging, diagnostic noise, market close format
**Location:** `fm_storage.py`, `fm_alerts.py`, `tools/news_sentiment.py`, `core/alphavantage_api.py`, `fm_main.py`, `main_runners.py`, `fm_watchlist.py`
**Severity:** Visual (duplicates, diagnostic leaks, format inconsistency) + minor logic investigation
**Problem:** Live Cycle 1 review with alert activity revealed several issues:

1. **Duplicate alert save confirmations**: `Complete alert saved for DAL 62.5 with score 6.66` appears twice per alert. Root cause identified: two identical `logging.info()` calls — one in `fm_storage.py:389` (storage layer, after `cursor.execute()`) and one in `fm_alerts.py:804` (caller, after `save_alert()` returns True). Not a double-save — just double-logging.

2. **Blank line with timestamp in alerts**: `16:15:43 -` (blank logging.info between alert display and SUMMARY line). Should be `print("")` for clean decorative spacing, or removed entirely.

3. **AV empty feed diagnostic noise**: When Alpha Vantage returns an empty feed, three diagnostic lines appear on console before the user-facing `No articles returned for OWL`:
   - `Alpha Vantage API returned empty feed - Response structure: 4 total keys, feed=[], items=0`
   - `Empty feed response logged to: E:\options_scanner\logs\av_empty_feed_responses.jsonl`
   - `Alpha Vantage returned EMPTY FEED for OWL: Response keys: [...]`
   All three should be `logging.debug()`. The "No articles returned" line is sufficient for console.

4. **News sentiment line duplicate**: After market close, `ℹ️ News sentiment: 1 symbols enriched across 1 cycles` appears as a standalone beautiful_log line, then the same fact appears inside the session summary box. Remove the standalone line (it's in `main_runners.py:449`).

5. **Market close line format**: `16:25:10 - 🔔 Market closed. Ending market hours pipeline.` is `logging.info()` with emoji in message text (giving `timestamp - 🔔 message`). Should be `beautiful_log` for consistent `🔔 timestamp - message` format.

6. **Dip detection disambiguation**: Two LUV lines appear identical (`LUV (PUT) via zscore - $50.98->$52.20 (+2.39%)`) but are actually for different watchlist entries from different days. The console output doesn't distinguish them. Add the watchlist entry date to disambiguate: `LUV (PUT, entry 02/17) via zscore...` vs `LUV (PUT, entry 02/18) via zscore...`.

7. **FM error/failure logging audit**: News sentiment showed diagnostic noise leaking to console on API failure. Other FM cycle processes (collector API failures, analyzer edge cases, watchlist DB errors, dip detection failures) should be audited for similar diagnostic leaks. Ensure all processes follow the pattern: one clean user-facing line on failure, diagnostics in debug.

**Fix:**
1. **Alert duplicate**: Demote `fm_storage.py:389` `logging.info("Complete alert saved...")` to `logging.debug()`. The caller's log in `fm_alerts.py:804` is the right layer for it.
2. **Blank alert line**: Find the blank `logging.info("")` between alert display and SUMMARY in `fm_alerts.py`, change to `print("")`.
3. **AV diagnostics**: In `tools/news_sentiment.py` and `core/alphavantage_api.py`, demote the three empty-feed diagnostic lines to `logging.debug()`. Keep `No articles returned for {symbol}` at `logging.info()`.
4. **News sentiment duplicate**: Remove `self.beautiful_log("News sentiment: ...")` at `main_runners.py:449`. The session summary box covers it.
5. **Market close format**: In `fm_main.py`, change `logging.info("🔔 Market closed...")` to `beautiful_log("🔔 Market closed. Ending market hours pipeline.")` — stutter prevention will handle the emoji.
6. **Dip disambiguation**: In `fm_watchlist.py` `update_prices_and_detect()`, add entry date to the dip detection log line. Format: `Dip detected: LUV (PUT, entry 02/17) via zscore...`
7. **Error logging audit**: Review `fm_collector.py`, `fm_analyzer.py`, `fm_alerts.py`, `fm_watchlist.py`, `tools/news_sentiment.py`, `core/alphavantage_api.py` for diagnostic lines at INFO/WARNING that should be DEBUG. Ensure each process has a clean failure pattern: one user-facing line, details in debug or text log only. Document findings and fix.

**Also fixed (not in original spec):** Added `print("")` before PERFORMANCE SUMMARY in `fm_main.py:1442` for visual separation from cycle breakdown.

**Status:** `DONE` — 2026-02-19. Sub-items 1-6 complete: (1) fm_storage.py:389 → debug, (2) fm_alerts.py blank lines → print(""), (3) alphavantage_api.py 3 diagnostic lines → debug, (4) main_runners.py standalone news sentiment beautiful_log removed, (5) fm_main.py market close → beautiful_log('warning'), (6) fm_watchlist.py dip log now includes entry date `(PUT, entry 02/17)`. Plus: print("") spacing before PERFORMANCE SUMMARY. Sub-item 7 (error logging audit) split into P-054, P-055, P-056.

### P-035: Enrich Market Hours Session Summary box
**Location:** `main_runners.py` (`_display_session_summary()`), `strategies/flow_monitor/fm_session_stats.py` (`FMSessionStats`)
**Severity:** Content (underutilized data, missing metrics)
**Problem:** The session summary box currently shows only cycle counts, top-level timing (avg/fastest/slowest), and conditional error/news sections. It underutilizes the rich data already in `FMSessionStats` and is missing several useful metrics entirely.

**Data already in FMSessionStats but not displayed:**
- `avg_collection`, `avg_storage` — per-phase average timings
- `avg_analysis`, `avg_analysis_query`, `avg_analysis_scoring`, `avg_analysis_db_write` — analysis sub-breakdowns
- `failed_options.always_failed` — symbols that failed options every cycle

**Data not currently tracked in FMSessionStats (needs new accumulators):**
- Total alerts generated across all cycles (count, by severity)
- Total contracts scanned (sum across cycles)
- Total watchlist entries created / updated
- Total dips detected
- Symbols in universe (constant but useful for the record)
- Market hours time span (first cycle start time → last cycle end time)

**Target output (err on the side of more — trim later if needed):**
```
╔══════════════════════════════════════════════════════════════════╗
║ MARKET HOURS SESSION SUMMARY                                     ║
╠══════════════════════════════════════════════════════════════════╣
║ Market hours: 9:30 AM – 4:00 PM (6.5 hours)                     ║
║ Cycles: 18 (18 successful, 0 failed)                             ║
║ Universe: 746 symbols | ~108K contracts/cycle                    ║
║                                                                  ║
║ Avg cycle: 1580.2s | Fastest: 1412.0s | Slowest: 1892.1s        ║
║   Collection: avg 1131.0s (API: 1056s + DB: 75s)                ║
║   Analysis:   avg 14.5s (Query: 2.7s + Score: 5.5s + DB: 6.4s) ║
║   Alerts:     avg 0.8s                                           ║
║   Sync:       avg 135.1s                                         ║
║                                                                  ║
║ Alerts: 14 total (4 HIGH, 10 MEDIUM)                             ║
║ Watchlist: 6 created, 12 updated                                 ║
║ News sentiment: 3 enriched, 1 skipped, 0 failed                 ║
║ Dips detected: 5                                                 ║
║                                                                  ║
║ Missing Quotes: 3 symbols (every cycle: BRK.B, BF.B, LBRDA)     ║
╚══════════════════════════════════════════════════════════════════╝
```

**Fix:**

1. **FMSessionStats — add new accumulators** in `__init__()`:
   - `self.total_alerts = 0` and `self.alerts_by_severity = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}`
   - `self.total_contracts_scanned = 0`
   - `self.watchlist_created = 0` and `self.watchlist_updated = 0`
   - `self.dips_detected = 0`
   - `self.symbol_count = 0`
   - `self.first_cycle_start = None` and `self.last_cycle_end = None`
   - `self.sync_times = []` (quick sync per-cycle)

2. **FMSessionStats.record_cycle()** — accept and accumulate the new metrics. Add parameters or accept a richer `timings` dict. The FM cycle loop in `fm_main.py` already has all this data in local variables — it just needs to pass it to `record_cycle()`.

3. **FMSessionStats.get_summary()** — include the new fields in the returned dict.

4. **_display_session_summary()** in `main_runners.py` — build the enriched box from the expanded summary dict. Use conditional display for sections that may be zero (alerts, dips, errors, missing quotes).

5. **fm_main.py cycle loop** — pass the additional data to `stats.record_cycle()`:
   - Alert count and severity breakdown from `alerts.process_alerts()` return
   - Contract count from collector
   - Watchlist stats from `fm_watchlist.update_daily_watchlist()` return
   - Dip count from `fm_watchlist.update_prices_and_detect()` return
   - Sync timing from `run_quick_sync()` return
   - Cycle start/end timestamps

**Note for implementing analyst:** The goal is comprehensive end-of-day visibility. Include everything listed above. We can trim later if any lines prove unnecessary — it's easier to remove than to add after the fact. The per-phase timing breakdown is the highest priority item (data already exists in FMSessionStats, just not displayed).

**Status:** `DONE` (Piece A) — 2026-02-19. Added per-phase timing breakdown to `_display_session_summary()`: Collection (API + DB split), Analysis (Query + Score + DB split), Alerts. All data already existed in `FMSessionStats.get_summary()` timing dict. Piece B (new accumulators: alerts by severity, contracts scanned, watchlist created/updated, dips detected, symbol count, market hours span, sync times) split to P-057.

### P-036: Post-market phase framing — opening banner, task headers, duplicate elimination, completion box
**Location:** `strategies/flow_monitor/fm_main.py` (`run_post_market()`), `main_runners.py` (`run_flow_monitor()` post-market section)
**Severity:** Visual (missing structure, pervasive duplication)
**Problem:** Post-market phase has no opening banner, no task numbering, and every layer of the call stack announces itself independently — creating 2-4x duplicate lines at both start and finish of each task. Pre-market has an intro box (`🔍 PRE-MARKET PREPARATION`) with step descriptions, numbered step headers (`── Step 1/3: Alert Resolution ──`), and a completion box. Post-market has none of this.

**Current start/finish pattern (example: market regime):**
```
16:38:21 - Running evening market regime summary...    ← run_post_market() line 1471
16:38:21 - Running Evening Market Summary...           ← run_subprocess_task() line 141
16:38:38 - Evening Market Summary completed successfully  ← run_subprocess_task() line 162
16:38:38 - Market regime summary completed              ← run_post_market() line 1476
```
Four lines, two pairs of duplicates. Same pattern exists across all 5 tasks.

**Fix:**

1. **Opening banner**: Add `create_status_box()` intro box at the start of `run_post_market()`, mirroring pre-market:
```
╔══════════════════════════════════════════════════════════════════╗
║ 🌆 POST-MARKET ANALYSIS                                         ║
╠══════════════════════════════════════════════════════════════════╣
║ Task 1: Historical Backfill — Update price data for all symbols  ║
║ Task 2: Market Regime Summary — Classify today's market behavior ║
║ Task 3: Symbol Rollup — Aggregate contract data to symbol level  ║
║ Task 4: Daily Evaluation — Score and evaluate today's scans      ║
║ Task 5: Watchlist Cleanup — Archive expired watchlist entries     ║
╚══════════════════════════════════════════════════════════════════╝
```

2. **Task headers with numbering**: Replace bare `logging.info("Running X...")` in `run_post_market()` with `_step_header()` style headers:
```
── Task 1/5: Historical Backfill ─────────────────────────────────
── Task 2/5: Market Regime Summary ───────────────────────────────
── Task 3/5: Symbol Rollup ───────────────────────────────────────
── Task 4/5: Daily Evaluation ────────────────────────────────────
── Task 5/5: Watchlist Cleanup ───────────────────────────────────
```

3. **Eliminate duplicate announcements**: The caller (`run_post_market()`) owns the task header with numbering. The wrapper methods (`run_historical_backfill()`, `run_subprocess_task()`, `run_symbol_rollup_task()`, etc.) should NOT print their own "Running X..." lines. Remove or demote to `logging.debug()`:
   - `run_subprocess_task()` line 141: `Running {}...` — demote to debug (or suppress when called from post-market)
   - `run_symbol_rollup_task()` line 672: `Running end-of-day symbol summary rollup...` — remove
   - Similar for each wrapper method

4. **Eliminate duplicate completions**: The caller builds completion lines from return dicts. Wrapper methods should NOT print their own completion confirmations. Remove or demote:
   - `run_subprocess_task()` line 162: `{} completed successfully` — demote to debug
   - `run_symbol_rollup_task()` line 695: `Symbol summary complete (Ns)` — remove
   - `run_post_market()` redundant completions like `Market regime summary completed` (line 1476), `Symbol rollup completed` (line 1496), etc. — replace with single completion line built from return dict

5. **Post-market completion summary box**: After all 5 tasks, draw a completion box from the accumulated `sub_tasks` dict:
```
╔══════════════════════════════════════════════════════════════════╗
║ ✅ POST-MARKET ANALYSIS COMPLETE                                  ║
╠══════════════════════════════════════════════════════════════════╣
║ Backfill: 746/746 symbols (7.3 min)                              ║
║ Regime: elevated | Neutral | SPY +0.16% | VIX 20.3               ║
║ Rollup: 156 summaries (18.6s)                                    ║
║ Evaluation: complete (82.1s)                                     ║
║ Cleanup: no expired entries                                      ║
║ Total: 12.4 min | Tasks: 5/5 successful                         ║
╚══════════════════════════════════════════════════════════════════╝
```

**Architecture rule**: The caller (`run_post_market()`) handles all framing — task headers, completion lines, boxes. The wrapper methods handle execution and return dicts silently. Components own progress output only.

**Note for implementing analyst:** The return dicts from all 5 sub-tasks are already well-structured and contain the metrics needed for the completion box. No new data collection is needed — this is purely a display-layer change. The `_step_header()` pattern from `fm_main.py:857` is the template for task headers.
**Status:** `DONE` — Agent session, 2026-02-19. All 5 fixes: intro box added, 5 task headers via `_step_header()`, duplicate announcements/completions demoted to debug in `run_post_market()` + `run_subprocess_task()` + `run_symbol_rollup_task()`, completion summary box built from `sub_tasks` dict.

### P-037: Historical backfill subprocess output cleanup
**Location:** `strategies/flow_monitor/fm_main.py` (`run_historical_backfill()` lines 202-331), `data/tradier_historical_backfill.py` (subprocess)
**Severity:** Visual (double timestamps, init noise, missing completion summary)
**Problem:** Historical backfill runs as a subprocess with streaming output via `logging.info("   {}".format(output.strip()))` (line 232). The subprocess uses its own logging format (`2026-02-19 16:30:00,975 - INFO - message`). When piped through `logging.info()`, the orchestrator's formatter adds ANOTHER timestamp, creating double-timestamp lines:

```
16:30:00 -    2026-02-19 16:30:00,975 - INFO - Tradier API client initialized
16:30:01 -    2026-02-19 16:30:01,112 - INFO - Updating historical data for 746 symbols
16:30:01 -    2026-02-19 16:30:01,113 - INFO - Estimated time: ~6.2 minutes
```

Additional issues:
- "Tradier API client initialized" — component init noise, not user-facing
- "Estimated time: ~6.2 minutes" — subprocess shouldn't self-estimate; context goes in the intro box or task header
- "Date range: 2026-02-14 to 2026-02-19" — useful context but buried in noise
- Progress lines (`Progress: 50/746 symbols (1.7/sec, ETA: 6.9min)`) — good data, bad format
- Completion stats (Symbols with data, Total records, API calls, Total time) — good data, not structured

**Fix:**

1. **Strip subprocess logging prefix**: In `run_historical_backfill()` line 232, strip the `YYYY-MM-DD HH:MM:SS,mmm - INFO - ` prefix from subprocess output before passing to `logging.info()`. Use a regex or string split on ` - INFO - ` to extract just the message. This eliminates double timestamps.

2. **Filter init noise**: Skip lines matching "Tradier API client initialized" (or any line containing "initialized") — don't display on console.

3. **Relocate estimated time**: Either:
   - Move the estimate to the task header context line (P-036 provides the header): `── Task 1/5: Historical Backfill (746 symbols, ~6 min) ──`
   - Or suppress from subprocess and let the progress lines speak for themselves

4. **Progress format cleanup**: After prefix stripping, progress lines should look like:
```
16:30:30 - Progress: 50/746 symbols (1.7/sec, ETA: 6.9min)
16:30:59 - Progress: 100/746 symbols (1.7/sec, ETA: 6.3min)
```
Clean and readable.

5. **Structured completion line**: After subprocess returns, build a completion line from the return dict (which already parses `Symbols with data: N/M`):
```
✅ 16:37:21 - Historical backfill complete: 746/746 symbols, 2238 records (7.3 min)
```
Use `beautiful_log('success')`. Suppress the subprocess's own completion stats block from console (it's redundant with this line).

6. **Failure display**: The subprocess already handles exit codes (0=perfect, 2=partial, 1=catastrophic). For exit code 2 (partial), extract failed symbol count from output and show: `⚠️ Backfill partial: 744/746 symbols (2 failed)`. For exit code 1, the existing `logging.error()` is sufficient. Verify that individual symbol failures in the streamed output are visible (they should be — they're part of the subprocess stdout).

**Depends on:** P-036 (task headers provide the framing)
**Status:** `DONE` — Agent session, 2026-02-19. Subprocess prefix stripping (splits on ` - INFO - `), init noise filtered (`initialized`, `Estimated time`), cleaned lines displayed, beautiful_log completion line with symbol counts and duration.

### P-038: Market regime summary — surface actual results
**Location:** `strategies/flow_monitor/fm_main.py` (`run_evening_market_regime_summary()` lines 642-663, `run_post_market()` regime section lines 1470-1488), `data/market_daily_summary.py` (subprocess)
**Severity:** Content (results not surfaced) + Visual (duplicate announcement/completion)
**Problem:** Market regime is the sparsest post-market task — four lines, zero results:

```
16:38:21 - Running evening market regime summary...
16:38:21 - Running Evening Market Summary...
16:38:38 - Evening Market Summary completed successfully
16:38:38 - Market regime summary completed
```

The subprocess computes today's market regime, direction, SPY change, and VIX level — then all of that is discarded. `run_subprocess_task()` returns `bool` only. `run_evening_market_regime_summary()` returns `{success, duration_seconds}` — no market data. The user has no idea what the market regime actually was.

**Fix:**

1. **Surface actual regime results**: After the subprocess succeeds, query `market_daily_summary` for today's row to get the regime data. Add to the return dict and display:
```python
# In run_evening_market_regime_summary(), after subprocess succeeds:
import sqlite3
db_path = os.path.join('data', 'datalake.db')
conn = sqlite3.connect(db_path)
row = conn.execute(
    "SELECT market_regime, market_direction, spy_change_pct, vix_close "
    "FROM market_daily_summary WHERE trade_date = ? ORDER BY rowid DESC LIMIT 1",
    (now_eastern().strftime('%Y-%m-%d'),)
).fetchone()
conn.close()
```
Return dict becomes: `{success, duration_seconds, market_regime, market_direction, spy_change_pct, vix_close}`.

2. **Completion line with results**: In `run_post_market()`, after regime completes:
```
✅ 16:38:38 - Market regime: elevated | Neutral | SPY +0.16% | VIX 20.3 (17.1s)
```
Use `beautiful_log('success')`. This is the single completion line — replaces all four current lines.

3. **Duplicate elimination**: Handled by P-036 (task header replaces the double announcement; this completion line replaces the double completion).

4. **Progress logging**: Not needed for a 17-second task. The task header (from P-036) and completion line are sufficient. No coffee break between this and the next task is needed either — it's so fast the 60-second coffee break is longer than the task itself.

5. **Performance tracking**: Duration is already in the return dict. The added regime data feeds the post-market completion box (P-036) and future performance DB.

**Depends on:** P-036 (task header + duplicate elimination)
**Status:** `DONE` — Agent session, 2026-02-19. DB query added after subprocess to fetch regime/direction/SPY/VIX from market_daily_summary. Return dict spread with regime_data. beautiful_log shows regime line. Post-market completion box uses rich regime data with fallback.

### P-039: Symbol rollup output — reduce verbosity, structured completion
**Location:** `strategies/flow_monitor/fm_main.py` (`run_symbol_rollup_task()` lines 665-722, `run_post_market()` rollup section lines 1490-1510), `strategies/flow_monitor/fm_symbol_rollup.py` (`populate_daily_summary()`, `_store_summaries()`, `_log_completion_stats()`)
**Severity:** Visual (triple announcement, verbose batches, quadruple completion)
**Problem:** Symbol rollup has the opposite problem from regime — it's not too sparse, it's too chatty:

**Triple announcement:**
```
16:39:38 - Running symbol summary rollup...             ← run_post_market()
16:39:38 - Running end-of-day symbol summary rollup...  ← run_symbol_rollup_task()
16:39:39 - Starting daily summary population for 2026-02-19  ← populate_daily_summary()
```

**Verbose batch progress (3 lines per batch x 4 batches = 12 lines):**
```
16:39:39 - Processing batch 1/4: symbols 1-50
16:39:47 - Stored 50 summaries successfully
16:39:47 - Batch completed in 7.36 seconds
```

**Quadruple completion (6 + 1 + 1 = 8 lines):**
```
16:39:58 - Flow symbol summary rollup: 2026-02-19    ← _log_completion_stats()
16:39:58 - Symbols processed: 156                     ← _log_completion_stats()
16:39:58 - Summaries created: 156                     ← _log_completion_stats()
16:39:58 - Errors encountered: 0                      ← _log_completion_stats()
16:39:58 - Total processing time: 18.55 seconds       ← _log_completion_stats()
16:39:58 - Average time per symbol: 0.119 seconds     ← _log_completion_stats()
16:39:58 - Symbol summary complete (19.5 seconds)     ← run_symbol_rollup_task()
16:39:58 - Symbol rollup completed                    ← run_post_market()
```

**Fix:**

1. **Announcement**: Handled by P-036 (task header replaces all three announcement lines).

2. **Batch progress — collapse to one line per batch**: In `fm_symbol_rollup.py`, remove "Stored N summaries successfully" from `_store_summaries()` (line 364) — demote to `logging.debug()`. Merge batch start and batch complete into one line AFTER the batch finishes:
```
16:39:47 - Batch 1/4: 50 symbols processed (7.4s)
16:39:52 - Batch 2/4: 50 symbols processed (5.5s)
16:39:57 - Batch 3/4: 50 symbols processed (5.0s)
16:39:58 - Batch 4/4: 6 symbols processed (0.6s)
```
This is 4 lines instead of 12 — same information, 3x more compact.

3. **Completion stats — demote to debug**: Move all of `_log_completion_stats()` to `logging.debug()`. The data is useful for forensics but not for console. Alternatively, keep it but route to the diagnostic logger only.

4. **Single completion line from return dict**: In `run_post_market()`, replace the triple completion with:
```
✅ 16:39:58 - Symbol rollup complete: 156 symbols, 156 summaries, 0 errors (18.6s)
```
Use `beautiful_log('success')`. All metrics come from the return dict (already populated from `rollup.stats`).

5. **Error display**: Errors are already tracked properly. Per-symbol failures log via `logging.error("Failed to process symbol...")` (visible on console), and `self.stats['errors']` accumulates. The completion line includes error count. If errors > 0, the P-036 completion box shows it. No change needed for error handling — it works.

6. **Also fix duplicate error logging**: `run_symbol_rollup_task()` lines 714-715 log the same error twice:
```python
logging.error("Symbol summary rollup error: {}".format(str(e)))
logging.error("Symbol summary rollup error: {}".format(e))
```
Remove one of them.

**Depends on:** P-036 (task header + duplicate elimination)
**Status:** `DONE` — Agent session, 2026-02-19. Batch progress consolidated (1 line per batch), store confirmation→debug, completion stats→debug, entry-point noise→debug, duplicate error logging fixed, beautiful_log completion line added.

### P-040: Daily evaluation subprocess output — suppress noise, reduce progress verbosity, structured completion
**Location:** `strategies/flow_monitor/fm_main.py` (`run_daily_evaluation_task()` lines 790-847), `strategies/flow_monitor/evaluation/run_daily_evaluation.py` (subprocess)
**Severity:** Visual (extreme noise — ~90 lines for a 42-second task)
**Problem:** Daily evaluation runs as a streamed subprocess. Its output is the noisiest of all post-market tasks — approximately 90 lines for 42 seconds of work. The subprocess has its own ASCII banner, extensive initialization checks, internally duplicated lines, per-10-alert progress, and a triple completion block. The streaming wrapper (`logging.info("   {}".format(output.strip()))`) adds double timestamps to every `INFO` line.

**Issue breakdown:**

1. **ASCII banner (6 lines)**: `======` decorated `FLOW MONITOR DAILY EVALUATION RUNNER` block with title, description, current time, separator. Replaced by P-036 task header.

2. **Init noise (9 lines)**: "Checking for running instances", "No conflicting instances found", "Initializing AlertEvaluator...", "Verifying database schema...", three `[OK]` schema checks, "Alert Evaluator initialized with 30-day tracking window", "AlertEvaluator initialized successfully". All debug-level — schema verification and instance checks are operational safety, not user-facing.

3. **Double timestamps**: Same root cause as P-037 — subprocess logging format (`2026-02-19 17:11:21 - INFO - message`) wrapped in orchestrator's `logging.info()`. Apply same prefix-stripping fix.

4. **Internal duplicates within the subprocess**: The subprocess says things 2-3 times:
   - "Initializing AlertEvaluator..." appears as both `print()` and `logging.info()`
   - "Starting alert evaluation run..." appears as both `print()` and `logging.info()`
   - "Found 359 alerts to evaluate" appears in THREE forms: `[OK]` prefix, `INFO` prefix, and query result line

5. **Batch progress — wildly over-verbose (~56 lines)**: 8 batches × (decorative `--- BATCH N/8 ---` header + `Processing alerts N-M` print + `Starting batch N/8 with X alerts` INFO + ~5 per-10 progress lines + `Batch N/8 completed` INFO) = ~56 lines. Progress every 10 alerts for 359 alerts is 36 progress lines alone.

6. **Triple completion block (~15 lines)**:
   - Block 1: `EVALUATION COMPLETE` with `[OK]` lines (2 lines)
   - Block 2: `ALERT EVALUATION SUMMARY` with INFO format (8 lines — contains the useful metrics)
   - Block 3: `======` decorated block with ✅ lines and log file path (5 lines)
   - Block 4: `Daily evaluation completed` from `run_post_market()` (1 line)

7. **Log file path on console**: `Log file: E:\options_scanner\strategies\flow_monitor\evaluation\logs\...` — not user-facing, debug only.

**Useful data buried in the noise:**
- Alert count: 359
- Performance peaks: 1011
- Tracking records created: 25
- Alerts completed: 0
- Errors: 0
- Duration: 42.7s

**Fix — two approaches (choose based on effort):**

**Approach A (subprocess-side cleanup):** Modify `run_daily_evaluation.py` to have a `--quiet` or `--orchestrated` mode that suppresses the banner, init noise, per-10 progress, and triple completion. Output only: one context line, per-50 (per-batch) progress, one summary line. This fixes the problem at the source but requires modifying the evaluation script.

**Approach B (streaming-side filter):** In `run_daily_evaluation_task()`, filter the streamed output. Strip `INFO` prefix (P-037 pattern), skip lines matching banner/init/schema patterns, collapse batch progress to one line per batch, capture summary metrics from output for structured completion line. More work in the wrapper but doesn't modify the subprocess.

**Recommendation:** Approach A. The subprocess's own output is the root problem — it was written as a standalone script with its own full console experience, not as a component being orchestrated. Adding `--orchestrated` mode (or `--quiet`) teaches it to be a good citizen when called by the orchestrator, while preserving its verbose standalone output for manual runs.

**Target output:**
```
── Task 4/5: Daily Evaluation ────────────────────────────────

17:11:21 - Evaluating 359 alerts in 8 batches
17:11:27 - Progress: 50/359 (13.9%)
17:11:33 - Progress: 100/359 (27.9%)
17:11:40 - Progress: 150/359 (41.8%)
17:11:45 - Progress: 200/359 (55.7%)
17:11:51 - Progress: 250/359 (69.6%)
17:11:57 - Progress: 300/359 (83.6%)
17:12:04 - Progress: 350/359 (97.5%)
✅ 17:12:04 - Evaluation complete: 359 alerts, 1011 peaks, 25 tracking records, 0 errors (42.7s)
```

Progress every 50 alerts (once per batch boundary) — 7 lines instead of 36. One structured completion line instead of 15. Total: ~10 lines instead of ~90.

**Return dict enrichment**: `run_daily_evaluation_task()` currently returns `{success, duration_seconds, return_code}`. Parse the subprocess stdout for summary metrics (alerts evaluated, peaks, tracking records, errors) and add to the return dict. This feeds the P-036 completion box.

**Depends on:** P-036 (task header + duplicate elimination), P-037 pattern (double-timestamp stripping)
**Status:** `DONE` — Agent session, 2026-02-19. Subprocess prefix stripping + noise filtering (18 skip patterns) in fm_main.py. Progress interval 10→50 in fm_evaluator.py. Completion verbosity reduced in both run_daily_evaluation.py and fm_evaluator.py. beautiful_log completion added.

### P-041: Watchlist cleanup output — deduplicate, structured completion
**Location:** `strategies/flow_monitor/fm_main.py` (`run_post_market()` lines 1584-1632), `strategies/flow_monitor/fm_watchlist.py` (`archive_expired_entries()`)
**Severity:** Visual (minor — small duplication)
**Problem:** Watchlist cleanup has a small duplication — the component and the caller both report the same result:

```
17:12:04 - Running watchlist cleanup...           ← run_post_market() line 1585
17:12:05 - Archived 15 expired watchlist entries  ← fm_watchlist.archive_expired_entries()
17:12:05 - Watchlist cleanup complete: 15 entries archived  ← run_post_market() line 1611
```

Three lines, two saying "15 entries archived". The announcement is replaced by P-036 task header.

**Fix:**

1. **Announcement**: Handled by P-036 (task header replaces "Running watchlist cleanup...").

2. **Component line**: Demote "Archived N expired watchlist entries" in `fm_watchlist.py` to `logging.debug()`. The caller's completion line is sufficient.

3. **Single completion line**: In `run_post_market()`, replace the current `logging.info("Watchlist cleanup complete: N entries archived")` with `beautiful_log`:
```
✅ 17:12:05 - Watchlist cleanup: 15 entries archived (0.7s)
```
Include duration from the return dict. For the zero case (no expired entries), use:
```
✅ 17:12:05 - Watchlist cleanup: no expired entries (0.2s)
```

4. **Suppress the zero-case duplicate**: Currently `run_post_market()` has both an `if cleanup_stats['entries_archived'] > 0:` branch and an `else:` branch that both call `logging.info()`. Merge into one `beautiful_log('success')` line that handles both cases.

**Target output:**
```
── Task 5/5: Watchlist Cleanup ───────────────────────────────

✅ 17:12:05 - Watchlist cleanup: 15 entries archived (0.7s)
```

**Depends on:** P-036 (task header)
**Status:** `DONE` — Agent session, 2026-02-19. Component `archive_expired_entries()` already clean (one info line per path). Added beautiful_log completion in run_post_market() Task 5 section.

### P-042: Enrich FM COMPLETE box — market hours detail, post-market gaps, total duration
**Location:** `main_runners.py` (`run_flow_monitor()` lines 503-548) — the `🎯 FLOW MONITOR COMPLETE` box builder
**Severity:** Content (significant underutilization of available data)
**Problem:** The FM completion box is the single end-of-day summary for a 7+ hour pipeline. Currently it shows good pre-market detail (when not skipped), but Market Hours gets only "Completed" with zero detail lines, and Post-Market is missing 2 of 5 task results (regime and evaluation). No total duration.

**Current output:**
```
╔══════════════════════════════════════════════════════════╗
║ 🎯 FLOW MONITOR COMPLETE                                 ║
╠══════════════════════════════════════════════════════════╣
║ Pre-Market: ✅ Skipped                                   ║
║ Market Hours: ✅ Completed                               ║
║ Post-Market: ✅ 5/5 tasks completed                      ║
║   Backfill: 746 symbols updated                          ║
║   Rollup: 156 summaries created                          ║
║   Cleanup: 15 entries archived                           ║
╚══════════════════════════════════════════════════════════╝
```

**Gap analysis:**

| Phase | Currently shown | Available but not shown |
|-------|----------------|------------------------|
| Pre-Market | Alerts, sentiment, sync (good) | Duration (minor) |
| Market Hours | "Completed" only | Cycles (count + success/fail), avg/fastest/slowest timing, alert totals |
| Post-Market | Backfill, rollup, cleanup (3/5) | Regime results, evaluation metrics, per-task durations |
| Overall | Nothing | Total FM pipeline duration |

**Data availability:**
- `market_hours_result['session_stats']` contains the full `FMSessionStats.get_summary()` dict — cycle counts, avg/min/max timing, errors, missing quotes. Already extracted at line 455 but never used in the completion box.
- `market_hours_result['total_cycles']` already extracted at line 443.
- Post-market regime results: blocked on P-038 (return dict enrichment)
- Post-market evaluation metrics: blocked on P-040 (return dict enrichment)
- Total duration: trivially computed from `time.time()` at method start

**Fix:**

1. **Market Hours detail lines** (available NOW — no dependencies):
```python
# After line 541 ("Market Hours: ✅ Completed")
if isinstance(market_hours_result, dict):
    stats = market_hours_result.get('session_stats', {})
    tc = stats.get('total_cycles', 0)
    sc = stats.get('successful_cycles', 0)
    fc = stats.get('failed_cycles', 0)
    if tc > 0:
        market_hours_lines.append("  Cycles: {} ({} successful{})".format(
            tc, sc, ", {} failed".format(fc) if fc > 0 else ""))
    timing = stats.get('timing', {})
    if timing:
        market_hours_lines.append("  Avg cycle: {:.1f}s | Fastest: {:.1f}s | Slowest: {:.1f}s".format(
            timing.get('avg_cycle', 0), timing.get('min_cycle', 0), timing.get('max_cycle', 0)))
```

2. **Post-Market regime line** (after P-038 enriches return dict):
```python
mr = pm_subs.get('market_regime', {})
if mr.get('success') and mr.get('market_regime'):
    post_market_lines.append("  Regime: {} | {} | SPY {:+.2f}% | VIX {:.1f}".format(
        mr['market_regime'], mr.get('market_direction', '?'),
        mr.get('spy_change_pct', 0), mr.get('vix_close', 0)))
```

3. **Post-Market evaluation line** (after P-040 enriches return dict):
```python
ev = pm_subs.get('evaluation', {})
if ev.get('success') and ev.get('alerts_evaluated'):
    post_market_lines.append("  Evaluation: {} alerts, {} tracking records".format(
        ev['alerts_evaluated'], ev.get('tracking_records_created', 0)))
```

4. **Market Hours alert totals** (after P-035 adds FMSessionStats accumulators):
```python
# Add after cycle timing line
# total_alerts and alerts_by_severity from enriched session_stats
```

5. **Total duration**: Add as the final line in the box:
```python
completion_lines.append("Total Duration: {}".format(format_duration(total_elapsed)))
```
Capture `fm_start_time = time.time()` at the top of `run_flow_monitor()` and compute elapsed at the end.

**Target output:**
```
╔══════════════════════════════════════════════════════════════════╗
║ 🎯 FLOW MONITOR COMPLETE                                        ║
╠══════════════════════════════════════════════════════════════════╣
║ Pre-Market: ✅ Completed                                         ║
║   Alerts resolved: 22 (18 building, 1 closing, 3 neutral)       ║
║   Sentiment updated: 79 symbols | Query DB synced                ║
║ Market Hours: ✅ Completed                                       ║
║   Cycles: 18 (18 successful, 0 failed)                           ║
║   Avg cycle: 1580.2s | Fastest: 1412.0s | Slowest: 1892.1s      ║
║   Alerts: 14 total (4 HIGH, 10 MEDIUM)                           ║
║ Post-Market: ✅ 5/5 tasks completed                              ║
║   Backfill: 746/746 symbols (7.3 min)                            ║
║   Regime: elevated | Neutral | SPY +0.16% | VIX 20.3             ║
║   Rollup: 156 summaries created                                  ║
║   Evaluation: 359 alerts, 25 tracking records                    ║
║   Cleanup: 15 entries archived                                   ║
║ Total Duration: 7h 43m                                           ║
╚══════════════════════════════════════════════════════════════════╝
```

**Implementation order:**
- Market Hours cycles + timing + total duration: implement now (no dependencies)
- Regime line: after P-038
- Evaluation line: after P-040
- Alert totals: after P-035

**Note for implementing analyst:** This item can be partially implemented immediately (market hours detail + total duration) and incrementally enriched as P-035, P-038, and P-040 land their return dict improvements. Each addition is a few lines of code in the completion box builder. Start with what's available now.

**Status:** `DONE` — 2026-02-19. All available data now displayed: (1) Market Hours cycles + timing from session_stats, (2) Post-Market regime line with direction/SPY/VIX from P-038 return dict, (3) Backfill enriched with symbols_total and duration, (4) Evaluation with duration, (5) Total FM pipeline duration using `_format_duration()`. Alert totals deferred to P-057 (needs new FMSessionStats accumulators). Initialized `session_stats={}` and `market_hours_result=None` before market hours block for after-hours path safety.

### P-043: Extend expiration cache TTL to cover evening OP
**Location:** `core/tradier_api.py:482` — `get_option_expirations(symbol, max_age_seconds=28800)`
**Severity:** Performance (unnecessary API calls in evening OP)
**Problem:** P-030 extended the expiration cache TTL from 1 hour to 8 hours to cover market hours. But morning OP runs at ~6:35 AM, and evening OP starts at ~5:13 PM — a 10.5-hour gap. By evening OP, the morning's cache entries are expired and the collector re-fetches expirations for symbols whose cache wasn't refreshed by FM during market hours. This produces ~200+ `Fetching option expirations for X` lines mid-collection and adds unnecessary API calls.

Observed in live output: symbols A through BXP used cached expirations (refreshed by FM at ~9:30 AM, ~7.7 hours old, within TTL). Starting at CAH, cache entries from the 6:35 AM morning OP had expired (10.5 hours old, beyond 8-hour TTL), triggering fresh fetches.

**Fix:** Change `max_age_seconds=28800` (8hr) to `max_age_seconds=57600` (16hr). Covers the full 6:35 AM to 10:35 PM window with margin. Expirations are exchange-set and never change intraday — a daily refresh at morning OP is sufficient.
**One-line change:** Same pattern as P-030.
**Status:** `DONE` — Agent session, 2026-02-19. Changed `max_age_seconds=28800` to `max_age_seconds=57600` at `tradier_api.py:482`.

### P-045: Evening OP output cleanup — rollup init noise, health report silence, completion box gap
**Location:** `strategies/option_pipeline/op_symbol_rollup.py`, `strategies/option_pipeline/op_main.py` (health report section), `main_runners.py` (`run_evening_option_pipeline()` completion box)
**Severity:** Visual (minor — noise, verbosity, missing data in completion box)
**Problem:** Three issues found during live evening OP review:

1. **Rollup init noise (3 lines):**
```
17:53:06 - OP Rollup: Initialized for symbol aggregation with batch size 100
   Processing 746 symbols (KLMN 800 universe)
   Batch size: 100 symbols
```
The tree diagram intro already provides this context. The two indented lines are `print()` calls (no timestamps). Demote all three to `logging.debug()`.

2. **Rollup completion stats verbosity (8 lines):** "Total symbols: 746" / "Symbols processed: 746" / "Symbols with data: 746" — three lines saying the same thing. Same pattern as FM rollup (P-039). Condense to ~3 lines or demote to debug and use a single summary line.

3. **Health report issues:**
   - **Double announcement**: "📝 Generating comprehensive health report with full pipeline analytics..." then "🔍 Performing comprehensive pipeline health check..." — same thing twice.
   - **3-minute silence**: 197 seconds between announcement and results with zero progress. User has no idea if it's hung. Add a context line: "Checking collection coverage, analysis completeness, and data quality — may take 2-3 minutes" or add periodic progress if feasible.

4. **Evening completion box missing P-012 fixes:** P-012 added duration, health status, and conditional failed symbols to the morning OP box, and removed the filler "Status: ✅ Complete pipeline executed" line. The evening box was not updated:
```
║ Evening Pipeline: ✅ Completed with volume data          ║
```
This filler line should be removed. Add duration (from `total_execution_time`), health status (from `health.pipeline_health.overall_status`), and conditional failed symbols — same as morning box.

**Fix:**
1. Demote rollup init lines to `logging.debug()` in `op_symbol_rollup.py`.
2. Condense `_log_completion_stats()` or demote to debug, replace with single summary line.
3. Remove one of the two health report announcements. Add context line about expected duration.
4. Apply P-012's completion box fixes to `run_evening_option_pipeline()` in `main_runners.py`.
**Status:** `DONE` — Agent session, 2026-02-19. All 4 fixes applied: rollup init→debug, _log_completion_stats condensed (single info summary + detail→debug), health report second announcement→debug with context line added, evening completion box mirrors morning pattern (duration, health, conditional failures, filler removed).

### P-046: Query database sync output cleanup — banner, progress interval, redundant completions
**Location:** `data/health/db_backup.py` (sync function), `main_runners.py` (`run_query_sync()` or equivalent)
**Severity:** Visual (redundant banner, ~100 progress lines, 6x completion messages)
**Problem:** Query database sync runs as a streamed subprocess (~28 minutes). The subprocess has its own decorated console experience that conflicts with the orchestrator's framing:

1. **Double banner**: Orchestrator draws its `🔄 QUERY DATABASE SYNC` mission box, then the subprocess immediately draws its own `======` decorated banner with title, timestamp. Redundant — the orchestrator box is sufficient.

2. **Progress interval too fine (~100 lines)**: Progress reports every 30,000 pages for ~2.9M pages = ~98 progress lines. For a 28-minute operation, progress every 100,000 pages (~29 lines) is sufficient.

3. **Mixed timestamp formats**: P-020 converted 8 key lines to `db_backup` named logger (full `YYYY-MM-DD HH:MM:SS - db_backup - INFO -` format), while the rest are raw `print()` with no timestamps. Inconsistent — neither matches the orchestrator's time-only format.

4. **6x completion messages**:
   - `✅ Backup completed: 2929935 pages (11.18 GB)` (logger)
   - `✅ Sync completed successfully in 27.7 minutes` (logger)
   - `✅ QUERY DATABASE SYNC SUCCESSFUL` (print, decorated)
   - `Analysis tools can now query: data/datalake_query.db` (print)
   - `Query sync completed successfully in 27.7 minutes` (logger)
   - `🔓 Sync lock file removed` (logger)
   Then the orchestrator box: `✅ QUERY SYNC OPERATION COMPLETE`
   Seven completion messages total.

5. **Orchestrator completion box too sparse**: Just "Query database: datalake_query.db" and "Status: Sync completed successfully". Missing: duration, size, table count, verification results — all of which are printed by the subprocess but not captured for the box.

**Fix:**

1. **Suppress subprocess banner**: When called with `--auto` flag (or a new `--orchestrated` flag), skip the `======` decorated header block and the redundant `Timestamp:` line. The orchestrator's mission box provides framing.

2. **Progress interval**: Change from every 30,000 pages to every 100,000 pages in `db_backup.py`. Reduces ~98 lines to ~29 lines. For a 28-minute operation this still provides good heartbeat coverage (~1 line per minute).

3. **Consolidate completion**: Keep two lines from the subprocess:
   - `✅ Sync completed: 2,929,935 pages (11.18 GB) in 27.7 minutes`
   - `✅ Verified: 30 tables, data fresh (latest: 2026-02-19 15:56:37)`
   Suppress: the decorated `QUERY DATABASE SYNC SUCCESSFUL` block, the redundant duration line, the lock file message (demote to debug), the `Analysis tools can now query` line.

4. **Enrich orchestrator completion box**: Parse subprocess output or return dict for duration, size, table count, verification status:
```
╔══════════════════════════════════════════════════════════╗
║ ✅ QUERY SYNC OPERATION COMPLETE                         ║
╠══════════════════════════════════════════════════════════╣
║ Synced: 11.18 GB (30 tables) in 27.7 minutes            ║
║ Verified: schema ✅ | data freshness ✅                  ║
║ Target: datalake_query.db ready for analysis             ║
╚══════════════════════════════════════════════════════════╝
```

**Note:** This is the same subprocess that P-006 (PARTIAL) and P-020 (DONE) already touched. P-020 converted 8 forensic lines to the `db_backup` named logger. This item addresses the console presentation layer on top of those forensic changes.
**Status:** `DONE` — Agent session, 2026-02-19. All 4 fixes applied: banner suppressed when interactive=False (matches P-046 sync pattern), progress interval 30K→100K, completion consolidated to 2 clean print() lines + lock/analysis→debug, orchestrator box enriched with regex-parsed size/tables/duration + wall-clock fallback.

### P-047: Remove "Resuming Operations" box + autofix duplicate line
**Location:** `main_ui.py` or `main.py` (coffee break resume handler), `main_runners.py` (autofix review section)
**Severity:** Visual (noise)
**Problem:** Two small issues:

1. **"Resuming Operations" box** appears after every coffee break — 4 lines of chrome to say "wait is over":
```
╔══════════════════════════════════════════════════════════╗
║ Resuming Operations                                      ║
╠══════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                      ║
╚══════════════════════════════════════════════════════════╝
```
The coffee break already announces "Up Next: X", and the next step's announcement follows immediately. This box adds nothing.

2. **Autofix review duplicate**: When no errors are queued, two lines say the same thing:
```
19:06:47 - No pending errors today - batch mode not needed
ℹ️ 19:06:47 - No errors in queue - batch mode not needed
```

**Fix:**
1. Remove the "Resuming Operations" box entirely. If any transition is needed, replace with a single blank line (`print("")`).
2. Remove one of the two "no errors" lines. Keep the `beautiful_log` version (with emoji), demote the other to `logging.debug()`.
**Status:** `DONE` — Agent session, 2026-02-19. Resuming Operations box replaced with `print("")` in main_ui.py. Autofix duplicate demoted to `logging.debug()` in autofix.py:509.

### P-048: Database backup output cleanup — CLI noise, double banner, triple completion, sparse box
**Location:** `data/health/db_backup.py` (backup function), `main_runners.py` (backup completion box)
**Severity:** Visual (subprocess noise, redundant completions, missing data in box)
**Problem:** Same pattern as query sync (P-046) — subprocess has its own console experience that conflicts with orchestrator framing.

1. **CLI diagnostic leak**:
```
No operation specified. Use --help to see available options.
Running default operation: disaster backup
```
The subprocess's argument parser prints this when called without an explicit flag. Should not appear on console. Fix in the calling command (pass explicit `--backup` flag) or suppress in the script when `--auto` is set.

2. **Double banner**: Orchestrator draws `💾 DATABASE BACKUP OPERATION` mission box, subprocess draws its own `======` decorated `DISASTER RECOVERY BACKUP` banner. Suppress subprocess banner when called from orchestrator (same approach as P-046).

3. **Triple completion**:
   - `✅ Backup completed in 3.0 minutes` (print)
   - `✅ DISASTER BACKUP SUCCESSFUL` + `======` decorated block (print)
   - `Disaster backup completed successfully in 3.0 minutes` (logger)
   - Then orchestrator box
   Consolidate to one subprocess completion line + orchestrator box.

4. **Orchestrator completion box too sparse**:
```
║ Backup file: datalake_backup.db                          ║
║ Status: Backup completed successfully                    ║
```
Missing size, duration, verification results. Target:
```
║ Backup: 11.18 GB in 3.0 minutes                         ║
║ Verified: size ✅ | schema ✅ (30 tables)                ║
```

**Note:** Keep the WAL/SHM file diagnostic as-is — that's intentional current monitoring.
**Status:** `DONE` — Agent session, 2026-02-19. All 4 fixes: `--disaster --auto` flags passed explicitly (fixes CLI diagnostic), banner wrapped in `if interactive:`, completion consolidated to single print() line + logger→debug, orchestrator box enriched with parsed size/duration. WAL diagnostics preserved.

### P-049: Trading day complete box — styling and per-step durations
**Location:** `main_runners.py` or `main.py` (end-of-day summary box builder)
**Severity:** Content (underutilized summary)
**Problem:** The end-of-day summary box is functional but could be richer:

1. **`--` prefix before step numbers** looks odd:
```
║   -- 1.1 Morning Option Pipeline: Skipped                ║
```
Should be just the step number, or a bullet: `1.1 Morning Option Pipeline: Skipped`.

2. **No per-step durations**: Each step just shows "OK" or "Skipped". The return dicts from every runner contain `duration_seconds`. Showing it makes this box the single glanceable record of the day:
```
║   ✅ 2. Flow Monitor: OK (7h 43m)                        ║
║   ✅ 3.1 Evening Option Pipeline: OK (47.8 min)          ║
║   ✅ 3.2 Query Sync (Evening): OK (27.7 min)             ║
```

3. **No emoji in title**: Every other major box has an emoji. `TRADING DAY COMPLETE` should have one for consistency — `🎯 TRADING DAY COMPLETE` or `✅ TRADING DAY COMPLETE`.

**Fix:**
1. Remove `--` prefix from step labels.
2. Append duration to each non-skipped step: `OK ({duration})`. Format: minutes for <1hr, `Xh Ym` for longer. Requires storing each runner's return dict (or at minimum its duration) in the orchestrator's results tracking — check if `daily_state.json` or an in-memory dict already captures this.
3. Add emoji to title.

**Note for implementing analyst:** The per-step duration data may require propagating return dicts from `run_*()` methods (see `docs/performance_tracking_enhancement/performance_tracking_notes.md` prerequisite section). If return dicts aren't available yet, wall-clock timing at the orchestrator level (wrapping each `run_*()` call with `time.time()`) is a simpler interim approach.
**Status:** `DONE` — Agent session, 2026-02-19. All 3 fixes: `--` prefix removed from step labels, `step_durations` dict added with `time.time()` wrapping around all 16 `run_*()` calls, `_format_duration()` helper added (<1m→"42s", 1-60m→"27.7 min", >60m→"7h 43m"), emoji added to title.

### P-044: Rename OP mission box from "Refresh" to "Update"
**Location:** `main_runners.py` — `run_evening_option_pipeline()` mission box title
**Severity:** Copy (terminology)
**Problem:** Evening OP mission box says "REFRESH" — `🌆 EVENING OPTION PIPELINE REFRESH`. The evening run captures end-of-day volume and OI data that didn't exist during the morning. "Update" is more accurate.
**Fix:** Morning keeps "REFRESH" (per Ben). Evening changes to "UPDATE".
**Status:** `DONE` — Direct edit, 2026-02-19. Changed evening mission box title from "EVENING OPTION PIPELINE REFRESH" to "EVENING OPTION PIPELINE UPDATE" in `main_runners.py`.

### P-050: Backfill subprocess — suppress completion stats block
**Location:** `strategies/flow_monitor/fm_main.py` (`run_historical_backfill()` streaming loop)
**Severity:** Visual (redundant — beautiful_log summary already covers this)
**Problem:** After prefix stripping (P-037), the subprocess completion stats still display as 5 lines:
```
22:00:07 -    Historical update completed!
22:00:07 -    Symbols with data: 746/746 (100.0%)
22:00:07 -    Total records updated: 2238
22:00:07 -    API calls made: 746
22:00:07 -    Total time: 7.4 minutes
```
These are redundant with the beautiful_log line: `✅ Backfill complete: 746/746 symbols (7.4 min)`
**Fix:** Add these patterns to the skip filter in the streaming loop: `'Historical update completed'`, `'Symbols with data'`, `'Total records'`, `'API calls made'`, `'Total time:'`. The raw output is still captured in `output_lines` for parsing (the `output_lines.append()` happens before the filter), so the return dict data is unaffected.
**Status:** `DONE` — Agent session, 2026-02-19. Added 5 patterns to skip filter. output_lines.append() still runs before filter so parsing unaffected.

### P-051: Evaluation subprocess — remaining noise after P-040
**Location:** `strategies/flow_monitor/fm_main.py` (`run_daily_evaluation_task()` streaming loop), `strategies/flow_monitor/evaluation/fm_evaluator.py`, `strategies/flow_monitor/evaluation/run_daily_evaluation.py`
**Severity:** Visual (blank lines, banner leak, duplicate starts, triple completion)
**Problem:** Live test revealed P-040 didn't catch everything:

1. **Blank timestamped lines** — 4 empty lines like `22:03:32 -` appear. These are blank `print()` or `logging.info("")` calls from the subprocess that pass through the filter (they don't match any skip pattern because they're empty).

2. **Banner leak** — `FLOW MONITOR DAILY EVALUATION RUNNER` appears. The skip filter checks for `'Daily Evaluation'` but the actual banner text is `'FLOW MONITOR DAILY EVALUATION RUNNER'` (uppercase, different wording). Add `'EVALUATION RUNNER'` to skip patterns.

3. **Duplicate "Starting alert evaluation run..."** — appears twice. One is from `run_daily_evaluation.py`, the other from `fm_evaluator.py`. One should be demoted to debug.

4. **Triple completion**:
```
22:04:01 -    Evaluated 219 alerts, 0 completed, 0 errors (24.7s)
22:04:01 -    Evaluation completed in 24.7 seconds
22:04:01 -    Evaluation completed successfully in 24.7s
```
Three lines for the same event. Keep the first (most informative), demote the other two to debug.

**Fix:**
1. Add blank-line filter: `if not line_text.strip(): continue` (after prefix stripping, before skip pattern check)
2. Add `'EVALUATION RUNNER'` to skip patterns
3. Find the duplicate "Starting alert evaluation run" and demote one to debug
4. In subprocess scripts, demote the 2 redundant completion lines to `logging.debug()`
**Status:** `DONE` — Agent session, 2026-02-19. All 4 fixes: blank line filter added, `EVALUATION RUNNER` added to skip patterns, duplicate "Starting" print→debug in run_daily_evaluation.py, two redundant completion lines→debug (kept "Evaluated N alerts" as single info line).

### P-052: Watchlist cleanup — demote component line (minor)
**Location:** `strategies/flow_monitor/fm_watchlist.py` (`archive_expired_entries()`)
**Severity:** Visual (minor duplication)
**Problem:** Both the component and the beautiful_log report the same result:
```
22:04:02 - No expired watchlist entries found
ℹ️ 17:00:00 - Cleanup: no expired entries
```
**Fix:** Demote `archive_expired_entries()`'s `logging.info()` calls to `logging.debug()`. The beautiful_log in `run_post_market()` now owns the user-facing output for this task.
**Status:** `DONE` — Agent session, 2026-02-19. Both logging.info() calls in archive_expired_entries() demoted to logging.debug().

### P-053: Query Sync — duplicate completion log line (minor)
**Location:** `data/health/db_backup.py`
**Severity:** Visual (minor — duplicate line with different format)
**Problem:** The sync completion message appears twice with different logging formats:
```
2026-02-19 23:11:11 - db_backup - INFO - Query sync completed successfully in 30.8 minutes
INFO:db_backup:Query sync completed successfully in 30.8 minutes
```
The second line is the Python root logger's default format, indicating either a duplicate handler or the root logger echoing. The `db_backup` module logger has its own handler but the message also propagates to the root logger which has a basicConfig-style handler attached.
**Fix:** Set `logger.propagate = False` on the db_backup module logger, OR ensure the root logger doesn't have a default handler that duplicates output. Check how the logger is configured at the top of `db_backup.py` — likely needs `propagate = False` to prevent the root logger from re-emitting the same message.
**Status:** `DONE` — 2026-02-19. Fixed as part of P-006: added `logger.propagate = False` after handler setup in `setup_logging()`.

### P-054: FM error/failure logging audit — collector and analyzer
**Location:** `strategies/flow_monitor/fm_collector.py`, `strategies/flow_monitor/fm_analyzer.py`
**Severity:** Visual (diagnostic noise on failure paths)
**Problem:** Extracted from P-034 item 7. These files may have INFO/WARNING diagnostic lines on failure paths that should be DEBUG. Goal: ensure each failure path has one clean user-facing line, with diagnostics in debug only.
**Fix:** Review all `logging.info()` and `logging.warning()` calls in failure/error handling paths. Demote diagnostics to `logging.debug()`. Keep one clean summary line per failure at INFO level.
**Status:** `OPEN`

### P-055: FM error/failure logging audit — alerts and watchlist
**Location:** `strategies/flow_monitor/fm_alerts.py`, `strategies/flow_monitor/fm_watchlist.py`
**Severity:** Visual (diagnostic noise on failure paths)
**Problem:** Extracted from P-034 item 7. Same pattern: audit failure paths for diagnostic leaks to console.
**Fix:** Review all `logging.info()` and `logging.warning()` calls in failure/error handling paths. Demote diagnostics to `logging.debug()`. Keep one clean summary line per failure at INFO level.
**Status:** `OPEN`

### P-056: FM error/failure logging audit — news sentiment and Alpha Vantage
**Location:** `tools/news_sentiment.py`, `core/alphavantage_api.py`
**Severity:** Visual (diagnostic noise on failure paths)
**Problem:** Extracted from P-034 item 7. The empty feed diagnostics were already fixed (P-034 sub-item 3), but other failure paths in these files may still leak diagnostics to console.
**Fix:** Review remaining `logging.info()` and `logging.warning()` calls in failure/error handling paths. Demote diagnostics to `logging.debug()`. Keep one clean summary line per failure at INFO level.
**Status:** `OPEN`

### P-057: Session Summary box — new accumulators and enriched display
**Location:** `strategies/flow_monitor/fm_session_stats.py`, `strategies/flow_monitor/fm_main.py` (cycle loop), `main_runners.py` (`_display_session_summary()`)
**Severity:** Content (missing end-of-day metrics)
**Problem:** Extracted from P-035 Piece B. The session summary box shows per-phase timing (added in P-035 Piece A) but is still missing several useful operational metrics that would give comprehensive end-of-day visibility.

**New accumulators needed in FMSessionStats:**
1. `total_alerts` + `alerts_by_severity` — from `alerts.process_alerts()` return
2. `total_contracts_scanned` — from collector contract count
3. `watchlist_created` + `watchlist_updated` — from `fm_watchlist.update_daily_watchlist()` return
4. `dips_detected` — from `fm_watchlist.update_prices_and_detect()` return
5. `symbol_count` — from `len(symbols)` (constant, set once)
6. `first_cycle_start` + `last_cycle_end` — from cycle start/end timestamps
7. `sync_times` — from `run_quick_sync()` return

**Each accumulator needs:**
- Field in `__init__()`
- Accumulation in `record_cycle()` (may need new params or richer timings dict)
- Exposure in `get_summary()`
- Persistence in `save_to_daily_state()` / `load_from_daily_state()`
- Display in `_display_session_summary()` (conditional — skip if zero)

**Target additions to session summary box:**
```
Universe: 746 symbols | ~108K contracts/cycle
Market hours: 9:30 AM – 4:00 PM (6.5 hours)
  Sync:       avg 135.1s
Alerts: 14 total (4 HIGH, 10 MEDIUM)
Watchlist: 6 created, 12 updated
Dips detected: 5
```
**Status:** `OPEN`

### P-058: Coffee break "Up Next" wrong on Fridays — STEP_SEQUENCE is linear but Friday branches
**Location:** `main.py:154` (`STEP_SEQUENCE`), `main.py:532` (coffee break call)
**Severity:** Visual (incorrect label)
**Problem:** `STEP_SEQUENCE` is a flat list: `..., Daily Backup, Autofix Review, Weekly Backup, ...`. On Fridays, the coffee break before Step 5.1 uses `after_step="Daily Backup"`, which resolves "Up Next" to "Autofix Review" — but the actual next step is "Weekly Backup". The linear sequence doesn't model the Friday branch.
**Fix:** Two options: (A) Change `after_step` on the Friday coffee breaks to point directly into the Friday portion of the sequence (e.g., `after_step="Autofix Review"` so it resolves to "Weekly Backup"), or (B) add a `next_step` override param to `coffee_break()` that bypasses the sequence lookup. Option A is simpler — just requires the right `after_step` values for the 3 Friday coffee breaks. The sequence itself stays as-is.
**Status:** `DONE` — Agent session, 2026-02-20. Changed after_step="Daily Backup" to after_step="Autofix Review" on the first Friday coffee break.

### P-059: Weekly backup mission box says "SQLite native backup API" but uses shutil.copy2
**Location:** `main_runners.py:1242-1251` (shared mission box), `main_runners.py:1281` (actual copy)
**Severity:** Copy inaccuracy
**Problem:** The mission box for weekly backup says "Method: SQLite native backup API with progress tracking". The weekly backup doesn't use the backup API — it copies the daily backup file via `shutil.copy2`. The mission box text is shared between daily/weekly but the method differs.
**Fix:** Conditionally set the "Method" line based on `backup_type`. Daily: "SQLite native backup API with progress tracking". Weekly: "File copy from daily backup (datalake_backup.db)".
**Status:** `DONE` — Agent session, 2026-02-20. Made Method line conditional: file copy for weekly, SQLite backup API for daily.

### P-060: Weekly backup — add progress logging and file size to completion box
**Location:** `main_runners.py:1264-1324` (weekly backup path)
**Severity:** Content (missing metrics + 5 minutes of silence)
**Problem:** The weekly backup copies an ~11GB file via `shutil.copy2`, which takes ~5 minutes with zero console output. The completion box says "Backup completed in 4.9 min" but doesn't report the file size. Two improvements: (1) Add chunked copy with progress reporting (e.g., every 1GB: "Copying... 4.2 / 11.2 GB"), and (2) include file size in the completion box ("Backup: 11.2 GB in 4.9 min").
**Fix:** Replace `shutil.copy2` with a chunked copy using `shutil.copyfileobj` (or manual read/write loop with ~64MB chunks). Report progress via `beautiful_log` or `logging.info` at regular intervals. After copy, `os.path.getsize()` on the result for the completion box. Preserve file metadata with `shutil.copystat` after the chunked copy (replaces `copy2`'s automatic metadata preservation).
**Status:** `DONE` — PM session, 2026-02-21. Replaced shutil.copy2 with 64MB chunked copy, progress every 1GB, file size in completion box via backup_size variable. shutil.copystat preserves metadata.

### P-061: Earnings weekly refresh — suppress yfinance HTTP 404 noise
**Location:** `strategies/earnings_intel/ei_fetch_upcoming.py:111` (yfinance call), `strategies/earnings_intel/ei_main.py:79-82` (tree preview)
**Severity:** Visual (noise — ~19 bare "HTTP Error 404:" lines per run)
**Problem:** yfinance itself prints `HTTP Error 404:` to stdout/stderr when a symbol has no earnings data on Yahoo Finance. Our code catches the exception at `ei_fetch_upcoming.py:138` and logs at debug — that's correct. But yfinance's own print leaks through before the exception is caught. ~21 of 746 symbols trigger this, producing 19+ bare `HTTP Error 404:` lines with no symbol context.
**Fix:** Two-part: (1) Redirect stdout/stderr around the `yf.Ticker(symbol).calendar` call using a context manager (e.g., `contextlib.redirect_stderr(io.StringIO())`). (2) After the fetch loop completes, add one summary line: `"21 symbols: no earnings data available"` at INFO level.
**Note:** Also remove the tree preview (lines 79-82 in `ei_main.py`) — the mission box already describes the 3 steps, and `[1/3]`, `[2/3]`, `[3/3]` announce each step inline. The tree is a third repetition.
**Status:** `DONE` — Agent session, 2026-02-20. Added stderr redirect around yfinance calls, added no-data summary line, removed tree preview from ei_main.py.

### P-062: Earnings weekly refresh — early cleanup line out of sequence
**Location:** `strategies/earnings_intel/ei_fetch_upcoming.py:143-155` (`_cleanup_past_earnings()`), caller in `ei_fetch_upcoming.py`
**Severity:** Visual (confusing sequencing)
**Problem:** The line `"Cleaned up 93 past earnings records"` appears at 19:08:08, before the fetch progress reporting begins and well before `[2/3]` and `[3/3]` which are the archive/cleanup steps. This is a pre-cleanup that runs inside the fetcher before the main loop. It's confusing because it looks like Step 3 happened before Step 1.
**Fix:** Either (A) demote the pre-cleanup log to `logging.debug()` (it's a fetcher internal detail), or (B) move it under a labeled context like `"  Pre-fetch cleanup: removed 93 expired records"` so it's clearly separate from the [1/3]-[2/3]-[3/3] sequence.
**Status:** `DONE` — Agent session, 2026-02-20. Relabeled early cleanup as "Pre-fetch cleanup" for clarity.

### P-063: Friday archive — remove redundant context box
**Location:** `main_runners.py:1753-1761` (the "⏳ FRIDAY ARCHIVE OPERATION" `create_status_box` call)
**Severity:** Visual (redundancy)
**Problem:** Two boxes appear back-to-back before any archive work starts. The mission box ("📦 FRIDAY SECTOR ARCHIVE OPERATION") has the real info: mission, time available, tiers, process. The context box ("⏳ FRIDAY ARCHIVE OPERATION") immediately follows with filler: "Database integrity is maintained throughout", "Weekend - extended time for complete archival". It adds no information.
**Fix:** Delete the second `create_status_box()` call (lines 1753-1761). The mission box at line 1730 is sufficient.
**Status:** `DONE` — Agent session, 2026-02-20. Deleted redundant context box and context_lines from run_friday_sector_archive().

### P-064: Sector archive subprocess — P-006 formatter split
**Location:** `data/health/db_archive_sector.py` (logging setup)
**Severity:** Visual (verbose timestamps in streamed output)
**Problem:** Same P-006 pattern as metadata and db_backup. The subprocess uses full `2026-02-20 19:11:36 - INFO - [DB_ARCHIVE] -` format which is verbose when streamed to the orchestrator console. Needs the split formatter: short format for console (`StreamHandler`), full format for file (`FileHandler`).
**Fix:** Apply same pattern as P-006 fixes in `symbol_metadata.py` and `db_backup.py`: explicit `StreamHandler` with `'%(asctime)s - %(message)s'` (datefmt `'%H:%M:%S'`) and `FileHandler` with full format. The `[DB_ARCHIVE]` tag should stay in the file format but doesn't need to be on every console line.
**Status:** `DONE` — Agent session, 2026-02-20. Split formatters: console gets HH:MM:SS short format, file keeps full format. Set propagate=False.

### P-065: Sector archive — consolidate print/logging duplication
**Location:** `data/health/db_archive_sector.py` (throughout — header, pre-flight, tier headers, table headers)
**Severity:** Visual (every event logged twice)
**Problem:** The script uses both `print()` for decorative console output and `logging.info()` for forensic logging. When streamed through `_run_streaming_subprocess()`, both reach the console, creating pairs:
- Pre-flight: `✅ Pre-flight check: Database is writable` (print) + `Pre-flight check PASSED: database is writable` (logging)
- Tier headers: `══ TIER 1: HIGH-FREQUENCY DATA ══` (print) + `TIER 1 START: 15-day retention, MOVE mode` (logging)
- Table headers: `Archiving flow_options_scans (cutoff: 2026-02-05, mode: MOVE)` (print) + same info in logging
- Sector start: `Processing airlines: 91,917 rows` (print) + `flow_options_scans | airlines: 91,917 rows to process` (logging)
**Fix:** After P-064 (formatter split), the print lines are the clean console output and the logging lines are the forensic record. The decorative `======` banners and `✅` pre-flight can stay as print() for console beauty. The logging lines should NOT duplicate — they should add detail the print lines don't have (e.g., timing, cumulative counts). Audit each pair and either: (A) demote the logging line to debug if the print line covers it, or (B) remove the print line if the logging line (with short format from P-064) is cleaner.
**Depends on:** P-064
**Status:** `DONE` — Agent session, 2026-02-21. Demoted duplicate logger lines to debug where print() covers same info. Kept logger.info for lines with additional data not in print output (table names, retention days, deleted counts, row totals).

### P-066: Sector archive — schema migration noise (45 lines for 1 column)
**Location:** `data/health/db_archive_sector.py` (schema sync / column migration)
**Severity:** Visual (noise — 3 lines × 15 sectors = 45 lines)
**Problem:** When a new column exists in the source but not in a sector archive, the script logs 3 lines per sector: `🔧 Updating flow_alerts schema: adding 1 missing columns`, `Adding 1 missing columns to flow_alerts in airlines.db`, `Added column: scan_interval_seconds INTEGER`. This repeats for all 15 sectors. The first occurrence is informative; the rest are noise.
**Fix:** Log the first occurrence at INFO, subsequent at DEBUG. After the table loop completes, add one summary: `"Schema sync: added scan_interval_seconds to flow_alerts in 15 sector archives"`. Alternatively, collect all migrations and report once at the end of the table.
**Note:** Also fix the double `[DB_ARCHIVE]` tag — message text starts with `[DB_ARCHIVE]` and the logger formatter also adds it, producing `[DB_ARCHIVE] - [DB_ARCHIVE] Adding...`.
**Status:** `DONE` — Agent session, 2026-02-20. Removed [DB_ARCHIVE] from message strings, schema migration first-only INFO with summary, rest at DEBUG.

### P-067: Sector archive — suppress single-batch progress for small sectors
**Location:** `data/health/db_archive_sector.py` (batch progress loop)
**Severity:** Visual (noise — 3 lines for 58-row copy, worst case: 3 lines for 1 row)
**Problem:** Small sectors (e.g., flow_alerts airlines: 58 rows) get full batch treatment: "58 rows to process" → "Batch 1: 58 rows copied (100.0%)" → "✓ airlines: 58 rows copied". Three lines for a 1-second operation. The batch progress line adds nothing when there's only 1 batch. Worst case in Tier 3: `earnings_events | utilities: 1 rows to process` → `Batch 1: 1 rows copied (100.0%)` → `✓ utilities: 1 rows copied` — three lines for ONE row.
**Fix:** Only print the `[HH:MM:SS] Batch N:` progress line when there are 2+ batches. The "rows to process" and "✓ done" lines are still useful for the forensic record. This removes ~10-12 redundant lines per small table.
**Additional scope:**
- For zero-row tables (`news_symbol_sentiment`, `news_articles`), collapse to single line: `"news_symbol_sentiment: 0 rows (skipped)"`
- For broadcast tables (`market_daily_summary` → all 15 sectors), collapse per-sector lines into one: `"✓ market_daily_summary: 4 rows copied to 15 sectors (60 total)"`
- Grammar: `"1 rows"` → `"1 row"` (singular when count == 1)
**Status:** `DONE` — Agent session, 2026-02-20. Single-batch suppression, zero-row skip, broadcast collapse, grammar singular.

### P-068: Sector archive — Tier completion duration in human-readable format
**Location:** `data/health/db_archive_sector.py` (tier completion print blocks)
**Severity:** Visual (readability)
**Problem:** Tier completion lines show raw seconds: `"TIER 1 COMPLETE - Duration: 5365.5 seconds"`. The logging line (`TIER 1 COMPLETE: 7,337,840 archived, 7,335,566 deleted in 5365.5s`) is fine for parsing, but the print banner should be human-readable.
**Fix:** Format duration in the print banner: `"Duration: 1h 29m"` (or `"16.0 min"` for Tier 2, `"20.5s"` for Tier 3). Keep raw seconds in the logging line for forensic grep.
**Additional scope:** Same pattern applies to VACUUM (`"2204.0 seconds"` → `"36.7 min"`) and ARCHIVE COMPLETE banner (`"21496.8 seconds (358.3 minutes)"` → `"5h 58m"`). All three locations in `db_archive_sector.py`.
**Status:** `DONE` — Agent session, 2026-02-20. Added _format_duration() helper, human-readable durations on print lines, raw seconds kept in logging lines.

### P-069: Sector archive optimizer — 270 lines of noise for 15 ANALYZE calls
**Location:** `data/health/db_archive_sector.py:1313-1347` (`optimize_sector_archives_subprocess()`), `data/health/db_optimize_sectors.py`
**Severity:** Visual (extreme noise — ~18 lines per sector × 15 sectors = ~270 lines)
**Problem:** Post-archive optimization spawns a **separate subprocess per sector** (`subprocess.run([..., '--sector', sector])` in a loop). Each invocation of `db_optimize_sectors.py` prints its own full banner (SECTOR ARCHIVE OPTIMIZER + `======`), logging duplicate of the banner, "Optimizing 1 sector archive(s)...", the actual result (2 useful lines: ANALYZE time + DB size), then completion banner + logging duplicate. That's ~18 lines per sector for ~2 lines of content. 15 sectors = ~270 lines for what should be ~18.
**Root cause:** The optimizer script is designed for standalone CLI use with full banners. When called 15 times in a loop from the archiver, each invocation repeats the ceremony.
**Fix — two options:**
- **Option A (preferred):** Replace subprocess calls with direct Python function import. `db_optimize_sectors.py` already has the optimization logic in callable functions. Import and call directly from `db_archive_sector.py`, printing one progress line per sector: `"  ✓ airlines: 1,038 MB in 62s"`. Add a header (`"Post-Archive Cleanup: Optimizing 15 sector databases..."`) and a summary total at the end. The standalone script keeps its banners for CLI use.
- **Option B (minimal):** Keep subprocess approach but add a `--quiet` flag to `db_optimize_sectors.py` that suppresses banners and prints only the result line. Call with `--quiet` from the loop.
**Target output:**
```
Post-Archive Cleanup: Optimizing 15 sector databases...
  ✓ airlines: 1,038 MB in 62s
  ✓ asset_management: 7,636 MB in 9.7 min
  ✓ basic_materials: 3,428 MB in 4.1 min
  ...
  ✓ utilities: 482 MB in 19s
Optimization complete: 15/15 sectors, total: 42.7 min
```
**Status:** `DONE` — Agent session, 2026-02-21. Replaced 15 subprocess calls with direct function import. Extracted optimize_sector_archive() from db_optimize_sectors.py. ~270 lines reduced to ~18.

### P-070: FRIDAY ARCHIVE COMPLETE box — enrich with subprocess metrics
**Location:** `main_runners.py:1775` (completion `create_status_box` call)
**Severity:** Content (missing metrics — box has zero data)
**Problem:** The FRIDAY ARCHIVE COMPLETE box says: `"Archive status: Completed successfully"` and `"Friday operation: Finished before Monday cutoff"`. Meanwhile the subprocess just printed: 7,955,921 rows archived, 7,953,596 rows deleted, 4,160 MB reclaimed via VACUUM, 5h 58m total duration. None of that reaches the orchestrator's completion box.
**Fix:** Parse the subprocess stdout for key metrics (same pattern as the daily backup box parsing "Backup completed: X.X GB in Y.Y minutes"). Look for:
- `"Total rows archived: N"` → rows_archived
- `"Total rows deleted: N"` → rows_deleted
- `"Space reclaimed: X MB (Y%)"` → space_reclaimed
- `"Total Duration: Ns"` → duration
Build enriched box:
```
╔═══════════════════════════════════════════════════╗
║ ✅ FRIDAY ARCHIVE COMPLETE                        ║
╠═══════════════════════════════════════════════════╣
║ Archived: 7,955,921 rows across 15 sectors        ║
║ Deleted: 7,953,596 rows from production            ║
║ VACUUM: 4,160 MB reclaimed (36.3%)                ║
║ Duration: 5h 58m                                   ║
║ Status: Finished before Monday cutoff              ║
╚═══════════════════════════════════════════════════╝
```
**Status:** `DONE` — PM session, 2026-02-21. Parse subprocess stdout for Total rows archived/deleted, Space reclaimed, Total Duration. Build enriched box with all metrics.

---

## Recurring Patterns

### beautiful_log() is available system-wide
`tools/log_utils.py:127` exports a standalone `beautiful_log(message, level)` function. Any module — orchestrator, strategy, utility — can import and use it for user-facing console output with consistent `emoji HH:MM:SS - message` format. The orchestrator's `self.beautiful_log()` is a thin delegate to this function. **Use beautiful_log for user-facing announcements; use logging.info() for forensic/progress detail.** For subprocesses run via `_run_streaming_subprocess()`, beautiful_log output passes through cleanly (raw `sys.stdout.write()`, no re-wrapping).

### Prefer beautiful_log() for orchestrator messages
Any orchestrator-level operational message visible in the console should use `beautiful_log()` rather than raw `logging.info()`. This ensures uniform format (`emoji HH:MM:SS - message`) and correct simulated time. Watch for this pattern throughout the review.

### Subprocess log format noise
When we see `YYYY-MM-DD HH:MM:SS - INFO -` from a strategy subprocess, that's a candidate for P-006. Track all affected subprocesses there.

### print() vs logging.info() — console beauty vs log file coverage
Metadata collector demonstrates the tradeoff: `print()` gives clean, prefix-free console output but nothing reaches the log file. `logging.info()` with P-006 short format gives nearly-as-clean console output AND log file coverage. **Default to `logging.info()`** for progress lines. Reserve `print()` for purely decorative elements (borders, headers) where log file capture has no value. Metadata collector (P-018), OI Timing (P-010), and DB Sync (P-020) all need this conversion.

---

## Future Consideration: Console vs Text Log Content Architecture

**Observed during this review — seed notes for a future refactor.**

The current system writes identical content to both console and text log (via `log_utils.py`'s dual `_safe_print()` + `_write_to_file_handler()` pipeline). This review revealed that the two outputs serve fundamentally different audiences with different needs:

**Console log (the live viewer):**
- Audience: Ben, watching the system run in real time
- Needs: Visual structure (boxes, borders, blank lines), heartbeat progress (proof the system is alive during long waits), decorative framing, "Up Next" awareness
- Tolerates: Noise, redundancy, purely visual elements
- Key question: "What is happening RIGHT NOW?"

**Text log (the forensic record):**
- Audience: Ben (or Claude) debugging after the fact, possibly hours or days later
- Needs: Timestamps on every meaningful event, key metrics (counts, durations, sizes), error context, start/end markers per step — grep-friendly
- Does NOT need: Box borders (`║═╗`), coffee break announcements, heartbeat page counts, decorative headers, celebration lines
- Key question: "What HAPPENED, and how long did it take?"

**Logging type taxonomy emerging from this review:**

| Type | Console | Text Log | Example |
|------|---------|----------|---------|
| **Forensic** | Yes | Yes | `Source: datalake.db (10.40 GB)`, `Sync completed in 14.0 min` |
| **Heartbeat** | Yes | No | `Progress: 30000/2726175 pages (1.1%)` |
| **Decorative** | Yes | No | `======` borders, `COLLECTION SUMMARY` headers |
| **Structural** | Yes | Compact form | Boxes → one-line summary in log; coffee breaks → skip entirely |
| **Error/Warning** | Yes | Yes (always) | `❌ ERROR: Sync failed`, `⚠️ Schema mismatch` |

**What this implies for the next refactor:**
- `create_status_box()` could write the box to console but a one-line summary to the log file
- Coffee breaks could skip the log file entirely (or log a single `☕ Waiting 60s, next: Earnings Arbitrage Scanner` line)
- A `log_forensic()` helper could route to both outputs while `log_heartbeat()` routes to console only
- The `_write_to_file_handler()` path in `log_utils.py` would need content-aware routing, not just format differences

**Not in scope for this punchlist** — but captured here so we don't lose the insight when we revisit text log architecture.
