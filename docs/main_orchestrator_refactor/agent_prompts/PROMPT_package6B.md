# Coding Agent Prompt — Package 6B: FM Function-Level Triage (Pre/Post-Market + Utilities)

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 6B — triaging all `beautiful_log()` and `safe_log()` calls in fm_main.py's non-market-hours functions, deleting the `safe_log()` definition, and removing `handle_error()` from post-market.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_STANDARD.md` — target architecture
2. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — Section 2 (FM violation inventory)
3. `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` — Section 15 (sub-phase elements)
4. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 6B (Steps 3-6 + Step 8)

Then read the actual source file:
- `strategies/flow_monitor/fm_main.py` — the only file you modify

## What You're Doing

5 steps (numbered 3-6, 8 per WORK_PACKAGES.md):

### Step 3: `run_historical_backfill()` — 9 beautiful_log calls

Triage each `beautiful_log()` call:

| Content pattern | Action |
|----------------|--------|
| `"Starting historical backfill..."` | **DELETE** — redundant with caller context |
| `"Checking for symbols needing backfill..."` | **DELETE** — operational noise |
| `"Found N symbols needing backfill"` | **KEEP as `logging.info()`** |
| `"Processing batch N/M..."` | **KEEP as `logging.info()`** — progress |
| `"Backfill complete for SYMBOL"` | **DELETE** — per-symbol noise |
| `"Coffee break between batches..."` | **DELETE** — the `coffee_break()` call provides the visual |
| `"Historical backfill complete"` | **DELETE** — completion announced by caller |
| Error-path logging | **KEEP as `logging.error()`** |

### Step 4: `run_quick_sync()` — 14 beautiful_log calls

| Content pattern | Action |
|----------------|--------|
| `"Starting quick sync..."` / `"Quick sync complete"` | **DELETE** |
| `"Fetching N symbols..."`, `"API budget: N calls remaining"` | **KEEP as `logging.info()`** |
| Per-symbol progress lines | **KEEP as `logging.info()`** |
| Coffee break announcements | **DELETE** — the `coffee_break()` call provides the visual |
| Error-path logging | **KEEP as `logging.error()`** |

### Step 5: Delete `safe_log()` definition and convert all 46 calls

`safe_log()` is an enhanced print with UTF-8 fallback. Convert all calls:

| Current | Replacement |
|---------|------------|
| `safe_log("message")` | `logging.info("message")` |
| `safe_log("WARNING: ...", level='warning')` | `logging.warning("...")` |
| `safe_log("ERROR: ...", level='error')` | `logging.error("...")` |

Note: `safe_log()` in fm_main.py does NOT take a `level` parameter — it always prints. So all calls convert to `logging.info()` unless the message text clearly indicates a warning or error.

Delete the `safe_log()` function definition after all calls are converted. If it's imported by other FM files, check those files too — but it's likely only used within `fm_main.py`.

### Step 6: `run_pre_market()` — 13 beautiful_log calls

After Package 4, this function returns a dict. Most visual output becomes redundant with the orchestrator completion box.

| Content pattern | Action |
|----------------|--------|
| `create_phase_header("PRE-MARKET PREPARATION", now)` | **DELETE** |
| `"🌅 PRE-MARKET PREPARATION - Flow Monitor system ready"` | **DELETE** |
| `"⚡ Market hours monitoring will begin at 9:30 AM"` | **DELETE** |
| `"🔍 TASK 0: Resolving Yesterday's Flow Alerts"` | **KEEP as `logging.info()`** — sub-phase progress |
| `"Using fresh OI data from morning Option Pipeline"` | **KEEP as `logging.info()`** — context |
| `"✅ Resolved N alerts (N BUILDING, N CLOSING, N NEUTRAL)"` | **KEEP as `logging.info()`** |
| `"⚠️ N contracts not found in today's OI data"` | **KEEP as `logging.warning()`** |
| `"✅ Resolution data synced to query database"` | **KEEP as `logging.info()`** |
| `"✅ Updated sentiment for N watchlist symbols"` | **KEEP as `logging.info()`** |
| `create_success_celebration("PRE-MARKET SETUP COMPLETE", ...)` | **DELETE** |
| `create_error_box("PRE-MARKET SETUP FAILED")` | **DELETE** |
| Error-path logging | **KEEP as `logging.error()`** |

### Step 8: `run_post_market()` — 22 beautiful_log calls, 5 handle_error calls

| Category | Action |
|----------|--------|
| `create_phase_header("POST-MARKET ANALYSIS", now)` | **DELETE** |
| `"🌆 INITIATING POST-MARKET ANALYSIS PIPELINE"` | **DELETE** |
| Per-task `"💾 Running historical data backfill first..."` etc. | **KEEP as `logging.info()`** — sub-phase progress |
| Per-task `"✅ [task] complete"` confirmations | **KEEP as `logging.info()`** — compact confirmation |
| Per-task metric displays | **KEEP as `logging.info()`** — information-dense |
| `coffee_break()` calls between tasks | **KEEP** — they work via rewritten function |
| `create_success_celebration("POST-MARKET PIPELINE", ...)` | **DELETE** |
| `create_error_box("POST-MARKET PIPELINE HAD FAILURES...")` | **DELETE** |
| `handle_error()` calls (1 CRITICAL + 3 ERROR + 1 WARNING) | **DELETE** — orchestrator routes via return dict |
| Error-path logging in except blocks | **KEEP as `logging.error()`** |

**Note on handle_error in post-market vs market hours:** Post-market's 5 `handle_error()` calls should be REMOVED because post-market returns a dict (Package 5) and the orchestrator does the error routing. Market hours' 4 `handle_error()` calls should be KEPT because market hours runs as a long-lived process where errors must be handled immediately.

## Rules

- Do NOT touch `run_market_hours()` (that's Package 6C)
- Do NOT touch FM component files (that's Package 6D)
- Do NOT touch `fm_session_stats.py`, `main_runners.py`
- Do NOT change return values or business logic
- Preserve error-path logging in except blocks

## Verification

1. `grep -rn "safe_log" strategies/flow_monitor/fm_main.py` — zero matches (definition deleted + all calls converted)
2. `grep -rn "beautiful_log" strategies/flow_monitor/fm_main.py` — matches should ONLY be in `run_market_hours()` (those are 6C's scope). Zero matches in any other function.
3. `grep -rn "handle_error" strategies/flow_monitor/fm_main.py` — EXACTLY 4 matches, all in `run_market_hours()` (post-market's 5 calls removed, market hours' 4 kept)
4. `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_post_market; print('OK')"` — succeeds

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 6B status to `complete`, fill in Coding Notes.
