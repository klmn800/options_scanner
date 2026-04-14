"""Earnings Browser Screen - Browse upcoming tradeable earnings"""

import logging
from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding

from morning_view.tui_data import get_data

logger = logging.getLogger(__name__)


class EarningsBrowserScreen(Screen):
    """Browse upcoming tradeable earnings (next 90 days)"""

    CSS = """
    EarningsBrowserScreen {
        background: $surface;
    }

    #browser-container {
        height: 100%;
        padding: 1 2;
    }

    #browser-header {
        padding: 1 2;
        background: $panel;
        border: solid $primary;
        margin-bottom: 1;
    }

    #browser-table {
        height: 1fr;
        border: solid $primary;
    }

    DataTable {
        height: 100%;
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
    """

    BINDINGS = [
        Binding("enter", "view_detail", "View Detail", show=True),
        Binding("p", "add_to_planner", "Add to Planner", show=True),
        Binding("s", "sort_by", "Sort", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.earnings_data = []
        self.sort_column = "date"
        self.sort_reverse = False

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        with VerticalScroll(id="browser-container"):
            yield Static(id="browser-header")
            yield DataTable(id="browser-table", zebra_stripes=True, cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize screen on mount"""
        self._load_earnings_data()
        self._build_table()

    def _load_earnings_data(self) -> None:
        """Load upcoming tradeable earnings from database"""
        try:
            data = get_data()

            # Load config directly
            from pathlib import Path
            import json
            config_path = Path(__file__).parent.parent / 'config.json'
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Get filter values
            max_price = config.get("filters", {}).get("max_symbol_price", 60)
            min_oi = config.get("filters", {}).get("min_liquidity_oi", 500)

            # Query database directly for upcoming earnings
            import sqlite3
            with sqlite3.connect(data.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        e.symbol,
                        e.earnings_date,
                        e.earnings_time,
                        o.close_price,
                        o.total_open_interest,
                        m.sector,
                        m.industry
                    FROM earnings_upcoming e
                    JOIN option_symbol_summary o ON e.symbol = o.symbol
                    JOIN symbol_metadata m ON e.symbol = m.symbol
                    WHERE e.earnings_date >= date('now')
                      AND e.earnings_date <= date('now', '+90 days')
                      AND o.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
                      AND o.close_price <= ?
                      AND o.total_open_interest >= ?
                    ORDER BY e.earnings_date
                """, (max_price, min_oi))

                results = cursor.fetchall()

            self.earnings_data = []
            for row in results:
                self.earnings_data.append({
                    "symbol": row[0],
                    "earnings_date": row[1],
                    "earnings_time": row[2] or "Unknown",
                    "price": row[3],
                    "open_interest": row[4],
                    "sector": row[5] or "Unknown",
                    "industry": row[6] or "Unknown"
                })

            logger.info(f"Loaded {len(self.earnings_data)} tradeable earnings")

        except Exception as e:
            logger.error(f"Error loading earnings data: {e}")
            self.notify(f"Error loading data: {str(e)}", severity="error")
            self.earnings_data = []

    def _build_table(self) -> None:
        """Build earnings table"""
        try:
            # Load config
            from pathlib import Path
            import json
            config_path = Path(__file__).parent.parent / 'config.json'
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            max_price = config.get("filters", {}).get("max_symbol_price", 60)
            min_oi = config.get("filters", {}).get("min_liquidity_oi", 500)

            # Update header
            header_text = f"""[bold cyan]Earnings Browser - Next 90 Days[/bold cyan]

Filters: <${max_price:.0f} price, {min_oi}+ OI | Showing {len(self.earnings_data)} tradeable symbols
[dim]Press ENTER to view details | Press 'P' to add to planner | Press 'S' to cycle sort[/dim]"""

            header_static = self.query_one("#browser-header", Static)
            header_static.update(header_text)

            # Sort data
            self._sort_data()

            # Build table
            table = self.query_one("#browser-table", DataTable)
            table.clear(columns=True)

            # Add columns
            table.add_column("Symbol", key="symbol", width=10)
            table.add_column("Date", key="date", width=12)
            table.add_column("Day", key="day", width=10)
            table.add_column("Price", key="price", width=10)
            table.add_column("OI", key="oi", width=12)
            table.add_column("Sector", key="sector", width=20)

            # Add rows
            for earnings in self.earnings_data:
                # Format date
                try:
                    dt = datetime.strptime(earnings["earnings_date"], "%Y-%m-%d")
                    date_str = dt.strftime("%m/%d")
                    day_str = dt.strftime("%a")
                except ValueError:
                    date_str = earnings["earnings_date"]
                    day_str = "?"

                # Format price
                price_str = f"${earnings['price']:.0f}"

                # Format OI
                oi = earnings["open_interest"]
                if oi >= 1000000:
                    oi_str = f"{oi / 1000000:.1f}M"
                elif oi >= 1000:
                    oi_str = f"{oi / 1000:.0f}K"
                else:
                    oi_str = str(oi)

                # Sector (truncated)
                sector = earnings["sector"][:18] if len(earnings["sector"]) > 18 else earnings["sector"]

                table.add_row(
                    earnings["symbol"],
                    date_str,
                    day_str,
                    price_str,
                    oi_str,
                    sector,
                    key=earnings["symbol"]
                )

        except Exception as e:
            logger.error(f"Error building table: {e}")
            self.notify(f"Error building table: {str(e)}", severity="error")

    def _sort_data(self) -> None:
        """Sort earnings data based on current sort column"""
        if self.sort_column == "date":
            self.earnings_data.sort(key=lambda x: x["earnings_date"], reverse=self.sort_reverse)
        elif self.sort_column == "symbol":
            self.earnings_data.sort(key=lambda x: x["symbol"], reverse=self.sort_reverse)
        elif self.sort_column == "price":
            self.earnings_data.sort(key=lambda x: x["price"], reverse=self.sort_reverse)
        elif self.sort_column == "sector":
            self.earnings_data.sort(key=lambda x: x["sector"], reverse=self.sort_reverse)

    def _get_selected_earnings(self) -> dict:
        """Get currently selected earnings data"""
        table = self.query_one("#browser-table", DataTable)
        if table.cursor_row >= 0 and table.cursor_row < len(self.earnings_data):
            return self.earnings_data[table.cursor_row]
        return None

    def action_view_detail(self) -> None:
        """View symbol detail screen"""
        earnings = self._get_selected_earnings()
        if not earnings:
            return

        symbol = earnings["symbol"]

        # Launch symbol detail screen
        from morning_view.screens.symbol_detail import SymbolDetailScreen
        self.app.push_screen(SymbolDetailScreen(symbol))

    def action_add_to_planner(self) -> None:
        """Add selected symbol to capital planner"""
        earnings = self._get_selected_earnings()
        if not earnings:
            self.notify("No symbol selected", severity="warning")
            return

        # TODO: Open add position modal with pre-filled data
        # For now, just notify
        self.notify(
            f"Adding {earnings['symbol']} to planner (feature coming soon!)",
            severity="information",
            timeout=3
        )

        # This will be implemented in Phase 5 when we integrate with Symbol Detail

    def action_sort_by(self) -> None:
        """Cycle through sort columns"""
        sort_columns = ["date", "symbol", "price", "sector"]
        current_idx = sort_columns.index(self.sort_column)
        next_idx = (current_idx + 1) % len(sort_columns)

        # If cycling back to same column, reverse order
        if sort_columns[next_idx] == self.sort_column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = sort_columns[next_idx]
            self.sort_reverse = False

        # Rebuild table
        self._build_table()

        self.notify(
            f"Sorted by: {self.sort_column} ({'desc' if self.sort_reverse else 'asc'})",
            severity="information",
            timeout=2
        )

    def action_refresh(self) -> None:
        """Refresh earnings data"""
        self.notify("Refreshing earnings data...", severity="information", timeout=1)
        self._load_earnings_data()
        self._build_table()
        self.notify("✓ Earnings data refreshed", severity="information", timeout=2)

    def action_back(self) -> None:
        """Go back to main menu"""
        self.app.pop_screen()
