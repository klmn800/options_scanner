"""Symbol Metadata & Archive Manager - Admin TUI Screen"""

import sys
import subprocess
import logging
from typing import Optional, Dict, List

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Static, Input, Button, Select, DataTable
from textual.screen import Screen
from textual.binding import Binding

from morning_view.admin_data import (
    get_symbol_metadata,
    update_symbol_archive,
    get_available_archives,
    get_archive_stats,
    estimate_migration_rows,
    PROJECT_ROOT,
    SECTOR_ARCHIVE_DIR
)

import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class SymbolMetadataEditorScreen(Screen):
    """Symbol metadata and archive manager - edit assignments, migrate data, create archives"""

    BINDINGS = [
        Binding("q", "request_quit", "Quit", show=True),
        Binding("escape", "back", "Back", show=True),
        Binding("1", "edit_symbol", "Edit Symbol", show=True),
        Binding("2", "migrate_data", "Migrate Data", show=True),
        Binding("3", "create_archive", "Create Archive", show=True),
        Binding("4", "view_stats", "View Stats", show=True),
        Binding("l", "lookup", "Lookup", show=False),
        Binding("s", "save", "Save", show=False),
        Binding("e", "estimate", "Estimate", show=False),
        Binding("m", "execute_migration", "Start Migration", show=False),
        Binding("c", "create", "Create", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("b", "toggle_backfill_metadata", "Toggle Metadata", show=False),
        Binding("p", "toggle_backfill_prices", "Toggle Prices", show=False),
        Binding("y", "migrate_yes", "Yes - Migrate", show=False),
        Binding("n", "migrate_no", "No - Skip", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.current_symbol_data: Optional[Dict] = None
        self.migration_estimate: Optional[Dict[str, int]] = None
        self._migration_confirmed: bool = False
        self._backfill_metadata: bool = False
        self._backfill_prices: bool = False
        self._metadata_missing: bool = False
        self._prices_insufficient: bool = False
        self._screen_stack: List[str] = []  # Track navigation history

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        with VerticalScroll(id="admin-container"):
            with Container(id="metadata-main", classes="admin-mode"):
                yield Static("[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]", classes="admin-header")
                yield Container(id="metadata-content")
                yield Static("", id="status-bar", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize with main menu"""
        self._screen_stack = []  # Reset navigation history
        self._show_main_menu()

    def _update_status(self, message: str, success: Optional[bool] = None) -> None:
        """Update status bar with message"""
        status = self.query_one("#status-bar", Static)
        if success is True:
            status.update(f"[green]✓ {message}[/green]")
        elif success is False:
            status.update(f"[red]✗ {message}[/red]")
        else:
            status.update(message)

    def _show_main_menu(self) -> None:
        """Show main menu with 4 options"""
        # Reset migration state and navigation
        self._migration_confirmed = False
        self._screen_stack = []  # Clear stack when returning to main menu

        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        menu_text = """[yellow]Manage symbol archive assignments and sector databases[/yellow]

[bold][1][/bold] Edit Symbol Archive Assignment
    Lookup symbol → change archive_db → save

[bold][2][/bold] Migrate Symbol Historical Data
    Move past data from one archive to another

[bold][3][/bold] Create New Sector Archive
    Build new sector database with aligned schema

[bold][4][/bold] View Archive Statistics
    List all archives with symbol counts
        """

        container.mount(Static(menu_text.strip()))
        self._update_status("[dim]1-4=Select function | ESC=Back | Q=Quit[/dim]")

    # ========================================================================
    # Function 1: Edit Symbol Archive Assignment
    # ========================================================================

    def action_edit_symbol(self) -> None:
        """Show edit symbol flow"""
        self._screen_stack = ["main_menu"]  # Mark that we're in a sub-screen
        self._show_edit_lookup_form()

    def _show_edit_lookup_form(self) -> None:
        """Step 1: Symbol lookup form"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        row1 = Horizontal(classes="form-row")

        container.mount(
            Static("[yellow]Edit Symbol Archive Assignment:[/yellow]\n"),
            row1
        )

        row1.mount(
            Static("Symbol: ", classes="form-label"),
            Input(placeholder="NVDA", id="edit-symbol-input")
        )

        self._update_status("[dim]L=Lookup | ESC=Back[/dim]")

    async def _do_edit_lookup(self) -> None:
        """Execute symbol lookup"""
        try:
            symbol_input = self.query_one("#edit-symbol-input", Input)

            symbol = symbol_input.value.upper().strip()

            if not symbol:
                self._update_status("Error: Symbol required", success=False)
                return

            self._update_status("Looking up symbol...")

            # Lookup metadata
            metadata = get_symbol_metadata(symbol)

            if metadata:
                self.current_symbol_data = metadata
                self._show_edit_form()
            else:
                self._update_status(f"Symbol '{symbol}' not found in symbol_metadata", success=False)

        except Exception as e:
            logger.error(f"Edit lookup error: {e}")
            self._update_status(f"Error: {str(e)}", success=False)

    def _show_edit_form(self) -> None:
        """Step 2: Edit form with dropdown"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        symbol_data = self.current_symbol_data
        current_archive = symbol_data['archive_db'] or "(none)"

        # Get available archives for dropdown
        archives = get_available_archives()
        # Format as tuples for Select widget: (display_text, value)
        archive_options = [(name, name) for name in archives]

        info_text = f"""[bold]Symbol:[/bold] {symbol_data['symbol']}
[bold]Company:[/bold] {symbol_data['company_name']}
[bold]Sector:[/bold] {symbol_data['sector']} | {symbol_data['industry']}
[bold]Current Archive:[/bold] {current_archive}
"""

        row1 = Horizontal(classes="form-row")

        container.mount(
            Static("[yellow]Edit Archive Assignment:[/yellow]\n"),
            Static(info_text),
            Static("\n[bold]Change to:[/bold]"),
            row1
        )

        # Mount Select dropdown
        archive_select = Select(archive_options, id="archive-select", allow_blank=False)
        # Set current value if it exists in options
        if symbol_data['archive_db'] and symbol_data['archive_db'] in archives:
            archive_select.value = symbol_data['archive_db']

        row1.mount(archive_select)

        self._update_status("[dim]S=Save | ESC=Cancel[/dim]")

    async def _do_edit_save(self) -> None:
        """Save archive assignment change"""
        try:
            archive_select = self.query_one("#archive-select", Select)

            new_archive = archive_select.value

            if not new_archive:
                self._update_status("Please select an archive", success=False)
                return

            symbol = self.current_symbol_data['symbol']
            old_archive = self.current_symbol_data['archive_db']

            if new_archive == old_archive:
                self._update_status("No changes made (same archive)")
                return

            self._update_status("Saving...")

            # Update database
            success, message = update_symbol_archive(symbol, new_archive)

            if success:
                self._update_status(message, success=True)
                self.notify(f"✓ {message}", severity="information", timeout=3)

                # Prompt for migration
                self.current_symbol_data['archive_db'] = new_archive  # Update cache
                self._show_migration_prompt(symbol, old_archive, new_archive)
            else:
                self._update_status(f"Error: {message}", success=False)

        except Exception as e:
            logger.error(f"Edit save error: {e}")
            self._update_status(f"Error: {str(e)}", success=False)

    def _show_migration_prompt(self, symbol: str, old_archive: str, new_archive: str) -> None:
        """Prompt user to migrate historical data"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        # If old archive is None, no data to migrate - just show success message
        if old_archive is None or old_archive == "(none)":
            prompt_text = f"""[green]Archive assignment updated successfully![/green]

[bold]Symbol:[/bold] {symbol}
[bold]Old Archive:[/bold] (none)
[bold]New Archive:[/bold] {new_archive}

[yellow]No historical data to migrate.[/yellow]

This symbol was not previously assigned to an archive.
Future archive operations (Friday nights) will route {symbol} to '{new_archive}'.

[dim]Press ESC to return to menu[/dim]
"""
            container.mount(Static(prompt_text))
            return

        prompt_text = f"""[green]Archive assignment updated successfully![/green]

[bold]Symbol:[/bold] {symbol}
[bold]Old Archive:[/bold] {old_archive}
[bold]New Archive:[/bold] {new_archive}

[yellow]Would you like to migrate historical data?[/yellow]

Future archive operations (Friday nights) will route {symbol} to '{new_archive}'.
Historical data remains in '{old_archive}' until you migrate it.
"""

        buttons = Horizontal(classes="button-row")

        container.mount(
            Static(prompt_text),
            buttons
        )

        buttons.mount(
            Button("Yes - Migrate Data", id="migration-yes-button", variant="primary"),
            Button("No - Keep Historical Data Where It Is", id="migration-no-button")
        )

        # Store migration parameters for later use
        self._pending_migration = {
            'symbol': symbol,
            'from_archive': old_archive,
            'to_archive': new_archive
        }

    # ========================================================================
    # Function 2: Migrate Symbol Historical Data
    # ========================================================================

    def action_migrate_data(self) -> None:
        """Show migrate data flow"""
        self._screen_stack = ["main_menu"]  # Mark that we're in a sub-screen
        self._show_migrate_input_form()

    def _show_migrate_input_form(self) -> None:
        """Step 1: Migration input form"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        # Get available archives
        archives = get_available_archives()
        archive_options = [(name, name) for name in archives]

        row1 = Horizontal(classes="form-row")
        row2 = Horizontal(classes="form-row")
        row3 = Horizontal(classes="form-row")
        buttons = Horizontal(classes="button-row")

        container.mount(
            Static("[yellow]Migrate Symbol Historical Data:[/yellow]\n"),
            row1,
            row2,
            row3,
            buttons,
            Static("", id="migrate-status-message")
        )

        row1.mount(
            Static("Symbol:", classes="form-label"),
            Input(placeholder="NVDA", id="migrate-symbol-input")
        )

        row2.mount(
            Static("From Archive:", classes="form-label"),
            Select(archive_options, id="migrate-from-select", allow_blank=False)
        )

        row3.mount(
            Static("To Archive:", classes="form-label"),
            Select(archive_options, id="migrate-to-select", allow_blank=False)
        )

        buttons.mount(
            Button("Estimate [E]", id="migrate-estimate-button", variant="primary"),
            Button("Cancel [ESC]", id="migrate-cancel-button")
        )

    async def _do_migrate_estimate(self) -> None:
        """Estimate migration row counts"""
        try:
            symbol_input = self.query_one("#migrate-symbol-input", Input)
            from_select = self.query_one("#migrate-from-select", Select)
            to_select = self.query_one("#migrate-to-select", Select)
            status = self.query_one("#migrate-status-message", Static)

            symbol = symbol_input.value.upper().strip()
            from_archive = from_select.value
            to_archive = to_select.value

            if not symbol:
                status.update("[red]Symbol required[/red]")
                return

            if not from_archive or not to_archive:
                status.update("[red]Both archives required[/red]")
                return

            if from_archive == to_archive:
                status.update("[red]Source and target must be different[/red]")
                return

            status.update("[yellow]Analyzing data...[/yellow]")

            # Reset backfill flags for new migration
            self._backfill_metadata = False
            self._backfill_prices = False

            # Get row count estimation
            row_counts = estimate_migration_rows(symbol, from_archive)

            if not row_counts:
                status.update(f"[red]No data found for {symbol} in {from_archive}[/red]")
                return

            # Store for later use
            self.migration_estimate = row_counts
            self._pending_migration = {
                'symbol': symbol,
                'from_archive': from_archive,
                'to_archive': to_archive
            }

            self._show_migrate_confirmation()

        except Exception as e:
            logger.error(f"Migration estimate error: {e}")
            status = self.query_one("#migrate-status-message", Static)
            status.update(f"[red]Error: {str(e)}[/red]")

    def _show_migrate_confirmation(self) -> None:
        """Step 2: Show estimation and confirm"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        migration = self._pending_migration
        row_counts = self.migration_estimate

        total_rows = sum(row_counts.values())

        # Check for missing data in target archive
        symbol = migration['symbol']
        to_archive = migration['to_archive']
        target_path = SECTOR_ARCHIVE_DIR / f"{to_archive}.db"

        # Check metadata
        metadata_count = self._count_rows_in_archive(target_path, symbol, 'symbol_metadata')
        metadata_missing = metadata_count == 0

        # Check historical prices
        prices_count = self._count_rows_in_archive(target_path, symbol, 'historical_prices')
        prices_insufficient = prices_count < 30

        # Build table display
        table_lines = ["[bold]Data to migrate:[/bold]\n"]
        table_lines.append(f"{'Table':<30} {'Rows':>10}")
        table_lines.append("-" * 42)

        for table_name, count in row_counts.items():
            table_lines.append(f"{table_name:<30} {count:>10,}")

        table_lines.append("-" * 42)
        table_lines.append(f"{'TOTAL':<30} {total_rows:>10,}")

        table_text = "\n".join(table_lines)

        # Build warnings section
        warnings_lines = []
        if metadata_missing or prices_insufficient:
            warnings_lines.append("\n[yellow]⚠️  Data gaps detected in target archive:[/yellow]")
            if metadata_missing:
                warnings_lines.append(f"  • symbol_metadata: 0 rows (missing)")
                warnings_lines.append(f"    [dim]Press B to enable metadata backfill from FMP API[/dim]")
            if prices_insufficient:
                warnings_lines.append(f"  • historical_prices: {prices_count} rows (< 30 days)")
                warnings_lines.append(f"    [dim]Press P to enable price backfill from FMP API[/dim]")
            warnings_lines.append("")

        warnings_text = "\n".join(warnings_lines)

        # Build backfill status display
        backfill_status = []
        if metadata_missing or prices_insufficient:
            backfill_status.append("\n[bold]Backfill:[/bold]")
            if metadata_missing:
                status = "✅ ON" if getattr(self, '_backfill_metadata', False) else "❌ OFF"
                backfill_status.append(f"  [B] Metadata: {status}")
            if prices_insufficient:
                status = "✅ ON" if getattr(self, '_backfill_prices', False) else "❌ OFF"
                backfill_status.append(f"  [P] Prices: {status}")

        backfill_text = "\n".join(backfill_status)

        # Build confirmation display - compact format to fit on screen
        confirm_lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            f"[yellow]Migration:[/yellow] {migration['symbol']} | {migration['from_archive']} → {migration['to_archive']}",
            "",
            table_text,
        ]

        # Only add warnings/backfill if present
        if warnings_text:
            confirm_lines.append(warnings_text)
        if backfill_text:
            confirm_lines.append(backfill_text)

        confirm_lines.extend([
            "",
            "[bold green]▶ Press M to START MIGRATION[/bold green]",
            "[dim]B/P: toggle backfill | ESC: cancel[/dim]" if (metadata_missing or prices_insufficient) else "[dim]ESC: cancel[/dim]"
        ])

        confirm_text = "\n".join(confirm_lines)

        container.mount(Static(confirm_text))

        # Store state for hotkey handler
        self._migration_confirmed = True
        self._metadata_missing = metadata_missing
        self._prices_insufficient = prices_insufficient

    def _execute_migration(self) -> None:
        """Launch migration script in external terminal"""
        try:
            migration = self._pending_migration

            symbol = migration['symbol']
            from_archive = migration['from_archive']
            to_archive = migration['to_archive']

            # Build command
            script_path = PROJECT_ROOT / 'data' / 'health' / 'migrate_symbol_archive.py'
            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', symbol,
                '--from', from_archive,
                '--to', to_archive
            ]

            # Add backfill flags if enabled
            if self._backfill_metadata:
                cmd.append('--backfill-metadata')
            if self._backfill_prices:
                cmd.append('--backfill-prices')

            # Launch in external cmd window (Windows)
            cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in cmd)
            subprocess.Popen(f'start cmd /k {cmd_str}', shell=True)

            # Build notification message
            backfill_msg = ""
            if self._backfill_metadata or self._backfill_prices:
                backfill_parts = []
                if self._backfill_metadata:
                    backfill_parts.append("metadata")
                if self._backfill_prices:
                    backfill_parts.append("prices")
                backfill_msg = f" (with {' + '.join(backfill_parts)} backfill)"

            self.notify(
                f"Migration started in external terminal: {symbol} ({from_archive} → {to_archive}){backfill_msg}",
                severity="information",
                timeout=10
            )

            # Return to main menu
            self._show_main_menu()

        except Exception as e:
            logger.error(f"Migration execute error: {e}")
            self.notify(f"Error launching migration: {str(e)}", severity="error", timeout=5)

    # ========================================================================
    # Function 3: Create New Sector Archive
    # ========================================================================

    def action_create_archive(self) -> None:
        """Show create archive flow"""
        self._screen_stack = ["main_menu"]  # Mark that we're in a sub-screen
        self._show_create_archive_form()

    def _show_create_archive_form(self) -> None:
        """Step 1: Archive name input"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        rules_text = """[dim]Rules:[/dim]
[dim]  • Lowercase, underscores only (e.g., crypto, special_situations)[/dim]
[dim]  • Must start with letter[/dim]
[dim]  • Max 50 characters[/dim]
"""

        row1 = Horizontal(classes="form-row")
        buttons = Horizontal(classes="button-row")

        container.mount(
            Static("[yellow]Create New Sector Archive:[/yellow]\n"),
            row1,
            Static(rules_text),
            buttons,
            Static("", id="create-status-message")
        )

        row1.mount(
            Static("Archive Name:", classes="form-label"),
            Input(placeholder="crypto", id="create-archive-input")
        )

        buttons.mount(
            Button("Create [C]", id="create-archive-button", variant="success"),
            Button("Cancel [ESC]", id="create-cancel-button")
        )

    async def _do_create_archive(self) -> None:
        """Execute archive creation"""
        try:
            archive_input = self.query_one("#create-archive-input", Input)
            status = self.query_one("#create-status-message", Static)

            archive_name = archive_input.value.strip()

            if not archive_name:
                status.update("[red]Archive name required[/red]")
                return

            status.update("[yellow]Creating archive...[/yellow]")

            # Call creation script
            script_path = PROJECT_ROOT / 'data' / 'health' / 'create_sector_archive.py'
            result = subprocess.run(
                [sys.executable, str(script_path), '--name', archive_name],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30000
            )

            if result.returncode == 0:
                self.notify(f"✅ Archive created: {archive_name}.db", severity="information", timeout=5)
                status.update(f"[green]Success! Archive created: data/sector_archive/{archive_name}.db[/green]")
            else:
                # Show error from script
                error_msg = result.stderr if result.stderr else result.stdout
                status.update(f"[red]Creation failed:\n{error_msg}[/red]")

        except subprocess.TimeoutExpired:
            status = self.query_one("#create-status-message", Static)
            status.update("[red]Timeout creating archive (took >30s)[/red]")
        except Exception as e:
            logger.error(f"Create archive error: {e}")
            status = self.query_one("#create-status-message", Static)
            status.update(f"[red]Error: {str(e)}[/red]")

    # ========================================================================
    # Function 4: View Archive Statistics
    # ========================================================================

    def action_view_stats(self) -> None:
        """Show archive statistics"""
        self._screen_stack = ["main_menu"]  # Mark that we're in a sub-screen
        self._show_archive_stats()

    def _show_archive_stats(self) -> None:
        """Display archive statistics table"""
        container = self.query_one("#metadata-content", Container)
        container.remove_children()

        # Get stats
        stats = get_archive_stats()

        # Create DataTable
        table = DataTable(id="stats-table")
        table.add_columns("Archive Name", "Symbols", "Size", "Last Updated")

        for stat in stats:
            table.add_row(
                stat['archive_name'],
                str(stat['symbol_count']),
                stat['file_size_human'],
                stat['last_modified']
            )

        buttons = Horizontal(classes="button-row")

        container.mount(
            Static("[yellow]Sector Archive Statistics:[/yellow]\n"),
            table,
            Static(f"\nTotal Archives: {len(stats)}\n"),
            buttons
        )

        buttons.mount(
            Button("Refresh [R]", id="stats-refresh-button", variant="primary"),
            Button("Back [ESC]", id="stats-back-button")
        )

    # ========================================================================
    # Event Handlers
    # ========================================================================

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle all button presses"""
        button_id = event.button.id

        # Edit Symbol Flow
        if button_id == "edit-lookup-button":
            await self._do_edit_lookup()
        elif button_id == "edit-back-button" or button_id == "edit-cancel-button":
            self._show_main_menu()
        elif button_id == "edit-save-button":
            await self._do_edit_save()

        # Migration Prompt
        elif button_id == "migration-yes-button":
            # Pre-fill migration form with stored values
            migration = self._pending_migration
            self._show_migrate_input_form()
            # Pre-populate fields
            symbol_input = self.query_one("#migrate-symbol-input", Input)
            from_select = self.query_one("#migrate-from-select", Select)
            to_select = self.query_one("#migrate-to-select", Select)
            symbol_input.value = migration['symbol']
            from_select.value = migration['from_archive']
            to_select.value = migration['to_archive']
            # Auto-trigger estimate
            await self._do_migrate_estimate()
        elif button_id == "migration-no-button":
            self._show_main_menu()

        # Migrate Data Flow
        elif button_id == "migrate-estimate-button":
            await self._do_migrate_estimate()
        elif button_id == "migrate-cancel-button" or button_id == "migrate-cancel-confirm-button":
            self._show_main_menu()
        elif button_id == "migrate-execute-button":
            self._execute_migration()

        # Create Archive Flow
        elif button_id == "create-archive-button":
            await self._do_create_archive()
        elif button_id == "create-cancel-button":
            self._show_main_menu()

        # View Stats Flow
        elif button_id == "stats-refresh-button":
            self._show_archive_stats()
        elif button_id == "stats-back-button":
            self._show_main_menu()

    def action_execute_migration_hotkey(self) -> None:
        """Execute migration via M hotkey"""
        if self._migration_confirmed and hasattr(self, '_pending_migration'):
            self._execute_migration()

    def action_toggle_backfill_metadata(self) -> None:
        """Toggle metadata backfill option (B key)"""
        if self._migration_confirmed and self._metadata_missing:
            self._backfill_metadata = not self._backfill_metadata
            self._show_migrate_confirmation()  # Refresh display

    def action_toggle_backfill_prices(self) -> None:
        """Toggle price backfill option (P key)"""
        if self._migration_confirmed and self._prices_insufficient:
            self._backfill_prices = not self._backfill_prices
            self._show_migrate_confirmation()  # Refresh display

    def _count_rows_in_archive(self, archive_path: Path, symbol: str, table_name: str) -> int:
        """
        Count rows for symbol in specific table within an archive.

        Args:
            archive_path: Path to archive database
            symbol: Stock ticker
            table_name: Table to query

        Returns:
            Row count (0 if table doesn't have symbol column or doesn't exist)
        """
        try:
            conn = sqlite3.connect(str(archive_path))
            cursor = conn.cursor()

            # Check if table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if not cursor.fetchone():
                conn.close()
                return 0

            # Check if table has 'symbol' column
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]

            if 'symbol' not in columns:
                conn.close()
                return 0

            # Count rows
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE symbol = ?", (symbol,))
            count = cursor.fetchone()[0]
            conn.close()

            return count

        except sqlite3.Error as e:
            logger.warning(f"Error counting rows in {table_name}: {e}")
            return 0

    def action_estimate_migration(self) -> None:
        """Trigger migration estimate via E hotkey"""
        # Check if we're on the migration input form
        try:
            self.query_one("#migrate-estimate-button")
            self.run_worker(self._do_migrate_estimate())
        except:
            pass  # Not on the right screen

    def action_back(self) -> None:
        """Navigate back to main menu or exit"""
        # If on confirmation screen, go back to input form
        if self._migration_confirmed:
            self._migration_confirmed = False
            self._backfill_metadata = False
            self._backfill_prices = False
            self._show_migrate_input_form()
        # If on any sub-screen, go to main menu
        elif len(self._screen_stack) > 0:
            self._show_main_menu()
        # If on main menu, exit to admin menu
        else:
            self._migration_confirmed = False
            self._backfill_metadata = False
            self._backfill_prices = False
            self._metadata_missing = False
            self._prices_insufficient = False
            self.app.pop_screen()
