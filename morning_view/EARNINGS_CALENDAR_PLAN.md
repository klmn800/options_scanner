# Earnings Calendar - Implementation Plan

**Status**: Static visual mockup complete (2025-10-11)
**Next Phase**: Add interactivity (navigation, drill-downs)
**Database**: Read-only access to `datalake_query.db`

---

## Current Implementation

### What's Built
- **File**: `morning_view/screens/earnings_calendar.py`
- **Data Layer**: `morning_view/tui_data.py:605` - `get_earnings_calendar(days_ahead=10)`
- **Menu Integration**: Press `3` from main menu launches calendar
- **Visual**: 2-week grid (10 trading days, split into 2 rows of 5)
- **Sector Emojis**: 🏦 finance, 💻 tech, 🏥 healthcare, 🍕 consumer, etc.
- **Color Coding**: Green (STRONG BUY/BUY), Yellow (WATCH), White (NEUTRAL)
- **Mouse Support**: Disabled globally in `mv_main.py:47` (prevents escape codes)

### What It Shows
```
Mon 10/14         │ Tue 10/15         │ Wed 10/16         │ Thu 10/17         │ Fri 10/18
──────────────────│ ──────────────────│ ──────────────────│ ──────────────────│ ──────────────────
🏦 C              │ 🏦 BAC            │ 📺 NFLX           │ 🏦 MS             │ 🏦 ALLY
🏦 JPM            │ 🏥 ABT            │ 💻 TSM            │ 🏦 GS             │ 🏦 AXP
🏥 JNJ            │ 🏦 CFG            │                   │ 🏦 BK             │
🍕 DPZ            │ 📊 EFX            │                   │                   │
⚙️ OMC            │                   │                   │                   │

│ 5 earnings      │ 4 earnings        │ 2 earnings        │ 3 earnings        │ 2 earnings
```

### User Feedback
- ✅ Layout looks good
- ✅ Emojis are semantic and helpful (easy to scan for sector clusters)
- ✅ Day separators work well (`│` vertical bars)
- ❌ Legend removed (unnecessary)
- ❌ Mouse support disabled (was interfering)

---

## Project Scope: Calendar Navigation (Phases 1-3)

**Estimated Time**: 6 hours
**Goal**: Make the calendar interactive with 3-level navigation

### Navigation Model (3 Levels)

**Level 1: Calendar Grid** (current screen)
- Arrow keys navigate between days (highlight selected day)
- Shows 2-week overview
- Visual indicator for selected day (border/color change)

**Level 2: Day Detail** (drill-down)
- Press ENTER on selected day → full list for that day
- DataTable with columns:
  - Symbol
  - Signal (STRONG BUY / BUY / WATCH / NEUTRAL)
  - Time (BMO / AMC / Unknown)
  - Expected Move %
  - Historical Avg Move %
  - Difference
  - Sector
- Sortable by column
- Color-coded rows by signal
- Count summary: "10 earnings - 3 STRONG BUY, 5 BUY, 2 WATCH"

**Level 3: Symbol Detail** (existing screen)
- Press ENTER on symbol row → existing SymbolDetailScreen
- Reuses existing infrastructure (screens/symbol_detail.py)

### Example Flow
```
1. User launches calendar → sees 2-week grid
2. Arrow keys highlight "Tue 10/15" (14 earnings)
3. Press ENTER → day detail table appears
4. Arrow keys navigate table rows
5. Press ENTER on "BAC" → existing symbol detail screen
6. ESC → back to day detail
7. ESC → back to calendar grid
8. ESC → back to main menu
```

---

## Technical Implementation Plan

### Phase 1: Make Grid Navigable (2-3 hours)
**File**: `morning_view/screens/earnings_calendar.py`

**Current Issue**: Grid is static text in a `Static` widget - can't navigate

**Solution**: Use DataTable or custom widget with focus states

**Option A: Hybrid Approach (Recommended)**
- Keep Static widget for visual grid
- Add invisible DataTable overlay with dates as rows
- Arrow keys move DataTable cursor
- Highlight selected day in Static content
- Enter triggers day detail view

**Option B: Pure DataTable**
- Abandon grid layout
- Use single-column DataTable with date rows
- Expandable rows show symbols for that day
- Simpler but loses visual calendar feel

**Option C: Custom Widget**
- Build custom Textual widget with grid logic
- Handle keyboard input manually
- Most flexible but most complex

**Recommendation**: Go with Option A (hybrid) - keep visual grid, add navigation layer

### Phase 2: Day Detail Screen (1-2 hours)
**New File**: `morning_view/screens/earnings_day_detail.py`

**Implementation**:
```python
class EarningsDayDetailScreen(Screen):
    def __init__(self, date: str, earnings_list: List[Dict]):
        self.date = date
        self.earnings_list = earnings_list

    def compose(self):
        # Header: "Earnings for Tuesday, October 15 - 14 events"
        # DataTable with earnings data
        # Status bar: "Enter: Symbol Detail | S: Sort | ESC: Back"

    def on_data_table_row_selected(self, event):
        symbol = event.row_key.value
        # Launch SymbolDetailScreen (existing)
```

**DataTable Columns**:
- Symbol (with emoji)
- Signal (color-coded)
- Time (BMO/AMC)
- Exp Move % (straddle_expected_move_pct)
- Hist Avg % (historical_avg_move_pct)
- Diff (move_difference_pct)
- Sector

**Sorting**: Allow sort by any column (press S to cycle)

### Phase 3: Calendar Navigation (1-2 hours)
**File**: `morning_view/screens/earnings_calendar.py`

**Add State Tracking**:
```python
def __init__(self):
    self.selected_date_idx = 0  # Index into sorted date list
    self.earnings_by_date = {}
    self.sorted_dates = []

def on_key(self, event):
    if event.key == "left":
        self.selected_date_idx = max(0, self.selected_date_idx - 1)
        self.refresh_display()
    elif event.key == "right":
        self.selected_date_idx = min(len(self.sorted_dates) - 1, self.selected_date_idx + 1)
        self.refresh_display()
    elif event.key == "enter":
        selected_date = self.sorted_dates[self.selected_date_idx]
        earnings = self.earnings_by_date[selected_date]
        self.app.push_screen(EarningsDayDetailScreen(selected_date, earnings))
```

**Visual Highlight**: Update `_build_week_row()` to highlight selected day
- Add border or background color
- Use Textual rich markup: `[on blue]...[/on blue]`

---

## Data Schema Reference

### earnings_upcoming table
```sql
symbol TEXT PRIMARY KEY
earnings_date DATE NOT NULL
earnings_days_ahead INTEGER
earnings_time TEXT  -- 'BMO', 'AMC', 'Unknown'
straddle_expected_move_pct REAL
historical_avg_move_pct REAL
move_difference_pct REAL
earnings_play_signal TEXT  -- 'STRONG BUY', 'BUY', 'WATCH', 'NEUTRAL'
earnings_alert BOOLEAN
```

### symbol_metadata table
```sql
symbol TEXT PRIMARY KEY
sector TEXT
industry TEXT
```

### Query in use
```sql
SELECT
    e.symbol, e.earnings_date, e.earnings_time,
    e.straddle_expected_move_pct, e.historical_avg_move_pct,
    e.move_difference_pct, e.earnings_play_signal,
    sm.sector, sm.industry
FROM earnings_upcoming e
LEFT JOIN symbol_metadata sm ON e.symbol = sm.symbol
WHERE e.earnings_days_ahead <= 10
ORDER BY e.earnings_date ASC, e.symbol ASC
```

---

## Calendar-Specific Enhancements (Future)

### Filters
- Toggle: Show only STRONG BUY / BUY signals
- Toggle: Show only symbols with sector peers (arbitrage opportunities)
- Toggle: Show only >3% expected moves
- Filter by sector (only show banks, only tech, etc.)

### Sector Grouping
- Day detail view groups by sector
- Shows: "Banks (7) | Healthcare (3) | Tech (2)"
- Helps identify sector concentration days

### Calendar Navigation
- Jump to specific date (press D → date picker)
- Jump to next big day (>10 earnings)
- Jump to next STRONG BUY day

### Export
- Press X → export day's earnings to clipboard (CSV format)
- Useful for pasting into trading journal

---

## Code Locations

### Files Modified
- `morning_view/tui_data.py` - Added `get_earnings_calendar()` method
- `morning_view/screens/earnings_calendar.py` - New calendar screen (static mockup)
- `morning_view/screens/__init__.py` - Added EarningsCalendarScreen export
- `morning_view/screens/main_menu.py` - Added menu option 3 binding
- `morning_view/mv_main.py` - Disabled mouse support globally

### Sector Emoji Mapping
Location: `morning_view/screens/earnings_calendar.py:14-37`

```python
SECTOR_EMOJI = {
    'Financial Services': '🏦',
    'Healthcare': '🏥',
    'Technology': '💻',
    'Communication Services': '📱',
    'Consumer Cyclical': '🍕',
    'Industrials': '⚙️',
    'Airlines': '✈️',
    'Automotive': '🚗',
    # ... etc
}
```

Extend this as needed for new sectors.

---

## Testing

### Current State
- Launch TUI: `python morning_view/mv_main.py`
- Press `3` → view calendar
- ESC → back to menu
- R → refresh calendar

### After Navigation Added
- Arrow keys should move highlight between days
- Enter should drill into day detail
- Enter on symbol should open existing symbol detail screen
- ESC should navigate back up the hierarchy

### Test Cases
1. **Empty day**: Day with 0 earnings should show "(none)" and pressing Enter should do nothing
2. **Busy day**: Day with 14+ earnings should show scrollable list
3. **Past date**: Dates in the past should not appear in calendar (query filters `>= DATE('now')`)
4. **Sector clustering**: Visual scan should make bank concentration obvious (10/15 has 7 bank earnings)

---

## Design Decisions

### Why Calendar Grid vs Scrollable List?
- **Grid**: Better visual overview, pattern recognition, planning aid
- **List**: More data density, easier navigation, familiar pattern
- **Decision**: Start with grid (more novel UI), can add list toggle later

### Why 10 Days?
- 2 weeks of trading days fits nicely in 2 rows of 5
- Aligns with typical "next week or two" planning horizon
- Configurable: change `days_ahead` parameter if needed

### Why Static Text + Overlay?
- Keeps visual grid intact (hard to build with pure DataTable)
- Arrow key navigation feels natural
- Textual's Static widget handles rich markup well

### Why Sector Emojis?
- **Semantic decorations**: Encode information without cognitive load
- Quick sector clustering recognition ("oh, all banks today")
- Fun and visually distinct

---

## Next Developer: Start Here

1. **Read this document** (you're doing it!)
2. **Test current state**: Launch TUI, press 3, see the mockup
3. **Pick Phase 1 approach**: Hybrid (recommended) or pure DataTable
4. **Implement day selection**: Arrow keys + highlight
5. **Build day detail screen**: New file with DataTable
6. **Wire navigation**: Enter on day → detail, Enter on symbol → existing symbol detail
7. **Test thoroughly**: Navigate all 3 levels, ESC back up
8. **Add filters/enhancements**: Optional, based on user feedback

**Questions?** Reference existing screens:
- `screens/discovery.py` - DataTable with navigation
- `screens/symbol_detail.py` - Screen that receives symbol parameter
- `screens/oi_timing.py` - DataTable with Enter drill-down

---

---

## ✅ Implementation Complete (2025-10-11)

**Phases 1-2 Completed:**
- ✅ **Calendar Grid Navigation**: Arrow keys, blue highlight, proper 10-day trading calendar
- ✅ **Day Detail Screen**: DataTable with all earnings, ENTER to drill into Symbol Detail
- ✅ **3-Level Navigation**: Calendar → Day Detail → Symbol Detail (all working with ESC back)
- ✅ **Data Fix**: Uses actual date range instead of `earnings_days_ahead` field
- ✅ **Windows Compatible**: ASCII separators (`|` and `=`) for cp1252 encoding
- ✅ **Emoji Alignment**: Custom padding function accounts for emoji visual width

**Files Created/Modified:**
- `morning_view/screens/earnings_calendar.py` - Full calendar with navigation
- `morning_view/screens/earnings_day_detail.py` - New day detail screen
- `morning_view/tui_data.py` - Updated `get_earnings_calendar()` with `end_date` param
- `morning_view/screens/__init__.py` - Added EarningsDayDetailScreen export

**Test Command:** `python morning_view/mv_main.py` → Press `3` → Navigate with arrows → ENTER on busy day (10/23)

**Optional Future Enhancements** (see section above):
- Filters (by signal, sector, move %)
- Sector grouping in day detail
- Export to clipboard
- Column sorting in day detail table

**Last Updated**: 2025-10-11
**Status**: ✅ Phases 1-2 Complete, working in production
**User Sentiment**: "This is great!" - wife loves the emojis 🎉

---

## 🎯 Additional Enhancements (Post-Initial Release)

### Calendar Extension: 2 Weeks → 4 Weeks (2025-10-11)
**Status**: ✅ Complete

**Changes:**
- Extended from 10 trading days (2 weeks) to 20 trading days (4 weeks)
- Split into 4 rows of 5 days each
- Updated display text: "Next 4 Weeks (20 Trading Days)"
- File: `morning_view/screens/earnings_calendar.py:126-183`

**Rationale**: User wanted longer planning horizon for earnings plays

---

### Flow Alerts Screen (2025-10-11)
**Status**: ✅ Complete

**New Feature**: Simple flow alerts reference table showing recent unusual options activity
- **File**: `morning_view/screens/flow_alerts.py` (NEW)
- **Menu**: Press `4` from main menu
- **Data**: Last 2 weeks of flow alerts
- **Columns**: Date, Symbol, Strike, Exp, Type, Money, UL, Vol, OI, IV, Last, Score
- **Filter**: Applies tradeable filter (see below)

**Data Source**: `tui_data.py:693` - `get_flow_alerts(days_back=14)`

**Bug Fixed**: Duplicate row keys - now uses loop index as unique key

---

### Config-Based Universal Tradeable Filter (2025-10-11)
**Status**: ✅ Complete

**Problem**: Filter criteria hardcoded in 5 locations (<$60 price, 500+ OI)

**Solution**: Centralized config in `config.json`
```json
"tradeable_filter": {
    "max_underlying_price": 60.0,
    "min_open_interest": 500,
    "description": "Universal filter for tradeable symbols/contracts across TUI"
}
```

**Implementation:**
1. **Config Loading** (`tui_data.py:50-61`): MorningViewsData.__init__() loads values
2. **SQL Filters Updated**:
   - `get_earnings_calendar()` - Uses `self.max_underlying_price` and `self.min_open_interest`
   - `get_flow_alerts()` - Uses parameterized query with config values
3. **Python Filter Updated** (`earnings_calendar.py:141`): Uses `data.max_underlying_price`
4. **Display Strings Updated**: Both screens show dynamic filter values
5. **Docstrings Updated**: Reference "config.json tradeable_filter values"

**Files Modified:**
- `config.json` - Added tradeable_filter section
- `morning_view/tui_data.py` - Config loading and SQL filter updates
- `morning_view/screens/earnings_calendar.py` - Python filter and display string
- `morning_view/screens/flow_alerts.py` - Display string

**Benefits:**
- Single source of truth for filter criteria
- No code changes needed to adjust filters
- Graceful fallback to defaults (60/500) if config missing

**Architecture Note**: Discovery/watchlist views remain hardcoded at 60/500 since SQL views are static and used by multiple tools. Only TUI-specific queries use dynamic config.

---

**Last Updated**: 2025-10-11 (Post-Release Enhancements)
**Next Steps**: None currently - all requested features complete
