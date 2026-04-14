"""OI Timing Screen - Smart Money vs Retail positioning"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class OITimingScreen(Screen):
    """OI Timing Analysis - Smart Money vs Retail positioning"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("s", "sort", "Sort"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
        self.timing_data = []
        self.sort_mode = 'oi'  # Default sort by OI

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Static(f"[bold cyan]{self.symbol} - OI Timing (Smart Money vs Retail)[/bold cyan]", id="timing-title"),
            DataTable(id="timing-table", zebra_stripes=True, cursor_type="row"),
            Static("", id="timing-detail"),
            Static("", id="status-bar", classes="status-bar"),
            id="timing-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table when screen is mounted"""
        self._load_timing_data()
        self._update_status_bar()

    def _load_timing_data(self) -> None:
        """Load OI timing data into table"""
        table = self.query_one("#timing-table", DataTable)

        # Clear existing data and columns
        table.clear(columns=True)

        # Add columns
        table.add_columns(
            "#", "Alert", "Strike", "Type", "Exp", "OI", "IV%", "IV‰", "Position", "Built", "@Price", "Days", "Move%"
        )

        # Load data
        data = get_data()
        self.timing_data = data.get_oi_timing(self.symbol, limit=10)

        if not self.timing_data:
            table.add_row("No timing data available")
            return

        # Apply sort mode
        if self.sort_mode == 'oi':
            # Sort by open interest descending (highest first)
            self.timing_data = sorted(self.timing_data, key=lambda x: x.get('open_interest', 0), reverse=True)
        elif self.sort_mode == 'built':
            # Sort by build start date descending (most recent first)
            self.timing_data = sorted(self.timing_data, key=lambda x: x.get('oi_build_start_date', ''), reverse=True)
        elif self.sort_mode == 'expiration':
            # Sort by expiration date ascending (soonest first)
            self.timing_data = sorted(self.timing_data, key=lambda x: x.get('expiration_date', ''))

        # Populate table with color-coded positioning
        for idx, row in enumerate(self.timing_data, 1):
            strike = row.get('strike', 0)
            opt_type = row.get('option_type', 'N/A')
            exp = row.get('expiration_date', 'N/A')
            oi = row.get('open_interest', 0)
            iv = row.get('iv', 0)
            iv_pct = row.get('iv_percentile', None)
            position = row.get('positioning_type', 'N/A')
            built = row.get('oi_build_start_date', 'N/A')
            build_price = row.get('oi_build_start_price', 0)
            days = row.get('oi_build_days_since', 0)
            price_move = row.get('oi_build_price_move_pct', 0)
            has_alert = row.get('has_flow_alert', 0)

            # Alert indicator
            alert_indicator = "[bold cyan]🚨[/bold cyan]" if has_alert else "─"

            # Color code IV percentile
            if iv_pct is not None and iv_pct > 0:
                if iv_pct < 30:
                    iv_pct_str = f"[green]{iv_pct:.0f}[/green]"
                elif iv_pct < 70:
                    iv_pct_str = f"{iv_pct:.0f}"
                else:
                    iv_pct_str = f"[red]{iv_pct:.0f}[/red]"
            else:
                iv_pct_str = "─"

            # Color code positioning
            if 'PREDICTIVE' in position:
                position_display = f"[green]🧠 PREDICTIVE[/green]"
            elif 'CHASING' in position:
                position_display = f"[yellow]📈 CHASING[/yellow]"
            else:
                position_display = position

            # Color code option type
            type_display = f"[green]{opt_type}[/green]" if opt_type == "CALL" else f"[red]{opt_type}[/red]"

            # Color code freshness (days since build)
            if days <= 7:
                days_display = f"[green]{days}[/green]"
            elif days <= 21:
                days_display = f"[yellow]{days}[/yellow]"
            else:
                days_display = f"[dim]{days}[/dim]"

            # Color code price move
            if price_move is not None and price_move != 0:
                if price_move > 0:
                    move_display = f"[green]+{price_move:.1f}%[/green]"
                else:
                    move_display = f"[red]{price_move:.1f}%[/red]"
            else:
                move_display = "N/A"

            table.add_row(
                str(idx),
                alert_indicator,
                f"[bold]${strike:.1f}[/bold]",
                type_display,
                exp,
                f"{oi:,}",
                f"{iv*100:.0f}" if iv else "─",
                iv_pct_str,
                position_display,
                built,
                f"${build_price:.2f}",
                days_display,
                move_display
            )

        # Focus table
        table.focus()

    def _update_status_bar(self) -> None:
        """Update status bar with timing analysis context"""
        try:
            status = self.query_one("#status-bar", Static)

            # Count predictive vs chasing
            predictive_count = sum(1 for row in self.timing_data if 'PREDICTIVE' in row.get('positioning_type', ''))
            chasing_count = sum(1 for row in self.timing_data if 'CHASING' in row.get('positioning_type', ''))
            alert_count = sum(1 for row in self.timing_data if row.get('has_flow_alert', 0))

            # Sort mode display names
            sort_display = {
                'oi': 'OI ↓',
                'built': 'Built ↓',
                'expiration': 'Exp ↑'
            }

            status_text = (
                f"[bold]{self.symbol}[/bold] OI Timing | "
                f"[cyan]🚨 Alerts: {alert_count}[/cyan] | "
                f"[green]Predictive: {predictive_count}[/green] | "
                f"[yellow]Chasing: {chasing_count}[/yellow] | "
                f"Total: {len(self.timing_data)} | "
                f"Sort: [cyan]{sort_display.get(self.sort_mode, 'OI')}[/cyan] | "
                f"[dim]↑↓: Navigate | Enter: History | S: Sort | ESC: Back | ?: Help[/dim]"
            )
            status.update(status_text)
        except NoMatches:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection - drill into contract history"""
        row_index = event.cursor_row
        if 0 <= row_index < len(self.timing_data):
            row = self.timing_data[row_index]
            contract_hash = row.get('contract_hash')
            strike = row.get('strike', 0)
            option_type = row.get('option_type', 'N/A')
            exp = row.get('expiration_date', 'N/A')

            if contract_hash:
                # Lazy import to avoid circular dependency
                from morning_view.screens.contract_history import ContractHistoryScreen
                # Navigate to contract history screen
                self.app.push_screen(ContractHistoryScreen(
                    contract_hash=contract_hash,
                    symbol=self.symbol,
                    strike=strike,
                    option_type=option_type,
                    expiration_date=exp
                ))

    def action_sort(self) -> None:
        """Cycle through sort modes"""
        # Cycle through sort modes
        sort_modes = ['oi', 'built', 'expiration']
        current_idx = sort_modes.index(self.sort_mode)
        next_idx = (current_idx + 1) % len(sort_modes)
        self.sort_mode = sort_modes[next_idx]

        # Reload table with new sort
        self._load_timing_data()
        self._update_status_bar()

        # Show notification with sort mode name
        mode_names = {
            'oi': 'Open Interest (highest first)',
            'built': 'Build Date (newest first)',
            'expiration': 'Expiration (soonest first)'
        }
        self.notify(f"✅ Sorted by: {mode_names[self.sort_mode]}", severity="information", timeout=2)

    def action_back(self) -> None:
        """Return to symbol detail"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

