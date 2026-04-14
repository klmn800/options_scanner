# Earnings Intelligence Admin TUI

**Status**: Planning phase (2025-10-11)
**Database**: Write access to `datalake.db` (production database)
**Purpose**: Safe, guided data management for earnings intelligence system

---

## Overview

The Admin TUI provides a dedicated interface for:
- **Pipeline management** (trigger, monitor, configure)
- **Data entry** (trading journal notes, tags, sentiment)
- **Industry leader assignment** (peer mapping configuration)
- **Database sync** (manual sync to datalake_query.db)
- **Backfill operations** (historical data gaps)
- **Data quality** (validation, cleanup, integrity checks)

**Critical Design Decision**: Separate admin operations from main TUI to:
1. Prevent accidental production database writes
2. Provide focused interface for maintenance tasks
3. Enable future user permissions (admin vs read-only users)
4. Isolate potentially destructive operations

---

## Launch Method

**Entry Point**: `morning_view/ei_admin.py` (new file)

```bash
# Launch admin TUI
python morning_view/ei_admin.py

# With debug logging
python morning_view/ei_admin.py --debug
```

**Safety Checks on Launch**:
```python
# ei_admin.py startup
def main():
    # 1. Verify datalake.db exists
    # 2. Check if production pipelines are running (warn if OID/Flow active)
    # 3. Create backup snapshot timestamp
    # 4. Load admin configuration
    # 5. Launch TUI
```

---

## Admin Main Menu

```
┌─ Earnings Intelligence Admin ─────────────────────────────┐
│                                                            │
│ ⚠️  PRODUCTION DATABASE (datalake.db)                      │
│ Last Backup: 2025-10-11 07:23 AM                          │
│                                                            │
│ 1. Pipeline Status & Controls                             │
│ 2. Trading Journal Management                             │
│ 3. Industry Leader Assignment                             │
│ 4. Database Sync to Query DB                              │
│ 5. Backfill Operations                                    │
│ 6. Data Quality & Validation                              │
│                                                            │
│ Q. Quit                                                    │
└────────────────────────────────────────────────────────────┘
```

---

## Feature 1: Pipeline Status & Controls (3-4 hours)

**Goal**: Monitor and manually trigger earnings intelligence pipelines

### Pipeline Dashboard
```
┌─ Earnings Intelligence Pipeline ──────────────────────────┐
│ Component              │ Status │ Last Run     │ Next Run │
├────────────────────────┼────────┼──────────────┼──────────┤
│ Weekly Refresh         │   ✓    │ 10/06 8:00AM │ 10/13    │
│ Daily Pipeline         │   ✓    │ 10/10 5:15PM │ Today 5PM│
│ Morning Scan           │   ✓    │ 10/11 6:32AM │ Tom 6:30A│
│ Snapshot Collection    │   ○    │ 0 in window  │ -        │
│ Post-Earnings Calc     │   ○    │ 0 at T+3     │ -        │
└────────────────────────────────────────────────────────────┘
Data: 26,635 events │ 9,250 moves │ 742 peer mappings

[R]un Now │ [L]ogs │ [C]onfigure │ [B]ack
```

### Status Indicators
- ✓ - Success (green)
- ○ - Idle/Waiting (gray)
- ⚠ - Warning (yellow)
- ✗ - Error (red)
- ⟳ - Running (cyan, animated)

### Run Now Submenu
```
┌─ Manual Pipeline Execution ───────────────────────────────┐
│ Select pipeline to run:                                    │
│                                                            │
│ 1. Weekly Refresh (60-90 min)                             │
│    Fetch upcoming earnings, archive old data, cleanup     │
│                                                            │
│ 2. Daily Pipeline (15-20 min)                             │
│    Collect snapshots, calculate moves, update summaries   │
│                                                            │
│ 3. Morning Arbitrage Scan (45-60 sec)                     │
│    Scan for IV discount opportunities                     │
│                                                            │
│ 4. Backfill Historical Data (varies)                      │
│    Fill gaps in earnings_events or earnings_moves         │
│                                                            │
│ ESC. Cancel                                                │
└────────────────────────────────────────────────────────────┘
```

### Implementation Details

**Status Detection**:
```python
def get_pipeline_status(pipeline_name: str) -> dict:
    """Get pipeline status from logs or database timestamps"""
    # Check logs/ei_*.log for last run timestamp
    # Check database tables for data freshness
    # Return: {status, last_run, next_run, record_count}
```

**Manual Execution**:
```python
def run_pipeline(pipeline_name: str):
    """Execute pipeline with progress monitoring"""
    # 1. Validate no conflicting pipelines running
    # 2. Show confirmation dialog with runtime estimate
    # 3. Launch subprocess with real-time log tail
    # 4. Display progress bar or live log output
    # 5. Show completion summary (records added/updated)
```

**Log Viewer**:
```
┌─ Pipeline Logs: Morning Arbitrage Scan ───────────────────┐
│ [2025-10-11 06:32:15] Starting arbitrage scan...          │
│ [2025-10-11 06:32:18] Found 45 upcoming earnings          │
│ [2025-10-11 06:32:23] Loaded 124 industries, 742 peers    │
│ [2025-10-11 06:32:58] Scan complete: 12 opportunities     │
│ [2025-10-11 06:33:01] High: 3 | Medium: 5 | Low: 4        │
│                                                            │
│ [SPACE] Pause │ [R]efresh │ [ESC] Close                   │
└────────────────────────────────────────────────────────────┘
```

---

## Feature 2: Trading Journal Management (3-4 hours)

**Goal**: Add, edit, delete trading notes with full text interface

### Journal Browse View
```
┌─ Earnings Trading Journal ────────────────────────────────┐
│ Your Recent Trades & Observations                          │
│                                                            │
│ Date  │ Symbol │ Type        │ Sentiment │ Tags           │
├───────┼────────┼─────────────┼───────────┼────────────────┤
│ 10/08 │ TSLA   │ Trade       │ Bullish   │ iv-crush,win   │
│ 10/05 │ AAPL   │ Observation │ Neutral   │ delayed-react  │
│ 10/01 │ NVDA   │ Trade       │ Bullish   │ sympathy,AMD   │
│ 09/28 │ JPM    │ Lesson      │ Bearish   │ breakout,loss  │
└────────────────────────────────────────────────────────────┘

[ENTER] Edit │ [A]dd Note │ [D]elete │ [F]ilter │ [B]ack
```

### Add/Edit Note Form
```
┌─ Add Trading Note: NVDA 2025-02-26 ───────────────────────┐
│ Symbol:    [NVDA                    ] [L]ookup Earnings   │
│ Date:      [2025-02-26              ]                     │
│                                                            │
│ Type:      [●] Trade  [ ] Observation  [ ] Pattern        │
│ Sentiment: [ ] Bullish  [●] Bearish  [ ] Neutral          │
│                                                            │
│ Tags (comma-separated):                                    │
│ [iv-crush, guidance-miss, sector-sympathy              ]   │
│                                                            │
│ Notes:                                                     │
│ ┌──────────────────────────────────────────────────────┐  │
│ │Sold 30DTE straddle. IV at 85%. Stock -5.1%, IV      │  │
│ │crushed to 0.41 (-34%). Winner but AMD sympathy      │  │
│ │selloff (-3.2%) was unexpected. Need to track tech   │  │
│ │correlation better next time.                        │  │
│ │                                                      │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                            │
│ [S]ave │ [C]ancel                                          │
└────────────────────────────────────────────────────────────┘
```

### Implementation Details

**Symbol/Date Lookup**:
```python
def lookup_earnings_event(symbol: str, date: str = None) -> dict:
    """Find existing earnings event or create stub"""
    # Query earnings_events for symbol/date
    # If exists: load event_id and any existing notes
    # If not exists: create new row, return new event_id
```

**Save Operation**:
```python
def save_trading_note(event_id: int, data: dict):
    """Save note to earnings_events table"""
    query = """
    UPDATE earnings_events
    SET notes = ?, tags = ?, note_type = ?, sentiment = ?,
        updated_at = CURRENT_TIMESTAMP
    WHERE event_id = ?
    """
    # Validate inputs (tags format, date validity, etc.)
    # Execute UPDATE with decimal formatting
    # Show confirmation toast
```

**Validation Rules**:
- Symbol must exist in symbol_metadata
- Date must be valid ISO format (YYYY-MM-DD)
- Tags: lowercase, comma-separated, no spaces in tag names
- Notes: max 2000 characters
- Sentiment: one of [Bullish, Bearish, Neutral]
- Type: one of [Trade, Observation, Pattern, Lesson]

---

## Feature 3: Industry Leader Assignment (2-3 hours)

**Goal**: Manage which symbols are industry leaders for peer correlation

### Industry Browser
```
┌─ Industry Leader Assignment ──────────────────────────────┐
│ Industry: Semiconductors (25 companies)                   │
│ Leaders drive sector sympathy calculations                │
│                                                            │
│ Symbol │ Name                      │ Leader? │ Mkt Cap    │
├────────┼───────────────────────────┼─────────┼────────────┤
│ NVDA   │ NVIDIA Corporation        │  [●]    │ $3.2T      │
│ AMD    │ Advanced Micro Devices    │  [●]    │ $220B      │
│ INTC   │ Intel Corporation         │  [ ]    │ $180B      │
│ QCOM   │ Qualcomm                  │  [ ]    │ $195B      │
│ MU     │ Micron Technology         │  [ ]    │ $120B      │
│ AVGO   │ Broadcom                  │  [ ]    │ $850B      │
└────────────────────────────────────────────────────────────┘

[SPACE] Toggle │ [S]ave Changes │ [N]ext Industry │ [B]ack
```

### Industry Selection Menu
```
┌─ Select Industry ──────────────────────────────────────────┐
│ 124 industries in database                                │
│                                                            │
│ [A]ir Freight & Logistics (12 companies, 3 leaders)       │
│ [B]anks - Regional (45 companies, 5 leaders)              │
│ [C]onsumer Electronics (18 companies, 4 leaders)          │
│ [S]emiconductors (25 companies, 2 leaders)                │
│ ...                                                        │
│                                                            │
│ Type letter or use arrows │ [ESC] Back                    │
└────────────────────────────────────────────────────────────┘
```

### Implementation Details

**Load Industry Data**:
```python
def get_industry_companies(industry: str) -> list:
    """Get all companies in industry with leader status"""
    query = """
    SELECT ipm.symbol, sm.company_name, sm.market_cap,
           ipm.is_industry_leader
    FROM industry_peer_mappings ipm
    JOIN symbol_metadata sm ON ipm.symbol = sm.symbol
    WHERE ipm.industry = ?
    ORDER BY sm.market_cap DESC
    """
    return query_db(query, (industry,))
```

**Save Leader Changes**:
```python
def update_industry_leaders(industry: str, leaders: list):
    """Update is_industry_leader flags"""
    # Begin transaction
    # Set all symbols in industry to is_industry_leader = 0
    # Set specified leaders to is_industry_leader = 1
    # Commit transaction
    # Trigger sympathy recalculation (optional: run pipeline)
```

**Validation Rules**:
- At least 1 leader per industry (prevent empty leaders)
- Max 5 leaders per industry (prevent over-representation)
- Leaders must be from same industry (consistency check)

---

## Feature 4: Database Sync (1-2 hours)

**Goal**: Manual sync from production to query database

### Sync Interface
```
┌─ Database Sync: Production → Query ───────────────────────┐
│                                                            │
│ Source:      E:\options_scanner\data\datalake.db          │
│ Destination: E:\options_scanner\data\datalake_query.db    │
│                                                            │
│ Last Sync:   2025-10-11 07:23 AM (3 hours ago)            │
│ Next Auto:   2025-10-11 05:45 PM (5 hours)                │
│                                                            │
│ Production DB Status:                                      │
│ - Size: 2.4 GB                                             │
│ - Last Modified: 2 minutes ago                             │
│ - Active Connections: 1 (OID pipeline)                    │
│                                                            │
│ ⚠️  WARNING: OID pipeline is running                       │
│    Sync may cause brief lock. Continue?                   │
│                                                            │
│ [S]ync Now │ [V]iew Sync Log │ [C]onfigure Schedule       │
│ [B]ack                                                     │
└────────────────────────────────────────────────────────────┘
```

### Sync Progress
```
┌─ Syncing Database... ─────────────────────────────────────┐
│                                                            │
│ [████████████████████████░░░░░░] 75% Complete             │
│                                                            │
│ Copying: earnings_sector_effects                          │
│ Progress: 18,245 / 24,327 rows                            │
│                                                            │
│ Elapsed: 12s │ Estimated: 4s remaining                    │
│                                                            │
│ [ESC] Cancel (safe - will rollback)                       │
└────────────────────────────────────────────────────────────┘
```

### Implementation Details

**Sync Method**:
```python
def sync_to_query_db():
    """Execute database sync via existing backup script"""
    # Use existing: python data/health/db_backup.py --sync --auto
    # Run as subprocess with progress monitoring
    # Parse output for progress updates
    # Handle errors (locked database, disk space, etc.)
```

**Safety Checks**:
```python
def can_sync_safely() -> tuple[bool, str]:
    """Check if sync is safe to perform"""
    checks = {
        'source_exists': os.path.exists('data/datalake.db'),
        'disk_space': get_free_space() > 5_000_000_000,  # 5GB
        'no_active_writes': not is_pipeline_running(),
        'backup_exists': get_last_backup_age() < 86400  # <24h
    }

    if all(checks.values()):
        return True, "Safe to sync"
    else:
        failed = [k for k, v in checks.items() if not v]
        return False, f"Failed checks: {', '.join(failed)}"
```

**Configuration**:
```
┌─ Sync Schedule Configuration ─────────────────────────────┐
│                                                            │
│ Auto-Sync Times (3x daily):                               │
│ ☑ 07:20 AM  (after morning OID)                           │
│ ☑ 05:45 PM  (after daily pipeline)                        │
│ ☑ 07:00 PM  (evening backup)                              │
│                                                            │
│ Sync Options:                                              │
│ ☑ Create timestamped backup before sync                   │
│ ☑ Validate integrity after sync                           │
│ ☐ Send notification on completion                         │
│                                                            │
│ [S]ave │ [R]eset to Defaults │ [C]ancel                   │
└────────────────────────────────────────────────────────────┘
```

---

## Feature 5: Backfill Operations (2-3 hours)

**Goal**: Fill historical data gaps

### Backfill Menu
```
┌─ Backfill Operations ─────────────────────────────────────┐
│ Fill gaps in historical data                              │
│                                                            │
│ 1. Backfill Earnings Events (API fetch)                   │
│    Fill missing earnings dates/estimates                  │
│    Estimated: 45 symbols missing Q3 2024 data             │
│                                                            │
│ 2. Backfill Earnings Moves (price calculation)            │
│    Calculate historical price moves for old events        │
│    Estimated: 120 events missing move_5day_pct            │
│                                                            │
│ 3. Backfill IV Snapshots (historical IV)                  │
│    Fetch historical IV around earnings dates              │
│    ⚠️ Expensive: Premium data source required              │
│                                                            │
│ 4. Recalculate Sector Sympathy (full rebuild)            │
│    Rebuild all peer correlations from scratch             │
│    Runtime: 15-20 minutes                                 │
│                                                            │
│ ESC. Back                                                  │
└────────────────────────────────────────────────────────────┘
```

### Backfill Configuration
```
┌─ Backfill Earnings Events ────────────────────────────────┐
│                                                            │
│ Date Range:                                                │
│ From: [2024-01-01] To: [2024-12-31]                       │
│                                                            │
│ Symbols: (leave blank for all KLMN 800)                   │
│ [NVDA, AMD, TSLA                                       ]   │
│                                                            │
│ Data Sources:                                              │
│ ☑ Financial Modeling Prep API                             │
│ ☑ yfinance (fallback)                                     │
│ ☐ Manual CSV import                                       │
│                                                            │
│ Options:                                                   │
│ ☑ Skip symbols with complete data                         │
│ ☑ Validate fetched data before saving                     │
│ ☐ Dry run (preview without saving)                        │
│                                                            │
│ [R]un Backfill │ [C]ancel                                 │
└────────────────────────────────────────────────────────────┘
```

### Implementation Details

**Gap Detection**:
```python
def detect_earnings_gaps() -> dict:
    """Find symbols with missing earnings data"""
    query = """
    SELECT sm.symbol,
           COUNT(ee.event_id) as event_count,
           MAX(ee.earnings_date) as last_earnings
    FROM symbol_metadata sm
    LEFT JOIN earnings_events ee ON sm.symbol = ee.symbol
    WHERE sm.symbol IN (SELECT symbol FROM klmn_universe)
    GROUP BY sm.symbol
    HAVING event_count < 8 OR last_earnings < date('now', '-90 days')
    """
    # Return list of symbols needing backfill
```

**Backfill Execution**:
```python
def backfill_earnings_events(symbols: list, date_range: tuple):
    """Fetch and insert missing earnings events"""
    # For each symbol:
    #   1. Query API for earnings in date range
    #   2. Filter out existing events (by symbol + date)
    #   3. Insert new events with decimal formatting
    #   4. Update progress bar
    #   5. Log results
```

---

## Feature 6: Data Quality & Validation (2-3 hours)

**Goal**: Identify and fix data integrity issues

### Quality Dashboard
```
┌─ Data Quality Dashboard ──────────────────────────────────┐
│                                                            │
│ ✓ Earnings Events: 26,635 records, 0 errors               │
│ ⚠ Earnings Moves: 9,250 records, 15 missing IV data       │
│ ✓ Sector Effects: 742 mappings, 0 orphaned records        │
│ ✗ Snapshots: 3,450 records, 120 outside T-7 to T+3        │
│                                                            │
│ Recent Issues (Last 7 Days):                               │
│ - 10/08: 5 earnings moves missing direction (fixed)       │
│ - 10/05: TSLA snapshot outside valid window (ignored)     │
│                                                            │
│ [ENTER] View Issue Details │ [R]un Validation │ [F]ix All │
│ [B]ack                                                     │
└────────────────────────────────────────────────────────────┘
```

### Validation Rules
```
┌─ Data Validation Rules ───────────────────────────────────┐
│                                                            │
│ Earnings Events:                                           │
│ ☑ earnings_date is valid ISO date                         │
│ ☑ symbol exists in symbol_metadata                        │
│ ☑ fiscal_quarter matches expected format (Q1/Q2/Q3/Q4)    │
│ ☐ earnings_surprise within reasonable range (-100% +100%) │
│                                                            │
│ Earnings Moves:                                            │
│ ☑ move_1day_pct < 50% (sanity check for splits)           │
│ ☑ move_direction matches sign of move_1day_pct            │
│ ☑ iv_crush_pct < 0 (IV always decreases post-earnings)    │
│                                                            │
│ Sector Effects:                                            │
│ ☑ peer_symbol != primary_symbol (no self-correlation)     │
│ ☑ correlation_strength between -1 and 1                   │
│ ☑ sample_size >= 3 (minimum for statistical relevance)    │
│                                                            │
│ [S]ave Rules │ [R]eset to Defaults │ [C]ancel              │
└────────────────────────────────────────────────────────────┘
```

### Auto-Fix Options
```
┌─ Auto-Fix Data Issues ────────────────────────────────────┐
│ Found 15 fixable issues:                                   │
│                                                            │
│ Issue Type: Missing move_direction                        │
│ Count: 8 records                                           │
│ Fix: Derive from sign of move_1day_pct                    │
│ ☑ Apply this fix                                          │
│                                                            │
│ Issue Type: Duplicate snapshots (same symbol/date/time)   │
│ Count: 3 records                                           │
│ Fix: Keep most recent, delete duplicates                  │
│ ☑ Apply this fix                                          │
│                                                            │
│ Issue Type: Orphaned sector effects (no primary event)    │
│ Count: 4 records                                           │
│ Fix: Delete orphaned records                              │
│ ☐ Apply this fix (destructive - review manually)          │
│                                                            │
│ [F]ix Selected │ [R]eview Each │ [C]ancel                 │
└────────────────────────────────────────────────────────────┘
```

### Implementation Details

**Validation Queries**:
```python
def validate_data_quality() -> list:
    """Run all validation rules and return issues"""
    issues = []

    # Check 1: Missing move_direction
    query = """
    SELECT event_id, symbol, earnings_date
    FROM earnings_moves
    WHERE move_1day_pct IS NOT NULL AND move_direction IS NULL
    """
    issues.extend(run_validation_query(query, 'missing_direction'))

    # Check 2: Invalid correlation strength
    query = """
    SELECT peer_id, primary_symbol, peer_symbol
    FROM earnings_sector_effects
    WHERE correlation_strength < -1 OR correlation_strength > 1
    """
    issues.extend(run_validation_query(query, 'invalid_correlation'))

    # ... more checks
    return issues
```

**Auto-Fix Logic**:
```python
def apply_auto_fix(issue_type: str, dry_run: bool = False):
    """Apply automatic fix for known issue type"""
    fixes = {
        'missing_direction': """
            UPDATE earnings_moves
            SET move_direction = CASE
                WHEN move_1day_pct > 0 THEN 'Up'
                WHEN move_1day_pct < 0 THEN 'Down'
                ELSE 'Flat'
            END
            WHERE move_direction IS NULL
        """,
        'duplicate_snapshots': """
            DELETE FROM earnings_snapshots
            WHERE snapshot_id NOT IN (
                SELECT MAX(snapshot_id)
                FROM earnings_snapshots
                GROUP BY symbol, snapshot_date, snapshot_time
            )
        """
    }

    if dry_run:
        # Return count of affected rows without executing
        return count_affected_rows(fixes[issue_type])
    else:
        # Execute fix
        execute_with_transaction(fixes[issue_type])
```

---

## Implementation Timeline

**Total Estimated Time**: 14-20 hours

| Feature | Hours | Priority |
|---------|-------|----------|
| 1. Pipeline Status & Controls | 3-4 | HIGH |
| 2. Trading Journal Management | 3-4 | HIGH |
| 3. Industry Leader Assignment | 2-3 | MEDIUM |
| 4. Database Sync | 1-2 | HIGH |
| 5. Backfill Operations | 2-3 | LOW |
| 6. Data Quality & Validation | 2-3 | MEDIUM |

**Suggested Approach**:
1. Start with Features 1, 2, 4 (core admin functions) - ~8 hours
2. Add Feature 3 if peer mapping needs tuning
3. Features 5-6 are nice-to-have for long-term maintenance

---

## Safety Mechanisms

### Pre-Launch Checks
```python
def verify_admin_launch_safety():
    """Safety checks before allowing admin operations"""
    checks = {
        'production_db_exists': os.path.exists('data/datalake.db'),
        'no_collection_running': not is_oid_or_flow_active(),
        'recent_backup_exists': get_last_backup_age() < 86400,
        'disk_space_sufficient': get_free_space() > 5_000_000_000
    }

    warnings = []
    if checks['no_collection_running'] == False:
        warnings.append("⚠️ Data collection pipeline is active")

    return checks, warnings
```

### Transaction Wrappers
```python
def safe_write_operation(query: str, params: tuple, confirm: bool = True):
    """Execute write with rollback on error"""
    if confirm:
        # Show confirmation dialog with affected rows count
        response = confirm_dialog(f"Execute: {query[:50]}...?")
        if not response:
            return False

    try:
        conn = sqlite3.connect('data/datalake.db')
        conn.execute('BEGIN IMMEDIATE')
        cursor = conn.execute(query, params)
        row_count = cursor.rowcount
        conn.commit()
        return True, row_count
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
```

### Audit Logging
```python
def log_admin_action(action: str, details: dict):
    """Log all write operations for audit trail"""
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'user': os.getenv('USERNAME', 'unknown'),
        'details': details
    }
    # Write to logs/ei_admin_audit.log
```

---

## Testing Plan

### Feature 1 Tests (Pipeline Controls)
- ✓ Pipeline status reads correctly from logs/DB
- ✓ Manual run buttons execute scripts successfully
- ✓ Progress monitoring displays live output
- ✓ Error handling for failed pipelines

### Feature 2 Tests (Trading Journal)
- ✓ Add note form validates inputs
- ✓ Edit existing note preserves data
- ✓ Delete note requires confirmation
- ✓ Tags are comma-separated and stored correctly

### Feature 3 Tests (Industry Leaders)
- ✓ Industry browse lists all 124 industries
- ✓ Leader toggles work correctly
- ✓ Save persists changes to database
- ✓ Validation prevents 0 leaders or >5 leaders

### Feature 4 Tests (Database Sync)
- ✓ Sync completes successfully
- ✓ Progress bar updates accurately
- ✓ Safety checks prevent sync during collection
- ✓ Error handling for locked database

### Feature 5 Tests (Backfill)
- ✓ Gap detection identifies missing data
- ✓ Backfill fetches and inserts correctly
- ✓ Dry run mode works without writing
- ✓ Duplicate detection prevents re-insertion

### Feature 6 Tests (Data Quality)
- ✓ Validation rules detect known issues
- ✓ Auto-fix applies corrections correctly
- ✓ Destructive fixes require confirmation
- ✓ Validation log captures results

---

## Future Enhancements

### User Permissions
- Admin role: full access
- Analyst role: read-only + journal writes
- Viewer role: read-only (use main TUI)

### Scheduled Tasks
- Configure pipeline schedules from TUI
- One-time future tasks (e.g., "run backfill tomorrow at 8 AM")

### Bulk Operations
- Bulk tag existing journal entries
- Bulk delete old snapshots (data retention policy)

### Data Export
- Export journal to CSV/JSON
- Export validation results to report

---

## Code Structure

### New Files
- `morning_view/ei_admin.py` - Entry point
- `morning_view/admin/admin_app.py` - Main TUI app class
- `morning_view/admin/screens/pipeline_control.py`
- `morning_view/admin/screens/journal_management.py`
- `morning_view/admin/screens/industry_leaders.py`
- `morning_view/admin/screens/database_sync.py`
- `morning_view/admin/screens/backfill_ops.py`
- `morning_view/admin/screens/data_quality.py`
- `morning_view/admin/admin_data.py` - Data layer (write operations)

### Modified Files
- None (admin TUI is fully isolated)

---

**Last Updated**: 2025-10-11
**Status**: Planning phase
**Database**: Write access to `datalake.db`
**Estimated Total Time**: 14-20 hours
**Priority Features**: Pipeline Control, Trading Journal, Database Sync
