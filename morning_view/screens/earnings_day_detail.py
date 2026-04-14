"""Earnings Day Detail Screen - DataTable showing all earnings for a specific day"""

from typing import List, Dict
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding


class EarningsDayDetailScreen(Screen):
    """Day detail view - shows all earnings for selected date in DataTable"""

    BINDINGS = [
        Binding("escape", "back", "Back to Calendar"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, date: str, earnings_list: List[Dict]):
        super().__init__()
        self.date = date
        self.earnings_list = earnings_list

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Vertical(
            Static(self._build_header(), id="day-header"),
            DataTable(id="earnings-table"),
            id="day-detail-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Setup DataTable on mount"""
        table = self.query_one("#earnings-table", DataTable)

        # Add columns
        table.add_column("Symbol", width=12)
        table.add_column("Signal", width=15)
        table.add_column("Time", width=10)
        table.add_column("Exp Move %", width=12)
        table.add_column("Hist Move %", width=12)
        table.add_column("Diff", width=10)
        table.add_column("Sector", width=25)

        # Add rows
        for earnings in self.earnings_list:
            symbol = earnings.get('symbol', 'N/A')
            signal = earnings.get('earnings_play_signal', 'UNKNOWN')
            time = earnings.get('earnings_time', 'Unknown')
            exp_move = earnings.get('straddle_expected_move_pct')
            hist_move = earnings.get('historical_avg_move_pct')
            move_diff = earnings.get('move_difference_pct')
            sector = earnings.get('sector', 'N/A')

            # Format values
            exp_move_str = f"{exp_move:.1f}%" if exp_move else "N/A"
            hist_move_str = f"{hist_move:.1f}%" if hist_move else "N/A"
            move_diff_str = f"{move_diff:+.1f}%" if move_diff else "N/A"

            # Color-code signal
            if signal == 'STRONG BUY':
                signal_display = f"[bold green]{signal}[/bold green]"
            elif signal == 'BUY':
                signal_display = f"[green]{signal}[/green]"
            elif signal == 'WATCH':
                signal_display = f"[yellow]{signal}[/yellow]"
            elif signal == 'AVOID':
                signal_display = f"[dim]{signal}[/dim]"
            else:
                signal_display = signal

            table.add_row(
                symbol,
                signal_display,
                time,
                exp_move_str,
                hist_move_str,
                move_diff_str,
                sector,
                key=symbol  # Use symbol as row key for selection
            )

        # Enable cursor
        table.cursor_type = "row"

    def _build_header(self) -> str:
        """Build header with date and count"""
        try:
            dt = datetime.strptime(self.date, '%Y-%m-%d')
            date_display = dt.strftime('%A, %B %d, %Y')
        except:
            date_display = self.date

        count = len(self.earnings_list)

        # Count by signal
        strong_buy = sum(1 for e in self.earnings_list if e.get('earnings_play_signal') == 'STRONG BUY')
        buy = sum(1 for e in self.earnings_list if e.get('earnings_play_signal') == 'BUY')
        watch = sum(1 for e in self.earnings_list if e.get('earnings_play_signal') == 'WATCH')

        header = f"\n[bold cyan]Earnings for {date_display}[/bold cyan]\n"
        header += f"[dim]{count} tradeable earnings"

        if strong_buy > 0 or buy > 0 or watch > 0:
            signals = []
            if strong_buy > 0:
                signals.append(f"[bold green]{strong_buy} STRONG BUY[/bold green]")
            if buy > 0:
                signals.append(f"[green]{buy} BUY[/green]")
            if watch > 0:
                signals.append(f"[yellow]{watch} WATCH[/yellow]")
            header += f" - {', '.join(signals)}"

        header += "[/dim]\n"
        return header

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection - launch Symbol Detail screen"""
        symbol = event.row_key.value if event.row_key else None

        if symbol:
            # Lazy import to avoid circular dependency
            from morning_view.screens.symbol_detail import SymbolDetailScreen
            self.app.push_screen(SymbolDetailScreen(symbol))

    def action_back(self) -> None:
        """Return to calendar"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help"""
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())
