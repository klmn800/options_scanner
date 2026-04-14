# Sector Archive Deployment Summary

**Date:** 2025-10-28
**Status:** ✅ Ready for Production
**First Run:** Next Friday (automatic)

---

## Changes Made

### 1. Fixed Production Database Configuration
**File:** `data/health/db_archive_sector.py`
**Line:** 55
```python
# BEFORE (pointed to test database):
SOURCE_DB = TEST_SOURCE_DB  # 'archive_2025_10.db'

# AFTER (points to production):
SOURCE_DB = DEFAULT_SOURCE_DB  # 'datalake.db'
```

### 2. Created Standalone Sector Optimizer
**New File:** `data/health/db_optimize_sectors.py`
- Runs ANALYZE on all sector archive databases
- Maintains query performance without full VACUUM
- Called automatically by archive script after archiving
- Can be run manually for maintenance

**Features:**
```bash
python data/health/db_optimize_sectors.py                  # All sectors
python data/health/db_optimize_sectors.py --sector airlines  # Specific sector
python data/health/db_optimize_sectors.py --list           # Show available sectors
```

### 3. Integrated Sector Optimization into Archive Workflow
**File:** `data/health/db_archive_sector.py`
**Lines:** 1375-1380

**Archive sequence:**
1. Run Tier 1 → Tier 2 → Tier 3 archiving
2. Call `db_optimize_sectors.py` (ANALYZE all sector archives)
3. VACUUM production database (reclaim space from deletions)

### 4. Updated Main Orchestrator
**File:** `main.py`
**Function:** `run_database_archive_with_timeout()` (lines 1449-1566)

**Changes:**
- Script path: `db_archive_expired.py` → `db_archive_sector.py`
- Command args: `--no-interaction` → `--all-tiers`
- Status messaging: Updated for sector archiving and three-tier strategy
- Version bump: 2.4 → 2.5

**New docstring section:**
```python
Friday Night Archive:
  - Three-tier retention strategy (sector-based routing)
  - Tier 1 (15d MOVE): flow_options_scans, flow_alerts (copy mode)
  - Tier 2 (30d MOVE): option_contracts, option_symbol_summary, flow_symbol_summary
  - Tier 3 (90d COPY): historical_prices, earnings_events, news_*, market_daily_summary
  - Output: data/sector_archive/{sector}.db (airlines, technology, etc.)
  - Timeout: Friday 6:30 PM → Monday 5:45 AM cutoff (59 hours)
  - Post-archive: Optimize sector archives (ANALYZE) + VACUUM production
```

### 5. Updated Documentation
**File:** `CLAUDE.md`

**Added sections:**
- Database Backup & Archive Strategy (expanded)
- Database Health Scripts (new section)
- Database Archiving and Optimization commands
- Archive tiers and recovery scenarios

**Key additions:**
```markdown
### Database Backup & Archive Strategy
**Archives (Friday nights only):**
3. **Sector Archives** (`data/sector_archive/{sector}.db`)
   - Three-tier retention strategy (15d/30d/90d)
   - Routes data by symbol sector (airlines, technology, etc.)
   - Runs Friday 6:30 PM → Monday 5:45 AM cutoff
   - See `data/sector_archive/MIGRATION_CHECKLIST.md` for details

**Archive Tiers:**
- **Tier 1 (15d MOVE):** `flow_options_scans`, `flow_alerts` (copy mode)
- **Tier 2 (30d MOVE):** `option_contracts`, `option_symbol_summary`, `flow_symbol_summary`
- **Tier 3 (90d COPY):** Reference data (prices, earnings, news, market)
```

### 6. Created Migration Documentation
**New Files:**
- `data/sector_archive/MIGRATION_CHECKLIST.md` - Full migration guide with validation tasks
- `data/sector_archive/DEPLOYMENT_SUMMARY.md` - This file

---

## Dry-Run Results (2025-10-28)

**Analysis completed in 16 seconds:**

### Volume Summary
- **Total rows to archive:** 11,389,444 rows
- **Total rows to delete:** 10,528,847 rows
- **Total rows to copy:** 860,597 rows (stay in production)
- **Sectors affected:** All 13 sectors ✅

### Breakdown by Tier

**Tier 1 (15-day MOVE):** 10,308,381 rows
- `flow_options_scans`: 10,308,055 rows
- `flow_alerts`: 326 rows (COPY mode - stays in production)

**Tier 2 (30-day MOVE):** 220,792 rows
- `option_contracts`: 168,750 rows
- `option_symbol_summary`: 50,601 rows
- `flow_symbol_summary`: 1,441 rows

**Tier 3 (90-day COPY):** 860,271 rows
- `historical_prices`: 833,756 rows
- `earnings_events`: 26,493 rows
- `market_daily_summary`: 22 rows (copied to all 13 sectors)

### Sector Distribution
**Top 5 sectors by volume (Tier 1):**
1. Technology: 2,342,310 rows (23%)
2. Consumer Cyclical: 1,628,550 rows (16%)
3. Healthcare: 1,011,939 rows (10%)
4. Financial Services: 959,898 rows (9%)
5. Industrials: 863,885 rows (8%)

---

## System Behavior

### Friday Archive Workflow
```
Friday 6:30 PM  - Archive begins (automatic)
                  │
                  ├─ Tier 1: ~3-5 hours (10.3M rows)
                  ├─ Tier 2: ~30 minutes (221K rows)
                  ├─ Tier 3: ~1 hour (860K rows)
                  │
                  ├─ Optimize sector archives (~15 min, 13 sectors)
                  └─ VACUUM production (~30 min, reclaim ~5 GB)

Friday ~11:30 PM - Archive completes
                   Weekly backup starts (datalake_backup_weekly.db)

Monday 5:45 AM   - Timeout cutoff (if still running)
                   Graceful shutdown before Morning OID at 6:35 AM
```

**First run will be slower** due to:
- Large backlog (15 days of flow data)
- Creating new sector archive files
- First-time VACUUM after major deletion

**Subsequent Fridays** will process only 7 days of new data (~50% faster).

### Timeout Handling
- **Available time:** Friday 6:30 PM → Monday 5:45 AM = ~59 hours
- **Safety buffer:** 10 minutes before Morning OID starts
- **Behavior:** Graceful shutdown if approaching cutoff
- **Recovery:** Resumes next Friday if incomplete

---

## Pre-Deployment Verification

### ✅ Completed Checks
- [x] SOURCE_DB configuration fixed (using datalake.db)
- [x] Sector coverage verified (all 800 symbols mapped)
- [x] Dry-run analysis successful (11.4M rows across 13 sectors)
- [x] Sector optimization script created and integrated
- [x] Main.py integration complete
- [x] Documentation updated (CLAUDE.md, main.py, migration guide)
- [x] Disk space confirmed (plenty available)

### No Action Required
System is configured to run automatically Friday night. No manual intervention needed.

---

## Monitoring First Run

### What to Watch Friday Night
1. **Start time:** Should begin around 6:30 PM (after daily backup)
2. **Console output:** Shows tier progress, sector routing, row counts
3. **Duration:** Expect 6-7 hours for first run
4. **Completion:** Should finish before midnight Friday

### Log Files to Check
```bash
# Main orchestrator log
logs/orchestrator_2025-11-01.log  # (Friday's date)

# Archive script output (captured by orchestrator)
# Look for these patterns:
# - "TIER 1: 15-day retention, MOVE mode"
# - "TIER 2: 30-day retention, MOVE mode"
# - "TIER 3: 90-day retention, COPY mode"
# - "SECTOR ARCHIVE OPTIMIZATION"
# - "VACUUM complete"
```

### Verification Commands (Saturday Morning)
```bash
# List sector archives created
python data/health/db_optimize_sectors.py --list

# Spot-check data in a sector archive
python tools/direct_db_query.py --db data/sector_archive/airlines.db \
  --sql "SELECT COUNT(*) FROM flow_options_scans"

python tools/direct_db_query.py --db data/sector_archive/technology.db \
  --sql "SELECT COUNT(*) FROM option_contracts"

# Check production database size (should be smaller)
# Compare with previous Friday backup size
dir data\datalake.db
dir data\datalake_backup.db
```

---

## Success Criteria

First run considered successful when:

1. ✅ Archive completes within timeout window (Friday 6:30 PM → Monday 5:45 AM)
2. ✅ All 13 sector archives created in `data/sector_archive/`
3. ✅ Row counts match dry-run expectations (~11.4M rows archived)
4. ✅ Production database size decreases (VACUUM working)
5. ✅ Sector archives respond to queries (ANALYZE working)
6. ✅ Weekly backup created (datalake_backup_weekly.db)
7. ✅ Monday Morning OID starts normally at 6:35 AM

---

## Rollback Plan (If Needed)

If critical issues arise:

1. **Let Friday complete** - Don't interrupt mid-archive
2. **Review logs Saturday** - Identify specific failure point
3. **Revert main.py** (if necessary):
   ```python
   # Line 1478 in main.py
   archive_script = os.path.join(project_root, 'data', 'health', 'db_archive_expired.py')

   # Lines 1507-1511 in main.py
   result = subprocess.run([
       sys.executable, archive_script,
       '--no-interaction',
       '--time-limit', str(int(timeout_seconds))
   ], ...)
   ```
4. **File issue** - Document what went wrong
5. **Fix and retry** - Address issues for next Friday

---

## Next Steps

### Immediate (This Friday)
- System will run automatically
- No user intervention required
- Monitor logs if desired (optional)

### Week 1 Post-Deployment (Next Saturday)
- Verify sector archives created successfully
- Check production database size reduction
- Spot-check archived data integrity

### Weeks 2-4 (Validation Period)
- Track 3-4 consecutive Friday runs
- Verify consistent completion times
- Monitor sector archive growth rates

### Month 2+ (Cleanup Phase)
- Evaluate old monthly archives (`archive_YYYY_MM.db`)
- Plan cleanup strategy (keep for redundancy or delete)
- Document long-term retention policy

---

## Files Changed

### Modified Files (4)
1. `data/health/db_archive_sector.py` - Fixed SOURCE_DB, added sector optimization call
2. `main.py` - Updated archive script path and args, new version 2.5
3. `CLAUDE.md` - Added archive strategy, commands, documentation links

### New Files (3)
1. `data/health/db_optimize_sectors.py` - Standalone sector optimization script
2. `data/sector_archive/MIGRATION_CHECKLIST.md` - Complete migration guide
3. `data/sector_archive/DEPLOYMENT_SUMMARY.md` - This file

### Deprecated Files (1)
- `data/health/db_archive_expired.py` - No longer called by main.py (kept for reference)

---

## Contact & Support

**Questions or issues?**
- Check `data/sector_archive/MIGRATION_CHECKLIST.md` for detailed troubleshooting
- Review Friday night logs in `logs/orchestrator_YYYY-MM-DD.log`
- Consult `data/sector_archive/README.md` for sector routing logic

**System ready for automatic deployment.**
No further action required before Friday.

---

**Deployment prepared by:** Claude Code
**Deployment approved by:** Ben
**First production run:** Next Friday (automatic)
**Status:** ✅ Ready
