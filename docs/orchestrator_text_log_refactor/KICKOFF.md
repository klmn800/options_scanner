# Text Log Refactor — Kickoff

**Created:** 2026-02-20
**Status:** Changes 1 & 2 DONE (Feb 2026). Change 3 + P1-P5 audit fixes DONE (2026-03-13). P6-P9 deferred.
**Origin:** big-to-do-list.txt items 8 & 9, lessons from console output refactor

---

## Goal

The orchestrator text log (`logs/orchestrator_YYYY-MM-DD.log`) is the forensic record of the trading day. Its audience is developers and AI agents (especially autofix) diagnosing problems after the fact.

Today it's a mix of useful data and decorative console art, while simultaneously missing entire phases of work. Fix both: **clean up the decorative stuff, fill the subprocess gaps.**

---

## The Approach

Each logging function in `log_utils.py` already produces two outputs: one for the console, one for the text file. The refactor adjusts what two of those functions write to the file. No new plumbing, no new calls needed across the codebase.

**What changes:**
- `create_status_box()` — file output changes from full box art to plain content lines
- `phase_header()` — file output changes from `═══` banner to compact `--- [PHASE N] TITLE ---` marker

**What stays the same:**
- `beautiful_log()` — already clean in the file (plain message text, no emoji, logging formatter adds timestamp). Indistinguishable from `logging.info()` in the text log. No change needed.
- `logging.info/warning/error()` — already correct. No change.
- `print("")` — already console-only. No change.
- Console output — completely untouched. Boxes, emojis, banners all stay.

**Why beautiful_log stays:** During the console refactor, `logging.info()` calls that duplicated `beautiful_log()` messages were demoted or removed to clean up the console. This means `beautiful_log()` is now the sole source of some forensic data (milestones, timing breakdowns). Removing it from the file would create gaps requiring ~88 new `logging.info()` calls. Since it already writes clean text to the file, there's no reason to remove it.

---

## Implementation

### Change 1: `create_status_box()` — strip borders from file output

**File:** `tools/log_utils.py`, inside `create_status_box()`

Today the render loop writes every box line (borders + content) to the file handler. Change it to write only the title and content lines as plain text.

**Console (unchanged):**
```
╔══════════════════════════════════════════════════════════╗
║ MORNING OP COMPLETE                                      ║
╠══════════════════════════════════════════════════════════╣
║ Symbols: 746                                             ║
║ Contracts: 127,432                                       ║
║ Duration: 41m 31s                                        ║
╚══════════════════════════════════════════════════════════╝
```

**Log file (before):**
```
2026-02-19 07:16:33 - INFO - ╔══════════════════════════════════════════════════════════╗
2026-02-19 07:16:33 - INFO - ║ MORNING OP COMPLETE                                      ║
2026-02-19 07:16:33 - INFO - ╠══════════════════════════════════════════════════════════╣
2026-02-19 07:16:33 - INFO - ║ Symbols: 746                                             ║
2026-02-19 07:16:33 - INFO - ║ Contracts: 127,432                                       ║
2026-02-19 07:16:33 - INFO - ║ Duration: 41m 31s                                        ║
2026-02-19 07:16:33 - INFO - ╚══════════════════════════════════════════════════════════╝
```

**Log file (after):**
```
2026-02-19 07:16:33 - INFO - MORNING OP COMPLETE
2026-02-19 07:16:33 - INFO -   Symbols: 746
2026-02-19 07:16:33 - INFO -   Contracts: 127,432
2026-02-19 07:16:33 - INFO -   Duration: 41m 31s
```

### Change 2: `phase_header()` — compact marker in file output

**File:** `tools/log_utils.py`, inside `phase_header()`

Today writes the full `═══` banner (3 lines) to the file. Change to write a single marker line.

**Console (unchanged):**
```
════════════════════════════════════════════════════════════
                 PHASE 1: PRE-MARKET OPERATIONS
════════════════════════════════════════════════════════════
```

**Log file (before):**
```
2026-02-19 06:35:01 - INFO - ════════════════════════════════════════════════════════════
2026-02-19 06:35:01 - INFO -                PHASE 1: PRE-MARKET OPERATIONS
2026-02-19 06:35:01 - INFO - ════════════════════════════════════════════════════════════
```

**Log file (after):**
```
2026-02-19 06:35:01 - INFO - --- [PHASE 1] PRE-MARKET OPERATIONS ---
```

### Change 3: Subprocess gap — forward output to file handler

**File:** `main_runners.py`, inside `_run_streaming_subprocess()`

Add `_write_to_file_handler(stripped_line)` alongside the existing `sys.stdout.write()`. Strip the subprocess's own timestamp before logging (pattern: `split(' - INFO - ', 1)` from console refactor).

Also fix the two non-standard subprocess invocations:
- `run_metadata_collection()`: switch from `subprocess.run(capture_output=True)` + `print()` to `_run_streaming_subprocess()`
- `run_morning_views()`: add file-handler forwarding to the custom Popen capture loop (keep console suppression)

---

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| beautiful_log in text file | **Keep** | Already clean (no emoji in file). Sole source of some data after console refactor demotions. Removing it would require ~88 new logging.info() calls. |
| Per-symbol collection lines (22K/day) | **Keep at INFO** | Disk is cheap. `grep NVDA orchestrator_2026-02-19.log` is the first thing you do debugging a symbol. |
| Subprocess double-timestamps | **Strip** | One consistent timestamp format. Pattern already proven in console refactor. |
| Phase headers in log | **Compact marker** | `--- [PHASE 2] FLOW MONITOR ---`. Greppable, visual separation. |
| Box content in log | **Plain text, no borders** | Title + indented content lines. Same data, no art. |

---

## Scope

| Change | File | Lines Changed (est.) |
|--------|------|---------------------|
| Box file output → plain content | `tools/log_utils.py` | ~15 |
| Phase header file output → marker | `tools/log_utils.py` | ~5 |
| Subprocess forwarding to file handler | `main_runners.py` | ~15 |
| Metadata subprocess switch | `main_runners.py` | ~10 |
| Morning views file forwarding | `main_runners.py` | ~5 |
| **Total** | **2 files** | **~50 lines** |

---

## Future Work (not in this implementation)

- **logging.debug() promotions**: ~15 task start/completion markers across FM and OP could be promoted to INFO. Incremental, do anytime.
- **Subprocess scripts' own logging**: Some subprocess scripts (metadata, db_backup) use `print()` internally. Converting those to `logging.info()` would give them proper formatting before we forward their output. Low priority.
- **Performance persistence** (big-to-do-list item 8): `step_performance_log` table, rolling baselines, autofix integration. Separate project, builds on the forensic foundation this refactor establishes.

---

## References

- `docs/orchestrator_text_log_refactor/AUDIT_REPORT.md` — full audit of all 25 files
- `docs/CONSOLE_DEVELOPER_GUIDE.md` Section 4 — logging type taxonomy
- `docs/main_orchestrator_refactor/POST_REFACTOR_PUNCHLIST.md` line 1508 — original seed notes
- `tools/log_utils.py` — where Changes 1 & 2 live
- `main_runners.py` — where Change 3 lives
