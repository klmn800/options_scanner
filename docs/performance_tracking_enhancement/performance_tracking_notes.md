# Performance Tracking Enhancement — Notes

**Created:** 2026-02-19
**Origin:** big-to-do-list.txt item 8, discussion during console output refactor Phase 2
**Status:** Brainstorming — this document captures ideas and observations, not a definitive plan. Everything here is subject to change as the design evolves.

---

## The Problem

Every strategy and orchestrator step already computes timing data (`time.time()` deltas, `FMSessionStats` per-cycle breakdowns, strategy return dicts with `duration_seconds`). All of it evaporates at the end of each trading day. There is no historical record of how long things take, no baselines to detect degradation, and no way to answer questions like "has collection been getting slower over the past month?"

---

## Design Decisions (Agreed)

- **Dedicated database** — not in `datalake.db`. Performance data is meta-operational, not market data. Keeps the production DB clean and avoids lock contention during writes.
- **End-of-day persistence** — a process in the main orchestrator that compiles the day's performance data and writes it to the database. Runs once, after all strategies complete. Not per-cycle (too noisy for long-term storage).
- **Catalogue-driven** — a dictionary of all measurable performance pieces, so the schema is deliberate and extensible rather than ad-hoc.

---

## Critical Prerequisite: Return Dict Propagation

**As of 2026-02-19, every `run_*()` method in `main_runners.py` returns `bool`.** The rich dicts from strategies (OP pipeline results, FM session stats, EI calculations) are consumed inside the runner methods for status box display and then discarded. They never propagate to the caller.

This means the end-of-day collection process **cannot currently access** the metrics listed in the catalogue below without one of these changes:

1. **Propagate return dicts** — change each `run_*()` method to return the strategy's dict instead of `True`/`False`. The orchestrator already has the dicts in local variables; the change is replacing `return True` with `return result`. This is the cleanest approach and aligns with the Console Developer Guide's return dict contracts.
2. **Persist to daily_state.json** — save the full return dict to `daily_state.json` alongside the current status strings. The end-of-day process reads from the JSON file. Less clean but avoids changing runner signatures.
3. **Instrument separately** — add `time.time()` wrappers at the orchestrator level, independent of strategy return dicts. Captures duration but loses strategy-specific metrics (contracts stored, alerts generated, etc.).

**Recommendation:** Option 1. It's the smallest code change per method (swap `return True` for `return result`) and provides the richest data. Also unblocks autofix improvements (richer context in `queue_error()` calls).

---

## Measurable Performance Pieces — Catalogue

Legend for **Data Status** column:
- **EXISTS** — data is computed and accessible today (in a return dict, class attribute, or variable)
- **EXISTS-INTERNAL** — data exists inside the `run_*()` method but is discarded before returning (needs return dict propagation)
- **NEEDS INSTRUMENTATION** — not currently measured; would require new code

### Orchestrator Steps (main_runners.py)

Every `run_*()` method currently returns `bool`. Rich dicts exist internally for some.

| Step | Call Type | Return Today | Data Status | What Could Be Captured |
|------|-----------|-------------|-------------|----------------------|
| Morning Option Pipeline | In-process | `True` or `sys.exit` | EXISTS-INTERNAL | duration, symbols collected, contracts stored, symbols failed, health status |
| Metadata Collection | Subprocess | `bool` | NEEDS INSTRUMENTATION | duration only (subprocess boundary — no structured data) |
| Morning Views | Subprocess | `bool` | NEEDS INSTRUMENTATION | duration only (subprocess boundary) |
| FM Pre-Market | In-process | `bool` (via `run_flow_monitor`) | EXISTS-INTERNAL | duration, alerts resolved, sentiment updated, sync rows |
| FM Market Hours | In-process | `bool` (via `run_flow_monitor`) | EXISTS-INTERNAL | total cycles, session stats dict (see FM section below) |
| FM Post-Market | In-process | `bool` (via `run_flow_monitor`) | EXISTS-INTERNAL | per-task durations (backfill, regime, rollup, evaluation, cleanup) |
| Evening Option Pipeline | In-process | `True` or `sys.exit` | EXISTS-INTERNAL | same as morning OP |
| Earnings Daily Pipeline | In-process | `bool` | EXISTS-INTERNAL | duration, snapshots created, moves calculated, alerts triggered |
| Earnings Morning Scan | In-process | `bool` | EXISTS-INTERNAL | duration, opportunities found |
| Earnings Weekly Refresh | In-process | `bool` | EXISTS-INTERNAL | duration, events fetched |
| Database Backup | Subprocess | `bool` | NEEDS INSTRUMENTATION | duration only (subprocess boundary) |
| Query DB Sync | Subprocess | `bool` | **PARTIALLY DONE** | duration, pages, size, tables now saved to `daily_state.json` `sync_performance[]` (2026-02-23). Quick sync not yet tracked. |
| Sector Archive | Subprocess | `bool` | NEEDS INSTRUMENTATION | duration only (subprocess boundary) |

**Note on subprocesses:** Metadata, Morning Views, DB Backup, Query Sync, and Sector Archive all run as subprocesses. Their internal metrics don't cross the process boundary. For these, we can capture wall-clock duration from the orchestrator side (`time.time()` around the call) but not internal breakdowns unless the scripts are refactored to write metrics to a shared location (JSON file, database row). **Update 2026-02-23:** Query Sync now demonstrates the stdout-parsing approach — regex extraction from subprocess output into `daily_state.json`. This pattern could be replicated for DB Backup and Sector Archive without refactoring those scripts.

### FM Per-Cycle Detail (FMSessionStats) — EXISTS

This data is real and verified. `FMSessionStats` in `fm_session_stats.py` accumulates these in Python lists across all market hours cycles. Currently persisted to `daily_state.json` (overwritten each morning) but not to any database.

| Metric | Source Field | Verified |
|--------|-------------|----------|
| Cycle count | `stats.total_cycles` | Yes |
| Per-cycle times | `stats.cycle_times` (list of floats) | Yes |
| Per-cycle collection times | `stats.collection_times` | Yes |
| Per-cycle storage times | `stats.storage_times` | Yes |
| Per-cycle analysis times | `stats.analysis_times` | Yes |
| Per-cycle alert times | `stats.alert_times` | Yes |
| Per-cycle analysis query times | `stats.analysis_query_times` | Yes |
| Per-cycle analysis scoring times | `stats.analysis_scoring_times` | Yes |
| Per-cycle analysis DB write times | `stats.analysis_db_write_times` | Yes |
| Failed cycles count | `stats.failed_cycles` | Yes |
| News enrichment totals | `stats.news_enrichment` dict | Yes |
| Total alerts generated | Accumulated in cycle loop | Yes |

For the performance DB, persist daily summaries (avg, min, max, total) rather than per-cycle rows. The raw lists can go in a JSON column for drill-down if needed.

### FM Per-Cycle Detail (FMPerformanceTracker) — EXISTS but redundant

`fm_performance_tracker.py` tracks similar data to `FMSessionStats` using `deque(maxlen=100)`. It also tracks memory usage via `psutil` and task-level rolling averages. However, it has **zero persistence** — pure RAM, no file writes, no database. It predates `FMSessionStats` (Aug 2025 vs later) and appears to be the older, less-used version. Should be evaluated for consolidation or deprecation during implementation.

### API-Level — NEEDS INSTRUMENTATION (Future)

| Metric | Source | Notes |
|--------|--------|-------|
| Tradier API calls per day | Not currently counted | Would need counter in `tradier_api.py` |
| Tradier avg response time | Not currently tracked | Would need timing wrapper in `tradier_api.py` |
| Alpha Vantage calls used | `news_sentiment.py` budget tracker | Already tracked in-memory, not persisted |
| Alpha Vantage budget remaining | Config: 25/day | Trivial |

### Database Operations — MIXED

| Metric | Source | Data Status |
|--------|--------|-------------|
| Quick sync duration per cycle | `run_quick_sync()` return value | EXISTS (returned to FM cycle loop) |
| Quick sync rows per cycle | `run_quick_sync()` return value | EXISTS (returned to FM cycle loop) |
| Full sync duration | `db_backup.py` stdout | **DONE** — saved to `daily_state.json` `sync_performance[]` (2026-02-23) |
| Full sync pages/size/tables | `db_backup.py` stdout | **DONE** — parsed from subprocess output, saved alongside duration |
| Archive duration (Fridays) | `db_archive_sector.py` stdout | NEEDS INSTRUMENTATION (subprocess) |
| datalake.db file size | `os.path.getsize()` | Trivial to measure |

---

## Dimensional Analysis Requirements

Performance should be queryable by **day of week** and **time of day**, not just by date.

- **Day of week**: How does Monday compare to Friday? Mondays may be slower (weekend gap, more data to process). Fridays have archive operations competing for I/O. Day-of-week patterns are invisible if we only store `trade_date` — we need `day_of_week` (0=Monday through 4=Friday) as a column or derive it at query time.
- **Time of day**: How does a 10:00 AM FM cycle compare to a 2:00 PM cycle? Early cycles may be slower (cold caches, more expirations to fetch). Late cycles may show different alert patterns. This requires **per-cycle rows for FM**, not just daily summaries — each row needs a `cycle_start_time` timestamp.

This argues for storing FM per-cycle detail (not just daily aggregates) so we can slice by hour. The daily orchestrator steps naturally have one row per day, but `day_of_week` should be stored on those too for easy cross-day queries.

Example queries this enables:
```sql
-- Average FM collection time by hour of day
SELECT strftime('%H', cycle_start_time) as hour, AVG(collection_seconds)
FROM fm_cycle_performance GROUP BY hour;

-- Monday vs Friday orchestrator step durations
SELECT day_of_week, step_name, AVG(duration_seconds)
FROM step_performance GROUP BY day_of_week, step_name;

-- Are 2 PM cycles consistently slower than 10 AM?
SELECT CASE WHEN strftime('%H', cycle_start_time) < '12' THEN 'morning' ELSE 'afternoon' END as session,
       AVG(cycle_seconds), AVG(collection_seconds), AVG(analysis_seconds)
FROM fm_cycle_performance GROUP BY session;
```

This may tip the schema decision toward having a **separate `fm_cycle_performance` table** with one row per cycle (rather than cramming cycle detail into the JSON column of the step table). ~15-20 rows per trading day — small data.

---

## Schema Ideas (Rough)

### Option A: Wide table, one row per step per day

```sql
CREATE TABLE step_performance (
    trade_date TEXT NOT NULL,
    step_name TEXT NOT NULL,          -- 'morning_op', 'fm_pre_market', 'fm_market_hours', etc.
    duration_seconds REAL,
    status TEXT,                      -- 'success', 'failed', 'skipped'
    primary_metric_name TEXT,         -- 'contracts_stored', 'alerts_resolved', etc.
    primary_metric_value REAL,
    secondary_metric_name TEXT,
    secondary_metric_value REAL,
    error_count INTEGER DEFAULT 0,
    notes TEXT,                       -- JSON blob for step-specific extras
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, step_name)
);
```

Pros: Simple, one table. Cons: Generic metric columns lose type safety.

### Option B: Normalized — step table + metrics table

```sql
CREATE TABLE perf_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    step_name TEXT NOT NULL,
    duration_seconds REAL,
    status TEXT,
    error_count INTEGER DEFAULT 0,
    recorded_at TEXT NOT NULL,
    UNIQUE(trade_date, step_name)
);

CREATE TABLE perf_metrics (
    step_id INTEGER NOT NULL REFERENCES perf_steps(id),
    metric_name TEXT NOT NULL,
    metric_value REAL,
    PRIMARY KEY (step_id, metric_name)
);
```

Pros: Extensible, each step can have N metrics. Cons: Joins for every query.

### Option C: One table per category

Separate tables for orchestrator steps, FM cycle summaries, API stats. Each with typed columns.

Pros: Clean, queryable, type-safe. Cons: More tables, more schema maintenance.

**Leaning toward:** Option A for simplicity. The `notes` JSON column handles step-specific extras without schema changes. Easy to query: `SELECT * FROM step_performance WHERE step_name = 'fm_market_hours' ORDER BY trade_date DESC LIMIT 30`.

---

## Collection Process — End-of-Day

Where it would run: In the main orchestrator's daily sequence, after all strategies complete but before the day-end summary box.

Rough flow:
1. Gather return dicts from each `run_*()` method (requires return dict propagation — see prerequisite above)
2. Gather FM session stats from `daily_state.json` or in-memory (if FM ran)
3. Compute summary metrics (averages, totals for FM cycles)
4. Measure any trivial metrics (db file size, etc.)
5. Write to performance database
6. Log confirmation: `beautiful_log("Performance data saved: N steps recorded", 'success')`

**Note on current `daily_state.json`:** Stores `orchestrator_results` (step names → bool), `fm_session` (the full session stats dict), and as of 2026-02-23, `sync_performance` (list of sync entries with timing/size/pages). The orchestrator results lack timing data. The FM session dict has timing. The sync_performance list demonstrates the append-to-daily-state pattern that could be generalized for all orchestrator steps. Bridging this gap is part of the return dict propagation work.

---

## Use Cases

### Primary: Autofix Reference and Diagnostics

Performance data is a **first-class input for the autofix system**. When autofix spawns a Claude session to diagnose an issue, historical performance baselines give it critical context:

- **"Is this slow, or normal?"** — If FM collection takes 1400s today and the 30-day average is 1350s, that's normal variance. If it takes 2800s, something is wrong. Without baselines, autofix can't distinguish.
- **"When did this start?"** — Trend data lets autofix identify when degradation began: "Collection time increased 40% starting 2026-02-15, correlating with symbol universe expansion from 720 to 746."
- **"What changed?"** — Comparing today's per-step breakdown against historical averages highlights which specific phase degraded (API latency? DB writes? Analysis scoring?).
- **Error queue enrichment** — When `queue_error()` fires, the context dict could include "this step's 30-day baseline vs today's actual" as diagnostic context, giving the spawned session immediate performance comparison without needing to query anything.

### Secondary: Development and Maintenance

- **Regression detection** — After a code change, did analysis time jump? Compare pre/post deployment averages.
- **Capacity planning** — How much time does each phase consume? Where's the bottleneck? When does the daily cycle risk overrunning its time window?
- **Trend monitoring** — Is collection time creeping up week over week? (DB bloating, API slowing, symbol universe growing)
- **Morning View integration** — Future: show a "system health" panel with yesterday's timing vs 30-day baseline.

---

## Completed Work

### 2026-02-23: Full Sync Performance Tracking (Prep)

**What:** Full query sync (morning/evening/final) now records performance to `daily_state.json` under a `sync_performance` list.

**Files changed:**
- `main_ui.py` — new `_save_sync_performance()` function (appends to daily state)
- `main_runners.py` — calls it from `run_query_database_sync()` on all exit paths (success + 3 failure modes); also now parses page count from subprocess output

**Fields captured per entry:**
- `timestamp` — when the sync ran (Eastern)
- `sync_type` — `'full'` (ready for `'quick'` when FM quick-sync tracking is added)
- `success` — bool
- `duration_seconds` — wall-clock time
- `size_display` — e.g. `"7.16 GB"` (parsed from subprocess stdout)
- `pages` — e.g. `1878109` (parsed from subprocess stdout)
- `tables` — e.g. `28` (parsed from subprocess stdout)

**What this enables:**
- 3 entries per trading day (morning 1.4, evening 3.2, final 3.5)
- Day-over-day sync time comparison (e.g. Monday post-weekend vs Tuesday)
- DB growth tracking via pages count
- Foundation for the performance database — these fields map directly to `step_performance` rows

**Not yet done:**
- Quick sync tracking (runs inside FM, would need `_save_sync_performance('quick', ...)` call in `fm_main.py:run_quick_sync()`)
- Migration from `daily_state.json` to the dedicated performance database
- `step_durations` dict in `main.py` already captures wall-clock for all steps but is only used for the day-end summary display — not persisted

### Observations from Research (2026-02-23)

During the sync tracking implementation, several things were confirmed:

1. **`step_durations` dict already exists in `main.py`** (~line 391). Every `run_*()` call is wrapped with `time.time()` deltas stored in `step_durations[step_name]`. This is used only by `_print_day_summary()` and then discarded. Persisting this dict to `daily_state.json` at end-of-day would capture wall-clock durations for ALL orchestrator steps with minimal effort — a strong candidate for the next incremental step.

2. **Quick sync timing exists but isn't persisted anywhere.** `fm_main.py:run_quick_sync()` returns `(success, elapsed, row_count)` to the FM cycle loop. It's logged to diagnostics and displayed, but not accumulated in `FMSessionStats` or `daily_state.json`. Adding it to the session stats lists (like `storage_times`, `analysis_times`) would be straightforward.

3. **`daily_state.json` is proving to be a solid interim store.** It now holds orchestrator results, FM session stats, and sync performance — all the building blocks for the future performance database. The migration path is clear: read `daily_state.json` at end-of-day, write rows to `performance.db`, done.

4. **The stdout-parsing pattern works well for subprocess steps.** The sync implementation shows that regex-parsing structured output lines (pages, size, duration) from subprocess stdout is reliable and doesn't require refactoring the subprocess scripts. This same pattern applies to DB Backup (`"Backup completed in X.X minutes"`) and Sector Archive (which has similar completion lines).

---

## Implementation Phases (Suggested)

### Phase 0: Quick Wins (NEW — minimal effort, high value)
- Persist `step_durations` dict to `daily_state.json` at end-of-day (captures wall-clock for ALL steps immediately)
- Add quick sync timing to `FMSessionStats` (sync_times list, sync_row_counts list)
- Add quick sync entries to `daily_state.json` sync_performance list from `fm_main.py`

### Phase 1: Foundation
- Create `data/performance.db` (or chosen location)
- Create `step_performance` table (Option A schema)
- Propagate return dicts from `run_*()` methods (swap `return True` → `return result`)
- Write end-of-day collection step in orchestrator — reads `daily_state.json`, writes to `performance.db`
- Persist orchestrator step durations + statuses

### Phase 2: FM Detail
- Persist FM session stats daily summary (avg/min/max cycle times, alert totals)
- Evaluate `FMPerformanceTracker` for consolidation with `FMSessionStats`

### Phase 3: Baselines and Autofix Integration
- Compute rolling 30-day baselines
- Add baseline comparison to `queue_error()` context
- Optional: deviation detection triggers (2x baseline = warning, 3x = queue error)

### Phase 4: Deeper Instrumentation (Future)
- API-level metrics (Tradier call counts, response times)
- Subprocess metrics (parse stdout or write to shared file)
- Morning View health panel

---

## Open Questions

- [ ] Database location — `data/performance.db`? Or a subdirectory like `data/health/performance.db`?
- [ ] Retention policy — keep forever (small data, ~13 rows/day)? Or rolling window?
- [ ] FM per-cycle detail — leaning toward storing it (one row per cycle, ~15-20 rows/day) to enable time-of-day analysis. Separate `fm_cycle_performance` table?
- [ ] Should the collection process be a standalone script or inline in the orchestrator?
- [ ] Baseline computation: rolling 30-day average? Percentile-based (p50/p90/p99)? Both?
- [ ] `FMPerformanceTracker` — consolidate into `FMSessionStats`, or deprecate?
- [x] For subprocess steps (metadata, backup, sync, archive) — is wall-clock duration from the orchestrator sufficient, or do we need internal breakdowns? **Answer (2026-02-23):** Stdout parsing works well for sync (pages, size, duration extracted). Wall-clock + parsed stdout is sufficient for the subprocess steps. Internal breakdowns would be nice-to-have but aren't necessary for Phase 1.
- [ ] Quick sync tracking — add to `FMSessionStats` lists and `daily_state.json` sync_performance? Or wait for the performance database?
- [ ] `step_durations` persistence — persist the existing dict to `daily_state.json` at end-of-day as the lowest-effort next step?

---

## References

- `big-to-do-list.txt` item 8 — original description
- `strategies/flow_monitor/fm_session_stats.py` — current in-memory FM accumulator (verified)
- `strategies/flow_monitor/fm_performance_tracker.py` — older in-memory tracker (RAM only, zero persistence)
- `logs/daily_state.json` — daily state: orchestrator results, FM session stats, sync performance (2026-02-23)
- `main_runners.py` — all `run_*()` methods return `bool` (audit: 2026-02-19)
- `main_ui.py` — `_save_sync_performance()` function (2026-02-23), `_save_orchestrator_result()`, `_save_fm_session()`
- `main.py` — `step_durations` dict (~line 391) captures wall-clock for all steps but only used for display
- `docs/CONSOLE_DEVELOPER_GUIDE.md` Section 8 — return dict contracts (the target)
- `autofix/reference/AUTOFIX_CHEAT_SHEET.md` — error routing and context enrichment
