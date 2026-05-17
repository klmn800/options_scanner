# Sector Archive Migration Checklist

**Migration from:** Expiration-based monthly archiving (`db_archive_expired.py`)
**Migration to:** Sector-based three-tier archiving (`db_archive_sector.py`)
**Date:** 2025-10-28
**Status:** Ready for production deployment

> **⚠️ HISTORICAL DOCUMENT — not current state.** This checklist describes the original migration to sector-based archiving in 2025-10. The tier policy has since evolved (notably P028 in 2026-05-15 cut tier1 to 7d, migrated summary tables to tier3 with 300d override, and added `flow_daily_aggregates`).
>
> For current tier policy, see:
> - `data/health/db_archive_sector.py` (canonical — `TIER_POLICIES` dict + module docstring)
> - `data/sector_archive/README.md` (archive consumer view)
> - `data/health/DATABASE_HEALTH_WORKFLOWS.md` (workflow context)
>
> Use this file only as a historical record of how sector archiving was originally introduced.

---

## Pre-Migration Verification

### ✅ Completed Checks
- [x] **Source Database Configuration** - Changed from `TEST_SOURCE_DB` to `DEFAULT_SOURCE_DB` (datalake.db)
- [x] **Sector Coverage** - Verified all symbols have sector mapping (query returned 0 unmapped symbols)
- [x] **Archive Directory** - `data/sector_archive/` exists with sector databases
- [x] **Sector Optimization** - Created standalone `db_optimize_sectors.py` for post-archive cleanup
- [x] **Main.py Integration** - Updated Friday archive module to use sector archiving

### 📋 Pre-Deployment Tasks

- [ ] **Dry-run analysis** - Verify archive volumes against production database:
  ```bash
  python data/health/db_archive_sector.py --all-tiers --dry-run
  ```
  Expected output: Row counts for each tier, sectors affected, disk space estimate

- [ ] **Disk space check** - Ensure sufficient space for dual archiving period:
  ```bash
  # Check current archive sizes
  dir data\archive_*.db  # Old monthly archives
  dir data\sector_archive\*.db  # New sector archives

  # Estimate total space needed (both systems will coexist initially)
  ```

- [ ] **Backup production database** - Safety checkpoint before first run:
  ```bash
  python data/health/db_backup.py
  ```

---

## Archive Strategy Comparison

### Old System (db_archive_expired.py)
**Output:** Monthly files (`archive_2025_09.db`, `archive_2025_10.db`, etc.)

**Strategy:** Expiration-based
- Contracts archived when `expiration_date < cutoff`
- Cutoff logic: Before 4 PM = previous days, After 4 PM = include today
- Retention tables (90-day): `options_symbol_summary`, `option_symbol_summary`

**Tables Archived:**
- `flow_options_scans` (by expiration_date)
- `option_contracts` (by expiration_date)
- `flow_alerts` (by expiration_date)
- `alert_contract_tracking` (by expiration_date + foreign keys)
- Summary tables (time-based retention)

### New System (db_archive_sector.py)
**Output:** Sector files (`airlines.db`, `technology.db`, `financials.db`, etc.)

**Strategy:** Three-tier time-based retention
- **Tier 1 (15 days, MOVE):** `flow_options_scans`, `flow_alerts` (copy mode)
- **Tier 2 (30 days, MOVE):** `option_contracts`, `option_symbol_summary`, `flow_symbol_summary`
- **Tier 3 (90 days, COPY):** Reference data (prices, earnings, news, market)

**Routing:** Symbol-based sector routing via `symbol_metadata.archive_db`

**Special Cases:**
- `market_daily_summary` → copied to ALL sectors
- `news_articles` → routed by `symbols_mentioned` JSON parsing
- `flow_alerts` → COPY mode (preserves in production for reporting)

---

## Key Differences

### 1. Archive Destination Changes
- **Old:** Data grouped by expiration month
- **New:** Data grouped by company sector
- **Impact:** Different organization, easier sector-specific analysis

### 2. Retention Logic Changes
- **Old:** Expiration-based (contracts) + 90-day (summaries)
- **New:** Unified time-based tiers (15d/30d/90d)
- **Impact:** May archive different data volumes, especially for long-dated options

### 3. Data Lifecycle Changes
- **Old:** All data moved to archives (deleted from production)
- **New:** Mixed MOVE/COPY (Tier 3 keeps reference data in production longer)
- **Impact:** `flow_alerts` stays in production indefinitely (reporting needs)

### 4. Cleanup Procedures
- **Old:** VACUUM + ANALYZE on production database only
- **New:** VACUUM production + ANALYZE all sector archives
- **Impact:** More databases to maintain, but better query performance across archives

---

## Friday Archive Workflow

### Execution Sequence (Post-Collection)
```
6:35 AM  - Morning OID Collection
7:20 AM  - Query Database Sync #1
         - Morning Views (email watchlist)
9:15 AM  - Flow Monitor starts
4:30 PM  - Flow Monitor post-market analysis
5:00 PM  - Evening OID Collection
5:45 PM  - Query Database Sync #2
         - Earnings Alert Processing
         - Airline Play Tracking
7:00 PM  - Query Database Sync #3 (complete dataset)
         - 60-second lock release pause
         - Database Backup (daily) → datalake_backup.db
         - Log Analysis

FRIDAY ONLY:
7:30 PM  - Archive operations begin (if Friday):
           1. Run db_archive_sector.py --all-tiers
           2. Tier 1 archive (15-day data)
           3. Tier 2 archive (30-day data)
           4. Tier 3 archive (90-day reference data)
           5. Optimize sector archives (ANALYZE)
           6. VACUUM production database

~11:00 PM - Weekly Backup → datalake_backup_weekly.db

MONDAY:
5:45 AM  - Archive timeout cutoff (if still running)
6:35 AM  - Morning OID starts (needs clean database)
```

### Timeout Handling
- **Cutoff:** Monday 5:45 AM (10-minute buffer before OID starts at 6:35 AM)
- **Calculation:** Friday ~6:30 PM → Monday ~5:45 AM = ~59 hours available
- **Behavior:** Graceful shutdown if approaching cutoff (not hard-killed)
- **Recovery:** Will resume next Friday if incomplete

---

## Main.py Changes Summary

### Updated Code (main.py:1449-1566)

**Function:** `run_database_archive_with_timeout()`

**Key changes:**
1. **Script path** (line 1478):
   ```python
   # OLD:
   archive_script = os.path.join(project_root, 'data', 'health', 'db_archive_expired.py')

   # NEW:
   archive_script = os.path.join(project_root, 'data', 'health', 'db_archive_sector.py')
   ```

2. **Command arguments** (line 1507-1511):
   ```python
   # OLD:
   result = subprocess.run([
       sys.executable, archive_script,
       '--no-interaction',
       '--time-limit', str(int(timeout_seconds))
   ], ...)

   # NEW:
   result = subprocess.run([
       sys.executable, archive_script,
       '--all-tiers',  # Run Tier 1 + Tier 2 + Tier 3
       '--time-limit', str(int(timeout_seconds))
   ], ...)
   ```

3. **Status messaging** (line 1467-1475):
   - Updated to reflect sector archiving and three-tier strategy
   - Changed "expired contracts" to "sector-specific databases"
   - Added tier descriptions (T1/T2/T3 with retention days)

---

## Post-Migration Tasks

### Immediate (First Friday After Deployment)

- [ ] **Monitor archive execution** - Watch first Friday run for:
  - Archive duration (should complete in allocated time)
  - Disk space usage (both archive systems active)
  - Sector database file sizes (verify reasonable growth)
  - Production database cleanup (VACUUM reclaims space)

- [ ] **Verify sector archives** - Check data integrity:
  ```bash
  # List all sector archives and sizes
  python data/health/db_optimize_sectors.py --list

  # Spot-check data in a sector archive
  python tools/direct_db_query.py --db data/sector_archive/airlines.db --sql "SELECT COUNT(*) FROM flow_options_scans"
  python tools/direct_db_query.py --db data/sector_archive/airlines.db --sql "SELECT COUNT(*) FROM option_contracts"
  ```

- [ ] **Compare archive outputs** - Ensure data parity:
  ```sql
  -- Check if same data archived by both systems (first overlap week)
  -- Old system: archive_2025_10.db
  -- New system: sector archives (airlines.db, technology.db, etc.)
  ```

### Week 2-4 (Validation Period)

- [ ] **Monitor weekly execution** - Track 3-4 consecutive Friday runs:
  - Consistent completion times
  - No database lock conflicts
  - Sector archive growth rates
  - Production database size trends

- [ ] **Verify sector optimization** - Check `db_optimize_sectors.py` runs successfully:
  ```bash
  # Manual test
  python data/health/db_optimize_sectors.py

  # Check if it's being called by archive script (look for output)
  ```

- [ ] **Test archive queries** - Verify sector archives are usable:
  ```bash
  # Example: Query airlines sector for historical analysis
  python tools/direct_db_query.py --db data/sector_archive/airlines.db \
    --sql "SELECT symbol, COUNT(*) FROM option_contracts WHERE trade_date >= '2025-10-01' GROUP BY symbol"
  ```

### Month 2+ (Cleanup Phase)

- [ ] **Evaluate old archives** - Once confident in new system (4+ successful Friday runs):
  - Review old monthly archives (`archive_YYYY_MM.db`)
  - Identify overlap period (same data in both systems)
  - Plan cleanup strategy (keep for redundancy or delete to reclaim space)

- [ ] **Document archive retention policy:**
  - How long to keep old monthly archives?
  - Disk space budget for sector archives?
  - Backup strategy for sector archives?

---

## Rollback Plan (If Needed)

If critical issues arise with sector archiving:

1. **Stop Friday archive** - Comment out archive call in main.py:
   ```python
   # Line 1875 in main.py
   # archive_success = self.run_database_archive_with_timeout()
   archive_success = True  # Temporarily disabled
   ```

2. **Revert to old system:**
   ```python
   # Restore db_archive_expired.py in main.py
   archive_script = os.path.join(project_root, 'data', 'health', 'db_archive_expired.py')

   # Restore old command args
   result = subprocess.run([
       sys.executable, archive_script,
       '--no-interaction',
       '--time-limit', str(int(timeout_seconds))
   ], ...)
   ```

3. **Investigate issues** - Review logs for root cause:
   - Archive script errors
   - Database locking conflicts
   - Timeout issues
   - Sector routing problems

4. **Fix and redeploy** - Address issues in db_archive_sector.py and retry next Friday

---

## Success Criteria

Migration considered successful when:

1. ✅ **Execution:** Archive runs to completion within timeout window (Friday 6:30 PM → Monday 5:45 AM)
2. ✅ **Data Integrity:** Sector archives contain expected tables and row counts
3. ✅ **Performance:** Production database size decreases after archiving (VACUUM working)
4. ✅ **Query Performance:** Sector archives respond to queries efficiently (ANALYZE working)
5. ✅ **Stability:** 4+ consecutive Friday runs without failures or manual intervention
6. ✅ **Cleanup:** Production database VACUUM completes successfully each Friday
7. ✅ **Optimization:** Sector archive ANALYZE completes successfully each Friday

---

## Questions & Decisions

### Resolved
- ✅ Source database hardcoding fixed (using datalake.db now)
- ✅ Sector coverage verified (all symbols mapped)
- ✅ Sector cleanup separated into standalone script
- ✅ Main.py integration completed

### Outstanding
- ⏳ **Disk space management:** How long to keep old monthly archives alongside new sector archives?
- ⏳ **Tier 3 cleanup strategy:** When to delete reference data from production after copying to sectors?
- ⏳ **Sector archive backup:** Should sector archives be included in backup strategy?

---

## Related Files

### Archive Scripts
- `data/health/db_archive_sector.py` - New sector-based archiving (production)
- `data/health/db_archive_expired.py` - Old expiration-based archiving (deprecated)
- `data/health/db_optimize_sectors.py` - Standalone sector optimization

### Orchestration
- `main.py` - Main orchestrator (Friday archive integration)
  - Function: `run_database_archive_with_timeout()` (lines 1449-1566)
  - Function: `calculate_archive_timeout()` (lines 1723-1751)

### Documentation
- `data/sector_archive/README.md` - Sector archive design and routing logic
- `data/sector_archive/MIGRATION_CHECKLIST.md` - This file

---

## Notes

- Old monthly archives remain in `data/` directory until manual cleanup
- Sector archives accumulate in `data/sector_archive/` directory
- Both systems can coexist during validation period (no conflicts)
- `flow_alerts` table stays in production (copy mode in Tier 1) for reporting
- Market data (`market_daily_summary`) copied to ALL sector archives for context

---

**Migration prepared by:** Claude Code
**Migration approved by:** [Pending Ben's approval]
**First production run:** [Next Friday after approval]
