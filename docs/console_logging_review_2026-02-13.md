# Console Logging Review - Option Pipeline Evening Run
**Date:** 2026-02-13
**Reviewer:** Claude (with Ben)
**Scope:** `main.py` orchestrator console output for the evening Option Pipeline run

---

## Design Principles (Reference)

Per project conventions:
- **Orchestrator** (`main.py`/`main_runners.py`) owns all visual structure: phase headers, mission boxes, completion boxes
- **Strategies** own progress output only: per-symbol lines, warnings, batch counters
- All formatted output flows through `tools/log_utils.py` (console + log file)
- Completion summaries built from structured return values, never hardcoded

---

## Phase 2: Symbol Rollup

### Issue 2.1 — Progress logging too sparse
**File:** `strategies/option_pipeline/op_symbol_rollup.py:110-112`
**Severity:** UX

Progress logs every 500 symbols, but with batch_size=100 and 747 symbols, only 2 of 8 batches ever print:
- Batches 1-4 (100-400): **silent** — `100%500 != 0`, etc.
- Batch 5 (500): logs
- Batches 6-7 (600-700): **silent**
- Batch 8 (747): logs (matches `== len(all_symbols)`)

Result: ~2 minutes of silence, then "500/747", then "747/747". Feels truncated.

**Fix:** Change interval from 500 to 200 (or log every batch).

### Issue 2.2 — Strategy owns a completion box
**File:** `strategies/option_pipeline/op_symbol_rollup.py:1349-1374`
**Severity:** Design violation

`_log_completion_stats()` produces a full `====` bordered summary block with 10 lines of stats. Per design rules, the orchestrator should build this from the `stats` dict that `process_symbols()` returns.

---

## Phase 3: OI Timing Analysis

### Issue 3.1 — Progress logging every 100 is excessive
**File:** `strategies/option_pipeline/op_timing_calculator.py:153-155`
**Severity:** UX

Logs every 100 contracts out of ~13,400 = **134 progress lines**. Drowns the console.

**Fix:** Change from 100 to 1000.

### Issue 3.2 — No detail on skipped contracts
**File:** `strategies/option_pipeline/op_timing_calculator.py:139-151`
**Severity:** Diagnostic gap

75 contracts were skipped but there's no info on which symbols or why. `calculate_timing_for_contract()` has 3 silent early-return paths:
- Line 62-63: `len(rows) < 2` (insufficient history)
- Line 68-69: `current_oi <= 0`
- Line 81-82: OI never reached 50% threshold

All return `(None, None)` with no logging. Should collect skipped symbol names and skip reasons, report a summary at the end.

### Issue 3.3 — Duplicate completion output
**Files:** `op_timing_calculator.py:160` + `op_main.py:610-614`
**Severity:** Design violation

Two completion announcements:
1. Strategy prints `[OK] Completed 2026-02-13: 13356 contracts updated, 75 skipped` (via `print()`)
2. `op_main.py` logs `OI timing analysis completed successfully!` with a tree-formatted block (via `logging.info()`)

### Issue 3.4 — Strategy owns formatted completion summary
**File:** `strategies/option_pipeline/op_main.py:608-614`
**Severity:** Design violation

The `op_main.py` wrapper produces a tree-formatted completion block. This should be the orchestrator's job.

### Issue 3.5 — Raw print() bypasses log file
**File:** `strategies/option_pipeline/op_timing_calculator.py:108, 122, 155, 160`
**Severity:** Logging gap

All output in `op_timing_calculator.py` uses `print()` instead of `logging`. These lines reach the console but never appear in log files.

---

## Phase 4: Health Report + Pipeline Completion

### Issue 4.1 — Health check silently fails every run (KeyError: 0)
**File:** `strategies/option_pipeline/op_main.py:772, 782, 792, 801`
**Severity:** Bug (functional)

`query_db()` returns **dicts** (`op_storage.py:1788`), but the health check accesses rows by numeric index:
```python
collected_symbols = set([row[0] for row in collected_result])  # line 772 — KeyError
analyzed_count = analysis_result[0][0]                         # line 782 — KeyError
momentum_count = momentum_result[0][0]                         # line 792 — KeyError
rollup_count = rollup_result[0][0]                             # line 801 — KeyError
```

`dict[0]` raises `KeyError(0)`. When formatted as `"{}".format(e)`, it prints as just `0`.

**Result:** Health check fails silently on every run, always returns UNKNOWN status. The health report file is generated with no real health data. The warning message `Pipeline health check error: 0` is cryptic and non-actionable.

**Fix:** Use column names: `row['symbol']`, `result[0]['count']`, etc.

### Issue 4.2 — Double completion announcement
**Files:** `op_main.py:745` + `main_runners.py:543, 564`
**Severity:** Design violation

Two separate completion outputs:
1. **Strategy** (`op_main.py:745`): `create_success_celebration("OPTION PIPELINE", accomplishments)` — plain text summary
2. **Orchestrator** (`main_runners.py:543+564`): `beautiful_log()` success line + `create_status_box("EVENING OPTION PIPELINE COMPLETE", ...)` — formatted box

Per design rules, only the orchestrator's box should remain. The strategy's `create_success_celebration` call should be removed.

---

## Query Database Sync

### Issue 5.1 — Progress logging every 1,000 pages is absurd at scale
**File:** `data/health/db_backup.py:1372-1374`
**Severity:** UX

Logs every 1,000 pages out of ~3.2M = **~3,200 progress lines**. At 12 GB, this dominates the console for the entire 19-minute sync.

**Fix:** Change from 1,000 to 30,000 (~107 lines for 3.2M pages).

### Issue 5.2 — Six separate completion/status announcements
**Severity:** Design violation (egregious)

The sync operation produces **six** announcements on success:

| # | Source | Line | Output |
|---|--------|------|--------|
| 1 | `db_backup.py` | backup callback | `Backup completed: 3207639 pages (12.24 GB)` |
| 2 | `db_backup.py` | :1441 | `Sync completed successfully in 18.7 minutes` + 3-line detail block |
| 3 | `db_backup.py` | :1553 | `QUERY DATABASE SYNC SUCCESSFUL` + 2-line detail block |
| 4 | `db_backup.py` | :1592 | `Sync lock file removed - readers can now access database` |
| 5 | `main_runners.py` | :1501 | `QUERY DATABASE SYNC COMPLETED SUCCESSFULLY` (beautiful_log) |
| 6 | `main_runners.py` | :1514 | `QUERY SYNC OPERATION COMPLETE` box |

Per design rules, only **one** should remain: the orchestrator's completion box (#6). The script (`db_backup.py`) should return structured results and let the orchestrator handle all formatting.

### Issue 5.3 — Script produces visual structure (banners, boxes)
**File:** `data/health/db_backup.py`
**Severity:** Design violation

The script outputs its own `======` banners and formatted blocks. As a tool/utility called by the orchestrator, it should return data and leave visual formatting to the caller.

---

## Database Backup (Daily)

### Issue 6.1 — "No operation specified" message leaks into production output
**File:** `data/health/db_backup.py:1750-1751`
**Severity:** Bug (cosmetic)

When the orchestrator invokes `db_backup.py` without explicit flags, it falls through to a default handler that prints:
```
No operation specified. Use --help to see available options.
Running default operation: disaster backup
```

This is a CLI help message — shouldn't appear in orchestrator output. Either the orchestrator should pass `--disaster` explicitly, or the script shouldn't print these lines when invoked programmatically.

### Issue 6.2 — WAL/SHM file notice is noise
**File:** `data/health/db_backup.py:562-570`
**Severity:** UX (low)

Prints a 4-line block about WAL/SHM files every run:
```
SQLite auxiliary files detected:
   - WAL file: data/datalake.db-wal (25.1 MB)
   - SHM file: data/datalake.db-shm (0.1 MB)
   Note: These files may indicate recent write activity
```

WAL/SHM will **always** exist after evening collection just finished. This is expected state, not a warning. Should be DEBUG level at most, or removed entirely.

### Issue 6.3 — No progress logging during 6.2-minute backup
**File:** `data/health/db_backup.py` (disaster backup path)
**Severity:** UX

The query sync logs 3,200 progress lines (too many). The daily backup logs **zero** progress lines during a 6.2-minute operation (too few). Inconsistent — the backup function apparently doesn't use the same page-level progress callback that the sync does.

Should have progress logging at the same 30,000-page interval recommended for query sync.

### Issue 6.4 — Five completion announcements (same pattern)
**Severity:** Design violation

| # | Source | Line | Output |
|---|--------|------|--------|
| 1 | `db_backup.py` | :585 | `Backup completed in 6.2 minutes` |
| 2 | `db_backup.py` | :587-598 | Verification block (size match, schema match) |
| 3 | `db_backup.py` | :600 | `DISASTER BACKUP SUCCESSFUL` |
| 4 | `db_backup.py` | :602 | Logger: `Disaster backup completed successfully in 6.2 minutes` |
| 5 | `main_runners.py` | | `DATABASE BACKUP COMPLETED SUCCESSFULLY` + completion box |

Same as query sync — tool should return results, orchestrator formats one summary.

### Issue 6.5 — Script produces visual structure (banners)
**File:** `data/health/db_backup.py:504`
**Severity:** Design violation

The disaster backup path outputs its own `======` banner with "DISASTER RECOVERY BACKUP" header. Same issue as query sync (5.3).

---

## Weekly Backup (Friday)

### Issue 7.1 — 5+ minutes of complete silence during 12 GB file copy
**File:** `main_runners.py:1266`
**Severity:** UX

The weekly backup is a `shutil.copy2()` of the daily backup (12.24 GB). This runs for ~5 minutes with zero output — just "Initializing backup operation..." then nothing until "COMPLETED SUCCESSFULLY".

Unlike the daily backup (which invokes `db_backup.py` as a subprocess), the weekly path is an inline file copy with no progress callback.

**Fix:** Either use `shutil.copyfileobj()` with a chunked loop to report progress, or just log a "Copying 12.24 GB from daily backup (this takes ~5 minutes)..." message so the user isn't staring at a frozen terminal.

### Issue 7.2 — Completion box has no useful info
**File:** `main_runners.py:1282-1287`
**Severity:** UX (minor)

The completion box says:
```
Backup file: datalake_backup_weekly.db
Status: Backup completed successfully
Protection: Database secured
System: Ready for safe operations
```

No file size, no duration, no source info. Compare to daily backup which at least had verification output. The box is generic filler — "System: Ready for safe operations" adds nothing.

### Issue 7.3 — Mission box is overdetailed for a file copy
**Severity:** UX (minor)

The mission box describes "SQLite native backup API with progress tracking" — but the weekly backup doesn't use the SQLite backup API at all. It's `shutil.copy2`. The mission box is copy-pasted from the daily backup template and doesn't reflect what actually happens.

---

## Earnings Weekly Refresh (Friday)

### Issue 8.1 — HTTP 404 errors with no context, not counted as errors
**Files:** `ei_fetch_upcoming.py:141-143`, yfinance internal logging
**Severity:** Bug (diagnostic)

~20 `HTTP Error 404:` lines appear in the output, but:
- **No symbol name** — just `HTTP Error 404:` with nothing after the colon
- **Not counted** — the summary says `Errors: 0`

Root cause: These 404s come from **yfinance's internal logging** at ERROR level. When yfinance gets a 404 for a symbol, it logs the raw HTTP error itself, then catches the exception internally and returns empty data. Our code (`_fetch_symbol_earnings`) sees no data → returns `None` → doesn't hit the except block → error counter not incremented.

So `Errors: 0` is technically correct (no exceptions reached our code), but the console shows 20 ERROR-level lines — extremely misleading. The user sees "ERROR" and "Errors: 0" in the same output.

**Fix options:**
1. Suppress yfinance's logger: `logging.getLogger('yfinance').setLevel(logging.CRITICAL)`
2. Or track "symbols with no data" as a separate counter and report at end
3. Or both — suppress the noisy yfinance errors and report our own clean summary

### Issue 8.2 — Numbers don't reconcile between outputs
**Severity:** UX / confusing

The output contains conflicting numbers:
- Fetcher: "Earnings found: **710**", "New insertions: **710**"
- Orchestrator box: "Upcoming earnings: **601**"

The 601 comes from `main_runners.py:1086` which queries `SELECT COUNT(*) FROM earnings_upcoming WHERE earnings_date >= DATE('now')`. So 710 were inserted (some may have earnings dates that already passed this week), then 601 remain as future-dated. This is explainable but never explained — the user sees 710 then 601 and wonders where 109 records went.

Similarly: "Past cleaned: 205" (from fetcher cleanup before fetch) vs "Cleaned up 100 old records" (from step 3 post-archive cleanup) vs "Archived events: 198" (total in archive table, not this run's count). Three different cleanup numbers, all unexplained.

### Issue 8.3 — Mission box step order doesn't match execution
**File:** `main_runners.py:1056-1059` vs `ei_fetch_upcoming.py:68-69`
**Severity:** UX (misleading)

Mission box says:
```
Step 1: Fetch next 90 days of earnings from yfinance
Step 2: Archive past events to earnings_events
Step 3: Cleanup old records from earnings_upcoming
```

But the fetcher runs `_cleanup_past_earnings()` **first** (line 68-69), then fetches. So cleanup happens inside "Step 1" before any fetching. There are actually two cleanups — one inside the fetcher and one as "Step 3".

### Issue 8.4 — Four completion announcements
**Severity:** Design violation

| # | Source | Output |
|---|--------|--------|
| 1 | `ei_fetch_upcoming.py:236-244` | `====` EARNINGS FETCH SUMMARY box |
| 2 | `ei_main.py:185` | `Fetched 710 earnings for 747 symbols` |
| 3 | `ei_main.py:332` | `WEEKLY REFRESH complete:` text block (create_success_celebration) |
| 4 | `main_runners.py:1076+1097` | `WEEKLY REFRESH COMPLETED` + orchestrator box |

### Issue 8.5 — Strategy owns visual structure (tree, banners)
**File:** `ei_main.py:158-161`, `ei_fetch_upcoming.py:236-244`
**Severity:** Design violation

The strategy produces the tree-formatted intro block AND the `====` fetch summary. The fetcher also has its own `main()` block (lines 284-286) that produces yet another `====` banner when run standalone — this doesn't show in orchestrator mode but adds maintenance surface.

### Issue 8.6 — Two redundant "initializing" lines from orchestrator
**File:** `main_runners.py:1065-1068`
**Severity:** UX (minor)

```
🔥 19:29:54 - Initializing earnings weekly refresh
🔥 19:29:54 - Running earnings weekly refresh...
🔄 Fetching earnings calendar, archiving past events, cleanup...
```

Three lines to say "starting". Two `beautiful_log` calls + a `print()`. One line would suffice.

---

## Cross-Cutting Theme: Duplicate Completion Announcements

This pattern repeats across **every phase reviewed**:

| Phase | Strategy/Tool announces | Orchestrator announces | Total |
|-------|------------------------|----------------------|-------|
| Phase 2 (Rollup) | `====` completion box | Orchestrator box | 2 |
| Phase 3 (Timing) | `[OK]` print + tree block | Orchestrator box | 3 |
| Phase 4 (Health + Complete) | `create_success_celebration` | Orchestrator box | 2 |
| Query Sync | 4 separate announcements | 2 (beautiful_log + box) | 6 |
| Daily Backup | 4 separate announcements | 1 (beautiful_log + box) | 5 |
| Weekly Backup | 0 (inline copy) | 2 (beautiful_log + box) | 2 |
| Earnings Refresh | 3 separate announcements | 1 (beautiful_log + box) | 4 |

**Root cause:** No consistent boundary between "strategy reports results" and "orchestrator formats output." Each component was developed independently and added its own completion logging.

**Recommended fix pattern:**
1. Strategies/tools return structured dicts with results
2. Remove all `print()`/`logging.info()` completion blocks from strategies
3. Remove all `====` banners, tree blocks, `[OK]` lines from strategies
4. Orchestrator builds exactly one completion summary from the returned dict

---

## Summary

| # | Phase | Issue | Type | Severity |
|---|-------|-------|------|----------|
| 2.1 | Rollup | Progress interval too wide (500) | UX | Low |
| 2.2 | Rollup | Strategy owns completion box | Design | Medium |
| 3.1 | Timing | Progress interval too narrow (100) | UX | Low |
| 3.2 | Timing | No detail on skipped contracts | Diagnostic | Medium |
| 3.3 | Timing | Duplicate completion output | Design | Medium |
| 3.4 | Timing | Strategy owns completion summary | Design | Medium |
| 3.5 | Timing | Raw print() bypasses log file | Logging | Medium |
| 4.1 | Health | KeyError: 0 — health check always fails | Bug | High |
| 4.2 | Completion | Double completion announcement | Design | Medium |
| 5.1 | Query Sync | Progress interval too narrow (1,000/3.2M) | UX | Medium |
| 5.2 | Query Sync | Six completion announcements | Design | High |
| 5.3 | Query Sync | Script produces visual structure | Design | Medium |
| 6.1 | Backup | CLI help message leaks into output | Bug | Low |
| 6.2 | Backup | WAL/SHM notice is always-present noise | UX | Low |
| 6.3 | Backup | No progress during 6.2-min operation | UX | Medium |
| 6.4 | Backup | Five completion announcements | Design | High |
| 6.5 | Backup | Script produces visual structure | Design | Medium |
| 7.1 | Weekly Backup | 5-min silence during 12 GB copy | UX | Medium |
| 7.2 | Weekly Backup | Completion box has no useful info | UX | Low |
| 7.3 | Weekly Backup | Mission box describes wrong method | UX | Low |
| 8.1 | Earnings Refresh | 404 errors: no context, not counted, "Errors: 0" | Bug | High |
| 8.2 | Earnings Refresh | Numbers don't reconcile (710 vs 601) | UX | Medium |
| 8.3 | Earnings Refresh | Mission box step order wrong | UX | Low |
| 8.4 | Earnings Refresh | Four completion announcements | Design | Medium |
| 8.5 | Earnings Refresh | Strategy owns visual structure | Design | Medium |
| 8.6 | Earnings Refresh | Three "starting" lines | UX | Low |
