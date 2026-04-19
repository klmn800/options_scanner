# Observation: Architecture Notes (Session 005)

**Date:** 2026-04-18
**Status:** Initial observations, will deepen in future sessions

## FM Alert Pipeline Architecture

**Entry point:** `fm_analyzer.py:_calculate_unified_score()` → `fm_alerts.py:process_alerts()` → console + DB

**Scoring formula (v2):**
- Component 1: Premium score (0-6 pts) — log-scale, market-cap-adjusted thresholds
- Component 2: Volume surprise (0-4 pts) — vs daily running total or baseline estimate
- Total: 0-10, bounded. Threshold 3.5 (alert), 5.0 (HIGH).

**Filters applied BEFORE alerting:**
- ETF: rejected (is_etf = 1)
- Delta: 0.25 ≤ |delta| ≤ 0.75 (rejects deep OTM/ITM)
- DTE: ≥ 7 (config: `min_dte: 7`)
- Top 100 candidates per scan (ORDER BY score DESC)

**Deduplication — intentionally disabled (dead code cleanup):**
- `_check_alert_deduplication()` exists in fm_analyzer.py but is never called — intentionally
- Config key `alert_deduplication_hours: 4` also unused
- Ben confirmed: repeated surges on the same contract ARE signal (volume acceleration). Dedup was correctly disabled.
- Action: delete the dead method and unused config key as cleanup

## v3 Integration Path

**Clean insertion points in `_calculate_unified_score()`:**
1. After `base_score = self._calculate_flow_score(...)` — add flow concentration multiplier
2. After `unified_score = min(10.0, max(0.0, base_score))` — add actionability bonuses
3. Return tuple position 1 (`0.0`) is a placeholder (formerly smart_money) — can hold bonus

**Data availability at scoring time:**
- `flow_percentage` — YES (from flow_options_scans via query)
- `volume / open_interest` (V/OI) — YES (both fields in contract dict)
- `dte` — YES
- `last_price` — YES
- `moneyness` — YES
- `iv_percentile_30d` — YES (joined from option_symbol_summary in alert candidate query)
- Multi-leg detection — REQUIRES cross-alert logic (check other alerts in same cycle)

**No schema changes needed for v3.** All data is already available. Implementation is purely logic changes in `_calculate_unified_score()` plus alert_reason formatting.

## OP Pipeline Observations

- Collects ~117K contracts/day across 816-819 symbols
- Feeds `option_symbol_summary` (93 columns, ~820 rows/day)
- 62% of contracts have OI < 100 (low liquidity), but contribute to IV averaging and max pain
- Production DB retains ~30-45 days; older data archived to sector archives
- Well-utilized: earnings intel, FM resolution, and snapshot collector all depend on option_symbol_summary

## Config Structure

All FM config in `config.json` under `flow_monitor`:
- `min_significance_score: 3.5` — alert threshold
- `min_dte: 7, max_dte: 75` — DTE window
- `alert_deduplication_hours: 4` — UNUSED (BUG-005)
- `scan_interval_minutes: 12` — target cycle time
- `evaluation` — tracking and quality score weights
- `dip_detection` — z-score system for dip alerts
- `earnings_signal_tracking` — intraday signal recomputation
