# Bug Tracker

Small bugs and issues I notice during analysis. Batched into proposals or flagged for quick fixes.
Each entry includes a ready-to-run Claude command when the fix is straightforward.

---

## Open

### BUG-001 (2026-04-18) — Orphaned earnings_upcoming entries for offboarded symbols
**Severity:** Medium (causes false STRONG BUY signals)
**Root cause:** Symbols offboarded from the scanner (EXAS, AL, SEE, HOLX, possibly others) still have active entries in `earnings_upcoming`. The lifecycle offboarding tool (PRD 0013) wasn't retroactively applied to these symbols, and their stale option data produces garbage straddle calculations.
**Impact:** 4 of 15 current BUY/STRONG BUY signals are false positives.
**Fix options:**
1. Run lifecycle offboard for each symbol (proper cleanup)
2. Quick: DELETE from earnings_upcoming WHERE symbol IN (list of offboarded symbols)
3. Verify the offboarding tool clears earnings_upcoming as part of its flow

**To investigate:** Does `symbol_lifecycle.py --offboard` clean `earnings_upcoming`? Check the offboarding code.

```
claude -p "Check if tools/symbol_lifecycle.py --offboard cleans up earnings_upcoming entries for the offboarded symbol. If not, add that step. Also identify all symbols currently in earnings_upcoming that are NOT in symbol_metadata (orphaned entries) and remove them."
```

### BUG-002 (2026-04-18) — Offboarded symbol data may not archive properly
**Severity:** Low (data accumulation, not functional)
**Root cause:** If offboarding removes a symbol from `symbol_metadata`, and the sector archive process uses `symbol_metadata.archive_db` for routing, then data for offboarded symbols in production tables (option_contracts, flow_options_scans, etc.) may never get archived — just silently accumulates.
**Impact:** Ghost data growing in production database. Not urgent but worth understanding.
**Status:** Needs investigation — check offboarding flow + archive routing interaction.

```
claude -p "Investigate: when a symbol is offboarded via tools/symbol_lifecycle.py, does it get removed from symbol_metadata? If so, does the sector archive process (data/health/db_archive_sector.py) skip symbols not in symbol_metadata? This could leave orphaned data that never gets archived. Check the code paths and report findings."
```

---

## Resolved

*(none yet)*
