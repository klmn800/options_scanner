# Autofix System Cheat Sheet

**Quick Reference for Understanding and Maintaining the Autonomous Error-Fixing System**

---

## What Is This?

Autofix is your autonomous code maintenance system. When errors occur, it:
1. Logs them to a daily error queue
2. Spawns Claude Code to fix them (immediately or end-of-day)
3. Documents what happened in journals

---

## The Two Modes

### Immediate Mode (Fire Brigade)
**When**: Instantly when CRITICAL error occurs
**Purpose**: Quick fix to get system running again
**File**: `autofix/main_fix_launcher.py`
**Spawned by**: `tools/autofix.py` → `handle_error(severity='CRITICAL')`
**Behavior**:
- Spawns Claude Code in new window
- Writes to `autofix/logs/auto_fix_journal_YYYY-MM-DD.md`
- System exits immediately (fix requires restart)
- Marks error: `handled_by: immediate`, `fix_status: in_progress`

**Example triggers:**
- Flow Monitor collection fails (no data stored)
- Database table missing
- Module import errors

### Batch Mode (Night Janitor)
**When**: Scheduled end-of-day (7:30 PM weekdays, 10 PM Fridays)
**Purpose**: Fix non-critical errors, review immediate fixes, detect patterns
**File**: `autofix/batch_mode_spawner.py`
**Spawned by**: `main.py` → Step 7.6
**Behavior**:
- Processes ALL pending errors from today's queue
- Spawns Claude Code sequentially (one at a time)
- Waits for completion before next spawn
- Writes to `autofix/logs/batch_review_YYYY-MM-DD.md`
- Marks errors: `handled_by: batch`, `fix_status: fixed`

**Example triggers:**
- Market summary API failures (non-critical)
- Subprocess exit codes (informational)
- Weekly refresh warnings

---

## File Guide (What Does What)

### Core System Files

**`tools/autofix.py`**
- **What**: Error queue management + spawn coordinator
- **Key functions**:
  - `queue_error()` - Writes error to daily JSON file
  - `handle_error()` - Routes CRITICAL → immediate, ERROR → batch
  - `get_todays_errors()` - Reads daily queue
  - `mark_error_fixed()` - Updates error status
  - `check_and_spawn_batch_mode()` - End-of-day batch processing
- **When to touch**: Adding new error types, changing severity logic

**`autofix/main_fix_launcher.py`**
- **What**: Immediate mode spawner (CRITICAL errors)
- **Key functions**:
  - `launch_claude_fix()` - Main entry point
  - `build_diagnostic_prompt()` - Creates fix prompt
  - `auto_accept_bypass_prompt()` - Sends keystrokes for automation
- **When to touch**: Changing immediate mode prompt, spawn behavior

**`autofix/batch_mode_spawner.py`**
- **What**: Batch mode spawner (end-of-day processing)
- **Key functions**:
  - `spawn_batch_fix_for_error()` - Spawns Claude for one error
  - `build_fix_prompt()` - Creates batch fix prompt
  - `build_fix_context()` - Gathers historical data
- **When to touch**: Changing batch mode prompt, context structure

**`autofix/batch_mode_tracker.py`**
- **What**: Batch mode coordination and session discovery
- **Key functions**:
  - `find_todays_errors()` - Gets pending errors from queue
  - `load_historical_journals()` - Load past 30 days of journals for pattern detection
  - `should_skip_batch_mode()` - Check if Friday archive is running
- **When to touch**: Changing batch mode discovery or skip logic

**Note**: `_mark_duplicate_errors()` lives in `tools/autofix.py`, not in the tracker.

### Instruction Files (What Claude Reads)

**`autofix/instructions/AUTO_FIX_INSTRUCTIONS.md`**
- **For**: Immediate mode Claude sessions
- **Content**: Quick fix guidelines, restart instructions, monitoring limits
- **When to touch**: Changing immediate mode behavior/expectations

**`autofix/instructions/BATCH_MODE_INSTRUCTIONS.md`**
- **For**: Batch mode Claude sessions
- **Content**: Review guidelines, quality grading, pattern detection, escalation rules
- **When to touch**: Changing batch mode expectations, fix quality standards

### Data Files (Where Errors Live)

**`autofix/errors/errors_YYYY-MM-DD.json`**
- **What**: Daily error queue (the source of truth)
- **Structure**:
```json
{
  "timestamp": "2025-11-14T18:41:04.687001",
  "error_type": "earnings_daily_pipeline_unexpected",
  "severity": "CRITICAL",
  "context": { /* error-specific data */ },
  "source_file": "strategies/earnings_intel/ei_main.py",
  "source_line": 458,
  "handled_by": "immediate",  // or "batch" or "none"
  "fix_status": "pending",    // or "in_progress", "fixed", "deduplicated"
  "fix_timestamp": null,
  "attempt_count": 0,
  "notes": ""
}
```
- **When to touch**: Manually marking errors as fixed/ignored

**`autofix/logs/auto_fix_journal_YYYY-MM-DD.md`**
- **What**: Immediate mode's work log (what it did)
- **Written by**: Immediate mode Claude sessions
- **When to touch**: Reviewing what immediate mode fixed

**`autofix/logs/batch_review_YYYY-MM-DD.md`**
- **What**: Batch mode's work log (quality assessments)
- **Written by**: Batch mode Claude sessions
- **When to touch**: Reviewing batch mode's pattern detection

**`autofix/context/batch_context_YYYY-MM-DD.json`**
- **What**: Context data for batch mode (error history, patterns)
- **Created by**: `build_fix_context()` in batch_mode_spawner.py
- **When to touch**: If context file is too large (>25K tokens)

---

## The Error Queue Flow

```
1. Error occurs in code
   ↓
2. Code calls queue_error(error_type, context, severity)
   ↓
3. Error written to autofix/errors/errors_YYYY-MM-DD.json
   ↓
4. Route based on severity:
   ├─ CRITICAL → handle_error() → _spawn_immediate_fix() → sys.exit(1)
   │              (tools/autofix.py → main_fix_launcher.py)
   │
   └─ ERROR → Wait for batch mode
              (main.py Step 7.6 → batch_mode_spawner.py)
   ↓
5. Claude Code spawned with prompt from file (@filename)
   ↓
6. Claude reads instructions, fixes code, updates journal
   ↓
7. Claude calls mark_error_fixed(timestamp, notes='...')
   ↓
8. Error queue updated: fix_status='fixed', notes added
```

---

## How to Add Autofix to New Error Points

**Example: Adding autofix to YFinance backfill failures**

1. **In your script** (e.g., `data/yfinance_historical_backfill.py`):
```python
# At the top
from tools.autofix import queue_error

# After operation completes
if failed_symbols and (len(failed_symbols) > 50 or failure_rate > 0.15):
    queue_error(
        error_type='yfinance_backfill_high_failure_rate',
        context={
            'failed_symbols': len(failed_symbols),
            'total_symbols': len(symbols),
            'failure_rate': round(failure_rate, 3),
            'timeout_count': timeout_count,
            'failed_sample': failed_symbols[:20]
        },
        severity='ERROR'  # Batch mode (or 'CRITICAL' for immediate)
    )
```

### For CRITICAL Errors (Immediate Mode)

Use this pattern when the error requires **immediate attention** and the system cannot continue:

```python
# At the top
from tools.autofix import handle_error
import os
import traceback

# When CRITICAL error occurs (inside try/except)
except Exception as e:
    handle_error(
        error_type='descriptive_error_name',
        context={
            'error': str(e),
            'traceback': traceback.format_exc(),
            # ... other diagnostic context
        },
        severity='CRITICAL',              # ← Triggers immediate mode
        main_py_pid=os.getppid()          # ← REQUIRED for process detection
    )
    # Note: handle_error() calls sys.exit(1) - execution stops here
```

**Key differences from ERROR severity:**
- Uses `handle_error()` instead of `queue_error()` (includes immediate spawn logic)
- **Must include `main_py_pid=os.getppid()`** - enables process detection for kill/restart
- Calls `sys.exit(1)` automatically - kills current process
- Spawns Claude Code immediately (not end-of-day batch)

**When to use CRITICAL:**
- Data collection produced zero results (data loss)
- Database table/view missing (hard dependency failure)
- Module import errors (system can't function)
- API authentication failures (can't collect data)

**Examples in codebase:**
- `strategies/flow_monitor/fm_main.py:1395` - Tradier init failure
- `strategies/option_pipeline/op_main.py:325` - Zero contracts collected
- `strategies/earnings_intel/ei_main.py:278` - Archive schema errors

---

2. **Document in audit** (`autofix/AUTOFIX_INTEGRATION_AUDIT.md`):
- Update the script's status from ❌ MISSING to ✅ INTEGRATED
- Document the trigger conditions and severity

3. **Done!** Error will now:
- Get logged to daily queue
- Processed by batch mode at end of day
- Claude will see the context and fix it

---

## Common Maintenance Tasks

### Check Today's Errors
```bash
cat autofix/errors/errors_2025-11-14.json
```

### Check Batch Mode Results
```bash
cat autofix/logs/batch_review_2025-11-14.md
```

### Manually Mark Error as Fixed
```python
python -c "
from tools.autofix import mark_error_fixed
mark_error_fixed('2025-11-14T18:41:04.687001', notes='Fixed manually - renamed file')
"
```

### Check Error History (30 days)
```python
python -c "
from tools.autofix import get_error_history
history = get_error_history(days=30)
for date, errors in history.items():
    print(f'{date}: {len(errors)} errors')
"
```

### Test Error Queue
```python
python -c "
from tools.autofix import queue_error
queue_error('test_error', context={'test': True}, severity='ERROR')
print('Test error queued successfully')
"
```

---

## Troubleshooting

### "Claude spawned but got generic prompt"
**Symptom**: Claude says "I'll help you with the options scanner..." instead of specific fix task
**Cause**: Quote escaping bug (should be fixed as of 2025-11-14)
**Check**: Look at prompt file in `autofix/logs/batch_prompt_*.txt` or `immediate_prompt_*.txt`
**Fix**: Verify both `main_fix_launcher.py` and `batch_mode_spawner.py` use `@filename` approach (not inline prompts)

### "Context file too large (>25K tokens)"
**Symptom**: Batch mode can't read context file
**Cause**: Too much data embedded (especially logs)
**Check**: `autofix/context/batch_context_*.json` size
**Fix**: Reduce log excerpt size or use file references instead of embedding

### "Error shows as pending but was fixed"
**Symptom**: Error queue shows `fix_status: pending` but you fixed it
**Cause**: Claude didn't call `mark_error_fixed()`
**Fix**: Manually mark it:
```python
from tools.autofix import mark_error_fixed
mark_error_fixed('TIMESTAMP_HERE', notes='Your fix description')
```

### "Batch mode spawned too many times for same error"
**Symptom**: Multiple Claude windows for identical error_type
**Cause**: Deduplication failed
**Check**: `autofix/batch_mode_tracker.py` → `_mark_duplicate_errors()`
**Fix**: Should auto-deduplicate as of 2025-11-14 fix

### "Immediate mode didn't exit/restart"
**Symptom**: System kept running after CRITICAL error
**Cause**: `sys.exit(1)` not called or caught by try/except
**Check**: `tools/autofix.py` line 380 - should have `sys.exit(1)`
**Fix**: Ensure no broad exception handlers are catching SystemExit

---

## Key Design Decisions (Why It Works This Way)

### Why two modes?
- **Immediate**: Can't wait - system is broken RIGHT NOW
- **Batch**: Can wait - review calmly, find patterns, apply proper fixes

### Why sequential spawning in batch mode?
- Prevents file conflicts (multiple Claude sessions editing same file)
- Easier to debug (one journal entry at a time)
- Completion markers coordinate handoff

### Why use error queue instead of direct spawning?
- Unified tracking (everything in one place)
- Historical pattern detection (see recurring issues)
- Deduplication (don't fix same error 5 times)
- Batch mode review (end-of-day processing)

### Why @filename instead of inline prompts?
- Windows batch file quote escaping is fragile
- No character limits (Windows CMD has 8191 char limit)
- Easier debugging (can read the exact prompt file)
- Works with any special characters

### Why severity matters?
- **CRITICAL**: System can't function (immediate fix required)
- **ERROR**: System degraded but operational (batch mode acceptable)

---

## Integration Status

**✅ Fully Integrated (3)**:
- Flow Monitor (`fm_collector.py`)
- Option Pipeline (`op_main.py`)
- Tradier Historical Backfill (`tradier_historical_backfill.py`)

**🟡 Partially Integrated (2)**:
- Earnings Intel (orchestrator covered, component internals gaps)
- Main.py (pipeline-level covered, system-level gaps)

**❌ Missing Integration**:
- See `autofix/AUTOFIX_INTEGRATION_AUDIT.md` for full list and priorities

---

## What Good Autofix Integration Looks Like

The autofix system handles a wide range of errors — from transient API failures to missing data mappings to schema mismatches. The examples below illustrate qualities of well-integrated error points, not an exhaustive catalog. Use them as inspiration when adding new `queue_error()` calls.

### Example: Self-Describing Error Context (metadata_unmapped_industry_codes)

When the ADR symbol batch was added (2026-03-12), DEO (Diageo) had a Morningstar industry code the system didn't recognize. The `queue_error()` call in `data/symbol_metadata.py` included everything a batch-mode agent would need to fix it autonomously:

```python
queue_error('metadata_unmapped_industry_codes', context={
    'unmapped_codes': sorted(unmapped_codes),        # What's wrong: [20510020]
    'symbols_affected': affected_symbols[:10],        # Who's affected: ['DEO']
    'action_needed': 'Add codes to MORNINGSTAR_INDUSTRY_MAP'  # What to do
}, severity='ERROR')
```

**Why this worked well:**
- **Self-describing context** — the error dict told the agent exactly what code was missing, which symbols were affected, and what action to take. No log-diving required.
- **Correct severity** — `ERROR` (not `CRITICAL`) because the pipeline continued fine; DEO just got `industry='N/A'` until the mapping was added. Batch mode, not immediate mode.
- **Surgical fix** — the agent added one line (`20510020: 'Beverages - Wineries & Distilleries'`) and was done. Total cycle: error queued → agent spawned → root cause obvious from context → 1-line fix → verified → email sent.

### Principles for New Integrations

These qualities make any `queue_error()` call effective, regardless of error type:

1. **Put actionable data in `context`** — not just "something failed" but the specific IDs, codes, counts, or thresholds that a future agent (or human) needs to diagnose and fix.
2. **Match severity to impact** — `CRITICAL` (immediate mode) for pipeline-blocking failures; `ERROR` (batch mode) for degraded-but-functional states.
3. **Name the error type descriptively** — `metadata_unmapped_industry_codes` beats `metadata_error`. The type string is what groups errors for pattern detection across days.
4. **Include the "what to do" hint** — even a brief `action_needed` string saves the reviewing agent significant investigation time.

---

## Quick Command Reference

```bash
# View today's errors
cat autofix/errors/errors_$(date +%Y-%m-%d).json

# View immediate mode journal
cat autofix/logs/auto_fix_journal_$(date +%Y-%m-%d).md

# View batch mode review
cat autofix/logs/batch_review_$(date +%Y-%m-%d).md

# Test batch mode spawning
python -c "from tools.autofix import check_and_spawn_batch_mode; check_and_spawn_batch_mode()"

# Check error history
python -c "from tools.autofix import get_error_history; print(get_error_history(days=7))"
```

---

## When to Escalate to Human (You)

Autofix will handle most issues autonomously, but escalate when:

1. **Pattern detected** (same error 3+ times in 30 days)
2. **Breaking changes needed** (schema migrations, API changes)
3. **Business logic decisions** (which data source to prefer, trading rules)
4. **Uncertain about approach** (multiple valid solutions)
5. **External dependencies failing** (API keys expired, service down)

Check for escalations in:
- Batch review journals (look for "ESCALATED" status)
- Email notifications (batch mode sends summary reports)

---

## Performance Database (`data/performance.db`)

End-of-day metrics written by Phase 6: System Maintenance. Use this to establish baselines, detect degradation, and correlate failures with market conditions.

**Context field**: Error queue entries include `'performance_db': 'data/performance.db'` — query it directly.

### 15 Tables

| Table | Description |
|-------|-------------|
| `daily_context` | Market regime, VIX, SPY, universe size, news API budget |
| `op_pipeline_performance` | Option Pipeline (morning + evening) — contracts, symbols, timing, health |
| `ei_pipeline_performance` | Earnings Intel — daily pipeline, morning scan, weekly refresh |
| `fm_pre_market_performance` | FM pre-market — alert resolution, sentiment update, sync |
| `fm_cycle_performance` | FM per-cycle — scan_timestamp PK, contracts, alerts, timing splits |
| `fm_post_market_performance` | FM post-market — backfill, regime, rollup, evaluation |
| `sync_performance` | Full + quick syncs — duration, rows, size_mb for DB trending |
| `metadata_performance` | Symbol metadata refresh — symbols, quotes, duration |
| `morning_views_performance` | Morning Views generation — duration, success |
| `backup_performance` | Daily + weekly backup — size, duration, verification |
| `batch_mode_performance` | Autofix batch review — errors found, sessions spawned |
| `airline_play_performance` | Airline tracking — symbols, contracts tracked |
| `sector_archive_performance` | Friday archive — tier row counts, space reclaimed |

### Diagnostic Queries

```sql
-- "Is this slow, or normal?" (OP baseline)
SELECT AVG(collection_seconds) AS avg, MAX(collection_seconds) AS max
FROM op_pipeline_performance
WHERE run_type = 'morning' AND trade_date >= date('now', '-30 days');

-- "When did degradation start?" (OP trending)
SELECT trade_date, collection_seconds, total_contracts
FROM op_pipeline_performance WHERE run_type = 'morning'
ORDER BY trade_date DESC LIMIT 14;

-- "What were market conditions when it broke?"
SELECT trade_date, vix_close, market_regime, spy_close
FROM daily_context ORDER BY trade_date DESC LIMIT 7;

-- "How big is the database and is it growing fast?"
SELECT trade_date, MAX(size_mb) AS eod_size_mb
FROM sync_performance WHERE sync_type = 'full'
GROUP BY trade_date ORDER BY trade_date DESC LIMIT 14;

-- "Is INSERT time growing within a single day?" (FM intra-day)
SELECT scan_timestamp, cycle_number, storage_seconds, sync_seconds
FROM fm_cycle_performance WHERE trade_date = date('now')
ORDER BY scan_timestamp;

-- "Did the archive affect Friday performance?"
SELECT a.duration_seconds AS archive_time, a.total_rows_deleted,
       f.duration_seconds AS fm_post_time
FROM sector_archive_performance a
JOIN fm_post_market_performance f USING (trade_date)
WHERE a.day_of_week = 4;

-- "Cross-table: slow collection days vs market conditions"
SELECT d.trade_date, d.market_regime, d.vix_close,
       o.collection_seconds, o.total_contracts
FROM daily_context d
JOIN op_pipeline_performance o USING (trade_date)
WHERE o.run_type = 'morning'
ORDER BY o.collection_seconds DESC LIMIT 10;

-- "FM cycle degradation pattern"
SELECT trade_date, COUNT(*) as cycles,
       AVG(collection_seconds) as avg_collect,
       AVG(storage_seconds) as avg_storage,
       AVG(analysis_seconds) as avg_analysis
FROM fm_cycle_performance
WHERE trade_date >= date('now', '-7 days')
GROUP BY trade_date ORDER BY trade_date;

-- "Sync duration trending (full syncs only)"
SELECT trade_date, sync_time,
       duration_seconds, rows_synced, size_mb
FROM sync_performance
WHERE sync_type = 'full'
ORDER BY trade_date DESC, sync_time DESC LIMIT 20;

-- "Overall system health: any failures today?"
SELECT trade_date, success, duration_seconds
FROM op_pipeline_performance WHERE trade_date = date('now')
UNION ALL
SELECT trade_date, success, duration_seconds
FROM ei_performance WHERE trade_date = date('now');
```

---

## Database Sync Architecture Context

Understanding the sync subsystem helps when diagnosing sync-related errors. These patterns were established after significant performance investigation and the reasoning is worth knowing.

### Quick Sync (`create_quick_sync()` in `data/health/db_backup.py`)

Quick sync copies new rows from `datalake.db` → `datalake_query.db` every ~30 minutes during market hours. It uses a watermark approach (reads only rows newer than the target's latest timestamp).

**Why performance-sensitive PRAGMAs exist:**

The function sets several PRAGMAs that may look like candidates for removal or simplification during debugging, but each addresses a specific production problem:

- **`cache_size = -256000` (source)**: The production database is 11GB+. Default 8MB cache causes heavy disk I/O when reading ~100K rows per sync. 256MB keeps B-tree pages cached during the scan. Memory frees when the connection closes.

- **`cache_size = -256000` (target)**: Same issue on the write side — inserting ~100K rows across 2 indexes with only 8MB of cache thrashes disk.

- **`wal_autocheckpoint = 0` (target)**: Prevents SQLite from auto-checkpointing mid-batch. Without this, inserting 100K rows triggers ~150 auto-checkpoints adding ~75 seconds of overhead.

- **`PRAGMA wal_checkpoint(PASSIVE)` after commit**: This is the counterpart to `wal_autocheckpoint=0`. Since the query DB is effectively read-only for analysis tools, no other process ever triggers a WAL checkpoint. Without this explicit checkpoint, the WAL grows unbounded across cycles (~100-150MB per cycle). By end of day the WAL reaches 1.5-2.5GB and every INSERT has to scan through it for primary key and index lookups. This caused sync times to grow from ~30 seconds (cycle 1) to 20+ minutes (cycle 12) on Feb 20, 2026. PASSIVE mode was chosen because analysis tools may be reading the query DB concurrently.

- **Separate connections (no ATTACH)**: An earlier design used `ATTACH DATABASE` to copy between databases in a single connection. This caused recurring "database is locked" errors during market hours because ATTACH forces both databases into one connection's lock scope. Separate connections with WAL mode let the source reader run without blocking Flow Monitor's concurrent writes.

**Transient failures are expected:** "database is locked" during market hours is normal — Flow Monitor, the analyzer, and quick sync can overlap. The function has built-in retry logic (3 attempts with 5/15/30s backoff). A transient failure followed by a successful retry is working as designed.

**Query DB index reduction:** After full syncs, `create_query_sync()` automatically drops 3 production-only indexes from `datalake_query.db`'s `flow_options_scans` table (contract, significance, expiration). These serve FM alerting on production only — keeping them on the query DB doubles B-tree maintenance per INSERT during quick-sync for no analytical benefit. If you see "Dropped 3 production-only indexes from query DB" in logs, this is intentional.

### Relevant diagnostic query

```sql
-- "Is quick sync degrading within a day?" (check WAL checkpoint health)
SELECT scan_timestamp, cycle_number, sync_seconds, sync_rows
FROM fm_cycle_performance WHERE trade_date = date('now')
ORDER BY scan_timestamp;
-- Stable 40-70s is healthy. Growing times suggest WAL checkpoint isn't running.
```

---

**Last Updated**: 2026-02-26
**System Status**: Production (2 modes operational, performance tracking active)
