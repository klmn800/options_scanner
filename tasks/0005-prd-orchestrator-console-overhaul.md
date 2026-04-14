# PRD: Orchestrator Console Output Overhaul

**PRD ID:** 0005
**Date:** 2026-02-11
**Source:** `ORCHESTRATOR_AUDIT.md` — full trading day audit (Feb 10, 2026)
**Scope:** Logging architecture + display layer rework. Critical bugs are tracked separately and should be fixed before this PRD work begins.

---

## 1. Introduction / Overview

The orchestrator (`main.py`) and its strategies produce console output through 3 incompatible systems: `beautiful_log()` (sys.stdout.write), `logging.info()` (Python logging), and bare `print()` calls. This creates duplicated output, inconsistent formatting, incomplete log files, and a confusing developer experience.

This PRD redesigns the console output as a **two-layer system**:
- **Content layer** (strategies/tools): Progress output — per-symbol lines, warnings, batch progress
- **Framing layer** (orchestrator): Uniform decoration — phase headers, step boxes, completion summaries

The orchestrator becomes the sole owner of visual structure (boxes, phase transitions, day summary). Strategies focus on doing their job and returning structured results.

---

## 2. Goals

1. **Single logging system** — All output (console + file) flows through one shared utility (`tools/log_utils.py`), eliminating 3 competing approaches
2. **No duplicate output** — Each event announced exactly once. No double opening boxes, no triple completion announcements
3. **Complete log files** — The `.log` file captures everything that appeared on console, including orchestrator-level output that currently bypasses it
4. **Layered display ownership** — Strategies print progress, orchestrator frames it. Clear separation, no overlap
5. **Dynamic welcome banner** — Built at runtime from the actual schedule, always accurate, no maintenance
6. **Honest day-end summary** — Built from actual collected results, not hardcoded
7. **Reduced noise** — Drop countdown spam, eliminate DEBUG lines in production, suppress per-alert logging to log-file-only where appropriate

---

## 3. User Stories

- **As the operator (Ben)**, I want a scrolling heartbeat during long operations so I know the system is alive, but I don't want the same completion announced 2-3 times per step.
- **As a debugger**, I want the `.log` file to contain a complete record of what happened — including orchestrator announcements that currently only go to console.
- **As a reader of the welcome banner**, I want to see every step that will run today, with step numbers matching the log output, so I can use it as a reference throughout the day.
- **As a reviewer of the day-end summary**, I want honest pass/fail status per step based on what actually happened, not hardcoded "PERFECT EXECUTION."

---

## 4. Functional Requirements

### 4.1 Shared Logging Utility (`tools/log_utils.py`)

1. Extract `beautiful_log()` from `main_ui.py` into a standalone function in `tools/log_utils.py` that any module can import
2. Extract `create_status_box()` into `tools/log_utils.py` as a standalone function
3. Both functions must write to **both** console (sys.stdout) and the Python logging system (so output reaches the `.log` file)
4. `beautiful_log()` must accept a `level` parameter ('info', 'success', 'error', 'warning', 'phase') and map to appropriate emoji + logging level
5. Remove the duplicate `beautiful_log()` copy from `fm_main.py` — it should import from `tools/log_utils.py`
6. `main_ui.py` methods should delegate to the shared utility (preserve the mixin interface so `self.beautiful_log()` still works, but implementation calls through to `log_utils`)
7. Add a `phase_header()` function for phase transitions (visual separator between Phase 1, 2, 3, etc.)
8. The `✅ ✅` stutter must be fixed: when `beautiful_log("✅ MESSAGE", 'success')` is called, the function should not prepend another ✅. Either strip leading emoji from the message or don't add emoji when the message already starts with one.

### 4.2 Display Ownership — Orchestrator Framing Layer

9. **Opening boxes**: Only `main_runners.py` draws an opening box per step (the "mission box"). Strategies must NOT draw their own opening boxes.
10. **Completion boxes**: Only `main_runners.py` draws a completion box per step, populated from the strategy's return data. Strategies must NOT draw their own completion boxes/banners.
11. **Progress output**: Strategies continue printing their own progress lines (per-symbol processing, warnings, batch progress). This is the scrolling heartbeat.
12. **Strategy return values**: Each strategy must return structured results (dict) with enough data for the orchestrator to build a meaningful completion box. Where strategies already return dicts (Option Pipeline), use existing data. Where they don't, add return values.
13. Remove all `create_status_box()` calls from within strategies that duplicate the orchestrator's framing. Specifically:
    - `op_main.py`: Remove "OID PIPELINE STARTING", "OID COLLECTION COMPLETE", "OID PIPELINE COMPLETE" boxes
    - `fm_main.py`: Remove "POST-MARKET COMPLETE" box (orchestrator handles this)
    - `ei_main.py`: Remove redundant opening/closing boxes when called from orchestrator
    - Other strategies: audit and remove as found
14. Phase transition headers: Add visual phase headers for all 5 phases, not just Phase 2 (Flow Monitor). Format:
    ```
    ════════════════════════════════════════════════════════════
     PHASE 1: PRE-MARKET OPERATIONS
    ════════════════════════════════════════════════════════════
    ```

### 4.3 Dynamic Welcome Banner

15. `print_banner()` in `main_ui.py` must build the process list dynamically at runtime
16. Include ALL steps with their step numbers (1.1 through 5.3), matching the log output
17. Show Friday-only steps conditionally (only on Fridays), with a "(Friday only)" label
18. Use actual symbol count from config (e.g., "758 symbols" not "~750")
19. Remove time estimates from the banner (per design decision: drop them entirely)
20. The banner must be the single source of truth for "what runs today"

### 4.4 Day-End Summary Box

21. Replace the hardcoded "PERFECT EXECUTION" / status box with a summary built from actual collected results
22. Track success/failure of each step throughout the day using a results dict
23. Show actual failure counts and which steps failed (e.g., "15 backfill failures, 1 autofix error")
24. Show total runtime for the day
25. Show steps that were skipped and why (e.g., "Weekly ops: Skipped (not Friday)")
26. Only show "PERFECT EXECUTION" if every step genuinely succeeded with zero failures
27. For the "partial success" path, show per-step status with meaningful detail, not just OK/FAIL

### 4.5 Noise Reduction

28. **Coffee break countdown**: Replace 11-line countdown with a single line: `"☕ Coffee break: 60 seconds (context message)"` — then one line when done: `"☕ Resuming operations"`. No per-second or per-10-second countdown.
29. **DEBUG lines**: Remove all bare `print("DEBUG: ...")` statements from production code paths (`op_main.py`, `fm_main.py`, etc.)
30. **Time estimates**: Remove all hardcoded estimated durations from mission boxes ("~14 minutes", "~150 min", "~6 min", etc.)
31. **Cycle counter**: Remove `daily_cycle_count` tracking — it's always 1 when auto-started daily and adds no value
32. **Dependency checks**: Remove "✓ SQLite3 available / ✓ psutil available" from console output (these never fail)
33. **Dead feature references**: Investigate and remove or fix: "Interesting Strikes: 0", "Momentum updates: 0", "Analysis Updates: 0" in completion boxes. If the features are dead, remove the lines. If alive, fix why they're always 0.
34. **Daily evaluator**: Individual alert processing lines (`Processing alert 9413 (symbol: HOOD, 2026-02-27)`) should go to log file only, not console. Console should show batch progress only (e.g., `"Progress: 50/359 alerts evaluated"`)
35. **FM cycle performance**: Each cycle's performance summary should be printed once (not duplicated via both print() and logging.info())
36. **Health report paths**: When showing health report filenames, include the full relative path (e.g., `logs/option_pipeline_health_2026-02-10.txt`)

### 4.6 Terminology Cleanup

37. Rename `OIDOrchestrator` class in `op_main.py` to `OPOrchestrator` (or `OptionPipelineOrchestrator`)
38. Replace all "OID" references in log messages, banners, and comments with "OP" or "Option Pipeline"
39. Fix internal phase numbering in `op_main.py`: currently shows "Phase 1/5, 3/5, 4/5" — should be sequential (1/4, 2/4, 3/4, 4/4) or match what phases actually exist

### 4.7 Market Regime Narrative

40. Step 2.5 (Market Regime Summary) should output a 1-line market narrative after completion, e.g.: `"Market Regime: Bull | SPY +1.2% | VIX 14.3 | Trending"` — this turns a currently invisible step into something informative

---

## 5. Non-Goals (Out of Scope)

- **Critical bug fixes** (rotate_daily_log inheritance bug, view recreation after sync, JETS investigation) — these are separate immediate fixes, not part of the overhaul
- **Strategy logic changes** — we're only changing how strategies communicate their output, not what they calculate
- **New features** — no new monitoring, alerting, or analysis capabilities
- **TUI changes** — Morning View TUI is unaffected
- **Log file format changes** — the `.log` file format (timestamp - LEVEL - message) stays the same
- **Autofix integration** — existing autofix hooks are preserved as-is
- **Performance optimization** — this is a display/logging rework, not a performance project
- **fm_main.py internal cycle logging** — the Flow Monitor's internal cycle loop (collection → analysis → alerts) is complex and tightly coupled. Cleaning up its duplicate output (Req 35) is in scope, but restructuring its internal flow is not.

---

## 6. Design Considerations

### Architecture: Two-Layer Display Model

```
┌─────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (main_runners.py)  — FRAMING LAYER            │
│  • Phase headers ("PHASE 1: PRE-MARKET")                    │
│  • Step mission boxes ("Step 1.1: Morning Option Pipeline")│
│  • Step completion boxes (from strategy return values)       │
│  • Day-end summary (from collected results)                  │
│  • Coffee breaks (single line)                              │
├─────────────────────────────────────────────────────────────┤
│  STRATEGIES / TOOLS  — CONTENT LAYER                        │
│  • Per-symbol progress ("Processing AAPL - 1,247 contracts")│
│  • Warnings ("WARNING: HON - no data returned")             │
│  • Batch progress ("Progress: 50/359")                      │
│  • Phase labels within strategy ("Phase 1/4: Collection")   │
│  • NO boxes, NO banners, NO completion announcements        │
└─────────────────────────────────────────────────────────────┘
```

### Shared Utility: `tools/log_utils.py`

```python
# Standalone functions — no class, no mixin dependency
from tools.log_utils import beautiful_log, create_status_box, phase_header

beautiful_log("Processing complete", level='success')  # Console + log file
create_status_box("STEP COMPLETE", ["Line 1", "Line 2"])  # Console + log file
phase_header("PRE-MARKET OPERATIONS", phase_number=1)  # Visual separator
```

### Backward Compatibility

`main_ui.py` mixin methods (`self.beautiful_log()`, `self.create_status_box()`) will delegate to the shared utility. Existing orchestrator code continues to use `self.beautiful_log()` — no refactor of calling code in main.py/main_runners.py required. Strategies that need logging import directly from `tools/log_utils.py`.

### Example: Before vs After for a Single Step

**BEFORE (current — Step 1.2 Arbitrage Scanner):**
```
╔══ EARNINGS ARBITRAGE SCANNER ══╗        ← main_runners.py mission box
║ Mission: Find pre-market...    ║
╚════════════════════════════════╝
🔥 07:12:58 - Initializing earnings arbitrage scanner
🔥 07:12:58 - Running morning arbitrage scanner...
🔄 Scanning for sector sympathy...

╔══ MORNING ARBITRAGE SCAN ══╗             ← ei_main.py opening box
║ [1/3] Checking earnings... ║
╚════════════════════════════╝
... strategy progress output ...
╔══ SCAN COMPLETE ══╗                      ← ei_main.py closing box
║ Results: 0 found  ║
╚═══════════════════╝

✅ 07:13:28 - ✅ ARBITRAGE SCANNER COMPLETED    ← doubled emoji
╔══ ARBITRAGE SCANNER COMPLETE ══╗         ← main_runners.py closing box
║ Opportunities found: 0        ║
╚════════════════════════════════╝
```

**AFTER (proposed):**
```
════════════════════════════════════════════
 PHASE 1: PRE-MARKET OPERATIONS            ← phase header (once)
════════════════════════════════════════════

╔══ Step 1.2: Earnings Arbitrage Scanner ══╗  ← orchestrator opens
║ Scan for sector sympathy opportunities   ║
╚══════════════════════════════════════════╝

[1/3] Checking today's earnings calendar...    ← strategy progress
[2/3] Analyzing peer IV levels...
[3/3] Scoring arbitrage opportunities...
No earnings reporting today — scan complete.

╔══ Step 1.2 Complete ═════════════════════╗  ← orchestrator closes
║ Opportunities: 0 | High-quality: 0      ║  ← from return value
║ Status: No earnings today               ║
╚══════════════════════════════════════════╝
```

---

## 7. Technical Considerations

### Files to Modify

| File | Changes |
|------|---------|
| `tools/log_utils.py` | **NEW** — shared beautiful_log, create_status_box, phase_header |
| `main_ui.py` | Delegate to log_utils, rewrite print_banner for dynamic content, simplify coffee_break |
| `main_runners.py` | Remove redundant mission/completion box content, use strategy return values for stats |
| `main.py` | Add phase headers, add results tracking dict, rewrite day-end summary, remove cycle counter |
| `main_calendar.py` | Simplify countdown timer (if countdown logic lives here) |
| `strategies/option_pipeline/op_main.py` | Remove internal boxes/banners, rename OID→OP, fix phase numbering, return structured results |
| `strategies/flow_monitor/fm_main.py` | Remove own beautiful_log copy, remove redundant boxes, import from log_utils, fix cycle duplication |
| `strategies/earnings_intel/ei_main.py` | Remove redundant boxes when called from orchestrator |
| `strategies/flow_monitor/fm_evaluator.py` (or similar) | Move individual alert logging to file-only, keep batch progress on console |
| `strategies/flow_monitor/fm_post_market.py` (or similar) | Market regime 1-line narrative |

### Dependencies and Ordering

1. `tools/log_utils.py` must be created first — everything else depends on it
2. Strategy box removal and orchestrator box updates can happen in parallel per strategy
3. Welcome banner rework is independent of box changes
4. Day-end summary depends on results tracking being added to the day loop

### Standalone Strategy Runs

Strategies can be run independently (e.g., `python fm_main.py --pre-market`), but this is rare — nearly all runs go through main.py. When run standalone, there's no orchestrator framing layer, so you only get the strategy's progress lines without pretty boxes. This is acceptable for ad-hoc runs. No orchestrator-mode detection mechanism is needed — just remove strategy boxes unconditionally.

---

## 8. Success Metrics

- **Zero duplicate announcements**: No step has more than 1 opening and 1 closing box
- **Complete log files**: `.log` file contains orchestrator-level output (beautiful_log lines) — can verify by grepping for phase headers
- **Accurate day-end summary**: Day-end box shows actual pass/fail per step, actual failure counts, no hardcoded status
- **Dynamic banner**: Welcome banner includes all steps with correct numbers and conditional Friday items
- **Reduced console lines**: Measurable reduction in total output lines per day (target: ~40% fewer lines from eliminated duplication and countdown noise)
- **Single import path**: All logging goes through `tools/log_utils.py` or Python's `logging` module — no more bare `sys.stdout.write()` bypasses

---

## 9. Open Questions

1. **`failure_morgue` table warning**: The audit flagged `[WARNING] failure_morgue table missing` appearing every run during daily evaluation. Is this a real missing table or a deprecated reference? Needs investigation before deciding whether to fix or remove.
2. **Watchlist cleanup formalization**: Post-market has a hidden "watchlist cleanup" step not numbered or documented. Should it become Step 2.8, or remain a quiet sub-task of evaluation?
3. **FM cycle logging depth**: The audit notes per-expiration logging in FM cycles generates thousands of lines. Ben likes the scrolling heartbeat but says per-expiration detail has never been useful for debugging. Should we reduce to per-symbol only? (This is borderline in-scope since it's FM-internal.)

---

## 10. Implementation Phases

### Phase A: Foundation (tools/log_utils.py)
- Create shared logging utility
- Wire main_ui.py to delegate to it
- Replace fm_main.py's copy
- Fix ✅✅ stutter

### Phase B: Orchestrator Framing
- Add phase transition headers
- Add results tracking dict to day loop
- Rewrite day-end summary from tracked results
- Dynamic welcome banner

### Phase C: Strategy Deduplication
- Remove boxes from op_main.py (+ OID→OP rename + phase numbering fix)
- Remove boxes from fm_main.py post-market
- Remove boxes from ei_main.py

### Phase D: Noise Reduction
- Simplify coffee_break to 2 lines
- Remove DEBUG lines from production
- Remove time estimates from mission boxes
- Evaluator: individual alerts to log-file-only
- FM cycles: deduplicate performance summaries
- Remove dead feature references or fix them
- Full health report paths
- Market regime 1-line narrative
