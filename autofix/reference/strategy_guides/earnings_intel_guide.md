# Earnings Intelligence Strategy Guide

**Purpose:** Auto-fix reference for Earnings Intelligence errors
**Updated:** October 14, 2026

---

## Read this first

The canonical technical reference is **`docs/earnings_strategy_refactor/EARNINGS_INTELLIGENCE_TECHNICAL_GUIDE.md`**. Read the section that matches the failing step before changing anything:

| Failing step / error source | Guide section |
|---|---|
| `ei_main.run_daily_pipeline` sub-steps 1–8, return dict | §3 Pipeline Architecture |
| `ei_lite_refresh.py`, `earnings_date_disputes`, Earnings Researcher spawn | §4 Earnings Date Confirmation |
| `ei_moves_upcoming.py` (signals, straddle, alert flag) | §5 Signal Classification |
| `ei_watchlist.py` (`watchlist_population_failure`) | §6 The Earnings Watchlist |
| `ei_snapshot_collector.py`, `earnings_snapshots` | §8 Tables (snapshot join-key policy) |
| `ei_post_earnings_calc.py`, `earnings_moves`, outcome columns | §9 Post-Earnings Analysis |
| `ei_collector.py` (`earnings_collector_*` errors, Friday Step 5.3) | §3 Weekly Refresh |
| Symptoms (UNKNOWN signals, NULL IV, missing moves, wrong dates) | §13 Troubleshooting table |

Known non-errors (don't "fix" these): the arbitrage scan (sub-step 8) is intentionally disabled; Alpha Vantage budget exhaustion is not a failure; zero post-earnings events on a given day is normal; most peer-symbol snapshot rows have a NULL `event_id` (§12).

## Autofix guardrails specific to EI

**Safe to fix (with the usual verification):**
- Exception handling, logging, and console output in any `ei_*.py`
- Query bugs that don't change what a column means
- Timeout/retry behavior around yfinance and Finnhub calls

**Investigate and escalate instead of fixing:**
- Signal math or thresholds (`relative_underpricing_pct`, the 0.85 straddle multiplier, `earnings_play.*` in `config.json`). These are uncalibrated by design and changes alter every downstream outcome label.
- Outcome classifiers (`compute_straddle_outcome`, `compute_move_vs_historical`). They are shared with backfill tools.
- Date-selection rules in `ei_collector.py` / `ei_lite_refresh.py` (yfinance-wins, confirmed-row skip).
- Anything that would require a schema change. Schema changes go through the existing idempotent migration helpers, not ad-hoc `ALTER TABLE`.

**Never:**
- Write `date_confirmed` / `date_confirmed_by` directly. Only `tools/earnings_confirm.py` may, and only with `--by agent` from an automated session.
- Run `python data/health/db_backup.py --sync` (see project `CLAUDE.md`).
- Delete or rewrite `earnings_events` / `earnings_moves` history to make an error go away.
