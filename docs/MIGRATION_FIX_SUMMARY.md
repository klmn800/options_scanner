# Migration Scripts Fix Summary

**Date:** October 22, 2025
**Issue:** Data loss in sector migration due to duplicate detection failure
**Status:** ✅ FIXED - All 13 migration scripts patched

---

## Root Cause Analysis

### What Happened

1. **First migration run** (asset_management):
   - User ran `migrate_asset_management_archive.py` with 28 symbols (including XL* ETFs)
   - Script successfully inserted 276,239 rows into `data/legacy/asset_management.db`
   - User hit Ctrl+C during DELETE operation (interrupted at line 183)
   - **Result:** Data copied to destination, source archive partially intact

2. **Second migration run** (asset_management):
   - User corrected symbol list to 17 symbols (removed XL* ETFs)
   - Script tried to insert 223,420 rows
   - ALL rows were duplicates (PRIMARY KEY collision: `contract_hash, scan_timestamp`)
   - `INSERT OR IGNORE` silently skipped all 223,420 rows (0 inserted)
   - Script printed WARNING but **continued to DELETE** all 223,420 rows
   - **Result:** DATA LOSS - 223,420 rows deleted from archive, but data still exists in destination

### Critical Bugs Identified

#### Bug #1: Missing Abort Logic (Lines 178-180)
```python
# OLD CODE - DANGEROUS
if inserted != count_to_migrate:
    print(f"    WARNING: Expected to insert {count_to_migrate} rows, but inserted {inserted}")
    print(f"    This is OK if data already existed from another archive (duplicates skipped)")

# Delete from source  ← CONTINUES EVEN WHEN inserted == 0!
```

**Problem:** Script warns about 0 insertions but still deletes from source archive.

**Fix:** Raise exception when `inserted == 0` before deletion:
```python
# NEW CODE - SAFE
if inserted == 0 and count_to_migrate > 0:
    print(f"    CRITICAL ERROR: 0 rows inserted out of {count_to_migrate} expected!")
    raise Exception(
        f"ZERO ROWS INSERTED! Cannot proceed with deletion. "
        f"Expected {count_to_migrate} rows, but none were inserted into {dest_table_name}."
    )
```

#### Bug #2: Broken PRIMARY KEY Creation (Lines 94-106)
```python
# OLD CODE - WRONG
for col in columns_info:
    pk = " PRIMARY KEY" if col[5] else ""  # Creates MULTIPLE single-column PKs!
    column_defs.append(f"{col_name} {col_type}{not_null}{pk}")

create_sql = f"CREATE TABLE {new_table_name} ({', '.join(column_defs)})"
```

**Problem:**
- For composite PRIMARY KEY `(contract_hash, scan_timestamp)`, this creates TWO separate single-column PKs
- Result: `INSERT OR IGNORE` silently fails for all rows

**Fix:** Use full CREATE TABLE statement from source:
```python
# NEW CODE - CORRECT
source_cursor.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
    (table_name,)
)
create_sql = source_cursor.fetchone()[0]
create_sql = create_sql.replace(f"CREATE TABLE {table_name}", f"CREATE TABLE {new_table_name}", 1)
```

---

## Fixes Applied

### All 13 Migration Scripts Patched

✅ **Primary group (airlines + asset_management):**
- `migrate_airlines_archive.py` (manually fixed)
- `migrate_asset_management_archive.py` (manually fixed)

✅ **Sector group (batch fixed via `batch_fix_migrations.py`):**
- `migrate_basic_materials_archive.py`
- `migrate_communication_services_archive.py`
- `migrate_consumer_cyclical_archive.py`
- `migrate_consumer_defensive_archive.py`
- `migrate_energy_archive.py`
- `migrate_financial_services_archive.py`
- `migrate_healthcare_archive.py`
- `migrate_industrials_archive.py`
- `migrate_real_estate_archive.py`
- `migrate_technology_archive.py`
- `migrate_utilities_archive.py`

### Changes Made

**1. PRIMARY KEY Preservation**
- Location: `create_table_if_not_exists()` function
- Lines: ~94-106
- Change: Use full CREATE TABLE statement instead of building from column info

**2. Abort-on-Zero-Insert Logic**
- Location: `migrate_table_data()` function
- Lines: ~178-189
- Change: Raise exception if `inserted == 0` before deletion
- Added: Debug output with failed row sample

---

## Recovery Status

### Backups Available
- ✅ `data/archive_2025_07.db` - Restored from backup (7,086,920 rows, 818 symbols)
- ✅ `data/archive_2025_07 - bad.db` - Failed migration state (6,803,971 rows, 797 symbols)
- ✅ `data/legacy/asset_management.db` - Contains migrated data (276,239 rows, 25 symbols)

### Data Integrity
- ✅ No actual data loss - all 223,420 asset management rows exist in `asset_management.db`
- ✅ Extra 52,819 rows from XL* ETFs also in `asset_management.db` (from first run)
- ✅ Source archive restored to pre-migration state

---

## Testing Recommendations

### Before Re-Running Asset Management Migration

1. **Delete corrupted destination:**
   ```bash
   del data\legacy\asset_management.db
   ```

2. **Verify source archive:**
   ```bash
   python tools/direct_db_query.py --db data/archive_2025_07.db --sql "SELECT COUNT(*) FROM option_contracts WHERE symbol IN ('BEN', 'BK', 'BX', 'SPY', 'QQQ')"
   ```
   Expected: ~223,420 rows

3. **Run migration:**
   ```bash
   python tools/migrate_asset_management_archive.py
   ```

4. **Expected behavior:**
   - Creates fresh `asset_management.db`
   - Inserts 223,420 rows (all 17 symbols)
   - Deletes 223,420 rows from archive
   - No errors

### If Duplicate Detection Occurs

**Scenario:** If you accidentally run migration twice, the script will now:

1. Detect 0 inserted rows
2. Print diagnostic information:
   ```
   CRITICAL ERROR: 0 rows inserted out of 223420 expected!
   First failed row sample: (...)
   Destination table: option_contracts
   Source table: option_contracts
   ```
3. **ABORT with exception** before deletion
4. Source archive remains intact ✅

---

## Future Prevention

### Safe Migration Practices

1. **Check destination before migration:**
   ```python
   # Migration scripts should check if destination already has data
   cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE symbol IN ({symbols})")
   existing_count = cursor.fetchone()[0]
   if existing_count > 0:
       print(f"WARNING: Destination already has {existing_count} rows for these symbols")
       # Ask for confirmation or abort
   ```

2. **Dry-run mode:**
   ```bash
   python migrate_sector.py --dry-run  # Show what would be migrated without deletion
   ```

3. **Transaction safety:**
   - All operations in transaction
   - Commit only after verification
   - Rollback on any error

### Testing Strategy

- ✅ **Prototype with airlines first** (6 symbols, small dataset)
- ✅ **Verify row counts match** (source deleted == destination inserted)
- ✅ **Check date ranges** (ensure complete coverage)
- ✅ **Test schema compatibility** (oi_daily vs option_contracts)

---

## Files Modified

### Migration Scripts (13 files)
- `tools/migrate_*.py` - All sector/industry migration scripts

### Tools Created
- `tools/batch_fix_migrations.py` - Automated fix application script

### Documentation
- `docs/MIGRATION_FIX_SUMMARY.md` (this file)

---

## Approval for Production Use

**Status:** ✅ READY FOR TESTING

**Recommended Next Steps:**
1. Delete `data/legacy/asset_management.db`
2. Run `python tools/migrate_asset_management_archive.py`
3. Verify successful migration (no errors, correct row counts)
4. Proceed with remaining sector migrations

**Critical Reminder:** Keep backups of all archive databases until full migration validated!

---

**Fixed by:** Claude Code
**Reviewed by:** Ben
**Date:** October 22, 2025
