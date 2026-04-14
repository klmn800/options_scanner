# Coding Agent Prompt — Package 6C: FM Market Hours Triage

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 6C — triaging the 24 `beautiful_log()` calls in `run_market_hours()`, the most critical section of FM. This function runs for 6+ hours as a delegated orchestrator and SHOULD produce per-cycle operational output, but the current output uses non-standard formatting functions.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — delegated orchestrator rules (FM market hours section)
2. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — Section 2 (FM violation inventory)
3. `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` — Section 10 (approved target output with line-by-line keep/cut), Section 17 (per-call cross-check table)
4. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 6C (Step 7)

Then read the actual source file:
- `strategies/flow_monitor/fm_main.py` — find `run_market_hours()` function (this is the ONLY function you modify)

## What You're Doing

1 step (Step 7 per WORK_PACKAGES.md):

### Step 7: `run_market_hours()` — 24 beautiful_log calls — MOST CRITICAL

The performance breakdown is useful and stays:
```
✅ Cycle 15 complete - Performance Breakdown:
   📊 Collection: 1222.9s
   🔍 Analysis: 22.4s
   🚨 Alerts: 1.8s
   🎯 Watchlist: 6.4s
   🔄 DB Sync: 99.6s (104,416 rows)
   ⏱️ Total: 1353.0s
```

Keep this multi-line breakdown. Convert from `beautiful_log()`/`print()` to `logging.info()`. Do NOT condense to a single line.

**Full triage table:**

| Category | Action |
|----------|--------|
| Startup banner / `"MARKET HOURS BEGINNING"` + `"Real-time monitoring"` | **DELETE** |
| `create_phase_header("MARKET HOURS MONITORING")` | **DELETE** — redundant with orchestrator mission box |
| Per-cycle multi-line performance breakdown (`"✅ Cycle N complete"` + 6 metric lines) | **KEEP** — convert to `logging.info()` |
| Every-10-cycle performance summary (`"📈 PERFORMANCE SUMMARY"` + 6 stat lines) | **KEEP** — convert to `logging.info()` |
| `"🔍 Collection complete: {ts} ({time}s)"` | **KEEP as `logging.info()`** |
| Cycle header `"=== Cycle N \| time \| symbols ==="` | **ASK BEN** — recommend KEEP as visual separator but strip `===` decoration. Convert to plain `logging.info("Cycle N \| time \| symbols")` for now. Flag in Review Notes for Ben's decision. |
| `"🔔 Market closed."` | **KEEP as `logging.info()`** |
| `coffee_break()` calls between cycles | **KEEP** — they work via rewritten function |
| API budget warnings (`"Low API budget"`) | **KEEP as `logging.warning()`** |
| Failure cluster warnings | **KEEP as `logging.warning()`** |
| `handle_error()` calls (4 total: 3 CRITICAL + 1 WARNING) | **KEEP** — FM is a long-lived process, these ARE the error routing |
| End-of-day summary (`stats.format_end_of_day_lines()` loop) | **KEEP as `logging.info()`** |
| Symbol gaps file saved (`"Saved to {filename}"`) | **KEEP as `logging.info()`** |
| `"🏁 MARKET HOURS PIPELINE COMPLETE"` | **DELETE** — orchestrator handles completion |
| Error-path logging (`"Collection failed"`, `"Market cycle error"`) | **KEEP as `logging.error()` / `logging.warning()`** |

**IMPORTANT on `handle_error()` in market hours:** There are 4 calls — 3 with `severity='CRITICAL'` (zero alerts stored, collection failed, unexpected error) and 1 with `severity='WARNING'` (news enrichment failure). Market hours can't route errors through a return value during execution, so these calls are correct and MUST stay.

## Rules

- ONLY modify `run_market_hours()` — do NOT touch any other function
- Do NOT touch FM component files (that's Package 6D)
- Do NOT touch `fm_session_stats.py`, `main_runners.py`
- Do NOT change return values or business logic
- Do NOT remove `handle_error()` calls — all 4 must stay
- Preserve error-path logging in except blocks

## Verification

1. `grep -rn "beautiful_log" strategies/flow_monitor/fm_main.py` — zero matches in the entire file (6B handled non-market-hours, 6C handles market hours)
2. `grep -rn "handle_error" strategies/flow_monitor/fm_main.py` — EXACTLY 4 matches, all in `run_market_hours()` — 3 with `severity='CRITICAL'` and 1 with `severity='WARNING'` (news enrichment)
3. Market hours output: verify the multi-line performance breakdown is preserved (not condensed) and redundant lines are removed
4. **Flag in Review Notes:** The "Ask Ben" item about cycle header format (`=== Cycle N | time | symbols ===`) — document what you chose and why

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 6C status to `complete`, fill in Coding Notes. Flag the cycle header decision in Review Notes.
