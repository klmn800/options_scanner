# Text Log Audit Punchlist — March 12, 2026

**Audit scope:** `orchestrator_2026-03-11.log` (15,167 lines, full trading day)
**Standard source:** `KICKOFF.md`, `AUDIT_REPORT.md` from `docs/orchestrator_text_log_refactor/`
**Purpose:** Compare production text logs against the forensic-first design standard

---

## Design Standard Recap

The orchestrator text log is the **forensic record of the trading day**. Its audience is developers and AI agents (Autofix) diagnosing problems after the fact.

**Principles:**
- **Forensic-first**: Answer "what happened, how long, what went wrong?"
- **Clean and greppable**: Plain text, no decorative console art, no emojis
- **Data-driven**: Built from actual measured values
- **Comprehensive**: Fill subprocess gaps so all operations are logged

---

## What's Working Well

Before the problems — credit where due:

1. **Phase headers** are correctly routed: `--- [PHASE 1] PRE-MARKET OPERATIONS ---` (compact marker, not full ═══ banner). This was a Phase 3 routing fix and it works.
2. **Status box content** is correctly flattened: titles + indented lines, no Unicode borders. The OP completion box, FM completion box, etc. all render as plain text.
3. **Cycle performance breakdowns** are excellent forensic data — collection time, API time, DB write time, analysis breakdown, sync time. Every cycle has a complete timing profile.
4. **Alert resolution detail display** (new 3/11 feature) is high-value forensic data in the log — shows yesterday's alert, today's OI delta, resolution classification.
5. **End-of-day report** is clean and information-dense — market summary, flow activity, earnings outlook, system performance metrics, all in greppable format.
6. **Progress markers** are present at key intervals (100/416, 200/416 etc.) for OP collection and FM historical backfill.

---

## Problems Found

### P1: Emojis in Log File (364 instances on 3/11)

**Standard says:** Log file gets "clean message only" — emojis are console decoration only.
**Actual:** 364 emoji instances throughout the day's log.

**Root cause:** `beautiful_log()` at `log_utils.py:187` writes the raw `message` parameter to the file handler. The function correctly *avoids adding* a level emoji (✅/❌/etc.) if the message already starts with one. But it doesn't *strip* emojis that callers embed in the message string itself. So when `main_runners.py` calls `beautiful_log("🎯 MORNING OPTION PIPELINE COMPLETE")`, the 🎯 goes straight to the log file.

**Affected patterns (all from caller-embedded emojis):**
- `☕ Coffee Break` — 36 instances
- `💤 Waiting N hours...` — 8 instances
- `🌅 MORNING OPTION PIPELINE REFRESH`
- `🎯 MORNING OPTION PIPELINE COMPLETE` / `EVENING OPTION PIPELINE COMPLETE`
- `📈 EARNINGS INTELLIGENCE` / `FLOW MONITOR PIPELINE`
- `🔍 PRE-MARKET PREPARATION` / `FLOW MONITOR — MARKET HOURS ENGINE`
- `🌆 POST-MARKET ANALYSIS`
- `💾 DATABASE BACKUP OPERATION`
- `🏢 SYMBOL METADATA COLLECTION`
- `📊 PERFORMANCE DATA COLLECTION` / Progress lines
- `📈 PERFORMANCE SUMMARY (Last N cycles)`
- `📊 TODAY'S FLOW ACTIVITY`
- `🛫 AIRLINE PLAY TRACKING PHASE` / `AIRLINE TRACKING: ...`
- `✈️ AIRLINE OPTIONS: ...`
- `🌙 WAITING FOR NEXT TRADING DAY`
- `✅` on completion lines, sync lines, backup lines
- `🔴` on STRONG BUY earnings alerts
- `🚨 FLOW MONITOR ALERTS`
- `📅 EARNINGS OUTLOOK`
- `⚙️ SYSTEM PERFORMANCE`
- `⏰ WAITING FOR TRADING DAY START`
- `🛑 Press Ctrl+C...`

**Fix:** Add an emoji-stripping function in `log_utils.py` that removes Unicode emoji characters before writing to the file handler. Apply in `_write_to_file_handler()` or at the `beautiful_log()` call site (line 187).

---

### P2: Duplicate Log Lines (2 confirmed cases)

**Standard says:** Each fact should appear once in the log.
**Actual:** Some events are logged twice — once via `beautiful_log()` (which writes to file handler) and again via `logging.info()` in the same code path.

**Evidence:**
```
Line 1276: Alert resolution complete: 21 resolved (13 BUILDING, 5 CLOSING, 3 NEUTRAL)
Line 1277: Alert resolution complete: 21 resolved (13 BUILDING, 5 CLOSING, 3 NEUTRAL)

Line 1361: Watchlist sentiment updated: 73 symbols (42 BUILDING, 21 CLOSING, 10 NEUTRAL)
Line 1362: Watchlist sentiment updated: 73 symbols (42 BUILDING, 21 CLOSING, 10 NEUTRAL)
```

**Root cause:** `fm_main.py` calls both `beautiful_log(msg)` AND `logging.info(msg)` for the same event. Since `beautiful_log` already writes to the file handler, the `logging.info()` call creates a second line.

**Fix:** In `fm_main.py`, remove the `logging.info()` call where `beautiful_log()` already covers the same message. Audit other files for the same pattern.

---

### P3: Double Timestamps from Subprocess Output (57 lines)

**Standard says:** Log format is `YYYY-MM-DD HH:MM:SS - LEVEL - message`. One timestamp per line.
**Actual:** Metadata collection subprocess output has doubled timestamps:
```
2026-03-11 07:01:22 - INFO - 07:01:22 - Configuration loaded
2026-03-11 07:02:29 - INFO - 07:02:29 - Database writes: 416 successful, 0 failed
```

The outer `YYYY-MM-DD HH:MM:SS - INFO -` comes from the logging formatter. The inner `HH:MM:SS -` comes from the subprocess's own output format. 57 such lines on 3/11.

**Root cause:** `main_runners.py` captures subprocess stdout and forwards each line via `logging.info(line)`. The subprocess already formats its output with `HH:MM:SS -` prefixes. No timestamp stripping occurs.

**Fix:** In `_run_streaming_subprocess()` or `run_metadata_collection()`, strip `HH:MM:SS - ` prefixes from subprocess output before passing to `logging.info()`. Regex: `r'^\d{2}:\d{2}:\d{2} - '`

---

### P4: Decorative Banners from Subprocesses (13 lines)

**Standard says:** No decorative console art in log file.
**Actual:** `==` separator lines leak from two subprocess sources:

**Metadata collector** (3 lines):
```
2026-03-11 07:01:22 - INFO - ==================================================
2026-03-11 07:02:29 - INFO - ==================================================
2026-03-11 07:02:29 - INFO - ==================================================
```

**Morning views** (10 lines):
```
2026-03-11 07:14:16 - INFO - ========================================================================================================================
```
(One per symbol, 10 symbols = 10 banner lines, plus `---` separator lines)

**Root cause:** These subprocesses write decorative output to stdout. When `main_runners.py` captures and forwards this output, the banners come along.

**Fix:** In the subprocess forwarding path, filter out lines that are purely decorative (regex: `^[=\-]{20,}$`). Alternatively, fix the subprocess scripts themselves to not emit banners when `--no-interaction` is passed.

---

### P5: Blank Lines in Log File (23 lines)

**Standard says:** Every log line should carry information.
**Actual:** 23 empty lines like:
```
2026-03-11 06:58:24 - INFO -
2026-03-11 09:15:01 - INFO -
```

**Root cause:** Spacer `print("")` calls in some code paths (e.g., between alert resolution blocks) get routed to the file handler as empty messages. The `_safe_print()` function is console-only, but some code uses `logging.info("")` or `beautiful_log("")` for spacing.

**Fix:** Add guard in `_write_to_file_handler()`: skip writes where `message.strip() == ""`.

---

### P6: Coffee Break Boxes Have Low Forensic Value (36 instances)

**Standard says (AUDIT_REPORT):** Coffee break content is "low forensic value."
**Actual:** Every coffee break logs 2-4 lines:
```
☕ Coffee Break
  Quick coffee break
  Duration: 60 seconds
  Up Next: Earnings Intelligence
```

With 36 instances per day, this is ~120 lines of "we paused for 60 seconds" noise. The forensic value is near zero — if you need to know when a phase started, the `Step N.N:` marker already tells you.

**Fix options:**
- **Option A (recommended):** Suppress coffee break content from log file entirely. The `create_status_box("☕ Coffee Break", ...)` call in `main_runners.py` could use a `log_to_file=False` parameter.
- **Option B:** Log a single line: `Coffee break: 60s before Step 1.2`

---

### P7: Wait/Sleep Messages Are Low-Value (8+ lines)

```
2026-03-11 06:25:08 - INFO - 💤 Waiting 10 minutes until trading day start
...
2026-03-11 18:18:07 - INFO - 💤 Waiting 12.3 hours until next trading day
2026-03-11 18:48:07 - INFO - 💤 Waiting 11.8 hours until next trading day
...repeated every 30 minutes overnight...
```

**Fix:** Log the initial wait once (with target time), then suppress periodic countdown repeats from the log file. The current code logs every 30-minute poll, which adds nothing for forensics.

---

### P8: Morning Views Subprocess Dumps Entire Dashboard (280+ lines)

Lines 978-1254 contain the full morning views output for all 10 watchlist symbols — complete with WATCHLIST VIEW, OI DISTRIBUTION VIEW, OI TIMING CONTEXT, earnings data, sector data, etc. This is 280 lines of densely formatted dashboard content.

**Assessment:** This is a subprocess gap fix that went too far — the original problem was "subprocess output doesn't reach the log." Now it ALL reaches the log. But the morning views content is already written to its own dedicated log file (`logs/morning_views_YYYY-MM-DD.log`) and emailed as a document.

**Fix:** Log a summary line instead: `Morning Views: 10 symbols processed, email sent`. The full content is in its own log.

---

### P9: AUDIT_REPORT Phase 1 Checklist Items Still Open

The February 2026 audit identified ~70 lines of missing `logging.info()` coverage. None have been implemented. Key gaps:

1. **main.py step markers** — Currently `Step 1.1: Morning Option Pipeline Refresh` is present (good), but the audit wanted `--- [STEP 1.1] ---` format for grep consistency.
2. **Skip decision logging** — `Phase 5: Weekly operations skipped (not Friday)` IS logged (line 15090), so this item may be partially done.
3. **fm_main.py sole-sourced beautiful_log data** — 11 data points where `beautiful_log()` is the only source. If the file handler ever breaks, this data is lost. Parallel `logging.info()` calls were recommended as redundancy.
4. **fm_collector.py missing logging.info()** — Symbol counts, contract totals, storage timing at specific lines.
5. **op_main.py debug→info promotion** — One `logging.debug()` that should be `logging.info()`.

**Assessment:** The redundancy concern (P9.3) is real but lower priority now that the `_write_to_file_handler()` mechanism is proven stable. The step marker format (P9.1) is cosmetic. The remaining items are minor.

---

## Priority Summary

| # | Issue | Lines Affected | Effort | Impact |
|---|-------|---------------|--------|--------|
| P1 | Emojis in log file | 364/day | Medium | High — breaks grep, confuses Autofix |
| P2 | Duplicate log lines | 2-4/day | Low | Medium — misleading during triage |
| P3 | Double timestamps (subprocess) | 57/day | Low | Medium — ugly, harder to parse |
| P4 | Decorative banners (subprocess) | 13/day | Low | Low — visual noise |
| P5 | Blank lines | 23/day | Low | Low — visual noise |
| P6 | Coffee break noise | 120/day | Low | Low — noise but benign |
| P7 | Wait/sleep repeats | 8+/day | Low | Low — noise at end of day |
| P8 | Morning views full dump | 280/day | Medium | Medium — drowns signal with noise |
| P9 | Missing logging.info coverage | N/A | Medium | Low — deferred, system is stable |

---

## Recommended Execution Order

**Batch 1 — Quick wins (P2, P3, P4, P5):** ~30 minutes
Fix duplicate lines, strip subprocess timestamps, filter banners, skip blank lines.

**Batch 2 — Emoji stripping (P1):** ~30 minutes
Add `_strip_emojis()` to `log_utils.py`, apply before file handler writes.

**Batch 3 — Noise reduction (P6, P7, P8):** ~45 minutes
Suppress coffee breaks from log, suppress wait repeats, summarize morning views.

**Batch 4 — Coverage gaps (P9):** ~60 minutes, can defer
Add missing `logging.info()` calls per the original audit checklist.

---

## Appendix: Sample Ideal Log Lines (Goal State)

What the log SHOULD look like after fixes:

```
2026-03-11 06:35:01 - INFO - --- [PHASE 1] PRE-MARKET OPERATIONS ---
2026-03-11 06:35:01 - INFO - Step 1.1: Morning Option Pipeline Refresh
2026-03-11 06:35:01 - INFO - MORNING OPTION PIPELINE REFRESH
2026-03-11 06:35:01 - INFO -   Objective: Refresh Option Contract tables with OI data
2026-03-11 06:35:01 - INFO -   Universe: KLMN 800
2026-03-11 06:35:02 - INFO - Data Collection (1/4)
2026-03-11 06:35:02 - INFO -    Universe: 416 symbols
2026-03-11 06:35:04 - INFO - Fetching option expirations for AAPL
2026-03-11 06:35:11 - INFO - Flushed 540 contracts to storage (AAPL)
...
2026-03-11 06:58:06 - INFO - Progress: 100.0% (416/416) | Contracts: 85,301 | API Calls: 2719
2026-03-11 06:58:06 - INFO - Time: 23.1 minutes
2026-03-11 06:58:27 - INFO - MORNING OPTION PIPELINE COMPLETE
2026-03-11 06:58:27 - INFO -   Symbols Collected: 416
2026-03-11 06:58:27 - INFO -   Total Contracts: 85,301
2026-03-11 06:58:27 - INFO -   OI Timing: 10,923 contracts
2026-03-11 06:58:27 - INFO -   Duration: 23.4 min
2026-03-11 06:59:27 - INFO - Step 1.2: Earnings Intelligence
2026-03-11 06:59:27 - INFO - EARNINGS INTELLIGENCE
...
2026-03-11 07:01:21 - INFO - Step 1.3: Metadata Collection Pipeline
2026-03-11 07:01:22 - INFO - SYMBOL METADATA COLLECTION
2026-03-11 07:01:22 - INFO - Configuration loaded
2026-03-11 07:01:25 - INFO - Quotes complete: 416/416 symbols
2026-03-11 07:02:28 - INFO - Fundamentals complete: 415/416 symbols
2026-03-11 07:02:29 - INFO - Beta complete: 416/416 symbols
2026-03-11 07:02:29 - INFO - Database writes: 416 successful, 0 failed
2026-03-11 07:02:29 - INFO - Failed symbols: Fundamentals failed (1): VIX
2026-03-11 07:02:30 - INFO - METADATA COLLECTION COMPLETE
...
```

No emojis. No double timestamps. No decorative banners. No blank lines. Every line carries information.
