# PRD 0006 Deferred Items

**Date:** 2026-02-13
**Source:** PRD 0006 implementation session + follow-up discussion
**Status:** Pending future pass

---

## Deferred Fixes (low risk, just not prioritized)

**Item 15: Timestamp format standardization** — **IMPLEMENTED (2026-02-13)**
- Console output now standardized on `HH:MM:SS` (no milliseconds) across all modules, matching `beautiful_log()`.
- File/log output retains milliseconds for debugging.
- Fix: `console_formatter.default_msec_format = None` on console handlers in `main.py`, `fm_main.py`, `op_main.py`, `ei_main.py`.
- Compact format (`20260213_152954`) unchanged — used for filenames/session IDs only.

---

## Investigation Items (need research before implementing)

**B. Watchlist cleanup formalization** — **IMPLEMENTED (2026-02-13)**
- Post-market banner now lists all 5 tasks in a two-column layout instead of the vague "Historical backfill and evaluation".

**C. FM cycle per-expiration logging** — **RESOLVED (2026-02-13)**
- All per-expiration logging (chain fetch + contract storage detail) demoted to `logging.debug()`.
- At normal INFO level, these lines are fully suppressed. Only visible with `--debug` flag.
- No further refactoring needed.

**D. Consistently failing symbols** — **RESOLVED (2026-02-13)**
- `FMSessionStats` tracks `errors_by_symbol` with per-cycle error type and identifies "always failing" symbols in end-of-day summary + orchestrator box. `fm_collector.py` captures structured error details (`last_error_details`). Greeks null bug fix (2026-02-13) resolved the root cause for ~28 permanently-failing symbols (HON, CVX, WOLF, BDX, etc.).

**E. Arbitrage opportunities display** — **IMPLEMENTED (2026-02-13)**
- **Root cause:** Scanner found opportunities but never wrote to `earnings_sector_effects` (literal TODO in code). Orchestrator queried empty table, always showed "Opportunities found: 0".
- **Fix:** Added `_persist_opportunities()` method to `ei_arbitrage_scanner.py`. Writes ranked opportunities to `earnings_sector_effects` with proper decimal formatting. Idempotent (re-runs clear pre-earnings rows). Orchestrator's existing queries now receive actual data.
- Also added `_get_symbol_industry()` helper and `industry` field to opportunity records.

**G. Error/warning aggregation** — **IMPLEMENTED (2026-02-13)**
- See "Already Addressed" section below.

**H. Earnings alert content visibility** — **IMPLEMENTED (2026-02-13)**
- **Fix:** `run_earnings_pipeline()` completion box now shows signal breakdown + top symbols instead of bare count.
- Format: `"Earnings alerts: 123 (83 STRONG BUY, 22 BUY, 18 WATCH)"` with second line `"  Top: DAY (0d, 1090%), CFLT (0d, 962%), ..."`.
- Shows up to 5 top symbols by relative underpricing, with `"...+N more"` for >8 alerts. Falls back to count-only if detail query fails.

---

## New Item (from 2026-02-13 session)

**I. Autofix integration for FM collector per-symbol errors** — **RESOLVED (2026-02-13)**
- Per-symbol errors captured via `fm_collector.py` structured error details (`last_error_details`). `FMSessionStats` aggregates into `errors_by_type` and `errors_by_symbol`. Data surfaced in end-of-day summary and orchestrator box. Greeks null bug fix (2026-02-13) eliminated the root cause of most persistent failures (~430 errors/day).

---

## Already Addressed (for reference)

These were in the original deferred list but got partially or fully resolved during the 2026-02-13 session:

- **Item 11** (Version/PID/Memory banner) — already removed from active code
- **Item 16** (Banner "4 operations" vs "Task 1/3") — numbering already consistent
- **Item 17** (Earnings alert lines) — intentionally kept, T+3 move results are low volume and useful
- **Item A** (`failure_morgue` warning) — Dead code removed from `fm_evaluator.py` (2026-02-13). Table never existed in production. Removed ~840 lines: table checks, save/read methods, failure pattern detection, failure report generation, and config loader. README updated.
- **Item F** (News sentiment visibility) — Implemented (2026-02-13). `run_market_hours()` now returns dict with accumulated `news_enrichment` stats across all cycles. Orchestrator surfaces summary line: "News sentiment: N symbols enriched across M cycles". Per-cycle `logging.info()` line preserved for scroll visibility.
- **Item G** (Error/warning aggregation) — Implemented (2026-02-13). New `FMSessionStats` class (`strategies/flow_monitor/fm_session_stats.py`) accumulates all operational stats across FM market hours cycles: cycle counts, timing (avg/min/max), errors by type (timeout/rate_limit/connection/other), errors by symbol, missing quotes, failed options, news enrichment. `fm_collector.py` now captures structured error details per cycle (`last_error_details`). End-of-day summary in `fm_main.py` driven by `stats.format_end_of_day_lines()`. Orchestrator (`main_runners.py`) displays "MARKET HOURS SESSION SUMMARY" box from `session_stats` dict. Symbol gaps JSON still persisted to `logs/symbol_gaps_*.json`. Note: stats are in-memory only — a mid-day restart resets counters (same as before).
