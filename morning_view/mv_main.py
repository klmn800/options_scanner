#!/usr/bin/env python3
"""
Morning Views TUI - Interactive Terminal Dashboard

A Dwarf Fortress-style TUI for browsing Morning Views data.
Navigate through nested screens using keyboard controls.

Usage:
    python morning_view/mv_main.py

Controls:
    Arrow Keys    - Navigate menus/tables
    Enter         - Select item
    ESC           - Go back
    Q             - Quit (from main menu)
    Ctrl+E        - Edit page with Claude (dev tool)
    ?             - Show keyboard shortcuts
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from textual.app import App
from textual.binding import Binding

# Import main menu screen
from morning_view.screens import MainMenuScreen

# Import for auto-creating views if needed
try:
    from morning_view.morning_views import MorningViews
except ImportError:
    MorningViews = None

from morning_view.tui_data import get_data


# ========== Main Application ==========

class MorningViewsApp(App):
    """Morning Views TUI Application"""

    # Disable mouse support (prevents escape codes in terminal)
    # Textual 0.6+ uses capture_mouse (was ENABLE_MOUSE_SUPPORT in older versions)

    CSS = """
    /* ===== Global Theme ===== */
    Screen {
        background: $surface;
    }

    /* ===== Containers ===== */
    #main-container, #watchlist-container, #symbol-container,
    #timing-container, #distribution-container, #compare-container,
    #search-container, #help-container {
        height: 100%;
        padding: 1 2;
    }

    #main-menu, #symbol-detail, #distribution-content, #help-content {
        padding: 1 2;
        border: solid $primary;
        background: $surface-darken-1;
    }

    #market-context-panel {
        width: 45%;
        height: 1fr;
        padding: 1 2;
        border: solid $accent;
        background: $surface-darken-2;
        margin-left: 1;
    }

    #main-menu {
        width: 55%;
        height: 1fr;
    }

    /* ===== Headers & Titles ===== */
    #watchlist-title, #timing-title, #compare-title, #search-title {
        padding: 1 0;
        text-style: bold;
        background: $primary-darken-2;
        color: $text;
        border: solid $accent;
    }

    /* ===== Data Tables ===== */
    DataTable {
        height: 1fr;
        border: solid $primary;
        background: $surface;
    }

    DataTable > .datatable--header {
        background: $boost;
        text-style: bold;
        color: $text;
    }

    DataTable > .datatable--cursor {
        background: $accent;
        color: $text;
    }

    DataTable:focus > .datatable--cursor {
        background: $accent-darken-2;
    }

    /* ===== Input Fields ===== */
    #search-input {
        margin: 1 0;
        border: solid $primary;
    }

    #search-input:focus {
        border: solid $accent;
    }

    /* ===== Static Content ===== */
    Static {
        overflow: auto;
    }

    /* ===== Status Bar ===== */
    .status-bar {
        dock: bottom;
        height: 3;
        background: $boost;
        color: $text;
        padding: 1 2;
        border-top: solid $primary;
    }

    /* ===== Color Classes ===== */
    .bullish {
        color: $success;
        text-style: bold;
    }

    .bearish {
        color: $error;
        text-style: bold;
    }

    .neutral {
        color: $warning;
    }

    .high-conviction {
        color: $success;
        text-style: bold;
    }

    .medium-conviction {
        color: $warning;
    }

    .low-conviction {
        color: $text-muted;
    }

    /* ===== Admin Mode Theme ===== */
    .admin-mode {
        border: solid $error;
    }

    .admin-header {
        background: $error-darken-3;
        color: $warning;
        text-style: bold;
        padding: 1 2;
    }

    .admin-warning {
        background: $warning-darken-2;
        color: $text;
        text-style: bold;
        padding: 1 0;
    }

    #admin-container {
        height: 100%;
        padding: 1 2;
    }

    #admin-menu {
        padding: 1 2;
        border: solid $error;
        background: $surface-darken-1;
    }

    /* ===== Admin Form Styling ===== */
    .form-row {
        height: auto;
        margin: 1 0;
    }

    .form-label {
        width: 12;
        padding: 0 1;
        text-align: right;
    }

    .button-row {
        height: auto;
        margin: 2 0;
    }

    #journal-content Input {
        margin: 0 1;
        border: solid $primary;
    }

    #journal-content Input:focus {
        border: solid $accent;
    }

    #journal-content TextArea {
        height: 10;
        margin: 1 0;
        border: solid $primary;
    }

    #journal-content TextArea:focus {
        border: solid $accent;
    }

    #journal-content RadioSet {
        height: auto;
        margin: 1 0;
    }

    #journal-content Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+e", "edit_with_claude", "Edit Page", show=True),
    ]

    def __init__(self, *args, **kwargs):
        """Initialize app and load config"""
        super().__init__(*args, **kwargs)

        # Load config from morning_view/config.json
        config_path = Path(__file__).parent / 'config.json'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception as e:
            # Fallback to defaults if config load fails
            self.config = {
                'display': {'watchlist_limit': 20},
                'filters': {},
                'confluence_scoring': {}
            }

    def on_mount(self) -> None:
        """Initialize app on mount"""
        try:
            # Always recreate views to ensure they're up to date with current schema
            # This is fast (~100ms) and ensures views always match code changes
            if MorningViews is None:
                self.exit(message="ERROR: Cannot auto-create views - MorningViews import failed.")
                return

            try:
                # Create MorningViews instance - it will drop/recreate views in __init__
                # Use the same config path as the TUI
                config_path = Path(__file__).parent / 'config.json'
                mv = MorningViews(str(config_path))
                # Views are created in __init__, just need to close the connection
                mv.conn.close()

            except Exception as view_error:
                self.exit(message=f"ERROR: Failed to create SQL views: {str(view_error)}")
                return

            # Check if data exists
            data = get_data()
            display_date = data.get_display_date()
            if display_date == "No data":
                self.exit(message="ERROR: No data found in database. Run OID morning scan first.")
                return

            # Start with main menu
            self.push_screen(MainMenuScreen())

        except Exception as e:
            self.exit(message=f"ERROR: Failed to initialize: {str(e)}\n\nTroubleshooting:\n1. Ensure datalake_query.db exists\n2. Check database permissions")
            return

    def action_quit(self) -> None:
        """Quit application"""
        self.exit()

    def action_edit_with_claude(self) -> None:
        """Launch Claude Code dev session for current screen."""
        try:
            # Detect current screen
            current_screen = self.screen
            screen_name = current_screen.__class__.__name__

            # Map screen class to file path
            screen_file_map = {
                "MainMenuScreen": "morning_view/screens/main_menu.py",
                "DiscoveryScreen": "morning_view/screens/discovery.py",
                "MyWatchlistScreen": "morning_view/screens/my_watchlist.py",
                "SymbolDetailScreen": "morning_view/screens/symbol_detail.py",
                "FlowAlertsScreen": "morning_view/screens/flow_alerts.py",
                "EarningsCalendar90DayScreen": "morning_view/screens/earnings_calendar_90day.py",
                "EarningsBrowserScreen": "morning_view/screens/earnings_browser.py",
                "CapitalPlannerScreen": "morning_view/screens/capital_planner.py",
                "SettingsScreen": "morning_view/screens/settings.py",
                "HelpScreen": "morning_view/screens/help.py",
                "AdminMenuScreen": "morning_view/admin_screens/admin_menu.py",
                "PipelineControlScreen": "morning_view/admin_screens/pipeline_control.py",
                "TradingJournalScreen": "morning_view/admin_screens/trading_journal.py",
                "DatabaseSyncScreen": "morning_view/admin_screens/database_sync.py",
                "SymbolMetadataEditorScreen": "morning_view/admin_screens/symbol_metadata_editor.py",
                "ClaudeDevModal": "morning_view/modals/claude_dev_modal.py",
            }

            file_path = screen_file_map.get(screen_name, "morning_view/mv_main.py")

            # Clean up screen name for display
            display_name = screen_name.replace("Screen", "").replace("90Day", " (90-day)")

            # Launch modal
            from morning_view.modals.claude_dev_modal import ClaudeDevModal
            self.push_screen(ClaudeDevModal(display_name, file_path))

        except Exception as e:
            self.notify(f"❌ Failed to launch Claude dev modal: {e}", severity="error")


def main():
    """Entry point for TUI"""
    app = MorningViewsApp()
    app.run()


if __name__ == "__main__":
    main()
