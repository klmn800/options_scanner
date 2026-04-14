# Coding Agent Prompt — Package 7: Utility Runner Polish

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 7 — minor cleanup of utility runner methods in main_runners.py. This is the final polish package.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 7 (3 steps)
2. `main_runners.py` — the only file you modify

## What You're Doing

3 steps:

### Step 1: Normalize subprocess completion boxes

For subprocess runners that can't return metrics, simplify completion boxes to show only what's honestly known:

```
Success/Fail status
Duration
```

No "Database secured", no "Performance optimized", no approximate counts like "~750 symbols".

Search for and remove these filler phrases from `main_runners.py`:
- `"Database secured"`
- `"Performance optimized"`
- `"Ready for safe operations"`
- `"Ready for analysis"`
- `"Ready for.*operations"`
- `"~750 symbols"` or `"~750"`
- `"4 SQL views"`

### Step 2: Airline play method

`run_airline_play_phase()` is nearly compliant — already reads from component dicts. Find and remove the 4 `beautiful_log` calls (search for `"Running airline tracking"`, `"Phase 1/2"`, `"Phase 2/2"`, `"Airline tracking phase completed"`). Ensure the completion box uses dict values (it likely already does).

### Step 3: Batch mode review

`run_batch_mode_review()` — the intermediate "ERROR QUEUE" box is acceptable (shows what's about to be processed). Remove any duplicate announcements if present.

## Rules

- ONLY modify `main_runners.py`
- Do NOT touch strategy files or subprocess scripts
- Do NOT change business logic
- Keep completion boxes — just clean their content

## Verification

1. `grep -rn "Database secured\|Performance optimized\|Ready for.*operations\|~750\|4 SQL views" main_runners.py` — zero matches

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 7 status to `complete`, fill in Coding Notes.
