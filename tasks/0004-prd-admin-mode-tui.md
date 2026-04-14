# PRD: Admin Mode for Morning Views TUI

**Status**: Planning Phase
**Created**: 2025-10-13
**Estimated Effort**: 5-7 hours
**Priority**: HIGH

---

## Problem Statement

The Morning Views TUI is currently read-only, using `datalake_query.db`. Several workflows require write access to the production database (`datalake.db`):

1. **Pipeline manual triggers** - main.py breaks frequently, need ability to run individual pipelines or resume from specific stages
2. **Trading journal** - Log notes/tags/sentiment for earnings trades
3. **Portfolio tracking** (future) - Log position entries/exits
4. **File operations** (future) - Edit MD/TXT files, view logs, export JSON

Currently, these operations require direct database manipulation or running scripts manually via command line, which is cumbersome and error-prone.

---

## Goals

### Primary Goals
1. **Admin Mode toggle** - Press `X` to enter admin mode with write access to production database
2. **Pipeline Control Panel** - Manually trigger any pipeline script with live output monitoring
3. **Trading Journal** - Add/append notes to earnings events with symbol/date lookup
4. **Infrastructure** - Framework to easily add more admin features (file browser, backfill ops, etc.)

### Non-Goals
- Separate admin TUI application (keep everything in one interface)
- Complex authentication/permissions (single user system)
- Automated pipeline scheduling (that's handled by main.py/scheduler)

---

## User Personas

**Primary User: Ben (Trader/Developer)**
- Uses TUI daily for analysis
- Frequently modifies code, causing main.py to break
- Needs quick access to re-run specific pipelines
- Occasionally logs trading notes after taking positions
- Prefers keyboard-driven workflows
- Values speed over safety warnings (but wants data integrity)

---

## User Stories

### Pipeline Control
1. As a trader, I want to **manually trigger the morning scan pipeline** when main.py breaks, so I can get fresh data without restarting the entire orchestrator
2. As a developer, I want to **see live output** from running pipelines, so I can debug issues in real-time
3. As a trader, I want to **detach from a running pipeline** and come back later to check status, so I can continue analyzing while pipelines run

### Trading Journal
4. As a trader, I want to **quickly log notes** about an earnings trade I just took, so I can capture my reasoning while it's fresh
5. As a trader, I want to **append to existing notes** rather than overwrite, so I can track my thought process over time
6. As a trader, I want the system to **find the earnings event** for me based on symbol/date, so I don't have to manually create database records

### Admin Infrastructure
7. As a user, I want **clear visual indicators** when in admin mode, so I don't accidentally write to production when analyzing
8. As a user, I want **resilient error handling**, so my work isn't lost if the database is temporarily locked

---

## Solution Design

### Architecture Overview

**Single TUI with Two Modes:**
- **Normal Mode** (default): Read-only, `datalake_query.db`, cyan/blue theme
- **Admin Mode** (toggle): Write-enabled, `datalake.db`, red/maroon theme

**Mode Toggle:**
- Press `X` from main menu to enter Admin Mode
- Admin Mode shows new "Admin Main Menu" screen with write features
- Press `ESC` to exit admin mode back to main menu
- Visual: Red borders, "⚠️ ADMIN MODE - PRODUCTION DATABASE" header

**Database Strategy:**
- WAL mode already enabled on `datalake.db` (verified)
- Read/write operations can happen concurrently
- Fallback: If write fails due to lock, show error and keep form data in memory for retry

### Feature 1: Admin Mode Framework (1.5 hours)

**Files Modified:**
- `morning_view/mv_main.py` - Add admin theme CSS
- `morning_view/tui_data.py` - Add `admin_mode` parameter to switch database

**Files Created:**
- `morning_view/admin_screens/admin_menu.py` - Admin main menu screen
- `morning_view/admin_data.py` - Write operations data layer

**Admin Main Menu:**
```
┌─ ADMIN MODE - PRODUCTION DATABASE ────────────────────────┐
│ ⚠️  Write access enabled - datalake.db                     │
│                                                            │
│ 1. Pipeline Controls                                      │
│    Manually trigger data collection pipelines             │
│                                                            │
│ 2. Trading Journal                                        │
│    Add/edit notes for earnings trades                     │
│                                                            │
│ 3. File Browser                                           │
│    View/edit config files, logs, exports                  │
│                                                            │
│ 4. Database Sync                                          │
│    Sync production → query database                       │
│                                                            │
│ ESC. Exit Admin Mode                                      │
└────────────────────────────────────────────────────────────┘
```

**Color Theme (Admin Mode):**
- Primary borders: `bright_red`
- Headers: `yellow` (warning color)
- Background: `$surface` (same as normal)
- Text: `$text` (same as normal)

**Implementation:**
```python
# mv_main.py - Add to CSS
"""
/* Admin Mode Theme */
.admin-mode {
    border: solid $error;  /* Red borders */
}

.admin-header {
    background: $error;
    color: $text;
    text-style: bold;
}

.admin-warning {
    background: $warning-darken-2;
    color: $text;
    text-style: bold;
}
"""
```

### Feature 2: Pipeline Control Panel (1.5 hours)

**File:** `morning_view/admin_screens/pipeline_control.py`

**Design Decision: Spawn New Terminal Window**
- Avoids threading/buffering complexity (learned from web dashboard pain)
- Pipeline runs independently with full interactivity (NOT --no-interact mode)
- User sees native output with colors, progress bars, prompts
- TUI and pipeline run concurrently, user switches between windows
- Safer: TUI crash doesn't kill pipeline, interrupted writes are isolated

**Pipeline Selection Menu:**
```
┌─ ADMIN MODE - Pipeline Controls ──────────────────────────┐
│ Select pipeline to run in new terminal window:            │
│                                                            │
│ Earnings Intelligence:                                     │
│   1. Weekly Refresh (60-90 min)                           │
│      Fetch upcoming earnings, archive old events          │
│                                                            │
│   2. Daily Pipeline (15-20 min)                           │
│      Collect snapshots, calculate moves                   │
│                                                            │
│   3. Morning Arbitrage Scan (1-2 min)                     │
│      Scan for IV discount opportunities                   │
│                                                            │
│ OID Strategy:                                              │
│   4. Morning Analysis (5-10 min)                          │
│      Analyze morning open interest changes                │
│                                                            │
│   5. Evening Operations (10-15 min)                       │
│      Process end-of-day OI data                           │
│                                                            │
│ Flow Monitor:                                              │
│   6. Run Flow Monitor (30-60 sec)                         │
│      Options flow analysis workflow                       │
│                                                            │
│ System:                                                    │
│   7. Database Sync (2-5 min)                              │
│      Sync production → query database                     │
│                                                            │
│ ESC. Back                                                  │
└────────────────────────────────────────────────────────────┘
```

**After Triggering Pipeline:**
```
┌─ ADMIN MODE - Pipeline Launched ──────────────────────────┐
│                                                            │
│ ✓ Pipeline started in new terminal window:                │
│                                                            │
│   Earnings Intel - Morning Arbitrage Scan                 │
│                                                            │
│ The pipeline is running in a separate window.             │
│ Switch to that window to monitor progress.                │
│                                                            │
│ You can close this TUI - the pipeline will continue.      │
│                                                            │
│ [ENTER] Continue                                           │
└────────────────────────────────────────────────────────────┘
```

**Implementation:**
```python
import subprocess
import sys
from pathlib import Path

PIPELINES = [
    {
        "id": "ei_weekly",
        "name": "Weekly Refresh",
        "category": "Earnings Intelligence",
        "script": "strategies/earnings_intel/ei_main.py",
        "args": ["--weekly-refresh"],  # NO --no-interact
        "description": "Fetch upcoming earnings, archive old events, cleanup",
        "runtime": "60-90 min"
    },
    {
        "id": "ei_daily",
        "name": "Daily Pipeline",
        "category": "Earnings Intelligence",
        "script": "strategies/earnings_intel/ei_main.py",
        "args": ["--daily-pipeline"],
        "description": "Collect snapshots, calculate moves, update summaries",
        "runtime": "15-20 min"
    },
    {
        "id": "ei_morning",
        "name": "Morning Arbitrage Scan",
        "category": "Earnings Intelligence",
        "script": "strategies/earnings_intel/ei_main.py",
        "args": ["--morning-scan"],
        "description": "Scan for IV discount opportunities",
        "runtime": "1-2 min"
    },
    {
        "id": "oid_morning",
        "name": "Morning Analysis",
        "category": "OID Strategy",
        "script": "strategies/oi_delta/oid_main.py",
        "args": ["--oid-morning"],
        "description": "Analyze morning open interest changes",
        "runtime": "5-10 min"
    },
    {
        "id": "oid_evening",
        "name": "Evening Operations",
        "category": "OID Strategy",
        "script": "strategies/oi_delta/oid_main.py",
        "args": ["--oid-evening"],
        "description": "Process end-of-day OI data",
        "runtime": "10-15 min"
    },
    {
        "id": "fm_run",
        "name": "Run Flow Monitor",
        "category": "Flow Monitor",
        "script": "strategies/flow_monitor/fm_main.py",
        "args": [],
        "description": "Options flow analysis workflow",
        "runtime": "30-60 sec"
    },
    {
        "id": "db_sync",
        "name": "Database Sync",
        "category": "System",
        "script": "data/health/db_backup.py",
        "args": ["--sync", "--auto"],
        "description": "Sync production → query database",
        "runtime": "2-5 min"
    }
]


def launch_pipeline_in_new_window(pipeline: dict) -> bool:
    """
    Launch pipeline in new terminal window.

    Args:
        pipeline: Pipeline dict with 'script' and 'args'

    Returns:
        True if launched successfully, False otherwise
    """
    project_root = Path(__file__).parent.parent.parent
    script_path = project_root / pipeline['script']

    # Build command for new terminal
    # Windows: Use 'start cmd /k' to keep window open after completion
    command = [
        'cmd', '/c', 'start',
        'cmd', '/k',
        sys.executable,
        str(script_path)
    ] + pipeline['args']

    try:
        # Launch detached process
        subprocess.Popen(
            command,
            cwd=str(project_root),
            shell=True  # Required for 'start' command on Windows
        )
        return True
    except Exception as e:
        # Log error, return False
        return False
```

**Key Advantages:**
- **Simple**: ~50 lines of code vs 200+ for threading/buffering
- **Reliable**: No race conditions, buffer overflow, or zombie processes
- **Better UX**: Native terminal with full ANSI colors, progress bars, user input
- **Safer**: Pipeline and TUI are isolated processes
- **Windows-native**: Uses standard `cmd` or Windows Terminal

### Feature 3: Trading Journal (2.5 hours)

**Status:** ⚠️ **PROOF OF CONCEPT ONLY** - Limited usefulness discovered during implementation. The `earnings_events` table only contains historical data through 2025-09-25. Post-trade journaling on past earnings may not align with actual trading workflow needs. Consider redesigning for future use cases or integrating with live position tracking.

**File:** `morning_view/admin_screens/trading_journal.py`

**Workflow:**

**Step 1: Symbol/Date Lookup**
```
┌─ ADMIN MODE - Trading Journal ────────────────────────────┐
│ Find or create earnings event:                            │
│                                                            │
│ Symbol: [NVDA____]  Date: [2025-02-26]  [L]ookup          │
│                                                            │
│ Status: Searching...                                       │
└────────────────────────────────────────────────────────────┘
```

**Step 2a: Event Found**
```
┌─ ADMIN MODE - Trading Journal ────────────────────────────┐
│ Event Found: NVDA - 2025-02-26                            │
│ Earnings Date: 2025-02-26 | Actual EPS: $1.23            │
│                                                            │
│ Existing Notes (243 chars):                               │
│ ┌──────────────────────────────────────────────────────┐  │
│ │Previous trade: Sold straddle, IV crushed -34%.      │  │
│ │Winner but AMD sympathy unexpected.                   │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                            │
│ [A]ppend Note │ [O]verwrite │ [C]ancel                    │
└────────────────────────────────────────────────────────────┘
```

**Step 2b: Event Not Found**
```
┌─ ADMIN MODE - Trading Journal ────────────────────────────┐
│ No event found for NVDA on 2025-02-26                    │
│                                                            │
│ ⚠️  This will create a new earnings event stub             │
│                                                            │
│ [C]reate & Continue │ [B]ack                              │
└────────────────────────────────────────────────────────────┘
```

**Step 3: Add Note**
```
┌─ ADMIN MODE - Add Note to NVDA 2025-02-26 ────────────────┐
│ Type:      [x] Trade  [ ] Observation  [ ] Pattern        │
│ Sentiment: [ ] Bullish  [x] Bearish  [ ] Neutral          │
│                                                            │
│ Tags: [iv-crush, tech-sympathy                         ]   │
│                                                            │
│ New Note (will be appended with timestamp):               │
│ ┌──────────────────────────────────────────────────────┐  │
│ │Follow-up: Position closed early due to increased    │  │
│ │correlation risk. Need better sector hedging.        │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                            │
│ [S]ave (append) │ [C]ancel                                │
└────────────────────────────────────────────────────────────┘
```

**Database Operations:**
```python
# admin_data.py

def lookup_earnings_event(symbol: str, earnings_date: str) -> Optional[dict]:
    """
    Find earnings event by symbol and date.

    Returns:
        Dict with event_id, symbol, earnings_date, existing notes/tags
        None if not found
    """
    conn = sqlite3.connect('data/datalake.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT event_id, symbol, earnings_date, earnings_time,
               actual_eps, estimate_eps, notes, tags, note_type, sentiment
        FROM earnings_events
        WHERE symbol = ? AND earnings_date = ?
    """, (symbol, earnings_date))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'event_id': row[0],
            'symbol': row[1],
            'earnings_date': row[2],
            'earnings_time': row[3],
            'actual_eps': row[4],
            'estimate_eps': row[5],
            'notes': row[6],
            'tags': row[7],
            'note_type': row[8],
            'sentiment': row[9]
        }
    return None


def append_journal_note(symbol: str, earnings_date: str, note_data: dict) -> tuple[bool, str]:
    """
    Append note to existing earnings event or create new event.

    Args:
        symbol: Stock ticker
        earnings_date: ISO date (YYYY-MM-DD)
        note_data: Dict with 'notes', 'tags', 'note_type', 'sentiment'

    Returns:
        (success: bool, message: str)
    """
    from datetime import datetime

    try:
        conn = sqlite3.connect('data/datalake.db')
        cursor = conn.cursor()

        # Check if event exists
        existing = lookup_earnings_event(symbol, earnings_date)

        if existing:
            # Append to existing notes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            separator = f"\n\n--- {timestamp} ---\n"

            existing_notes = existing['notes'] or ""
            updated_notes = existing_notes + separator + note_data['notes']

            # Merge tags (comma-separated, no duplicates)
            existing_tags = set((existing['tags'] or "").split(","))
            new_tags = set(note_data['tags'].split(","))
            merged_tags = ",".join(sorted(existing_tags | new_tags))

            cursor.execute("""
                UPDATE earnings_events
                SET notes = ?, tags = ?, note_type = ?, sentiment = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
            """, (updated_notes, merged_tags, note_data['note_type'],
                  note_data['sentiment'], existing['event_id']))

            message = f"Note appended to {symbol} {earnings_date}"

        else:
            # Create new event stub
            cursor.execute("""
                INSERT INTO earnings_events
                (symbol, earnings_date, notes, tags, note_type, sentiment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (symbol, earnings_date, note_data['notes'], note_data['tags'],
                  note_data['note_type'], note_data['sentiment']))

            message = f"New event created for {symbol} {earnings_date}"

        conn.commit()
        conn.close()
        return True, message

    except sqlite3.Error as e:
        return False, f"Database error: {str(e)}"
```

### Feature 4: File Browser (Future - Not in MVP) (1.5 hours)

**File:** `morning_view/admin_screens/file_browser.py`

**Features:**
- Navigate directory tree
- View text files (MD, TXT, log files)
- Edit config files (JSON with syntax highlighting)
- Export data to JSON
- Simple text editor with save

**Not implementing in MVP** - Add later when needed.

---

## Technical Specifications

### File Structure
```
morning_view/
├── mv_main.py                      # Add admin CSS theme
├── tui_data.py                     # No changes (already supports write_db)
├── screens/
│   ├── main_menu.py               # Add 'X' binding for admin mode
│   └── ...                        # Existing screens
├── admin_screens/                 # NEW
│   ├── __init__.py
│   ├── admin_menu.py              # Admin main menu
│   ├── pipeline_control.py        # Pipeline triggers + monitoring
│   └── trading_journal.py         # Journal entry form
└── admin_data.py                  # NEW - Write operations data layer
```

### Database Schema

**No schema changes required.** All operations use existing tables:
- `earnings_events` - Store journal notes in `notes`, `tags`, `note_type`, `sentiment` fields
- All other tables - Read operations only

### Error Handling

**Database Lock (Rare with WAL):**
```python
try:
    conn.execute(query, params)
    conn.commit()
except sqlite3.OperationalError as e:
    if "database is locked" in str(e):
        return False, "Database busy. Pipeline may be running. Try again."
    else:
        return False, f"Database error: {str(e)}"
```

**Pipeline Execution Failure:**
```python
def run_pipeline(command: list) -> tuple[bool, str]:
    """Run pipeline and return success status"""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=3600  # 1 hour max
        )

        if result.returncode == 0:
            return True, "Pipeline completed successfully"
        else:
            return False, f"Pipeline failed with code {result.returncode}"

    except subprocess.TimeoutExpired:
        return False, "Pipeline timed out (>1 hour)"
    except Exception as e:
        return False, f"Failed to run pipeline: {str(e)}"
```

### Testing Plan

**Manual Testing Checklist:**

1. **Admin Mode Toggle**
   - [ ] Press X from main menu → enters admin mode
   - [ ] Admin menu displays with red theme
   - [ ] ESC exits back to main menu
   - [ ] Database connection switches to datalake.db

2. **Pipeline Control**
   - [ ] All 7 pipelines listed
   - [ ] Select pipeline → spawns new terminal window
   - [ ] Pipeline runs with full interactivity (colors, progress bars)
   - [ ] TUI continues to be usable
   - [ ] Pipeline runs independently (closing TUI doesn't kill it)
   - [ ] User can switch between TUI and pipeline windows

3. **Trading Journal**
   - [ ] Symbol/date lookup finds existing event
   - [ ] Shows existing notes if found
   - [ ] Append mode adds timestamp separator
   - [ ] Tags merge without duplicates
   - [ ] Create new event if not found
   - [ ] Validation: symbol, date format, required fields
   - [ ] Error message if database locked
   - [ ] Form data preserved on error

---

## Success Metrics

**Qualitative:**
- Ben uses admin mode regularly for pipeline triggers
- Trading journal workflow feels natural and quick
- Admin mode clearly distinguishable from normal mode

**Quantitative:**
- Pipeline manual trigger used 5+ times per week
- Trading journal entries added 2-3 times per week
- Zero data corruption incidents from admin mode usage

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Database corruption from concurrent writes | HIGH | LOW | WAL mode handles concurrency; test extensively |
| User forgets they're in admin mode | MEDIUM | LOW | Persistent red theme; warning banner on every screen |
| Journal notes lost on DB lock error | MEDIUM | LOW | Keep form data in memory; offer retry button |
| Pipeline fails silently in background window | MEDIUM | LOW | User responsible for checking pipeline terminal; failure returns non-zero exit code |

---

## Future Enhancements (Post-MVP)

### Phase 2
1. **File Browser** - View/edit MD, TXT, JSON files
2. **Portfolio Tracker** - Log position entries/exits
3. **Granular Pipeline Control** - Run individual functions within pipelines
4. **Database Sync Manual Trigger** - Force sync to query DB

### Phase 3
1. **Backfill Operations** - Fill historical data gaps
2. **Data Quality Dashboard** - Validation checks and auto-fix
3. **Industry Leader Assignment** - Manage peer mappings
4. **Export Tools** - Export journal/portfolio to CSV/JSON

---

## Implementation Timeline

**Total Estimated: 5-7 hours**

| Task | Hours | Dependencies |
|------|-------|--------------|
| 1. Admin mode framework + theme | 1.5 | None |
| 2. Pipeline control panel | 1.5 | Task 1 |
| 3. Trading journal | 2.5 | Task 1 |
| 4. Testing + polish | 1-2 | Tasks 1-3 |

**Approach:**
1. Build Task 1 first → verify admin mode toggle works
2. Build Task 2 → test with one pipeline (morning scan)
3. Build Task 3 → test with real earnings event
4. Integration testing with both features

---

## Open Questions

1. ~~**Pipeline stdout buffering**~~ - RESOLVED: Pipelines run in native terminal, no buffering issues
2. **Journal browse view** - TODO: Should there be a separate screen to browse past journal entries? (Currently just add/append) - Defer to Phase 2 discussion
3. **Database sync** - RESOLVED: Manual trigger in admin mode, automated sync already handled by main.py
4. ~~**Background pipeline persistence**~~ - RESOLVED: Pipelines run independently, survive TUI restart naturally

---

## Appendix: Key Design Decisions

### Why Admin Mode Toggle Instead of Separate TUI?
- User already comfortable with main TUI interface
- Easier to copy design patterns from existing screens
- Reduces context switching between applications
- Admin operations are infrequent, don't need dedicated app

### Why Spawn New Terminal Window for Pipelines?
- **Simplicity**: 50 lines vs 200+ for threading/buffering (avoiding web dashboard pain)
- **Better UX**: Native terminal with full ANSI colors, progress bars, user input
- **Reliability**: No race conditions, buffer overflow, or state management complexity
- **Safety**: Pipeline and TUI are isolated processes, DB write interrupts can't corrupt TUI state
- **Familiar**: User already comfortable with multiple terminal windows

### Why Append-Only for Journal Notes?
- Preserves historical context and thought evolution
- Timestamp separators show when notes were added
- Can always manually edit database if overwrite needed
- Append is safer than overwrite (no accidental data loss)

### Why Not Separate Admin Database?
- Production database already supports concurrent access (WAL mode)
- Admin operations are infrequent and low-risk
- Simplifies architecture (one source of truth)
- Sync mechanism already handles query database updates

---

**Last Updated**: 2025-10-13
**Status**: Ready for implementation
**Total Estimated Time**: 5-7 hours
**Next Step**: Generate task list with `@ai-dev-tasks/generate-tasks.md`
