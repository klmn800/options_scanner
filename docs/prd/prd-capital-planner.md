# PRD: Capital Planner for Morning View TUI

**Document Version:** 1.0
**Created:** 2025-10-12
**Status:** Draft → Approved
**Target Release:** End of Day 2025-10-12

---

## Problem Statement

User needs to strategically plan earnings option plays over 90-day windows to manage capital deployment and achieve $500/week profit target. Current system excels at tactical signal generation ("what to watch today") but lacks forward-looking capital planning ("when is my capital locked up?").

**Current Pain Points:**
- No visibility into future capital commitments
- No conflict detection (overlapping positions)
- No systematic entry/exit timing discipline
- Trades executed reactively ("whenever it feels okay") vs strategically

**Goal:** Build prescriptive planning system that forces systematic execution and capital discipline.

---

## User Workflow

1. User opens morning_view TUI
2. Browses upcoming earnings (Earnings Browser or existing calendar)
3. Identifies interesting symbols based on signals/analysis
4. Adds symbols to Capital Planner with:
   - Manual entry/exit dates (with T-minus hints)
   - Manual position size calculation
   - Optional notes (thesis, key levels, etc.)
5. Reviews capital timeline to check:
   - Peak deployment periods
   - Overlapping positions
   - Total capital utilization vs $3000 budget
6. Uses this plan throughout weeks to guide actual trade execution
7. Updates position status as trades progress (planned → watching → entered → closed)
8. Archived closed positions auto-cleanup (discussed timing TBD)

---

## In Scope (v1)

### Core Features
- ✅ Capital Planner main screen (hybrid summary + table view)
- ✅ Earnings Browser screen (filterable upcoming earnings)
- ✅ Settings screen (edit config.json + planner_config.json)
- ✅ Add position from Symbol Detail ('P' hotkey)
- ✅ Timeline Detail view (vertical Gantt chart)
- ✅ Position CRUD (create, edit, delete)
- ✅ Capital utilization visualization (weekly bars)
- ✅ Manual data entry (dates, prices, contracts)
- ✅ Freeform status changes (planned/watching/entered/closed)
- ✅ Notes field per position (500 char limit)

### Data Management
- ✅ JSON-based storage (no database writes)
- ✅ Read-only database queries for enrichment
- ✅ Position archival for closed trades

### UI/UX
- ✅ Vertical scroll-friendly design
- ✅ Keyboard navigation throughout
- ✅ Warning indicators (no blockers except nonsensical input)
- ✅ Truncated notes in table, full text in edit view

---

## Out of Scope (v1)

- ❌ Actual trade execution tracking (real cost basis, P&L)
- ❌ Live contract prices from database
- ❌ Automated entry/exit signals based on IV triggers
- ❌ Historical performance analysis
- ❌ AI recommendations ("You should trade this")
- ❌ Alerts/notifications when it's time to enter/exit
- ❌ Multi-user support
- ❌ Export to CSV/Excel
- ❌ Integration with broker APIs

---

## Data Models

### planner_config.json
```json
{
  "capital": {
    "total_capital": 3000,
    "target_position_size": 300,
    "warning_threshold_pct": 80
  },
  "defaults": {
    "default_entry_days_before": 14,
    "default_exit_days_before": 2
  },
  "archival": {
    "auto_archive_closed": false,
    "archive_after_days": 7
  }
}
```

### planner_data.json
```json
{
  "version": "1.0",
  "last_updated": "2025-10-12T14:30:00",
  "positions": [
    {
      "id": "nvda_20251023_001",
      "symbol": "NVDA",
      "earnings_date": "2025-10-23",
      "entry_date": "2025-10-09",
      "exit_date": "2025-10-21",
      "num_contracts": 2,
      "estimated_contract_price": 5.50,
      "estimated_total_cost": 1100,
      "status": "planned",
      "notes": "High IV buildup expected, following strong guidance",
      "created_at": "2025-10-12T08:30:00",
      "updated_at": "2025-10-12T08:30:00"
    }
  ],
  "archived_positions": []
}
```

**Field Specifications:**
- `id`: Unique identifier (format: `{symbol}_{earnings_date}_{sequence}`)
- `symbol`: Immutable after creation
- `earnings_date`: Immutable after creation (delete to change)
- `entry_date`, `exit_date`: User-editable dates
- `num_contracts`: Integer, user-editable
- `estimated_contract_price`: Float, manual entry (not live data)
- `estimated_total_cost`: Calculated (contracts × price)
- `status`: String enum (planned, watching, entered, closed) - freeform, user-controlled
- `notes`: String, max 500 chars, no line breaks
- Timestamps: ISO 8601 format

---

## UI Specifications

### Main Menu (Modified)
Add two new menu items:
- `[6] Capital Planner` - Navigate to planner
- `[7] Settings` - Navigate to settings

### Screen 1: Capital Planner (Main View)

**Layout:** Hybrid design - summary chart at top, positions table below

```
╔══════════════════════════════════════════════════════════════════╗
║ Capital Planner - 5 Positions Planned                            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║ Capital Summary (Next 4 Weeks)                                   ║
║                                                                   ║
║ Week Starting    Deployed                   Positions             ║
║ ───────────────────────────────────────────────────────────────  ║
║ Oct 07  ████████░░░░░░░░  $1,100 (37%)      NVDA                ║
║ Oct 14  █████████████████ $2,600 (87%) ⚠️   NVDA, AMD, LULU     ║
║ Oct 21  ██████░░░░░░░░░░  $900 (30%)        AMD, LULU           ║
║ Oct 28  ████░░░░░░░░░░░░  $600 (20%)        LULU                ║
║                                                                   ║
║ ───────────────────────────────────────────────────────────────  ║
║                                                                   ║
║ Planned Positions                            [Sort: Entry Date ▼]║
║                                                                   ║
║ Symbol  Entry     Exit      Days  Cost     Status    Notes       ║
║ ───────────────────────────────────────────────────────────────  ║
║ ▸ NVDA  10/09 Wed 10/21 Mon  12   $1,100   Planned   High IV... ║
║   AMD   10/10 Thu 10/22 Tue  12   $900     Planned   Following..║
║   LULU  10/14 Mon 10/26 Sat  12   $600     Watching  Retail se..║
║   TSLA  10/18 Fri 10/30 Wed  12   $1,200   Planned   Entry aft..║
║   APP   10/21 Mon 11/02 Sat  12   $800     Planned   Post-NVDA..║
║                                                                   ║
║ [A] Add  [E] Edit  [D] Delete  [V] Timeline  [F] Filter  [ESC]  ║
╚══════════════════════════════════════════════════════════════════╝
```

**Summary Chart:**
- Weekly bars showing capital deployment (next 4 weeks visible)
- Bar width = % of total capital
- Warning icon (⚠️) at 80%+ utilization
- Position symbols listed per week

**Positions Table:**
- Sortable by entry date (default), exit date, symbol, cost
- Filterable by status (show all / planned only / watching only / etc)
- Arrow key navigation
- Cursor highlight on selected row
- Notes truncated to ~50 chars with ellipsis

**Keybindings:**
- `A` - Add new position (opens add modal)
- `E` - Edit selected position
- `D` - Delete selected position (confirmation prompt)
- `V` - View timeline detail (Gantt chart)
- `F` - Filter by status (cycle through: all / planned / watching / entered)
- `↑↓` - Navigate table
- `ESC` - Back to main menu

---

### Screen 2: Add/Edit Position Modal

**Layout:** Centered modal overlay

```
╔══════════════════════════════════════════════════════════╗
║ Add Position to Planner                                  ║
╠══════════════════════════════════════════════════════════╣
║                                                           ║
║ Symbol:           [NVDA    ]                             ║
║ Earnings Date:    [2025-10-23] (from DB)                ║
║                                                           ║
║ Entry Date:       [2025-10-09] (hint: T-14 = Oct 9)     ║
║ Exit Date:        [2025-10-21] (hint: T-2 = Oct 21)     ║
║                                                           ║
║ ───────── Position Calculator ─────────                  ║
║                                                           ║
║ Contracts:        [2      ]                              ║
║ Price per:        [$5.50  ]                              ║
║ Total Cost:       $1,100 (target: $300) ⚠️               ║
║                                                           ║
║ Status:           [Planned ▼] (dropdown)                 ║
║                                                           ║
║ Notes (optional, 500 char max):                          ║
║ ┌──────────────────────────────────────────────────────┐ ║
║ │High IV buildup expected                              │ ║
║ │                                                      │ ║
║ └──────────────────────────────────────────────────────┘ ║
║                                                           ║
║ [TAB] Next Field  [S] Save  [ESC] Cancel                 ║
╚══════════════════════════════════════════════════════════╝
```

**Validation Rules:**
- Symbol: Required, alphanumeric only
- Earnings Date: Required, valid date format
- Entry/Exit Dates: Required, valid dates, exit > entry
- Contracts: Integer > 0
- Price: Float > 0
- Total Cost: Auto-calculated, warning if > 2× target (no block)
- Notes: Max 500 chars, single line (line breaks stripped)

**Pre-fill Behavior (when opened from Symbol Detail):**
- Symbol, earnings date auto-filled from database
- Entry date = earnings_date - default_entry_days_before
- Exit date = earnings_date - default_exit_days_before
- Other fields empty

**Edit Mode:**
- Same layout, pre-filled with existing position data
- Symbol and earnings_date fields disabled (immutable)
- Title changes to "Edit Position"

---

### Screen 3: Timeline Detail (Vertical Gantt)

**Layout:** Full-screen scrollable timeline

```
╔══════════════════════════════════════════════════════════════════╗
║ Position Timeline - Next 90 Days                   [D]aily [W]eekly ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║ Position        Oct 09      Oct 16      Oct 23      Oct 30       ║
║ ────────────────┼───────────┼───────────┼───────────┼────────    ║
║ NVDA            ████████████████████████▌                        ║
║ $1,100          Entry: Wed 10/09        Exit: Mon 10/21          ║
║                                                                   ║
║ AMD                     ████████████████████████▌                ║
║ $900                    Entry: Thu 10/10        Exit: Tue 10/22  ║
║                                                                   ║
║ LULU                            ████████████████████████▌        ║
║ $600                            Entry: Mon 10/14  Exit: Sat 10/26║
║                                                                   ║
║ TSLA                                    ████████████████████████▌║
║ $1,200                                  Entry: Fri 10/18  Exit...║
║                                                                   ║
║ APP                                             ████████████████ ║
║ $800                                            Entry: Mon 10/21..║
║ ────────────────┼───────────┼───────────┼───────────┼────────    ║
║                                                                   ║
║ Daily Capital (showing Oct 09 - Nov 02):                         ║
║                                                                   ║
║ Oct 09-13       $1,100  ████░░░░░░░░░░░░                         ║
║ Oct 14-20       $2,600  █████████████████ ⚠️                     ║
║ Oct 21-22       $1,500  ██████░░░░░░░░░░                         ║
║ Oct 23-26       $600    ████░░░░░░░░░░░░                         ║
║ Oct 27-29       $600    ████░░░░░░░░░░░░                         ║
║ Oct 30-Nov 02   $800    █████░░░░░░░░░░░                         ║
║                                                                   ║
║ [↑↓] Scroll  [D] Daily View  [W] Weekly View  [ESC] Back        ║
╚══════════════════════════════════════════════════════════════════╝
```

**Features:**
- Each position = one row in Gantt chart
- Bars span from entry to exit date
- Position cost shown on left
- Timeline scrolls vertically (arrow keys, mouse wheel)
- Toggle between daily and weekly granularity (D/W keys)
- Capital summary at bottom (date ranges + utilization bars)

---

### Screen 4: Earnings Browser

**Layout:** Full-screen table of upcoming tradeable earnings

```
╔══════════════════════════════════════════════════════════════════╗
║ Earnings Browser - Next 90 Days                 [Sort: Date ▼]   ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║ Filters: <$60 price, 500+ OI (from config.json)                  ║
║                                                                   ║
║ Symbol  Date      Price  Sector       OI      Signal    Action   ║
║ ───────────────────────────────────────────────────────────────  ║
║ ▸ NVDA  10/23 Wed $142   Technology   45K     STRONG    [+Plan]  ║
║   AMD   10/24 Thu $155   Technology   32K     BUY       [+Plan]  ║
║   TSLA  10/25 Fri $245   Automotive   28K     WATCH     [+Plan]  ║
║   LULU  10/28 Mon $58    Retail       15K     BUY       [+Plan]  ║
║   ...                                                             ║
║                                                                   ║
║ Showing 264 tradeable symbols                                    ║
║                                                                   ║
║ [ENTER] View Detail  [P] Add to Planner  [↑↓] Navigate  [ESC]   ║
╚══════════════════════════════════════════════════════════════════╝
```

**Data Source:**
- Query `earnings_upcoming` table
- Join with `oi_symbol_summary` for latest price, OI
- Join with `symbol_metadata` for sector
- Apply filters from config.json (max price, min OI)
- Optionally join with earnings signals if available

**Actions:**
- `ENTER` on row → Opens Symbol Detail screen (existing)
- `P` on row → Opens Add Position modal with symbol pre-filled
- `↑↓` → Navigate table
- Sortable by date, symbol, price, sector

---

### Screen 5: Settings

**Layout:** Form with input fields for all config values

```
╔══════════════════════════════════════════════════════════════════╗
║ Settings                                                          ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                   ║
║ [Discovery Filters] (config.json)                                ║
║                                                                   ║
║   Max Symbol Price:        [$60     ]                            ║
║   Min Liquidity (OI):      [500     ]                            ║
║   DTE Range Min:           [7       ]                            ║
║   DTE Range Max:           [60      ]                            ║
║                                                                   ║
║ [Capital Planner] (planner_config.json)                          ║
║                                                                   ║
║   Total Capital:           [$3000   ]                            ║
║   Target Position Size:    [$300    ]                            ║
║   Warning Threshold:       [80      ]% of total                  ║
║   Default Entry (days):    [14      ] days before earnings       ║
║   Default Exit (days):     [2       ] days before earnings       ║
║                                                                   ║
║ [Confluence Scoring] (config.json)                               ║
║                                                                   ║
║   Has Flow Alert:          [1       ]                            ║
║   Volume Surge:            [1       ]                            ║
║   Earnings Catalyst:       [1       ]                            ║
║   News Sentiment Strong:   [1       ]                            ║
║   OI Conviction High:      [1       ]                            ║
║   Min Confluence Score:    [2       ]                            ║
║                                                                   ║
║ [Display] (config.json)                                          ║
║                                                                   ║
║   Watchlist Limit:         [10      ]                            ║
║                                                                   ║
║ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ║
║                                                                   ║
║ [S] Save Changes  [R] Reset to Defaults  [ESC] Cancel            ║
╚══════════════════════════════════════════════════════════════════╝
```

**Validation:**
- All numeric fields: integers or floats as appropriate
- Reasonable ranges (no negative numbers, no zero divisions)
- Invalid input → Show error message below field, prevent save
- Changes only written to files on 'S' press

**Behavior:**
- `S` - Validate all fields, write to config.json + planner_config.json, close screen
- `R` - Reset all fields to original defaults (confirmation prompt)
- `ESC` - Discard unsaved changes, close screen
- `TAB` - Navigate between fields

---

### Modified Screen: Symbol Detail

**Add new keybinding:**
- `P` - Add this symbol to Capital Planner
- Opens Add Position modal with symbol + earnings_date pre-filled

**Footer update:**
```
[↑↓] Navigate  [ENTER] View Contract  [P] Add to Planner  [ESC] Back
```

---

## Technical Architecture

### File Structure
```
morning_view/
├── config.json                    (EXISTING - modified to add planner filters)
├── planner_config.json            (NEW - planner-specific settings)
├── planner_data.json              (NEW - position data)
├── capital_planner_data.py        (NEW - JSON read/write API)
├── screens/
│   ├── capital_planner.py         (NEW - main planner screen)
│   ├── earnings_browser.py        (NEW - browse upcoming earnings)
│   ├── capital_timeline.py        (NEW - Gantt timeline view)
│   ├── settings.py                (NEW - settings screen)
│   ├── symbol_detail.py           (MODIFY - add 'P' keybinding)
│   └── main_menu.py               (MODIFY - add planner + settings items)
└── tui_data.py                    (MODIFY - add planner data access methods)
```

### Data Access Layer: capital_planner_data.py

**Functions:**
```python
def load_planner_config() -> dict
def save_planner_config(config: dict) -> None
def load_positions() -> list[dict]
def save_positions(positions: list[dict]) -> None
def add_position(position: dict) -> str  # returns ID
def update_position(position_id: str, updates: dict) -> bool
def delete_position(position_id: str) -> bool
def get_position_by_id(position_id: str) -> dict | None
def archive_closed_positions(days_threshold: int = 7) -> int  # returns count
def get_capital_timeline(positions: list[dict]) -> dict  # compute utilization
def validate_position(position: dict) -> tuple[bool, str]  # returns (valid, error_msg)
```

### Database Queries (Read-Only)

**For Earnings Browser:**
```sql
SELECT
    e.symbol,
    e.earnings_date,
    e.earnings_time,
    o.close_price,
    o.total_open_interest,
    m.sector,
    m.industry
FROM earnings_upcoming e
JOIN oi_symbol_summary o ON e.symbol = o.symbol
JOIN symbol_metadata m ON e.symbol = m.symbol
WHERE e.earnings_date >= date('now')
  AND e.earnings_date <= date('now', '+90 days')
  AND o.trade_date = (SELECT MAX(trade_date) FROM oi_symbol_summary)
  AND o.close_price <= {max_price_from_config}
  AND o.total_open_interest >= {min_oi_from_config}
ORDER BY e.earnings_date
```

**For Pre-filling Add Position Modal (from Symbol Detail):**
```sql
SELECT
    symbol,
    earnings_date,
    earnings_time
FROM earnings_upcoming
WHERE symbol = {selected_symbol}
  AND earnings_date >= date('now')
ORDER BY earnings_date
LIMIT 1
```

---

## Warning Indicators

**Capital Utilization Warnings:**
- 80%+ of total capital → Yellow warning ⚠️
- 100%+ of total capital → Red warning ⛔
- Shown in weekly summary bars and timeline view

**No Blockers:**
- User can add positions that exceed capital limit
- User can enter nonsensical values (system warns but doesn't prevent)
- Philosophy: Personal use tool, flexible over rigid

**Exception: Validation Errors**
- Settings screen blocks save on invalid input (negative numbers, non-numeric, etc.)
- Add/Edit modal requires all fields filled (no partial saves)

---

## Error Handling

### Corrupted/Missing JSON Files

**planner_data.json corrupted:**
- Show error notification: "Position data corrupted. Creating fresh file."
- Create new empty file with version header
- Log error to console

**planner_config.json missing:**
- Silently create with defaults
- No error shown to user

**config.json corrupted:**
- Fallback to hardcoded defaults
- Show error notification
- TUI continues to function

### Database Errors

**earnings_upcoming query fails:**
- Earnings Browser shows: "Database unavailable. Cannot load earnings data."
- Add Position modal disables pre-fill (manual entry still works)

**oi_symbol_summary query fails:**
- Show stale data if available
- Warning message: "Live prices unavailable. Showing last known data."

---

## Archival Strategy

**Closed Positions:**
- Status "closed" positions remain visible in planner
- User can manually trigger archival (future feature)
- Auto-archival discussed but deferred (timing TBD - likely Monday cleanup or on-demand)

**Archived Data:**
- Moved to `archived_positions` array in planner_data.json
- Not displayed in main planner view
- Available for future historical analysis (out of scope v1)

---

## Success Metrics

**Qualitative (User Feedback):**
- "I know when my capital is locked up"
- "I can plan 4 weeks ahead without spreadsheets"
- "I'm more disciplined about entry/exit timing"

**Quantitative (Usage):**
- Number of positions planned per week (target: 5-10)
- Peak capital utilization (target: 70-90%)
- Time spent in planner vs other TUI screens

---

## Implementation Phases

### Phase 1: Data Layer (2-3 hours)
- Create `planner_config.json` with defaults
- Create `planner_data.json` structure
- Build `capital_planner_data.py` with all CRUD functions
- Add tests for data validation logic

### Phase 2: Settings Screen (2-3 hours)
- Build settings screen with form inputs
- Read/write to config.json + planner_config.json
- Input validation and error handling
- Add to main menu (item #7)

### Phase 3: Earnings Browser (3-4 hours)
- Build earnings browser screen
- Database query for tradeable earnings
- Apply filters from config
- Sort/filter controls
- Add to main menu or accessible from planner

### Phase 4: Capital Planner Main View (4-5 hours)
- Build hybrid view (summary + table)
- Weekly capital bar chart
- Positions table with sort/filter
- Add/Edit/Delete position modals
- Position calculator in add modal
- Notes field (truncated display)
- Add to main menu (item #6)

### Phase 5: Symbol Detail Integration (2 hours)
- Add 'P' keybinding to Symbol Detail
- Pre-fill logic for add modal
- Query earnings_upcoming for dates

### Phase 6: Timeline Detail View (3-4 hours)
- Build vertical Gantt chart screen
- Position bars with entry/exit markers
- Daily capital summary at bottom
- Toggle daily/weekly view
- Accessible from main planner ('V' key)

### Phase 7: Testing & Polish (2-3 hours)
- End-to-end testing of full workflow
- Edge case handling (empty data, invalid inputs)
- Visual polish (alignment, colors, spacing)
- Documentation updates (CLAUDE.md)

**Total Estimated Time: 18-24 hours**
**Target: Complete in one development day (ambitious but feasible)**

---

## Open Questions / Future Enhancements

**Deferred for Post-v1:**
1. Auto-archival timing for closed positions (Monday cleanup? On-demand? Auto after 7 days?)
2. Live contract prices integration (requires option_contracts scan for future dates)
3. Position status change notifications (alert when T-14 entry window opens)
4. Historical performance tracking (actual P&L vs planned)
5. Export planned positions to CSV/calendar formats
6. AI integration ("Ask Oracle about this play")
7. Earnings date change detection (compare planner vs DB, warn on drift)

---

## Appendices

### A. Sample planner_config.json (Default Values)
```json
{
  "capital": {
    "total_capital": 3000,
    "target_position_size": 300,
    "warning_threshold_pct": 80
  },
  "defaults": {
    "default_entry_days_before": 14,
    "default_exit_days_before": 2
  },
  "archival": {
    "auto_archive_closed": false,
    "archive_after_days": 7
  }
}
```

### B. Position ID Format
Format: `{symbol}_{earnings_date}_{sequence}`

Examples:
- `nvda_20251023_001` - First NVDA position for Oct 23 earnings
- `nvda_20251023_002` - Second NVDA position (if added another)
- `amd_20251024_001` - First AMD position

Sequence increments if same symbol+date added multiple times (edge case).

### C. Status Enum (Suggested Values)
User can enter freeform text, but suggested dropdown options:
- `planned` - Intend to trade
- `watching` - Maybe trade, monitoring
- `entered` - Actually bought position
- `closed` - Exited position

### D. Date Hint Calculations
In Add Position modal, show hints based on defaults:
- Entry hint: `earnings_date - default_entry_days_before`
- Exit hint: `earnings_date - default_exit_days_before`

Example:
```
Earnings: 2025-10-23
Default entry: 14 days before
Default exit: 2 days before

→ Entry hint: Oct 9 (2025-10-09)
→ Exit hint: Oct 21 (2025-10-21)
```

---

**End of PRD**
