# Coding Agent Prompt — Package 6D: FM Component Files Cleanup

You are a coding agent working on a console output refactor for the options scanner system. Your job is to execute Package 6D — removing `"=" * N` separator lines, converting `print()` to `logging.info()`, and cleaning up decorative banners from all FM component files. Also verify `safe_log()` is fully removed across the FM directory and clean up dead imports from `fm_main.py`.

## Before You Start

Read these files:
1. `docs/main_orchestrator_refactor/CONSOLE_OUTPUT_AUDIT.md` — Section 2 (FM violation inventory)
2. `docs/main_orchestrator_refactor/VISUAL_DESIGN_REFERENCE.md` — Section 16 (alert display target mockup)
3. `docs/main_orchestrator_refactor/WORK_PACKAGES.md` — find Package 6D (Steps 9-11)

Then read the actual source files:
- `strategies/flow_monitor/fm_alerts.py` — alert display borders
- `strategies/flow_monitor/fm_analyzer.py` — analysis summary borders
- `strategies/flow_monitor/fm_social_notifier.py` — queue alert box
- `strategies/flow_monitor/fm_collector.py` — print → logging conversion
- `strategies/flow_monitor/fm_alert_resolver.py` — diagnostic separators
- `strategies/flow_monitor/fm_symbol_rollup.py` — separator + announcement
- `strategies/flow_monitor/evaluation/fm_evaluator.py` — separator
- `strategies/flow_monitor/fm_agent.py` — separators
- `strategies/flow_monitor/fm_main.py` — dead import cleanup only (Step 11)

## What You're Doing

3 steps:

### Step 9: Clean up FM component files

| File | What to remove |
|------|---------------|
| `fm_alerts.py` | `_display_alerts_to_console()`: Remove `"="*80` border lines and `"-"*N` category separators. Convert all `print()` to `logging.info()`. KEEP emoji category headers (`🔴 HIGH CONVICTION`, `🟡 MEDIUM`, `⚪ LOW`), per-alert detail lines, and summary line. Use blank lines to separate categories. `_log_alert_summary()`: Remove `"="*50` borders. Keep stat lines as `logging.info()`. See VISUAL_DESIGN_REFERENCE.md Section 16 for the full target mockup. **ASK BEN** if he prefers to keep the alert display borders — flag in Review Notes. |
| `fm_analyzer.py` | `_log_analysis_summary()`: Remove `"="*60` border lines around `UNIFIED ALGORITHM ANALYSIS SUMMARY`. Keep all stat lines as `logging.info()`. Content stays — only decorative borders removed. |
| `fm_social_notifier.py` | `queue_alert_for_posting()` box (`═` box with `print()`). Keep CLI `print()` statements (acceptable for standalone use). |
| `fm_collector.py` | Convert ~10 `print()` startup/status messages to `logging.info()`. |
| `fm_symbol_rollup.py` | `"=" * 60` separator and `"OP ROLLUP COMPLETE"` announcement. |
| `fm_alert_resolver.py` | Diagnostic separators (`"="*60`). |
| `evaluation/fm_evaluator.py` | `"=" * 50` separator. |
| `fm_agent.py` | `"=" * 70` separators. |

### Step 10: Verify `safe_log()` is fully removed

Search the entire `strategies/flow_monitor/` directory for `safe_log` references. If any FM component files import or call `safe_log` from `fm_main`, update those imports and calls too.

### Step 11: Remove dead imports from fm_main.py

After deleting formatting functions and `safe_log()` (in earlier packages), check the import section at the top of `fm_main.py` for now-unused imports. The file currently does NOT import `colorama` or `shutil` — it uses raw ANSI codes in `colorize()`. Once `colorize()` is deleted (6A), verify no other code depends on ANSI sequences.

**Note on `handle_error` import:** `fm_main.py` uses lazy imports (`from tools.autofix import handle_error` inside each function body), NOT a top-level import. Since market hours KEEPS 4 `handle_error()` calls, those inline imports stay. No top-level import cleanup needed for autofix.

## Rules

- Do NOT touch `fm_session_stats.py`
- Do NOT touch `fm_watchlist.py` — its `"=" * 70` patterns are email body formatting, not console output
- Do NOT touch `fm_baseline_generator.py` — no violations (verified clean)
- Do NOT touch `main_runners.py`
- Do NOT change return values or business logic
- Keep all actual progress lines and metric content — only remove decorative borders/separators

## Verification

1. `grep -rn "safe_log" strategies/flow_monitor/` — zero matches (including component files)
2. `grep -rn '"="\s*\*\s*[0-9]\|"=" \* [0-9]\|"="\*[0-9]' strategies/flow_monitor/` — zero matches in non-Deprecated files. Note: `fm_alerts.py` uses `"="*50` (no spaces), so check both patterns. `fm_watchlist.py` `"=" * 70` patterns are email body content and should remain.
3. `python -c "from strategies.flow_monitor.fm_main import run_pre_market, run_market_hours, run_post_market; print('OK')"` — succeeds
4. **Flag in Review Notes:** The "Ask Ben" item about alert display borders in fm_alerts.py — document what you chose and why

## When Done

Update `docs/main_orchestrator_refactor/PROGRESS_TRACKER.md`: set Package 6D status to `complete`, fill in Coding Notes. Flag the alert borders decision in Review Notes.
