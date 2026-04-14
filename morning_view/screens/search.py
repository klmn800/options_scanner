"""Search Screen - Symbol search functionality"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static, DataTable, Input
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class SearchScreen(Screen):
    """Search for symbols"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("?", "help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Static("[bold cyan]Search Symbol[/bold cyan]", id="search-title"),
            Input(placeholder="Enter symbol (e.g., AAPL)", id="search-input"),
            DataTable(id="search-results", zebra_stripes=True, cursor_type="row"),
            id="search-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Focus input on mount"""
        input_widget = self.query_one("#search-input", Input)
        input_widget.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search submission"""
        search_term = event.value.strip()
        if not search_term:
            return

        # Search database
        data = get_data()
        results = data.search_symbol(search_term)

        # Update results table
        table = self.query_one("#search-results", DataTable)
        table.clear(columns=True)
        table.add_columns("Symbol", "Score", "Bias", "Signal", "Price")

        if not results:
            table.add_row("No results found")
            return

        for row in results:
            symbol = row.get('symbol', 'N/A')
            score = row.get('confluence_score', 0)
            bias = row.get('direction_bias', 'N/A')
            signal = row.get('primary_signal', 'N/A')
            price = row.get('close_price', 0)

            table.add_row(
                symbol,
                str(score),
                bias,
                signal,
                f"${price:.2f}"
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection"""
        table = self.query_one("#search-results", DataTable)
        row_key = event.row_key
        cell = table.get_cell(row_key, "Symbol")
        symbol = str(cell)

        if symbol and symbol != "No results found":
            # Lazy import to avoid circular dependency
            from morning_view.screens.symbol_detail import SymbolDetailScreen
            # Navigate to symbol detail
            self.app.push_screen(SymbolDetailScreen(symbol))

    def action_back(self) -> None:
        """Return to main menu"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())