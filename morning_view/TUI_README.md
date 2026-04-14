# Morning Views TUI - Interactive Terminal Dashboard

A terminal user interface for browsing Morning Views data with keyboard-driven navigation.

**Version:** 1.0 MVP
**Last Updated:** 2025-10-07
**Status:** Complete and ready for testing

---

## Quick Start

### Prerequisites
1. **Database:** `data/datalake_query.db` must exist and have data
2. **SQL Views:** Run `python morning_views.py` once to create Morning Views database views
3. **Python Environment:** textual library installed (`pip install textual`)

### Launch
```bash
python morning_view/mv_main.py
```

**If you get an error:**
- "SQL views not found" → Run `python morning_views.py` first
- "No data found" → Run OID morning scan to populate database
- "Database not found" → Sync or recreate `datalake_query.db`

---

## Navigation

### Main Menu
```
┌─ Morning Views ─────────────────────────────────────────────┐
│ 2025-10-07 07:35 AM                                         │
│ Market: BULLISH | Regime: normal                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│    [1] Today's Watchlist         (Top 20 symbols)           │
│    [2] Search Symbol                                        │
│    [Q] Quit                                                 │
│    [?] Keyboard Shortcuts                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Controls:**
- `1` - Today's Watchlist
- `2` - Search Symbol
- `Q` - Quit
- `?` - Help

---

## Screen Hierarchy

```
Main Menu
├── [1] Watchlist ────────┐
│   └─ Select Symbol ─────┤
│      ├─ [1] OI Timing   │
│      ├─ [2] OI Distribution
│      └─ [3] Compare Strikes
│
└── [2] Search ───────────┤
    └─ (same as Watchlist)
```

---

## Features

### 1. Watchlist Screen

**What it shows:**
- Top 20 symbols ranked by confluence score
- Direction bias (BULLISH/BEARISH) with color coding
- Active alerts count
- 5-day price change
- Primary signal (FLOW_ALERT, OI_SIGNAL, etc.)

**Controls:**
- `↑↓` - Navigate symbols
- `Enter` - View symbol detail
- `F` - Filter by signal type (placeholder)
- `S` - Sort options (placeholder)
- `ESC` - Back to main menu

**Visual Features:**
- ⭐ Star ratings for high confluence scores
- 🟢 Green for bullish bias
- 🔴 Red for bearish bias
- Color-coded price changes
- Status bar showing market context

**Example Row:**
```
2  MGM   4 ⭐⭐⭐  🟢 BULLISH  FLOW_ALERT  2  $33.93  +2.3%
```

---

### 2. Symbol Detail Hub

**What it shows:**
- Symbol overview (price, sector, industry)
- Confluence score with stars
- Direction bias and conviction level
- Menu for drilling into analysis

**Controls:**
- `1` - OI Timing Analysis
- `2` - OI Distribution
- `3` - Compare Strikes
- `ESC` - Back to watchlist

**Example:**
```
┌─ MGM - Symbol Detail ───────────────────────────────────────┐
│ Consumer Cyclical - Resorts & Casinos                       │
│                                                              │
│ Price: $33.93 | 5d Change: +2.3%                            │
│ Confluence Score: 4/5 ⭐⭐⭐ | Bias: BULLISH (MEDIUM)        │
│                                                              │
│    [1] OI Timing Analysis        (Smart Money vs Retail)    │
│    [2] OI Distribution           (Strikes, Greeks, Time)    │
│    [3] Compare Strikes           (Pick best contract)       │
└─────────────────────────────────────────────────────────────┘
```

---

### 3. OI Timing Screen

**What it shows:**
- Top 10 contracts by open interest
- When OI was built (date and price)
- Position type: PREDICTIVE (smart money) or CHASING (retail)
- Price movement since build
- Days since build (color-coded: green=fresh, yellow=aging, dim=old)

**Controls:**
- `↑↓` - Navigate contracts
- `ESC` - Back to symbol detail
- `?` - Help

**Visual Features:**
- 🧠 Green for PREDICTIVE positions
- 📈 Yellow for CHASING positions
- Green CALL / Red PUT color coding
- Move % color-coded (green positive, red negative)

**Key Insight:**
Look for **PREDICTIVE + fresh (≤7 days) + positive move** = smart money positioned early

**Example Row:**
```
1  $36  CALL  10/24  24,239  🧠 PREDICTIVE  10/03  $34.00  3 days  +5.6%
```

---

### 4. OI Distribution Screen

**What it shows:**
- Call/Put OI breakdown with ASCII bar charts
- Top 5 call and put strikes
- Time distribution (0-7, 8-21, 22-35, 36-60 DTE) with visual bars
- Moneyness distribution (ITM/ATM/OTM) for calls and puts
- Greek exposures (Delta, Gamma, Vega)
- Max pain level and distance from current price

**Controls:**
- `Scroll` - View full distribution
- `ESC` - Back to symbol detail

**Visual Features:**
- ASCII bar charts for percentages: `████████░░░░░░░░`
- Color-coded time buckets (green=0-7, yellow=8-21, cyan=22-35, blue=36-60)
- Bullish/Bearish tags based on net delta
- Visual emphasis on max gamma strike (pin risk)

**Example:**
```
TIME DISTRIBUTION (Days to Expiration)
──────────────────────────────────────────────────────────────
0-7 DTE   ██████████░░░░░░░░░░░░░░░░░░░░ 25.3%
8-21 DTE  ████████████████████░░░░░░░░░░ 48.7%
22-35 DTE ████████░░░░░░░░░░░░░░░░░░░░░░ 20.1%
36-60 DTE ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  5.9%
```

---

### 5. Compare Strikes Screen

**What it shows:**
- Top 15 CALL options (14-30 DTE)
- Price, Delta, Breakeven move%, Delta per dollar
- Open interest and volume
- Multi-select capability to build comparison basket

**Controls:**
- `↑↓` - Navigate options
- `Space` - Select/deselect contract (adds ☑ checkmark)
- `V` - View comparison summary (up to 4 contracts)
- `C` - Clear all selections
- `ESC` - Back to symbol detail

**Visual Features:**
- ⭐⭐⭐ Stars for high delta per dollar (>1.0)
- Color-coded breakeven: green (<5%), yellow (<10%), red (>10%)
- Color-coded DTE: yellow (≤14 days)
- Selection checkmarks in first column

**Strategy:**
- **High Delta/$** = Maximum leverage
- **Low Breakeven Move%** = Easier to profit
- **Low Theta** = More time to be right
- **High OI** = Better liquidity

**Example Row:**
```
☑  $36  10/24  14  $0.50  0.32  +7.6%  0.64 ⭐⭐  -$0.04  24,239
```

---

### 6. Search Screen

**What it shows:**
- Input field for symbol search
- Search results table (matches from watchlist)

**Controls:**
- Type symbol and press `Enter`
- `↑↓` - Navigate results
- `Enter` - View selected symbol detail
- `ESC` - Back to main menu

**Example:**
```
Search Symbol
─────────────
> AAL▊

Results:
Symbol  Score  Bias         Signal       Price
AAL     3      🔴 BEARISH   OI_SIGNAL    $11.27
```

---

### 7. Help Screen

**What it shows:**
- Complete keyboard shortcuts reference
- Screen-by-screen navigation guide
- Usage tips

**Controls:**
- `ESC` - Close help

**Access:**
- Press `?` on any screen to view help

---

## Keyboard Reference

### Global
- `Q` - Quit (from main menu)
- `?` - Help overlay
- `ESC` - Go back
- `Ctrl+E` - Edit Page with Claude (development tool)

### Navigation
- `↑↓` Arrow Keys - Navigate tables/menus
- `Enter` - Select item / drill down
- `1-9` Number Keys - Quick menu selection

### Watchlist
- `F` - Filter by signal type
- `S` - Sort options

### Compare Strikes
- `Space` - Select/deselect contract
- `V` - View selected comparison
- `C` - Clear selections

---

## Status Bars

Every screen has a context-aware status bar at the bottom showing:
- Current symbol or view
- Key metrics (market direction, selections, etc.)
- Available keyboard shortcuts

**Example:**
```
MGM | Signal: FLOW_ALERT | Active Alerts: 2 | 1-3: Views | ESC: Back | ?: Help
```

---

## Color Coding Guide

### Directional Bias
- 🟢 **Green** - BULLISH / Positive moves / CALL options
- 🔴 **Red** - BEARISH / Negative moves / PUT options
- 🟡 **Yellow** - NEUTRAL / Warnings / SOMEWHAT_BULLISH/BEARISH

### Quality Indicators
- ⭐⭐⭐ **3 stars** - Excellent (score ≥4, delta/$ >1.0)
- ⭐⭐ **2 stars** - Good (score ≥3, delta/$ >0.7)
- ⭐ **1 star** - Fair (score ≥2)

### Freshness
- **Green** - Fresh (0-7 days)
- **Yellow** - Aging (8-21 days)
- **Dim** - Old (>21 days)

### Smart Money
- 🧠 **Green PREDICTIVE** - Smart money positioned early
- 📈 **Yellow CHASING** - Retail chasing momentum

---

## Tips & Best Practices

### Daily Workflow
1. Launch TUI: `python morning_view/mv_main.py`
2. Review top 5 symbols on watchlist
3. For each interesting symbol:
   - Check OI Timing (PREDICTIVE = good signal)
   - View OI Distribution (check time buckets)
   - Compare Strikes (pick best delta/$ ratio)
4. Note trades in separate journal (or wait for trade tracking feature)

### What to Look For
- **High confluence (≥3)** = Multiple signals aligned
- **PREDICTIVE timing + fresh (<7 days)** = Smart money
- **BULLISH bias + MEDIUM/HIGH conviction** = Strong directional view
- **Delta/$ > 0.7** = Good leverage efficiency
- **Breakeven < 10%** = Realistic price target

### What to Avoid
- **CHASING positions + old (>14 days) + underwater** = Bagholders
- **Low OI (<500)** = Poor liquidity
- **Very high IV** = Expensive premium (check earnings calendar)

---

## Troubleshooting

### "SQL views not found"
**Solution:**
```bash
python morning_views.py
```
This creates the required SQL views in datalake_query.db.

### "No data found in database"
**Solution:**
Run OID morning scan to populate data:
```bash
python main.py --oid-morning
```

### "Database is locked"
**Solution:**
TUI uses `datalake_query.db` (read-only copy). If you see this error:
1. Check if another process is using the database
2. Run database sync: `python data/health/db_backup.py --sync --auto`

### Empty watchlist
**Possible causes:**
1. No trading data for today yet (run before market open)
2. Filters too strict (price <$60, OI >500)
3. Query database not synced with main database

**Solution:**
Check if data exists:
```bash
python tools/direct_db_query.py --sql "SELECT COUNT(*) FROM v_morning_watchlist"
```

### Emoji/Unicode not displaying
**Solution:**
Windows Terminal supports UTF-8. If you're using CMD or PowerShell:
1. Switch to Windows Terminal
2. Or set encoding: `chcp 65001` before running TUI

---

## Performance

- **Startup time:** <1 second (if views exist)
- **Screen load time:** <500ms per screen
- **Database size:** ~500MB (typical)
- **Memory usage:** ~50MB (textual app)

---

## Files

### TUI Application
- `morning_view/mv_main.py` - Main TUI application
- `morning_view/tui_data.py` - Database query helper

### Documentation
- `morning_view/TUI_README.md` - This file
- `morning_view/USER_GUIDE.md` - Original Morning Views guide
- `morning_view/FUTURE_FEATURES.md` - Planned enhancements

### Database
- `data/datalake_query.db` - Query database (read-only)
- SQL Views: `v_morning_watchlist`, `v_symbol_oi_detail`, `v_oi_timing_context`, `v_option_comparison`

---

## Known Limitations

### MVP Scope
1. **Read-only:** Cannot enter trades (see FUTURE_FEATURES.md)
2. **Static data:** No real-time refresh (manual restart required)
3. **Comparison view:** Multi-select works, full side-by-side view pending
4. **Filtering:** UI exists but data layer support needed
5. **Sorting:** Placeholder only

### Design Limitations
1. **Windows Terminal only:** Optimized for Windows (Ben's environment)
2. **Morning data:** Shows yesterday's volume/Greeks + today's OI
3. **CALL options only:** Compare Strikes screen (PUTs need separate view)
4. **DTE range:** 14-30 days for comparison (configurable in code)

---

## Future Enhancements

See `FUTURE_FEATURES.md` for complete roadmap.

**Highest Priority:**
1. Trade entry form + tracking
2. Active positions view
3. Full comparison view (side-by-side)
4. Real-time data refresh

---

## Development Tools

### Edit Page with Claude (Ctrl+E)

The TUI includes a built-in development accelerator that spawns Claude Code sessions for quick bug fixes and feature additions.

**How to use:**
1. Press `Ctrl+E` on any screen
2. A modal appears showing:
   - Auto-detected current screen and file
   - Log file location
   - Input field for your request
3. Type your development request (e.g., "Fix the table alignment issue")
4. Press Enter or click Launch
5. New Claude Code window opens with full context pre-loaded

**What gets passed to Claude:**
- Current screen's Python file (e.g., `@morning_view/screens/flow_alerts.py`)
- Your typed request
- Screen name and reproduction steps
- Today's log file location

**Example prompt generated:**
```
I need help with @morning_view/screens/main_menu.py.
Fix the alignment of the admin mode menu item.
This is the MainMenu screen.
To reproduce, run python morning_view/mv_main.py and navigate to this screen.
Check logs/morning_view_2025-10-31.log for recent errors.
```

**Benefits:**
- Zero context switching - stay in the TUI
- Automatic file detection - no manual file paths
- Log breadcrumbs included - Claude can check for errors
- Works in both query and admin mode

**Files:**
- `tools/launch_claude_dev.py` - Launcher script
- `morning_view/modals/claude_dev_modal.py` - Input modal
- `mv_main.py` - Global hotkey binding

---

## Support & Feedback

**Report Issues:**
- Check `morning_view/logs/` for error logs
- Include error message and steps to reproduce

**Feature Requests:**
- Add to FUTURE_FEATURES.md
- Priority driven by user feedback

---

## Credits

**Built with:**
- [Textual](https://github.com/Textualize/textual) - Python TUI framework
- SQLite - Database
- Rich - Terminal formatting

**Developed:** 2025-10-07
**Style:** Dwarf Fortress / Paradox Games inspired
**Philosophy:** Dense information, keyboard-driven, minimal mouse usage

---

**Enjoy your morning analysis! 📊**
