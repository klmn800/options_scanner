# Morning Views Development Journal

**Living Document** - Track changes, ideas, issues, and evolution of the Morning Views TUI system.

---

## 📋 Table of Contents
- [Daily Changelog](#daily-changelog)
- [Future Enhancements](#future-enhancements)
- [Known Issues](#known-issues)
- [Design Decisions](#design-decisions)
- [User Experience Notes](#user-experience-notes)

---

## 📅 Daily Changelog

### 2025-10-08 - Config Integration & Data Freshness
**Changes:**
- ✅ Integrated `config.json` reading into TUI (mv_main.py)
- ✅ Replaced hardcoded `limit=20` with dynamic `config.display.watchlist_limit`
- ✅ Main menu now shows correct limit dynamically (e.g., "Top 10 symbols")
- ✅ Both _load_watchlist() and action_refresh() now respect config limit
- ✅ Added data freshness indicator: "Latest scan: X:XX PM" on main menu
- ✅ Manual database sync fixed date display issue (was showing 10/6, now 10/7)

**User Feedback:**
- TUI works well and will be primary interface going forward
- Config should be editable via TUI in future (Settings screen)
- Data freshness visibility is important for intraday use

**Technical Notes:**
- Config loaded in MorningViewsApp.__init__() as self.config
- Screens access via self.app.config.get('display', {}).get('watchlist_limit', 20)
- Fallback to 20 if config missing or malformed
- Added get_latest_scan_time() to tui_data.py for freshness tracking

### 2025-10-08 - Database Sync Infrastructure (Flow Monitor Integration)
**Context:** Flow Monitor performance optimization that improves Morning Views data freshness

**Changes:**
- ✅ Quick-sync integrated into Flow Monitor market hours cycle (~every 15 minutes)
- ✅ Watermark-based sync: only copies new rows since last sync (~95K rows in ~3 minutes)
- ✅ Database index optimization: dropped 5 redundant indexes on flow_options_scans
- ✅ WAL checkpoint added after storage operations to prevent bloat

**Impact on Morning Views:**
- Query database (datalake_query.db) stays current during market hours
- TUI refresh shows flow data within 15 minutes of collection
- Automatic background syncs require no manual intervention

**Technical:**
- Quick-sync tool: `data/health/db_backup.py --quick-sync`
- Syncs: flow_alerts, flow_options_scans tables only
- Performance: ~460 rows/sec, 3-minute sync cycles

---

## 🚀 Future Enhancements

### Realistic (Near-term)
- [ ] **Settings Screen** (Priority: HIGH)
  - Edit watchlist_limit (5, 10, 15, 20)
  - Adjust filters (max_symbol_price, min_liquidity_oi, DTE range)
  - Toggle display options (show/hide certain columns)
  - All changes write back to config.json
  - Accessible via "S" key from main menu

- [ ] **Refresh Improvements**
  - Show "Refreshing..." spinner during database queries
  - Display time since last refresh
  - Auto-refresh option (every N minutes)
  - Notification when new data available

- [ ] **Filter & Sort Enhancements**
  - Implement functional filter cycling (FLOW_ALERT, EARNINGS, etc.)
  - Sort by Score, Alerts, Price Change, etc.
  - Save filter/sort preferences to config

- [ ] **Symbol Detail Enhancements**
  - Add "Notes" field for tracking personal observations
  - Show historical confluence scores (trending up/down)
  - Link to earnings calendar view
  - Quick action: "Add to personal watchlist"

### Ambitious (Long-term)
- [ ] **Live Data Integration**
  - WebSocket connection to Flow Monitor for real-time updates
  - Flash notification when new high-significance alert triggers
  - Live price updates (every 1-5 seconds during market hours)
  - Show "LIVE" indicator when streaming active

- [ ] **Chart Visualization**
  - Textual-based ASCII charts for OI distribution
  - Historical price sparklines in watchlist
  - Greek exposure visualizations (bar charts)

- [ ] **Multi-Strategy View**
  - Switch between Morning OID view and Flow Monitor view
  - Separate tabs for different strategies
  - Cross-strategy symbol comparison

- [ ] **Export & Sharing**
  - Export watchlist to CSV/JSON
  - Share symbol analysis via email
  - Generate PDF reports

- [ ] **AI Assistant Integration**
  - Natural language queries: "Show me all high-conviction bearish plays"
  - Smart recommendations: "Based on your trading style..."
  - Risk analysis: "What's the downside on this position?"

---

## ⚠️ Known Issues

### Active Issues
- None currently identified

### Resolved Issues
- ~~Hardcoded watchlist limit (20) - fixed 2025-10-08~~
- ~~Missing data freshness indicator - fixed 2025-10-08~~
- ~~Date display showing stale data (10/6 instead of 10/7) - fixed via manual sync~~

---

## 🏗️ Design Decisions

### Why Single Config File?
**Decision:** Use `morning_view/config.json` for both CLI and TUI
**Rationale:** TUI is becoming primary interface, avoid duplicate config management
**Alternative Considered:** Separate tui_config.json - rejected due to maintenance burden

### Why Hybrid Data Model (Today's OI + Yesterday's Other Data)?
**Decision:** SQL views join today's OI with yesterday's volume/greeks/price
**Rationale:** Morning Views runs at 7:30 AM after morning OID scan
- Today's data only has OI (lagging indicator, shows current positions)
- Yesterday's data has complete volume, price action, greeks
**Implementation:** Self-join on oi_symbol_summary using MAX(trade_date) logic

### Why Per-Query Database Connections?
**Decision:** Open/close connections for each query instead of persistent connection
**Rationale:** Prevents "database locked" errors when multiple processes access query DB
**Implementation:** Context manager pattern in tui_data.py (_get_connection method)

### Why Limit LIMIT in SQL Views?
**Decision:** v_morning_watchlist has `LIMIT 20` hardcoded in SQL
**Issue:** This overrides config.display.watchlist_limit
**TODO:** Consider removing SQL LIMIT and only filtering in Python layer
**Workaround:** Current approach works because Python get_watchlist(limit=N) can request less than 20

---

## 👤 User Experience Notes

### What Works Well
- **Keyboard Navigation:** Arrow keys, Enter, ESC feel natural and responsive
- **Visual Hierarchy:** Color-coded biases (🟢 BULL, 🔴 BEAR) are immediately clear
- **Information Density:** Strikes good balance between detail and readability
- **Context Preservation:** Status bars keep you oriented (market regime, scan time)

### Pain Points
- **Config Editing:** Currently requires text editor, would be better in TUI
- **Refresh Ambiguity:** Not obvious when data was last refreshed (now showing scan time)
- **Filter Placeholders:** "F" key shows warning, not actual filtering yet

### Usage Patterns Observed
- **Morning Routine:** Launch TUI at 7:30 AM, review watchlist, drill into top 3-5 symbols
- **Intraday Checks:** Press R to refresh every 30 minutes during market hours
- **Symbol Deep Dive:** OI Timing screen most valuable for understanding smart money positioning

### Feature Requests from User
1. **Settings Screen** - "I'd like to change the limit without editing files"
2. **Data Confidence** - "How do I know if this data is fresh or stale?"
3. **Quick Actions** - "Would love to copy symbol to clipboard or open in TradingView"

---

## 📝 Notes for Future Claude Developers

### When Making Changes
1. **Update this journal** - Add dated entry under Daily Changelog
2. **Test with config.json** - Ensure changes respect user preferences
3. **Check both CLI and TUI** - Both tools share the same data/config
4. **Consider freshness** - Morning Views runs 7:30 AM, evening OID at 5 PM
5. **Database locking** - Always use query DB (datalake_query.db), never primary during collection

### Key Files to Know
- `mv_main.py` - TUI application (Textual framework)
- `tui_data.py` - Database query layer (read-only)
- `morning_views.py` - CLI version (still used for email delivery)
- `config.json` - Shared configuration (filters, limits, scoring)

### Debugging Tips
- **Views not found:** Run `python morning_view/morning_views.py` to create SQL views
- **Database locked:** Check if OID or Flow Monitor collection is running
- **Config not loading:** Verify config_path is relative to mv_main.py location
- **Hardcoded values:** Search codebase for literal "20" or filter values

### Architecture Philosophy
- **Simple is better** - Favor straightforward solutions over clever abstractions
- **Config-driven** - Make behavior adjustable via config.json when reasonable
- **Fail gracefully** - Show error messages, don't crash on missing data
- **User-first** - Ben's workflow drives design decisions, not technical elegance

---

## 🔍 Enhancement Session Notes - 2025-10-08 (Afternoon)

**Context:** Ben using TUI in production, providing detailed feedback on each screen

### WATCHLIST Screen

**Issue 1: Stale Price Data**
- **Current:** Shows yesterday's close_price (by design - from hybrid data model)
- **Problem:** Price out of date during market hours
- **Proposed Solution:** Use real-time price from `flow_options_scans.underlying_price`
  - Query most recent underlying_price for symbol from flow_options_scans table
  - Updates throughout day as Flow Monitor scans complete (~every 15 min)
  - Gives intraday price movement context
- **Open Question:** How to handle when no scan data exists (pre-market/weekends)? Fall back to yesterday's close?

**Issue 2: Missing Visual Cue for Drill-Down**
- **Need:** User doesn't know ENTER key opens Symbol Detail
- **Solution:** Add visual indicator "[Enter: Detail]" to status bar or row highlight

---

### SYMBOL DETAIL Screen

**Feature Request 1: AI Analysis (Priority: HIGH)**
- **Hotkey:** Will be mapped to #4
- **Status:** Ben working on this separately in another window
- **Action:** Coordinate with his implementation, don't overlap work

**Feature Request 2: Confluence Score Breakdown**
- **Current:** Just shows score number (e.g., "3/5 ⭐⭐")
- **Need:** Expandable menu/display showing HOW score was calculated
- **Proposed Display:**
  ```
  Confluence Score: 3/5
  ─────────────────────────
  ✓ Has Flow Alert            +1
  ✓ Volume Surge >1.5x        +1
  ✗ Earnings Catalyst 1-30d    0
  ✗ Strong News Sentiment      0
  ✓ High OI Conviction >30%   +1
  ```
- **Implementation:** Could be inline display or sub-menu (press key to toggle)
- **Benefit:** Gives context for WHY symbol is ranked where it is

---

### OI TIMING ANALYSIS Screen

**Purpose:** View interesting strikes from temporal perspective, understand smart money timing

**Issue 1: Wrong Sort Order**
- **Current:** Sorted by `open_interest DESC` (size-first approach)
- **Problem:** Doesn't support temporal analysis goal
- **Proposed Sort Options:**
  - **Option A:** `oi_build_start_date ASC` (oldest builds first) - shows aging positions
  - **Option B:** `expiration_date ASC` (soonest expiry first) - shows time-critical positions
- **User Goal:** "Look at this from a time perspective"

**Feature Request: Contract History Deep Dive (HIGH PRIORITY)**
- **Current:** List view only - no way to drill deeper
- **Proposed:** Press ENTER on contract row → navigate to "Contract History" screen
- **Data to Show:**
  1. **OI History Chart/Table:** Daily open_interest over time (query oi_daily by contract_hash)
  2. **Volume History:** Daily volume pattern to see accumulation/distribution
  3. **IV History:** Implied volatility changes (tracking hedging activity)
  4. **Build Pattern Visualization:**
     - How OI accumulated (gradual vs sudden spike)
     - Visual representation of build phase
  5. **Timing Context:**
     - Price during OI build period
     - Current price vs build start price
     - Price move % since build started
  6. **Key Metrics Summary:**
     - Build start date & price
     - Days since build began
     - Peak OI reached (is it still growing?)
     - OI momentum: Increasing / Stable / Decreasing
     - Predictive vs Chasing classification
- **Implementation Notes:**
  - Query: `SELECT * FROM oi_daily WHERE contract_hash = ? ORDER BY trade_date ASC`
  - Display as scrollable table with date, OI, volume, IV, price columns
  - Consider ASCII charts if feasible (Textual library might support)
- **User Feedback:** "Very interested in hashing this one out"

---

### OI DISTRIBUTION Screen

**Section: OI Breakdown**
- **Status:** ✅ No changes needed
- **Feedback:** "Colors intuitive, bar chart simple and effective"

**Section: Top 5 Calls/Puts - Layout Needs Work**
- **Current:** Pipe-delimited: `$15 (2025-10-18)|$16 (2025-10-18)|$17 (2025-10-25)|...`
- **Problem:** Hard to read, contracts blend together
- **Current Sort:** Correct (exp date → strike price)
- **Proposed Improvements:**
  - Use more vertical space (screen is scrollable)
  - Better visual separation between contracts
  - Consider table format:
    ```
    CALLS                              PUTS
    Strike    Exp         OI      %    Strike    Exp         OI      %
    $15.00    10/18    5,240   8.2%    $14.00    10/18    4,100   6.4%
    $16.00    10/18    4,180   6.5%    $13.00    10/18    3,850   6.0%
    ```
  - Or grouped by expiration with dividers:
    ```
    Expires 10/18/2025:
      Calls: $15 (5,240) | $16 (4,180)
      Puts:  $14 (4,100) | $13 (3,850)

    Expires 10/25/2025:
      Calls: $17 (3,200) | $18 (2,900)
      Puts:  $13 (2,750) | $12 (2,500)
    ```

**Section: Time Distribution - Needs Date Context**
- **Current:** Shows DTE buckets: "0-7 DTE: 25% | 8-21 DTE: 40% | ..."
- **Problem:** User has to mentally map DTE numbers to actual calendar dates
- **Proposed Improvements:**
  - Add actual date ranges: "0-7 DTE (Oct 15-22): 25%"
  - Reference back to strikes: "8-21 DTE includes $15 & $16 Oct 18 strikes"
  - Make time buckets concrete with calendar dates

**Section: Moneyness Distribution**
- **Status:** ✅ No changes needed

**Section: Greek Exposures - Missing Context**
- **Problem:** Numbers shown without interpretation - what's significant?
- **Examples of Current Display:**
  - Net Delta Exposure: +2.5M shares
  - Total Gamma Exposure: 0.80M
  - Max Gamma Strike: $25
  - Net Vega Exposure: +45K

- **What's Missing:**
  - **Total Gamma 0.80M** → Is this high/low/medium pin pressure to max gamma strike?
  - **Max Gamma Strike $25** → How strong is the pressure to pin here? What's the probability?
  - **Net Vega +45K** → What's significant? Is this high sensitivity to IV changes?
  - **Net Delta +2.5M** → What % of daily volume is this? Is directional exposure meaningful?

- **Proposed Solution:** Add helper text/interpretation with each metric
  - Example: "Net Delta: +2.5M shares (equiv to 15% of avg daily volume) - MODERATE BULLISH PRESSURE"
  - Example: "Total Gamma: 0.80M - HIGH pin pressure to max gamma strike $25"
  - Example: "Net Vega: +45K - LOW sensitivity to IV changes"

- **Implementation Considerations:**
  - Need formulas/thresholds for high/medium/low classifications
  - May need additional data (daily volume, float, typical IV ranges)
  - Could be config-driven thresholds

---

### COMPARE STRIKES Screen

**Status:** Appears to be under construction

**User Question:** "What is the purpose of this view?"

**Current Behavior:**
- Sorted by: open_interest DESC
- Shows: 2-4 week CALL options (14-30 DTE)
- Displays: Strike, Exp, DTE, Last Price, Delta, B/E Move, Delta/$, Theta, OI

**Proposed Improvements:**

**Sort Order Issue:**
- **Current:** By OI (highest first)
- **Proposed:**
  - **Primary Group:** By expiration date (soonest → furthest)
  - **Secondary Sort:** By strike (lowest → highest) within each exp
- **Alternative:** Make entire page sortable
  - Toggle between sort modes: OI / Strike / DTE / Delta/$ / Theta
  - Hotkey to cycle sort order

**Selection Feature (if implemented):**
- If user can SELECT specific contracts (checkboxes, space bar)
- Then compare 2-4 selected contracts side-by-side (existing 4-option comparison)
- Full-page sorting becomes less critical (pick what you want manually)

**User Sentiment:** "Eager to see how this fleshes out"

---

### HELP PAGE

**Bug: Content Truncated**
- **Issue:** Help text cuts off, can't scroll down to see full content
- **Evidence:** User provided screenshot showing truncation
- **Expected:** Should be able to scroll through entire help screen
- **Fix:** Enable scrolling in help container
  - Check CSS: Static widget needs `overflow: auto`
  - Or use ScrollableContainer instead of Container
  - Verify height constraints not limiting scrolling

---

**Status:** All enhancement notes captured. Next steps:
1. Prioritize features with Ben
2. Create implementation tasks
3. Update JOURNAL.md as features are completed

---

## 🔧 Implementation Session - 2025-10-08 (Evening)

**Context:** Implemented prioritized enhancements from afternoon feedback session.

### Changes Implemented

**1. Help Page Scrolling Fix** ✅
- **File:** `mv_main.py` line 1088
- **Change:** Container → ScrollableContainer
- **Result:** Help content now scrollable, no truncation

**2. ENTER Visual Cue** ✅
- **File:** `mv_main.py` line 264
- **Change:** Status bar text "Enter: Select" → "Enter: Detail"
- **Result:** Clear indication that ENTER opens symbol detail screen

**3. OI Timing Analysis Sort Order** ✅
- **File:** `tui_data.py` line 194
- **Change:** `ORDER BY open_interest DESC` → `ORDER BY expiration_date ASC, strike ASC`
- **Rationale:** Time-focused analysis - soonest expiry first, then by strike
- **Result:** Contracts now sorted temporally as user requested

**4. Confluence Score Breakdown** ✅
- **File:** `mv_main.py` SymbolDetailScreen class
- **Added:**
  - "C" key binding to toggle breakdown display
  - State tracking: `self.show_confluence_breakdown`
  - Method: `_build_confluence_breakdown()` - calculates and displays 5 scoring factors
  - Method: `action_toggle_confluence()` - toggles display on/off
  - Updated `_build_detail_menu()` to conditionally show breakdown
- **Features:**
  - Shows all 5 factors: Flow Alert, Volume Surge, Earnings Catalyst, News Sentiment, OI Conviction
  - Visual indicators: ✓ (green) for active factors, ✗ (dim) for inactive
  - Displays actual values: e.g., "Volume Surge 2.3x >1.5x"
  - Toggle on/off with C key
- **Result:** Users can now understand WHY a symbol has its confluence score

**5. Compare Strikes Sort Order** ✅
- **File:** `tui_data.py` line 247
- **Change:** `ORDER BY open_interest DESC` → `ORDER BY expiration_date ASC, strike ASC`
- **Rationale:** Group contracts by expiration, then by strike for easier comparison
- **Result:** Strikes now organized logically by time and price

### Technical Details

**Confluence Score Logic:**
```
Factor 1: active_alerts_count > 0          → +1
Factor 2: volume_surge_factor > 1.5        → +1
Factor 3: earnings_days_ahead 1-30         → +1
Factor 4: |news_sentiment_avg| > 0.3       → +1
Factor 5: max(top_call/put_pct) > 30%      → +1
```

**Database Query Impact:**
- Confluence breakdown queries `v_symbol_oi_detail` for OI conviction percentages
- All other factors already available in `v_morning_watchlist`
- Minimal performance impact (only when breakdown toggled on)

### User Instructions

**New Features Available:**
- **Help Page:** Now fully scrollable - use arrow keys to view all content
- **Watchlist:** Status bar shows "Enter: Detail" for clarity
- **OI Timing:** Contracts sorted by expiration date (soonest → furthest)
- **Symbol Detail:** Press **C** to toggle confluence score breakdown
- **Compare Strikes:** Contracts grouped by expiration, then strike

### User Feedback Round 2 - Immediate Fixes

**1. Help Page** ✅ - Working perfectly

**2. ENTER Visual Cue** ✅ - Clarified
- Located in Watchlist status bar (bottom of screen)
- Requires TUI restart to see change
- Text: `↑↓: Navigate | Enter: Detail | R: Refresh | ESC: Back`

**3. OI Timing Sort** ✅ - Perfect

**4. Confluence Breakdown** ✅ - "Fantastic"
- **Future Enhancement Ideas (captured for later):**
  - Drill into each factor for details:
    - Flow Alerts: view individual alert details
    - Volume Surge: show option volume history chart
    - Earnings: show more earnings-related information
    - News: link to news articles and sentiment data
  - Interactive factor exploration
- **Additional Fix:** Made Symbol Detail screen scrollable (breakdown takes screen space)

**5. Compare Strikes Sort** ✅ - Perfect
- **Additional Fixes:**
  - Made screen scrollable (long contract list)
  - Added current underlying price to header
  - Shows price with 5d change color-coded

### Additional Implementation (Round 2)

**Symbol Detail Scrolling** ✅
- **File:** `mv_main.py` line 346
- **Change:** Container → ScrollableContainer
- **Rationale:** Confluence breakdown expands content, needs scrolling
- **Result:** Can now scroll through full detail menu with breakdown visible

**Compare Strikes Enhancements** ✅
- **File:** `mv_main.py` line 870
- **Changes:**
  - Container → ScrollableContainer for long contract lists
  - Added `_build_compare_header()` method to show current price
  - Header displays: Symbol, Current Price, 5d Change% (color-coded)
- **Result:** Full contract list viewable, price context always visible

### User Quote
> "This is so damn good, it's so easy for me to tell you what's missing because it's so clearly laid out, good job dude."

### Next Steps

**Pending Work (from earlier session):**
- Contract History Deep Dive (HIGH PRIORITY) - drill into individual contracts
- Real-time price on Watchlist (use flow_options_scans data)
- Top 5 Calls/Puts layout improvements
- Time Distribution date context
- Greek Exposure interpretation/context

**Future Enhancements (captured today):**
- Interactive confluence factor drill-down (flow alerts, volume history, earnings, news)
- May require new sub-screens or modal views

---

---

## 🔧 Contract History Deep Dive Implementation - 2025-10-08 (Evening)

**Context:** Implemented highest-priority feature from user feedback - ability to drill into individual contracts from OI Timing screen.

### Changes Implemented

**1. Database Layer (`tui_data.py`)** ✅
- **New Method:** `get_contract_history(contract_hash)` (lines 200-244)
- **Query:** Selects 25+ fields from `oi_daily` table for full time-series analysis
- **Returns:** Daily history ordered by trade_date (oldest → newest)
- **Fields Include:**
  - OI metrics: open_interest, oi_change, oi_change_pct, oi_momentum_5d
  - Volume metrics: volume, volume_avg_5d, volume_ratio_5d
  - IV metrics: implied_volatility, iv_change_1d, iv_change_5d, iv_percentile_20day
  - Greeks: delta, gamma, theta, vega
  - Context: underlying_price, days_to_expiration, build_pattern, building_unwinding

**2. New Screen: ContractHistoryScreen (`mv_main.py`)** ✅
- **Location:** Lines 709-933
- **Components:**
  - Contract identification header (symbol, strike, type, expiration)
  - Key metrics summary panel with calculated insights
  - Daily history table (10 columns, scrollable)
  - Status bar with context

**3. Key Metrics Panel** ✅
- **Build Start:** Date and price when OI accumulation began
- **Price Movement:** % change since build started (color-coded)
- **Days Since Build:** Total days of accumulation
- **OI Momentum:** INCREASING (within 5% of peak) / STABLE (within 20%) / DECREASING
- **Build Pattern:** From database (gradual vs spike)
- **Positioning Classification:**
  - 🧠 PREDICTIVE: Price moved <2%, build >7 days (early position)
  - 📈 CHASING: Price moved >5% (late to party)
  - ⚖️ NEUTRAL: Everything else

**4. Daily History Table** ✅
- **Columns:** Date, OI, OI Δ%, Volume, Vol/OI, IV, IV Δ, Price, DTE, Build
- **Color Coding:**
  - OI Change: Green >10%, Red <-10%
  - IV Change: Yellow rising, Green falling
  - Volume/OI ratio: Yellow >1.5x (high activity)
  - Build indicator: 📈 BUILDING (green) / 📉 UNWINDING (red)
- **Scrollable:** Full contract history visible

**5. Navigation Integration** ✅
- **Updated:** `OITimingScreen.on_data_table_row_selected()` (lines 680-698)
- **Trigger:** Press ENTER on any contract row
- **Action:** Navigates to ContractHistoryScreen with contract details
- **Status Bar:** Updated to show "Enter: History" hint

### User Experience

**Navigation Flow:**
1. Watchlist → Symbol Detail → OI Timing Analysis
2. Select contract with arrow keys
3. Press **ENTER** → Contract History screen
4. Scroll through daily history
5. Press **ESC** → back to OI Timing

**What Users See:**
- Full OI accumulation history from first appearance
- Price context: where smart money entered vs current price
- Volume patterns: accumulation vs distribution phases
- IV trends: hedging activity tracking
- Build momentum: is position still growing or unwinding?

### Technical Details

**Database Query:**
```sql
SELECT trade_date, open_interest, oi_change_pct, volume,
       volume_ratio_5d, implied_volatility, iv_change_5d,
       underlying_price, days_to_expiration, building_unwinding,
       build_pattern, oi_build_start_date, oi_build_start_price
FROM oi_daily
WHERE contract_hash = ?
ORDER BY trade_date ASC
```

**Test Results:**
- ✅ Tested with SOFI $23 PUT (2025-10-10 expiry)
- ✅ Retrieved 24 days of history (2025-09-03 → 2025-10-08)
- ✅ All fields populated correctly
- ✅ TUI launches without errors
- ✅ Navigation and scrolling work smoothly

### Success Criteria (All Met)

- ✅ User can drill into any contract from OI Timing screen
- ✅ Historical data displays clearly in scrollable table
- ✅ Shows build pattern (gradual vs spike)
- ✅ Displays momentum indicators (increasing/stable/decreasing)
- ✅ Easy to understand timing context (when smart money entered)

### User Feedback
> "Very interested in hashing this one out" - Feature request fulfilled

---

## 🔧 Major Refactoring - 2025-10-10

**Context:** Refactored monolithic `mv_main.py` (2,553 lines) into organized screen modules for better maintainability.

### Changes Implemented

**1. File Structure Reorganization** ✅
- **Created:** `morning_view/screens/` directory with 12 screen modules
- **Backup:** `mv_main_backup.py` created before refactoring
- **Result:** Same ~2,500 lines of code, but organized into 13 focused files instead of one monolith

**2. Screen Modules Extracted** ✅
All screen classes extracted from `mv_main.py` into separate files:
- `screens/__init__.py` - Central export point for all screen classes (42 lines)
- `screens/main_menu.py` - MainMenuScreen (105 lines)
- `screens/help.py` - HelpScreen (86 lines)
- `screens/search.py` - SearchScreen (92 lines)
- `screens/discovery.py` - DiscoveryScreen (245 lines)
- `screens/my_watchlist.py` - MyWatchlistScreen + ConfirmRemoveDialog (328 lines)
- `screens/symbol_detail.py` - SymbolDetailScreen (253 lines)
- `screens/oi_timing.py` - OITimingScreen (167 lines)
- `screens/contract_history.py` - ContractHistoryScreen (240 lines)
- `screens/oi_distribution.py` - OIDistributionScreen (181 lines)
- `screens/compare_strikes.py` - CompareStrikesScreen (281 lines)
- `screens/ai_council.py` - AICouncilScreen + 4 dialogs + FullSynthesisScreen (502 lines)

**3. Simplified Main Application File** ✅
- **File:** `mv_main.py` reduced from 2,553 lines to 220 lines (91.4% reduction)
- **Contains Only:**
  - Imports (including clean `from morning_view.screens import MainMenuScreen`)
  - `MorningViewsApp` class with full CSS definitions
  - `on_mount()` initialization logic
  - `main()` entry point
- **Removed:** All 16 screen class definitions (moved to screen modules)

**4. Lazy Import Pattern Implementation** ✅
- **Pattern:** All cross-screen navigation uses lazy imports (imports inside action methods)
- **Purpose:** Prevents circular dependency errors between screen modules
- **Example:**
  ```python
  def action_watchlist(self) -> None:
      # LAZY IMPORT - avoids circular imports
      from morning_view.screens.discovery import DiscoveryScreen
      self.app.push_screen(DiscoveryScreen())
  ```
- **Applied To:** All screen files that navigate to other screens

### Testing Results

**Import Tests:** ✅
- All 16 screen classes import successfully
- No circular import errors
- Module structure verified

**Functional Tests:** ✅
- TUI launches successfully
- Main menu renders correctly with market context
- All navigation flows work identically to before refactor
- No errors during screen transitions

**Code Review Results:**
- `discovery.py`: 7/10 - Broad exception handling noted (pre-existing)
- `symbol_detail.py`: 7/10 - Multiple data fetches noted (pre-existing)
- **Important:** No new bugs introduced - all issues were in original code

### Benefits Achieved

✅ **Easier Navigation** - Know exactly which file contains which screen
✅ **Faster Editing** - Work on 100-300 line files instead of 2,500 lines
✅ **Better Organization** - Related code stays together in focused modules
✅ **Clearer Git Diffs** - Changes isolated to specific screen files
✅ **Simpler Testing** - Can test individual screens in isolation
✅ **Future-Proof** - Easy to add new screens without bloating one file

### Technical Details

**Import Strategy:**
- Top-level imports: Textual widgets, data utilities, timezone utils
- Lazy imports: Screen-to-screen navigation (inside action methods)
- Clean exports: All screens available via `from morning_view.screens import *`

**Files Modified:**
- 1 file deleted (original mv_main.py - backed up as mv_main_backup.py)
- 13 files created (1 main app + 12 screen modules)
- 0 files with breaking changes
- 0 functionality lost

**Database Impact:**
- None - refactoring was purely organizational
- All database queries remain unchanged
- TUI data layer (`tui_data.py`) untouched

### User Impact

**Positive:**
- No visible changes to user experience
- TUI behaves identically to before refactor
- All keyboard shortcuts and navigation work the same

**Neutral:**
- Code organization improved for developers
- Future feature additions will be easier
- Git history preserved via backup file

### Future Maintenance

**When Adding New Screens:**
1. Create new file in `screens/` directory
2. Add export to `screens/__init__.py`
3. Use lazy imports for navigation
4. Follow existing screen patterns

**When Modifying Screens:**
1. Edit specific screen file (not mv_main.py)
2. Test screen in isolation
3. Verify navigation still works

**Documentation:**
- `REFACTOR_PLAN.md` archived as completed
- Screen module structure documented in this journal entry

---

## 🤖 AI Council Implementation - 2025-10-10

**Context:** Implemented multi-advisor AI analysis system with provider refactoring and data source improvements.

### Phase 1: Multi-Provider Model Configuration Refactor ✅

**Problem:** Model configurations scattered across config.json, advisor_config.json, and ai_providers.py. Updating deprecated models required 6+ edits.

**Solution:** Single source of truth in config.json

**Changes:**
- Added `available_models` and `pricing` to all provider sections in config.json
- Removed hardcoded MODELS and PRICING dicts from AnthropicProvider, OpenAIProvider, XAIProvider, GeminiProvider
- Providers now read models/pricing from config in `__init__()`
- Updated deprecated models: xAI grok-beta → grok-2-1212, Gemini 1.5 models → Gemini 2.0/2.5 models

**Testing:**
- ✅ All 4 providers tested with live API calls
- ✅ All 4 advisors validated (model mappings + pricing correct)
- ✅ 3 synthesis models validated

**Benefit:** Model deprecation now = change ONE line in config.json

### Phase 2: Advisor Data Source Fixes ✅

**1. Catalyst Hunter Data Sources**
- **Fixed:** Removed OI/flow data access (was incorrectly inheriting from gather_general_data)
- **Added:** news_articles table with full headlines + summaries
- **Now Focused On:** News sentiment, news articles, earnings, sector/industry, market regime ONLY
- **No Access To:** Flow alerts, OI timing/distribution, options contracts

**2. Advanced Detective Option Chain Data**
- **Added:** Available expiration dates query
- **Added:** Option chain summary (strikes per expiration)
- **Added:** Explicit warning in prompt: "Only recommend strikes/dates that exist in data. Never invent expiration dates."
- **Purpose:** Prevent hallucinations (e.g., "Nov 17th calls" when only 11/14 and 11/21 exist)

### Phase 3: Token Limits & Prompt Engineering ✅

**Changes:**
- Cut max_tokens by 1/3 for all advisors:
  - General Analyst: 400 → 270
  - Advanced Detective: 500 → 330
  - Risk Analyst: 450 → 300
  - Catalyst Hunter: 450 → 300

**Prompt Improvements:**
- Added: "You have STRICT token limits. Get to the point immediately. Skip obvious statements."
- Added: "Skip obvious statements like 'trades don't materialize as expected'"
- Reinforced: Plain text only (no markdown ##, **, bullets)
- Reinforced: LEAD with "minimal new information" if re-analyzing without new insights

**Goal:** Force brevity, eliminate markdown, reduce hedging language

### Phase 4: Analysis Persistence (7-Day Cache) ✅

**Implementation:**
- **File:** `morning_view/screens/ai_council.py`
- **on_mount():** Loads cached analyses from advisor_analysis_cache table (< 7 days old)
- **Binding:** Press **C** to clear all analyses (in-memory + database cache)
- **action_clear_analysis():** Deletes cache records for symbol, clears all advisor columns

**User Experience:**
- Analyses persist across screen visits (no more re-running at cost)
- Can clear stale analyses to force fresh analysis without previous context
- Cache automatically expires after 7 days

**Database:**
- Uses existing `advisor_analysis_cache` table
- Queries: `SELECT * WHERE symbol = ? AND advisor_id = ? AND created_at > date('now', '-7 days')`
- Clear: `DELETE WHERE symbol = ?`

### Technical Implementation Details

**Files Modified:**
- `config.json` - Added model mappings + pricing for all providers
- `morning_view/ai_providers.py` - Removed hardcoded configs, read from config
- `morning_view/advisor_config.json` - Cut token limits, strengthened prompts
- `morning_view/advisor_data.py` - Fixed Catalyst Hunter data sources, added option chain to Detective
- `morning_view/ai_council.py` - Added option chain display logic
- `morning_view/screens/ai_council.py` - Added cache loading + Clear button

**Testing Results:**
- ✅ Anthropic (Haiku, Sonnet): Working
- ✅ OpenAI (GPT-4o-mini): Working
- ✅ xAI (Grok-2): Working
- ✅ Google (Gemini 2.0): Working
- ✅ Cache persistence: Analyses load on screen mount
- ✅ Clear function: Removes analyses + deletes cache

### User Feedback (Testing Session)

**Issues Found:**
1. ❌ Catalyst Hunter showing OI data (flow alerts, options) - FIXED
2. ❌ Markdown formatting still appearing (##, **) - ADDRESSED with stronger prompts
3. ❌ Responses truncated due to max_tokens - FIXED (reduced by 1/3, dynamic +20% on re-analysis)
4. ❌ Advanced Detective hallucinated "Nov 17th" expiration - FIXED (added option chain data)
5. ❌ Risk Analyst too wordy with hedging language - ADDRESSED with explicit prompt rules
6. ✅ Analysis doesn't persist on screen revisit - FIXED (7-day cache loading)

**Cost Observations:**
- General Analyst: ~$0.0025 per analysis
- Advanced Detective: ~$0.0114 per analysis
- Risk Analyst: ~$0.0005 per analysis
- Catalyst Hunter: ~$0.0075 per analysis
- Synthesis (Sonnet): ~$0.0118 per synthesis

### Remaining Work (Future Implementation)

**High Priority:**
1. **xAI Live Search Integration** - Enable real-time Twitter/X and web search for Catalyst Hunter
   - Cost: +$0.025 per search
   - Benefit: Real-time sentiment, breaking news, sector narratives
   - Implementation: Modify XAIProvider to support tool calling API

2. **Prompt Engineering Refinement** - Continue testing/iterating on advisor prompts
   - Goal: Eliminate remaining markdown usage
   - Goal: Further reduce verbosity
   - Goal: Improve actionable insight density

3. **Data Source Review** - Weekend project to refine what each advisor sees
   - Map out complete data access requirements per advisor role
   - Consider: Twitter sentiment, Reddit mentions, analyst ratings, sector rotation

4. **Synthesis Database Access** - Give Chief Strategist direct database access for omniscient analysis
   - High context limit (2-3k tokens) designed for comprehensive data ingestion
   - May require architectural changes

**User Quote:**
> "Great job today :-)"

---

**Last Updated:** 2025-10-10 by Claude Code (AI Council Implementation Complete)
**Next Review:** When xAI Live Search implemented or significant user feedback received
