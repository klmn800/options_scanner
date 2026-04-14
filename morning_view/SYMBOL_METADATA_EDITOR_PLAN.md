# Symbol Metadata & Archive Manager - Implementation Plan

**Created:** 2025-10-29
**Completed:** 2025-10-30
**Status:** ✅ Complete
**Location:** Admin Mode → Symbol Metadata & Archives (Menu Option 5)

---

## Overview

TUI admin screen for managing symbol archive assignments and sector archive databases. Allows Ben to reassign symbols to different archives (e.g., moving NVDA from "technology" to custom "airline_suppliers" archive) and create new sector databases on demand.

---

## Features

### 1. Edit Symbol Archive Assignment
- **Lookup:** Enter symbol → display current `archive_db` value and company info
- **Edit:** Dropdown selection from available archives (dynamically populated)
- **Save:** Update `symbol_metadata.archive_db` in production database
- **Result:** Future archive operations (Friday nights) route symbol to new database

### 2. Migrate Symbol Historical Data
- **Triggered:** Optional after archive assignment change OR standalone operation
- **Estimate:** Show row counts across 12 tables before migration
- **Data Gap Detection:** Automatically checks target archive for missing metadata and insufficient historical prices (<30 days)
- **Backfill Options:** Interactive toggles (B/P keys) to enable FMP API backfill for missing data
- **Execute:** Launch migration script in external Windows terminal with optional backfill flags
- **Tables:** 12 normalized tables (flow_options_scans, option_contracts, symbol_metadata, etc.)
- **Safety:** Copy → Verify → Delete pattern with full logging

### 3. Create New Sector Archive
- **Input:** Archive name (lowercase, underscores only)
- **Validation:** Check uniqueness, proper format (regex: `^[a-z][a-z0-9_]*$`)
- **Schema:** Copy 13 table schemas from `datalake.db`
- **Auto-Populate:** Always copies `market_daily_summary` table for research context
- **Output:** New database at `data/sector_archive/{name}.db` ready for use
- **Availability:** Immediately appears in dropdown for symbol assignment

### 4. View Archive Statistics
- **Display:** Table showing all sector archives
- **Columns:** Archive name, symbol count, file size, last updated
- **Data sources:**
  - Symbol count: `SELECT COUNT(*) FROM symbol_metadata WHERE archive_db = '{name}'`
  - File size: `os.path.getsize()`
  - Last updated: File modification timestamp

---

## Database Schema

### 13 Normalized Tables (copied to new archives)
1. `symbol_metadata` - Company fundamentals and sector classification
2. `market_daily_summary` - Daily market metrics and regime data
3. `historical_prices` - OHLC price data
4. `flow_options_scans` - Intraday contract scans (36 columns)
5. `option_contracts` - Daily OI tracking (66 columns)
6. `flow_alerts` - Flow alerts with profitability (41 columns)
7. `flow_symbol_summary` - Alert-focused daily metrics (12 columns)
8. `option_symbol_summary` - Symbol-level OI/IV summaries (93 columns)
9. `earnings_events` - Earnings archive with trading journal
10. `earnings_upcoming` - Pending earnings calendar
11. `news_articles` - News article text and metadata
12. `news_symbol_sentiment` - Per-symbol sentiment scores
13. `alert_contract_tracking` - Alert profitability tracking

**Source of truth:** `data/datalake.db` via `PRAGMA table_info(table_name)`

---

## Implementation Files

### Phase 1: Standalone Scripts (CLI Testable)

#### File: `data/health/create_sector_archive.py`
**Purpose:** Create new sector archive database with aligned schema

**Features:**
- Validates archive name (format, uniqueness)
- Reads schema from `datalake.db` for 13 tables
- Creates empty database at `data/sector_archive/{name}.db`
- Optional: Copy reference tables (symbol_metadata, market_daily_summary)

**CLI Usage:**
```bash
python data/health/create_sector_archive.py --name crypto
python data/health/create_sector_archive.py --name airline_suppliers --copy-reference
python data/health/create_sector_archive.py --name crypto --dry-run
```

**Exit Codes:**
- 0: Success
- 1: Validation error (invalid name, already exists)
- 2: Database error (schema copy failed)

---

#### File: `data/health/migrate_symbol_archive.py`
**Purpose:** Move symbol's historical data from one archive to another

**Features:**
- Copies data for single symbol across 13 tables
- Copy → Verify row counts → Delete from source
- Progress logging to `logs/migration_{symbol}_{timestamp}.log`
- Dry-run mode for estimation

**CLI Usage:**
```bash
# Full migration
python data/health/migrate_symbol_archive.py --symbol NVDA --from technology --to crypto

# Migration with backfill (if data missing)
python data/health/migrate_symbol_archive.py --symbol CCJ --from technology --to nuclear --backfill-metadata --backfill-prices

# Estimate only (no writes)
python data/health/migrate_symbol_archive.py --symbol NVDA --from technology --to crypto --dry-run
```

**Backfill Features:**
- `--backfill-metadata`: Calls `fmp_symbol_metadata.py` if target archive has 0 rows in symbol_metadata
- `--backfill-prices`: Calls `fmp_historical_backfill.py --backfill-2021` if target has <30 days of historical_prices
- Backfill runs AFTER successful migration, copies data from datalake.db to target archive
- Uses `INSERT OR REPLACE` for safe updates

**Tables Migrated (in order):**
1. flow_options_scans
2. option_contracts
3. flow_alerts
4. flow_symbol_summary
5. option_symbol_summary
6. historical_prices
7. earnings_events
8. earnings_upcoming
9. news_articles
10. news_symbol_sentiment
11. alert_contract_tracking
12. symbol_metadata (single row)
13. market_daily_summary (if date-filtered rows exist)

**Safety Features:**
- Transaction-based operations
- Row count verification before deletion
- Archive database existence checks
- Symbol existence validation
- Detailed logging of all operations

**Exit Codes:**
- 0: Success (all tables migrated)
- 1: Validation error (missing archive, symbol not found)
- 2: Migration error (copy/verify/delete failed)

---

### Phase 2: TUI Integration

#### File: `morning_view/admin_data.py` (additions)
**New Functions:**

```python
def get_symbol_metadata(symbol: str) -> Optional[Dict]:
    """
    Get symbol's archive_db, company name, sector, industry.

    Returns:
        Dict with: symbol, company_name, sector, industry, archive_db
        None if symbol not found
    """

def update_symbol_archive(symbol: str, new_archive: str) -> Tuple[bool, str]:
    """
    Update symbol's archive_db field in datalake.db.

    Args:
        symbol: Stock ticker
        new_archive: New archive database name (e.g., "crypto")

    Returns:
        (True, "Success message") or (False, "Error message")
    """

def get_available_archives() -> List[str]:
    """
    List all sector archives from filesystem AND database.

    Returns:
        Sorted list of archive names (e.g., ["airlines", "crypto", "technology"])

    Implementation:
        - Scan data/sector_archive/*.db files
        - Query DISTINCT archive_db from symbol_metadata
        - Return union, sorted
    """

def get_archive_stats() -> List[Dict]:
    """
    Get statistics for all sector archives.

    Returns:
        List of dicts with:
            - archive_name: str
            - symbol_count: int (from symbol_metadata)
            - file_size_bytes: int (from os.path.getsize)
            - file_size_human: str (e.g., "1.5 GB")
            - last_modified: str (ISO format)
    """

def estimate_migration_rows(symbol: str, from_archive: str) -> Dict[str, int]:
    """
    Estimate row counts for symbol migration.

    Args:
        symbol: Stock ticker
        from_archive: Source archive name

    Returns:
        Dict mapping table_name → row_count
        Example: {"flow_options_scans": 45000, "option_contracts": 1200, ...}
    """
```

---

#### File: `morning_view/admin_screens/symbol_metadata_editor.py`
**Class:** `SymbolMetadataEditorScreen(Screen)`

**Main Menu (4 options):**
1. Edit Symbol Archive Assignment
2. Migrate Symbol Historical Data
3. Create New Sector Archive
4. View Archive Statistics

**Key Bindings:**
- `1` - Edit symbol
- `2` - Migrate data
- `3` - Create archive
- `4` - View stats
- `E` - Estimate migration (when on migration input form)
- `M` - Start migration (when on confirmation screen)
- `B` - Toggle metadata backfill (when on confirmation screen with missing data)
- `P` - Toggle price backfill (when on confirmation screen with insufficient data)
- `ESC` - Back to previous screen or admin menu

**User Flows:**

**Flow 1: Edit Symbol Archive**
```
Step 1: Lookup form
  Input: Symbol
  Button: [Lookup] [Cancel]

Step 2: Display + Edit form
  Display: Current archive, company info
  Dropdown: Available archives (populated from get_available_archives())
  Buttons: [Save] [Cancel]

Step 3: Save confirmation
  Execute: update_symbol_archive(symbol, new_archive)
  Notify: Success/error message
  Prompt: "Migrate historical data? [Yes] [No]"
    - Yes → Flow 2 (pre-filled)
    - No → Return to menu
```

**Flow 2: Migrate Historical Data**
```
Step 1: Input form (or pre-filled from Flow 1)
  Input: Symbol, From Archive, To Archive
  Button: [Estimate] [Cancel]
  Hotkey: E to estimate

Step 2: Confirmation display with data gap detection
  Display: Table with row counts per table (scrollable)
  Display: Total rows
  Auto-check: Missing symbol_metadata in target? (shows warning + B hotkey hint)
  Auto-check: Insufficient historical_prices (<30 days)? (shows warning + P hotkey hint)
  Display: Backfill status (ON/OFF for metadata and prices)
  Hotkey: B to toggle metadata backfill
  Hotkey: P to toggle price backfill
  Hotkey: M to start migration
  Display: "▶ Press M to START MIGRATION" (prominent, at bottom of scrollable area)

Step 3: Launch migration
  Execute: subprocess.Popen('start cmd /k python data/health/migrate_symbol_archive.py ... --backfill-metadata --backfill-prices')
  Notify: "Migration started (with metadata + prices backfill)" or basic notification
  Return to menu
```

**Flow 3: Create New Archive**
```
Step 1: Name input form
  Input: Archive name
  Display: Validation rules (lowercase, underscores)
  Button: [Create] [Cancel]

Step 2: Validation + Creation
  Validate: Name format, uniqueness
  Execute: subprocess.run(['python', 'data/health/create_sector_archive.py', '--name', name])
  Display: Real-time output (table creation progress)

Step 3: Success notification
  Notify: "Archive created: data/sector_archive/{name}.db"
  Return to menu (dropdown will now include new archive)
```

**Flow 4: View Statistics**
```
Single screen:
  Display: Table with archive stats
  Columns: Archive Name | Symbols | Size | Last Updated
  Data: From get_archive_stats()
  Button: [Refresh] [Back]
```

---

#### File: `morning_view/admin_screens/admin_menu.py` (modification)
**Change:** Add menu option 5

```python
BINDINGS = [
    Binding("1", "pipeline_control", "Pipeline Controls"),
    Binding("2", "trading_journal", "Trading Journal"),
    Binding("3", "file_browser", "File Browser"),
    Binding("4", "database_sync", "Database Sync"),
    Binding("5", "symbol_metadata", "Symbol Metadata & Archives"),  # NEW
    Binding("escape", "exit_admin", "Exit Admin Mode"),
]

def action_symbol_metadata(self) -> None:
    """Show symbol metadata editor screen"""
    from morning_view.admin_screens.symbol_metadata_editor import SymbolMetadataEditorScreen
    self.app.push_screen(SymbolMetadataEditorScreen())
```

---

## Technical Details

### Archive Name Validation
- **Regex:** `^[a-z][a-z0-9_]*$`
- **Rules:**
  - Lowercase only
  - Starts with letter (not digit or underscore)
  - Can contain underscores and numbers
  - Max 50 characters
- **Examples:**
  - ✅ Valid: `crypto`, `airline_suppliers`, `special_situations`, `tech2`
  - ❌ Invalid: `Crypto`, `_airlines`, `123tech`, `tech-stocks`

### External Terminal Launch (Windows)
```python
import subprocess
import sys

# Build command
cmd = [
    sys.executable,  # Python interpreter path
    'data/health/migrate_symbol_archive.py',
    '--symbol', symbol,
    '--from', from_archive,
    '--to', to_archive
]

# Launch in new cmd window (stays open after completion)
cmd_str = ' '.join(cmd)
subprocess.Popen(f'start cmd /k {cmd_str}', shell=True)
```

### Database Locking Strategy
- **Production DB:** `datalake.db` with WAL mode - safe for concurrent reads
- **Archive DBs:** Also use WAL mode - safe for migration operations
- **Migration pattern:** Open connection → Copy data → Close connection → Open again → Delete data
- **TUI writes:** Transaction-based with error handling for "database locked" scenarios

---

## Success Criteria

### Phase 1 Complete When:
- ✅ `create_sector_archive.py` creates valid empty archives via CLI
- ✅ `migrate_symbol_archive.py` successfully moves symbol data via CLI
- ✅ Both scripts have proper error handling and exit codes
- ✅ Log files are generated with clear progress tracking

### Phase 2 Complete When:
- ✅ Admin menu option 5 opens Symbol Metadata Editor screen
- ✅ Can lookup symbol and see current archive assignment
- ✅ Can change archive assignment via dropdown
- ✅ Can create new sector archive via TUI
- ✅ Can launch migration in external terminal window
- ✅ Can view archive statistics table
- ✅ All error cases display helpful messages (symbol not found, archive exists, etc.)

### Full System Integration When:
- ✅ Symbol reassignment via TUI affects Friday night archiving (routes to new database)
- ✅ New archives created via TUI are immediately usable by archiving scripts
- ✅ Migrated data appears in target archive and is removed from source
- ✅ No data corruption or loss during migrations

---

## Testing Plan

### Manual Testing - Phase 1
```bash
# Test 1: Create new archive
python data/health/create_sector_archive.py --name test_archive
# Verify: data/sector_archive/test_archive.db exists with 13 empty tables

# Test 2: Create duplicate (should fail)
python data/health/create_sector_archive.py --name test_archive
# Verify: Error message, exit code 1

# Test 3: Invalid name (should fail)
python data/health/create_sector_archive.py --name Test_Archive
# Verify: Error message about lowercase requirement

# Test 4: Dry-run migration
python data/health/migrate_symbol_archive.py --symbol DAL --from airlines --to test_archive --dry-run
# Verify: Shows row counts, no actual data moved

# Test 5: Full migration
python data/health/migrate_symbol_archive.py --symbol DAL --from airlines --to test_archive
# Verify: Data in test_archive, removed from airlines, log file created

# Test 6: Verify migrated data
python tools/direct_db_query.py --db data/sector_archive/test_archive.db --sql "SELECT COUNT(*) FROM option_contracts WHERE symbol='DAL'"
# Verify: Row count matches pre-migration count
```

### Manual Testing - Phase 2
```
1. Launch Morning View TUI: python morning_view/mv_main.py
2. Navigate to Admin Mode → Symbol Metadata & Archives
3. Test Edit Flow:
   - Lookup "DAL"
   - Change archive from "airlines" to "test_archive"
   - Save
   - Verify success notification
4. Test Create Flow:
   - Create archive "crypto"
   - Verify success message
   - Check filesystem: data/sector_archive/crypto.db exists
5. Test Migrate Flow:
   - Enter "NVDA" / "technology" / "crypto"
   - View estimation
   - Launch migration
   - Verify external terminal opens with live progress
6. Test View Stats:
   - View archive statistics table
   - Verify "crypto" appears with 0 symbols
   - Verify "test_archive" shows DAL (1 symbol)
```

---

## Open Questions / Decisions Made

### Q: Should migration delete source data immediately or keep for N days?
**Decision:** Delete immediately after verification. Reasoning:
- Archives are backed up weekly
- Sector archives already have backups (see `data/sector_archive/backups/`)
- Clean separation prevents confusion about "source of truth"
- User can always re-run archiving script to repopulate from datalake.db

### Q: Should create_sector_archive.py copy reference tables from datalake.db?
**Decision:** Make it optional via `--copy-reference` flag. Reasoning:
- Empty archives are faster to create
- Reference tables (symbol_metadata, market_daily_summary) get populated during first archiving run
- Optional flag allows pre-population for testing or immediate use

### Q: How to handle symbols not found in source archive during migration?
**Decision:** Treat as warning, not error. Log message but don't fail. Reasoning:
- Symbol may have been archived previously
- Friday archiving is idempotent (only moves data if present)
- User intent is "ensure symbol is in target archive" - missing data doesn't violate this

---

## Future Enhancements (Not in Scope)

- Bulk symbol reassignment (CSV import, sector-wide moves)
- Archive merge tool (combine two archives into one)
- Archive split tool (break apart large archives by sub-sector)
- Migration progress bar in TUI (requires threading/async)
- Undo migration (restore from backup)
- Archive data validation tool (check for orphaned records, missing foreign keys)

---

## Implementation Notes & Lessons Learned

### TUI Scrolling Pattern (CRITICAL)
**Problem:** Container widgets nested inside VerticalScroll don't trigger scrolling properly, causing content to be cut off.

**Solution:** Place Container **directly** inside VerticalScroll:
```python
# ✅ CORRECT - Enables scrolling
with VerticalScroll(id="metadata-scroll"):
    yield Container(id="metadata-content")

# ❌ WRONG - Blocks scrolling
with VerticalScroll(id="admin-container"):
    yield Static("[header]")
    yield Container(id="metadata-content")  # Nested too deep!
```

**Reference:** `morning_view/admin_screens/database_sync.py` uses correct pattern.

### Handling None Archive Assignment
When a symbol has `archive_db = NULL` in the database:
- Edit flow shows "Current Archive: (none)"
- Migration prompt skips (no historical data to migrate)
- Prevents crash when trying to set `Select.value = None` (use Select.clear() instead)

### Backfill Threshold
Historical prices threshold set to **30 days** (not 100+ days). Rationale:
- Most analysis needs ~20-60 days of lookback
- 30 days = 1 month of trading data
- Triggers backfill for truly sparse datasets

### ESC Navigation
Implemented multi-level back navigation:
- Main menu: ESC → Exit to admin menu
- Sub-screens: ESC → Return to main menu
- Confirmation screen: ESC → Return to input form
- Uses `_screen_stack` list to track navigation state

---

## Related Documentation

- **Sector Archive Design:** `data/sector_archive/documentation/README.md`
- **Schema Documentation:** `data/sector_archive/documentation/SCHEMA_DOCUMENTATION.md`
- **Migration History:** `data/sector_archive/documentation/MIGRATION_SUMMARY.md`
- **Database Standards:** `CLAUDE.md` → Database Standards section
- **Admin Screen Pattern:** `morning_view/admin_screens/trading_journal.py` (reference implementation)

---

## Implementation Timeline

**Phase 1 (Standalone Scripts):**
- create_sector_archive.py: ~1 hour
- migrate_symbol_archive.py: ~2 hours
- Testing: ~30 minutes

**Phase 2 (TUI Integration):**
- admin_data.py additions: ~1 hour
- symbol_metadata_editor.py: ~3 hours
- admin_menu.py integration: ~15 minutes
- Testing: ~1 hour

**Total Estimated Time:** ~8-9 hours
**Actual Time:** ~9 hours (including backfill features and UI refinements)

---

## Completion Summary

**Status:** ✅ **COMPLETE** (2025-10-30)

**Delivered Features:**
- ✅ Create new sector archives with schema alignment
- ✅ Edit symbol archive assignments with validation
- ✅ Migrate historical data with Copy→Verify→Delete pattern
- ✅ Automatic data gap detection (metadata & prices)
- ✅ Interactive backfill toggles with FMP API integration
- ✅ View archive statistics with live refresh
- ✅ External terminal window for long-running operations
- ✅ Scrollable TUI displays with proper Container nesting
- ✅ Multi-level ESC navigation
- ✅ Comprehensive error handling for edge cases (None archives, missing data)

**Testing Results:**
- Successfully migrated JETS (asset_management → airlines): 11,172 rows
- Successfully migrated BWXT (industrials → nuclear): 49,156 rows
- Successfully created "nuclear" archive with market_daily_summary
- Backfill features tested and working for NXE symbol

**Known Limitations:**
- Migration runs in external terminal (not embedded in TUI)
- No bulk symbol operations (single symbol at a time)
- No undo/rollback capability (rely on backups)
