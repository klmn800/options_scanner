# Bug Tracker

Small bugs and issues I notice during analysis. Batched into proposals or flagged for quick fixes.
Each entry includes a ready-to-run Claude command when the fix is straightforward.

---

## Open

### BUG-002 (2026-04-18) -- Offboarded symbol data may not archive properly
**Severity:** Low (data accumulation, not functional)
**Root cause:** If offboarding removes a symbol from `symbol_metadata`, and the sector archive process uses `symbol_metadata.archive_db` for routing, then data for offboarded symbols in production tables (option_contracts, flow_options_scans, etc.) may never get archived -- just silently accumulates.
**Impact:** Ghost data growing in production database. Not urgent but worth understanding.
**Status:** Needs investigation -- check offboarding flow + archive routing interaction.

```
claude -p "Investigate: when a symbol is offboarded via tools/symbol_lifecycle.py, does it get removed from symbol_metadata? If so, does the sector archive process (data/health/db_archive_sector.py) skip symbols not in symbol_metadata? This could leave orphaned data that never gets archived. Check the code paths and report findings."
```

### BUG-003 (2026-04-18) -- Query DB sync didn't capture Friday collector output
**Severity:** Low (stale query DB, analysis-only impact)
**Observation:** Production DB has 44 April earnings_events (through 4/17) but query DB only has 5 (through 4/8). The Friday `ei_collector` populated the production DB but the sync hasn't propagated to query DB yet. Historical prices ARE current (4/17) in both DBs.
**Likely cause:** Sync ran before the collector, or sync hasn't run since collector completed.
**Impact:** Analysis sessions need to use `--db data/datalake.db` for earnings data until next sync.
**Status:** Monitor -- likely self-resolves on next trading day's sync.

### BUG-004 (2026-04-18) -- CTRA multi-strike roll: $36 strike didn't fire an alert
**Severity:** Info (design limitation, not bug per se)
**Observation:** On 4/14, CTRA had 15,000 contracts at both $34 (V/OI 517) and $36 (V/OI 0.99). Only $34 fired an alert because $36's volume didn't produce a volume_surprise_factor high enough (V/OI near 1 = low surprise). But the $36 position was the CLOSING leg of a roll -- critical context for understanding $34.
**Impact:** Ben bought $34 thinking it was directional conviction, but it was a roll from $36 to $34. The system could have detected this by checking adjacent strikes in the same scan.
**Status:** Addressed in Proposal 003 (Tier 2: Roll Detection).

### BUG-005 (2026-04-18) -- Dead code cleanup: unused deduplication method + config
**Severity:** Low (dead code, not a bug)
**What:** `fm_analyzer.py:1014` defines `_check_alert_deduplication()` that is never called. Config key `alert_deduplication_hours: 4` is also unused. These are leftovers from a deliberate design decision — repeated surges on the same contract ARE informative (volume acceleration signal), so dedup was intentionally disabled. The method and config key should be deleted as cleanup.
**Ben's input:** "That second alert is informative — I want to know when a contract gets another big injection of volume." Confirmed dedup-off was the right call.

```
cd /d E:\options_scanner
claude -p "Dead code cleanup in fm_analyzer.py: delete the _check_alert_deduplication() method (around line 1014) and the 'NOTE TO REVIEWER' comment above it. It's intentionally unused — repeated surges on the same contract are valuable signal. Also remove the unused config key alert_deduplication_hours from config.json (under flow_monitor). Update the debug log at fm_alerts.py line 76 to remove 'no deduplication window' since that's no longer a notable design choice."
```

---

## Resolved

### BUG-001 (2026-04-18, FIXED 2026-04-18) -- Orphaned earnings_upcoming entries for offboarded symbols
**Root cause:** Symbols offboarded before PRD 0013 (EXAS, AL, SEE, HOLX, ABEV) had orphaned `earnings_upcoming` entries producing false STRONG BUY signals.
**Fix:** Ben deleted the 5 orphaned entries from production DB. Lifecycle tool (`--offboard`) already handles this going forward.
