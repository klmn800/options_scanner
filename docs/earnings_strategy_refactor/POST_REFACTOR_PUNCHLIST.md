# Post-Refactor Punchlist: Earnings Intelligence (PRDs 0008 / 0009 / 0010)

**Created:** 2026-02-27
**Purpose:** Issues found during QC audit of PRDs 0008, 0009, and 0010 completeness. Each item was discovered by comparing PRD/task requirements against the current codebase.

**Status:** All items resolved. 11 items identified: 9 done, 2 closed/accepted (E-004, E-009).

---

## Instructions for Analysts

This is a living document. The PM session (Claude Code) adds items during review; coding analysts implement them and mark completion.

### Picking up an item
1. Read the item's **Problem** and **Fix** sections completely
2. Read any referenced files before making changes
3. If an item says "depends on E-XXX", check that E-XXX is marked `DONE` first

### Marking an item complete
Add a **Status** line at the end of the item block:

```
**Status:** `DONE` — [your name/session], [date]. [One sentence summary of what you did.]
```

### If an item needs adjustment
```
**Status:** `PARTIAL` — [your name/session], [date]. [What you did + what remains.]
```

### Do NOT
- Delete or rewrite existing item descriptions
- Renumber items (E-XXX numbers are permanent)
- Add new items (only the PM review session adds items)

---

## Items

### E-001: Stale `'1.2 Arbitrage Scanner'` key in mid-day skip logic
**Location:** `main.py:403`
**Severity:** Functional
**PRD Req:** 0008 Req 2, Req 5 / Task 5.2
**Problem:** The mid-day start routing (after 9:00 AM) marks morning steps as `'skipped'` in the results dict. Line 403 still lists `'1.2 Arbitrage Scanner'` — a key that no longer exists in the pipeline. The actual Step 1.2 is now `'1.2 Earnings Intelligence'`. This means:
- A phantom `results['1.2 Arbitrage Scanner'] = 'skipped'` entry is created (harmless but confusing)
- The real `results['1.2 Earnings Intelligence']` is **never** marked `'skipped'` — so if someone starts mid-day, EI may attempt to run when it should be skipped
**Fix:** Change `'1.2 Arbitrage Scanner'` to `'1.2 Earnings Intelligence'` on line 403:
```python
for key in ['1.1 Morning Option Pipeline', '1.2 Earnings Intelligence',
            '1.3 Metadata Collection', '1.4 Query Sync (Morning)',
            '1.5 Morning Views']:
```

**Status:** `DONE` — QC session, 2026-02-27. Changed `'1.2 Arbitrage Scanner'` to `'1.2 Earnings Intelligence'` on line 403.

---

### E-002: Stale docstring references to old step names
**Location:** `main.py:10`, `main.py:20`
**Severity:** Documentation
**PRD Req:** 0008 Req 5
**Problem:** The module docstring's "Clean Architecture" section still shows the old pipeline layout:
- Line 10: `"Earnings Arbitrage Scanner"` — should be `"Earnings Intelligence"`
- Line 20: `"Earnings Alert Processing"` — this evening step no longer exists (removed in Req 4, was old Step 3.3)
**Fix:** Update lines 9-21 to reflect the current step layout:
```
  6:35 AM  - Morning Option Pipeline (fresh OI for KLMN 800)
           - Earnings Intelligence (signals, watchlist, news, arbitrage)
           - Metadata Collection Pipeline
           - Query Database Sync (morning data + metadata)
           - Morning Views (emailed watchlist)
  ...
           - Evening Option Pipeline (volume-enriched data)
           - Query Database Sync (volume-enriched OI)
           - Airline Play Tracking
           - Query Database Sync (final)
           - Database Backup (datalake_backup.db - daily)
```

**Status:** `DONE` — QC session, 2026-02-27. Updated docstring lines 9-21: "Earnings Arbitrage Scanner" → "Earnings Intelligence", removed "Earnings Alert Processing", added "Query Database Sync (final)" to evening section.

---

### E-003: Missing `signals_updated` in return dict and completion box
**Location:** `ei_main.py:737-747` (return dict), `main_runners.py:1037-1076` (completion box)
**Severity:** Spec deviation (low functional impact)
**PRD Req:** 0008 Req 10 / Task 4.6, Req 18 / Task 6.2
**Problem:** The PRD and task list both specify `signals_updated` as a top-level field in the return dict (Req 10) and as a line in the completion box ("Signals updated: N" per Req 18 / Task 6.2). Neither exists in the code. The data is available via `sub_tasks['expected_moves']['processed']` but never surfaced.
**Fix:**
In `ei_main.py`, add to the return dict (after line 739):
```python
'signals_updated': moves_results.get('processed', 0),
```
In `main_runners.py`, add after line 1043:
```python
box_lines.append("Signals updated: {}".format(result.get('signals_updated', 0)))
```
Also add to the failure dict at `main_runners.py:1030`:
```python
'signals_updated': 0,
```
And to the failure dict at `ei_main.py:764`:
```python
'signals_updated': 0,
```

**Status:** `DONE` — QC session, 2026-02-27. Added `signals_updated` and `watchlist_breakdown` to both success and failure return dicts in `ei_main.py`, plus failure dict in `main_runners.py`. Added "Signals updated: N" line to completion box.

---

### E-004: `arb_opportunities` vs PRD's `arbitrage_opportunities`
**Location:** `ei_main.py:746`, `ei_main.py:772`, `main_runners.py:1034`, `main_runners.py:1069`
**Severity:** Spec deviation (no functional impact — internally consistent)
**PRD Req:** 0008 Req 10 / Task 4.6
**Problem:** The PRD specifies `arbitrage_opportunities` as the return dict key name. Both `ei_main.py` and `main_runners.py` consistently use the abbreviated `arb_opportunities` instead. The code works correctly but deviates from the spec.
**Fix:** Either:
- (a) Rename to `arbitrage_opportunities` in both files (4 locations) to match the PRD, OR
- (b) Accept the abbreviation and note it as an intentional deviation
**Recommendation:** Option (b) — the abbreviation is clear and both layers agree. Document in this punchlist as accepted.

**Status:** `CLOSED (accepted)` — QC session, 2026-02-27. Abbreviation is internally consistent across both layers. No rename needed.

---

### E-005: `watchlist_breakdown` not at return dict top level
**Location:** `ei_main.py:737-747`
**Severity:** Spec deviation (no functional impact — data accessible via sub_tasks)
**PRD Req:** 0008 Req 10 / Task 4.6
**Problem:** The PRD specifies `watchlist_breakdown` as a top-level field in the return dict. It exists only inside `sub_tasks['watchlist']['breakdown']` (populated at line 457). The orchestrator reaches into `sub_tasks` to access it (`main_runners.py:1050-1051`), which works but deviates from the flat dict contract in the spec.
**Fix:** Add to the return dict in `ei_main.py` (after line 743):
```python
'watchlist_breakdown': watchlist_results.get('breakdown', {}),
```
And to both failure dicts:
```python
'watchlist_breakdown': {},
```

**Status:** `DONE` — QC session, 2026-02-27. Added `watchlist_breakdown` to top-level return dicts in `ei_main.py` (success + failure). Updated `main_runners.py` to read from top-level field instead of reaching into `sub_tasks`.

---

### E-006: Task 4.3 spec references wrong table for news dedup
**Location:** Task list `tasks/tasks-0008-prd-earnings-watchlist-morning-pipeline.md` line 56, PRD Req 19
**Severity:** Documentation (code is correct)
**PRD Req:** 0008 Req 19
**Problem:** Both the PRD (Req 19) and the task list (Task 4.3) specify that news dedup should check `news_articles` table. The implementation correctly checks `news_symbol_sentiment` instead (`ei_main.py:513`), because `news_symbol_sentiment` is the table with a per-symbol `symbol` column — `news_articles` does not have one. The code is correct; the spec documents are wrong.
**Fix:** No code change needed. Update the PRD and task list docs to say `news_symbol_sentiment` for accuracy. This is already documented in MEMORY.md as a known gotcha.

**Status:** `DONE` — QC session, 2026-02-27. Updated PRD Req 19 (line 219) and Task 4.3 (line 56) and Database Operations table (line 349) to reference `news_symbol_sentiment` with correct column name `fetched_at`.

---

### E-007: CLAUDE.md docstring still references old step layout
**Location:** `CLAUDE.md` line "Phase 1 (6:35 AM)" section
**Severity:** Documentation
**PRD Req:** 0008 Req 5
**Problem:** The CLAUDE.md "Daily Schedule" section says:
```
Phase 1 (6:35 AM): Pre-market — Morning Option Pipeline, Arbitrage Scanner, Metadata, Sync, Morning Views
```
This should reflect the new Step 1.2 name ("Earnings Intelligence" not "Arbitrage Scanner") and the evening phase should not reference the old Earnings Pipeline step.
**Fix:** Update the Daily Schedule section in CLAUDE.md:
```
Phase 1 (6:35 AM): Pre-market — Morning Option Pipeline, Earnings Intelligence, Metadata, Sync, Morning Views
```
And verify the Phase 3 description no longer mentions "Earnings Pipeline" (it should list: Evening OP, Sync, Airline Play, Final Sync).

**Status:** `DONE` — QC session, 2026-02-27. Phase 1: "Arbitrage Scanner" → "Earnings Intelligence". Phase 3: removed "Earnings Pipeline" (now: Evening OP, Sync, Airline Play, Final Sync).

---

### E-008: `ei_watchlist.py` missing `queue_error()` autofix integration
**Location:** `strategies/earnings_intel/ei_watchlist.py:618-627`
**Severity:** Functional (autofix gap)
**PRD Req:** 0008 Req 27 / Task 2.9
**Problem:** Task 2.9 and PRD Req 27 both require that fatal failures in `populate_watchlist()` queue via `queue_error()` with severity `ERROR` and context including `failed_step='watchlist_population'` and `error_message`. The current code just logs the error and returns a failure dict — it does not call `queue_error()` and does not even import it. The orchestrator layer (`main_runners.py:1127`) does queue an error when the *overall* EI pipeline fails, but that error lacks the sub-step specificity that Req 27 mandates (autofix wouldn't know it was the watchlist step that broke).
**Fix:** In `ei_watchlist.py`:
1. Add import: `from tools.autofix import queue_error`
2. In the except block at line 618, before the return, add:
```python
try:
    queue_error(
        error_type='watchlist_population_failure',
        context={
            'failed_step': 'watchlist_population',
            'error_message': str(e),
            'performance_db': 'data/performance.db',
        },
        severity='ERROR'
    )
except Exception:
    pass  # Don't let autofix integration break the return
```

**Status:** `DONE` — QC session, 2026-02-27. Added `from tools.autofix import queue_error` import and `queue_error()` call in except block with `error_type='watchlist_population_failure'` and `failed_step` context. Omitted `performance_db` key from context (not relevant to this error). Updated module docstring with autofix integration note.

---

### E-009: ON CONFLICT UPDATE SET missing 8 enrichment columns
**Location:** `strategies/earnings_intel/ei_watchlist.py:517-530`
**Severity:** Spec deviation (arguably protective — see note)
**PRD Req:** 0008 Req 16 / Task 2.7
**Problem:** Task 2.7 explicitly says: *"The UPDATE SET clause must list ALL columns EXCEPT symbol, first_appeared_date, and created_at."* That's 21 columns. The ON CONFLICT DO UPDATE SET only lists 13 columns. Missing 8:
- `alert_count_5d`
- `news_sentiment_label`, `news_sentiment_score`, `news_article_count`
- `actual_move_pct`, `move_direction`
- `iv_collapse_pct`, `iv_crush_severity`

**Behavioral impact:** On daily re-runs for existing symbols, the initial upsert builds rows with NULL for all 8 enrichment columns (lines 487-494). Because these 8 are omitted from ON CONFLICT, the UPDATE preserves yesterday's enrichment values instead of NULLing them. The enrichment pass then runs immediately after and refreshes them with fresh data. If the enrichment pass *fails*, yesterday's values are preserved — which is actually better than the spec's approach (which would NULL them out, losing the data).

So the omission is *arguably an improvement* over the literal spec. But it deviates from the explicit task requirement.

**Fix (two options):**
- (a) Add all 8 columns to the UPDATE SET to match the spec exactly. Accept that enrichment-pass failures would lose yesterday's data.
- (b) Accept the deviation as intentional, document it with a code comment explaining why, and note it as a deliberate departure from the spec.
**Recommendation:** Option (b) — add a code comment. The protective behavior is valuable.

**Status:** `CLOSED (accepted)` — QC session, 2026-02-27. Omission is intentional and protective: preserves yesterday's enrichment data if the enrichment pass fails. Code comment added to `ei_watchlist.py` at the ON CONFLICT clause explaining the rationale and referencing this punchlist item.

---

### E-010: `oi_balance_text` column missing from watchlist table renderer
**Location:** `main_runners.py:1153-1155`
**Severity:** Spec deviation (missing user-facing data)
**PRD Req:** 0008 Req 17 / Task 6.3
**Problem:** Task 6.3 specifies 11 columns with explicit header names. The 10th column should be `oi_balance_text` (header: `"OI Bal"`). The implementation only shows 10 columns — `oi_balance_text` is completely absent, and the 10th column is `news_sentiment_label` (which should be the 11th).

Task 6.3 column spec:
```
symbol, status, current_price, days_to_earnings("Days"), earnings_time,
earnings_play_signal("Signal"), iv_percentile_30d("IV%ile"),
relative_underpricing_pct("Underprc%"), expected_move_pct("ExpMv%"),
oi_balance_text("OI Bal"),          ← MISSING
news_sentiment_label("Sentiment")
```

Actual columns:
```
Sym, Status, Price, Days, Time, Signal, IV%, Undr%, ExpMv, Sentiment
```

**Fix:** Add an `oi_balance_text` column between `ExpMv` and `Sentiment`. Use abbreviated header `"OI Bal"` per the task spec. Truncate values to fit (e.g., "Clr Call" for "Clear Call Bias"). May need to adjust column widths to stay within 120-char terminal width.

**Status:** `DONE` — QC session, 2026-02-27. Added "OI Bal" column (width 8) between ExpMv and Sentiment. Abbreviation map for 6 values (Clr Call, Hvy Call, Balanced, Lns Put, Hvy Put, Clr Put). Table now 116 chars wide, fits 120-char terminal.

---

### E-011: Table renderer uses plain dashes instead of box-drawing characters
**Location:** `main_runners.py:1156`
**Severity:** Spec deviation (cosmetic)
**PRD Req:** 0008 Req 17 / Task 6.3, PRD Section 6
**Problem:** Task 6.3 says *"Use box-drawing characters, fit within 120-char terminal width."* PRD Section 6 says *"The earnings watchlist table uses box-drawing ASCII characters, matching the system's established console output style."* The implementation uses plain dashes for separators (`"-" * len(hdr.strip())`) and no box borders.
**Fix:** Replace dash separators with box-drawing characters (─ for horizontal, │ for column separators, ┌┐└┘ for corners, ├┤┬┴┼ for junctions). Match the style of existing status boxes in `main_ui.py` (which use ╔═╗║╚╝). Or, if the simpler style is preferred, accept as intentional and update the task spec.

**Status:** `DONE` — Claude Opus, 2026-02-27. Replaced plain dashes with single-line box-drawing characters (┌─┬┐│├┼┤└┴┘) in `_render_earnings_watchlist()`. Single-line style complements double-line status boxes. 105 chars wide with indent, fits 120-char terminal.

---

## Summary

| Item | Severity | PRD | Status | Description |
|------|----------|-----|--------|-------------|
| E-001 | **Functional** | 0008 | DONE | Stale `'1.2 Arbitrage Scanner'` key in mid-day skip — EI not skipped on mid-day starts |
| E-002 | Documentation | 0008 | DONE | `main.py` docstring references old step names |
| E-003 | Spec deviation | 0008 | DONE | Missing `signals_updated` field + completion box line |
| E-004 | Spec deviation | 0008 | CLOSED | `arb_opportunities` vs `arbitrage_opportunities` naming — accepted |
| E-005 | Spec deviation | 0008 | DONE | `watchlist_breakdown` not at return dict top level |
| E-006 | Documentation | 0008 | DONE | PRD/task spec says `news_articles`, code correctly uses `news_symbol_sentiment` |
| E-007 | Documentation | 0008 | DONE | CLAUDE.md Daily Schedule references old step names |
| E-008 | **Functional** | 0008 | DONE | `ei_watchlist.py` missing `queue_error()` autofix integration |
| E-009 | ~~Spec deviation~~ | 0008 | CLOSED | ~~ON CONFLICT UPDATE SET missing 8 enrichment columns~~ — accepted, protective |
| E-010 | **Spec deviation** | 0008 | DONE | `oi_balance_text` column missing from watchlist table renderer |
| E-011 | Spec deviation | 0008 | DONE | Table renderer uses plain dashes, not box-drawing characters |

**PRD 0009 (Finnhub BMO/AMC):** No issues found. All 14 sub-tasks fully compliant.

**PRD 0010 (Close Data Loops):** No issues found. All completed tasks (1-4) fully compliant. Task 5 correctly deferred.
