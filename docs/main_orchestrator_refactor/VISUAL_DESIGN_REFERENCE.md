# Visual Design Reference

Every distinct visual element the console output system produces, rendered as a mockup. Use this as the single source of truth for what the system should look like during and after the refactor.

**Rendering engine:** `tools/log_utils.py` — all elements flow through `_safe_print()` (console) and `_write_to_file_handler()` (log file).

### Current vs Target Status

Each section is tagged with its implementation status:

- **CURRENT** — Looks like this today. No visual changes needed.
- **TARGET** — Shows the post-refactor design. Does NOT look like this today.
- **CURRENT RENDERING / TARGET CONTENT** — The box/element itself renders correctly today, but the data inside it changes (e.g., filler lines removed, DB queries replaced with return dict values).

---

## Table of Contents

1. [Startup Banner](#1-startup-banner) — CURRENT
2. [Phase Header](#2-phase-header) — CURRENT
3. [Mission Box](#3-mission-box) — CURRENT
4. [Completion Box (Success)](#4-completion-box-success) — CURRENT RENDERING / TARGET CONTENT
5. [Completion Box (Failure / Skip)](#5-completion-box-failure--skip) — CURRENT
6. [Coffee Break](#6-coffee-break) — TARGET
7. [beautiful_log Lines](#7-beautiful_log-lines) — CURRENT
8. [Strategy Progress Lines](#8-strategy-progress-lines) — TARGET
9. [Inline Warnings](#9-inline-warnings) — TARGET
10. [FM Cycle Output (Delegated Orchestrator)](#10-fm-cycle-output-delegated-orchestrator) — CURRENT (KEEP) / TARGET (trim redundancy)
11. [FM Session Summary Box](#11-fm-session-summary-box) — CURRENT
12. [Day-End Summary](#12-day-end-summary) — CURRENT
13. [Autofix Subprocess Banner](#13-autofix-subprocess-banner) — CURRENT
14. [Element Inventory](#14-element-inventory)
15. [Sub-Phase Structure (Strategy Coordinators)](#15-sub-phase-structure-strategy-coordinators) — CURRENT / TARGET (channel fix)
16. [FM Alert Display Block](#16-fm-alert-display-block) — CURRENT / TARGET (border removal)
17. [FM Market Hours beautiful_log Cross-Check](#17-fm-market-hours-beautiful_log-cross-check) — Reference (Package 6 Step 7 alignment)
18. [FM Coffee Break (Internal)](#18-fm-coffee-break-internal) — TARGET

---

## 1. Startup Banner — CURRENT

**Produced by:** `main_ui.py` → `print_banner(mode)`
**When:** Once, at the very start of a daily cycle
**Border style:** Double-line `╔═╗ ║ ╠═╣ ╚═╝`, inner width 67 chars

### Full Mode (`mode="full"`)

```
╔═══════════════════════════════════════════════════════════════════╗
║ 🚀 OPTIONS SCANNER ORCHESTRATOR v4.0                             ║
╠═══════════════════════════════════════════════════════════════════╣
║ 📅 Wednesday, February 18, 2026                                  ║
║ ⏰ 06:35:00 AM EST                                               ║
║ 🏭 Production System: Active                                     ║
╠═══════════════════════════════════════════════════════════════════╣
║ 🌟 TODAY'S SCHEDULE                                              ║
║                                                                   ║
║ Phase 1: Pre-Market (6:35 AM)                                     ║
║   1.1  Morning Option Pipeline Refresh                            ║
║   1.2  Earnings Arbitrage Scanner                                 ║
║   1.3  Metadata Collection                                        ║
║   1.4  Query Database Sync                                        ║
║   1.5  Morning Views (email)                                      ║
║                                                                   ║
║ Phase 2: Flow Monitor (9:15 AM - 5:00 PM)                        ║
║   2.1  Pre-Market Setup                                           ║
║   2.2  Market Hours Monitoring                                    ║
║   2.3  Market Close                                               ║
║   2.4  Historical Backfill                                        ║
║   2.5  Market Regime Summary                                      ║
║   2.6  Symbol Rollup                                              ║
║   2.7  Daily Evaluation                                           ║
║                                                                   ║
║ Phase 3: Post-Market (~5:00 PM)                                   ║
║   3.1  Evening Option Pipeline Refresh                            ║
║   3.2  Airline Play Tracking (7 symbols)                          ║
║   3.3  Query Database Sync (Final)                                ║
║                                                                   ║
║ Phase 4: Evening Operations                                       ║
║   4.1  Daily Backup                                               ║
║   4.2  Autofix Review                                             ║
║                                                                   ║
║ Phase 5: Friday Operations                                        ║
║   5.1  Weekly Backup                                              ║
║   5.2  Earnings Calendar Refresh                                  ║
║   5.3  Sector Archive (3-tier)                                    ║
║                                                                   ║
║ 🎯 Mission: Complete daily options analysis workflow              ║
╚═══════════════════════════════════════════════════════════════════╝
```

Non-Friday variant replaces Phase 5 content with:
```
║ Phase 5: Weekly ops (Friday only - skipped today)                 ║
```

### Single-Step Modes

Same border structure, shorter content. Example (`mode="option-morning"`):

```
╔═══════════════════════════════════════════════════════════════════╗
║ 🚀 OPTIONS SCANNER ORCHESTRATOR v4.0                             ║
╠═══════════════════════════════════════════════════════════════════╣
║ 📅 Wednesday, February 18, 2026                                  ║
║ ⏰ 06:35:00 AM EST                                               ║
║ 🏭 Production System: Active                                     ║
╠═══════════════════════════════════════════════════════════════════╣
║ 🌅 MORNING OPTION PIPELINE                                       ║
║                                                                   ║
║ Target: Collect fresh Open Interest for KLMN symbols              ║
║ Strategy: Collection → Rollup → OI Timing Analysis                ║
║                                                                   ║
║ 🎯 Mission: Fresh OI data before market open                     ║
╚═══════════════════════════════════════════════════════════════════╝
```

Other modes: `flow-monitor`, `option-evening`, `test`.

---

## 2. Phase Header — CURRENT

**Produced by:** `log_utils.py` → `phase_header(title, phase_number)`
**When:** At the start of each major phase of the daily cycle
**Width:** `max(60, len(header_text) + 4)`, centered

### With phase number

```
════════════════════════════════════════════════════════════
                PHASE 1: PRE-MARKET OPERATIONS
════════════════════════════════════════════════════════════
```

### Without phase number

```
════════════════════════════════════════════════════════════
                       COFFEE BREAK
════════════════════════════════════════════════════════════
```

---

## 3. Mission Box — CURRENT

**Produced by:** `log_utils.py` → `create_status_box(title, lines, success=True)`
**When:** Before each strategy/step runs — the orchestrator's "here's what we're about to do"
**Border style:** Double-line `╔═╗ ║ ╠═╣ ╚═╝` (same as success completion box)
**Width:** `max(60, longest_line + 4)`

```
╔══════════════════════════════════════════════════════════╗
║ 🌅 MORNING OPTION PIPELINE REFRESH                      ║
╠══════════════════════════════════════════════════════════╣
║ Objective: Refresh Option Contract tables with OI data   ║
║ Steps: Collection → Rollup → OI Timing Analysis → Report ║
║ Universe: KLMN 800                                       ║
║ Timing: Completes before Flow Monitor starts at 9:15 AM  ║
╚══════════════════════════════════════════════════════════╝
```

**Design note:** Mission boxes and success completion boxes use the same `create_status_box()` function with `success=True`. They are visually identical — differentiated only by title and content.

---

## 4. Completion Box (Success) — CURRENT RENDERING / TARGET CONTENT

**Produced by:** `log_utils.py` → `create_status_box(title, lines, success=True)`
**When:** After a strategy returns successfully — built from the return dict

**What changes:** The box rendering stays identical. The *content* changes — filler lines like "Database secured" and "System: Ready for operations" are removed, hardcoded approximate counts are replaced with real values from return dicts, and DB queries are eliminated. See CONSOLE_OUTPUT_AUDIT.md for the full list of filler lines being removed.
**Border style:** Double-line `╔═╗ ║ ╠═╣ ╚═╝`

```
╔══════════════════════════════════════════════════════════╗
║ MORNING OPTION PIPELINE COMPLETE                         ║
╠══════════════════════════════════════════════════════════╣
║ Trade Date: 2026-02-18                                   ║
║ Symbols Collected: 747                                   ║
║ Total Contracts: 18,432                                  ║
║ Symbol Summaries: 747                                    ║
║ OI Timing Calculated: 12,891                             ║
║ Duration: 12m 34s                                        ║
╚══════════════════════════════════════════════════════════╝
```

**Rules:**
- Every field comes from the strategy's return dict — never query the DB
- Include: key counts, duration, error count (if > 0, list affected symbols)
- No filler lines ("System: Ready for operations", "Database secured")
- No hardcoded approximate counts ("~750 symbols")

---

## 5. Completion Box (Failure / Skip) — CURRENT

**Produced by:** `log_utils.py` → `create_status_box(title, lines, success=False)`
**When:** Strategy failed or step was skipped
**Border style:** Single-line `┌─┐ │ ├─┤ └─┘`

### Failure

```
┌──────────────────────────────────────────────────────────┐
│ MORNING OPTION PIPELINE FAILED                           │
├──────────────────────────────────────────────────────────┤
│ Symbols Attempted: 747                                   │
│ Symbols Succeeded: 305                                   │
│ Errors: 442                                              │
│ Failure Reason: Tradier API authentication revoked        │
│ Duration: 4m 12s                                         │
└──────────────────────────────────────────────────────────┘
```

### Skip

```
┌──────────────────────────────────────────────────────────┐
│ SKIPPED                                                  │
├──────────────────────────────────────────────────────────┤
│ Market closed today                                      │
└──────────────────────────────────────────────────────────┘
```

**Design note:** The single-line border is a deliberate visual signal — lighter weight tells the user "this didn't run" or "this didn't work" at a glance.

---

## 6. Coffee Break — TARGET

**Produced by:** `main_ui.py` → `coffee_break()` using `log_utils.create_status_box()`
**When:** Orchestrator pauses between steps (inter-step cooldowns, market window waits)

**What changes:** Currently renders as two bare `_safe_print()` lines: `☕ Coffee break: 60 seconds - context` and `☕ Resuming operations`. Does NOT go to the log file. No "Up Next" awareness. Target uses `create_status_box()` for visual consistency and log file capture, and dynamically resolves the next step name via `STEP_SEQUENCE`.

### Standard coffee break (with dynamic "Up Next")

Every coffee break shows what comes next. The "Up Next" line is resolved dynamically from a `STEP_SEQUENCE` constant — not hardcoded at each call site. If steps are reordered, added, or removed, updating the sequence list automatically updates every coffee break's "Up Next" display.

```
╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Time for a quick stretch                                 ║
║ Duration: 60 seconds                                     ║
║ Press Ctrl+C to safely stop Option Scanner system.       ║
║ Up Next: Earnings Arbitrage Scanner                      ║
╚══════════════════════════════════════════════════════════╝
```

### Resuming

```
╔══════════════════════════════════════════════════════════╗
║ Resuming Operations                                      ║
╠══════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                      ║
╚══════════════════════════════════════════════════════════╝
```

### More examples across the day

```
╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Taking a well-deserved break                             ║
║ Duration: 60 seconds                                     ║
║ Up Next: Evening Option Pipeline                         ║
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Final sync complete - waiting for lock release           ║
║ Duration: 60 seconds                                     ║
║ Up Next: Daily Backup                                    ║
╚══════════════════════════════════════════════════════════╝
```

### Implementation: STEP_SEQUENCE

The step order is defined once as a class constant on the orchestrator. `coffee_break()` receives `after_step` to identify which step just finished, looks up the next entry, and renders it.

```python
STEP_SEQUENCE = [
    'Morning Option Pipeline',
    'Earnings Arbitrage Scanner',
    'Metadata Collection',
    'Query Database Sync (Morning)',
    'Morning Views',
    'Flow Monitor',
    'Evening Option Pipeline',
    'Query Database Sync (Evening)',
    'Earnings Pipeline',
    'Airline Play Tracking',
    'Query Database Sync (Final)',
    'Daily Backup',
    'Autofix Review',
    # Friday-only (only reached inside `if is_friday:` block)
    'Weekly Backup',
    'Earnings Calendar Refresh',
    'Sector Archive',
]
```

Call sites identify the step that just finished:
```python
self.coffee_break(60, "Time for a quick stretch", after_step="Morning Option Pipeline")
# → "Up Next: Earnings Arbitrage Scanner"  (looked up dynamically)
```

If `after_step` is the last entry in the sequence (or not provided), the "Up Next" line is omitted.

**Rules:**
- No countdown updates or "still waiting" messages between the two boxes
- "Up Next" is always present except after the final step of the day
- FM's internal `coffee_break()` (between post-market sub-tasks) uses the same format with its own context-aware messages and next-task info

---

## 7. beautiful_log Lines — CURRENT

**Produced by:** `log_utils.py` → `beautiful_log(message, level)`
**When:** Orchestrator operational messages (not strategy output)
**Format:** `emoji HH:MM:SS - message`

### All 5 levels

```
ℹ️ 09:15:32 - Processing 800 symbols
✅ 09:18:44 - Pipeline complete
❌ 09:18:44 - Failed to connect to Tradier API
⚠️ 09:18:44 - API rate limit approaching
🔥 09:18:44 - Entering market hours phase
```

### Anti-stutter behavior

If the message already starts with an emoji, the level emoji is suppressed:

```
09:18:44 - ✅ Already has emoji            (no double emoji)
09:18:44 - 🚀 Launching pipeline           (no double emoji)
```

**Scope note:** `beautiful_log()` is an orchestrator tool. Strategies should not call it. Strategy output uses `print()` or `logging.info()`.

---

## 8. Strategy Progress Lines — TARGET

**Produced by:** Strategy code via `print()` or `logging.info()`
**When:** During strategy execution — the only thing strategies produce

**What changes:** Today strategies also produce boxes (`═══` banners), `beautiful_log()` calls, celebrations (`🎉 COLLECTION COMPLETE`), tree diagrams (`├─ └─`), and multi-line summaries. After the refactor, all of that is deleted — only these clean progress lines remain. See CONSOLE_OUTPUT_AUDIT.md for the full violation inventory.
**Indent:** 2 spaces to visually nest under the mission box

### Progress Framework

Progress intervals are determined by two questions: **are per-item details informative?** and **what's the item scale?**

| | Details Important | Details NOT Important |
|---|---|---|
| **Full universe (~750 symbols)** | Per-item with info | Batch summary per 100 |
| **Sub-universe (50-200 items)** | Per-item with info | Batch summary per 50 |
| **Contract universe (thousands)** | — | Batch summary per 1,000 |
| **Huge (100K+ pages/rows)** | — | Keep current intervals |
| **Tiny (< 10 items)** | Per-item (always) | Per-item (always) |

### Per-Process Spec

| Process | Scale | Details? | Interval | Notes |
|---------|-------|----------|----------|-------|
| OP Collector | Full universe | Yes | Per-item + summary/100 | Shows contracts fetched per symbol |
| OP Symbol Rollup | Full universe | No | Per 100 | Batch count + ETA |
| OP Timing Calculator | Contracts (~13K) | No | Per 1,000 | Updated/skipped counts |
| Symbol Metadata | Full universe | No | Per 100 (batched) | 3 phases, batch success counts |
| FM Collector (market hours) | Full universe | Yes | Per-item | Shows contracts per symbol |
| FM Historical Backfill | Sub-universe | No | Per 100 | Currently 50 — needs fix |
| FM Symbol Rollup | Sub-universe | Yes | Per-item with data | Show alerts fired, key metrics stored |
| FM Evaluator | Sub-universe | No | Per 50 | Batch count only |
| FM Alert Resolver | Variable (tens-hundreds) | Yes | Per-item with data | Show BUILDING/CLOSING/NEUTRAL per alert |
| FM Alerts display | Per-scan (0-20) | Yes | Per-item | These ARE the product |
| EI Fetch Upcoming | Full universe | Yes | Per-item | Show earnings found per symbol |
| EI Moves Upcoming | Sub-universe (~50-150) | Yes | Per-item with data | Shows signal, underpricing |
| EI Post Earnings Calc | Tiny (1-5) | Yes | Per-item | Always per-item |
| EI Arbitrage Scanner | Tiny (handful) | — | Scan-level only | No iteration to batch |
| DB Archive Sector | Per-sector nested | — | Per-sector + per-batch | Friday night operations |
| DB Backup | Huge (100K+ pages) | No | Per 30,000 pages | ~2-3 GB database |

### Per-Item Format (details important)

When details matter, each line shows what was processed and key data:

```
  Fetching option expirations for NVDA
  ✅ Flushed 892 contracts to storage (NVDA)
  Fetching option expirations for GOOG
  ✅ Flushed 634 contracts to storage (GOOG)
  📊 Progress: 26.8% (200/747) | Success: 99.5% | Contracts: 24,891 | API Calls: 1120
```

```
  AAPL: BUILDING (OI +12,400, 3 contracts)
  NVDA: CLOSING (OI -8,200, 2 contracts)
  MSFT: NEUTRAL (OI +200, 1 contract)
```

```
  TOST: earnings in 3d, 45.2% underpriced → BUY signal
  NFLX: earnings in 5d, 12.1% underpriced → NEUTRAL
```

### Batch Summary Format (details not important)

When individual items aren't informative, show periodic batch counts:

```
  Progress: 100/747 symbols (13.4%) - batch: 3.2s, ETA: 21s
  Progress: 200/747 symbols (26.8%) - batch: 3.1s, ETA: 18s
```

```
  Progress: 1000/13431 contracts (7.4%) - 812 updated, 188 skipped
  Progress: 2000/13431 contracts (14.9%) - 1687 updated, 313 skipped
```

### Multi-step strategy

```
  [1/3] Fetching earnings calendar...
  AAPL: earnings 2026-02-25
  NVDA: earnings 2026-03-01
  ...
  [2/3] Archiving past events...
  [3/3] Cleaning up expired records...
```

### Time-based heartbeat

If no progress line has been emitted for **60 seconds**, emit one regardless of the count interval.

### ETA guidance

Include ETA only when per-item pace is stable (uniform API calls, fixed DB inserts). Omit for variable-latency operations. A jumping ETA is worse than no ETA.

---

## 9. Inline Warnings — TARGET

**Produced by:** Strategy code via `print()` or `logging.warning()`
**When:** Exceptional conditions during execution — failure clusters, threshold breaches
**Indent:** 2 spaces (same as progress)

```
  WARNING: 10 consecutive failures — possible API issue (last: NVDA, GOOG, AMZN)
  WARNING: WOLF - greeks null, skipping
  WARNING: API budget below 5 calls — throttling enrichment
```

**Rules:**
- Isolated failures (1-2 symbols): Say nothing mid-stream. Include in `failed_symbols` in return dict.
- Failure clusters (10+ consecutive): Emit a single warning line.
- Always prefixed with `WARNING:` — never `beautiful_log()`, boxes, or banners.

---

## 10. FM Cycle Output (Delegated Orchestrator) — CURRENT (KEEP) / TARGET (trim redundancy)

**Produced by:** FM market hours loop via `logging.info()` (target channel — current uses mixed `print()`/`beautiful_log()`)
**When:** After each ~20-minute collection cycle during market hours
**Role:** FM is a delegated orchestrator during market hours — permitted to produce per-cycle output

The FM cycle output is **information-dense and useful**. The refactor does NOT condense it to a single line. Instead, it:
1. Fixes the **output channel** (everything via `logging.info()` / `logging.warning()`, no `beautiful_log()` or raw `print()`)
2. Removes **redundant announcements** (same fact stated twice in different formats)
3. Removes **strategy-owned visual elements** (`═══` banners drawn by strategy code) — the orchestrator owns box/banner rendering
4. Keeps all **useful diagnostic content** (analysis summaries, alert displays, timing breakdowns)

### Performance breakdown — KEEP

```
✅ Cycle 15 complete - Performance Breakdown:
   📊 Collection: 1222.9s
   🔍 Analysis: 22.4s
   🚨 Alerts: 1.8s
   🎯 Watchlist: 6.4s
   🔄 DB Sync: 99.6s (104,416 rows)
   ⏱️ Total: 1353.0s
```

This stays. It shows where time went in each cycle — essential for monitoring system health.

### What changes per cycle (redundancy removal)

The full cycle currently produces output in these blocks. Here's what to keep vs cut:

**Collection phase:**
- KEEP: Per-symbol collection lines (`Option chains collected for LUV - 224 contracts`)
- KEEP: Deduplication warnings (formalize to always show which symbols are affected)
- KEEP: Storage confirmation (`Stored 104287 option contracts...`)
- CUT: Double "collection complete" announcements (keep the emoji-prefixed one with timing)

**Analysis phase:**
- KEEP: `Starting unified algorithm analysis...`
- KEEP: `Retrieved 104287 contracts for unified analysis`
- KEEP: `Market regime: elevated`
- KEEP: Full analysis summary block (contracts processed, statistics tracking, data quality warnings, filter counts, conviction tiers, timing) — **content stays, `═══` banner rendering changes to orchestrator-owned**
- CUT: `DEBUG:` prefixed lines at INFO level
- CUT: `Successfully updated 104287 contracts` (redundant with summary block)

**Alert phase:**
- KEEP: `Processing alerts for scan: ...`
- KEEP: Alert display block (the `🚨 FLOW MONITOR ALERTS` visual with per-alert details)
- KEEP: Per-alert save confirmations (`Complete alert saved for XPO 210.0 with score 6.43`)
- KEEP: `Alert persistence complete: 1 saved, 0 failures`
- KEEP: Alert processing summary block (candidates, filters, alerts sent, notifications, DB saves)
- CUT: Pre-display chatter (`Found 4 alert candidates`, `Filters applied: 1 passed, 3 filtered`, `Processing 1 unique alerts`, `Updating 3 filtered contracts`) — this info is in the processing summary

**Watchlist + news phase:**
- KEEP: `Watchlist updated: 1 created, 0 updated from 1 alerts`
- KEEP: News enrichment results per symbol
- CUT: Duplicate "Fetching news" lines (two formats for same fetch)
- CUT: Duplicate batch/overall summary when they say the same thing

**DB sync:**
- KEEP: Start and completion lines

**Cycle summary:**
- KEEP: Multi-line performance breakdown (see above)

### Approved target: full cycle output

```
[per-symbol collection lines — 746 lines, one per symbol]
2026-02-17 15:48:32 - WARNING - ⚠️ API returned 160 duplicate contracts in batch (symbols: LUV, JETS)
2026-02-17 15:48:32 - WARNING - ⚠️ Deduplicated 160 duplicate contracts from API response before DB insert
2026-02-17 15:50:05 - INFO - Stored 104287 option contracts with scan_timestamp: 2026-02-17 15:29:42

🔍 Collection complete: 2026-02-17 15:29:42 (1222.9s)
2026-02-17 15:50:05 - INFO - Starting unified algorithm analysis for scan: 2026-02-17 15:29:42 (live production mode)
2026-02-17 15:50:07 - INFO - Retrieved 104287 contracts for unified analysis
2026-02-17 15:50:08 - INFO - Market regime: elevated

2026-02-17 15:50:27 - INFO - UNIFIED ALGORITHM ANALYSIS SUMMARY
2026-02-17 15:50:27 - INFO - Contracts processed: 104287
2026-02-17 15:50:27 - INFO - Contracts updated: 104287
2026-02-17 15:50:27 - INFO - Enhanced statistics tracking:
2026-02-17 15:50:27 - INFO -   Early day fallbacks: 91
2026-02-17 15:50:27 - INFO -   Running total used: 15289
2026-02-17 15:50:27 - INFO -   Missing baselines: 142
2026-02-17 15:50:27 - WARNING - Data quality issues detected:
2026-02-17 15:50:27 - WARNING -   Missing price data: 52
2026-02-17 15:50:27 - WARNING -   Bad tick data (ask < bid): 0
2026-02-17 15:50:27 - WARNING -   Total data quality warnings: 52
2026-02-17 15:50:27 - INFO - Premium filtered: 100793
2026-02-17 15:50:27 - INFO - Volume filtered: 104260
2026-02-17 15:50:27 - INFO - High conviction alerts (8.0+): 7
2026-02-17 15:50:27 - INFO - Unified alerts (6.0+): 19
2026-02-17 15:50:27 - INFO - Smart money alerts (1.5+): 0
2026-02-17 15:50:27 - INFO - Total analysis time: 22.24 seconds
2026-02-17 15:50:27 - INFO - Total significant flows detected: 26

2026-02-17 15:50:28 - INFO - Processing alerts for scan: 2026-02-17 15:29:42

2026-02-17 15:50:29 - INFO -
2026-02-17 15:50:29 - INFO - 🚨 FLOW MONITOR ALERTS - 15:50:29
2026-02-17 15:50:29 - INFO -
2026-02-17 15:50:29 - INFO - 🟡 MEDIUM ALERTS (Score 6.0-7.9)
2026-02-17 15:50:29 - INFO - XPO [LAR] $210.0 calls (31d) | Vol: 4,021 (4.0x) | OI: 6,836 | V/OI: 0.6 | ...
2026-02-17 15:50:29 - INFO -
2026-02-17 15:50:29 - INFO - 📊 SUMMARY: 1 alerts sent (0 HIGH, 1 MEDIUM, 0 LOW)

2026-02-17 15:50:29 - INFO - Saving 1 alerts to flow_alerts table
2026-02-17 15:50:29 - INFO - Complete alert saved for XPO 210.0 with score 6.43
2026-02-17 15:50:29 - INFO - Alert persistence complete: 1 saved, 0 failures

2026-02-17 15:50:29 - INFO -
2026-02-17 15:50:29 - INFO - ALERT PROCESSING SUMMARY
2026-02-17 15:50:29 - INFO - Candidates found: 4
2026-02-17 15:50:29 - INFO - Filters applied: 1 ETFs, 2 delta
2026-02-17 15:50:29 - INFO - Alerts sent: 1
2026-02-17 15:50:29 - INFO - Console notifications: 1
2026-02-17 15:50:29 - INFO - Email notifications: 0
2026-02-17 15:50:29 - INFO - Database saves: 1 successful, 0 failed

2026-02-17 15:50:32 - INFO - Watchlist updated: 1 created, 0 updated from 1 alerts
2026-02-17 15:50:34 - INFO - News enrichment for XPO: score=-0.02, label='Bullish 1/Bearish 1/Neutral 1', articles=3

🔄 Starting database quick-sync...
✅ Quick-sync completed: 104,416 rows in 99.6s

✅ Cycle 15 complete - Performance Breakdown:
   📊 Collection: 1222.9s
   🔍 Analysis: 22.4s
   🚨 Alerts: 1.8s
   🎯 Watchlist: 6.4s
   🔄 DB Sync: 99.6s (104,416 rows)
   ⏱️ Total: 1353.0s

┌───────────────────────────────────────────────────────────┐
│ ☕ Coffee Break - 60 seconds                               │
│ Press Ctrl+C to safely stop Option Scanner system.         │
├───────────────────────────────────────────────────────────┤
│ Up Next: Evening Option Pipeline                           │
└───────────────────────────────────────────────────────────┘

=== Cycle 16 | 15:53:15 | 746 symbols ===
```

**Note:** The `═══` banners that previously wrapped the analysis summary (`fm_analyzer.py`) and alert display/processing summary (`fm_alerts.py`) are removed in the approved target. The *content* stays identical — only the decorative borders are stripped. Blank lines provide section separation. See Section 16 for the alert display target format. When in doubt about keeping or cutting any piece of cycle output, ask Ben.

---

## 11. FM Session Summary Box — CURRENT

**Produced by:** `main_runners.py` → `_display_session_summary(session_stats)`
**When:** After FM market hours ends — orchestrator builds from `FMSessionStats.get_summary()` return dict
**Border style:** Double-line (success box)

```
╔══════════════════════════════════════════════════════════════════════╗
║ MARKET HOURS SESSION SUMMARY                                        ║
╠══════════════════════════════════════════════════════════════════════╣
║ Cycles: 20 (19 successful, 1 failed)                                ║
║ Avg cycle: 141.2s | Fastest: 128.4s | Slowest: 167.3s              ║
║                                                                      ║
║ Collection Errors: 14 total (8 timeout, 4 connection, 2 other)      ║
║ Missing Quotes: 3 symbols (every cycle: VIXW, SPX, VIX)            ║
║ Failed Options: 2 symbols                                            ║
║                                                                      ║
║ News sentiment: 12 enriched, 3 skipped, 1 failed                    ║
╚══════════════════════════════════════════════════════════════════════╝
```

**Data source:** `FMSessionStats.get_summary()` — the model return dict. Zero DB queries.

**Restart resilience:** `FMSessionStats` saves its state to `logs/daily_state.json` after each cycle and restores from it on init (Package 0, Steps 6-7). If FM is restarted mid-day, the session summary reflects ALL cycles from the entire day, not just post-restart cycles.

### End-of-Day Detail Lines

After the session summary box, `format_end_of_day_lines()` returns additional detail lines rendered via `beautiful_log()`:

```
ℹ️ 16:05:12 -
ℹ️ 16:05:12 - Missing Quotes Summary (3 symbols across 20 cycles):
ℹ️ 16:05:12 -    Every cycle (3): VIXW, SPX, VIX
ℹ️ 16:05:12 -
ℹ️ 16:05:12 - Failed Options Summary (2 symbols across 20 cycles):
ℹ️ 16:05:12 -    Every cycle (1): WOLF
ℹ️ 16:05:12 -    Intermittent:
ℹ️ 16:05:12 -      BDX - 14/20 cycles
ℹ️ 16:05:12 -
ℹ️ 16:05:12 - Collection Errors: 14 total (8 timeout, 4 connection, 2 other)
ℹ️ 16:05:12 -    Recurring error symbols: WOLF (x20), BDX (x14)
```

---

## 12. Day-End Summary — CURRENT

**Produced by:** `main.py` → `_print_day_summary(results, day_start_time)`
**When:** After all daily phases complete (end of `run_smart_endless_operation()`)
**Border style:** Double-line if no failures, single-line if any failures

### All steps passed

```
╔══════════════════════════════════════════════════════════════════════╗
║ TRADING DAY COMPLETE                                                ║
╠══════════════════════════════════════════════════════════════════════╣
║   ✅ 1.1 Morning Option Pipeline: OK                                ║
║   ✅ 1.2 Arbitrage Scanner: OK                                      ║
║   ✅ 1.3 Metadata Collection: OK                                    ║
║   ✅ 1.4 Query Sync (Morning): OK                                   ║
║   ✅ 1.5 Morning Views: OK                                          ║
║   ✅ 2. Flow Monitor: OK                                            ║
║   ✅ 3.1 Evening Option Pipeline: OK                                ║
║   ✅ 3.2 Query Sync (Evening): OK                                   ║
║   ✅ 3.3 Earnings Pipeline: OK                                      ║
║   ✅ 3.4 Airline Play: OK                                           ║
║   ✅ 3.5 Query Sync (Final): OK                                     ║
║   ✅ 4.1 Daily Backup: OK                                           ║
║   ✅ 4.2 Autofix Review: OK                                         ║
║   -- 5.1 Weekly Backup: Skipped                                     ║
║   -- 5.2 Earnings Refresh: Skipped                                  ║
║   -- 5.3 Sector Archive: Skipped                                    ║
║                                                                      ║
║ Runtime: 10h 32m                                                     ║
║ Passed: 13 | Failed: 0 | Skipped: 3                                 ║
╚══════════════════════════════════════════════════════════════════════╝
```

### With failures

```
┌──────────────────────────────────────────────────────────────────────┐
│ TRADING DAY COMPLETE - 2 FAILURES                                    │
├──────────────────────────────────────────────────────────────────────┤
│   ✅ 1.1 Morning Option Pipeline: OK                                 │
│   ❌ 1.2 Arbitrage Scanner: FAILED                                   │
│   ✅ 1.3 Metadata Collection: OK                                     │
│   ✅ 1.4 Query Sync (Morning): OK                                    │
│   ✅ 1.5 Morning Views: OK                                           │
│   ❌ 2. Flow Monitor: FAILED                                         │
│   -- 3.1 Evening Option Pipeline: Skipped                            │
│                                                                      │
│ Runtime: 2h 30m                                                      │
│ Passed: 4 | Failed: 2 | Skipped: 1                                   │
└──────────────────────────────────────────────────────────────────────┘
```

**Key detail:** The `results` dict is built from actual True/False/'skipped' values collected during the day — never hardcoded.

**Restart resilience:** The orchestrator persists each phase result to `logs/daily_state.json` as it completes (Package 0, Step 6). On mid-day restart, saved results are loaded back into the `results` dict. Phases that ran before the restart show their actual outcome (OK/FAILED), not "Skipped." The `date` field in the JSON acts as a staleness guard — yesterday's data is ignored.

---

## 13. Autofix Subprocess Banner — CURRENT

**Produced by:** `main_ui.py` → `display_autofix_output(result)`
**When:** A subprocess triggers autofix immediate mode — detected by scanning subprocess stdout for the autofix banner marker
**Style:** Raw `=` separators (not Unicode boxes — intentionally distinct, signals "system intervention")

```
======================================================================
🚨 AUTOFIX IMMEDIATE MODE TRIGGERED IN SUBPROCESS
======================================================================
[subprocess autofix output displayed here]
======================================================================
```

**Detection:** Checks for `🚨` or `SPAWNING AUTO-FIX` in subprocess stdout.

---

## 14. Element Inventory

Quick-reference: which function produces what, who calls it.

| Element | Function | Called by | Border |
|---------|----------|-----------|--------|
| Startup banner | `main_ui.print_banner()` | Orchestrator (once) | `╔═╗` custom |
| Phase header | `log_utils.phase_header()` | Orchestrator | `═══` separator |
| Mission box | `log_utils.create_status_box(success=True)` | Orchestrator (before step) | `╔═╗ ║ ╠═╣ ╚═╝` |
| Completion box (success) | `log_utils.create_status_box(success=True)` | Orchestrator (after step) | `╔═╗ ║ ╠═╣ ╚═╝` |
| Completion box (failure) | `log_utils.create_status_box(success=False)` | Orchestrator (after step) | `┌─┐ │ ├─┤ └─┘` |
| Coffee break | `log_utils.create_status_box()` | Orchestrator (between steps) | `╔═╗ ║ ╠═╣ ╚═╝` |
| beautiful_log line | `log_utils.beautiful_log()` | Orchestrator only | None (single line) |
| Progress line | `print()` / `logging.info()` | Strategy | None (single line) |
| Inline warning | `print()` / `logging.warning()` | Strategy | None (single line) |
| **Sub-phase header** | `create_phase_header()` in coordinator (target: `logging.info()`) | Coordinator (OP, FM) | `──` single-dash separator |
| **Sub-phase intro** | `create_progress_box()` in coordinator (target: `logging.info()`) | Coordinator (OP, EI, FM) | None (tree: `├─` `└─`) |
| **Sub-phase completion** | Inline `logging.info()` in coordinator/component | Coordinator + component | None (multi-line text) |
| FM cycle summary | `logging.info()` | FM delegated orchestrator | Multi-line breakdown (KEEP) |
| FM alert display | `logging.info()` (target: was `print()`) | FM delegated orchestrator (via `fm_alerts.py`) | None (blank-line separated, Section 16) |
| FM alert processing summary | `logging.info()` | FM delegated orchestrator (via `fm_alerts.py`) | None (plain text, Section 16) |
| FM internal coffee break | `log_utils.create_status_box()` (target: was `contextual_coffee_break()`) | FM coordinator (post-market) + delegated orchestrator (market hours) | `╔═╗ ║ ╠═╣ ╚═╝` (Section 18) |
| FM session summary | `log_utils.create_status_box(success=True)` | Orchestrator | `╔═╗ ║ ╠═╣ ╚═╝` |
| Day-end summary | `log_utils.create_status_box(success=varies)` | Orchestrator | Double or single |
| Autofix banner | `main_ui.display_autofix_output()` | Orchestrator | `======` raw |

### Output Channels

| Element | Console | Log file |
|---------|---------|----------|
| `create_status_box()` | Yes | Yes (blank lines skipped) |
| `beautiful_log()` | Yes (emoji + timestamp) | Yes (plain message) |
| `phase_header()` | Yes | Yes (blank lines skipped) |
| `print_banner()` | Yes (via `_safe_print`) | **No** |
| Strategy `print()` | Yes | **No** (unless logging used) |
| Strategy `logging.info()` | Yes | Yes |
| Coffee break (current) | Yes (via `_safe_print`) | **No** |
| Coffee break (target) | Yes | Yes (via `create_status_box`) |
| Sub-phase header (current) | Yes (via `print()` / `safe_log()`) | **No** |
| Sub-phase header (target) | Yes | Yes (via `logging.info()`) |
| Sub-phase intro tree (current) | Yes (via `print()` / `safe_log()`) | **No** |
| Sub-phase intro tree (target) | Yes | Yes (via `logging.info()`) |
| Sub-phase completion summary (current) | Yes (via `print()` / `safe_log()`) | **No** |
| Sub-phase completion summary (target) | Yes | Yes (via `logging.info()`) |
| FM alert display (current) | Yes (via `print()`) | **No** |
| FM alert display (target) | Yes | Yes (via `logging.info()`) |
| FM internal coffee break (current) | Yes (via `beautiful_log()`) | **No** |
| FM internal coffee break (target) | Yes | Yes (via `create_status_box()`) |

---

## 15. Sub-Phase Structure (Strategy Coordinators) — CURRENT / TARGET (channel fix)

**The missing layer.** The output architecture defines two layers: orchestrator (boxes, phase headers) and strategy (progress lines). But three strategy coordinators produce a **third layer** of visual structure: sub-phase transitions within multi-step internal pipelines. These elements are already visible in the Full Phase 1 Example below but were never formally defined.

**What changes:** The visual format stays. The **output channel** changes from `print()` / `safe_log()` (console-only) to `logging.info()` (console + log file). No structural or content changes.

### Which Strategies Have Sub-Phases

| Coordinator | Internal Phases | Phase Count | Duration |
|-------------|----------------|:-----------:|----------|
| `op_main.py` | Collection → Rollup → OI Timing → Health Report | 4 | ~40 min |
| `ei_main.py` (daily) | Snapshots → Post-Earnings Calc → Expected Moves | 3 | ~2 min |
| `ei_main.py` (weekly) | Fetch Upcoming → Archive Past → Cleanup Old | 3 | ~30 sec |
| `ei_main.py` (morning) | Arbitrage scan (single step — no sub-phases) | 1 | ~2 sec |
| `fm_main.py` (pre-market) | Alert Resolution → Sentiment Update | 2 | ~10 sec |
| `fm_main.py` (post-market) | Backfill → Regime → Rollup → Evaluation → Cleanup | 5 | ~15 min |
| `fm_main.py` (market hours) | Delegated orchestrator — handled in Section 10 | N/A | ~6.5 hours |

**Note:** FM market hours is a delegated orchestrator (Section 10), not a coordinator. Its cycle output is already defined separately. The sub-phase structure here covers FM pre-market and post-market only.

### 15.1 Sub-Phase Header

**Produced by:** `create_phase_header()` in each coordinator (currently via `safe_log()` → `print()`)
**Target channel:** `logging.info()`
**Format:** `── emoji PHASE_NAME (N/M) ──` with trailing dashes to ~70 chars

The sub-phase header is visually lighter than the orchestrator's `═══` phase header — single dashes `──` vs double `═══`. This is intentional: it signals "internal step within a strategy" at a glance, not "new major phase of the daily cycle."

```
── 📊 DATA COLLECTION (1/4) ──────────────────────────────────────────
```
```
── 📈 SYMBOL ROLLUP (2/4) ───────────────────────────────────────────
```
```
── ⏱️  OI TIMING ANALYSIS (3/4) ─────────────────────────────────────
```
```
── 📋 HEALTH REPORT (4/4) ───────────────────────────────────────────
```

**OP (`op_main.py`)** uses the `(N/M)` counter with total phases calculated dynamically:
```python
create_phase_header("📊 PHASE {}: DATA COLLECTION".format(current_phase), now_eastern(), current_phase, total_phases)
# Output: ── 📊 PHASE 1: DATA COLLECTION (1/4) ──
```

**EI (`ei_main.py`)** uses `[N/M]` inline step labels instead of the formal `create_phase_header()`:
```
📸 [1/3] Collecting IV/price snapshots...
📈 [2/3] Running post-earnings calculations...
🎯 [3/3] Updating expected moves...
```

**FM (`fm_main.py`)** uses `create_phase_header()` for the overall mode header and `create_task_box()` for numbered tasks:
```
── POST-MARKET ANALYSIS ──
Task 1/3: Historical Backfill — Update price data for market analysis
```

### 15.2 Sub-Phase Intro (Tree Diagrams)

**Produced by:** `create_progress_box()` in OP/EI coordinators (currently via `safe_log()` → `print()`)
**Target channel:** `logging.info()`
**Format:** Tree-structured description of what the sub-phase will do

These appear immediately after a sub-phase header, before the first progress line. They tell the user what operations are about to happen.

```
📊 Aggregating contract data to symbol level...
   ├─ Calculating Put/Call ratios
   ├─ Finding concentration strikes
   └─ Generating display summaries
```

```
⏱️  Calculating OI timing (smart money vs retail analysis)...
   ├─ Finding when OI was established (50% threshold)
   ├─ Getting stock prices on build dates
   └─ Updating option_contracts with timing data
```

```
🔍 Starting daily earnings intelligence pipeline...
   ├─ Collect IV/price snapshots for upcoming earnings
   ├─ Calculate post-earnings metrics (T-3 day events)
   └─ Update expected moves with latest IV
```

```
🔄 Starting weekly earnings refresh pipeline...
   ├─ Fetch upcoming earnings (next 90 days)
   ├─ Archive past earnings events
   └─ Cleanup old records
```

**Keep vs cut decision:** These tree diagrams are **useful** — they tell the user exactly what the sub-phase will do before progress lines start. They run once per sub-phase (not per item), so they add 3-4 lines total per sub-phase. **KEEP**, convert to `logging.info()`.

### 15.3 Sub-Phase Completion Summary

**Produced by:** `create_success_celebration()` in coordinators + inline logging in phase methods
**Target channel:** `logging.info()`
**Format:** Varies by coordinator — see evidence below

After a sub-phase finishes, the coordinator emits a summary. There are two patterns in the codebase:

**Pattern A: Inline summary (OP timing phase, OP health report)**
Tree-structured result block, same visual language as the intro:
```
✅ OI timing analysis completed successfully!
   ├─ Total contracts processed: 13,717
   ├─ Timing data added: 13,077
   ├─ Skipped (insufficient data): 640
   └─ Execution time: 8.8 seconds
```

**Pattern B: Block summary (OP collection — from `op_collector.py`)**
Banner-style block with `=` separators and emoji metrics — currently drawn by the component:
```
======================================================================
🎉 COLLECTION COMPLETE
======================================================================
⏱️  Time: 38.0 minutes
📊 Symbols Processed: 746
✅ Successful: 746
❌ Failed: 0
📋 Total Contracts: 106,036
🌐 API Calls: 4366
```

**Pattern C: Block summary (OP rollup — from `op_symbol_rollup.py`)**
`=` separator with stats block:
```
============================================================
OP ROLLUP COMPLETE: 2026-02-18
============================================================
Total symbols: 746
Symbols processed: 746
Symbols with data: 746
Summaries created: 746
Errors encountered: 0
Total processing time: 36.06 seconds
```

**Pattern D: Final celebration (OP — from `op_main.py`)**
End-of-pipeline summary after all sub-phases complete:
```
OPTION PIPELINE complete:
  Total execution time: 38.8 minutes
  Symbols collected: 746
  Total contracts: 106,036
  Symbol summaries created: 746
  OI timing calculated: 13,077 contracts
```

**Pattern E: One-liner (EI sub-tasks)**
Simple confirmation line per task:
```
✅ Fetched 42 earnings for 800 symbols
✅ Archived 12 past earnings events
✅ Cleaned up 8 old records
```

**Keep vs cut decisions:**

| Pattern | Verdict | Reason |
|---------|---------|--------|
| A: Inline tree summary | **KEEP** (convert to `logging.info()`) | Information-dense, compact, useful diagnostic data |
| B: `═══` collection banner | **DELETE** the `═══` borders. **KEEP** the metric lines as plain `logging.info()` | Banner violates "strategies don't draw boxes." The data is useful. |
| C: `═══` rollup banner | **DELETE** the `═══` borders. **KEEP** stats as `logging.info()` | Same reason as B |
| D: Final celebration | **DELETE** | Redundant with orchestrator's completion box (which shows the same data from the return dict) |
| E: One-liner confirmations | **KEEP** (convert to `logging.info()`) | Compact, non-redundant progress output |

### 15.4 Target Sub-Phase Output

After the refactor, sub-phase output follows this pattern. The OP pipeline provides the clearest example:

```
── 📊 DATA COLLECTION (1/4) ──────────────────────────────────────────
📊 Collection Phase Starting
  Universe: 747 symbols
  Start Time: 06:35:03 ET

  [per-symbol progress lines from op_collector.py]
  📊 Progress: 100.0% (747/747) | Success: 100.0% | Contracts: 106,036

⏱️  Time: 38.0 minutes
📊 Symbols Processed: 747
✅ Successful: 747
❌ Failed: 0
📋 Total Contracts: 106,036
🌐 API Calls: 4366

── 📈 SYMBOL ROLLUP (2/4) ───────────────────────────────────────────
📊 Aggregating contract data to symbol level...
   ├─ Calculating Put/Call ratios
   ├─ Finding concentration strikes
   └─ Generating display summaries

  [batch progress lines from op_symbol_rollup.py]

Total symbols: 747
Symbols processed: 747
Summaries created: 747
Total processing time: 36.06 seconds

── ⏱️  OI TIMING ANALYSIS (3/4) ─────────────────────────────────────
⏱️  Calculating OI timing (smart money vs retail analysis)...
   ├─ Finding when OI was established (50% threshold)
   ├─ Getting stock prices on build dates
   └─ Updating option_contracts with timing data

  [batch progress lines from op_timing_calculator.py]

✅ OI timing analysis completed successfully!
   ├─ Total contracts processed: 13,717
   ├─ Timing data added: 13,077
   ├─ Skipped (insufficient data): 640
   └─ Execution time: 8.8 seconds

── 📋 HEALTH REPORT (4/4) ───────────────────────────────────────────
✅ Health report generated in 1.5 seconds
   └─ Report file: logs/option_pipeline_health_2026-02-18.txt
```

**What's different from today:**
- `═══` / `===` / `"=" * N` banner borders removed from component summaries
- The metric lines survive as plain `logging.info()` output
- Final `create_success_celebration("OPTION PIPELINE", ...)` deleted (orchestrator completion box handles it)
- All output goes through `logging.info()` (reaches both console and log file)
- Sub-phase headers via `create_phase_header()` converted from `safe_log()` to `logging.info()`

### 15.5 Function Inventory (Sub-Phase Elements)

Current functions that produce sub-phase elements, per coordinator:

**`op_main.py` (6 functions — all slated for conversion or deletion):**

| Function | What it produces | Current channel | Action |
|----------|-----------------|----------------|--------|
| `safe_log()` | `print()` wrapper with UTF-8 fallback | `print()` | **DELETE** — replace all calls with `logging.info()` |
| `create_phase_header()` | `── emoji PHASE N: NAME (N/M) ──` sub-phase headers | `safe_log()` → `print()` | **KEEP content, DELETE function** — inline as `logging.info("── {} ──".format(...))` |
| `create_progress_box()` | Tree diagram intros (`├─`, `└─`) | `safe_log()` → `print()` | **KEEP content, DELETE function** — inline as `logging.info()` calls |
| `create_success_celebration()` | End-of-pipeline summary lines | `safe_log()` → `print()` | **DELETE** — redundant with orchestrator completion box |
| `create_error_box()` | `"ERROR: message"` single line | `safe_log()` → `print()` | **DELETE** — replace with `logging.error()` |
| `log_pipeline_start()` | Startup info line | `safe_log()` → `print()` | **DELETE** — redundant with orchestrator mission box |

**`ei_main.py` (8 functions — all slated for deletion):**

| Function | What it produces | Current channel | Action |
|----------|-----------------|----------------|--------|
| `safe_log()` | `print()` wrapper | `print()` | **DELETE** — replace with `logging.info()` |
| `colorize()` | ANSI color wrapper | N/A (helper) | **DELETE** |
| `beautiful_log()` | Colored `safe_log()` | `safe_log()` → `print()` | **DELETE** |
| `create_phase_header()` | `── emoji MODE_NAME ──` mode headers | `safe_log()` → `print()` | **DELETE** — redundant with orchestrator mission box |
| `create_progress_box()` | Tree diagram intros | `safe_log()` → `print()` | **DELETE** — tree diagrams in EI are inline `safe_log()` calls, not via this function |
| `create_success_celebration()` | `"MODE complete: accomplishments"` | `safe_log()` → `print()` | **DELETE** — redundant with orchestrator completion box |
| `create_error_box()` | `"ERROR: message"` | `safe_log()` → `print()` | **DELETE** — replace with `logging.error()` |
| `log_pipeline_start()` | Mode startup lines | `safe_log()` → `print()` | **DELETE** — redundant with orchestrator mission box |

**`fm_main.py` (9 functions — all slated for deletion or conversion):**

| Function | What it produces | Current channel | Action |
|----------|-----------------|----------------|--------|
| `get_display_settings()` | Cached config dict | N/A (helper) | **DELETE** — only used by deleted functions |
| `colorize()` | ANSI color wrapper | N/A (helper) | **DELETE** |
| `beautiful_log()` | Colored `safe_log()` | `safe_log()` → `print()` | **DELETE** |
| `create_phase_header()` | `── PHASE_NAME ──` sub-phase headers | `safe_log()` → `print()` | **DELETE** — replace calls with `logging.info()` |
| `create_task_box()` | `"Task N/M: name — purpose"` | `safe_log()` → `print()` | **DELETE** — replace with `logging.info()` |
| `create_error_box()` | `"ERROR: message"` | `safe_log()` → `print()` | **DELETE** — replace with `logging.error()` |
| `create_success_celebration()` | `"pipeline complete: accomplishments"` | `safe_log()` → `print()` | **DELETE** — redundant with orchestrator completion box |
| `create_section_divider()` | `"─" * 60` or titled divider | `beautiful_log()` | **DELETE** |
| `contextual_coffee_break()` | `┌─┐│├└` coffee break box | `beautiful_log()` | **DELETE** — replaced by `coffee_break()` rewrite using `create_status_box()` |

### 15.6 What Sub-Phase Elements Are NOT

To prevent confusion with the two established layers:

- Sub-phase headers are **NOT** orchestrator phase headers. They use `──` (single dash), not `═══` (double). They never appear at the orchestrator level.
- Sub-phase intros are **NOT** strategy progress lines. They describe what's *about to happen*, not what *is happening*. They run once per sub-phase, not per item.
- Sub-phase completion summaries are **NOT** orchestrator completion boxes. They have no `╔═╗` borders. They are plain multi-line text.
- The final `create_success_celebration()` call IS redundant with the orchestrator completion box and gets deleted.

---

## Full Phase Flow Example

How a single phase looks from start to finish — the three-section pattern:

```
════════════════════════════════════════════════════════════
                PHASE 1: PRE-MARKET OPERATIONS
════════════════════════════════════════════════════════════

╔══════════════════════════════════════════════════════════╗
║ 🌅 MORNING OPTION PIPELINE REFRESH                      ║
╠══════════════════════════════════════════════════════════╣
║ Objective: Refresh Option Contract tables with OI data   ║
║ Steps: Collection → Rollup → OI Timing Analysis → Report ║
║ Universe: KLMN 800                                       ║
║ Timing: Completes before Flow Monitor starts at 9:15 AM  ║
╚══════════════════════════════════════════════════════════╝

  Initializing for 747 symbols...
  Progress: 200/747 symbols (26.8%) - ETA: 120s
  Progress: 400/747 symbols (53.5%) - ETA: 80s
  Progress: 600/747 symbols (80.3%) - ETA: 40s
  Progress: 747/747 symbols (100.0%)

╔══════════════════════════════════════════════════════════╗
║ MORNING OPTION PIPELINE COMPLETE                         ║
╠══════════════════════════════════════════════════════════╣
║ Trade Date: 2026-02-18                                   ║
║ Symbols Collected: 747                                   ║
║ Total Contracts: 18,432                                  ║
║ Symbol Summaries: 747                                    ║
║ OI Timing Calculated: 12,891                             ║
║ Duration: 12m 34s                                        ║
╚══════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Time for a quick stretch                                 ║
║ Duration: 60 seconds                                     ║
║ Up Next: Earnings Arbitrage Scanner                      ║
╚══════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════╗
║ Resuming Operations                                      ║
╠══════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                      ║
╚══════════════════════════════════════════════════════════╝
```

That's it. Phase header → mission box → progress → completion box → coffee break. Nothing else.

---

## Full Phase 1 Example — Pre-Market Operations (Soup to Nuts)

Complete faux output for the pre-market phase with all 5 steps, showing transitions, varied output densities, success/failure boxes, and coffee break chaining. This is what a user would see scrolling through the console after Phase 1 finishes.

```
════════════════════════════════════════════════════════════════════════
                      PHASE 1: PRE-MARKET OPERATIONS
════════════════════════════════════════════════════════════════════════

╔══════════════════════════════════════════════════════════════════════╗
║ 🌅 MORNING OPTION PIPELINE REFRESH                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Objective: Refresh Option Contract tables with OI data               ║
║ Steps: Collection → Rollup → OI Timing Analysis → Report             ║
║ Universe: KLMN 800                                                   ║
║ Timing: Completes before Flow Monitor starts at 9:15 AM             ║
╚══════════════════════════════════════════════════════════════════════╝

── 📊 DATA COLLECTION (1/4) ──────────────────────────────────────────
📊 Collection Phase Starting
  Universe: 747 symbols
  Start Time: 06:35:03 ET

2026-02-18 06:35:03 - INFO - Fetching option expirations for A
2026-02-18 06:35:05 - INFO - Fetching option expirations for AAPL
✅ Flushed 640 contracts to storage (A, AAPL)
2026-02-18 06:35:14 - INFO - Fetching option expirations for ABBV
✅ Flushed 213 contracts to storage (ABBV)
2026-02-18 06:35:19 - INFO - Fetching option expirations for ABNB
✅ Flushed 374 contracts to storage (ABNB)
    ... [743 more symbols — per-item, details important] ...
2026-02-18 07:12:53 - INFO - Fetching option expirations for JBLU
2026-02-18 07:12:57 - INFO - Fetching option expirations for ALK
✅ Flushed 113 contracts to storage (ALK, JBLU)
2026-02-18 07:13:00 - INFO - Fetching option expirations for JETS
✅ Flushed 147 contracts to storage (JETS)

📊 COLLECTION COMPLETE
  ⏱️  Time: 38.0 minutes
  📊 Symbols Processed: 747
  ✅ Successful: 747
  ❌ Failed: 0
  📋 Total Contracts: 106,036
  🌐 API Calls: 4,366

── 📈 SYMBOL ROLLUP (2/4) ───────────────────────────────────────────
📊 Aggregating contract data to symbol level...
   ├─ Calculating Put/Call ratios
   ├─ Finding concentration strikes
   └─ Generating display summaries

2026-02-18 07:13:06 - INFO - OP Rollup: Initialized for symbol aggregation with batch size 100
2026-02-18 07:13:30 - INFO -    Progress: 500/747 symbols (67.0%) - batch: 3.57s, ETA: 14.9s
2026-02-18 07:13:41 - INFO -    Progress: 747/747 symbols (100.0%) - batch: 4.07s, ETA: 0.0s
2026-02-18 07:13:42 - INFO - OP Rollup: Successfully created 747 symbol summaries

OP ROLLUP COMPLETE: 2026-02-18
  Total symbols: 747
  Symbols processed: 747
  Symbols with data: 747
  Summaries created: 747
  Errors encountered: 0
  Total processing time: 36.06 seconds

── ⏱️  OI TIMING ANALYSIS (3/4) ─────────────────────────────────────
⏱️  Calculating OI timing (smart money vs retail analysis)...
   ├─ Finding when OI was established (50% threshold)
   ├─ Getting stock prices on build dates
   └─ Updating option_contracts with timing data

Found 13,717 contracts with OI > 1000
  Progress: 1,000/13,717 contracts (947 updated, 53 skipped)
  Progress: 2,000/13,717 contracts (1,915 updated, 85 skipped)
    ... [per 1,000 — contract scale, details not important] ...
  Progress: 13,000/13,717 contracts (12,374 updated, 626 skipped)
  Progress: 13,717/13,717 contracts (13,077 updated, 640 skipped)

✅ OI timing analysis completed successfully!
   ├─ Total contracts processed: 13,717
   ├─ Timing data added: 13,077
   ├─ Skipped (insufficient data): 640
   └─ Execution time: 8.8 seconds

── 📋 HEALTH REPORT (4/4) ───────────────────────────────────────────
2026-02-18 07:13:52 - INFO - ✅ Health report generated in 1.5 seconds
2026-02-18 07:13:52 - INFO -    └─ Report file: logs/option_pipeline_health_2026-02-18.txt

╔══════════════════════════════════════════════════════════════════════╗
║ MORNING OPTION PIPELINE COMPLETE                                     ║
╠══════════════════════════════════════════════════════════════════════╣
║ Trade Date: 2026-02-18                                               ║
║ Symbols Collected: 747                                               ║
║ Total Contracts: 106,036                                             ║
║ Symbol Summaries: 747                                                ║
║ OI Timing Calculated: 13,077 contracts                               ║
║ Duration: 38.8 minutes                                               ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ Time for a quick stretch                                             ║
║ Duration: 60 seconds                                                 ║
║ Press Ctrl+C to safely stop Option Scanner system.                   ║
║ Up Next: Earnings Arbitrage Scanner                                  ║
╚══════════════════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════════════════╗
║ Resuming Operations                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                                  ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ 🎯 EARNINGS ARBITRAGE SCANNER                                       ║
╠══════════════════════════════════════════════════════════════════════╣
║ Mission: Find pre-market sector sympathy opportunities               ║
║ Analysis: Today's earnings with cheap peer IV                        ║
║ Criteria: Historical correlation + IV discount                       ║
║ Output: High-quality arbitrage plays flagged                         ║
╚══════════════════════════════════════════════════════════════════════╝

2026-02-18 06:50:14 - INFO - Scanning 3 earnings events for today
2026-02-18 06:50:14 - INFO - WMT: 12 peers, 4 with IV discount > 15%
2026-02-18 06:50:15 - INFO - HD: 8 peers, 2 with IV discount > 15%
2026-02-18 06:50:15 - INFO - BABA: 6 peers, 0 opportunities (IV already elevated)

╔══════════════════════════════════════════════════════════════════════╗
║ ARBITRAGE SCANNER COMPLETE                                           ║
╠══════════════════════════════════════════════════════════════════════╣
║ Scan Date: 2026-02-18                                                ║
║ Earnings Today: 3                                                    ║
║ Opportunities Found: 6                                               ║
║ High Quality: 2  |  Medium: 3  |  Low: 1                            ║
║ Duration: 1.8s                                                       ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ Quick coffee break                                                   ║
║ Duration: 60 seconds                                                 ║
║ Press Ctrl+C to safely stop Option Scanner system.                   ║
║ Up Next: Metadata Collection                                         ║
╚══════════════════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════════════════╗
║ Resuming Operations                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                                  ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ 🏢 SYMBOL METADATA COLLECTION                                       ║
╠══════════════════════════════════════════════════════════════════════╣
║ Mission: Refresh company sector, industry, market cap, beta          ║
║ Quota: ALL ~750 symbols per run (~60 seconds)                        ║
║ Beta: 60-day covariance calculation with SPY                         ║
║ Dependencies: historical_prices for beta calculation                 ║
║ Source: Tradier Fundamentals + Quotes API                            ║
╚══════════════════════════════════════════════════════════════════════╝

    [subprocess output — metadata script runs independently]
    [orchestrator streams stdout but has no per-item visibility]

╔══════════════════════════════════════════════════════════════════════╗
║ METADATA COLLECTION COMPLETE                                         ║
╠══════════════════════════════════════════════════════════════════════╣
║ Status: ✅ Completed successfully                                    ║
║ Duration: 58s                                                        ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ Morning cuppa to go with the news                                    ║
║ Duration: 60 seconds                                                 ║
║ Press Ctrl+C to safely stop Option Scanner system.                   ║
║ Up Next: Query Database Sync (Morning)                               ║
╚══════════════════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════════════════╗
║ Resuming Operations                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                                  ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ 🔄 QUERY DATABASE SYNC                                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ Mission: Sync query database from primary datalake.db                ║
║ Target: datalake_query.db (read-only for analysis)                   ║
║ Purpose: Prevent database locking during analysis operations         ║
║ Schedule: After Morning and Evening Option Pipelines                 ║
╚══════════════════════════════════════════════════════════════════════╝

    [subprocess streams backup progress]
    Syncing: 30,000/98,412 pages...
    Syncing: 60,000/98,412 pages...
    Syncing: 90,000/98,412 pages...
    Syncing: 98,412/98,412 pages — complete

╔══════════════════════════════════════════════════════════════════════╗
║ QUERY SYNC COMPLETE                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Query database: datalake_query.db                                    ║
║ Status: 98,412 pages synced in 42.3s                                 ║
║ Duration: 42s                                                        ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ Lock release before Morning Views                                    ║
║ Duration: 60 seconds                                                 ║
║ Press Ctrl+C to safely stop Option Scanner system.                   ║
║ Up Next: Morning Views                                               ║
╚══════════════════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════════════════╗
║ Resuming Operations                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                                  ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ 📊 MORNING VIEWS GENERATION                                         ║
╠══════════════════════════════════════════════════════════════════════╣
║ Mission: Generate and email daily options watchlist                   ║
║ Source: datalake_query.db (fresh from sync)                          ║
║ Views: Creates 4 SQL views with hybrid data                          ║
║ Data: TODAY's OI + YESTERDAY's volume/greeks/price                   ║
║ Output: Markdown log + .docx email attachment                        ║
╚══════════════════════════════════════════════════════════════════════╝

    [subprocess runs morning_views.py — orchestrator streams output]

╔══════════════════════════════════════════════════════════════════════╗
║ MORNING VIEWS COMPLETE                                               ║
╠══════════════════════════════════════════════════════════════════════╣
║ Status: ✅ Completed successfully                                    ║
║ Duration: 22s                                                        ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ Stretch before the main event                                        ║
║ Duration: 60 seconds                                                 ║
║ Press Ctrl+C to safely stop Option Scanner system.                   ║
║ Up Next: Flow Monitor                                                ║
╚══════════════════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════════════════╗
║ Resuming Operations                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                                  ║
╚══════════════════════════════════════════════════════════════════════╝
```

### What this demonstrates

| Concept | Where it appears |
|---------|-----------------|
| **Phase header** | Top: `═══ PHASE 1: PRE-MARKET ═══` |
| **Mission box** | Before each of the 5 steps — double borders, step-specific content |
| **Sub-phase headers** (Section 15.1) | Inside OP pipeline: `── 📊 DATA COLLECTION (1/4) ──` separating internal steps |
| **Sub-phase intro** (Section 15.2) | Tree diagrams describing what the sub-phase does (`├─ Calculating...`) |
| **Sub-phase summary** (Section 15.3) | After each sub-phase completes: stats block with timing, counts, results |
| **Per-item progress** (details important) | OP collection: one line per symbol (747 lines) |
| **Batch progress** (details not important) | OP rollup: per 100, OI timing: per 1,000 |
| **Tiny-set progress** (details important) | Arbitrage scanner: per-item with specifics (WMT, HD, BABA) |
| **Subprocess progress** | Metadata + Query Sync: limited visibility, stream what's available |
| **Rich completion box** (dict return) | OP and Arbitrage: multiple data lines from return dict |
| **Lean completion box** (subprocess) | Metadata and Morning Views: status + duration only |
| **Coffee break with "Up Next"** | Between every step, chaining through STEP_SEQUENCE |
| **Resuming box** | After every coffee break |
| **Consistent rhythm** | Every step follows: mission → progress → completion → coffee → resume |

### What's NOT shown here (but would appear in real output)

- **Failure box** (single-line borders `┌─┐`): If any step fails, the completion box switches to single borders with error details. The coffee break still appears — the system continues to the next step.
- **Skip box**: If a step is skipped (e.g., arbitrage scanner finds 0 earnings today), a single-border box appears with the skip reason.
- **Inline warnings**: `logging.warning()` lines for data quality issues would appear in the progress section.
- **Startup banner**: Appears once before Phase 1, not repeated.

---

## 16. FM Alert Display Block — CURRENT / TARGET (border removal)

**Produced by:** `fm_alerts.py` → `_send_notifications()` → `_display_alerts_to_console()` and `_log_alert_summary()`
**When:** After each market hours cycle, if alerts passed filters
**Current rendering:** `print()` with `"="*80` borders and `"-"*50` category separators
**Target rendering:** `logging.info()` with no decorative borders — content and structure preserved

### Current (`_display_alerts_to_console()` and `_log_alert_summary()` in fm_alerts.py)

```
================================================================================
🚨 FLOW MONITOR ALERTS - 15:50:29
================================================================================

🔴 HIGH CONVICTION ALERTS (Score 5.0+)
--------------------------------------------------
NVDA [LAR] $142.0 calls (17d) | Vol: 8,200 (6.2x) | OI: 12,450 | V/OI: 0.7 | ...

🟡 MEDIUM ALERTS (Score 3.5-4.9)
----------------------------------------
XPO [LAR] $210.0 calls (31d) | Vol: 4,021 (4.0x) | OI: 6,836 | V/OI: 0.6 | ...

📊 SUMMARY: 2 alerts sent (1 HIGH, 1 MEDIUM, 0 LOW)
================================================================================
```

```
==================================================
ALERT PROCESSING SUMMARY
==================================================
Candidates found: 4
Filters applied: 1 ETFs, 2 delta
Alerts sent: 1
Console notifications: 1
Email notifications: 0
Database saves: 1 successful, 0 failed
==================================================
```

### Target (after Package 6 Step 9)

The `=*80` and `-*50` borders are removed. The category headers, per-alert detail lines, summary line, and processing summary all stay as plain `logging.info()` output. The emojis in category headers (🔴, 🟡, ⚪) provide sufficient visual distinction without decorative borders.

```
2026-02-18 15:50:29 - INFO -
2026-02-18 15:50:29 - INFO - 🚨 FLOW MONITOR ALERTS - 15:50:29
2026-02-18 15:50:29 - INFO -
2026-02-18 15:50:29 - INFO - 🔴 HIGH CONVICTION ALERTS (Score 5.0+)
2026-02-18 15:50:29 - INFO - NVDA [LAR] $142.0 calls (17d) | Vol: 8,200 (6.2x) | OI: 12,450 | V/OI: 0.7 | ...
2026-02-18 15:50:29 - INFO -
2026-02-18 15:50:29 - INFO - 🟡 MEDIUM ALERTS (Score 3.5-4.9)
2026-02-18 15:50:29 - INFO - XPO [LAR] $210.0 calls (31d) | Vol: 4,021 (4.0x) | OI: 6,836 | V/OI: 0.6 | ...
2026-02-18 15:50:29 - INFO -
2026-02-18 15:50:29 - INFO - 📊 SUMMARY: 2 alerts sent (1 HIGH, 1 MEDIUM, 0 LOW)
```

```
2026-02-18 15:50:29 - INFO -
2026-02-18 15:50:29 - INFO - ALERT PROCESSING SUMMARY
2026-02-18 15:50:29 - INFO - Candidates found: 4
2026-02-18 15:50:29 - INFO - Filters applied: 1 ETFs, 2 delta
2026-02-18 15:50:29 - INFO - Alerts sent: 1
2026-02-18 15:50:29 - INFO - Console notifications: 1
2026-02-18 15:50:29 - INFO - Email notifications: 0
2026-02-18 15:50:29 - INFO - Database saves: 1 successful, 0 failed
```

**Design decision:** Blank lines between category blocks replace the `-*N` separators. The emoji category headers (`🔴`, `🟡`, `⚪`) are strong enough visual anchors to separate groups without decorative lines. The alert content is the product of FM — it must be readable, not decorative.

**Alternative considered and rejected:** Using `──` single-dash separators (like sub-phase headers) was considered but rejected because alerts are data output, not structural transitions. The blank-line approach matches how `logging.info()` normally works.

**Note:** If Ben prefers the borders to stay (since alerts are THE product and visual prominence matters during 6.5 hours of monitoring), this is the easiest item to reverse — just keep the `print()` calls with `"="*80` as-is. **Ask Ben** before implementing if uncertain.

---

## 17. FM Market Hours beautiful_log Cross-Check — Reference (Package 6 Step 7 alignment)

**Purpose:** Map every `beautiful_log()` call in `run_market_hours()` to a keep/cut decision. Cross-reference against Section 10 approved target and Package 6 Step 7. Search by content pattern to find each call.

### Full Call Inventory

| Content (search pattern) | Category | Section 10 | Package 6 Step 7 | Verdict |
|--------------------------|----------|-----------|-------------------|---------|
| `create_phase_header("MARKET HOURS MONITORING", now)` | Startup | Not shown | Step 1: DELETE | **DELETE** — redundant with orchestrator mission box |
| `"📈 INITIATING MARKET HOURS PIPELINE"` | Startup | Not shown | DELETE | **DELETE** |
| `"Real-time monitoring: N symbols per cycle"` | Startup | Not shown | DELETE | **DELETE** |
| `"🔔 Market closed. Ending market hours pipeline."` | Exit signal | Not explicit | — | **KEEP as `logging.info()`** — natural exit signal, not redundant |
| `"=== Cycle N \| time \| symbols ==="` | Cycle header | **Shown** in approved output | "DELETE (completion line suffices)" | **⚠️ DISCREPANCY** — see below |
| `"🔍 Collection complete: {timestamp} ({time}s)"` | Collection | **Shown** in approved output | "DELETE redundant" | **KEEP** — Section 10 explicitly says "keep the emoji-prefixed one with timing" |
| `"⚠️ Collection failed - skipping analysis"` | Error | N/A | "KEEP as logging.warning()" | **KEEP as `logging.warning()`** |
| `"❌ Market cycle error: {e}"` | Error | N/A | "KEEP as logging.error()" | **KEEP as `logging.error()`** |
| `"✅ Cycle N complete - Performance Breakdown:"` | Perf header | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"   📊 Collection: {time}s"` | Perf line | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"   🔍 Analysis: {time}s"` | Perf line | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"   🚨 Alerts: {time}s"` | Perf line | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"   🎯 Watchlist: {time}s"` | Perf line | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"   🔄 DB Sync: {time}s ({rows} rows)"` | Perf line | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"   ⏱️ Total: {time}s"` | Perf line | **Shown** | "KEEP" | **KEEP as `logging.info()`** |
| `"📈 PERFORMANCE SUMMARY (Last N cycles):"` | 10-cycle | Not shown in Section 10 | "KEEP" | **KEEP as `logging.info()`** |
| Average/slowest/fastest stats (6 lines after PERFORMANCE SUMMARY) | 10-cycle | Not shown | "KEEP" | **KEEP as `logging.info()`** |
| `"📊 {line}"` (end-of-day lines loop from `format_end_of_day_lines()`) | EOD summary | Covered in Section 11 | "KEEP" | **KEEP as `logging.info()`** |
| `"Saved to {filename}"` (symbol gaps JSON) | Gaps file | Not shown | — | **KEEP as `logging.info()`** — diagnostic |
| `"🏁 MARKET HOURS PIPELINE COMPLETE"` | Completion | Not shown | "DELETE" | **DELETE** — orchestrator handles completion |

### Discrepancy: Cycle Header Line

**Section 10** shows the cycle header in its approved target:
```
=== Cycle 16 | 15:53:15 | 746 symbols ===
```

**Package 6 Step 7** says:
> `"Cycle N starting..."` announcements — **DELETE** (the completion line suffices)

**Analysis:** The cycle header (`=== Cycle N ===`) serves as a visual separator between cycles during 6.5 hours of continuous output. Without it, one cycle's performance breakdown bleeds directly into the next cycle's collection lines with no visual break. The coffee break box (between cycles) partially fills this role, but the cycle header also carries useful context (cycle number, time, symbol count).

**Recommendation:** **KEEP** the cycle header. Convert from `beautiful_log()` to `logging.info()`. Remove the `===` wrapper characters — use a plain format like:

```
2026-02-18 15:53:15 - INFO - Cycle 16 | 15:53:15 | 746 symbols
```

Or keep the `===` since they provide quick visual grep-ability in long logs. **Ask Ben** which style he prefers.

**Resolution needed:** Update Package 6 Step 7 to say "KEEP — convert to `logging.info()`" for the cycle header, aligning with Section 10. Or remove it from Section 10 if Ben agrees it's redundant.

### Summary

- **24 `beautiful_log()` call sites** in `run_market_hours()` (some conditional, EOD lines loop runs multiple times)
- **3 DELETE:** Startup banner (2 lines), completion announcement
- **1 DELETE:** Phase header (via `create_phase_header()`)
- **18 KEEP** (convert to `logging.info()` / `logging.warning()` / `logging.error()`)
- **1 DISCREPANCY:** Cycle header — Section 10 keeps, Package 6 deletes
- **1 UNLISTED:** Market close signal — not in either doc, recommend KEEP

---

## 18. FM Coffee Break (Internal) — TARGET

**Produced by:** `fm_main.py` → `coffee_break()` (module-level, NOT the orchestrator's `self.coffee_break()`)
**When:** Between FM post-market tasks and between market hours cycles
**Current rendering:** `contextual_coffee_break()` draws a `┌─┐│├└` box via `beautiful_log()`
**Target rendering:** `create_status_box()` from `log_utils.py` — standard double-line box

### Current (`contextual_coffee_break()` and `coffee_break()` in fm_main.py)

```
┌───────────────────────────────────────────────────────────┐
│ ☕ Coffee Break - 60 seconds                               │
├───────────────────────────────────────────────────────────┤
│ Data refreshed — all symbols have current pricing          │
│ Up Next: Market Regime Summary                             │
└───────────────────────────────────────────────────────────┘
```

Followed by `☕ Resuming operations` as a bare text line.

### Target (after Package 6 Step 2)

```
╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Data refreshed — all symbols have current pricing        ║
║ Duration: 60 seconds                                     ║
║ Up Next: Market Regime Summary                           ║
╚══════════════════════════════════════════════════════════╝
```

No resuming box (unlike the orchestrator's coffee break which has an explicit "Resuming Operations" box). FM's coffee break just pauses and continues — the next task announcement serves as the resumption signal.

### Context-Aware Messages

FM's `coffee_break()` uses a `context` parameter to select situation-specific messages:

| Context Key | Message | Used After |
|-------------|---------|-----------|
| `backfill_complete` | "Data refreshed — all symbols have current pricing" | Historical backfill (post-market task 1) |
| `backfill_partial` | "Data partially refreshed — some symbols failed" | Backfill with partial failures |
| `rollup_complete` | "Symbol analysis complete — daily metrics calculated" | Symbol rollup (post-market task 3) |
| `pre_evaluation` | "Running performance evaluation" | Before evaluation |
| `task_complete` | "Task complete" | Generic task completion |
| `tasks_complete` | "All daily tasks completed successfully" | All post-market tasks done |
| `pipeline_transition` | "Pipeline complete — preparing for next phase" | Between major phases |
| `sync_complete` | "Query DB synced" | After quick-sync during market hours |
| `default` | "Quick coffee break" | Fallback |

### Differences from Orchestrator's coffee_break()

| Aspect | Orchestrator (`main_ui.py`) | FM Internal (`fm_main.py`) |
|--------|---------------------------|---------------------------|
| Scope | Between top-level steps | Between FM sub-tasks |
| "Up Next" source | `STEP_SEQUENCE` constant | `next_task` parameter (explicit) |
| Resuming box | Yes | No |
| Sleep | `time.sleep()` (non-interruptible) | Interruptible via `shutdown_event` (5-second checks) |
| Ctrl+C handling | Caught by orchestrator | Graceful shutdown via `shutdown_event.set()` |

**Design note:** FM's interruptible sleep is critical for graceful shutdown. The orchestrator can afford a simple `time.sleep()` because it checks for interrupts between steps. FM needs to check `shutdown_event` during sleep because a coffee break in market hours could be the user's window to stop the system cleanly.

---

## Full Phase 2 Example — Flow Monitor Daily Cycle (Soup to Nuts)

Complete faux output for the Flow Monitor phase showing the orchestrator mission box, FM pre-market preparation, market hours (first cycle → mid-day cycle → last cycle → market close), session summary, and post-market tasks with coffee breaks. This is the Phase 2 equivalent of the Phase 1 example above.

**Key difference from Phase 1:** Phase 2 has ONE orchestrator-level mission/completion box pair wrapping the entire FM daily cycle. Inside that wrapper, FM operates as three distinct sub-phases: pre-market (coordinator), market hours (delegated orchestrator), and post-market (coordinator). The orchestrator does not draw per-sub-phase boxes — FM's internal output fills the gap.

### Pre-Market + Market Hours Startup

```
════════════════════════════════════════════════════════════════════════
                      PHASE 2: FLOW MONITOR
════════════════════════════════════════════════════════════════════════

╔══════════════════════════════════════════════════════════════════════╗
║ 📈 FLOW MONITOR PIPELINE                                            ║
╠══════════════════════════════════════════════════════════════════════╣
║ Mission: Complete daily options flow monitoring cycle                 ║
║ Pre-Market: System preparation and setup (9:15 AM)                  ║
║ Market Hours: Real-time flow monitoring (9:30 AM - 4:00 PM)        ║
║ Post-Market (4:30 PM):                                               ║
║   1. Historical backfill    3. Symbol rollup                         ║
║   2. Market regime summary  4. Evaluation + cleanup                  ║
╚══════════════════════════════════════════════════════════════════════╝

ℹ️ 09:10:00 - Waiting until 9:15 AM for pre-market preparation (5.0 minutes)
```

### FM Pre-Market (Coordinator Output)

After the wait expires, FM's pre-market sub-phase runs. Post-refactor, `run_pre_market()` produces compact progress lines (no phase headers, no celebrations). The orchestrator does not draw a separate mission box for pre-market — it's inside the single FM wrapper.

```
2026-02-18 09:15:01 - INFO - 🔍 Resolving Yesterday's Flow Alerts
2026-02-18 09:15:01 - INFO -    Using fresh OI data from morning Option Pipeline
2026-02-18 09:15:03 - INFO -    ✅ Resolved 8 alerts (3 BUILDING, 4 CLOSING, 1 NEUTRAL)
2026-02-18 09:15:03 - WARNING -    ⚠️ 2 contracts not found in today's OI data
2026-02-18 09:15:04 - INFO -    ✅ Resolution data synced to query database
2026-02-18 09:15:05 - INFO -    ✅ Updated sentiment for 5 watchlist symbols
```

No celebration block at the end — the orchestrator doesn't draw a completion box for pre-market specifically. The data flows into the overall FM return dict.

### Transition to Market Hours

```
ℹ️ 09:15:06 - Waiting until 9:30 AM for market open collector/analyzer (14.9 minutes)
```

### Market Hours — First Cycle

The first cycle starts at market open. FM is now operating as a **delegated orchestrator** — it produces its own per-cycle operational output.

```
2026-02-18 09:30:01 - INFO - Cycle 1 | 09:30:01 | 746 symbols

[per-symbol collection lines — 746 lines, one per symbol from fm_collector.py]
2026-02-18 09:50:03 - WARNING - ⚠️ API returned 42 duplicate contracts in batch (symbols: SPY, QQQ)
2026-02-18 09:50:03 - WARNING - ⚠️ Deduplicated 42 duplicate contracts from API response before DB insert
2026-02-18 09:50:05 - INFO - Stored 103,847 option contracts with scan_timestamp: 2026-02-18 09:30:01

2026-02-18 09:50:06 - INFO - 🔍 Collection complete: 2026-02-18 09:30:01 (1202.4s)
2026-02-18 09:50:06 - INFO - Starting unified algorithm analysis for scan: 2026-02-18 09:30:01 (live production mode)
2026-02-18 09:50:08 - INFO - Retrieved 103847 contracts for unified analysis
2026-02-18 09:50:09 - INFO - Market regime: normal

2026-02-18 09:50:28 - INFO - UNIFIED ALGORITHM ANALYSIS SUMMARY
2026-02-18 09:50:28 - INFO - Contracts processed: 103847
2026-02-18 09:50:28 - INFO - Contracts updated: 103847
2026-02-18 09:50:28 - INFO - Enhanced statistics tracking:
2026-02-18 09:50:28 - INFO -   Early day fallbacks: 746
2026-02-18 09:50:28 - INFO -   Running total used: 0
2026-02-18 09:50:28 - INFO -   Missing baselines: 103847
2026-02-18 09:50:28 - INFO - Premium filtered: 99812
2026-02-18 09:50:28 - INFO - Volume filtered: 103820
2026-02-18 09:50:28 - INFO - High conviction alerts (8.0+): 3
2026-02-18 09:50:28 - INFO - Unified alerts (6.0+): 11
2026-02-18 09:50:28 - INFO - Total analysis time: 22.14 seconds
2026-02-18 09:50:28 - INFO - Total significant flows detected: 14

2026-02-18 09:50:29 - INFO - Processing alerts for scan: 2026-02-18 09:30:01

2026-02-18 09:50:29 - INFO -
2026-02-18 09:50:29 - INFO - 🚨 FLOW MONITOR ALERTS - 09:50:29
2026-02-18 09:50:29 - INFO -
2026-02-18 09:50:29 - INFO - 🔴 HIGH CONVICTION ALERTS (Score 8.0+)
2026-02-18 09:50:29 - INFO - NVDA [LAR] $142.0 calls (17d) | Vol: 8,200 (6.2x) | OI: 12,450 | V/OI: 0.7 | ...
2026-02-18 09:50:29 - INFO - AAPL [LAR] $235.0 puts (10d) | Vol: 5,100 (3.8x) | OI: 9,200 | V/OI: 0.6 | ...
2026-02-18 09:50:29 - INFO - AMZN [LAR] $210.0 calls (24d) | Vol: 4,800 (4.1x) | OI: 7,300 | V/OI: 0.7 | ...
2026-02-18 09:50:29 - INFO -
2026-02-18 09:50:29 - INFO - 📊 SUMMARY: 3 alerts sent (3 HIGH, 0 MEDIUM, 0 LOW)

2026-02-18 09:50:29 - INFO - Saving 3 alerts to flow_alerts table
2026-02-18 09:50:30 - INFO - Complete alert saved for NVDA 142.0 with score 9.12
2026-02-18 09:50:30 - INFO - Complete alert saved for AAPL 235.0 with score 8.74
2026-02-18 09:50:30 - INFO - Complete alert saved for AMZN 210.0 with score 8.31
2026-02-18 09:50:30 - INFO - Alert persistence complete: 3 saved, 0 failures

2026-02-18 09:50:30 - INFO -
2026-02-18 09:50:30 - INFO - ALERT PROCESSING SUMMARY
2026-02-18 09:50:30 - INFO - Candidates found: 14
2026-02-18 09:50:30 - INFO - Filters applied: 1 ETFs, 2 delta
2026-02-18 09:50:30 - INFO - Alerts sent: 3
2026-02-18 09:50:30 - INFO - Console notifications: 3
2026-02-18 09:50:30 - INFO - Email notifications: 1
2026-02-18 09:50:30 - INFO - Database saves: 3 successful, 0 failed

2026-02-18 09:50:32 - INFO - Watchlist updated: 3 created, 0 updated from 3 alerts
2026-02-18 09:50:34 - INFO - News enrichment: 2 enriched, 1 skipped, 0 failed

2026-02-18 09:50:35 - INFO - 🔄 Starting database quick-sync...
2026-02-18 09:52:14 - INFO - ✅ Quick-sync completed: 103,847 rows in 99.2s

2026-02-18 09:52:14 - INFO - ✅ Cycle 1 complete - Performance Breakdown:
2026-02-18 09:52:14 - INFO -    📊 Collection: 1202.4s
2026-02-18 09:52:14 - INFO -    🔍 Analysis: 22.1s
2026-02-18 09:52:14 - INFO -    🚨 Alerts: 1.4s
2026-02-18 09:52:14 - INFO -    🎯 Watchlist: 5.8s
2026-02-18 09:52:14 - INFO -    🔄 DB Sync: 99.2s (103,847 rows)
2026-02-18 09:52:14 - INFO -    ⏱️ Total: 1330.8s

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Query DB synced                                          ║
║ Duration: 60 seconds                                     ║
╚══════════════════════════════════════════════════════════╝
```

### Market Hours — Mid-Day Cycle (Cycle 10, with 10-cycle summary)

```
2026-02-18 13:25:01 - INFO - Cycle 10 | 13:25:01 | 746 symbols

[per-symbol collection lines]
2026-02-18 13:45:05 - INFO - Stored 104,287 option contracts with scan_timestamp: 2026-02-18 13:25:01

2026-02-18 13:45:06 - INFO - 🔍 Collection complete: 2026-02-18 13:25:01 (1204.1s)
2026-02-18 13:45:06 - INFO - Starting unified algorithm analysis for scan: 2026-02-18 13:25:01 (live production mode)
2026-02-18 13:45:08 - INFO - Retrieved 104287 contracts for unified analysis
2026-02-18 13:45:09 - INFO - Market regime: elevated

2026-02-18 13:45:28 - INFO - UNIFIED ALGORITHM ANALYSIS SUMMARY
2026-02-18 13:45:28 - INFO - Contracts processed: 104287
2026-02-18 13:45:28 - INFO - Contracts updated: 104287
    ... [statistics tracking, data quality, filter counts, conviction tiers] ...
2026-02-18 13:45:28 - INFO - Total analysis time: 22.24 seconds
2026-02-18 13:45:28 - INFO - Total significant flows detected: 26

2026-02-18 13:45:29 - INFO - Processing alerts for scan: 2026-02-18 13:25:01
2026-02-18 13:45:29 - INFO - No alert candidates found for scan

2026-02-18 13:45:30 - INFO - 🔄 Starting database quick-sync...
2026-02-18 13:47:08 - INFO - ✅ Quick-sync completed: 104,416 rows in 98.1s

2026-02-18 13:47:08 - INFO - ✅ Cycle 10 complete - Performance Breakdown:
2026-02-18 13:47:08 - INFO -    📊 Collection: 1204.1s
2026-02-18 13:47:08 - INFO -    🔍 Analysis: 22.2s
2026-02-18 13:47:08 - INFO -    🚨 Alerts: 1.1s
2026-02-18 13:47:08 - INFO -    🔄 DB Sync: 98.1s (104,416 rows)
2026-02-18 13:47:08 - INFO -    ⏱️ Total: 1325.5s

2026-02-18 13:47:08 - INFO - 📈 PERFORMANCE SUMMARY (Last 10 cycles):
2026-02-18 13:47:08 - INFO -    Average cycle time: 1338.2s
2026-02-18 13:47:08 - INFO -    Average collection: 1210.4s
2026-02-18 13:47:08 - INFO -    Average analysis: 22.1s
2026-02-18 13:47:08 - INFO -    Average alerts: 1.3s
2026-02-18 13:47:08 - INFO -    Slowest cycle: 1412.0s
2026-02-18 13:47:08 - INFO -    Fastest cycle: 1280.3s

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Query DB synced                                          ║
║ Duration: 60 seconds                                     ║
╚══════════════════════════════════════════════════════════╝
```

### Market Hours — Last Cycle + Market Close

```
2026-02-18 15:48:01 - INFO - Cycle 20 | 15:48:01 | 746 symbols

[per-symbol collection lines]
2026-02-18 16:00:03 - INFO - Stored 104,102 option contracts with scan_timestamp: 2026-02-18 15:48:01

2026-02-18 16:00:04 - INFO - 🔍 Collection complete: 2026-02-18 15:48:01 (720.2s)
    ... [analysis, alerts, watchlist, sync — same structure as prior cycles] ...

2026-02-18 16:02:30 - INFO - ✅ Cycle 20 complete - Performance Breakdown:
2026-02-18 16:02:30 - INFO -    📊 Collection: 720.2s
2026-02-18 16:02:30 - INFO -    🔍 Analysis: 21.8s
2026-02-18 16:02:30 - INFO -    🚨 Alerts: 1.2s
2026-02-18 16:02:30 - INFO -    🎯 Watchlist: 5.1s
2026-02-18 16:02:30 - INFO -    🔄 DB Sync: 97.8s (104,102 rows)
2026-02-18 16:02:30 - INFO -    ⏱️ Total: 846.1s

2026-02-18 16:02:30 - INFO - 📈 PERFORMANCE SUMMARY (Last 20 cycles):
2026-02-18 16:02:30 - INFO -    Average cycle time: 1320.4s
    ... [average stats] ...

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Query DB synced                                          ║
║ Duration: 60 seconds                                     ║
╚══════════════════════════════════════════════════════════╝

                    ... market closes during coffee break ...

2026-02-18 16:03:31 - INFO - 🔔 Market closed. Ending market hours pipeline.
```

### End-of-Day Summary Lines + Session Summary Box

After market hours exits, FM emits its end-of-day summary lines, then the orchestrator builds the session summary box.

```
2026-02-18 16:03:32 - INFO - 📊 Missing Quotes Summary (3 symbols across 20 cycles):
2026-02-18 16:03:32 - INFO -    Every cycle (3): VIXW, SPX, VIX
2026-02-18 16:03:32 - INFO -
2026-02-18 16:03:32 - INFO - 📊 Failed Options Summary (2 symbols across 20 cycles):
2026-02-18 16:03:32 - INFO -    Every cycle (1): WOLF
2026-02-18 16:03:32 - INFO -    Intermittent:
2026-02-18 16:03:32 - INFO -      BDX - 14/20 cycles
2026-02-18 16:03:32 - INFO -
2026-02-18 16:03:32 - INFO - 📊 Collection Errors: 14 total (8 timeout, 4 connection, 2 other)
2026-02-18 16:03:32 - INFO -    Recurring error symbols: WOLF (x20), BDX (x14)
2026-02-18 16:03:32 - INFO -    Saved to symbol_gaps_2026-02-18.json

ℹ️ 16:03:32 - News sentiment: 12 symbols enriched across 20 cycles

╔══════════════════════════════════════════════════════════════════════╗
║ MARKET HOURS SESSION SUMMARY                                        ║
╠══════════════════════════════════════════════════════════════════════╣
║ Cycles: 20 (19 successful, 1 failed)                                ║
║ Avg cycle: 1320.4s | Fastest: 846.1s | Slowest: 1412.0s            ║
║                                                                      ║
║ Collection Errors: 14 total (8 timeout, 4 connection, 2 other)      ║
║ Missing Quotes: 3 symbols (every cycle: VIXW, SPX, VIX)            ║
║ Failed Options: 2 symbols                                            ║
║                                                                      ║
║ News sentiment: 12 enriched, 3 skipped, 1 failed                    ║
╚══════════════════════════════════════════════════════════════════════╝
```

### Transition to Post-Market

```
ℹ️ 16:03:33 - Waiting until 4:30 PM for post-market analysis (26.5 minutes)
```

### FM Post-Market (Coordinator Output — 5 Tasks)

Post-refactor, `run_post_market()` produces compact per-task progress lines with coffee breaks between tasks. No phase headers, no `create_success_celebration()`, no DB diagnostic queries (metrics come from return dicts after Package 5). The orchestrator does not draw per-task boxes — FM's internal output provides the structure.

**Task 1: Historical Backfill** (subprocess — output streamed)

```
2026-02-18 16:30:01 - INFO - 💾 Running historical data backfill first...

    [streamed subprocess output from tradier_historical_backfill]
    Fetching AAPL... ✅ (252 rows)
    Fetching NVDA... ✅ (252 rows)
    ... [746 symbols] ...
    Symbols with data: 744/746 (99.7%)

2026-02-18 16:42:15 - INFO - ✅ Historical backfill completed successfully
2026-02-18 16:42:15 - INFO -    All symbols updated with current pricing

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Data refreshed — all symbols have current pricing        ║
║ Duration: 60 seconds                                     ║
║ Up Next: Market Regime Summary                           ║
╚══════════════════════════════════════════════════════════╝
```

**Task 2: Market Regime Summary** (subprocess)

```
2026-02-18 16:43:20 - INFO - 📊 Running evening market regime summary...

    [streamed subprocess output from market_daily_summary]

2026-02-18 16:44:02 - INFO - ✅ Market regime summary completed
2026-02-18 16:44:02 - INFO -    Market Regime: elevated | Bull | SPY +0.52% | VIX 18.3

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Task complete                                            ║
║ Duration: 60 seconds                                     ║
║ Up Next: Symbol Rollup                                   ║
╚══════════════════════════════════════════════════════════╝
```

**Task 3: Symbol Rollup** (in-process)

```
2026-02-18 16:45:08 - INFO - 📈 Running symbol summary rollup...
2026-02-18 16:45:08 - INFO - 📊 Running end-of-day symbol summary rollup...
2026-02-18 16:45:44 - INFO - ✅ Symbol summary complete (36.1 seconds)

╔══════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                          ║
╠══════════════════════════════════════════════════════════╣
║ Task complete                                            ║
║ Duration: 60 seconds                                     ║
║ Up Next: Daily Evaluation                                ║
╚══════════════════════════════════════════════════════════╝
```

**Task 4: Daily Evaluation** (subprocess — output streamed)

```
2026-02-18 16:46:50 - INFO - 📋 Running daily evaluation...

    [streamed subprocess output from run_daily_evaluation]
    Evaluating 20 scans for 2026-02-18...
    Processing scan 1/20: 2026-02-18 09:30:01
    ... [evaluation progress] ...

2026-02-18 16:48:12 - INFO - ✅ Daily evaluation completed
```

**Task 5: Watchlist Cleanup** (in-process)

```
2026-02-18 16:48:12 - INFO - 🗂️ Running watchlist cleanup...
2026-02-18 16:48:13 - INFO - ✅ Watchlist cleanup complete: 4 entries archived
```

### FM Completion Box (Orchestrator)

After `run_post_market()` returns, the orchestrator draws the final completion box for the entire FM daily cycle.

```
╔══════════════════════════════════════════════════════════════════════╗
║ 🎯 FLOW MONITOR COMPLETE                                            ║
╠══════════════════════════════════════════════════════════════════════╣
║ Pre-Market: ✅ Completed                                             ║
║   Alerts resolved: 8 (3 BUILDING, 4 CLOSING, 1 NEUTRAL)            ║
║   Watchlist sentiment: 5 symbols updated                             ║
║ Market Hours: ✅ Completed                                           ║
║   Cycles: 20 (19 successful, 1 failed)                              ║
║   Avg cycle: 1320.4s                                                 ║
║ Post-Market: ✅ Completed                                            ║
║   Backfill: 744/746 symbols | Regime: elevated                      ║
║   Rollup: complete | Evaluation: complete                            ║
║   Cleanup: 4 entries archived                                        ║
║ Duration: 7h 18m                                                     ║
╚══════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════╗
║ ☕ Coffee Break                                                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ Taking a well-deserved break                                         ║
║ Duration: 60 seconds                                                 ║
║ Press Ctrl+C to safely stop Option Scanner system.                   ║
║ Up Next: Evening Option Pipeline                                     ║
╚══════════════════════════════════════════════════════════════════════╝

                    ... 60 seconds pass ...

╔══════════════════════════════════════════════════════════════════════╗
║ Resuming Operations                                                  ║
╠══════════════════════════════════════════════════════════════════════╣
║ Wait complete — continuing pipeline                                  ║
╚══════════════════════════════════════════════════════════════════════╝
```

### What this demonstrates

| Concept | Where it appears |
|---------|-----------------|
| **Phase header** | Top: `═══ PHASE 2: FLOW MONITOR ═══` |
| **Single mission box** | One mission box wrapping the entire FM daily cycle (pre + market + post) |
| **Pre-market coordinator output** | Compact progress lines: alert resolution results, sentiment updates |
| **Orchestrator wait messages** | `beautiful_log()` lines for timing waits (9:15 AM, 9:30 AM, 4:30 PM) |
| **Delegated orchestrator per-cycle output** | Full cycle with collection → analysis → alerts → watchlist → sync → performance breakdown |
| **Alert display (no borders)** | `logging.info()` lines with emoji category headers, no `═══` decorative borders |
| **Alert processing summary (no borders)** | Plain `logging.info()` stats, no `═══` borders |
| **10-cycle performance summary** | Averages, slowest, fastest — appears at cycle 10 and 20 |
| **Market close signal** | `"🔔 Market closed."` — natural exit from while loop |
| **End-of-day detail lines** | Missing quotes, failed options, collection errors from `format_end_of_day_lines()` |
| **Session summary box (orchestrator)** | `_display_session_summary()` draws double-border box from `get_summary()` dict |
| **FM internal coffee breaks** | `create_status_box()` with context-aware messages between post-market tasks |
| **Orchestrator coffee break** | Standard format with "Up Next: Evening Option Pipeline" after FM completes |
| **Rich completion box (dict return)** | Per-sub-phase metrics from FM pre/market/post return dicts |
| **Post-market task announcements** | Single `logging.info()` line per task start + result |

### What's different from Phase 1

| Aspect | Phase 1 (Pre-Market) | Phase 2 (Flow Monitor) |
|--------|---------------------|----------------------|
| **Orchestrator boxes** | Per-step mission + completion (5 pairs) | One pair wrapping entire FM cycle |
| **Duration** | ~2 hours | ~7+ hours |
| **Internal structure** | Sub-phase headers (`──`) inside OP | Three distinct sub-phases (pre/market/post) with different roles |
| **Per-cycle output** | N/A | Repeated cycle structure during market hours |
| **Coffee breaks** | Orchestrator only (STEP_SEQUENCE) | Both orchestrator (after FM completes) and FM internal (between post-market tasks) |
| **Alert display** | N/A | Per-cycle alert block is THE product of FM |
| **Session summary** | N/A | Orchestrator draws dedicated session summary box |

### What's NOT shown here (but would appear in real output)

- **Collection failure mid-cycle**: If collection returns None, FM logs a warning and calls `handle_error(severity='CRITICAL')` → process exits. The orchestrator detects the non-zero exit code and draws a failure box.
- **Zero alerts**: Most cycles produce 0 alerts. The alert display block is simply absent, and the cycle output goes directly from analysis summary to quick-sync.
- **Quick-sync failure**: Logged as a warning, cycle continues. The "DB Sync" line in the performance breakdown shows `0.0s (0 rows)`.
- **Agent analysis** (Task 5a): Optional, disabled by default (`--run-agent` flag). When enabled, appears between evaluation and watchlist cleanup.
- **Post-market task failure**: If backfill fails, `handle_error(severity='CRITICAL')` fires and exits. For non-critical tasks (regime, rollup, evaluation), `handle_error(severity='ERROR')` queues for batch mode and the pipeline continues.
- **Shutdown during coffee break**: `shutdown_event.set()` interrupts the sleep. FM logs `"Coffee break interrupted - shutting down gracefully"` and exits the loop.
