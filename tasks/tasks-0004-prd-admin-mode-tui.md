# Task List: Admin Mode for Morning Views TUI

**PRD:** `0004-prd-admin-mode-tui.md`
**Status:** In Progress
**Total Estimated Time:** 5-7 hours

---

## Relevant Files

### New Files (To Be Created)
- `morning_view/admin_screens/__init__.py` - Package init for admin screens
- `morning_view/admin_screens/admin_menu.py` - Admin main menu screen with navigation
- `morning_view/admin_screens/pipeline_control.py` - Pipeline selection and launcher
- `morning_view/admin_screens/trading_journal.py` - Trading journal entry form
- `morning_view/admin_data.py` - Data layer for write operations (journal notes, event lookup)

### Files to Modify
- `morning_view/mv_main.py` - Add admin mode CSS theme (red borders, yellow headers)
- `morning_view/screens/main_menu.py` - Add 'X' key binding to enter admin mode

### Files to Reference (Existing Patterns)
- `morning_view/tui_data.py` - Already has `_get_write_connection()` for database writes
- `morning_view/screens/settings.py` - Form pattern with validation and save operations
- `morning_view/screens/main_menu.py` - Menu pattern with keyboard bindings

### Database Tables (Existing)
- `earnings_events` - Store journal notes in `notes`, `tags`, `note_type`, `sentiment` columns

---

## Tasks

- [x] 1.0 Set up Admin Mode Framework & Infrastructure
  - [x] 1.1 Create `morning_view/admin_screens/` directory
  - [x] 1.2 Create `morning_view/admin_screens/__init__.py` (package init with AdminMenuScreen export)
  - [x] 1.3 Create `morning_view/admin_data.py` with full implementation (lookup_earnings_event, append_journal_note)
  - [x] 1.4 Add admin CSS theme to `morning_view/mv_main.py` (`.admin-mode`, `.admin-header`, `.admin-warning` classes with red/yellow colors)
  - [x] 1.5 Add `X` key binding to `morning_view/screens/main_menu.py` to push admin menu screen
  - [x] 1.6 Add lazy import for `AdminMenuScreen` in `main_menu.py` action handler

- [x] 2.0 Create Admin Main Menu Screen
  - [x] 2.1 Create `morning_view/admin_screens/admin_menu.py` with `AdminMenuScreen` class
  - [x] 2.2 Add imports (Textual widgets, containers, bindings)
  - [x] 2.3 Implement `compose()` method with Header, Footer, and menu container
  - [x] 2.4 Build menu text with red warning banner and 4 options (Pipeline Controls, Trading Journal, File Browser placeholder, Database Sync)
  - [x] 2.5 Add BINDINGS for keys 1-4 and ESC
  - [x] 2.6 Implement action handlers: `action_pipeline_control()`, `action_trading_journal()`, `action_exit_admin()`
  - [x] 2.7 Add lazy imports for `PipelineControlScreen` and `TradingJournalScreen`
  - [x] 2.8 Apply admin theme CSS classes to containers
  - [x] 2.9 Test: Press X from main menu → see admin menu with red theme (READY FOR MANUAL TEST)

- [x] 3.0 Build Pipeline Control Screen
  - [x] 3.1 Create `morning_view/admin_screens/pipeline_control.py` with `PipelineControlScreen` class
  - [x] 3.2 Define `PIPELINES` list with 7 pipeline dicts (id, name, category, script, args, description, runtime)
  - [x] 3.3 Implement `launch_pipeline_in_new_window(pipeline: dict) -> bool` function using `subprocess.Popen` with `cmd /c start cmd /k`
  - [x] 3.4 Build pipeline selection menu layout grouped by category (Earnings Intelligence, OID Strategy, Flow Monitor, System)
  - [x] 3.5 Add BINDINGS for keys 1-7 (pipelines) and ESC (back)
  - [x] 3.6 Implement action handlers that call `launch_pipeline_in_new_window()` and show notification
  - [x] 3.7 Add success notification: "Pipeline started in new terminal window"
  - [x] 3.8 Add error notification if pipeline launch fails
  - [x] 3.9 Test: Select pipeline → verify new terminal window opens with pipeline running (READY FOR MANUAL TEST)

- [x] 4.0 Build Trading Journal Screen
  - [x] 4.1 Create `morning_view/admin_screens/trading_journal.py` with `TradingJournalScreen` class
  - [x] 4.2 Implement `lookup_earnings_event(symbol, earnings_date)` in `admin_data.py` (query earnings_events table, return dict or None)
  - [x] 4.3 Implement `append_journal_note(symbol, earnings_date, note_data)` in `admin_data.py` (append with timestamp separator, merge tags, UPDATE or INSERT)
  - [x] 4.4 Build Step 1: Symbol/date lookup form with Input widgets for symbol and date, plus [L]ookup button
  - [x] 4.5 Build Step 2a: Event found view showing existing notes, with [A]ppend and [O]verwrite buttons
  - [x] 4.6 Build Step 2b: Event not found view with warning and [C]reate button
  - [x] 4.7 Build Step 3: Note entry form with radio buttons (Type, Sentiment), Input for tags, TextArea for notes
  - [x] 4.8 Add validation: symbol uppercase 1-5 chars, date format YYYY-MM-DD, tags comma-separated lowercase
  - [x] 4.9 Implement save action that calls `append_journal_note()` with error handling (DB lock → show error, keep form data)
  - [x] 4.10 Add success notification: "Note saved to {symbol} {date}"
  - [x] 4.11 Test with existing earnings event (append mode) (READY FOR MANUAL TEST)
  - [x] 4.12 Test with new earnings event (create mode) (READY FOR MANUAL TEST)

- [ ] 5.0 Integration Testing & Polish (MANUAL TESTING REQUIRED)
  - [ ] 5.1 Test: Admin mode toggle (X enters admin mode from main menu, ESC exits back to main menu)
  - [ ] 5.2 Test: All 7 pipelines launch successfully in new terminal windows
  - [ ] 5.3 Test: Trading journal append to existing event (verify timestamp separator and merged tags in DB)
  - [ ] 5.4 Test: Trading journal create new event (verify stub created in earnings_events table)
  - [ ] 5.5 Test: Error handling (DB lock during journal save → error message shown, form data preserved)
  - [ ] 5.6 Test: Input validation (invalid symbol, invalid date, missing required fields)
  - [ ] 5.7 Verify: Red theme is visible and distinct from normal mode
  - [ ] 5.8 Verify: All keyboard shortcuts work as expected (1-7, X, ESC, L, A, S)
  - [ ] 5.9 Polish: Review UI text, spacing, and alignment
  - [ ] 5.10 Polish: Add helpful hints/descriptions where needed

---

**Status:** ✅ IMPLEMENTATION COMPLETE - Ready for manual testing
**Next Step:** User testing in terminal (python morning_view/mv_main.py)
