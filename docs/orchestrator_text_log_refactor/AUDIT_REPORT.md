# Text Log Refactor — Audit Report

**Created:** 2026-02-20
**Scope:** All files in the orchestrator chain (25 files audited)
**Purpose:** Catalog what data lives where, what goes dark when we flip the routing switches, and what changes are needed before we flip them.

---

## Executive Summary

The audit confirms the core assumption from the kickoff: **the work is adding `logging.info()` summaries to the `run_*()` methods, not rebuilding logging infrastructure.**

Three systemic findings:

1. **Every completion box in `main_runners.py` is sole-sourced.** When we stop writing `create_status_box()` to the log file, the summary of every step's results vanishes. This affects 11 runner methods. The fix is a pattern: after each strategy returns its dict, add `logging.info()` lines extracting key metrics.

2. **`main.py` routes almost everything through `beautiful_log()`.** 26 calls, only 4 `logging.*` calls (all fallbacks for stdout failure). Phase transitions, skip decisions, wait messages — all vanish. Same fix: add parallel `logging.info()` for data-carrying messages.

3. **Subprocess output doesn't reach the log file.** `_run_streaming_subprocess()` writes to `sys.stdout` only. Three other subprocess invocations use different mechanisms but have the same gap. Fix: forward lines to the file handler, strip double timestamps.

The good news: **strategy coordinators and leaf components are mostly solid.** `op_main.py` and `ei_main.py` use `logging.info()` exclusively (zero `beautiful_log` or `create_status_box` calls). FM leaf components are covered except `fm_collector.py`. The data integrity risk is concentrated in the orchestrator layer.

---

## Findings by Layer

### 1. Routing Mechanics (`tools/log_utils.py`)

Three call sites write to the file handler today. Three changes needed:

| Function | File Write (today) | File Write (proposed) | Call Site |
|----------|-------------------|----------------------|-----------|
| `beautiful_log()` | `_write_to_file_handler(message, log_level)` at line 171 | **Remove** | Single call |
| `create_status_box()` | `_write_to_file_handler(line)` at line 212 in render loop | **Remove** | Inside for-loop |
| `phase_header()` | `_write_to_file_handler(line)` at line 244 in render loop | **Replace** with single `logging.info("--- [PHASE X] TITLE ---")` | Inside for-loop |

No other changes to `log_utils.py`. The console output is untouched.

---

### 2. Orchestrator Layer

#### `main.py` — Root orchestrator

**Today:** 26 `beautiful_log()` calls, 3 `create_status_box()` calls, 4 `logging.*` calls (fallbacks only). Zero `logging.debug()`.

**What goes dark:**
- Phase step markers: "Step 1.1: Morning Option Pipeline Refresh", "Step 2: Flow Monitor Pipeline", etc. (15 calls)
- Skip decisions: "Skipping Morning OP - started after 8:45 AM", "Phase 5: Weekly operations skipped (not Friday)" (3 calls)
- State restoration: "Restored N phase results from daily_state.json" (1 call)
- Day-complete box: per-step pass/fail/skip status, counts, runtime (1 box — **high forensic value**)
- Wait/timing messages: "Waiting until 9:15 AM..." (inherited from `main_calendar.py`, see below)
- Errors/warnings: pipeline failure messages (4 calls)

**What already works:** The 4 `logging.*` fallbacks for stdout failure cover completion/error status on that edge case. `print()` calls (8) are pre-logging initialization output (instance check, time simulation) — correctly bypass the log.

**Changes needed:**
- Add `logging.info()` for each phase step marker (15 lines)
- Add `logging.info()` for skip decisions (3 lines)
- Add `logging.info()` for state restoration count
- Add `logging.info()` summary after day-complete box is built (step results, pass/fail/skip counts, runtime)
- Add `logging.info()` for error/warning paths that only use `beautiful_log`

#### `main_runners.py` — Pipeline runners

**Today:** Every `run_*()` method follows the same template: mission box (decorative) -> work -> completion box (sole-sourced data). Zero `logging.info()` for success metrics.

**What goes dark — the systematic pattern:**

| Runner | Data in Completion Box (sole-sourced) |
|--------|--------------------------------------|
| `_display_session_summary` | Cycle counts, timing breakdown (avg/fastest/slowest), collection errors, missing quotes, news enrichment |
| `run_morning_option_pipeline` | Symbols collected, contracts, summaries, OI timing, duration, health, failed symbols |
| `run_evening_option_pipeline` | Same as morning |
| `run_flow_monitor` | Pre-market details, market hours summary, post-market details, total duration |
| `run_earnings_pipeline` | Snapshots, moves, alert count + signal breakdown, top symbols |
| `run_earnings_morning_scan` | Opportunities, high-quality count |
| `run_earnings_weekly_refresh` | Earnings found, archived, cleaned, upcoming count |
| `run_airline_play_phase` | Symbols tracked, contracts tracked |
| `run_database_backup` | Backup size, duration |
| `run_batch_mode_review` | Error queue details, sessions spawned |
| `run_query_database_sync` | Sync size, tables, duration |

**What also goes dark (beautiful_log):**
- FM phase-skip messages ("Market hours detected — skipping pre-market")
- Wait-until messages ("Waiting until 9:30 AM")
- Milestone markers ("Running post-market analysis")
- View recreation ("Query database views recreated")
- Error/warning paths (pipeline failure messages, encoding warnings)

**Subprocess gap (separate from routing changes):**

| Runner | Mechanism | Gap |
|--------|-----------|-----|
| `_run_streaming_subprocess` | `sys.stdout.write()` per line | Console only — backup, sync, archive |
| `run_metadata_collection` | `subprocess.run(capture_output=True)` + `print()` | Console only |
| `run_morning_views` | Custom `Popen` loop, output intentionally suppressed | Neither console nor log |

**Changes needed:**
- For each `run_*()`: after building `status_lines` / `box_lines` from the return dict, add `logging.info()` calls extracting the key metrics. Same data, same code location, one pattern repeated 11 times.
- For `beautiful_log` data-carrying calls: add parallel `logging.info()` (approximately 8 calls)
- Subprocess gap fix: see Section 5 below

#### `main_ui.py` — Display utilities

**Today:** Zero `beautiful_log()`, 1 `create_status_box()` (coffee break), zero `logging.*`. Defines wrapper methods that delegate to `log_utils`.

**What goes dark:** Coffee break box content (context, duration, next step). Low forensic value.

**Changes needed:** None. Coffee breaks are operational pauses, not forensic data.

**Already works well:** Clean delegation pattern. No data hiding.

#### `main_calendar.py` — Market calendar/timing

**Today:** 8 `beautiful_log()` calls, 2 `create_status_box()` calls, zero `logging.*`. Zero `logging.debug()`.

**What goes dark:**
- Holiday detection: "Market holiday detected: 2026-02-16 - Presidents' Day"
- Calendar errors: "Market calendar check failed, using weekday fallback"
- Wait initiation: "Waiting until 9:15 for pre-market..."
- Progress updates: "2.3 hours until pre-market..."
- Wait-for-trading-day box: current time, target date, wait duration, holiday list

**Changes needed:**
- Add `logging.info()` for holiday detection (useful for post-hoc "why didn't it run?" diagnosis)
- Add `logging.info()` for calendar errors/fallback
- Add `logging.info()` for wait initiation (timestamp + target time + operation name)
- Progress updates and wait boxes: low forensic value, skip

---

### 3. Strategy Coordinators

#### `fm_main.py` — Flow Monitor coordinator (DEEP AUDIT)

**Today:** 24 `beautiful_log()` calls, 4 `create_status_box()` calls, 55+ `logging.info()` calls, 39 `logging.warning()`, 18 `logging.error()`, 9 `logging.debug()`. Also has a separate diagnostic logger writing to `logs/diagnostic/flow_monitor_YYYY-MM-DD.log`.

**What goes dark (beautiful_log sole-sourced data):**

| Line(s) | Data | Forensic Value |
|---------|------|----------------|
| 1202-1203 | "Collection complete (1371.9s -- API: 999.4s + DB Write: 180.1s)" | HIGH — per-cycle collection summary |
| 396-400 | "Quick-sync completed: N rows in Xs" | MEDIUM — sync result per cycle |
| 717-721 | "Regime: BULL-MODERATE \| Bullish \| SPY +0.45% \| VIX 14.2" | HIGH — market context |
| 759-762 | "Rollup complete: N summaries from M symbols (Xs)" | MEDIUM — rollup metrics |
| 908 | "Evaluation complete (Xs)" | LOW — just duration |
| 1004-1008 | "Alert resolution: N resolved (X BUILDING, Y CLOSING, Z NEUTRAL)" | HIGH — pre-market results |
| 1023-1027 | "Watchlist sentiment updated: N symbols" | MEDIUM — pre-market results |
| 1041-1043 | "Pre-market updates synced (N alerts, M watchlist rows)" | MEDIUM — pre-market sync |
| 1291-1292 | "News enrichment: N enriched, M skipped, K failed" | MEDIUM — per-cycle news stats |
| 1414 | "Cycle N complete - Performance Breakdown:" | HIGH — cycle completion header |
| 1723/1725 | "Cleanup: N entries archived" / "no expired entries" | LOW — cleanup result |

**What already works well:**
- **Per-cycle performance breakdown (lines 1416-1430)** is `logging.info()` — survives the switch. This is the detailed Collection/Analysis/Alerts/Sync/Total timing split.
- **Rolling averages (lines 1443-1456)** are `logging.info()` — survives.
- **End-of-day summary (lines 1473-1475)** is `logging.info()` — survives.
- **All warnings and errors** use `logging.warning/error()` — survive.
- **Diagnostic logger** writes per-cycle summaries indexed by scan_timestamp to separate file — unaffected.

**Key insight:** The performance breakdown (the most forensically valuable per-cycle data) is already in `logging.info()`. The `beautiful_log` "Collection complete" line is a human-readable milestone that *precedes* the detailed breakdown. When it vanishes, the detailed data is still there — but you lose the visual separator that says "cycle N done, here's why."

**Changes needed:**
- Add `logging.info()` parallels for the 11 sole-sourced `beautiful_log` data points listed above
- The cycle completion header (line 1414) needs a `logging.info()` equivalent — it's the anchor for the performance breakdown that follows
- Pre-market results (alert resolution, sentiment, sync) need `logging.info()` coverage

**Status box data at risk:**
- Post-market completion box (line 1813): task success/failure counts, sub-task details. Add `logging.info()` summary.
- Market hours intro box (line 1111): decorative, safe to lose.

**logging.debug() candidates for promotion:**

| Line | Message | Recommendation |
|------|---------|---------------|
| 141 | "Running {task_name}..." | Promote — task start marker |
| 736 | "Running end-of-day symbol summary rollup..." | Promote — rollup start marker |
| 712 | "Could not fetch regime results: {}" | Leave — truly diagnostic |
| 1574, 1594, 1616, 1709, 1715 | Post-market task completions | Remove — duplicates of `beautiful_log` on same tasks |

#### `op_main.py` — Option Pipeline coordinator

**Today:** Zero `beautiful_log()`, zero `create_status_box()`. ~40 `logging.info()` calls. 1 `logging.debug()`. Has diagnostic logger.

**Already works well.** All phase headers, collection metrics (symbols, contracts, failures), rollup counts, OI timing stats, health assessment — all `logging.info()`. Return dict is comprehensive and well-structured.

**Changes needed:** None for routing. The data at risk is only in `main_runners.py`'s completion boxes that consume the return dict.

**One candidate:** Line 668 `logging.debug("Performing comprehensive pipeline health check...")` — promote to `logging.info()`.

#### `ei_main.py` — Earnings Intelligence coordinator

**Today:** Zero `beautiful_log()`, zero `create_status_box()`. ~45 `logging.info()` calls. Zero `logging.debug()`. Has diagnostic logger.

**Already works well.** Phase labels, result summaries (fetch counts, archive counts, moves calculated, opportunity counts), error handling — all `logging.info()`. Return dicts are comprehensive.

**Changes needed:** None. Same situation as OP — data at risk is only in `main_runners.py`'s completion boxes.

---

### 4. Leaf Components

#### Flow Monitor Leaves

| File | beautiful_log | logging.info | Verdict |
|------|--------------|-------------|---------|
| `fm_collector.py` | 7 (3 milestones, 4 carry unique data) | 33 | **Needs 5 changes** — lines 250, 254, 277, 407, 417 carry symbol counts/contract totals/storage timing as sole source |
| `fm_analyzer.py` | 2 (milestones) | 26 | **Solid, no changes.** Metrics (filter counts, alert counts, timing breakdown) already in `logging.info()` |
| `fm_alerts.py` | 3 (banner + summary) | 21 | **Solid, no changes.** Candidate counts, filter counts, success/failure all in `logging.info()` |
| `fm_watchlist.py` | 1 (email sent notification) | 16 | **Solid, no changes.** Entry creates/updates, dip detection, email summary all in `logging.info()` |
| `fm_health_reporter.py` | 2 (report generated/updated) | 3 | **Solid, no changes.** Report path and health status in `logging.info()` |
| `fm_session_stats.py` | 0 | 0 | **No changes.** Pure data accumulator — logging happens at consumption point (fm_main.py) |

#### Option Pipeline Leaves

| File | beautiful_log | logging.info | Verdict |
|------|--------------|-------------|---------|
| `op_collector.py` | 0 | 16 | **Solid, no changes.** Progress %, success rate, contracts, API calls all in `logging.info()` |
| `op_rollup.py` | 0 | 2 | **Solid, no changes.** Summary stats in `logging.info()`, granular data in `logging.debug()` |
| `op_health_reporter.py` | 0 | 3 | **Solid, no changes.** File I/O only |

#### Earnings Intel + Tools

| File | beautiful_log | logging.info | Verdict |
|------|--------------|-------------|---------|
| `ei_arbitrage_scanner.py` | 0 | 10 | **Acceptable.** 11 `print()` calls in CLI summary mode — standalone use only, doesn't affect orchestrator path |
| `news_sentiment.py` | 0 | 5 | **Acceptable.** 8 `print()` in CLI mode, logging covers orchestrator path |

---

### 5. Subprocess Gap

Four scripts run as subprocesses. Their output reaches the console but not the log file.

| Script | Invoked By | Output Volume | Key Forensic Data | Has Own Timestamps |
|--------|-----------|---------------|-------------------|-------------------|
| `data/symbol_metadata.py` | `run_metadata_collection` (subprocess.run + print) | ~30-50 lines | Success rates per phase, failure lists, beta calculations | Implicit via logging |
| `data/health/db_backup.py` | `run_database_backup` / `run_query_database_sync` (streaming) | ~100-150 lines | Lock detection, retry sequence, duration, size, integrity checks | Yes (explicit) |
| `data/health/db_archive_sector.py` | `run_sector_archive` / `run_friday_sector_archive` (streaming) | ~200-500 lines | Per-tier timing, row counts, batch progress, error breakdown | Yes (explicit) |
| `morning_view/morning_views.py` | `run_morning_views` (custom Popen, suppressed) | ~20-50 lines | Symbol count, data freshness, file generation | Implicit via logging |

**Fix location:** `_run_streaming_subprocess()` in `main_runners.py` lines 122-130. Add `_write_to_file_handler(stripped)` (or `logging.info()`) alongside the `sys.stdout.write()` call. Strip the subprocess's own timestamp prefix before logging (pattern: `split(' - INFO - ', 1)[1]` already proven in console refactor).

**`run_metadata_collection`** uses `subprocess.run(capture_output=True)` + `print()` — switch to `_run_streaming_subprocess()` to get the same fix.

**`run_morning_views`** uses custom `Popen` with intentional suppression — add file-handler forwarding to the capture loop (lines 819-824) even though console output stays suppressed.

---

### 6. logging.debug() Promotion Candidates

~250 `logging.debug()` calls exist across FM and OP. Rather than ruling on each individually, here are the categories:

| Category | Examples | Count (est.) | Recommendation |
|----------|---------|-------------|----------------|
| **Task start/completion markers** | "Running rollup...", "Rollup completed" | ~15 | **Promote to info** — forensic value for sequencing |
| **Cache decisions** | "Using cached expirations", "Cache miss for symbol X" | ~20 | **Leave as debug** — too granular |
| **Filtering reasons** | "Skipping contract: below threshold", "Filtered: low OI" | ~80 | **Leave as debug** — per-contract noise |
| **Algorithm parameters** | "Score components: vol=2.3, oi=1.8, premium=0.5" | ~40 | **Leave as debug** — optimization data, not forensic |
| **Non-fatal error details** | "Could not parse timestamp", "Regex failed for line" | ~30 | **Leave as debug** — unless recurring, handled by error counts |
| **Buffer/batch operations** | "Flushing buffer: 500 rows", "Batch 3/10 complete" | ~15 | **Leave as debug** — internal mechanics |
| **Duplicates of beautiful_log** | Post-market task completions in fm_main.py | 5 | **Remove** — dead weight after routing change |

**Net recommendation:** Promote ~15 task start/completion markers. Leave the rest. Remove the 5 duplicates in `fm_main.py`.

---

## Implementation Checklist

Ordered by the transition plan: fix gaps first, then flip routing switches.

### Phase 1: Add `logging.info()` Coverage (before flipping switches)

**main.py** (~20 additions):
- [ ] Phase step markers (15): "--- [STEP 1.1] Morning Option Pipeline Refresh ---"
- [ ] Skip decisions (3): log reason + timestamp
- [ ] State restoration: log count
- [ ] Day-complete summary: log step results, pass/fail/skip counts, runtime

**main_runners.py** (~25 additions):
- [ ] 11 completion box parallels: extract key metrics from return dict, log before building box
- [ ] ~8 beautiful_log data-carrying calls: add parallel logging.info()
- [ ] `_recreate_query_views()`: add logging.info()

**main_calendar.py** (~3 additions):
- [ ] Holiday detection: log date + description
- [ ] Calendar error/fallback: log exception
- [ ] Wait initiation: log target time + operation name

**fm_main.py** (~15 additions):
- [ ] 11 sole-sourced beautiful_log data points (collection complete, regime, rollup, alert resolution, sentiment update, sync, news enrichment, cycle completion header, cleanup)
- [ ] Post-market completion box parallel
- [ ] Promote 2 logging.debug() to info (task start markers at lines 141, 736)
- [ ] Remove 5 duplicate logging.debug() calls (lines 1574, 1594, 1616, 1709, 1715)

**fm_collector.py** (~5 additions):
- [ ] Lines 250, 254, 277, 407, 417: add logging.info() for symbol counts, contract totals, storage timing

**op_main.py** (1 change):
- [ ] Line 668: promote logging.debug() to logging.info()

### Phase 2: Fix Subprocess Gap

**main_runners.py**:
- [ ] `_run_streaming_subprocess()`: forward each line to file handler with timestamp stripping
- [ ] `run_metadata_collection()`: switch from subprocess.run + print to _run_streaming_subprocess
- [ ] `run_morning_views()`: forward captured lines to file handler (keep console suppression)

### Phase 3: Flip Routing Switches

**tools/log_utils.py** (3 changes):
- [ ] `beautiful_log()` line 171: remove `_write_to_file_handler()` call
- [ ] `create_status_box()` line 212: remove `_write_to_file_handler()` call in render loop
- [ ] `phase_header()` line 244: replace render loop's `_write_to_file_handler()` calls with single `logging.info("--- [PHASE {phase_number}] {title} ---")`

---

## What Already Works Well

These areas need no changes and shouldn't be second-guessed during implementation:

- **`op_main.py`**: Exemplary logging — all metrics via `logging.info()`, comprehensive return dicts, diagnostic logger for summaries. Zero `beautiful_log` or `create_status_box`.
- **`ei_main.py`**: Same pattern as OP. All three mode functions (weekly, daily, morning scan) log via `logging.info()` and return structured dicts.
- **FM per-cycle performance breakdown** (fm_main.py lines 1416-1430): Already `logging.info()`. The detailed Collection/Analysis/Alerts/Sync/Total timing split survives the routing change untouched.
- **FM rolling averages and end-of-day summary**: Already `logging.info()` via FMSessionStats.
- **FM diagnostic logger**: Per-cycle summaries indexed by scan_timestamp, separate file. Unaffected.
- **All logging.warning() and logging.error() calls**: Already reach the log file via standard logging. Unaffected.
- **fm_analyzer.py, fm_alerts.py, fm_watchlist.py, fm_health_reporter.py**: Solid `logging.info()` coverage of all key metrics.
- **All OP leaf components**: Zero `beautiful_log`, all data via `logging.info()`.

---

## Estimated Scope

| Category | Files Changed | Lines Added | Lines Removed |
|----------|--------------|-------------|---------------|
| logging.info() additions | 6 files | ~70 lines | 0 |
| logging.debug() promotions | 2 files | 0 (level change only) | 0 |
| logging.debug() removals | 1 file | 0 | 5 lines |
| Subprocess gap fix | 1 file (main_runners.py) | ~15 lines | ~5 lines |
| Routing switches | 1 file (log_utils.py) | ~3 lines | ~5 lines |
| **Total** | **~8 files** | **~88 lines** | **~15 lines** |

Small, surgical changes. No new framework, no new dependencies, no architectural changes.
