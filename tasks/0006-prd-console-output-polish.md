# PRD: Console Output Polish & Remaining Audit Items

**PRD ID:** 0006
**Date:** 2026-02-11 (updated 2026-02-13)
**Source:** Cross-reference of `ORCHESTRATOR_AUDIT.md` against PRD 0005 — items the first PRD missed
**Prerequisite:** PRD 0005 (Phases A-C complete, Phase D partial)

---

## 1. Introduction / Overview

PRD 0005 addressed the architectural logging problems (shared utility, two-layer display model, strategy deduplication, phase headers, day-end summary). This PRD covers the **remaining console output issues** found during the Feb 10, 2026 audit that were not captured in PRD 0005.

These fall into three categories:
- **Misleading or broken output** — things that display wrong information
- **Missing progress** — long-running operations with zero feedback
- **Unnecessary noise** — output that adds no value in production
- **Inconsistencies** — formatting, naming, and counting mismatches

This is a cleanup PRD. No architectural changes. Each item is independently fixable.

### Already Completed (removed from requirements)

The following items from the original audit have been addressed across sessions:

**Fixed Feb 11 session:**
- Startup countdown timer — reworked to three-tier (30min/15min/1min), 10-second spam removed
- Metadata sample data — removed from production console
- Metadata failed symbols — now shown by name with quotes vs fundamentals breakdown

**Fixed in PRD 0005 implementation:**
- OID → OP terminology throughout
- Phase numbering corrected in op_main.py
- Double output pattern resolved (strategy summaries kept, orchestrator duplicates removed)
- DEBUG lines removed from op_config.py, fm_config.py
- Coffee break countdown simplified to 2 lines
- Shared logging utility (tools/log_utils.py)
- Dynamic welcome banner with all steps
- Honest day-end summary replacing "PERFECT EXECUTION"
- Phase transition headers for all 5 phases
- Emoji stutter fix
- rotate_daily_log() inheritance bug
- beautiful_log() now writes to log file
- View recreation after sync

---

## 2. Goals

1. **No misleading output** — every status line reflects actual results, not assumptions or parsing artifacts
2. **No prolonged silence** — operations over 60 seconds should show at least periodic heartbeat
3. **No dead or mystery output** — every line printed to console should be identifiable and purposeful
4. **Consistent formatting** — timestamps, counts, and descriptions match across modules

---

## 3. Functional Requirements (19 remaining)

### 3.1 Misleading or Broken Output

**1. "Pipeline health check failed: 0" confusing wording**
- File: `strategies/option_pipeline/op_main.py` (health report phase)
- Problem: Reads like the health check itself failed. Actually means "0 failures found."
- Fix: Reword to `"Health check: 0 issues found"` or `"Pipeline health: CLEAN (0 failures)"`

**2. "Email: Sent successfully" — verified or assumed?**
- File: `main_runners.py` → `run_morning_views()` completion box (~line 584)
- Problem: Box claims email was sent, but this may be assumed from return code 0 rather than verified from return data.
- Fix: Only claim "Email sent" if morning_views.py returns confirmation. Otherwise say "Process completed (check email delivery)."

**3. Broken WAL parsing in backup status**
- File: `main_runners.py` → `run_database_backup()` (~line 1140)
- Problem: Status line shows `Status: - WAL file: data/datalake.db-wal (21.2 MB)` — the size-parsing loop grabbed a WAL metadata line instead of actual backup size.
- Fix: Tighten the parsing regex, or just report "Backup completed" without trying to parse size from stdout.

**4. "Snapshots created: 0" looks alarming**
- File: `main_runners.py` → `run_earnings_pipeline()` completion box (~line 785)
- Problem: Shows "Snapshots collected today: 0" which looks like a failure, but `earnings_snapshots` is empty by design (known issue).
- Fix: Either suppress the snapshots line until the table is populated, or add context: `"Snapshots: 0 (collector pending — see known issues)"`

**5. "Evening market data collection" wrong description in post-market box**
- File: `strategies/flow_monitor/fm_main.py` → `run_post_market()` closing box
- Problem: POST-MARKET COMPLETE box references "evening market data collection" which is Step 3.1, not post-market.
- Fix: Update description to reflect actual post-market tasks (backfill, regime, rollup, evaluation).

**6. Post-market task count wrong**
- File: `strategies/flow_monitor/fm_main.py` → `run_post_market()`
- Problem: Says "All 4 post-market tasks successful" but watchlist cleanup makes it 5.
- Fix: Update count to match actual tasks, or derive count dynamically.

**7. "759 symbols" vs "758 symbols" off by one**
- File: `strategies/flow_monitor/fm_main.py` → backfill task box vs progress text
- Problem: Task box says 759, text says 758. One is from config, the other from the actual list.
- Fix: Use same source for both (the actual list length).

### 3.2 Missing Progress Indication

**8. Query DB sync: 36 minutes of silence**
- File: `main_runners.py` → `run_query_database_sync()` (~line 1350)
- Problem: Sync takes ~36 minutes with zero output between "Starting..." and "Completed."
- Fix: Use `_run_streaming_subprocess()` instead of `subprocess.run()` so the sync script's output streams to console. If db_backup.py itself is silent, add periodic size-check logging (e.g., every 5 minutes print current copy progress as % of source size).

**9. Database backup: 4.5 minutes of silence**
- File: `main_runners.py` → `run_database_backup()` (~line 1129)
- Problem: Same pattern — `subprocess.run()` with `capture_output=True` produces no output for ~5 minutes.
- Fix: Same approach — either stream subprocess output or add periodic heartbeat.

### 3.3 Unnecessary Noise

**10. Arbitrage scanner no-op verbosity**
- File: `strategies/earnings_intel/ei_main.py` → `run_morning_scan()`
- Problem: When no earnings report today, outputs ~30 lines to say "nothing to do."
- Fix: When no earnings today, output 1 line: `"No earnings reporting today — scan skipped."` Skip the full pipeline setup/teardown output.

**11. "Version: 2.0 Enhanced | PID | Memory" in FM post-market banner**
- File: `strategies/flow_monitor/fm_main.py` → `run_post_market()`
- Problem: Version string and memory usage are noise. PID is marginally useful.
- Fix: Remove the version/PID/memory line. If PID is needed for debugging, log it to file only.

**12. Coffee break after Friday skip**
- File: `main.py` → `run_smart_endless_operation()` (~line 453)
- Problem: After "Phase 5: Weekly operations skipped," there's still a 60-second coffee break doing nothing.
- Fix: Only coffee_break when the preceding step actually ran.

**13. "Mini-collector successful: 0 / failed: 0" in evaluator**
- File: `strategies/flow_monitor/fm_evaluator.py` (or similar)
- Problem: Unclear what "mini-collector" is. Always shows 0/0. Looks like dead code or a feature that never fires.
- Fix: Investigate. If dead, remove. If alive, rename to something descriptive.

**14. FlowMonitorStorage initialized redundantly**
- File: `strategies/flow_monitor/fm_main.py` → post-market tasks
- Problem: FlowMonitorStorage initialized before rollup AND after rollup AND after evaluation. Each init prints a log line.
- Fix: Initialize once at the start of post-market and pass to tasks that need it, or suppress the init log message after the first.

### 3.4 Inconsistencies

**15. Timestamp format varies across modules**
- Affected files: fm_main.py, op_main.py, various strategies
- Problem: Three formats in use:
  - `16:30:01,820` (logging default with comma milliseconds)
  - `16:30:01` (beautiful_log / custom format)
  - `20260211_152954` (compact timestamp in FM collection)
- Fix: Standardize on `HH:MM:SS` for console output. The compact format is fine for filenames but not for console log lines. Configure logging formatters to use `%H:%M:%S` without milliseconds.

**16. Post-market banner says "4 operations" but Task 1 says "Task 1/3"**
- File: `strategies/flow_monitor/fm_main.py` → `run_post_market()`
- Problem: Banner header count doesn't match the Task X/Y numbering in individual tasks.
- Fix: Use consistent numbering. If there are 5 tasks (including watchlist cleanup), number them 1/5 through 5/5.

**17. Earnings pipeline individual ALERT lines**
- File: `strategies/earnings_intel/ei_main.py` → daily pipeline
- Problem: Individual symbol alerts scroll on console. Different from evaluator per-alert lines (PRD 0005 req 34) — these are earnings-specific.
- Fix: Keep on console (they're informative and low volume) but confirm this is intentional.

### 3.5 Autofix Batch Mode Polish

**18. ERROR QUEUE box shows after fix, should be before**
- File: `main_runners.py` → `run_batch_mode_review()` (~line 1202)
- Problem: The error queue display appears AFTER sessions are spawned/completed. Should show the queue first, then the processing results.
- Fix: Move the error queue display box before the `check_and_spawn_batch_mode()` call, or split into two phases: show queue → process → show results.

**19. "Still waiting" duplicate lines**
- File: `tools/autofix.py` or `autofix/batch_mode_spawner.py`
- Problem: Shows two "1 min" lines, two "2 min" lines — likely 30-second polling writing both a print() and logging.info() line.
- Fix: Pick one output method. Same pattern as FM cycle dedup (PRD 0005 req 35).

---

## 4. Investigation Items (research before implementing)

These need investigation to determine the right fix:

**A. `failure_morgue` table warning**
- Shows `[WARNING] failure_morgue table missing` every run during daily evaluation.
- Question: Is this a real missing table that should be created, or a deprecated reference that should be removed?

**B. Watchlist cleanup formalization**
- Post-market has a hidden "watchlist cleanup" step — not numbered, not in banner, not in task count.
- Question: Should it become Step 2.8, or remain a quiet sub-task?

**C. FM cycle per-expiration logging**
- Every expiration date for every symbol logged individually — thousands of lines per cycle.
- Ben says per-expiration detail "has never been useful for debugging." Could reduce to per-symbol only.
- Question: Worth the refactor risk in FM-internal code?

**D. Consistently failing symbols**
- HON, DAY, FI etc. fail silently cycle after cycle with no escalation or tracking.
- Question: Should there be a "symbol health" tracker that escalates after N consecutive failures?

**E. Arbitrage opportunities display**
- When opportunities ARE found, are they actually listed on console? Needs code verification.

**F. News sentiment visibility**
- Runs inline with FM but output is not visible in main.py console.
- Question: Should it surface a summary line? Or is silent operation correct?

**G. Error/warning aggregation**
- No end-of-day summary of all warnings encountered across all steps.
- Question: Should the day-end summary include a "Warnings: 12 total (5 backfill, 4 evaluation, 3 collection)" line?

**H. Earnings alert content visibility**
- 197 alerts triggered — do they surface anywhere Ben can see them outside the TUI?
- Question: Should the day-end summary include "Earnings alerts: 197 active" or similar?

---

## 5. Non-Goals

- **Architectural changes** — PRD 0005 handled that. This is item-by-item cleanup.
- **Strategy logic changes** — only changing display/logging, not calculations
- **Performance optimization** — symbol rollup taking 881 seconds is noted but out of scope
- **New features** — no new monitoring capabilities (symbol health tracker from item D would be new)
- **JETS investigation** — separate bug fix tracked independently

---

## 6. Implementation Notes

### Ordering

These items are independent — no dependencies between them. Can be done in any order or in parallel. Suggested grouping by file to minimize context switches:

**`main_runners.py`**: Items 2, 3, 4, 8, 9, 12, 18
**`main.py`**: Item 12
**`strategies/option_pipeline/op_main.py`**: Item 1
**`strategies/flow_monitor/fm_main.py`**: Items 5, 6, 7, 11, 14, 16
**`strategies/earnings_intel/ei_main.py`**: Items 10, 17
**Cross-cutting (timestamps)**: Item 15
**`tools/autofix.py` or `autofix/`**: Item 19
**`strategies/flow_monitor/fm_evaluator.py`**: Item 13

### Risk

Low. These are all display-only changes. No database operations, no API calls, no calculation logic affected.

---

## 7. Success Metrics

- Zero misleading status lines (items 1-7)
- No operation over 60 seconds without console output (items 8-9)
- Dead output removed (items 10-14)
- Consistent timestamp format across all console output (item 15)
- Consistent task counting in FM post-market (items 6, 7, 16)
- Autofix review shows queue before processing (item 18)
