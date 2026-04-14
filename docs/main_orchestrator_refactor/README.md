# Console Output Overhaul

We are working on a multi-package refactor of the options scanner's console output system. The goal: strategies return structured data and stay silent, the orchestrator owns all visual output (boxes, banners, phase headers, coffee breaks). Today, every strategy has its own beautification layer, announces its own completion, and some return `bool` instead of dicts — forcing the orchestrator to query the database for completion box data.

Your job is to execute one piece of this refactor cleanly, without breaking anything else. 

As you work, be mindful that user Ben likes most of how the current logging is displayed - you must always pause to verify with him what the intended console logging output should look like post-refactor, comparing with the current state, and seeking feedback and approval before making changes.

---

## Documentation — Read Order

Read these before starting work. They're all in this directory (`docs/main_orchestrator_refactor/`).

| Order | File | What it tells you |
|:---:|------|-------------------|
| 1 | `CONSOLE_OUTPUT_STANDARD.md` | The target architecture — roles, output patterns, what each layer produces and returns |
| 2 | `CONSOLE_OUTPUT_AUDIT.md` | Current violations — what's broken, per-file breakdowns, compliance percentages |
| 3 | `RETURN_DICT_CONTRACTS.md` | Interface specs — current vs proposed return dicts at every boundary |
| 4 | `LOG_UTILS_API.md` | Public API for `tools/log_utils.py` — function signatures and examples |
| 5 | `WORK_PACKAGES.md` | Your assignment — scoped packages with step-by-step instructions and verification checks |
| 6 | `PROGRESS_TRACKER.md` | Project status — check prerequisites, update when you finish |

---

## Workflow

Work follows a **code → review → verify** cycle for each package.

**If you are a coding agent:**
1. Check `PROGRESS_TRACKER.md` — confirm any prerequisites for your package are `verified`
2. Read your package in `WORK_PACKAGES.md` — understand scope, files, steps
3. Read the actual source code before making any changes (the docs describe patterns, not exact line numbers)
4. Execute the steps in your package
5. Run the verification checks listed in your package
6. Update `PROGRESS_TRACKER.md`: set status to `complete`, fill in Coding Notes

**If you are a review agent:**
1. Read the package that was just completed in `WORK_PACKAGES.md`
2. Run every verification check listed in the package's Verification section
3. Spot-check the actual code changes — do they match the intent?
4. Update `PROGRESS_TRACKER.md`: set status to `verified` (all checks pass) or `failed` (with notes)

Dependent packages (2 depends on 1; 6 depends on 4 and 5) must not start until their prerequisites are `verified`.

---

## Execution Order

There are 8 packages (0-7) organized into three batches by dependency:

```
Batch A (parallel, no dependencies):
  Package 0: Orchestrator Standalone Cleanup
  Package 1: EI Dict Returns
  Package 3: OP Visual Cleanup
  Package 4: FM Pre-Market Dict Return
  Package 5: FM Post-Market Research + Dict

Batch B (parallel, after dependencies verified):
  Package 2: EI Visual Cleanup        ← requires Package 1 verified
  Package 6: FM Visual Cleanup        ← requires Packages 0, 4, AND 5 verified

Batch C (final):
  Package 7: Utility Runner Polish
```

**For each package:** spawn a coding agent → review its work with a review agent → mark verified in `PROGRESS_TRACKER.md` → then (and only then) spawn dependent packages.

Batch A packages can all be spawned simultaneously. Batch B packages can run in parallel with each other once their respective dependencies are verified — Package 2 doesn't need to wait for Packages 4/5, and Package 6 doesn't need to wait for Package 1 (but does need Package 0 for daily state persistence in `fm_session_stats.py`). Package 7 has no hard dependencies but is lowest priority and benefits from all other work being done first.

---

## Rules

These apply to every package. Violating them creates regressions.

1. **Preserve error-path logging.** Lines in `except` blocks that log exceptions stay (convert to `logging.error()` if needed).

2. **Test imports after deleting functions.** Run `python -c "import module.name"` to confirm nothing breaks.

3. **Don't refactor business logic.** Change what functions return and what they print. Don't change what they do.

4. **Always read the actual code first.** The docs describe what to look for by function name and content pattern. Verify before changing.

5. **Stay in scope.** Only modify files listed in your package. If you find issues outside your scope, note them and move on.
