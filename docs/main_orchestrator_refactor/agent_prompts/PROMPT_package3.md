# Coding Agent Prompt — Package 3: OP Visual Cleanup

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 3 — removing beautification functions and completion banners from the Option Pipeline. Data flow is already correct (OP returns comprehensive dicts) — this is visual-only cleanup.

## Before You Start

Read these files in this order:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — target architecture (especially Coordinators section)
2. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — Section 3 (OP violation inventory)
3. `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` — Section 15 (Sub-Phase Structure) for what to keep
4. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 3 (3 steps)

Then read the actual source files:
- `strategies/option_pipeline/op_main.py` — main target
- `strategies/option_pipeline/op_collector.py` — completion banner removal
- `strategies/option_pipeline/op_symbol_rollup.py` — completion banner removal
- `strategies/option_pipeline/op_timing_calculator.py` — completion marker removal

## What You're Doing

3 steps:

1. **Delete formatting functions from op_main.py** — Delete these 6 functions: `safe_log()`, `create_phase_header()`, `create_progress_box()`, `create_success_celebration()`, `create_error_box()`, `log_pipeline_start()`

2. **Replace all calls in op_main.py** — For each call to a deleted function:
   - **KEEP (convert to `logging.info()`):** Sub-phase headers (`create_phase_header("📊 PHASE 1: DATA COLLECTION", ...)` → inline as `logging.info("── 📊 DATA COLLECTION (1/4) ──...")`). Tree diagram intros (`create_progress_box()` calls with `├─` / `└─`). Inline completion summaries (Pattern A trees). Per-item progress lines.
   - **DELETE:** `create_success_celebration("OPTION PIPELINE", accomplishments)`. `log_pipeline_start()` call. Startup banner (`"=" * 70` block in `main()`). Final success/failure print statements in `main()`. `_log_pipeline_summary()` method.

3. **Remove `═══` borders from component completion summaries, KEEP metric content:**
   - `op_collector.py`: Remove `"=" * 70` border lines (2 lines) and `"🎉 COLLECTION COMPLETE"` banner title. KEEP the 6 metric lines as plain `logging.info()`.
   - `op_symbol_rollup.py`: Remove `"=" * 60` separator lines (3 lines) and `"OP ROLLUP COMPLETE: ..."` title line. KEEP stats lines.
   - `op_timing_calculator.py`: Remove `[OK]` completion marker. If `BACKFILL COMPLETE` banner exists, delete the banner line only.

## Rules

- Do NOT touch return values (already correct)
- Do NOT touch main_runners.py (already reads from dicts)
- Do NOT change business logic
- Keep progress logging lines (progress counters showing N/M symbols)
- All kept output should go through `logging.info()`, not `print()` or `safe_log()`

## Verification

1. `grep -rn "safe_log\|create_phase_header\|create_success_celebration\|create_error_box\|create_progress_box\|log_pipeline_start" strategies/option_pipeline/` — zero matches
2. `grep -rn '"=" \* [0-9]\|COLLECTION COMPLETE\|ROLLUP COMPLETE' strategies/option_pipeline/` — zero matches
3. `python -c "from strategies.option_pipeline.op_main import OPOrchestrator; print('OK')"` — succeeds
4. Sub-phase headers (`── 📊 DATA COLLECTION`) exist as `logging.info()` calls
5. Tree diagram content (`├─`) exists as `logging.info()` calls

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 3 status to `complete`, fill in Coding Notes.
