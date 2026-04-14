"""Contract History Screen - Daily OI/Volume/IV tracking"""

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class ContractHistoryScreen(Screen):
    """Contract History Deep Dive - Daily OI/Volume/IV tracking"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, contract_hash: str, symbol: str, strike: float, option_type: str, expiration_date: str):
        super().__init__()
        self.contract_hash = contract_hash
        self.symbol = symbol
        self.strike = strike
        self.option_type = option_type
        self.expiration_date = expiration_date
        self.history_data = []

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield ScrollableContainer(
            Static(self._build_contract_header(), id="contract-header"),
            Static(self._build_metrics_summary(), id="metrics-summary"),
            DataTable(id="history-table", zebra_stripes=True),
            Static("", id="status-bar", classes="status-bar"),
            id="history-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table when screen is mounted"""
        self._load_history_data()
        self._update_status_bar()

    def _build_contract_header(self) -> str:
        """Build contract identification header"""
        type_color = "green" if self.option_type == "CALL" else "red"
        header_text = f"""
[bold cyan]═══ Contract History ═══[/bold cyan]
[bold]{self.symbol}[/bold] ${self.strike:.1f} [{type_color}]{self.option_type}[/{type_color}] Exp: {self.expiration_date}
"""
        return header_text.strip()

    def _build_metrics_summary(self) -> str:
        """Build key metrics summary from history"""
        if not self.history_data:
            return ""

        # Calculate metrics from history
        first_row = self.history_data[0]
        latest_row = self.history_data[-1]

        build_start_date = first_row.get('oi_build_start_date', 'N/A')
        build_start_price = first_row.get('oi_build_start_price', 0)
        current_price = latest_row.get('underlying_price', 0)

        # Price movement since build started
        if build_start_price and current_price:
            price_move_pct = ((current_price - build_start_price) / build_start_price) * 100
        else:
            price_move_pct = 0

        # OI momentum
        latest_oi = latest_row.get('open_interest', 0)
        first_oi = first_row.get('open_interest', 0)
        peak_oi = max(row.get('open_interest', 0) for row in self.history_data)

        # Determine momentum
        if latest_oi >= peak_oi * 0.95:  # Within 5% of peak
            momentum_status = "[green]INCREASING[/green]"
        elif latest_oi >= peak_oi * 0.80:  # Within 20% of peak
            momentum_status = "[yellow]STABLE[/yellow]"
        else:
            momentum_status = "[red]DECREASING[/red]"

        # Build pattern
        build_pattern = latest_row.get('build_pattern', 'N/A')
        building_unwinding = latest_row.get('building_unwinding', 'N/A')

        # Days since build
        days_since_build = len(self.history_data)

        # Positioning type (predictive vs chasing)
        if price_move_pct < 2 and days_since_build > 7:
            positioning = "[green]🧠 PREDICTIVE (early position)[/green]"
        elif price_move_pct > 5:
            positioning = "[yellow]📈 CHASING (late to party)[/yellow]"
        else:
            positioning = "⚖️ NEUTRAL"

        # Price move color
        if price_move_pct > 0:
            move_display = f"[green]+{price_move_pct:.1f}%[/green]"
        else:
            move_display = f"[red]{price_move_pct:.1f}%[/red]"

        summary_text = f"""
[bold yellow]KEY METRICS[/bold yellow]
{'─' * 70}
[bold]Build Start:[/bold] {build_start_date} @ ${build_start_price:.2f}
[bold]Current Price:[/bold] ${current_price:.2f} ({move_display} since build)
[bold]Days Since Build:[/bold] {days_since_build} days
[bold]OI Momentum:[/bold] {momentum_status} (Current: {latest_oi:,} | Peak: {peak_oi:,})
[bold]Build Pattern:[/bold] {build_pattern} ({building_unwinding})
[bold]Positioning:[/bold] {positioning}

[bold cyan]DAILY HISTORY[/bold cyan]
{'─' * 70}
"""
        return summary_text.strip()

    def _load_history_data(self) -> None:
        """Load historical data into table"""
        table = self.query_one("#history-table", DataTable)

        # Add columns
        table.add_columns(
            "Date", "OI", "OI Δ%", "Volume", "Vol/OI", "IV%", "IV‰", "IV Δ", "Price", "DTE", "Build"
        )

        # Load data
        data = get_data()
        self.history_data = data.get_contract_history(self.contract_hash)

        if not self.history_data:
            table.add_row("No history data available")
            return

        # Populate table with daily history
        for row in self.history_data:
            trade_date = row.get('trade_date', 'N/A')
            oi = row.get('open_interest', 0)
            oi_change_pct = row.get('oi_change_pct', 0)
            volume = row.get('volume', 0)
            vol_oi_ratio = row.get('volume_ratio_5d', 0)
            iv = row.get('iv', 0)
            iv_pct = row.get('iv_percentile_20day', None)
            iv_change = row.get('iv_change_5d', 0)
            price = row.get('underlying_price', 0)
            dte = row.get('dte', 0)
            build_pattern = row.get('building_unwinding', 'N/A')

            # Color code OI change
            if oi_change_pct and oi_change_pct > 10:
                oi_change_display = f"[green]+{oi_change_pct:.1f}%[/green]"
            elif oi_change_pct and oi_change_pct < -10:
                oi_change_display = f"[red]{oi_change_pct:.1f}%[/red]"
            elif oi_change_pct:
                oi_change_display = f"{oi_change_pct:+.1f}%"
            else:
                oi_change_display = "N/A"

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

            # Color code IV change
            if iv_change and iv_change > 0.1:
                iv_change_display = f"[yellow]+{iv_change:.2f}[/yellow]"
            elif iv_change and iv_change < -0.1:
                iv_change_display = f"[green]{iv_change:.2f}[/green]"
            elif iv_change:
                iv_change_display = f"{iv_change:+.2f}"
            else:
                iv_change_display = "N/A"

            # Color code volume/OI ratio
            if vol_oi_ratio and vol_oi_ratio > 1.5:
                vol_oi_display = f"[yellow]{vol_oi_ratio:.2f}[/yellow]"
            else:
                vol_oi_display = f"{vol_oi_ratio:.2f}" if vol_oi_ratio else "N/A"

            # Build pattern indicator
            if 'BUILDING' in build_pattern:
                build_display = "[green]📈 BUILD[/green]"
            elif 'UNWINDING' in build_pattern:
                build_display = "[red]📉 UNWIND[/red]"
            else:
                build_display = "[dim]─[/dim]"

            table.add_row(
                trade_date,
                f"{oi:,}",
                oi_change_display,
                f"{volume:,}",
                vol_oi_display,
                f"{iv*100:.0f}" if iv else "─",
                iv_pct_str,
                iv_change_display,
                f"${price:.2f}" if price else "N/A",
                str(dte) if dte else "N/A",
                build_display
            )

        # Focus table
        table.focus()

    def _update_status_bar(self) -> None:
        """Update status bar with contract context"""
        try:
            status = self.query_one("#status-bar", Static)

            if self.history_data:
                total_days = len(self.history_data)
                latest = self.history_data[-1]
                latest_oi = latest.get('open_interest', 0)

                status_text = (
                    f"[bold]{self.symbol}[/bold] ${self.strike:.1f} {self.option_type} | "
                    f"History: {total_days} days | "
                    f"Latest OI: {latest_oi:,} | "
                    f"[dim]↑↓: Scroll | ESC: Back | ?: Help[/dim]"
                )
            else:
                status_text = (
                    f"[bold]{self.symbol}[/bold] ${self.strike:.1f} {self.option_type} | "
                    f"No history data | "
                    f"[dim]ESC: Back | ?: Help[/dim]"
                )

            status.update(status_text)
        except NoMatches:
            pass

    def action_back(self) -> None:
        """Return to OI timing screen"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

