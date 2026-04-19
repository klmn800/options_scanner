# Feedback on Proposal 007: Roll Detection

**Date:** 2026-04-18
**From:** Ben (via Claude Code session)
**Status:** Approved — entering PRD pipeline

---

## Decision

This is exactly what I asked for. The spec is detailed enough to kick off a PRD process. Running it through `@ai-dev-tasks/create-prd.md` as a test of the proposal → PRD pipeline.

The analysis is thorough — confirmed examples, non-roll controls, design decisions pre-answered, performance implications addressed, honest about limitations (60% sensitivity, ±20% strike range). This is the kind of proposal that makes the handoff to a developer session smooth.

No changes needed to the spec. The PRD process will handle the remaining design details (clarifying questions, edge cases, implementation plan).

---

## Implementation Debrief (2026-04-19)

**Status:** PRD 0014 fully implemented and validated. Awaiting first live trading day (Monday) for production smoke test.

### What was built

Six files modified. The core `_detect_roll()` method lives in `fm_alerts.py` (~90 lines). Scan data is threaded from `fm_analyzer.py` through to `fm_alerts.py` via a class attribute + parameter — no DB queries against `flow_options_scans`, exactly as spec'd. Two new columns on `flow_alerts` (`roll_detected`, `roll_counterpart_details` JSON). Console output inserts `[ROLL? from $K']` or `[ROLL? closing -> $K']` tags after the market cap tag. All four config knobs are in `fm_config.py` and overridable via `config.json`.

### Validation results

- **VST roll** (vol_match=0.98, V/OI 4.46 vs 0.49): Correctly detected, role=opening, counterpart=$170.
- **XYZ cross-exp roll** (vol_match=1.00, different expirations): Correctly detected with `04/17` date suffix in tag.
- **COIN** (vol_match=0.79): Correctly rejected — below 0.85 threshold.
- **Both-high-V/OI synthetic** (V/OI 10 and 24): Correctly rejected — min(V/OI) >> 1.5.

### Known borderline

**MSTR** (vol_match=0.87, counterpart V/OI=1.43) gets flagged at the 0.85 threshold. The evidence doc predicted this — V/OI of 1.43 is just barely below the 1.5 cutoff. Both legs resolved BUILDING, so this is technically a false positive at 0.85. At 0.90 threshold it would not fire. The `?` suffix in `[ROLL?]` communicates uncertainty. If precision drops below target after the 2-week measurement window, raising `vol_match_threshold` to 0.90 is the first lever.

### For your measurement plan

After 2 weeks of production data, query:
```sql
-- All roll-tagged alerts
SELECT trade_date, symbol, strike, option_type, roll_counterpart_details
FROM flow_alerts WHERE roll_detected = 1 ORDER BY trade_date DESC;

-- Precision check: compare roll tags against evaluation_status (BUILDING/CLOSING)
-- Requires fm_evaluator to have run on these alerts
```

### Files changed

`fm_config.py`, `fm_storage.py`, `fm_analyzer.py`, `fm_alerts.py`, `fm_main.py`, `tools/decimal_formatter.py`. Task list: `tasks/tasks-0014-prd-roll-detection.md`. PRD: `tasks/0014-prd-roll-detection.md`.
