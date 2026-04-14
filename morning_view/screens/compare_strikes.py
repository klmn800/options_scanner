"""Compare Strikes Screen - Side-by-side strike comparison"""

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class CompareStrikesScreen(Screen):
    """Compare strikes side-by-side for trade selection"""

    BINDINGS = [
        Binding("space", "toggle_select", "Select/Deselect"),
        Binding("c", "clear_basket", "Clear Basket"),
        Binding("v", "view_comparison", "View Selected"),
        Binding("escape", "back", "Back"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
        self.options_data = []
        self.selected_indices = set()  # Track selected rows

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield ScrollableContainer(
            Static(self._build_compare_header(), id="compare-header"),
            DataTable(id="compare-table", zebra_stripes=True, cursor_type="row"),
            Static("", id="status-bar", classes="status-bar"),
            id="compare-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table when screen is mounted"""
        self._load_options()
        self._update_status_bar()

    def _build_compare_header(self) -> str:
        """Build header with symbol and current price"""
        # Get current price from symbol overview
        data = get_data()
        overview = data.get_symbol_overview(self.symbol)

        if overview:
            current_price = overview.get('current_price', overview.get('close_price', 0))  # Use current_price, fallback to close_price
            price_chg = overview.get('price_change_5d_pct', 0)

            # Color-code price change
            if price_chg > 0:
                price_display = f"${current_price:.2f} [green](+{price_chg:.1f}%)[/green]"
            elif price_chg < 0:
                price_display = f"${current_price:.2f} [red]({price_chg:.1f}%)[/red]"
            else:
                price_display = f"${current_price:.2f}"

            header_text = f"[bold cyan]{self.symbol} - Compare Strikes (CALL options)[/bold cyan]\n[dim]Current Price: {price_display} | 5d Change[/dim]"
        else:
            header_text = f"[bold cyan]{self.symbol} - Compare Strikes (CALL options)[/bold cyan]"

        return header_text

    def _load_options(self) -> None:
        """Load options data into table"""
        table = self.query_one("#compare-table", DataTable)

        # Add columns with selection indicator
        table.add_columns(
            "✓", "Strike", "Exp", "DTE", "Last", "Delta", "IV%", "IV‰ (20d)", "B/E Move", "Delta/$", "Theta", "OI"
        )

        # Load data (2-4 week calls)
        data = get_data()
        self.options_data = data.get_option_comparison(self.symbol, option_type='CALL', min_dte=14, max_dte=30)

        if not self.options_data:
            table.add_row("No options data available")
            return

        # Populate table with enhanced formatting
        for idx, row in enumerate(self.options_data[:15]):  # Top 15 by OI
            strike = row.get('strike', 0)
            exp = row.get('expiration_date', 'N/A')
            dte = row.get('dte', 0)
            last_price = row.get('last_price', 0)
            delta = row.get('delta', 0)
            iv = row.get('iv', 0)
            iv_pct = row.get('iv_percentile', None)
            breakeven_move = row.get('breakeven_move_pct', 0)
            delta_per_dollar = row.get('delta_per_dollar', 0)
            theta = row.get('theta_decay_dollars', 0)
            oi = row.get('open_interest', 0)

            # Selection indicator
            selected = "☑" if idx in self.selected_indices else " "

            # Color code IV percentile (cheap vs expensive volatility)
            if iv_pct is not None and iv_pct > 0:
                if iv_pct < 30:
                    iv_pct_str = f"[green]{iv_pct:.0f}[/green]"  # Cheap IV = good for buying
                elif iv_pct < 70:
                    iv_pct_str = f"{iv_pct:.0f}"
                else:
                    iv_pct_str = f"[red]{iv_pct:.0f}[/red]"  # Expensive IV = bad for buying
            else:
                iv_pct_str = "─"

            # Color code delta/$
            if delta_per_dollar > 1.0:
                delta_str = f"[bold green]{delta_per_dollar:.2f} ⭐⭐⭐[/bold green]"
            elif delta_per_dollar > 0.7:
                delta_str = f"[green]{delta_per_dollar:.2f} ⭐⭐[/green]"
            else:
                delta_str = f"{delta_per_dollar:.2f}"

            # Color code breakeven
            if abs(breakeven_move) < 5:
                be_str = f"[green]{breakeven_move:+.1f}%[/green]"
            elif abs(breakeven_move) < 10:
                be_str = f"[yellow]{breakeven_move:+.1f}%[/yellow]"
            else:
                be_str = f"[red]{breakeven_move:+.1f}%[/red]"

            # Color code DTE freshness
            if dte <= 14:
                dte_str = f"[yellow]{dte}[/yellow]"
            else:
                dte_str = str(dte)

            table.add_row(
                selected,
                f"[bold]${strike:.1f}[/bold]",
                exp,
                dte_str,
                f"${last_price:.2f}",
                f"{delta:.2f}",
                f"{iv*100:.0f}" if iv else "─",
                iv_pct_str,
                be_str,
                delta_str,
                f"${theta:.2f}",
                f"{oi:,}"
            )

        # Focus table
        table.focus()

    def _update_status_bar(self) -> None:
        """Update status bar with selection count"""
        try:
            status = self.query_one("#status-bar", Static)

            if self.selected_indices:
                # Show comparison summary
                selected_count = len(self.selected_indices)
                status_text = (
                    f"[bold]{self.symbol}[/bold] | "
                    f"[green]Selected: {selected_count}[/green] | "
                    f"[bold]Space:[/bold] Select | [bold]V:[/bold] View Comparison | [bold]C:[/bold] Clear | "
                    f"[dim]ESC: Back[/dim]"
                )
            else:
                status_text = (
                    f"[bold]{self.symbol}[/bold] CALL options (14-30 DTE) | "
                    f"Contracts: {len(self.options_data)} | "
                    f"[bold]Space:[/bold] Select contracts | [bold]V:[/bold] View | [dim]ESC: Back[/dim]"
                )

            status.update(status_text)
        except NoMatches:
            pass

    def action_toggle_select(self) -> None:
        """Toggle selection of current row"""
        table = self.query_one("#compare-table", DataTable)
        row_index = table.cursor_row

        if row_index < 0 or row_index >= len(self.options_data):
            return

        # Toggle selection
        if row_index in self.selected_indices:
            self.selected_indices.remove(row_index)
        else:
            self.selected_indices.add(row_index)

        # Reload table to update selection indicators
        self._reload_table()
        self._update_status_bar()

    def _reload_table(self) -> None:
        """Reload table with updated selection indicators"""
        table = self.query_one("#compare-table", DataTable)
        current_cursor = table.cursor_row

        # Clear and repopulate
        table.clear()
        table.add_columns(
            "✓", "Strike", "Exp", "DTE", "Last", "Delta", "IV%", "IV‰ (20d)", "B/E Move", "Delta/$", "Theta", "OI"
        )

        for idx, row in enumerate(self.options_data[:15]):
            strike = row.get('strike', 0)
            exp = row.get('expiration_date', 'N/A')
            dte = row.get('dte', 0)
            last_price = row.get('last_price', 0)
            delta = row.get('delta', 0)
            iv = row.get('iv', 0)
            iv_pct = row.get('iv_percentile', None)
            breakeven_move = row.get('breakeven_move_pct', 0)
            delta_per_dollar = row.get('delta_per_dollar', 0)
            theta = row.get('theta_decay_dollars', 0)
            oi = row.get('open_interest', 0)

            # Selection indicator
            selected = "☑" if idx in self.selected_indices else " "

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

            # Color code delta/$
            if delta_per_dollar > 1.0:
                delta_str = f"[bold green]{delta_per_dollar:.2f} ⭐⭐⭐[/bold green]"
            elif delta_per_dollar > 0.7:
                delta_str = f"[green]{delta_per_dollar:.2f} ⭐⭐[/green]"
            else:
                delta_str = f"{delta_per_dollar:.2f}"

            # Color code breakeven
            if abs(breakeven_move) < 5:
                be_str = f"[green]{breakeven_move:+.1f}%[/green]"
            elif abs(breakeven_move) < 10:
                be_str = f"[yellow]{breakeven_move:+.1f}%[/yellow]"
            else:
                be_str = f"[red]{breakeven_move:+.1f}%[/red]"

            # Color code DTE
            if dte <= 14:
                dte_str = f"[yellow]{dte}[/yellow]"
            else:
                dte_str = str(dte)

            table.add_row(
                selected,
                f"[bold]${strike:.1f}[/bold]",
                exp,
                dte_str,
                f"${last_price:.2f}",
                f"{delta:.2f}",
                f"{iv*100:.0f}" if iv else "─",
                iv_pct_str,
                be_str,
                delta_str,
                f"${theta:.2f}",
                f"{oi:,}"
            )

        # Restore cursor position
        table.move_cursor(row=current_cursor)

    def action_clear_basket(self) -> None:
        """Clear all selections"""
        self.selected_indices.clear()
        self._reload_table()
        self._update_status_bar()
        self.notify("Selection cleared", severity="information")

    def action_view_comparison(self) -> None:
        """View side-by-side comparison of selected contracts"""
        if not self.selected_indices:
            self.notify("No contracts selected. Press Space to select contracts.", severity="warning")
            return

        if len(self.selected_indices) > 4:
            self.notify("Too many selected (max 4). Please deselect some.", severity="warning")
            return

        # Show comparison modal (for now just notify with summary)
        selected_strikes = [
            self.options_data[idx].get('strike', 0)
            for idx in sorted(self.selected_indices)
        ]

        summary = f"Comparing {len(self.selected_indices)} contracts: " + ", ".join(f"${s:.1f}" for s in selected_strikes)
        self.notify(summary + " (Full comparison view: future feature)", severity="information")

    def action_back(self) -> None:
        """Return to symbol detail"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

