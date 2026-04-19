# PRD 0014: Roll Detection in Flow Alerts

**Date:** 2026-04-18
**Status:** Draft
**Author:** Claude (from Strategic Advisor Proposal 007)
**Evidence:** `strategic_advisor/reviews/007_roll_detection.md`

---

## 1. Introduction / Overview

When an institutional trader "rolls" a position — closing one strike and opening another — both legs appear in the same Flow Monitor scan. The alert system fires on the opening leg (high volume = high significance score), but without context, it looks like a new directional bet. In reality, it's a position adjustment that carries a fundamentally different thesis.

Ben's two worst trades (VST -20%, CTRA held too long) were both roll patterns. This feature detects roll signatures at alert time and tags them in console output and database records, giving Ben the context to interpret multi-strike activity correctly.

Rolls represent ~15-20% of same-symbol multi-strike alerts. They are detectable at alert time using volume matching and V/OI divergence against data already loaded during the scan cycle.

---

## 2. Goals

1. **Detect roll patterns at alert time** by scanning the current cycle's data for matching counterpart legs.
2. **Tag alerts with roll context** in console output so Ben can immediately see when an alert is part of a position adjustment rather than a new directional bet.
3. **Store roll detection results** in the alert record for later analysis and measurement.
4. **Achieve zero false positives** at launch using the conservative combined heuristic (volume match >= 0.85 AND at least one leg V/OI < 1.5).
5. **Never suppress alerts** — rolls still represent real institutional activity; the tag adds context, not a filter.

---

## 3. User Stories

1. **As Ben**, when I see a high-score alert for VST $175 calls, I want to know if there's matching volume at the $170 strike with low V/OI, so I can recognize it as a roll rather than a new directional bet.

2. **As Ben**, when two alerts fire for the same symbol at different strikes, I want both to indicate they're part of the same roll, so I can evaluate them as a single position adjustment.

3. **As Ben**, when reviewing historical alerts, I want to query which alerts were detected as rolls, so I can measure whether roll-tagged alerts perform differently from non-roll alerts.

4. **As an analyst**, I want roll detection data stored in the database, so I can run the 2-week measurement plan (precision and recall against OI resolution) to validate and tune the algorithm.

---

## 4. Functional Requirements

### 4.1 Detection Algorithm

1. **Trigger:** When an alert fires for contract (symbol S, option_type T, expiration E, strike K, volume V), run roll detection before the alert is saved.

2. **Search Space:** Query the current scan cycle's data for contracts matching:
   - Same symbol S
   - Same option_type T (both calls or both puts)
   - Same OR adjacent expiration: counterpart expiration E' within ±30 calendar days of E
   - Different strike: K' ≠ K
   - Volume V' within 50-200% of V (pre-filter to narrow candidates before ratio check)

3. **Scoring:** For each candidate counterpart, compute:
   - `vol_match_ratio = min(V, V') / max(V, V')` — how closely volumes match
   - `voi_alert = V / max(OI, 1)` — V/OI of the alerting contract
   - `voi_counterpart = V' / max(OI', 1)` — V/OI of the counterpart

4. **Classification:** Flag as POSSIBLE ROLL if ALL of:
   - `vol_match_ratio >= roll_detection.vol_match_threshold` (default 0.85, configurable in `fm_config.py`)
   - At least one leg has V/OI < `roll_detection.voi_closing_threshold` (default 1.5, configurable in `fm_config.py`)

5. **Multiple Matches:** If multiple counterparts qualify, select the one with the highest `vol_match_ratio`. If tied, select the one with the lowest V/OI (strongest closing signal).

6. **Pairwise Detection:** Multi-leg rolls (3+ strikes) are detected pairwise. Each qualifying pair is flagged independently.

### 4.2 Alert Tagging — Console Output

7. **Opening Leg Tag:** When a roll is detected, append `[ROLL? from $K']` to the alert's console output line. If the counterpart has a different expiration, include it: `[ROLL? from $K' MM/DD]`.

8. **Closing Leg Tag:** If the counterpart (closing leg) ALSO triggered an alert (scored >= 3.5), tag that alert with `[ROLL? closing -> $K]`. If the closing leg alert has already been displayed, it won't retroactively update — the tag applies to whichever alert processes second.

9. **Tag Position:** The roll tag appears after existing tags (alert level, intent tags if present) and before the contract details. Example:
   ```
   VST [HIGH] [ROLL? from $170] $175 CALL 05/16 | Vol: 2,450 (8.1x) | ...
   VST [MED]  [ROLL? closing -> $175] $170 CALL 05/16 | Vol: 2,500 (1.2x) | ...
   ```

### 4.3 Data Storage

10. **New columns on `flow_alerts` table** (via ALTER TABLE, auto-migration):
    - `roll_detected` — BOOLEAN (0/1). 1 if this alert was flagged as part of a roll.
    - `roll_counterpart_details` — TEXT. JSON string with counterpart info:
      ```json
      {
        "counterpart_strike": 170.0,
        "counterpart_expiration": "2026-05-16",
        "vol_match_ratio": 0.98,
        "alert_voi": 4.46,
        "counterpart_voi": 0.49,
        "role": "opening"
      }
      ```
      `role` is `"opening"` (new position leg) or `"closing"` (existing position leg). The leg with higher V/OI is "opening"; the leg with lower V/OI is "closing". If both V/OI are < 1.5 or both are >= 1.5, the leg with higher V/OI is still "opening".

11. **Alert reason extension:** Append roll info to the existing `alert_reason` string: `v2|ROLL?$170|score: 5.3 (prem=...)`

12. **In-memory alert dict:** Add `roll_detected` (bool), `roll_counterpart_strike` (float), `roll_counterpart_expiration` (str), `roll_match_ratio` (float), `roll_role` (str) fields to the alert record dict before save.

### 4.4 Scan Data Access

13. **Data Source:** Use the current scan cycle's dataframe, passed in-memory from `fm_analyzer.py`. The analyzer already loads this data during `_get_contracts_with_baselines()`. The roll detection function needs access to the full set of contracts for the symbol being alerted — not just alert candidates (the closing leg often scores below 3.5). **Critical: Do NOT query `flow_options_scans` table for roll detection** — the table is 23M+ rows with a known missing-index performance issue.

14. **Scan Window:** Same scan timestamp only. No cross-scan lookback for v1. Rolls execute atomically (both legs in the same order), so they appear in the same scan cycle.

15. **No Additional API Calls:** Roll detection uses only data already collected during the scan. Zero additional Tradier API calls.

### 4.5 Constraints

16. **Strike Range Limitation:** Only contracts within the ±20% FM scan range are available. Rolls to far OTM/ITM strikes outside this range cannot be detected. This is a structural limitation, not a bug.

17. **No Alert Suppression:** Roll-tagged alerts are displayed and stored identically to non-roll alerts. The tag is additive context only.

18. **Volume Floor:** Both legs must have volume > 0 (implicit — contracts with zero volume aren't in the scan data with meaningful scores).

---

## 5. Non-Goals (Out of Scope)

- **Alert suppression or score modification** based on roll detection. Rolls are tagged, not filtered.
- **Cross-scan lookback** (checking previous FM cycle). Deferred to v2 if measurement shows missed rolls.
- **Multi-leg complex rolls** (e.g., 3-way strike ladders, calendar/diagonal spreads involving 3+ contracts). Pairwise detection is sufficient for v1.
- **Roll confidence scoring** (e.g., high/medium/low roll probability). Binary detection is sufficient for v1.
- **Performance.db tracking** — query `flow_alerts WHERE roll_detected = 1` for analysis instead.
- **Retroactive roll detection** on historical alerts. This is a going-forward feature.
- **Intent tag integration** (Proposal 005 from strategic advisor). Can be layered on later if intent tags ship.

---

## 6. Design Considerations

### Console Output Format

The roll tag follows existing tag patterns (e.g., `[HIGH]`, `[MED]`) using brackets. The `?` suffix communicates that this is a probabilistic detection, not a certainty.

**Same-expiration roll:**
```
VST [HIGH] [ROLL? from $170] $175 CALL 05/16 | Vol: 2,450 (8.1x) | Prem: $612K | Score: 7.2
```

**Cross-expiration roll:**
```
XYZ [MED] [ROLL? from $60 04/17] $62.5 CALL 05/15 | Vol: 1,200 (4.5x) | Prem: $180K | Score: 5.1
```

**Closing leg (also alerted):**
```
VST [MED] [ROLL? closing -> $175] $170 CALL 05/16 | Vol: 2,500 (1.2x) | Prem: $425K | Score: 3.8
```

### Integration Point

Roll detection runs in `fm_alerts.py` during alert processing, after alert candidates are identified but before alerts are saved. The function queries the current scan's data for the alerted symbol to find counterpart contracts.

---

## 7. Technical Considerations

### Data Access Pattern

The closing leg of a roll often does NOT trigger an alert (it scores below 3.5 because volume against a large existing OI yields a low volume surprise). Therefore, roll detection must search the full scan data for the symbol, not just alert candidates.

Two approaches to access the scan data:
- **Option A:** Query `flow_options_scans WHERE scan_timestamp = ? AND symbol = ?` from the database. Simple, one query per alerted symbol.
- **Option B:** Pass the scan dataframe from `fm_analyzer.py` through to `fm_alerts.py`. Avoids the DB round-trip but requires threading data through the pipeline.

**Recommendation: Option B (pass the dataframe).** The `flow_options_scans` table is 23M+ rows and has a known performance issue — the intraday earnings signal tracker query takes ~5 min on this table, likely due to a missing index on `scan_timestamp`. Roll detection runs on every alert (~15-20 alerts/cycle, ~16-18 cycles/day), so a slow query here would be a blocker. Passing the scan dataframe in-memory avoids this entirely.

**Implementation note:** `fm_analyzer.py` already loads the full scan data via `_get_contracts_with_baselines()`. The dataframe (or a reference to it) should be made available to the roll detection function in `fm_alerts.py`. The exact threading mechanism (return value, class attribute, parameter) is an implementation detail — but the key constraint is: **no queries against `flow_options_scans` for roll detection.**

### Schema Migration

```sql
ALTER TABLE flow_alerts ADD COLUMN roll_detected BOOLEAN DEFAULT 0;
ALTER TABLE flow_alerts ADD COLUMN roll_counterpart_details TEXT;
```

Auto-migration via the existing pattern (try ALTER, catch "duplicate column" error).

### Performance Impact

- ~5-30 alerted symbols per scan cycle
- Scan dataframe passed in-memory — zero additional DB queries
- In-memory loop over ~100-400 contracts per symbol for volume matching
- Total added time per cycle: < 1 second

### Dependencies

- `fm_analyzer.py` must have already written scan results to `flow_options_scans` before `fm_alerts.py` runs roll detection. This is already the case in the current pipeline order.
- `fm_storage.py` INSERT must include the two new columns.

---

## 8. Success Metrics

Measured after 2 weeks of production data (~32-36 trading cycles × 15-20 alerts/cycle = ~500-700 alerts):

1. **Precision > 80%:** Of alerts tagged `[ROLL?]`, at least 80% show one leg CLOSING and one BUILDING when checked against next-day OI resolution (via `fm_evaluator.py`).

2. **Recall > 50%:** Of all same-symbol pairs where one alert resolved CLOSING and another BUILDING on the same day, at least 50% were tagged `[ROLL?]`.

3. **Zero false positive rate on non-roll pairs:** No pairs where both legs resolved as BUILDING should be tagged `[ROLL?]` (this is the strict constraint; V/OI < 1.5 requirement protects against this).

4. **Qualitative:** Ben reports that the tag changes how he evaluates multi-strike alerts (reduces impulse to act on the opening leg as if it's a fresh directional bet).

---

## 9. Resolved Questions

**Alert processing order (was Q2):** Per-alert processing, not batching. Each alert independently searches the scan data for counterparts. If both legs fire alerts, both will independently find each other and both get tagged correctly. Batching adds complexity for no gain.

**Volume match ratio tuning (was Q4):** Make the threshold configurable in `fm_config.py`. Default 0.85, tunable during the 2-week measurement window.

## 10. Open Questions

1. **V/OI calculation edge case:** When OI = 0 for the counterpart (brand new strike), V/OI = V/1 = V, which is always >> 1.5. This means two new-position legs (both V/OI > 1.5) won't be flagged as a roll. Is this correct behavior? (Probably yes — if both legs are new positions, it's a spread, not a roll.)

2. **Measurement automation:** The 2-week measurement plan requires comparing roll tags against OI resolution. Should this be a manual SQL query, or should we build a small measurement script? (Recommend manual query for v1 — a few SQL commands suffice.)
