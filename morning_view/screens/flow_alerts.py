"""Flow Alerts Screen - Recent options flow activity"""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding


class FlowAlertsScreen(Screen):
    """Flow alerts - recent options flow activity from flow_alerts table"""

    BINDINGS = [
        Binding("escape", "back", "Back to Menu"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "sort", "Sort"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, symbol: str = None):
        """
        Initialize Flow Alerts screen.

        Args:
            symbol: Optional symbol filter (default None = show all symbols)
        """
        super().__init__()
        self.symbol = symbol
        self.sort_mode = 'date'  # Default: date (newest first)

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Vertical(
            Static(self._build_header(), id="alerts-header"),
            DataTable(id="alerts-table"),
            id="alerts-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Setup DataTable on mount"""
        self._load_alerts()

    def _build_header(self) -> str:
        """Build header text"""
        from morning_view.tui_data import get_data
        data = get_data()

        if self.symbol:
            title = f"\n[bold cyan]Flow Alerts - {self.symbol} (Last 2 Weeks)[/bold cyan]\n"
        else:
            title = f"\n[bold cyan]Flow Alerts - Last 2 Weeks[/bold cyan]\n"

        # Sort mode indicator
        sort_names = {
            'date': 'Date (newest first)',
            'symbol': 'Symbol (grouped)',
            'score': 'Score (highest first)'
        }
        sort_display = sort_names.get(self.sort_mode, 'Date')

        return f"{title}[dim]Filtered: <${data.max_underlying_price:.0f} price, {data.min_open_interest}+ OI | Sort: {sort_display}[/dim]\n"

    def _load_alerts(self) -> None:
        """Load alerts from database and populate table"""
        from morning_view.tui_data import get_data

        data = get_data()
        alerts = data.get_flow_alerts(days_back=14, symbol=self.symbol)  # Last 2 weeks, optionally filtered by symbol

        # Apply sort mode
        if self.sort_mode == 'date':
            # Sort by trade_date descending (newest first), then by alert_timestamp descending
            alerts = sorted(alerts, key=lambda x: (x.get('trade_date', ''), x.get('alert_timestamp', '')), reverse=True)
        elif self.sort_mode == 'symbol':
            # Sort by symbol alphabetically, then by date descending
            alerts = sorted(alerts, key=lambda x: (x.get('symbol', ''), x.get('trade_date', '')), reverse=False)
            # Reverse only the date part within each symbol group
            from itertools import groupby
            grouped = []
            for symbol, group in groupby(alerts, key=lambda x: x.get('symbol', '')):
                grouped.extend(sorted(list(group), key=lambda x: x.get('trade_date', ''), reverse=True))
            alerts = grouped
        elif self.sort_mode == 'score':
            # Sort by significance_score descending (highest first)
            alerts = sorted(alerts, key=lambda x: x.get('significance_score', 0), reverse=True)

        table = self.query_one("#alerts-table", DataTable)

        # Clear existing data
        table.clear(columns=True)

        # Add columns
        table.add_column("Date", width=10)
        table.add_column("Symbol", width=8)
        table.add_column("Strike", width=8)
        table.add_column("Exp", width=10)
        table.add_column("Type", width=6)
        table.add_column("Money", width=8)
        table.add_column("UL", width=8)
        table.add_column("Vol", width=8)
        table.add_column("OI", width=8)
        table.add_column("IV", width=6)
        table.add_column("Last", width=8)
        table.add_column("Score", width=6)

        # Add rows
        for idx, alert in enumerate(alerts):
            trade_date = alert.get('trade_date', 'N/A')
            symbol = alert.get('symbol', 'N/A')
            strike = alert.get('strike')
            expiration = alert.get('expiration_date', 'N/A')
            option_type = alert.get('option_type', 'N/A')
            moneyness = alert.get('moneyness', 'N/A')
            underlying_price = alert.get('underlying_price')
            volume = alert.get('volume')
            open_interest = alert.get('open_interest')
            iv = alert.get('iv')
            last_price = alert.get('last_price')
            score = alert.get('significance_score')

            # Format values
            strike_str = f"${strike:.2f}" if strike else "N/A"
            ul_str = f"${underlying_price:.2f}" if underlying_price else "N/A"
            vol_str = f"{volume:,}" if volume else "N/A"
            oi_str = f"{open_interest:,}" if open_interest else "N/A"
            iv_str = f"{iv:.1f}%" if iv else "N/A"
            last_str = f"${last_price:.2f}" if last_price else "N/A"
            score_str = f"{score:.1f}" if score else "N/A"

            # Shorten option type
            type_str = option_type[:1].upper() if option_type else "N/A"  # C or P

            table.add_row(
                trade_date,
                symbol,
                strike_str,
                expiration,
                type_str,
                moneyness,
                ul_str,
                vol_str,
                oi_str,
                iv_str,
                last_str,
                score_str,
                key=str(idx)  # Use index as unique key
            )

        # Enable cursor
        table.cursor_type = "row"

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection - could launch Symbol Detail in future"""
        # For now, do nothing - just a reference table
        pass

    def action_sort(self) -> None:
        """Cycle through sort modes"""
        # Cycle through sort modes
        sort_modes = ['date', 'symbol', 'score']
        current_idx = sort_modes.index(self.sort_mode)
        next_idx = (current_idx + 1) % len(sort_modes)
        self.sort_mode = sort_modes[next_idx]

        # Reload table with new sort
        self._load_alerts()

        # Update header to show new sort mode
        header = self.query_one("#alerts-header", Static)
        header.update(self._build_header())

        # Show notification with sort mode name
        mode_names = {
            'date': 'Date (newest first)',
            'symbol': 'Symbol (grouped)',
            'score': 'Score (highest first)'
        }
        self.notify(f"✅ Sorted by: {mode_names[self.sort_mode]}", severity="information", timeout=2)

    def action_refresh(self) -> None:
        """Refresh alerts data"""
        try:
            self._load_alerts()
            self.notify("✅ Alerts refreshed", severity="information", timeout=2)
        except Exception as e:
            self.notify(f"❌ Refresh failed: {e}", severity="error")

    def action_back(self) -> None:
        """Return to main menu"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help"""
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())
