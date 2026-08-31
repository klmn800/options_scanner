# Capital Planner - Quick Start Guide

**Built:** 2025-10-12
**Status:** Production Ready
**Estimated Build Time:** 20 minutes (actual: ~2 hours including PRD)

---

## What is Capital Planner?

A forward-looking earnings trade planning system integrated into Morning View TUI. Helps you strategically plan option positions 90 days ahead, visualize capital deployment, and enforce systematic entry/exit discipline.

**Goal:** Help achieve $500/week profit target through data-driven position planning.

---

## Quick Start

### Access Capital Planner

1. Run Morning View TUI:
   ```bash
   python morning_view/mv_main.py
   ```

2. Press `6` for Capital Planner

### Add Your First Position

**Method 1: From Capital Planner**
1. Press `A` to add position
2. Fill in:
   - Symbol (e.g., NVDA)
   - Earnings date (YYYY-MM-DD)
   - Entry date (hint: T-14 shown)
   - Exit date (hint: T-2 shown)
   - Contracts (e.g., 2)
   - Price per contract (e.g., 5.50)
3. Review calculator (shows cost vs $300 target)
4. Add notes (optional, 500 char max)
5. Press `S` to save

**Method 2: From Symbol Detail**
1. Browse symbols (items #1-5 on main menu)
2. Press ENTER on a symbol
3. Press `P` to add to planner
4. Symbol + earnings date auto-filled!
5. Fill in position details and save

---

## Key Features

### 1. Position Management
- **Add/Edit/Delete** positions
- **Status tracking:** planned → watching → entered → closed
- **Position calculator:** Shows cost vs target with warnings
- **Notes field:** Track thesis, key levels, strategy

### 2. Capital Visualization
- **Weekly summary bars:** Visual utilization %
- **Warning indicators:** ⚠️ at 80%+ of total capital
- **Timeline view:** Press `V` for Gantt chart
- **Daily/Weekly toggle:** Press `D` in timeline view

### 3. Planning Workflow
- **Filter by status:** Press `F` to cycle (all/planned/watching/entered)
- **Sort by date:** Positions auto-sorted by entry date
- **Earnings Browser:** Press `8` for upcoming earnings (90 days)

---

## Configuration

### Settings Screen (Item #7)

**Capital Planner Settings:**
- Total Capital: $3000 (default)
- Target Position Size: $300 (default)
- Warning Threshold: 80% (default)
- Default Entry: 14 days before earnings
- Default Exit: 2 days before earnings

**Discovery Filters:**
- Max Symbol Price: $60
- Min Liquidity (OI): 500
- DTE Range: 7-60 days

Press `S` to save changes, `R` to reset to defaults.

---

## Keyboard Shortcuts

### Capital Planner Screen
- `A` - Add position
- `E` - Edit selected position
- `D` - Delete selected position
- `V` - View timeline (Gantt chart)
- `F` - Filter by status
- `R` - Refresh
- `ESC` - Back to main menu

### Symbol Detail Screen
- `P` - Add to planner
- `W` - Add/remove from watchlist
- `C` - Toggle confluence breakdown
- `1-4` - View analysis screens

### Timeline View
- `D` - Toggle daily/weekly view
- `R` - Refresh
- `ESC` - Back to planner

---

## Data Storage

**Location:** JSON files (no database writes)
- `morning_view/planner_config.json` - Settings
- `morning_view/planner_data.json` - Positions

**Benefits:**
- No DB contention during collection windows
- Portable (can version control)
- Safe (production DB never touched)

**Archival:**
- Closed positions remain visible until manually archived
- Auto-archival coming in future release

---

## Example Workflow

### Planning 4 Weeks Ahead

1. **Browse Upcoming Earnings** (Item #8)
   - See 264 tradeable symbols (<$60, 500+ OI)
   - Sort by date/price/sector

2. **Identify Plays**
   - Use existing analysis (Discovery, Watchlist, Earnings Calendar)
   - Press `P` on symbols with upcoming earnings

3. **Review Capital Timeline**
   - Press `V` from Capital Planner
   - Check for peak deployment periods
   - Adjust if >80% utilization

4. **Execute Systematically**
   - Update status as you trade (planned → entered → closed)
   - Track actual vs planned timing
   - Add notes on what worked/didn't

---

## Tips & Best Practices

**Position Sizing:**
- Target $300/position for consistency
- Calculator warns if >2× target ($600+)
- Adjust for cheaper symbols (buy more contracts)

**Entry/Exit Timing:**
- Defaults: T-14 entry, T-2 exit (based on IV buildup pattern)
- Adjust per position as needed
- Track what timing works best for you

**Capital Management:**
- Avoid >80% utilization (leaves buffer)
- Watch for overlapping positions
- Plan exits to free up capital for new entries

**Discipline:**
- Use notes to document thesis BEFORE entering
- Update status as you execute
- Review timeline weekly to stay on plan

---

## Known Limitations (v1)

**Not Included:**
- ❌ Live contract prices (manual entry only)
- ❌ Actual P&L tracking (manual calculation)
- ❌ Auto-archival of closed positions
- ❌ Earnings date change detection
- ❌ Export to CSV/calendar

**Coming Soon:**
- Historical performance analysis
- AI strategy recommendations
- Automated archival (Monday cleanup)
- Integration with Earnings Intelligence strategy

---

## Troubleshooting

**"No upcoming earnings found"**
- Symbol may not have earnings in next 90 days
- Or earnings_upcoming table needs refresh

**Calculator shows warning**
- Position cost exceeds $300 target
- Warning only - save still allowed
- Adjust contracts or wait for better entry

**Timeline shows empty**
- No active positions (add some first!)
- Or all positions are status="closed"

**Settings won't save**
- Check for invalid values (negative numbers, etc.)
- Error message will show specific field

---

## File Structure

```
morning_view/
├── planner_config.json              # Settings
├── planner_data.json                # Position data
├── capital_planner_data.py          # Data access layer
└── screens/
    ├── capital_planner.py           # Main planner screen
    ├── capital_timeline.py          # Gantt timeline view
    ├── earnings_browser.py          # Browse upcoming earnings
    ├── settings.py                  # Config editor
    └── symbol_detail.py             # (Modified - added 'P' key)
```

---

## Support

**Documentation:**
- Full PRD: `docs/_local/prd/prd-capital-planner.md`
- Main README: `CLAUDE.md`

**Testing:**
- Run test suite: `python morning_view/test_planner_data.py`
- Manual testing checklist in PRD

---

**Built for Ben's $500/week earnings play strategy**
*Data-driven discipline through forward-looking capital planning*
