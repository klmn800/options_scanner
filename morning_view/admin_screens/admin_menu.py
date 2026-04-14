"""Admin Main Menu Screen - Entry point for admin operations"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding


class AdminMenuScreen(Screen):
    """Admin main menu screen - write access to production database"""

    BINDINGS = [
        Binding("1", "pipeline_control", "Pipeline Controls", show=False),
        Binding("2", "trading_journal", "Trading Journal", show=False),
        Binding("3", "file_browser", "File Browser", show=False),
        Binding("4", "database_sync", "Database Sync", show=False),
        Binding("5", "symbol_metadata", "Symbol Metadata & Archives", show=False),
        Binding("escape", "exit_admin", "Exit Admin Mode"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Static(self._build_menu(), id="admin-menu", classes="admin-mode"),
            id="admin-container"
        )
        yield Footer()

    def _build_menu(self) -> str:
        """Build admin menu text with warning banner"""
        menu_text = f"""
[bold red]ADMIN MODE - PRODUCTION DATABASE[/bold red]
[yellow]⚠️  Write access enabled - datalake.db[/yellow]

{'─' * 60}

   [bold][1][/bold] Pipeline Controls
        Manually trigger data collection pipelines

   [bold][2][/bold] Trading Journal [dim](Proof of Concept)[/dim]
        Add/edit notes for earnings trades

   [bold dim][3][/bold dim] [dim]File Browser[/dim]
        [dim]View/edit config files, logs, exports (Coming soon)[/dim]

   [bold][4][/bold] Database Sync
        Sync production → query database

   [bold][5][/bold] Symbol Metadata & Archives
        Manage archive assignments, migrate data, create archives

{'─' * 60}

[dim]Navigate: Press number keys | ESC: Exit Admin Mode[/dim]
        """
        return menu_text.strip()

    def action_pipeline_control(self) -> None:
        """Show pipeline control screen"""
        # LAZY IMPORT
        from morning_view.admin_screens.pipeline_control import PipelineControlScreen
        self.app.push_screen(PipelineControlScreen())

    def action_trading_journal(self) -> None:
        """Show trading journal screen"""
        # LAZY IMPORT
        from morning_view.admin_screens.trading_journal import TradingJournalScreen
        self.app.push_screen(TradingJournalScreen())

    def action_file_browser(self) -> None:
        """Show file browser screen (future feature)"""
        self.notify("File Browser - Coming in Phase 2", severity="information", timeout=3)

    def action_database_sync(self) -> None:
        """Show database sync screen"""
        # LAZY IMPORT
        from morning_view.admin_screens.database_sync import DatabaseSyncScreen
        self.app.push_screen(DatabaseSyncScreen())

    def action_symbol_metadata(self) -> None:
        """Show symbol metadata editor screen"""
        # LAZY IMPORT
        from morning_view.admin_screens.symbol_metadata_editor import SymbolMetadataEditorScreen
        self.app.push_screen(SymbolMetadataEditorScreen())

    def action_exit_admin(self) -> None:
        """Exit admin mode back to main menu"""
        self.app.pop_screen()
