"""Symbol Metadata & Archive Manager - Admin TUI Screen"""

import sys
import subprocess
import logging
from typing import Optional, Dict
from pathlib import Path
import sqlite3

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Static, Input, Select, DataTable
from textual.screen import Screen
from textual.binding import Binding
from textual import events

from morning_view.admin_data import (
    get_symbol_metadata,
    update_symbol_archive,
    get_available_archives,
    get_archive_stats,
    estimate_migration_rows,
    PROJECT_ROOT,
    SECTOR_ARCHIVE_DIR
)

logger = logging.getLogger(__name__)


class SymbolMetadataEditorScreen(Screen):
    """Symbol metadata and archive manager - simple static content approach"""

    BINDINGS = [
        Binding("q", "request_quit", "Quit", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.current_screen = "main_menu"
        self.current_symbol_data: Optional[Dict] = None
        self.migration_estimate: Optional[Dict[str, int]] = None
        self._pending_migration: Optional[Dict] = None
        self._backfill_metadata: bool = False
        self._backfill_prices: bool = False
        self._metadata_missing: bool = False
        self._prices_insufficient: bool = False
        # For input capture
        self.input_mode: Optional[str] = None
        self.input_buffer: str = ""
        # For archive browsing
        self.archive_stats: list = []
        self.selected_archive_index: int = 0
        self.viewing_archive_name: Optional[str] = None  # Track which archive we're viewing

    def compose(self) -> ComposeResult:
        """Create child widgets - single Static like pipeline_control"""
        yield Header()
        with VerticalScroll(id="admin-container"):
            yield Static(self._build_content(), id="admin-content", classes="admin-mode")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize with main menu"""
        self.current_screen = "main_menu"
        self._refresh_display()

    def _build_content(self) -> str:
        """Build current screen content as string"""
        if self.current_screen == "main_menu":
            return self._build_main_menu()
        elif self.current_screen == "edit_lookup":
            return self._build_edit_lookup()
        elif self.current_screen == "edit_form":
            return self._build_edit_form()
        elif self.current_screen == "migration_prompt":
            return self._build_migration_prompt()
        elif self.current_screen == "migrate_input":
            return self._build_migrate_input()
        elif self.current_screen == "migrate_confirm":
            return self._build_migrate_confirm()
        elif self.current_screen == "create_archive":
            return self._build_create_archive()
        elif self.current_screen == "create_success":
            return self._build_create_success()
        elif self.current_screen == "view_stats":
            return self._build_view_stats()
        elif self.current_screen == "archive_detail":
            return self._build_archive_detail()
        else:
            return "[red]Unknown screen[/red]"

    def _refresh_display(self):
        """Update the display with current content"""
        content = self._build_content()
        static = self.query_one("#admin-content", Static)
        static.update(content)

    def _build_main_menu(self) -> str:
        """Build main menu"""
        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[yellow]Manage symbol archive assignments and sector databases[/yellow]",
            "",
            "[bold][1][/bold] Edit Symbol Archive Assignment",
            "    Lookup symbol → change archive_db → save",
            "",
            "[bold][2][/bold] Migrate Symbol Historical Data",
            "    Move past data from one archive to another",
            "",
            "[bold][3][/bold] Create New Sector Archive",
            "    Build new sector database with aligned schema",
            "",
            "[bold][4][/bold] View Archive Statistics",
            "    List all archives with symbol counts",
            "",
            "[dim]1-4=Select function | ESC=Back | Q=Quit[/dim]"
        ]
        return "\n".join(lines)

    def _build_edit_lookup(self) -> str:
        """Build edit symbol lookup form"""
        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[yellow]Edit Symbol Archive Assignment:[/yellow]",
            "",
            f"Symbol: {self.input_buffer}_",
            "",
            "[dim]Type symbol and press ENTER to lookup | ESC=Back[/dim]"
        ]
        return "\n".join(lines)

    def _build_edit_form(self) -> str:
        """Build edit form"""
        if not self.current_symbol_data:
            return "[red]No symbol data loaded[/red]"

        symbol_data = self.current_symbol_data
        current_archive = symbol_data['archive_db'] or "(none)"

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[yellow]Edit Archive Assignment:[/yellow]",
            "",
            f"[bold]Symbol:[/bold] {symbol_data['symbol']}",
            f"[bold]Company:[/bold] {symbol_data['company_name']}",
            f"[bold]Sector:[/bold] {symbol_data['sector']} | {symbol_data['industry']}",
            f"[bold]Current Archive:[/bold] {current_archive}",
            "",
            "[bold]New Archive:[/bold] (type archive name and press ENTER)",
            f"> {self.input_buffer}_",
            "",
            "[dim]Type archive name and press ENTER to save | ESC=Back[/dim]",
            "",
            "[dim]Available archives: " + ", ".join(get_available_archives()) + "[/dim]"
        ]
        return "\n".join(lines)

    def _build_migration_prompt(self) -> str:
        """Build migration prompt after save"""
        if not self._pending_migration:
            return "[red]No migration data[/red]"

        migration = self._pending_migration
        symbol = migration['symbol']
        old_archive = migration['from_archive']
        new_archive = migration['to_archive']

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[green]Archive assignment updated successfully![/green]",
            "",
            f"[bold]Symbol:[/bold] {symbol}",
            f"[bold]Old Archive:[/bold] {old_archive}",
            f"[bold]New Archive:[/bold] {new_archive}",
            ""
        ]

        # Check what data exists in old archive
        if old_archive and old_archive != "(none)":
            old_archive_path = SECTOR_ARCHIVE_DIR / f"{old_archive}.db"
            metadata_count = self._count_rows_in_archive(old_archive_path, symbol, 'symbol_metadata')
            prices_count = self._count_rows_in_archive(old_archive_path, symbol, 'historical_prices')
            option_contracts_count = self._count_rows_in_archive(old_archive_path, symbol, 'option_contracts')

            lines.extend([
                "[bold]Historical data in old archive:[/bold]",
                f"  • symbol_metadata: {metadata_count} rows",
                f"  • historical_prices: {prices_count} rows"
            ])
            if option_contracts_count > 0:
                lines.append(f"  • option_contracts: {option_contracts_count:,} rows")

            lines.extend([
                "",
                "[yellow]Would you like to migrate historical data?[/yellow]",
                "",
                "Future archive operations (Friday nights) will route " + symbol + " to '" + new_archive + "'.",
                "Historical data remains in '" + old_archive + "' until you migrate it.",
                "",
                "[bold]Y[/bold]=Yes, migrate now | [bold]N[/bold]=No, skip | [bold]ESC[/bold]=Back"
            ])
        else:
            lines.extend([
                "[yellow]No historical data to migrate.[/yellow]",
                "",
                "This symbol was not previously assigned to an archive.",
                f"Future archive operations will route {symbol} to '{new_archive}'.",
                "",
                "[dim]ESC=Back to menu[/dim]"
            ])

        return "\n".join(lines)

    def _build_migrate_input(self) -> str:
        """Build migration input form - uses input mode for fields"""
        migration = self._pending_migration or {}

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[yellow]Migrate Symbol Historical Data:[/yellow]",
            ""
        ]

        # Show what's been entered so far
        if self.input_mode == "symbol":
            lines.extend([
                "[bold]Symbol:[/bold] (type and press ENTER)",
                f"> {self.input_buffer}_",
                ""
            ])
            # Show pre-filled destination if set
            if migration.get('to_archive'):
                lines.extend([
                    f"[dim]Destination: {migration['to_archive']} (will prompt for source)[/dim]",
                    ""
                ])
        elif self.input_mode == "from_archive":
            lines.extend([
                f"[bold]Symbol:[/bold] {migration.get('symbol', '')}",
                "[bold]From Archive:[/bold] (auto-filled from symbol metadata - edit if needed)",
                f"> {self.input_buffer}_",
                ""
            ])
            if migration.get('to_archive'):
                lines.extend([
                    f"[dim]To Archive: {migration['to_archive']} (pre-filled)[/dim]",
                    ""
                ])
        elif self.input_mode == "to_archive":
            lines.extend([
                f"[bold]Symbol:[/bold] {migration.get('symbol', '')}",
                f"[bold]From Archive:[/bold] {migration.get('from_archive', '')}",
                "[bold]To Archive:[/bold] (type and press ENTER)",
                f"> {self.input_buffer}_",
                ""
            ])

        lines.extend([
            "[dim]Type value and press ENTER (or Backspace to edit) | ESC=Back[/dim]",
            "",
            "[dim]Available archives: " + ", ".join(get_available_archives()) + "[/dim]"
        ])

        return "\n".join(lines)

    def _build_migrate_confirm(self) -> str:
        """Build migration confirmation screen"""
        if not self.migration_estimate or not self._pending_migration:
            return "[red]No migration data[/red]"

        migration = self._pending_migration
        row_counts = self.migration_estimate
        total_rows = sum(row_counts.values())

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            f"[yellow]Migration:[/yellow] {migration['symbol']} | {migration['from_archive']} → {migration['to_archive']}",
            "",
            "[bold]Data to migrate:[/bold]",
            "",
            f"{'Table':<30} {'Rows':>10}",
            "─" * 42
        ]

        for table_name, count in row_counts.items():
            lines.append(f"{table_name:<30} {count:>10,}")

        lines.extend([
            "─" * 42,
            f"{'TOTAL':<30} {total_rows:>10,}",
            "",
            f"[dim]↑ Data in source archive: '{migration['from_archive']}'[/dim]",
            ""
        ])

        # Check SOURCE archive data quality to determine if backfill needed
        symbol = migration['symbol']
        from_archive = migration['from_archive']
        source_path = SECTOR_ARCHIVE_DIR / f"{from_archive}.db"

        metadata_count = self._count_rows_in_archive(source_path, symbol, 'symbol_metadata')
        self._metadata_missing = metadata_count == 0

        prices_count = self._count_rows_in_archive(source_path, symbol, 'historical_prices')
        self._prices_insufficient = prices_count < 30

        if self._metadata_missing or self._prices_insufficient:
            lines.append("[yellow]⚠️  Data gaps in source archive (backfill recommended):[/yellow]")
            if self._metadata_missing:
                status_icon = "✅" if self._backfill_metadata else "❌"
                lines.extend([
                    f"  • symbol_metadata: 0 rows (missing - will fetch from API)",
                    f"    {status_icon} [B] Metadata backfill: {'ON' if self._backfill_metadata else 'OFF'}"
                ])
            if self._prices_insufficient:
                status_icon = "✅" if self._backfill_prices else "❌"
                lines.extend([
                    f"  • historical_prices: {prices_count} rows (< 30 days - will fetch from 2021)",
                    f"    {status_icon} [P] Price backfill: {'ON' if self._backfill_prices else 'OFF'}"
                ])
            lines.append("")

        lines.extend([
            "[bold green]M[/bold green]=Start Migration | [bold]B[/bold]/[bold]P[/bold]=Toggle Backfill | [bold]ESC[/bold]=Cancel"
        ])

        return "\n".join(lines)

    def _build_create_archive(self) -> str:
        """Build create archive form"""
        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[yellow]Create New Sector Archive:[/yellow]",
            "",
            f"Archive Name: {self.input_buffer}_",
            "",
            "[dim]Rules:[/dim]",
            "[dim]  • Lowercase, underscores only (e.g., crypto, special_situations)[/dim]",
            "[dim]  • Must start with letter[/dim]",
            "[dim]  • Max 50 characters[/dim]",
            "",
            "[dim]Type name and press ENTER to create | ESC=Cancel[/dim]"
        ]
        return "\n".join(lines)

    def _build_create_success(self) -> str:
        """Build create success screen"""
        archive_name = self.input_buffer

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[green]✓ Archive Created Successfully![/green]",
            "",
            f"[bold]Archive:[/bold] {archive_name}.db",
            f"[bold]Location:[/bold] data/sector_archive/{archive_name}.db",
            "[bold]Schema:[/bold] Aligned with datalake.db (all tables cloned)",
            "",
            "[yellow]What Happens Next:[/yellow]",
            "",
            "• Use the Archive Detail page to migrate symbols into this archive",
            "• Friday nights: sector_archive.py automatically routes data by archive_db",
            "• Optimization (optional): Run db_optimize_sectors.py after migration",
            "",
            "[bold green]SPACE[/bold green] = View Archive Details (manage contents)",
            "",
            "[dim]SPACE=Archive Details | ESC=Back to menu[/dim]"
        ]
        return "\n".join(lines)

    def _build_view_stats(self) -> str:
        """Build archive statistics display with selection"""
        self.archive_stats = get_archive_stats()

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            "[yellow]Sector Archive Statistics:[/yellow]",
            "",
            f"{'Archive Name':<30} {'Symbols':>10} {'Size':>12} {'Last Updated':>20}",
            "─" * 75
        ]

        for idx, stat in enumerate(self.archive_stats):
            # Highlight selected row
            prefix = "→ " if idx == self.selected_archive_index else "  "
            style = "[reverse]" if idx == self.selected_archive_index else ""
            end_style = "[/reverse]" if idx == self.selected_archive_index else ""

            lines.append(
                f"{style}{prefix}{stat['archive_name']:<28} {stat['symbol_count']:>10} "
                f"{stat['file_size_human']:>12} {stat['last_modified']:>20}{end_style}"
            )

        lines.extend([
            "─" * 75,
            f"Total Archives: {len(self.archive_stats)}",
            "",
            "[dim]↑/↓=Navigate | ENTER=View Details | R=Refresh | ESC=Back[/dim]"
        ])

        return "\n".join(lines)

    def _build_archive_detail(self) -> str:
        """Build detailed view of selected archive"""
        # Handle two cases: coming from view_stats or create_success
        if self.viewing_archive_name:
            # Coming from create_success - use stored name
            archive_name = self.viewing_archive_name
            archive_path = SECTOR_ARCHIVE_DIR / f"{archive_name}.db"

            # Get stats for display
            all_stats = get_archive_stats()
            archive = next((s for s in all_stats if s['archive_name'] == archive_name), None)
            if not archive:
                return f"[red]Archive '{archive_name}' not found[/red]"
        else:
            # Coming from view_stats - use selected index
            if not self.archive_stats or self.selected_archive_index >= len(self.archive_stats):
                return "[red]No archive selected[/red]"

            archive = self.archive_stats[self.selected_archive_index]
            archive_name = archive['archive_name']
            archive_path = SECTOR_ARCHIVE_DIR / f"{archive_name}.db"

        lines = [
            "[bold red]ADMIN MODE - Symbol Metadata & Archives[/bold red]",
            f"[yellow]Archive Details: {archive_name}[/yellow]",
            "",
            f"[bold]File:[/bold] {archive_path}",
            f"[bold]Size:[/bold] {archive['file_size_human']}",
            f"[bold]Last Modified:[/bold] {archive['last_modified']}",
            f"[bold]Symbol Count:[/bold] {archive['symbol_count']}",
            "",
            "[bold]Symbols in this archive:[/bold]",
            ""
        ]

        # Query archive to get ALL symbols (union of metadata + contract data)
        try:
            conn = sqlite3.connect(str(archive_path))
            cursor = conn.cursor()

            # Get all symbols from both tables (UNION to find orphaned data)
            cursor.execute("""
                SELECT DISTINCT symbol FROM symbol_metadata
                UNION
                SELECT DISTINCT symbol FROM option_contracts
                ORDER BY symbol
            """)

            all_symbols = [row[0] for row in cursor.fetchall()]

            if all_symbols:
                # Build header (100 chars total: -5 company, -5 sector from 110)
                lines.append(f"{'Symbol':<6} {'Company':<35} {'Sector':<15} {'Contracts':>14}  {'Date Range':<23}")
                lines.append("─" * 100)

                for symbol in all_symbols:
                    # Get metadata (may not exist for orphaned contract data)
                    cursor.execute("""
                        SELECT company_name, sector
                        FROM symbol_metadata
                        WHERE symbol = ?
                    """, (symbol,))

                    metadata = cursor.fetchone()
                    if metadata:
                        company, sector = metadata
                        company_truncated = (company[:32] + "...") if len(company) > 35 else company
                        sector_display = sector if sector else "-"
                    else:
                        company_truncated = "(no metadata)"
                        sector_display = "-"

                    # Get option_contracts stats for this symbol
                    cursor.execute("""
                        SELECT COUNT(DISTINCT contract_hash), MIN(trade_date), MAX(trade_date)
                        FROM option_contracts
                        WHERE symbol = ?
                    """, (symbol,))

                    result = cursor.fetchone()
                    contract_count = result[0] if result else 0
                    min_date = result[1] if result and result[1] else ""
                    max_date = result[2] if result and result[2] else ""

                    # Format date range
                    if min_date and max_date:
                        if min_date == max_date:
                            date_range = f"{min_date}"
                        else:
                            date_range = f"{min_date} to {max_date}"
                    else:
                        date_range = "(no data)"

                    # Format contract count with commas
                    count_str = f"{contract_count:,}" if contract_count > 0 else "-"

                    lines.append(
                        f"{symbol:<6} {company_truncated:<35} {sector_display:<15} {count_str:>14}  {date_range:<23}"
                    )

                lines.append("─" * 100)
                lines.append(f"Total: {len(all_symbols)} symbols")
            else:
                lines.append("[yellow]No symbols found in archive[/yellow]")

            conn.close()

        except sqlite3.Error as e:
            lines.append(f"[red]Error reading archive: {e}[/red]")

        lines.extend([
            "",
            f"[bold green]M[/bold green] = Migrate symbol TO '{archive_name}' archive",
            "",
            "[dim]M=Migrate to this archive | ESC=Back[/dim]"
        ])

        return "\n".join(lines)

    # ========================================================================
    # Event Handlers
    # ========================================================================

    def on_key(self, event: events.Key) -> None:
        """Handle all key presses"""
        key = event.key

        # Main menu navigation
        if self.current_screen == "main_menu":
            if key == "1":
                self.current_screen = "edit_lookup"
                self.input_buffer = ""
                self._refresh_display()
            elif key == "2":
                self.current_screen = "migrate_input"
                self.input_buffer = ""
                self.input_mode = "symbol"  # Start with symbol input
                self._pending_migration = {}
                self._refresh_display()
            elif key == "3":
                self.current_screen = "create_archive"
                self.input_buffer = ""
                self._refresh_display()
            elif key == "4":
                self.current_screen = "view_stats"
                self.selected_archive_index = 0  # Reset selection when entering
                self._refresh_display()

        # Edit lookup screen
        elif self.current_screen == "edit_lookup":
            if key == "enter":
                self.run_worker(self._do_edit_lookup())
            elif key in ("backspace", "delete"):
                self.input_buffer = self.input_buffer[:-1]
                self._refresh_display()
            elif len(key) == 1 and key.isprintable():
                self.input_buffer += key.upper()
                self._refresh_display()

        # Edit form screen
        elif self.current_screen == "edit_form":
            if key == "enter":
                self.run_worker(self._do_edit_save())
            elif key in ("backspace", "delete"):
                self.input_buffer = self.input_buffer[:-1]
                self._refresh_display()
            elif len(key) == 1 and key.isprintable():
                self.input_buffer += key.lower()
                self._refresh_display()

        # Migration input (multi-step form)
        elif self.current_screen == "migrate_input":
            if key == "enter":
                self.run_worker(self._do_migrate_input_step())
            elif key in ("backspace", "delete"):
                self.input_buffer = self.input_buffer[:-1]
                self._refresh_display()
            elif len(key) == 1 and key.isprintable():
                # Symbol input is uppercase, archive names are lowercase
                if self.input_mode == "symbol":
                    self.input_buffer += key.upper()
                else:
                    self.input_buffer += key.lower()
                self._refresh_display()

        # Migration prompt
        elif self.current_screen == "migration_prompt":
            if key == "y":
                # Proceed to migration confirmation screen
                self.run_worker(self._prepare_migration_confirm())
            elif key == "n":
                self.current_screen = "main_menu"
                self._refresh_display()

        # Migration confirmation
        elif self.current_screen == "migrate_confirm":
            if key == "m":
                self._launch_migration()
            elif key == "b" and self._metadata_missing:
                self._backfill_metadata = not self._backfill_metadata
                self._refresh_display()
            elif key == "p" and self._prices_insufficient:
                self._backfill_prices = not self._backfill_prices
                self._refresh_display()

        # Create archive
        elif self.current_screen == "create_archive":
            if key == "enter":
                self.run_worker(self._do_create_archive())
            elif key in ("backspace", "delete"):
                self.input_buffer = self.input_buffer[:-1]
                self._refresh_display()
            elif len(key) == 1 and key.isprintable():
                self.input_buffer += key.lower()
                self._refresh_display()

        # Create success
        elif self.current_screen == "create_success":
            if key == "space":
                # Go to archive detail for the newly created archive
                archive_name = self.input_buffer.strip()
                self.viewing_archive_name = archive_name
                self.current_screen = "archive_detail"
                self._refresh_display()

        # View stats
        elif self.current_screen == "view_stats":
            if key == "r":
                self._refresh_display()
            elif key == "up":
                if self.selected_archive_index > 0:
                    self.selected_archive_index -= 1
                    self._refresh_display()
            elif key == "down":
                if self.selected_archive_index < len(self.archive_stats) - 1:
                    self.selected_archive_index += 1
                    self._refresh_display()
            elif key == "enter":
                self.viewing_archive_name = None  # Clear - we're using selected_archive_index
                self.current_screen = "archive_detail"
                self._refresh_display()

        # Archive detail
        elif self.current_screen == "archive_detail":
            if key == "m":
                # Start migration workflow with to-archive pre-filled
                # Get current archive name
                if self.viewing_archive_name:
                    archive_name = self.viewing_archive_name
                else:
                    archive_name = self.archive_stats[self.selected_archive_index]['archive_name']

                # Start migrate workflow with to-archive pre-set
                self.current_screen = "migrate_input"
                self.input_buffer = ""
                self.input_mode = "symbol"
                self._pending_migration = {'to_archive': archive_name}  # Pre-fill destination
                self._refresh_display()

    def action_back(self) -> None:
        """Go back to previous screen or exit"""
        if self.current_screen == "main_menu":
            self.app.pop_screen()
        elif self.current_screen == "archive_detail":
            # Check if we came from create_success (viewing_archive_name set) or view_stats
            if self.viewing_archive_name:
                # Came from create_success - go to main menu
                self.viewing_archive_name = None
                self.current_screen = "main_menu"
            else:
                # Came from view_stats - go back there
                self.current_screen = "view_stats"
            self._refresh_display()
        else:
            self.current_screen = "main_menu"
            self.input_buffer = ""
            self._refresh_display()

    # ========================================================================
    # Action Methods
    # ========================================================================

    async def _do_edit_lookup(self) -> None:
        """Execute symbol lookup"""
        try:
            symbol = self.input_buffer.strip()
            if not symbol:
                self.notify("Symbol required", severity="error")
                return

            metadata = get_symbol_metadata(symbol)
            if metadata:
                self.current_symbol_data = metadata
                self.current_screen = "edit_form"
                self.input_buffer = ""
                self._refresh_display()
            else:
                self.notify(f"Symbol '{symbol}' not found in symbol_metadata", severity="error")

        except Exception as e:
            logger.error(f"Edit lookup error: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    async def _do_edit_save(self) -> None:
        """Save archive assignment change"""
        try:
            new_archive = self.input_buffer.strip()
            if not new_archive:
                self.notify("Archive name required", severity="error")
                return

            symbol = self.current_symbol_data['symbol']
            old_archive = self.current_symbol_data['archive_db']

            if new_archive == old_archive:
                self.notify("No changes made (same archive)", severity="warning")
                return

            # Update database
            success, message = update_symbol_archive(symbol, new_archive)

            if success:
                self.notify(f"✓ {message}", severity="information", timeout=3)

                # Show migration prompt
                self.current_symbol_data['archive_db'] = new_archive
                self._pending_migration = {
                    'symbol': symbol,
                    'from_archive': old_archive,
                    'to_archive': new_archive
                }
                self.current_screen = "migration_prompt"
                self._refresh_display()
            else:
                self.notify(f"Error: {message}", severity="error")

        except Exception as e:
            logger.error(f"Edit save error: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    async def _do_migrate_input_step(self) -> None:
        """Handle multi-step migration input"""
        try:
            value = self.input_buffer.strip()
            if not value:
                self.notify("Value required", severity="error")
                return

            if self.input_mode == "symbol":
                # Validate symbol exists
                metadata = get_symbol_metadata(value)
                if not metadata:
                    self.notify(f"Symbol '{value}' not found in symbol_metadata", severity="error")
                    return

                self._pending_migration['symbol'] = value

                # Auto-populate from_archive with current archive_db if it exists
                current_archive = metadata.get('archive_db')
                if current_archive:
                    self._pending_migration['from_archive'] = current_archive
                    self.input_buffer = current_archive
                else:
                    self.input_buffer = ""

                self.input_mode = "from_archive"
                self._refresh_display()

            elif self.input_mode == "from_archive":
                # Validate archive exists
                available = get_available_archives()
                if value not in available:
                    self.notify(f"Archive '{value}' not found. Available: {', '.join(available)}", severity="error")
                    return

                self._pending_migration['from_archive'] = value

                # Check if to_archive was pre-filled (coming from archive_detail)
                if self._pending_migration.get('to_archive'):
                    # Skip to_archive input step, go directly to confirmation
                    if value == self._pending_migration['to_archive']:
                        self.notify("From and To archives must be different", severity="error")
                        return
                    await self._prepare_migration_confirm()
                else:
                    # Normal flow - ask for to_archive
                    self.input_mode = "to_archive"
                    self.input_buffer = ""
                    self._refresh_display()

            elif self.input_mode == "to_archive":
                # Validate archive exists
                available = get_available_archives()
                if value not in available:
                    self.notify(f"Archive '{value}' not found. Available: {', '.join(available)}", severity="error")
                    return

                if value == self._pending_migration['from_archive']:
                    self.notify("From and To archives must be different", severity="error")
                    return

                self._pending_migration['to_archive'] = value

                # Proceed to confirmation screen
                await self._prepare_migration_confirm()

        except Exception as e:
            logger.error(f"Migration input step error: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    async def _prepare_migration_confirm(self) -> None:
        """Prepare migration confirmation screen with row estimates"""
        try:
            if not self._pending_migration:
                self.notify("No migration data", severity="error")
                return

            migration = self._pending_migration
            symbol = migration['symbol']
            from_archive = migration['from_archive']
            to_archive = migration['to_archive']

            # Get row estimates
            self.migration_estimate = estimate_migration_rows(symbol, from_archive)

            # Reset backfill flags
            self._backfill_metadata = False
            self._backfill_prices = False

            # Show confirmation screen
            self.current_screen = "migrate_confirm"
            self._refresh_display()

        except Exception as e:
            logger.error(f"Prepare migration confirm error: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    async def _do_create_archive(self) -> None:
        """Execute archive creation"""
        try:
            archive_name = self.input_buffer.strip()
            if not archive_name:
                self.notify("Archive name required", severity="error")
                return

            script_path = PROJECT_ROOT / 'data' / 'health' / 'create_sector_archive.py'
            result = subprocess.run(
                [sys.executable, str(script_path), '--name', archive_name],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30
            )

            if result.returncode == 0:
                self.notify(f"✓ Archive created: {archive_name}.db", severity="information", timeout=5)
                self.current_screen = "create_success"
                self._refresh_display()
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                self.notify(f"Creation failed: {error_msg}", severity="error")

        except subprocess.TimeoutExpired:
            self.notify("Timeout creating archive (took >30s)", severity="error")
        except Exception as e:
            logger.error(f"Create archive error: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    def _launch_migration(self) -> None:
        """Launch migration script in external terminal"""
        try:
            migration = self._pending_migration

            script_path = PROJECT_ROOT / 'data' / 'health' / 'migrate_symbol_archive.py'
            cmd = [
                sys.executable,
                str(script_path),
                '--symbol', migration['symbol'],
                '--from', migration['from_archive'],
                '--to', migration['to_archive']
            ]

            if self._backfill_metadata:
                cmd.append('--backfill-metadata')
            if self._backfill_prices:
                cmd.append('--backfill-prices')

            # Launch in external window
            cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in cmd)
            subprocess.Popen(f'start cmd /k {cmd_str}', shell=True)

            # Build notification
            backfill_msg = ""
            if self._backfill_metadata or self._backfill_prices:
                parts = []
                if self._backfill_metadata:
                    parts.append("metadata")
                if self._backfill_prices:
                    parts.append("prices")
                backfill_msg = f" (with {' + '.join(parts)} backfill)"

            self.notify(
                f"Migration started in external terminal: {migration['symbol']} "
                f"({migration['from_archive']} → {migration['to_archive']}){backfill_msg}",
                severity="information",
                timeout=10
            )

            self.current_screen = "main_menu"
            self._refresh_display()

        except Exception as e:
            logger.error(f"Migration launch error: {e}")
            self.notify(f"Error launching migration: {str(e)}", severity="error", timeout=5)

    def _count_rows_in_archive(self, archive_path: Path, symbol: str, table_name: str) -> int:
        """Count rows for symbol in specific table within an archive"""
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
