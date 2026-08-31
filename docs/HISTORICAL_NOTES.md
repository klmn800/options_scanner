# Historical Notes

Change logs documenting significant architectural decisions and migrations. Referenced from `CLAUDE.md`.

---

## Public Release Curation (2026-08-31)

**What happened:** The repo was prepared for public release as a read-only showcase. Retired three dormant subsystems in one pass — Oracle (Vanna AI text-to-SQL round in the Morning View analyzer), the Airline Play strategy (orchestrator Step 3.3 + its two datalake tables), and the AI Council (multi-provider consensus screens, per System Analyst proposal 035) — plus the emailed morning watchlist (Step 1.6) and a set of dead tools. Roughly 59K lines removed across nine commits.

**Also in this pass:** agent workspaces de-registered as submodules (each is a separate private repo; the sanitized framework skeleton is published as [agent_lab](https://github.com/klmn800/agent_lab)); working notes parked out of the repo; hardcoded credentials and personal identifiers scrubbed from the working tree and from all git history (`git filter-repo`, all commits preserved); branch renamed `master` → `main`.

**Why:** The system is a personal single-machine research platform. Publishing it is about showing the work — architecture, data model, operational history — not shipping an installable product.

---

## SSD Migration (2026-04-10)

**What happened:** The scanner's primary drive (E:) was migrated from a Seagate Barracuda ST2000DM008 2TB HDD (7200 RPM mechanical) to a Crucial BX500 2TB SATA SSD around noon 2026-04-10. All databases (`data/datalake.db`, `data/datalake_query.db`, `data/performance.db`, all `data/sector_archive/*.db`), logs, backups, and project files now live on flash storage. The old HDD is temporarily connected via USB adapter for data transfer.

**Measured impact — sector archive (first real workload, 6 hours post-install):**

| Date | Storage | Rows | Duration | Throughput |
|---|---|---|---|---|
| **2026-04-10** | **SSD** | **5.2M** | **42 min** | **~7.4M rows/hr** |
| 2026-03-21 | HDD | 6.9M | 16.7 hrs | ~414K rows/hr |
| 2026-03-14 | HDD | 9.4M | 10.3 hrs | ~914K rows/hr |
| 2026-03-07 | HDD | 6.4M | 6.15 hrs | ~1.05M rows/hr |
| 2026-02-28 | HDD | 6.8M | 9.12 hrs | ~747K rows/hr |
| 2026-03-30 | HDD | — | NULL (corruption) | — |
| 2026-03-27 | HDD | 2.74M (tech alone) | 50 hrs (tech alone) | ~55K rows/hr (worst) |

**Throughput: ~9x faster than HDD average, ~18x faster than worst recent HDD run, ~135x faster than the Mar 27 cliff.** Data captured in `performance.db.sector_archive_performance`. Source: same `db_archive_sector.py` code, same tuning parameters, only difference is the underlying storage. HDD run-to-run variance (414K → 1.05M rows/hr) came from page-cache-vs-seek-penalty roulette; SSD throughput should be consistent going forward.

**FM cycle and quick sync measurements pending** — first full trading day on SSD is 2026-04-13 (Monday). Will be logged in `docs/SSD_MIGRATION_RESULTS.md` once collected.

**Why it matters:** The preceding two months exposed the system to a series of HDD-driven performance and reliability problems:

- **Quick Sync Slowdown (Feb 2026):** WAL growth → random-seek scan cost → 114s → 1,208s cycle times. Fixed via WAL checkpoint + 256MB cache. HDD was the amplifier.
- **Sync Slowdown (Feb 26):** Variable 50-600s sync times attributed to HDD + dual-antivirus seek thrash. Remained intermittent until SSD migration.
- **Sector Archive 56-hour hang (Mar 27):** Secondary index B-trees on 26GB `technology.db` exceeded 2MB SQLite page cache → every INSERT became random HDD seeks → 12x slowdown. Only possible because ~100 random IOPS on mechanical drives created a performance cliff at scale.
- **Sector Archive corruption (Mar 30):** Index rebuilds on multi-GB files on HDD with dual antivirus corrupted B-trees in 4 archives. Rebuild windows on mechanical drives are long enough for I/O interference to matter.
- **option_contracts HDD corruption (Apr 7):** 7 corrupt B-tree pages required `data/health/repair_option_contracts.py`.

See `docs/SECTOR_ARCHIVE_INCIDENT_2026-04-02.md` for the definitive incident narrative.

**What was retained (HDD-era tuning, now harmless on SSD):**

| Parameter | Files | Why kept |
|---|---|---|
| `cache_size = -256000` (256MB) | `fm_storage.py`, `db_backup.py`, `db_archive_sector.py`, `repair_archive.py`, `repair_option_contracts.py`, migration scripts | Harmless on SSD. Memory is abundant. No measured downside. |
| `wal_autocheckpoint = 0` + explicit `PRAGMA wal_checkpoint(PASSIVE)` | `fm_storage.py`, `db_backup.py` | Not HDD-specific — the concurrency property (PASSIVE doesn't block readers) matters regardless of storage. Keeps WAL bounded across cycles. |
| `synchronous = NORMAL` | `db_archive_sector.py`, `db_backup.py` | Standard WAL-mode pairing. Acceptable on SSD. |
| `ORDER BY rowid` in archive bulk reads | `db_archive_sector.py` | No harm on SSD (natural order). Comment remains accurate for historical context. |
| No secondary indexes on sector archives | Policy across 18 archives | **Not HDD-specific.** Archives are write-heavy, rarely queried. Policy remains correct under SSD. Manually create indexes for one-off research queries. |

**What was NOT changed:**
- No code edits. Tuning comments still explain *why* each parameter exists — they're accurate history.
- No index additions. Write-heavy archives remain index-free.
- No relaxation of `synchronous` or journal modes. WAL + NORMAL is correct on both HDD and SSD.

**Follow-up work:**
- ~~Run a Friday sector archive cycle on SSD~~ **DONE 2026-04-10: 42 min vs 6-10 hr HDD baseline** (see table above).
- Measure a full trading day's FM cycle times on SSD (first full day: 2026-04-13 Mon). Quick sync stable band was 40-60s on HDD; expect significant reduction.
- Re-measure intra-day analysis time degradation (14s → 9min was HDD pattern — likely gone).
- Create `docs/SSD_MIGRATION_RESULTS.md` with full before/after numbers once FM/sync data is collected.
- **Tuning simplification** is now worth considering, not deferring. The tuning parameters that were load-bearing on HDD (256MB cache, WAL checkpoint strategy, ORDER BY rowid) are still correct on SSD but some may be reducible. Not a priority — the code works and isn't broken — but a reasonable cleanup target once FM/sync measurements are in.

**Verification at time of migration:**
```
powershell> Get-Partition | Where-Object DriveLetter -eq 'E'
  DriveLetter DiskNumber          Size
  ----------- ----------          ----
            E          0 2000381018112

powershell> Get-Disk | Where-Object Number -eq 0
  Number FriendlyName                              Size
  ------ ------------                              ----
       0 CT2000BX500SSD1                  2000398934016
```

---

## OID → Option Pipeline Migration (Oct 19, 2025)
- Renamed: `oi_delta/` → `option_pipeline/` (directory), `oid_*.py` → `op_*.py` (7 files)
- Renamed: `oi_daily` → `option_contracts`, `oi_symbol_summary` → `option_symbol_summary` (tables)
- Renamed: `implied_volatility` → `iv`, `days_to_expiration` → `dte` (columns)
- Legacy `options_symbol_summary` table contained data through Oct 15, 2025 (since dropped)

## Dip Detection Simplification (2026-02-10)

**What happened:** Removed `z_score` and `dip_threshold_used` columns from active use in `fm_watchlist.py`.

**Why:** These columns were causing a subtle bug where values would be overwritten with NULL on subsequent scans. When `already_flagged=True`, we skipped the detection block entirely, z_score stayed None, then the UPDATE statement wrote NULL over the previously stored value.

**What we kept:**
- The z-score detection logic still works - it calculates z_score locally to decide if a dip is in the "sweet spot" range
- Config parameters in `config.json` under `flow_monitor.dip_detection` still control thresholds
- `dip_detected` flag and `dip_detected_date` still work correctly

**What we removed:**
- Storing z_score in the database (was diagnostic clutter)
- Storing dip_threshold_used (same - just for debugging)
- Debug logging we added while investigating

**Database columns:** The `z_score` and `dip_threshold_used` columns still exist in `flow_watchlist_daily` (SQLite column drops are complicated). They'll just be NULL going forward. This is fine.

**If you need z_score for analysis:** It can be recalculated from `price_diff_pct`, `rv_5d`, and `entry_ul_price` using the formula: `z_score = price_change / (min(rv_5d, 0.12) * entry_price)`

## Earnings Signal Recalibration (2026-02-10)

**What happened:** Replaced absolute `move_difference_pct` with `relative_underpricing_pct` as the primary signal metric for earnings play signals.

**Why:** Analysis of TOST's upcoming earnings revealed the old thresholds were miscalibrated: 80.9% of stocks were AVOID, only 3 stocks in the entire universe reached WATCH, and BUY/STRONG BUY effectively never triggered. TOST at 2.97% absolute difference (top 4.4% of universe) was labeled NEUTRAL.

**What changed:**
- New metric: `relative_underpricing_pct = (historical_avg - expected) / expected * 100` -- answers "by what % is the market underpricing this stock's typical earnings move?"
- New column on `earnings_upcoming`: `relative_underpricing_pct`
- Signal thresholds now use relative underpricing (configurable in config.json `earnings_play.signal_thresholds`): WATCH=15%, BUY=30%, STRONG BUY=50%
- Alert threshold uses relative underpricing >= 15% (aligned with WATCH)
- `ei_post_earnings_calc.py` now computes IV collapse directly from `option_symbol_summary` (bypasses empty `earnings_snapshots`)
- `expected_move_pct` and `move_vs_expected_pct` now populated in `earnings_moves` table
- Bug fix: `primary_iv_buildup` in sector effects was reading from price data dict instead of IV data

**What was kept:**
- `move_difference_pct` still calculated and stored (backward compat)
- Old `move_difference_threshold` config key still exists
- All existing signal values (AVOID, NEUTRAL, WATCH, BUY, STRONG BUY, UNKNOWN) unchanged

**Backfill:** `ei_backfill_metrics.py` populates IV metrics for ~27 matchable events in production. 9,292 orphaned rows (archived events) await future archive-spanning backfill.

**Threshold status:** Initial thresholds are provisional. After ~100 events accumulate with `move_vs_expected_pct` data (~early March 2026), validate and adjust.

## Quick Sync Performance Architecture (2026-02-22)

**What happened:** Quick sync (`create_quick_sync()` in `data/health/db_backup.py`) was taking 3-20 minutes per cycle by end of day, despite syncing the same ~100K rows each time. After three targeted changes, it stabilized at 40-60 seconds per cycle with no intra-day degradation.

**Why it was slow:** The target database (`datalake_query.db`) WAL file grew unbounded throughout the day. `wal_autocheckpoint=0` was set to prevent mid-insert auto-checkpoints (good), but nothing ever checkpointed afterward. The query DB is effectively read-only for analysis tools, so no other writes triggered a checkpoint. By cycle 12, the WAL was ~1.5-2.5GB and every `INSERT OR IGNORE` had to scan it for primary key checks and index updates.

**Three changes and the reasoning behind each:**

1. **WAL checkpoint after writes** (the primary fix): After committing all inserts, a `PRAGMA wal_checkpoint(PASSIVE)` folds WAL pages back into the main database file. PASSIVE mode was chosen because analysis tools may be concurrently reading the query DB -- PASSIVE won't block them (RESTART/FULL would). This keeps the WAL small for the next cycle's inserts.

2. **Source connection cache_size 8MB → 256MB**: Reading ~100K rows from an 11GB+ database with 8MB of page cache caused heavy disk I/O during the SELECT scan. 256MB keeps B-tree traversal pages cached. Memory is freed when the connection closes.

3. **Eliminated redundant COUNT query**: Previously did `SELECT COUNT(*)` to know row count, then `SELECT *` to get the data -- two full scans. Now single-pass `SELECT *` then `len(rows)`.

**Companion change -- query DB index reduction:** After full syncs, 3 production-only indexes are automatically dropped from `datalake_query.db`'s `flow_options_scans` table (6 indexes → 2 + auto PK). These indexes (contract, significance, expiration) serve FM alerting on production only. Dropping them halves the B-tree maintenance per INSERT during quick-sync. The auto-cleanup runs in `create_query_sync()` after `backup()` completes.

**Performance before/after (Feb 20 → Feb 23, ~100K rows/cycle):**
- Before: 114s → 824s → 1,142s → 1,208s (growing throughout day)
- After: 32s → 48s → 45s → 50s → 49s → 51s (stable all day)

**If quick sync fails transiently** (e.g., "database is locked"): The function already has built-in retry logic (3 attempts with backoff). Transient lock failures during market hours are expected occasionally -- the retry mechanism handles them. The PRAGMAs and WAL checkpoint are load-bearing performance infrastructure, not error-handling code.

## OP Data Quality Tracking (2026-03-17)

**Problem:** The Option Pipeline reported `success: True` as long as no exception occurred, regardless of data completeness. Three blind spots:
1. Symbols returning 0 contracts were counted as "successful" — every KLMN symbol has options, so this is a failure.
2. API errors inside `collect_symbol_oi` were swallowed — the method caught its own exceptions and returned `[]`, which the caller treated as success.
3. No tracking of OI completeness — if the morning run executed before Tradier populated OI data, contracts with OI=0/null were silently filtered out with no visibility.

**Changes (6 files):**
- `op_collector.py` (v3.2): New `collection_stats` fields (`no_contract_symbols`, `total_options_seen`, `total_options_filtered`). `collect_symbol_oi` returns `None` on exception (not `[]`) so caller distinguishes API errors from empty results. Empty contract results counted as failures. OI filter ratio tracked per symbol and aggregate.
- `op_main.py`: New fields in collection return dict. Health check logging includes OI filter stats.
- `main_runners.py`: Morning and evening completion boxes show `Symbols: X/Y (%)`, `OI Filter: N/M options filtered (%)`, conditional `No Contracts:` and `Failed:` lines. Replaces the old `Health: HEALTHY` label.
- `op_health_reporter.py`: New DATA QUALITY section in health report file.
- `performance_writer.py`: 3 new columns in `op_pipeline_performance` table (`no_contract_count`, `total_options_seen`, `total_options_filtered`) with ALTER TABLE migration for existing databases.
- `performance_db_schema.md`: Schema docs updated.

**Key design decisions:**
- A failure is a failure — no classification into types. Verbose debug logging explains the why; stats just count the what.
- OI completeness is the primary concern, not Greeks. Greeks coercion (null→0.0) remains unchanged.
- `health_status` label (HEALTHY/DEGRADED/CRITICAL) kept internally for backward compat but no longer displayed in completion boxes — replaced by actual numbers.

## Oracle Retired (2026-08-31)

**What it was:** The project's first attempt at AI-assisted database analysis (2025). Three parts: `oracle/oracle_vanna.py` — Vanna AI (FAISS RAG over table schemas) generating SQL from natural-language questions, answered by Claude Haiku; `oracle/claude_api.py` — a Claude API wrapper with function-calling for deeper analysis passes; `oracle/ollama/` — a local-LLM chat prototype. `tools/oracle_bridge.py` exposed it programmatically, and the Morning View AI analyzer used it for a "Round 3" historical-exploration pass.

**Why it was retired:** The text-to-SQL framing oversimplified the analysis problem. Generating one SQL statement from one question produced shallow, error-prone answers on a 60+ table schema with domain gotchas (point-in-time OI, two-database workflow, lowercase option types). What replaced it in practice — direct SQL via `tools/direct_db_query.py` for humans, and schema-aware Claude Code agents with real database tools for autonomous analysis — handles multi-step reasoning, verification, and context the Vanna pipeline never could. Superseded in 2025; the code sat unused until its removal here. The Morning View analyzer's Round 3 was removed with it (now a 3-round framework; the synthesis round keeps its `round_4` internal name for log continuity).

**Removed:** `oracle/` (5,535 lines), `tools/oracle_bridge.py`, `docs/reference/VANNA_SLIM_REFERENCE.md`, the `oracle` config key, and text references throughout the docs.

## Airline Play Retired (2026-08-31)

**What it was:** An early (2025) single-sector strategy module — daily symbol- and contract-level tracking for 7 airline tickers (DAL, UAL, AAL, LUV, JBLU, ALK, JETS) into two dedicated tables (`airline_symbol_tracking`, `airline_options_tracking`), run as orchestrator Step 3.3. Built around research showing 40–94% volatility spikes in airline stocks in days 8–12 of each month.

**Why it was retired:** Never traded. The general-purpose pipelines (Flow Monitor, Option Pipeline, Earnings Intel) cover the same symbols with richer data, making the dedicated tables redundant duplicates of `option_contracts`/`option_symbol_summary`. Removed: the module, Step 3.3, the performance-writer block, and both datalake tables (127K + 1.6K rows, last written 2026-08-28; preserved in that evening's full backup). The `airline_play_performance` table in performance.db keeps its historical rows. JETS remains in the FM universe as its one ETF, and the `airlines.db` sector archive (a symbol grouping, not part of the strategy) is unaffected. Step renumbering deferred.

## Emailed Morning Watchlist Retired (2026-08-31)

Step 1.6 generated a daily watchlist report and emailed it as a .docx. Ben used it purely as a "system is alive" ping; the End-of-Day Market Report and the per-strategy health reporters made it redundant, and the Morning View TUI replaced it for actual review. `morning_view/morning_views.py` was reduced to the TUI view schema it also owned (user_watchlist table + 5 SQL views, recreated after every query-DB sync). `tools/document_emailer.py` went with it — the emailed watchlist was its last caller. The `morning_views_performance` table keeps its historical rows.
