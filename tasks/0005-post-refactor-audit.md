# Post-Refactor Audit — Orchestrator Console Overhaul
**Date:** 2026-02-12 (first production run after refactor)
**PRD:** `tasks/0005-prd-orchestrator-console-overhaul.md`
**Version:** v4.0

---

## Issues Found in Production

### 1. Overnight Wait Countdown — Excessive (93 lines)

**File:** `main_calendar.py:267-296` (`wait_until_next_trading_day()`)

**Observed behavior:**
- 11:36 PM → 5:36 AM: Every 30 min (13 lines) — **fine**
- 5:36 AM → 6:30 AM: Every 1 minute (55 lines) — **excessive**
- 6:30 AM → 6:35 AM: Every 10 seconds (25 lines) — **extremely excessive**
- Total: ~93 lines of countdown for a 7-hour wait

**Root cause:** Three-tier countdown logic:
```python
if wait_seconds > 3600:    chunk_size = 1800   # 30 min — OK
elif wait_seconds > 300:   chunk_size = 60     # 1 min — too chatty
else:                      chunk_size = 10     # 10 sec — way too chatty
```

**Fix applied:** Two-tier approach:
- \>1 hour: every 30 min (same)
- ≤1 hour: every 15 min (4-5 lines instead of 80)
- 10-second and 1-minute tiers removed entirely
- ~93 lines → ~17 lines for a 7-hour overnight wait

**Status:** Fixed

### 2. Option Pipeline Init Noise — DEBUG lines and redundant init messages

**Files:** `op_config.py`, `op_storage.py`, `op_collector.py`, `fm_config.py`

**Observed:** 6 lines of init noise before any real work started:
```
2026-02-12 06:35:02 - INFO - OID Configuration loaded from: E:\options_scanner\config.json
DEBUG: OID - Added core directory: E:\options_scanner\core
DEBUG: OID - Added tools directory: E:\options_scanner\tools
2026-02-12 06:35:03 - INFO - OID Tradier API client initialized successfully
2026-02-12 06:35:03 - INFO - OIDStorage initialized with database: E:\options_scanner\data\datalake.db
🔧 OID Collector 3.0 initialized - Universe: klmn_800 (~759 symbols)
```
Plus a second copy when OIDCollector re-initializes config/storage internally.

**Fix applied:**
- DEBUG print() lines removed from `op_config.py` and `fm_config.py`
- Config loaded, API init, Storage init messages demoted to `logging.debug`
- Collector init message demoted to `logging.debug`
- Bulk insert completion messages demoted to `logging.debug`
- All "OID" prefixes in log messages replaced with "OP:" across op_config, op_storage, op_collector

**Status:** Fixed

### 3. Mission Box Text — Needed updating

**File:** `main_runners.py`

**Before:** "Objective: Collect fresh Open Interest data for all symbols"
**After:** "Objective: Refresh Option Contract tables with OI data"

Also updated: "Strategy" → "Steps" (includes Report step), "Full Production" → "KLMN 800"

**Status:** Fixed (morning + evening boxes both updated)

---

## Confirmed Working

- Welcome banner: v4.0, "Refresh" labels, correct FM time range (9:15 AM - 5:00 PM), Friday-aware
- Phase headers: All 5 phases get ═══ banners
- Overnight wait box: Clean, informative, correct next-day detection
- Log rotation: "Daily log rotation complete" — no more doubled lines
- Phase 1 starts on time at 06:35:02
- Phase 1 mission box: Clean, correct text

---

## Pending Observations

*(Add notes here as the day progresses)*

- [ ] Phase 1 (Pre-Market) step completion boxes
- [ ] Phase 2 (Flow Monitor) cycle output — dedup verified?
- [ ] Phase 2 market regime narrative line
- [ ] Phase 3 (Post-Market) evening pipeline boxes
- [ ] Day-end summary box — honest pass/fail
- [ ] Evaluator verbosity — alert lines gone from console?
- [ ] Health report path — full relative path shown?
