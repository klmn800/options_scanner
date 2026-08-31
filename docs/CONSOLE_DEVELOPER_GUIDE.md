# Console Output Developer Guide

**Last updated:** 2026-02-28
**Purpose:** The definitive reference for how console output works in the options scanner. Read this when building a new strategy module, adding a new orchestrator step, or modifying existing output.

This guide reflects the system as actually implemented, not aspirational designs. When this document and any other doc disagree, this document wins.

  ┌───────────────────┬─────────────────────────────┬───────────────────────────────────────────────────────┐
  │     Function      │        Console gets         │                     Log file gets                     │
  ├───────────────────┼─────────────────────────────┼───────────────────────────────────────────────────────┤
  │ beautiful_log     │ emoji + timestamp + message │ Clean message only (formatter adds its own timestamp) │
  ├───────────────────┼─────────────────────────────┼───────────────────────────────────────────────────────┤
  │ create_status_box │ Full Unicode-bordered box   │ Title + indented content lines, no borders            │
  ├───────────────────┼─────────────────────────────┼───────────────────────────────────────────────────────┤
  │ phase_header      │ Full-width ═══ banner       │ Single line: --- [PHASE N] TITLE ---                  │
  ├───────────────────┼─────────────────────────────┼───────────────────────────────────────────────────────┤
  │ _safe_print       │ Raw text                    │ Nothing                                               │
  ├───────────────────┼─────────────────────────────┼───────────────────────────────────────────────────────┤
  │ logging.info()    │ HH:MM:SS - message          │ YYYY-MM-DD HH:MM:SS - INFO - message                  │
  └───────────────────┴─────────────────────────────┴───────────────────────────────────────────────────────┘

---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [Architecture: Two Layers](#2-architecture-two-layers)
3. [The Toolkit](#3-the-toolkit)
4. [Logging Type Taxonomy](#4-logging-type-taxonomy)
5. [Roles and Responsibilities](#5-roles-and-responsibilities)
6. [Building a New Strategy Module](#6-building-a-new-strategy-module)
7. [Building a New Coordinator](#7-building-a-new-coordinator)
8. [Return Dict Contracts](#8-return-dict-contracts)
9. [Progress Intervals](#9-progress-intervals)
10. [Error Behavior](#10-error-behavior)
11. [Anti-Patterns](#11-anti-patterns)
12. [Checklist](#12-checklist)

---

## 1. Philosophy

The goal is **smart logging** — the right information at the right density. Not minimal. Not maximal.

- **More** where it helps: a 15-line stats block after analysis is useful if every line carries diagnostic value.
- **Less** where it's noise: the same fact announced twice by two layers, or diagnostic internals that only matter when debugging.
- **Channel, not volume:** Most issues are about *who* produces output and *through what API*, not about *how much*.

The console is for the human watching the system run. It should answer: **"What is happening right now, and is it healthy?"**

The text log is the forensic record. It should answer: **"What happened, how long did it take, and what went wrong?"**

Both outputs flow through `tools/log_utils.py`, which writes to console (`sys.stdout`) and the root logger's file handler simultaneously.

---

## 2. Architecture: Two Layers

Every phase of the system follows a three-section pattern:

```
╔═══════════════════════════════════════════════════════════╗
║ MISSION BOX — what's about to happen                      ║
╚═══════════════════════════════════════════════════════════╝

[Strategy progress output — the only thing the strategy prints]

╔═══════════════════════════════════════════════════════════╗
║ COMPLETION BOX — what happened (built from return dict)   ║
╚═══════════════════════════════════════════════════════════╝
```

**Layer 1: Orchestrator** (`main_runners.py`) owns all visual structure — boxes, phase banners, coffee breaks, the day-end summary. It draws the mission box before a strategy runs and the completion box after, using the strategy's return dict.

**Layer 2: Strategy** (e.g., `fm_collector.py`, `op_collector.py`) owns progress output — per-symbol lines, validation milestones, stats blocks, inline warnings. It returns a structured dict with everything the orchestrator needs.

The orchestrator never queries the database for completion box data. The strategy never draws boxes or banners.

---

## 3. The Toolkit

All public functions live in `tools/log_utils.py`. Import what you need:

```python
from tools.log_utils import beautiful_log, create_status_box, phase_header
```

### beautiful_log(message, level='info')

Timestamped, emoji-prefixed line. Goes to both console and log file.

```python
beautiful_log("Processing 800 symbols", level='info')
# Console: ℹ️ 09:15:32 - Processing 800 symbols

beautiful_log("Pipeline complete", level='success')
# Console: ✅ 09:18:44 - Pipeline complete

beautiful_log("3 symbols failed", level='warning')
# Console: ⚠️ 09:18:44 - 3 symbols failed
```

**Levels:** `'info'` (ℹ️), `'success'` (✅), `'error'` (❌), `'warning'` (⚠️), `'phase'` (🔥)

**Stutter prevention:** If the message already starts with an emoji (e.g., `"🚨 FLOW MONITOR ALERTS"`), the level emoji is skipped automatically — you get `09:53:05 - 🚨 FLOW MONITOR ALERTS`, not `⚠️ 09:53:05 - 🚨 FLOW MONITOR ALERTS`.

### create_status_box(title, content_lines, success=True)

Unicode-bordered box. `success=True` → double borders (`╔═╗`), `success=False` → single borders (`┌─┐`). Auto-sizes to content width (minimum 60 chars). Goes to both console and log file.

```python
create_status_box("🎯 MORNING PIPELINE COMPLETE", [
    "Symbols processed: 800",
    "Errors: 0",
    "Duration: 12m 34s",
])
```

**Who can call this:** Orchestrator (`main_runners.py`) and delegated orchestrators (see Section 5). Strategies never call this.

### phase_header(title, phase_number=None)

Full-width centered banner between `═══` separators. Used for macro phase transitions.

```python
phase_header("PRE-MARKET OPERATIONS", phase_number=1)
# ════════════════════════════════════════════════════════════
#                  PHASE 1: PRE-MARKET OPERATIONS
# ════════════════════════════════════════════════════════════
```

**Who can call this:** Orchestrator only.

### Thread safety

`beautiful_log`, `create_status_box`, and `phase_header` all emit under a shared module-level `RLock` (`_OUTPUT_LOCK`), so a multi-line box or banner printed from one thread is never torn apart by lines from another. This matters on Fridays, where Step 5.1 (weekly backup) runs on a background thread while the main flow continues into 5.2. The lock guarantees each *unit* is contiguous — it does not guarantee ordering *between* units, so a `[5.1 BG]` box may still land before or after a neighboring main-thread line. Bare `logging.info()` / `print()` calls are not covered; if you need a multi-line block to stay intact across threads, route it through one of the three functions above.

### _step_header pattern

Not a log_utils function — a local helper pattern used by coordinators for sub-task separators within a phase. Fixed width, 60 characters.

```python
def _step_header(step_num, total, label):
    """Print a fixed-width step header: ── Step 1/3: Label ──────────────"""
    prefix = "── Step {}/{}: {} ".format(step_num, total, label)
    padding = max(0, 60 - len(prefix))
    print("\n" + prefix + "─" * padding)
```

Copy this into your coordinator if you need numbered sub-steps. It's decorative (`print()`), not logged — the step content that follows provides the forensic record.

### Cycle header pattern

Used by long-running loops (like FM market hours) to mark each iteration. Fixed width, 60 characters.

```python
cycle_prefix = "── Cycle {} | {} | {} symbols ".format(
    cycle, current_time.strftime('%H:%M:%S'), len(symbols))
print("\n" + cycle_prefix + "─" * max(0, 60 - len(cycle_prefix)))
```

---

## 4. Logging Type Taxonomy

This is the most important section for day-to-day development. Every line of output should use exactly one of these types:

| Type | API | Console | Log File | Use For |
|------|-----|---------|----------|---------|
| **Announcement** | `beautiful_log(msg, level)` | Yes (emoji + time) | Yes | Phase starts, milestones, completions. The "headlines." |
| **Forensic stats** | `logging.info(msg)` | Yes (time only) | Yes | Stats blocks, per-symbol results, filter counts. Cohesive data blocks. |
| **Demoted diagnostic** | `logging.debug(msg)` | No | Only with `--debug` | Internal algorithm details, batch progress, init confirmations. |
| **Decorative spacing** | `print("")` | Yes | No | Blank lines between zones. Visual breathing room. |
| **Structural** | `create_status_box()` | Yes | Yes | Intro/completion boxes. Orchestrator and delegated orchestrators only. |
| **Inline warning** | `logging.warning(msg)` | Yes | Yes | Exceptional conditions during a run (failure clusters, API issues). |

### When to use beautiful_log vs logging.info

This is the key judgment call. The rule of thumb:

**beautiful_log** = a standalone line that a human scanning the console should notice. Phase transitions, "we're done" confirmations, single important facts.

```python
beautiful_log("Starting FM Collector", 'info')              # Phase start
beautiful_log("Collection complete (1371.9s)", 'success')    # Milestone
beautiful_log("Market regime: normal", 'info')               # Important single fact
```

**logging.info** = a line within a cohesive block of related data. Stats, counts, breakdowns. Don't mix beautiful_log into a stats block — it breaks the visual rhythm.

```python
logging.info("Contracts updated: {:,}".format(count))        # Stats block
logging.info("Premium filter: {} passed ({:,} filtered)".format(passed, filtered))
logging.info("Volume filter: {} passed ({:,} filtered)".format(passed, filtered))
logging.info("High conviction alerts (8.0+): {}".format(high))
logging.info("Total analysis time: {:.2f} seconds".format(elapsed))
```

### Console log format

The orchestrator configures the root logger's console handler with a short format:

```
%(asctime)s - %(message)s     (datefmt='%H:%M:%S')
```

So `logging.info("Contracts updated: 101,300")` appears on console as:

```
09:53:04 - Contracts updated: 101,300
```

The file handler keeps the full format (`%(asctime)s - %(levelname)s - %(message)s`) for greppability.

### Conditional output

Suppress zero-value lines. Don't print a line that says "Smart money alerts: 0" — the absence is the signal.

```python
# Good: only show when there's something to show
if stats['smart_money_alerts'] > 0:
    logging.info("Smart money alerts (1.5+): {}".format(stats['smart_money_alerts']))

# Bad: noise when zero
logging.info("Smart money alerts (1.5+): {}".format(stats['smart_money_alerts']))
```

**Exception: pipeline step metrics.** For multi-step pipelines where each step is expected to produce output (e.g., Earnings Intelligence snapshots, post-earnings calculations), showing zero IS informative — it may indicate a data gap or upstream issue. Zero suppression applies to metrics where zero is the normal, expected state (e.g., smart money alerts most cycles). For metrics where zero is anomalous, show it.

Similarly, conditional phase headers — if there are no new watchlist entries, skip the news enrichment header entirely:

```python
if created_symbols:
    beautiful_log("Starting FM News Enrichment", 'info')
    # ... do enrichment ...
```

---

## 5. Roles and Responsibilities

### The Content-Based Rule

Choose the output function based on **what the content is**, not who's producing it. Any module — orchestrator, coordinator, or strategy component — follows the same rule:

| Content type | Function | Why |
|---|---|---|
| **Headline** — phase start, milestone, completion, important single fact | `beautiful_log` | Console gets visual hierarchy (emoji + timestamp); log file stays clean |
| **Data** — stats block, per-item progress, filter counts, cohesive metrics | `logging.info()` | Same content is useful in both channels |
| **Diagnostic** — algorithm internals, cache hits, batch counters | `logging.debug()` | Only visible with `--debug` |
| **Spacing** — blank lines between visual zones | `print("")` | Console-only; doesn't pollute log file |

The only **role-based restrictions** are on visual structure — boxes and banners define the flow of the whole system:

| Visual structure | Who can use it |
|---|---|
| `create_status_box()` | Orchestrator and delegated orchestrators only |
| `phase_header()` | Orchestrator only |

### Why beautiful_log is content-based, not role-based

`beautiful_log` and `logging.info()` both write to console and log file. The difference is **how**:

- `beautiful_log` writes a formatted line (emoji + timestamp) to console via `_safe_print`, then writes the **clean message** to the log file via the file handler directly. The log file never sees the emoji or decorative formatting.
- `logging.info()` goes through both handlers identically. If you embed `── 📊 DATA COLLECTION ──` in the message, that decoration ends up in the log file too.

So `beautiful_log` is the **correct tool for headlines** regardless of who's calling it — it gives the console visual hierarchy while keeping the log file greppable. Using `logging.info()` with manual emoji for headlines is a worse outcome for the log file.

### Orchestrator (`main_runners.py`)

The orchestrator owns ALL visual structure.

**Produces:**
- Phase headers (`phase_header()`)
- Mission boxes before each step (`create_status_box()`)
- Completion boxes after each step (`create_status_box()`, built from return dict)
- Coffee breaks
- Day-end summary
- Headlines and wait/timing messages (`beautiful_log`)

**Never produces:**
- Progress lines (strategy's job)
- Stats blocks (strategy's job)
- Per-symbol output

**Completion box rules:**
- Built ONLY from the strategy's return dict — never query the database
- Include: key counts, duration, error count if > 0
- If errors > 0: list affected symbols (up to 8, then `...+N`)
- No filler lines ("Status: Ready", "System: Complete")
- Use actual measured values, never hardcoded counts

### Coordinator (`fm_main.py`, `op_main.py`, `ei_main.py`)

Coordinators sequence multi-step pipelines and aggregate results. They are the "middle layer" between orchestrator and strategy components.

**Produces:**
- Headlines — `beautiful_log()` for step starts and completions
- Step headers — `beautiful_log("Step Name (N/M)", 'info')` with `print("")` spacing
- Tree-formatted detail under headers — `logging.info("   ├─ ...")`
- Stats and progress — `logging.info()` for cohesive data blocks
- Decorative spacing — `print("")` between zones

**Never produces:**
- Boxes (`create_status_box`) — exception: delegated orchestrator mode (see below)
- Phase banners (`phase_header`)
- Completion celebrations ("SUCCESS!", "ALL DONE!")
- Day-end summaries

**Returns:**
A combined dict with `sub_tasks` key containing per-component results. The orchestrator uses this for the completion box.

```python
return {
    'success': True,
    'duration_seconds': 12.5,
    'sub_tasks': {
        'alert_resolution': {'success': True, 'alerts_resolved': 22, ...},
        'sentiment_update': {'success': True, 'symbols_updated': 79, ...},
        'sync': {'success': True, 'alerts_synced': 22, 'watchlist_synced': 79},
    },
    'alerts_resolved': 22,
    'symbols_updated': 79,
}
```

### Delegated Orchestrator (FM Market Hours)

Some operations run for hours (FM market hours: 9:30 AM to 4:00 PM). These can't be wrapped in a single mission/completion box pair. The coordinator gets promoted to **delegated orchestrator** with expanded visual structure privileges.

**A delegated orchestrator may additionally:**
- Use `create_status_box()` for a one-time intro box at the start of the long operation
- Use `coffee_break()` for pauses between cycles or post-market tasks
- Draw cycle headers via `print()`

**A delegated orchestrator must not:**
- Draw phase banners (`phase_header()` — that's the top-level orchestrator's job)
- Announce its own final completion (the orchestrator draws the session summary box)

**Returns:** A comprehensive session dict when the long-lived operation ends. The orchestrator draws the session summary box from this.

### Strategy Component (`fm_collector.py`, `fm_analyzer.py`, `op_collector.py`, etc.)

Strategy components do the actual work. They own progress output.

**Produces:**
- Headlines — `beautiful_log('info')` for phase starts ("Fetching underlying prices", "Analyzing N contracts")
- Milestones — `beautiful_log('success')` for major checkpoints ("Collection complete", "Batch validated")
- Data — `logging.info()` for stats blocks, per-item progress, filter counts
- Inline warnings — `logging.warning()` for exceptional conditions

**Never produces:**
- Boxes (`create_status_box`)
- Phase banners (`phase_header`)
- Completion celebrations ("SUCCESS!", "ALL DONE!")
- `═══` or `===` banner separators

**Returns:** A structured dict with all metrics the coordinator/orchestrator needs.

**Real example — FM Collector (headlines + milestones):**

```python
# Headlines (info)
beautiful_log("Starting FM Collector", 'info')
beautiful_log("Scan timestamp: {}".format(scan_timestamp), 'info')
beautiful_log("Fetching underlying prices for {} symbols".format(len(symbols)), 'info')

# Milestones (success)
beautiful_log("Prices received for {} symbols".format(len(quotes_data)), 'success')
beautiful_log("Symbol list validated: {} unique, no duplicates".format(len(symbols)), 'success')
beautiful_log("Batch validated: {:,} contracts, no duplicates".format(len(hashes)), 'success')
beautiful_log("Stored {:,} contracts in {:.1f}s (scan: {})".format(count, elapsed, ts), 'success')
```

**Real example — FM Analyzer (headlines + data block):**

```python
# beautiful_log for headlines
beautiful_log("Analyzing {:,} contracts for significant flow activity".format(len(data)), 'info')
beautiful_log("Market regime: {}".format(regime), 'info')

# logging.info for the stats block (don't mix beautiful_log in here)
logging.info("Contracts updated: {:,}".format(stats['contracts_updated']))
logging.info("Missing baselines: {}".format(stats['missing_baselines']))
logging.info("Premium filter: {} passed ({:,} filtered)".format(passed, filtered))
logging.info("Volume filter: {} passed ({:,} filtered)".format(passed, filtered))
logging.info("High conviction alerts (8.0+): {}".format(stats['high_conviction']))
logging.info("Total analysis time: {:.2f} seconds".format(elapsed))
```

---

## 6. Building a New Strategy Module

You're adding a new strategy component (e.g., `strategies/my_strategy/ms_collector.py`). Here's what to do:

### Step 1: Import the toolkit

```python
import logging
from tools.log_utils import beautiful_log
```

### Step 2: Use beautiful_log for headlines, logging.info for detail

```python
def collect(self, symbols):
    beautiful_log("Starting My Strategy collector", 'info')
    beautiful_log("Processing {} symbols".format(len(symbols)), 'info')

    for symbol in symbols:
        result = self._process_symbol(symbol)
        logging.info("Processed {} — {} contracts".format(symbol, result['count']))

    beautiful_log("Collection complete: {:,} contracts in {:.1f}s".format(
        total, elapsed), 'success')
```

### Step 3: Demote diagnostics to debug

Anything that's only useful when actively debugging should use `logging.debug()`. This keeps it out of the console but available with `--debug`.

```python
logging.debug("Cache hit for {} expirations".format(symbol))
logging.debug("Batch insert: {} rows affected".format(rows))
logging.debug("Algorithm params: regime={}, threshold={}".format(regime, thresh))
```

### Step 4: Return a structured dict

Never return `bool`. Return a dict with everything the caller needs for the completion box.

```python
return {
    'success': True,
    'symbols_processed': len(symbols),
    'total_contracts': total_contracts,
    'errors': error_count,
    'failed_symbols': failed_list,
    'duration_seconds': time.time() - start_time,
}
```

### Step 5: Don't draw boxes or banners

The orchestrator handles visual structure. Your job is progress lines and a return dict.

```python
# WRONG — strategy drawing a box
create_status_box("COLLECTION COMPLETE", ["Processed: 800"])

# WRONG — strategy drawing a banner
logging.info("=" * 60)
logging.info("  COLLECTION COMPLETE")
logging.info("=" * 60)

# RIGHT — strategy returns data, orchestrator draws the box
return {'success': True, 'symbols_processed': 800, ...}
```

---

## 7. Building a New Coordinator

You're building `strategies/my_strategy/ms_main.py` to sequence multiple components. Here's the pattern:

### Step 1: Import what you need

```python
import time
import logging
from tools.log_utils import beautiful_log
```

### Step 2: Create a step header helper (if you have numbered steps)

```python
def _step_header(step_num, total, label):
    """Print a fixed-width step header."""
    prefix = "── Step {}/{}: {} ".format(step_num, total, label)
    padding = max(0, 60 - len(prefix))
    print("\n" + prefix + "─" * padding)
```

### Step 3: Sequence components with beautiful_log milestones

```python
def run_pipeline():
    start_time = time.time()

    _step_header(1, 3, "Data Collection")
    beautiful_log("Collecting data for {} symbols".format(count), 'info')
    collection_result = collector.collect(symbols)
    beautiful_log("Collection complete: {:,} contracts".format(
        collection_result['total_contracts']), 'success')

    _step_header(2, 3, "Analysis")
    beautiful_log("Analyzing collected data", 'info')
    analysis_result = analyzer.analyze(scan_id)
    beautiful_log("Analysis complete: {} alerts found".format(
        analysis_result['alerts_found']), 'success')

    _step_header(3, 3, "Reporting")
    beautiful_log("Generating report", 'info')
    report_result = reporter.generate()
    beautiful_log("Report generated", 'success')

    return {
        'success': True,
        'duration_seconds': time.time() - start_time,
        'sub_tasks': {
            'collection': collection_result,
            'analysis': analysis_result,
            'report': report_result,
        },
        'errors': sum(r.get('errors', 0) for r in [collection_result, analysis_result]),
    }
```

### Step 4: Add visual spacing between zones

Use `print("")` for blank lines between logical sections. This is decorative — it doesn't go to the log file.

```python
# After validation, before per-symbol heartbeat
print("")  # Visual breathing room

# After heartbeat, before stats block
print("")  # Separate progress from summary
```

---

## 8. Return Dict Contracts

Every strategy function called by the orchestrator must return a dict. The minimum contract:

```python
{
    'success': bool,           # Did the operation succeed?
    'duration_seconds': float, # How long did it take?
    'errors': int,             # How many errors?
}
```

For multi-step coordinators, add `sub_tasks`:

```python
{
    'success': bool,
    'duration_seconds': float,
    'errors': int,
    'failed_symbols': list,    # Which symbols failed (if applicable)
    'sub_tasks': {
        'step_name': {
            'success': bool,
            'duration_seconds': float,
            # ... step-specific metrics
        },
    },
}
```

**Rules:**
- Never return `bool`. Always return a dict.
- Include everything the orchestrator needs for the completion box. The orchestrator must never query the database for box data.
- Use actual measured values. If no measurement occurred, the value is `0` or `None`, not an assumption.
- Include `failed_symbols` as a list (not just a count) so the completion box can name them.

---

## 9. Progress Intervals

Two questions determine the right approach:

1. **Are per-item details informative?** If each line carries data the user cares about → log every item.
2. **What's the item scale?** Determines batch interval when details aren't important.

| Scale | Details Important | Details NOT Important |
|-------|-------------------|----------------------|
| Full universe (~750 symbols) | Per-item with data | Batch per 100 |
| Sub-universe (50-200 items) | Per-item with data | Batch per 50 |
| Contracts (thousands) | — | Batch per 1,000 |
| Huge (100K+ rows/pages) | — | Keep current intervals |
| Tiny (< 10 items) | Per-item (always) | Per-item (always) |

**"Details important"** = each line carries unique information (contracts collected, alert resolution outcome, earnings signal). If the line would just be "Processing AAPL... done" with no data, batch instead.

**Batch summary format:**

```
Progress: {done}/{total} ({pct:.1f}%) - ETA: {seconds:.0f}s
```

**60-second heartbeat rule:** If no progress line has been emitted for 60 seconds, emit one regardless of interval. Silent operations make the user wonder if the system hung.

**ETA guidance:** Only include ETA when per-item pace is stable (fixed DB inserts, uniform API calls). For variable-latency operations, omit ETA — an ETA that jumps around is worse than no ETA.

---

## 10. Error Behavior

### During a run

- **Isolated failures** (1-2 symbols): Log nothing mid-stream. Include in `failed_symbols` in the return dict.
- **Failure clusters** (10+ consecutive): Emit a single inline warning so the user knows *now*:
  ```
  WARNING: 10 consecutive failures — possible API issue (last: NVDA, GOOG, AMZN)
  ```
- **Unsalvageable** (API revoked, DB locked): Stop early. Return `{'success': False, 'failure_reason': '...'}`.

### After a run

The orchestrator reads the return dict and:
1. Draws completion box (always — success or failure)
2. If `success: False`, calls `queue_error()` with the full dict as context
3. If `severity: 'CRITICAL'`, calls `handle_error()` (spawn autofix, exit)

```python
# Orchestrator error routing pattern
try:
    result = strategy.run()
except Exception as e:
    result = {'success': False, 'failure_reason': str(e), 'errors': 1}

if result['success']:
    draw_completion_box(result)
else:
    draw_failure_box(result)
    queue_error(error_type='step_failure', context=result, severity='ERROR')
```

### Autofix integration

Strategies never import or call autofix directly. They return honest dicts. The orchestrator is the single integration point for error routing.

**Exception:** Subprocesses (via `_run_streaming_subprocess()`) can't return dicts through the process boundary — they return exit codes. These may call `queue_error()` directly (writing to the error JSON file). The orchestrator detects non-zero exit code and draws an error box.

### Three error categories

| Category | Example | Who detects | Who queues to autofix |
|----------|---------|-------------|----------------------|
| **Strategy degradation** | 47/747 symbols failed | Strategy (returns in dict) | Orchestrator |
| **Strategy fatal** | API auth revoked, DB locked mid-run | Strategy (returns `severity: 'CRITICAL'`) | Orchestrator |
| **Orchestrator crash** | Strategy threw unhandled exception | Orchestrator (try/except) | Orchestrator |

**Strategy degradation** and **strategy fatal** both flow through the return dict. The difference is severity — the orchestrator draws a failure completion box for both, then routes to `queue_error()` (ERROR) or `handle_error()` (CRITICAL).

**Orchestrator crash** is the safety net — the `except Exception` in `run_*()` methods. This stays regardless, because a strategy that crashes can't return a dict.

### CRITICAL error flow

CRITICAL errors should flow through the return dict, not bypass it:

```
Strategy detects unsalvageable condition (API auth dead, DB locked)
    ↓
Returns {'success': False, 'severity': 'CRITICAL', 'failure_reason': '...'}
    ↓
Orchestrator draws failure completion box (human sees clean output)
    ↓
Orchestrator calls handle_error() → spawns Claude → sys.exit(1)
```

This preserves the three-section pattern (mission → progress → completion) even for fatal errors. The human gets a clean error box, then the process exits and autofix takes over.

Reserve direct `handle_error()` + `sys.exit(1)` calls for pre-execution failures where no return path exists (import crashes, database unreachable at startup).

### Impact on autofix internals

Minimal. `queue_error()` already accepts a `context` dict — passing richer structured data instead of `{'error': str(e)}` is additive, not breaking. The prompt builders in `main_fix_launcher.py` and `batch_mode_spawner.py` format context into diagnostic prompts; richer context means better prompts automatically.

For full autofix reference, see `autofix/reference/AUTOFIX_CHEAT_SHEET.md`.

---

## 11. Anti-Patterns

| Anti-pattern | Example | Fix |
|--------------|---------|-----|
| Strategy draws a box | `create_status_box("DONE", [...])` | Return data. Let orchestrator draw the box. |
| Strategy draws a banner | `logging.info("=" * 60)` | Delete it. Return data instead. |
| Strategy announces completion | `print("[OK] Complete!")` | Delete it. Orchestrator handles this. |
| Orchestrator queries DB for box data | `cursor.execute("SELECT COUNT(*)")` | Use the strategy's return dict. |
| Manual emoji in logging.info for headlines | `logging.info("── 📊 DATA COLLECTION ──")` | Use `beautiful_log("Data Collection", 'info')` — keeps log file clean. |
| Multiple "starting" lines | `beautiful_log("Init...")` then `beautiful_log("Running...")` then `print("Starting...")` | One announcement. That's the start signal. |
| Multiple "done" lines | `beautiful_log("SUCCESS")` then `create_status_box("COMPLETE")` | One completion signal per layer. |
| Filler text in boxes | `"System: Ready for operations"` | Only measured facts. |
| beautiful_log inside a stats block | Stats block with one beautiful_log mixed in | Keep stats blocks as pure `logging.info()`. |
| Hardcoded counts in boxes | `"All ~750 symbols updated"` | Use actual count from return dict. |
| Zero-value noise | `"Smart money alerts: 0"` | Conditional: only log if > 0. |
| Returning bool | `return True` | Return a dict with metrics. |
| Diagnostic at INFO level | `logging.info("DEBUG: internal counter = 47")` | Use `logging.debug()`. |
| Strategy calling autofix | `from tools.autofix import handle_error` | Return `{'success': False, ...}`. Let orchestrator route. |

---

## 12. Checklist

Use this when building new phases or reviewing existing ones.

### Structure
- [ ] Orchestrator draws exactly 1 mission box before the strategy runs
- [ ] Strategy/coordinator produces no boxes (`create_status_box`) or banners (`phase_header`)
- [ ] Strategy returns a structured dict with all metrics
- [ ] Orchestrator draws exactly 1 completion box from the return dict
- [ ] No filler lines in boxes — only measured facts

### Output types (content-based, not role-based)
- [ ] `beautiful_log` used for headlines (phase starts, milestones, important facts) — by any module
- [ ] `logging.info()` used for stats blocks, per-item progress, cohesive data
- [ ] `logging.debug()` used for diagnostics and internals
- [ ] `print("")` used for decorative spacing only
- [ ] No manual emoji decorations in `logging.info()` for headlines (use `beautiful_log` instead)
- [ ] Zero-value lines are suppressed (conditional output)
- [ ] No `beautiful_log` mixed into `logging.info` stats blocks

### Progress
- [ ] Progress intervals follow the scale guide (Section 9)
- [ ] No silent gaps longer than 60 seconds
- [ ] ETA only included when pace is stable

### Errors
- [ ] Return dict includes `success`, `errors`, `failed_symbols`
- [ ] Inline WARNING emitted for failure clusters (10+)
- [ ] Strategy returns `{'success': False, 'failure_reason': '...'}` for unsalvageable runs
- [ ] Strategy never calls autofix directly (orchestrator routes errors)

### Integration
- [ ] Return dict has everything the completion box needs (no DB queries by orchestrator)
- [ ] Functions return dicts, not bools
- [ ] Coffee breaks use standard box format with "Up Next" line
- [ ] Sub-processes specify `encoding='utf-8', errors='replace'`

---

## Appendix A: Output Channel Summary

| What | Channel | Console? | Log file? |
|------|---------|----------|-----------|
| Orchestrator boxes | `create_status_box()` | Yes | Yes (borders + content) |
| Orchestrator messages | `beautiful_log()` | Yes (emoji + time) | Yes (message only) |
| Phase banners | `phase_header()` | Yes | Yes |
| Strategy milestones | `beautiful_log()` | Yes (emoji + time) | Yes (message only) |
| Strategy progress | `logging.info()` | Yes (time + message) | Yes (full format) |
| Diagnostics | `logging.debug()` | No | Only with --debug |
| Decorative spacing | `print("")` | Yes | No |
| Inline warnings | `logging.warning()` | Yes | Yes |

## Appendix B: Emoji Level Map

| Level | Emoji | When to use |
|-------|-------|-------------|
| `'info'` | ℹ️ | Phase starts, context facts, "Starting X" |
| `'success'` | ✅ | Completion confirmations, validation passed |
| `'warning'` | ⚠️ | Non-fatal issues, degraded operations |
| `'error'` | ❌ | Failures, crashes |
| `'phase'` | 🔥 | Major phase transitions (orchestrator-level) |

## Appendix C: Real Console Output Example

This is what a well-formatted FM cycle looks like in production:

```
── Cycle 1 | 09:30:01 | 746 symbols ────────────────────────────

ℹ️ 09:30:01 - Starting FM Collector
ℹ️ 09:30:01 - Scan timestamp: 2026-02-19 09:30:01
ℹ️ 09:30:01 - Fetching underlying prices for 746 symbols
✅ 09:30:16 - Prices received for 746 symbols
✅ 09:30:16 - Symbol list validated: 746 unique, no duplicates

09:30:16 - Fetching option expirations for A
09:30:18 - Option chains collected for A — 42 contracts
09:30:19 - Option chains collected for AAPL — 312 contracts
...
09:49:52 - Option chains collected for JETS — 185 contracts

✅ 09:49:52 - Batch validated: 101,300 contracts, no duplicates
✅ 09:52:53 - Stored 101,300 contracts in 180.1s (scan: 09:30:01)
✅ 09:52:53 - Collection complete (1371.9s — API: 1191.8s + DB Write: 180.1s)

ℹ️ 09:52:53 - Starting FM Analyzer
ℹ️ 09:52:53 - Analyzing 101,300 contracts for significant flow activity
ℹ️ 09:52:55 - Market regime: normal

09:53:04 - Contracts updated: 101,300
09:53:04 - Missing baselines: 187
09:53:04 - Premium filter: 234 passed (101,066 filtered)
09:53:04 - Volume filter: 124 passed (101,176 filtered)
09:53:04 - High conviction alerts (8.0+): 2
09:53:04 - Unified alerts (6.0+): 10
09:53:04 - Total analysis time: 10.82 seconds
09:53:04 - Total significant flows detected: 12

ℹ️ 09:53:04 - Starting FM Alerts
09:53:04 - Processing alerts for scan: 2026-02-19 09:30:01
09:53:04 - Found 7 alert candidates from scan
09:53:04 - Filters applied: 2 passed, 5 filtered (4 ETFs, 1 delta)

09:53:05 - 🚨 FLOW MONITOR ALERTS

09:53:05 - Scoring v2: premium + volume surprise (smart money removed 2026-04)
09:53:05 - 🟡 MEDIUM ALERTS (Score 3.5-4.9)
09:53:05 - SMCI [LAR] $32.0 calls (8d) | Vol: 10,720 (21.4x) | ...
09:53:05 - OXY [LAR] $50.0 calls (29d) | Vol: 2,743 (5.5x) | ...

📊 09:53:05 - 2 alerts saved (0 HIGH, 2 MEDIUM, 0 LOW) to flow_alerts
09:53:05 - Complete alert saved for SMCI 32.0 with score 4.65
09:53:05 - Complete alert saved for OXY 50.0 with score 4.10
09:53:05 - Alert persistence complete: 2 saved, 0 failures

ℹ️ 09:53:32 - Starting FM Watchlist
09:53:32 - Watchlist updated: 2 created, 0 updated from 2 alerts in flow_watchlist_daily

ℹ️ 09:53:33 - Starting FM News Enrichment
09:53:33 - Fetching news for SMCI (lookback: 3 days, limit: 50)
09:53:33 - Retrieved 18 articles for SMCI
09:53:33 - News enrichment for SMCI: score=0.04, label='Bullish 6/Bearish 4/Neutral 8'
09:53:45 - Fetching news for OXY (lookback: 3 days, limit: 50)
09:53:45 - Retrieved 22 articles for OXY
09:53:45 - News enrichment for OXY: score=0.24, label='Bullish 13/Bearish 4/Neutral 5'
✅ 09:53:45 - News enrichment complete: 2 enriched, 0 skipped, 0 failed

ℹ️ 09:53:47 - Starting FM Dip Detection
09:53:47 - Dip detected: VST (CALL) via zscore - $170.59->$168.25 (-1.37%)
09:53:47 - Buy-the-dip opportunities: 1 detected (zscore: 1, fallback: 0)
✅ 09:53:48 - Email notification sent for 1 dip(s)

ℹ️ 09:53:49 - Starting Quick Sync
09:53:49 - Syncing flow_alerts, flow_options_scans, flow_watchlist_daily to query database
✅ 09:54:49 - Quick-sync completed: 101,383 rows in 60.8s

✅ Cycle 1 complete - Performance Breakdown:
📊 Collection: 1371.9s (API: 1191.8s + DB: 180.1s)
🔍 Analysis: 10.8s
🚨 Alerts: 28.1s
📋 Watchlist/News/Dip: 17.2s
🔄 Quick Sync: 60.8s
⏱️ Total: 1488.8s (24.8 min)

📈 PERFORMANCE SUMMARY (2 cycles)
Average cycle: 1456.3s (24.3 min)
...
```
