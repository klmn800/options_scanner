# Console Output Refactor — PM State

**Last updated:** 2026-02-18
**PM Role:** Claude Code session acts as project manager, writes prompts, reviews work, tracks progress.

---

## Current Status

| Package | Status | Notes |
|---------|--------|-------|
| 0 - Orchestrator Standalone Cleanup | `verified` | PM verified 2026-02-18 |
| 1 - EI Dict Returns | `verified` | PM verified 2026-02-18 |
| 2 - EI Visual Cleanup | `verified` | PM verified 2026-02-18 |
| 3 - OP Visual Cleanup | `verified` | PM verified 2026-02-18 |
| 4 - FM Pre-Market Dict Return | `verified` | PM verified 2026-02-18 |
| 5 - FM Post-Market Research + Dict | `verified` | PM verified 2026-02-18 |
| 6A - FM Formatting Functions + Coffee | `verified` | PM verified 2026-02-18 |
| 6B - FM Function-Level Triage | `verified` | PM verified 2026-02-18 |
| 6C - FM Market Hours Triage | `verified` | PM verified 2026-02-18 |
| 6D - FM Component Files Cleanup | `verified` | PM verified 2026-02-18 |
| 7 - Utility Runner Polish | `verified` | PM verified 2026-02-18 |

## Baseline Backup

23 files saved to `backups/refactor_baseline/` before any changes.

## Git Status

Git init failed (large repo, permission issues). Using file backups instead. Can retry git later with proper .gitignore (already created at project root).

## Decisions Pending (Ask Ben)

1. **FM cycle header format** — keep `=== Cycle N ===` decorators or strip to plain? (Package 6C)
2. **FM alert display borders** — remove `"="*80` or keep for visual prominence? (Package 6D)
3. **Post-market per-task confirmations** — keep `"✅ [task] complete"` lines or delete? (Package 6B)

Ben said: "prepared to address them in situ" — will decide when he sees the proposals.

## Package 6 Split

**DONE** (2026-02-18). WORK_PACKAGES.md and PROGRESS_TRACKER.md updated with 6A/6B/6C/6D. Verified by PM.

## Agent Prompt Files

All coding agent prompts saved to `docs/main_orchestrator_refactor/agent_prompts/`:
- `PROMPT_split_package6.md` — Split Package 6 into sub-packages (do first) — **WRITTEN**
- `PROMPT_package0.md` — Orchestrator Standalone Cleanup — **WRITTEN**
- `PROMPT_package1.md` — EI Dict Returns — **WRITTEN**
- `PROMPT_package3.md` — OP Visual Cleanup — **WRITTEN**
- `PROMPT_package4.md` — FM Pre-Market Dict Return — **WRITTEN**
- `PROMPT_package5.md` — FM Post-Market Research + Dict — **WRITTEN**
- `PROMPT_package2.md` — EI Visual Cleanup — **WRITTEN**
- `PROMPT_package6A.md` — FM Formatting Functions + Coffee Break — **WRITTEN**
- `PROMPT_package6B.md` — FM Function-Level Triage — **WRITTEN**
- `PROMPT_package6C.md` — FM Market Hours Triage — **WRITTEN**
- `PROMPT_package6D.md` — FM Component Files Cleanup — **WRITTEN**
- `PROMPT_package7.md` — Utility Runner Polish — **WRITTEN**

## Workflow Per Package

1. Ben gives agent the prompt file
2. Agent does the work, reports back
3. Ben relays results to PM session (or new PM session that reads PM_STATE.md)
4. PM reviews against WORK_PACKAGES.md specs
5. PM writes review prompt → Ben gives to review agent
6. Review agent runs verification checks from PROGRESS_TRACKER.md
7. PM updates PM_STATE.md and PROGRESS_TRACKER.md

## Key Architecture Decisions (from docs)

- **Orchestrator** (main_runners.py) owns ALL visual structure (boxes, banners, phase headers, coffee breaks)
- **Strategies** own ONLY progress lines (no boxes, banners, celebrations)
- **Coordinators** (op_main.py, ei_main.py, fm pre/post) produce sub-phase headers via `logging.info()` only
- **Delegated orchestrator** (FM market hours) keeps per-cycle output but via `logging.info()`, not `beautiful_log()`
- All completion boxes built from return dicts, NEVER from DB queries
- `fm_session_stats.py` is the model file — compute, aggregate, return, never print
- Coffee breaks use `create_status_box()` with dynamic "Up Next" from STEP_SEQUENCE
- Daily state persisted to `logs/daily_state.json` for restart resilience

## Files Modified Per Package

| Package | Files |
|---------|-------|
| 0 | main_runners.py, main_ui.py, main.py, fm_session_stats.py |
| 1 | ei_main.py, ei_moves_upcoming.py, main_runners.py |
| 2 | ei_main.py, ei_arbitrage_scanner.py, ei_fetch_upcoming.py, ei_snapshot_collector.py, ei_post_earnings_calc.py, ei_moves_upcoming.py |
| 3 | op_main.py, op_collector.py, op_symbol_rollup.py, op_timing_calculator.py |
| 4 | fm_main.py (run_pre_market only), main_runners.py |
| 5 | fm_main.py (run_post_market + inner wrappers) |
| 6 | fm_main.py, fm_alerts.py, fm_analyzer.py, fm_social_notifier.py, fm_collector.py, fm_alert_resolver.py, fm_symbol_rollup.py, fm_evaluator.py, fm_agent.py |
| 7 | main_runners.py |
