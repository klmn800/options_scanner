# Sector Archive Incident Report — 2026-04-02

## Status: RESOLVED (2026-04-03) — Hardware risk eliminated 2026-04-10 via SSD migration

Archive repairs complete, root cause identified, archive process running with fixes applied. Underlying hardware risk (mechanical HDD) eliminated 2026-04-10 by migration to Crucial BX500 2TB SATA SSD.

## System Context

- **Platform at time of incident:** Windows 10 Pro, mechanical HDD (Seagate Barracuda ST2000DM008), dual antivirus (Windows Defender + one other)
- **Platform now:** Windows 10 Pro, Crucial BX500 2TB SATA SSD (migrated 2026-04-10)
- **Database:** SQLite 3, accessed via Python `sqlite3` module
- **Architecture:** A main production database (`data/datalake.db`) accumulates intraday options data. Every Friday night, an archival process (`data/health/db_archive_sector.py`) moves aged data into per-sector SQLite archive databases in `data/sector_archive/`. There are currently 19 sector archive databases ranging from 900 MB to 13 GB.
- **Archive process:** Batch SELECT from source → INSERT OR IGNORE into sector archive → DELETE from source. Three tiers with different retention windows (15d, 30d, 90d). Processes sectors sequentially.

## Root Cause: Secondary Index Overhead on Large Archives

### The performance problem (Mar 27)

The Mar 27 archive run took 56 hours instead of the normal 6-10 hours. The bottleneck was exclusively `technology.db` (26 GB, 142 symbols). Per-batch timing from the log:

| Run Date | Tech Rows | Duration | Throughput |
|----------|-----------|----------|------------|
| Feb 27   | 1.55M     | 29 min   | 3.2M rows/h |
| Mar 6    | 1.46M     | 17 min   | 5.2M rows/h |
| Mar 13   | 2.23M     | 37 min   | 3.6M rows/h |
| Mar 20   | 1.60M     | **7h 40m** | 209K rows/h |
| Mar 27   | 2.74M     | **50h** | 55K rows/h |

The degradation started on Mar 20 (12x slowdown from the prior week) and was catastrophic by Mar 27. Only the two largest archives were affected — all other sectors ran at normal speed.

**Cause:** Each archive table had 2 secondary indexes (date + symbol). Every `INSERT OR IGNORE` required updating both indexes. The archive connections used the default SQLite page cache of **2 MB**. As technology.db grew past ~22 GB, the index B-trees exceeded what could be cached — every insert required random HDD seeks to read and write index pages. On a mechanical drive at ~100 random IOPS, this created a performance cliff.

**Key evidence from the Mar 27 log:** Technology batches 5-40 each took ~6 hours. Then batch 45 took 1.8h, and batches 50-55 took 3 minutes each. As rows were deleted, the index shrank until it fit back in cache — producing a dramatic speedup at ~73% completion. The same pattern appeared on Mar 20 (slow start, then fast after batch 5).

### The corruption (Mar 30)

A previous Claude Code session (between Mon Mar 30 07:25 and Mon Mar 30 23:28) modified `db_archive_sector.py` to add a drop-and-rebuild index strategy. This session also started a second archive run on Monday night (Mar 30 23:28) using the new code.

The Mar 30 archive log (`logs/db_archive_2026-03-30.log`) shows the first appearance of:
```
Dropped 2 indexes on flow_options_scans in airlines.db
...
Rebuilt 2 indexes in airlines.db
```

Index rebuild times on the Mar 30 run:
- airlines: 5 min rebuild
- asset_management: 23 min rebuild
- consumer_cyclical: **64 min rebuild**
- financial_services: **38 min rebuild**
- technology: **3.5 hour rebuild**

**Every archive found to be corrupt had index rebuilds in the Mar 30 run.** The rebuilds involve heavy B-tree restructuring on multi-GB files. On a mechanical HDD with dual antivirus, a brief I/O interruption during a rebuild (AV file scan, HDD head contention) can leave the B-tree in an inconsistent state.

The Mar 30 run also only completed Tier 1 (the log ends at Tier 1 completion) — it may have been interrupted.

A subsequent Claude Code session on Apr 1 made further changes (dangerous PRAGMAs: `synchronous=OFF`, `journal_mode=MEMORY`), but these were **never used on any of the corrupted archives**. The PRAGMAs were reverted to `WAL` + `synchronous=NORMAL` before the next archive run.

**Note:** The Apr 1 session's technology migration used `synchronous=OFF` + `journal_mode=MEMORY` on the new `software.db`, which was found to have 4 corrupt index entries. This is the only confirmed damage from the dangerous PRAGMAs.

## Damage Assessment (Full Integrity Check — Apr 3)

`PRAGMA integrity_check` on all 19 archives (5 hours total):

| Archive | Size | Status | Detail |
|---------|------|--------|--------|
| airlines.db | 1.2 GB | **CORRUPT** | "database disk image is malformed" |
| asset_management.db | 9.1 GB | **CORRUPT** | "database disk image is malformed" |
| financial_services.db | 9.7 GB | **CORRUPT** | Tree 491875: ~100 rowid-out-of-order + 4 btreeInitPage errors |
| software.db | 12.8 GB | **CORRUPT** | 4 stale index entry counts (data OK, indexes stale) |
| 15 other archives | various | **OK** | Full integrity check passed |

## Remediation (Apr 3)

### 1. Index removal (all archives)
All 338 secondary indexes dropped across 18 archives (consumer_cyclical already had none). Script: `data/health/drop_all_archive_indexes.py`. Archives are index-free by policy — they're write-heavy and rarely queried. Manually create indexes for one-off research queries.

### 2. software.db fix
`REINDEX` to rebuild the 4 stale index entries. Data was intact.

### 3. Corrupt archive repairs (airlines, asset_management, financial_services)
Rebuilt via rowid scan → fresh database → file swap. Script: `data/health/repair_archive.py`.
- **airlines.db:** 3.26M rows recovered, 0 skipped, 3.4 min. 1.2 GB → 1.1 GB.
- **asset_management.db:** Repaired (rowid scan, no data loss).
- **financial_services.db:** Repaired. ~5,000 rowids in `flow_alerts` unrecoverable (1 corrupt page range). All other tables fully recovered.

consumer_cyclical.db was repaired earlier (Apr 2) via the migration/split process — confirmed clean by integrity check.

### 4. Archive process fixes (already in place from Apr 1, refined Apr 3)
- `_configure_archive_connection()`: `journal_mode=WAL`, `synchronous=NORMAL`, `cache_size=256MB`
- No secondary indexes created or rebuilt (policy: index-free archives)
- `ORDER BY rowid` for sequential HDD reads
- Dead code cleanup: removed `_rebuild_archive_indexes()`, cleaned up unused `dropped_indexes` variables

### 5. Archive run (Apr 3 evening)
Running with all fixes applied. ~10M `flow_options_scans` rows to archive from datalake.db (13.7 GB). Expected completion: 6-10 hours.

## Lessons

1. **Secondary indexes on large archive files + small page cache + HDD = performance cliff.** The archive process worked fine for months while files were small. Once technology.db crossed ~22 GB, index B-trees exceeded the 2 MB default cache and every INSERT became disk-bound. The fix is permanent: no indexes on archives, 256 MB cache.

2. **Index rebuilds on multi-GB files are dangerous on HDD.** The Mar 30 session's drop-and-rebuild strategy was a reasonable performance idea but created a window for corruption during the lengthy rebuild phase. The correct fix was to drop indexes permanently, not cycle them.

3. **Don't speculate about root causes.** The initial hypothesis blamed `synchronous=OFF` PRAGMAs from Apr 1, but the timeline didn't support it. The actual cause (Mar 30 index rebuilds) was only found by examining ALL archive logs chronologically.

4. **Integrity checks should be routine, not reactive.** The corruption existed for days before discovery. A post-archive `PRAGMA quick_check` would catch problems immediately.

5. **SSD migration completed 2026-04-10.** Migrated from Seagate Barracuda ST2000DM008 HDD to Crucial BX500 2TB SATA SSD. This eliminates the HDD-related risks that caused this incident: random seek penalties, antivirus I/O contention, and mechanical degradation. HDD-era tuning in `db_archive_sector.py` (256MB cache, WAL + NORMAL, ORDER BY rowid, no secondary indexes) retained as-is — harmless on SSD and the no-indexes policy remains correct for write-heavy archives regardless of storage. Post-migration archive performance measurement pending first full archive cycle on SSD.

## Key Files

- `data/health/db_archive_sector.py` — Production archive process (fixed)
- `data/health/repair_archive.py` — General-purpose archive repair tool
- `data/health/check_archive_integrity.py` — Full integrity check across all archives
- `data/health/drop_all_archive_indexes.py` — Bulk index removal tool
- `data/health/migrate_consumer_cyclical_split.py` — Split migration with corruption handling
- `data/health/migrate_technology_split.py` — Completed technology split migration
- `logs/db_archive_2026-03-27.log` — The 56-hour run (performance problem)
- `logs/db_archive_2026-03-30.log` — The index rebuild run (corruption source)
