# Task List: Morning View Watchlist Redesign - Phase 1

**Source PRD**: `tasks/0001-prd-morning-view-watchlist-redesign.md`
**Status**: Parent Tasks Generated - Awaiting Confirmation
**Created**: 2025-10-09

---

## Relevant Files

**Files to be Modified:**

- `morning_view/morning_views.py` - Create `user_watchlist` table and `v_morning_discovery` view with CTE pattern for explicit trigger flags
- `morning_view/tui_data.py` - Add query functions: `get_discovery()`, `get_my_watchlist()`, `add_to_watchlist()`, `remove_from_watchlist()`
- `morning_view/mv_main.py` - Transform `WatchlistScreen` → `DiscoveryScreen`, add new `MyWatchlistScreen` class
- `morning_view/config.json` - May require configuration adjustments (if needed for dual-DB write strategy)

**Files to be Created:**

- None (database schema changes are handled via SQL in `morning_views.py`)

**Database Changes:**

- `user_watchlist` table - Persistent user-curated watchlist storage
- `v_morning_discovery` view - Replaces `v_morning_watchlist` with explicit trigger flags and temporal sorting

---

## Tasks

### 1.0 Database Schema & View Implementation

Create database tables and views for two-tier watchlist system.

- [x] 1.1 Create `user_watchlist` table in `morning_views.py::_ensure_views_exist()`
  - Add table creation SQL with schema: symbol (PK), added_date, added_reason, user_notes, priority, removed_date
  - Add foreign key constraint to symbol_metadata
  - Use `CREATE TABLE IF NOT EXISTS` for idempotent operations

- [x] 1.2 Create indexes on `user_watchlist` table
  - Add index on `removed_date` for fast filtering of active watchlist (WHERE removed_date IS NULL)
  - Execute index creation immediately after table creation

- [x] 1.3 Create `v_morning_discovery` view with CTE pattern
  - Copy existing `v_morning_watchlist` view as starting point
  - Wrap in CTE to calculate trigger flags: `trigger_flow_alert` (active_alert_count > 0), `trigger_earnings_play` (earnings_alert = 1)
  - Add multi-level ORDER BY: new_alert_count DESC, active_alert_count DESC, move_difference_pct DESC, days_since_last_alert ASC
  - Remove LIMIT 20 clause (show all triggered symbols)
  - Add WHERE clause requiring at least one trigger: `WHERE trigger_flow_alert = 1 OR trigger_earnings_play = 1`

- [x] 1.4 Add LEFT JOIN to exclude watchlist symbols from discovery (optional - can defer)
  - Add LEFT JOIN to user_watchlist in CTE
  - Add WHERE clause: `AND user_watchlist.symbol IS NULL` to hide symbols already on watchlist

- [x] 1.5 Test view creation and query performance
  - Run `python morning_view/morning_views.py` to verify views create without errors
  - Query `SELECT * FROM v_morning_discovery LIMIT 50` and verify results make sense
  - Verify query completes in <1 second

---

### 2.0 Data Layer Query Functions

Add query methods to `tui_data.py` for discovery and watchlist operations.

- [x] 2.1 Add `get_discovery()` method to MorningViewsData class
  - Create method: `def get_discovery(self, limit: int = None) -> List[Dict]:`
  - Query `v_morning_discovery` view (view already handles sorting)
  - Apply limit if provided (default: None = show all)
  - Return `_rows_to_dicts()` for consistency with existing methods

- [x] 2.2 Add `get_my_watchlist()` method
  - Create method: `def get_my_watchlist(self) -> List[Dict]:`
  - Query user_watchlist JOIN base tables to get current trigger status
  - Filter: `WHERE user_watchlist.removed_date IS NULL` (active only)
  - Calculate relevance score: `(new_alert_count * 3) + (active_alert_count * 2) + move_difference_pct`
  - ORDER BY relevance score DESC by default
  - Return watchlist with trigger context

- [x] 2.3 Add `add_to_watchlist()` method with dual-DB write strategy
  - Create method: `def add_to_watchlist(self, symbol: str, added_reason: str = None) -> bool:`
  - Open connection to `datalake.db` (NOT query DB) for write operations
  - INSERT INTO user_watchlist with current date, symbol, added_reason
  - Handle duplicate check: UPDATE removed_date = NULL if symbol exists but was removed
  - Return True on success, False on failure
  - Add error handling with logging

- [x] 2.4 Add `remove_from_watchlist()` method
  - Create method: `def remove_from_watchlist(self, symbol: str) -> bool:`
  - Open connection to `datalake.db` for write
  - UPDATE user_watchlist SET removed_date = CURRENT_DATE WHERE symbol = ? AND removed_date IS NULL
  - Soft delete (preserve history)
  - Return True on success, False on failure

- [x] 2.5 Add helper method `is_on_watchlist()`
  - Create method: `def is_on_watchlist(self, symbol: str) -> bool:`
  - Query user_watchlist WHERE symbol = ? AND removed_date IS NULL
  - Return True if exists, False otherwise
  - Useful for showing watchlist status in Symbol Detail

- [x] 2.6 Test all new query functions manually
  - Add test symbols to watchlist via Python console
  - Verify persistence by querying database directly
  - Test remove operation and verify soft delete
  - Verify get_my_watchlist() returns correct trigger context

---

### 3.0 TUI Discovery Screen (formerly Watchlist)

Transform WatchlistScreen into DiscoveryScreen with trigger-based display.

- [x] 3.1 Rename WatchlistScreen class to DiscoveryScreen
  - Rename class definition: `class DiscoveryScreen(Screen):`
  - Update all references in mv_main.py
  - Update screen title: "SYMBOL DISCOVERY" instead of "Today's Watchlist"

- [x] 3.2 Update `_load_watchlist()` method to use `get_discovery()`
  - Rename method to `_load_discovery()` for clarity
  - Replace `data.get_watchlist()` call with `data.get_discovery()`
  - Remove limit parameter (Discovery shows all symbols)
  - Update table column headers to include "Triggers" column

- [x] 3.3 Add trigger badge display in table rows
  - Add "Triggers" column to DataTable
  - Build trigger string: "🚨" if trigger_flow_alert, "📅" if trigger_earnings_play
  - Show both badges if symbol has multiple triggers: "🚨📅"
  - Add fallback ASCII if emojis fail: "[FLOW] [EARN]"

- [x] 3.4 Update display to show temporal context
  - Add "New" column to show new_alert_count
  - Highlight rows with new_alert_count > 0 (use green color)
  - Show days_since_last_alert in "Days" column
  - Data is already sorted by view (new alerts first)

- [x] 3.5 Add logic to hide symbols already on My Watchlist (if view doesn't handle it)
  - If view doesn't LEFT JOIN exclude watchlist symbols, filter in Python:
  - Call `data.is_on_watchlist(symbol)` for each row
  - Skip adding row to table if already on watchlist
  - Add count to status bar: "X symbols (Y hidden on watchlist)"

- [x] 3.6 Update status bar with discovery-specific context
  - Replace "Watchlist" text with "Discovery"
  - Show total symbols found vs. symbols meeting triggers
  - Add hint: "Enter: Detail → W: Add to Watchlist"

- [x] 3.7 Update main menu navigation
  - Change main menu option [1] text: "Symbol Discovery" instead of "Today's Watchlist"
  - Update help text to explain Discovery vs My Watchlist
  - Verify escape key returns to main menu

---

### 4.0 TUI My Watchlist Screen (new persistent screen)

Create new MyWatchlistScreen class for user-curated persistent watchlist.

- [ ] 4.1 Create MyWatchlistScreen class in mv_main.py
  - Copy DiscoveryScreen as template
  - Define bindings: ESC (back), R (refresh), S (sort), X (remove)
  - Initialize with: `self.watchlist_data = []`, `self.sort_mode = 'relevance'`

- [ ] 4.2 Implement `_load_my_watchlist()` method
  - Call `data.get_my_watchlist()`
  - Add DataTable columns: Symbol, Triggers, Price, Added, Days, Notes
  - Populate table with watchlist rows
  - Apply current sort_mode (relevance/date/alphabetical)
  - Focus table for keyboard navigation

- [ ] 4.3 Add 🆕 badge logic for new activity
  - Check `new_alert_count > 0` for each row
  - If true, prepend 🆕 to Triggers column: "🆕 🚨📅"
  - Add parenthetical count: "(2 new alerts today!)" in status or separate column

- [ ] 4.4 Add ⚠️ stale warning logic
  - Check if `days_since_last_alert > 25` OR `active_alert_count = 0`
  - If stale, add ⚠️ emoji and "Stale (X days)" or "Stale (no triggers)" text
  - Use dim color for stale rows

- [ ] 4.5 Implement X key binding for removal
  - Add action: `def action_remove(self) -> None:`
  - Get selected symbol from table cursor position
  - Show confirmation dialog (custom or Textual modal)

- [ ] 4.6 Create Y/N confirmation dialog for removal
  - Option A: Use Textual's built-in confirmation (if available)
  - Option B: Create simple ConfirmRemoveDialog screen class
  - Display: "Remove TSLA from watchlist? [Y/N]"
  - On Y: call `data.remove_from_watchlist(symbol)`, reload table, show notification
  - On N: dismiss dialog, return to watchlist

- [ ] 4.7 Implement S key for sort mode cycling
  - Add action: `def action_toggle_sort(self) -> None:`
  - Cycle `self.sort_mode` through: 'relevance' → 'date_added' → 'alphabetical' → 'relevance'
  - Reload table with new sort
  - Show notification: "Sorted by: Relevance" etc.

- [ ] 4.8 Add MyWatchlistScreen to main menu
  - Update MainMenuScreen bindings: Add Binding("2", "my_watchlist", "My Watchlist")
  - Add action: `def action_my_watchlist(self) -> None:` that pushes MyWatchlistScreen
  - Update main menu text to show [2] My Watchlist
  - Shift existing [2] Search to [3]

---

### 5.0 Symbol Detail Watchlist Integration

Add watchlist add/remove functionality to SymbolDetailScreen.

- [ ] 5.1 Add watchlist status indicator to SymbolDetailScreen header
  - In `_build_detail_menu()`, call `data.is_on_watchlist(self.symbol)`
  - If on watchlist, add line: "★ On My Watchlist | Press W to remove"
  - If not on watchlist, add line: "Press W to add to My Watchlist"

- [ ] 5.2 Add W key binding to SymbolDetailScreen
  - Add to BINDINGS: `Binding("w", "toggle_watchlist", "Add/Remove Watchlist")`
  - Create action: `def action_toggle_watchlist(self) -> None:`
  - Check `data.is_on_watchlist(self.symbol)` to determine add vs remove

- [ ] 5.3 Implement add to watchlist logic
  - If not on watchlist:
    - Get active triggers from current symbol overview data
    - Build added_reason string: "FLOW_ALERT + EARNINGS_PLAY" or similar
    - Call `data.add_to_watchlist(self.symbol, added_reason)`
    - Show notification: "✅ TSLA added to My Watchlist"
    - Refresh detail menu to update status

- [ ] 5.4 Implement remove from watchlist logic (with confirmation)
  - If on watchlist:
    - Show confirmation: "Remove TSLA from watchlist? [Y/N]"
    - On Y: call `data.remove_from_watchlist(self.symbol)`
    - Show notification: "✅ TSLA removed from My Watchlist"
    - Refresh detail menu to update status

- [ ] 5.5 Update status bar to show watchlist status
  - Add watchlist indicator to status bar
  - Example: "TSLA | ★ On Watchlist | 2 Active Triggers | ..."

- [ ] 5.6 Verify all existing sub-views still work
  - Test navigation to OI Timing, OI Distribution, Compare Strikes, AI Council
  - Verify no regressions in existing screens
  - Test ESC key navigation flows correctly

---

### 6.0 Testing, Documentation & Future Notes

Validate functionality and document future enhancements.

- [ ] 6.1 Manual testing: Discovery screen shows all triggered symbols
  - Launch TUI: `python morning_view/mv_main.py`
  - Navigate to Discovery screen (option 1)
  - Verify trigger badges (🚨 📅) display correctly
  - Verify new alerts appear at top
  - Verify temporal sorting makes sense

- [ ] 6.2 Manual testing: Add symbols to My Watchlist
  - From Discovery, ENTER on symbol → press W
  - Verify confirmation prompt appears
  - Add 3-5 symbols to watchlist
  - Navigate to My Watchlist (option 2)
  - Verify symbols appear with correct triggers

- [ ] 6.3 Manual testing: Persistence across TUI restarts
  - Add symbols to watchlist
  - Quit TUI (ESC to main menu, then Q)
  - Relaunch TUI
  - Navigate to My Watchlist
  - Verify symbols still present

- [ ] 6.4 Manual testing: Remove symbols from watchlist
  - In My Watchlist screen, cursor on symbol
  - Press X key
  - Verify confirmation prompt: "Remove TSLA? [Y/N]"
  - Press Y
  - Verify symbol removed from table
  - Verify notification shows success

- [ ] 6.5 Manual testing: Edge cases
  - Test Discovery with no symbols meeting triggers (should show empty message)
  - Test My Watchlist when empty (should show "No symbols on watchlist")
  - Test adding duplicate symbol (should handle gracefully)
  - Test removing symbol not on watchlist (should handle gracefully)
  - Test stale symbol display (find symbol with days_since_last_alert > 25)

- [ ] 6.6 Document materialized trigger table migration path for Phase 2
  - Create markdown doc: `docs/trigger-table-migration.md`
  - Document current CTE approach (Option 1)
  - Document target materialized table approach (Option 3)
  - Outline migration steps for future phase
  - Reference in PRD appendix

- [ ] 6.7 Update project documentation
  - Update main README or docs with new Discovery + My Watchlist screens
  - Document keyboard shortcuts: W (watchlist), X (remove), S (sort)
  - Add screenshots or examples if appropriate
  - Update CLAUDE.md if Morning View section exists

---

## Next Steps

**All sub-tasks have been generated!**

**To begin implementation**, respond with:
```
Please start on task 1.1 and use @ai-dev-tasks/process-task-list.md
```

This will kick off the systematic implementation workflow with checkpoints after each task.

---

## Implementation Notes

**Current Codebase Patterns Identified:**
- View creation: `morning_views.py` in `_ensure_views_exist()` method (lines 78-459)
- Query pattern: `tui_data.py` uses context manager pattern with `_get_connection()` (line 35-39)
- TUI screens: Textual framework with `Screen` classes, bindings, compose/mount lifecycle
- Data formatting: `clean_database_row()` from `tools/decimal_formatter.py` for all database values

**Database Write Strategy Decision:**
- PRD recommends dual-connection approach: read from `datalake_query.db`, write watchlist to `datalake.db`
- Alternative: Create separate `watchlist.db` for user data isolation
- **Decision needed during implementation** - will test lock behavior with dual-connection first

**Key Dependencies:**
- `options_symbol_summary.active_alert_count` (already exists, populated by Flow Monitor)
- `options_symbol_summary.new_alert_count` (already exists, populated by Flow Monitor)
- `options_symbol_summary.days_since_last_alert` (already exists, populated by Flow Monitor)
- `earnings_upcoming.earnings_alert` (exists, may be sparse but usable)
- `earnings_upcoming.move_difference_pct` (exists for sorting)

**Testing Strategy:**
- Manual TUI navigation testing
- Database integrity checks (foreign keys, indexes)
- Persistence testing (close/reopen TUI)
- Edge cases: no triggers, empty watchlist, duplicate adds
