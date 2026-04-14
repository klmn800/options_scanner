# Console Output Standard

The system uses a role-based output architecture. Each role has clear responsibilities for what it produces, what it never produces, and what it returns. Each phase is intended to have a consistent appearance.

---

## Philosophy: Smart Logging, Not Minimal Logging

The goal of this refactor is **not** to reduce verbosity. It's to produce **smart logging** — the right information at the right density. That can mean *more* output in some places and *less* in others.

- **More:** If a summary block shows useful diagnostics (filter counts, data quality, timing breakdowns), keep it — even if it's 15 lines.
- **Less:** If the same fact is announced twice in different formats (e.g., "Collection complete" appearing as both a raw timestamp line and an emoji line), cut the redundant one.
- **Channel, not volume:** Many issues are about *how* output is produced (strategy drawing `═══` banners, using `beautiful_log()` instead of `logging.info()`), not about how *much* there is.

The refactor changes **who produces output** and **through what API**, not necessarily **how much**. When in doubt about whether to keep or cut a piece of output, ask Ben.

---

## The Pattern

```
════════════════════════════════════════════════════════════
                PHASE N: PHASE NAME
════════════════════════════════════════════════════════════

+-- ORCHESTRATOR OPENS (mission box) ----------------------+

  ╔══════════════════════════════════════════════════════╗
  ║ Title of Step                                        ║
  ╠══════════════════════════════════════════════════════╣
  ║ Mission: One sentence describing the goal            ║
  ║ Detail line if needed                                ║
  ║ Detail line if needed                                ║
  ╚══════════════════════════════════════════════════════╝

+-- STRATEGY PROGRESS (the only thing the strategy prints) -+
+-- Style depends on operation — per-item or batch summary  -+

  Fetching option expirations for AAPL
  ✅ Flushed 892 contracts to storage (AAPL)
  Fetching option expirations for ABBV
  ✅ Flushed 634 contracts to storage (ABBV)
  ...
  📊 Progress: 26.8% (200/747) | Success: 100.0% | Contracts: 24,891
  ...

+-- ORCHESTRATOR CLOSES (completion box from return dict) --+

  ╔══════════════════════════════════════════════════════╗
  ║ Step Complete                                        ║
  ╠══════════════════════════════════════════════════════╣
  ║ Symbols processed: 747                               ║
  ║ Records created: 747                                 ║
  ║ Errors: 0                                            ║
  ║ Duration: 3.4 minutes                                ║
  ╚══════════════════════════════════════════════════════╝
```

That's it. Three sections. Nothing else.

---

## Layer 1: Orchestrator (main_runners.py)

The orchestrator owns ALL visual structure.

**Produces:**
- Phase headers (`════ PHASE N: NAME ════`)
- Mission box before each step (what and why)
- Completion box after each step (built from strategy's return dict)
- Coffee breaks (see Coffee Break Format below)
- Day-end summary

**Never produces:**
- Progress lines (that's the strategy's job)
- Duplicate announcements (`beautiful_log` success + box = pick one, use the box)

**Completion box rules:**
- Built ONLY from the strategy's return dict — never query the database separately
- Include: key counts, duration, error count
- If errors > 0: list affected symbols
- No filler lines ("System: Ready for operations", "Protection: Database secured")

---

## Layer 2: Strategy / Tool

The strategy owns ONLY progress output.

**Produces:**
- Progress lines at reasonable intervals (see table below)
- Inline warnings (e.g., "WARNING: WOLF - greeks null, skipping")
- Phase labels within the strategy if multi-step (e.g., "[1/3] Fetching...", "[2/3] Archiving...")

**Never produces:**
- Boxes (`create_status_box`, `═══` banners, `===` separators)
- Completion announcements (`"COMPLETE"`, `"SUCCESS"`, `"[OK]"`, celebration blocks)
- Mission/opening announcements
- `beautiful_log()` calls

**Permitted exception — inline warnings:**
Strategies may emit single-line warnings for genuinely exceptional conditions (mass failures, unexpected API states, critical thresholds). These must be plain `print()` or `logging.warning()` prefixed with `WARNING:` — never `beautiful_log()`, boxes, or banners.
```
  WARNING: 47 consecutive API failures — possible rate limit
  WARNING: WOLF - greeks null, skipping
```

**Returns:**
A dict with everything the orchestrator needs for the completion box.

```python
return {
    'success': True,
    'symbols_processed': 747,
    'records_created': 747,
    'errors': 0,
    'failed_symbols': [],
    'duration_seconds': 205.4,
    # ... any step-specific metrics
}
```

---

## Coordinators (fm_main.py, op_main.py, ei_main.py)

Some strategies have multi-step pipelines that need sequencing — OP runs Collection → Rollup → Timing → Health Report, EI runs Fetch → Snapshots → Calculations → Moves, FM post-market runs 5 tasks in order. These files are **coordinators**: they sequence sub-tasks and aggregate results.

**A coordinator:**
- Calls component modules in sequence
- Aggregates return dicts from each into a single combined dict
- Handles errors and decides whether to continue or abort
- Returns the combined dict to main_runners.py
- **Never produces:** boxes (`╔═╗`, `═══` banners), `beautiful_log()` calls, completion celebrations, mission announcements
- **May produce:** lightweight sub-phase progress via `logging.info()` — sub-phase headers (`── NAME (N/M) ──`), tree diagram intros (`├─` / `└─`), and compact per-step confirmation lines. These are a third visual layer between orchestrator and strategy. See `VISUAL_DESIGN_REFERENCE.md` Section 15 for the full specification.

**The orchestrator decides granularity.** The coordinator's return dict should include a `sub_tasks` key with per-task results. main_runners.py then decides whether to draw per-sub-task boxes (for visibly separate multi-minute operations) or a single wrapper box (for quick sequential tasks).

```python
# Coordinator return dict pattern
return {
    'success': True,
    'duration_seconds': 245.8,
    'sub_tasks': {
        'collection': {'success': True, 'symbols_collected': 747, 'total_contracts': 18432, ...},
        'rollup': {'success': True, 'summaries_created': 747, ...},
        'timing': {'success': True, 'contracts_updated': 12891, ...},
    },
    'errors': 0,
    'failed_symbols': [],
}
```

**Model file:** `fm_session_stats.py` — computes, aggregates, returns. Provides `format_end_of_day_lines()` that returns strings without printing them. The caller decides what to display.

---

## Delegated Orchestrators (FM Market Hours)

Some operations run for hours and can't be wrapped in a single mission/completion box pair. Flow Monitor's market hours loop runs ~20-minute cycles for 6.5 hours. For these, the coordinator gets promoted to **delegated orchestrator** with constrained output privileges. The current FM market hours logging patterns (per-symbol collection, cycle summaries) are good and should be preserved — the goal here is to formalize what already works, not reduce verbosity.

**A delegated orchestrator may:**
- Emit per-cycle progress lines (per-symbol collection output, cycle summaries)
- Emit inline warnings for failure clusters
- Use `logging.info()` or `print()` for output (same channels as strategies)

**A delegated orchestrator must not:**
- Draw boxes, banners, or separators (see exception below)
- Use `beautiful_log()` or `create_status_box()` (see exception below)
- Announce its own completion ("MARKET HOURS COMPLETE")
- Define its own formatting functions

**Exception: coffee breaks.** FM's module-level `coffee_break()` function uses `create_status_box()` to draw pause boxes between market hours cycles and between post-market tasks. This is permitted because coffee breaks are system pauses, not strategy output — they serve the same role as the orchestrator's `self.coffee_break()`. See `VISUAL_DESIGN_REFERENCE.md` Section 18 for the target format.

**A delegated orchestrator returns:**
A comprehensive session dict when the long-lived operation ends. The orchestrator draws the completion box from this dict.

**Restart resilience:** FM session stats are saved to `logs/daily_state.json` after each cycle. On restart, `FMSessionStats` restores from the file if today's date matches, so the session summary reflects the full day. The orchestrator's phase results are also persisted here — see Package 0, Steps 6-7 in `WORK_PACKAGES.md`.

```
+-- Example: FM Market Hours output over 6.5 hours --+

  === Cycle 1 | 9:35 AM | 747 symbols ===
  Collecting AAPL... NVDA... GOOG... (per-symbol output)
  Cycle 1 complete: 747 collected, 12 alerts, 3.2s

  === Cycle 2 | 9:55 AM | 747 symbols ===
  Collecting AAPL... NVDA... GOOG...
  Cycle 2 complete: 747 collected, 8 alerts, 2.9s

  ... (cycles continue) ...

  WARNING: 10 consecutive failures — possible API issue

  === Cycle 20 | 4:00 PM | 747 symbols ===
  Collecting AAPL... NVDA... GOOG...
  Cycle 20 complete: 747 collected, 5 alerts, 3.1s
```

The orchestrator wraps this with a mission box before and a session summary completion box after.

See `VISUAL_DESIGN_REFERENCE.md` "Full Phase 2 Example" for the complete soup-to-nuts mockup covering pre-market → market hours → post-market with all transitions, coffee breaks, and the session summary box.

---

## Roles Summary

| Role | Who | Produces | Returns |
|------|-----|----------|---------|
| **Orchestrator** | main_runners.py | Boxes (`╔═╗`), phase headers (`═══`), coffee breaks, day-end summary | N/A (top level) |
| **Coordinator** | op_main.py, ei_main.py, fm pre/post-market | Sub-phase headers (`──`), tree intros (`├─`), step confirmations — via `logging.info()` only. No boxes, banners, celebrations. | Combined dict with `sub_tasks` |
| **Delegated Orchestrator** | fm_main.py market hours | Per-cycle progress, per-symbol output, inline warnings | Session summary dict |
| **Strategy** | fm_collector, op_collector, etc. | Progress lines, inline warnings | Metrics dict |

---

## Progress Interval Guide

Progress intervals are NOT one-size-fits-all. Two questions determine the right approach:

1. **Are per-item details informative?** If yes → log every item with relevant data.
2. **What's the item scale?** Determines batch size when details aren't important.

| | Details Important | Details NOT Important |
|---|---|---|
| **Full universe (~750 symbols)** | Per-item with info | Batch summary per 100 |
| **Sub-universe (50-200 items)** | Per-item with info | Batch summary per 50 |
| **Contract universe (thousands)** | — | Batch summary per 1,000 |
| **Huge (100K+ pages/rows)** | — | Keep current intervals |
| **Tiny (< 10 items)** | Per-item (always) | Per-item (always) |

**"Details important"** means each item's line carries information the user cares about — contracts fetched, alert resolution outcome, earnings signal triggered. If the line would just be "Processing AAPL... done" with no useful data, batch instead.

See `VISUAL_DESIGN_REFERENCE.md` section 8 for the complete per-process spec and format examples.

**Batch summary format:**
```
  Progress: {done}/{total} ({pct:.1f}%) - ETA: {seconds:.0f}s
```

No prefix timestamp (the orchestrator's boxes have timestamps).
Indent 2 spaces to visually nest under the mission box.

**Time-based heartbeat override:**
If no progress line has been emitted for **60 seconds**, emit one regardless of the item-count interval. Silent operations make the user wonder if the system hung.

**ETA guidance:**
ETA is optional. Only include it when the per-item pace is reasonably stable (e.g., fixed DB inserts, uniform API calls). For operations with highly variable latency (e.g., mixed API endpoints, conditional processing), omit ETA and show only count and percentage. An ETA that jumps around or goes backwards is worse than no ETA.

---

## Error Behavior Mid-Run

The completion box handles error reporting after the fact. But what about *during* a run that's going sideways?

**Strategy responsibilities during degraded runs:**
- **Isolated failures** (1-2 symbols fail): Log nothing mid-stream. Include them in `failed_symbols` in the return dict. The completion box handles it.
- **Clusters of failures** (e.g., 10+ consecutive): Emit a single inline warning so the user knows something is wrong *now*, not 5 minutes from now.
  ```
    WARNING: 10 consecutive failures — possible API issue (last: NVDA, GOOG, AMZN)
  ```
- **Threshold for early abort**: If a strategy determines the run is unsalvageable (e.g., API key revoked, database locked), it should stop early and return a result dict with `success: False` and a `failure_reason` string. Don't burn through 700 symbols that will all fail.

**Orchestrator responsibilities:**
- If the return dict has `success: False`, the completion box should clearly reflect the failure — not just show `Errors: 642` in the same format as a successful run.
- Include `failure_reason` in the box when present.

**Note:** This section covers *console output* behavior during errors. For actual error handling, routing, and recovery decisions, the Autofix system (`tools/autofix.py`, `autofix/reference/AUTOFIX_CHEAT_SHEET.md`) is the authoritative reference and always overrides this guide.

---

## Output Channels

| What | Channel | Goes to console? | Goes to .log? |
|------|---------|-----------------|---------------|
| Orchestrator boxes | `log_utils.create_status_box()` | Yes | Yes |
| Orchestrator messages | `log_utils.beautiful_log()` | Yes | Yes |
| Strategy progress (batch summaries) | `print()` or `logging.info()` | Yes | Yes |
| Strategy progress (per-item, details important) | `logging.info()` | Yes | Yes |
| Strategy debug detail (diagnostic internals) | `logging.debug()` | No | Only with --debug |
| Third-party library noise (yfinance, etc.) | Suppressed | No | No |

If a strategy uses `print()`, it must go through `sys.stdout` (which log_utils captures).
If a strategy uses `logging.info()`, it naturally reaches both channels.

---

## Coffee Break Format

When the orchestrator pauses between steps, it uses the standard box format — one box when entering the wait (with dynamic "Up Next"), one when resuming.

Every coffee break includes an **"Up Next"** line showing which step follows. This is resolved dynamically from a `STEP_SEQUENCE` constant — not hardcoded at each call site. Call sites pass `after_step=` to identify which step just finished; the next entry in the sequence is looked up automatically. If steps are reordered, only `STEP_SEQUENCE` needs updating.

```
  ╔══════════════════════════════════════════════════════╗
  ║ ☕ Coffee Break                                      ║
  ╠══════════════════════════════════════════════════════╣
  ║ Time for a quick stretch                             ║
  ║ Duration: 60 seconds                                 ║
  ║ Up Next: Earnings Arbitrage Scanner                  ║
  ╚══════════════════════════════════════════════════════╝

  ╔══════════════════════════════════════════════════════╗
  ║ Resuming Operations                                  ║
  ╠══════════════════════════════════════════════════════╣
  ║ Wait complete — continuing pipeline                  ║
  ╚══════════════════════════════════════════════════════╝
```

No countdown updates or periodic "still waiting" messages between the two boxes. "Up Next" is omitted only when the coffee break follows the final step of the day.

See `VISUAL_DESIGN_REFERENCE.md` section 6 for the full specification and `STEP_SEQUENCE` definition.

---

## Anti-Patterns (do not do these)

| Anti-pattern | Example | Fix |
|--------------|---------|-----|
| Strategy draws a box | `logging.info("=" * 60)` | Delete it. Return data instead. |
| Strategy announces completion | `print("[OK] Completed")` | Delete it. Orchestrator handles this. |
| Orchestrator queries DB for completion stats | `cursor.execute("SELECT COUNT(*)")` | Use the strategy's return dict. |
| Multiple "starting" lines | `beautiful_log("Initializing...")` then `beautiful_log("Running...")` then `print("Starting...")` | One mission box. That's the start signal. |
| Multiple "done" lines | `beautiful_log("SUCCESS")` then `create_status_box("COMPLETE")` | One completion box. That's the done signal. |
| Filler text in boxes | `"System: Ready for safe operations"` | Only include measured facts. |
| Batch every 100 on 13K contracts | 134 lines of batch summaries | Use per 1,000 for contract-scale operations. |
| No progress on 5-min operation | Total silence | Use the interval guide, or at minimum the 60-second heartbeat. |
| Hardcoded counts in boxes | `"All ~750 symbols updated"` | Use actual count from return dict. |

---

## Checklist: Does My Phase Follow the Standard?

Use this when building new phases or refactoring existing ones.

- [ ] Orchestrator draws exactly 1 mission box before the strategy runs
- [ ] Strategy prints only progress lines (no boxes, no banners, no celebrations)
- [ ] Strategy returns a structured dict with all metrics
- [ ] Orchestrator draws exactly 1 completion box from the return dict
- [ ] Progress lines follow the interval guide (per-item when details matter, batched otherwise)
- [ ] No `beautiful_log("SUCCESS")` + `create_status_box("COMPLETE")` double
- [ ] No filler lines in the completion box
- [ ] Third-party library loggers suppressed if noisy
- [ ] Long operations (>60s) have at least some progress indication
- [ ] No silent gaps longer than 60 seconds (use heartbeat override)
- [ ] ETA only included when per-item pace is stable; omitted for variable-latency operations
- [ ] Error details included when errors > 0 (symbol names, not just counts)
- [ ] Strategy emits inline WARNING for failure clusters, not just silent accumulation
- [ ] Return dict includes `success: False` and `failure_reason` for unsalvageable runs
- [ ] Error handling defers to Autofix protocols where applicable
- [ ] Coffee breaks use standard box format (not bare text)
- [ ] Coordinators (op_main.py, ei_main.py) produce no boxes, banners, celebrations, or `beautiful_log()` calls
- [ ] Coordinator sub-phase output (headers, tree intros, confirmations) uses `logging.info()` — not `safe_log()`, `print()`, or `beautiful_log()`
- [ ] Coordinator return dicts include `sub_tasks` key with per-task results
- [ ] Delegated orchestrators (FM market hours) use `logging.info()`/`print()`, not `beautiful_log()` or boxes
- [ ] Functions returning bool are converted to return structured dicts
- [ ] Autofix `queue_error()` called by orchestrator using the return dict as context (not bare `str(e)`)
- [ ] Strategies never import or call autofix directly (except subprocesses — see below)
- [ ] CRITICAL failures returned in dict (`severity: 'CRITICAL'`), not actioned by strategy via `handle_error()`

---

## Autofix Integration

The Console Output Standard and the Autofix system (`tools/autofix.py`) share the same integration point: the orchestrator. Both care about the same moment — a strategy fails — and both benefit from the same structured return dict. These two systems should be unified, not parallel.

### Principle: One Error Path, Not Two

Today, `queue_error()` gets called in the `except` block of each `run_*()` method with a bare exception string. After the overhaul, the orchestrator passes the strategy's full return dict as `queue_error()` context. The spawned Claude session gets the same structured failure diagnosis the completion box showed — symbols processed before failure, what failed, why it stopped — instead of just `"Exception: ..."`.

### Principle: Orchestrator Is the Single Integration Point

Strategies never import or call autofix. They return honest dicts. The orchestrator reads the return dict and decides:
1. Draw completion box (always — success or failure)
2. If `success: False`, call `queue_error()` with the dict as context
3. If `severity: 'CRITICAL'` in the dict, call `handle_error()` after drawing the error box

This keeps error routing in one place, not scattered across strategy files.

### Three Error Categories

| Category | Example | Who detects | Who queues to autofix |
|----------|---------|-------------|----------------------|
| **Strategy degradation** | 47/747 symbols failed | Strategy (returns in dict) | Orchestrator |
| **Strategy fatal** | API auth revoked, DB locked mid-run | Strategy (returns `severity: 'CRITICAL'`) | Orchestrator |
| **Orchestrator crash** | Strategy threw unhandled exception | Orchestrator (try/except) | Orchestrator |

**Strategy degradation** and **strategy fatal** both flow through the return dict. The difference is severity — the orchestrator draws a failure completion box for both, then routes to `queue_error()` (ERROR) or `handle_error()` (CRITICAL).

**Orchestrator crash** is the safety net — the `except Exception` in `run_*()` methods. This stays regardless, because a strategy that crashes can't return a dict.

### CRITICAL Error Flow

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

This preserves the console output standard's three-section pattern (mission → progress → completion) even for fatal errors. The human gets a clean error box, then the process exits and autofix takes over.

Reserve direct `handle_error()` + `sys.exit(1)` calls for pre-execution failures where no return path exists (import crashes, database unreachable at startup).

### Orchestrator Error Routing Pattern

```python
# IDEAL: One path, richer context
try:
    result = strategy.run()
except Exception as e:
    # Safety net for unhandled crashes
    result = {'success': False, 'failure_reason': str(e), 'errors': 1}

# Console output — always
if result['success']:
    draw_completion_box(result)
else:
    draw_failure_box(result)

# Autofix routing — only on failure
if not result['success']:
    severity = result.get('severity', 'ERROR')
    queue_error(
        error_type=f'{step_name}_failure',
        context=result,  # The whole dict — autofix gets everything
        severity=severity
    )
    if severity == 'CRITICAL':
        handle_error(...)  # Spawn immediate fix, exit
```

### Subprocess Exception

Strategies that run via `_run_streaming_subprocess()` can't return dicts through the process boundary — they return exit codes. For these:
- The subprocess may call `queue_error()` directly (writing to the error JSON file)
- The orchestrator detects non-zero exit code and draws an error box
- This is a pragmatic exception to the "strategies never call autofix" rule

### Impact on Autofix Internals

Minimal. `queue_error()` already accepts a `context` dict — passing richer structured data instead of `{'error': str(e)}` is additive, not breaking. The prompt builders in `main_fix_launcher.py` and `batch_mode_spawner.py` format context into diagnostic prompts; richer context means better prompts automatically. The instruction files, safety rails, batch scheduling, and deduplication logic are unchanged.
