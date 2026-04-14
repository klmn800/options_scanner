"""OI Distribution Screen - Strikes, Greeks, Time breakdown"""

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class OIDistributionScreen(Screen):
    """OI Distribution - Strikes, Greeks, Time breakdown"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield ScrollableContainer(
            Static(self._build_distribution(), id="distribution-content"),
            Static("", id="status-bar", classes="status-bar"),
            id="distribution-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Update status bar on mount"""
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """Update status bar with distribution context"""
        try:
            status = self.query_one("#status-bar", Static)
            data = get_data()
            oi_detail = data.get_oi_distribution(self.symbol)

            if oi_detail:
                total_oi = oi_detail.get('total_open_interest', 0)
                pcr = oi_detail.get('put_call_ratio', 0)

                # Determine bias from PCR
                if pcr > 1.5:
                    bias = "[red]BEARISH[/red]"
                elif pcr < 0.7:
                    bias = "[green]BULLISH[/green]"
                else:
                    bias = "[yellow]NEUTRAL[/yellow]"

                status_text = (
                    f"[bold]{self.symbol}[/bold] OI Distribution | "
                    f"Total OI: {total_oi:,} | "
                    f"P/C Ratio: {pcr:.2f} ({bias}) | "
                    f"[dim]ESC: Back | ?: Help[/dim]"
                )
                status.update(status_text)
        except NoMatches:
            pass

    def _make_bar(self, percentage: float, max_width: int = 40) -> str:
        """Create ASCII bar chart for percentage"""
        if percentage is None or percentage == 0:
            return ""

        filled = int((percentage / 100) * max_width)
        bar = "█" * filled + "░" * (max_width - filled)
        return bar

    def _build_distribution(self) -> str:
        """Build OI distribution display with visual charts"""
        data = get_data()
        oi_detail = data.get_oi_distribution(self.symbol)

        if not oi_detail:
            return f"[bold red]No OI distribution data for {self.symbol}[/bold red]"

        # Extract values
        total_call_oi = oi_detail.get('total_call_oi', 0)
        total_put_oi = oi_detail.get('total_put_oi', 0)
        total_oi = total_call_oi + total_put_oi
        put_call_ratio = oi_detail.get('put_call_ratio', 0)
        top_calls = oi_detail.get('top_call_display', 'N/A')
        top_puts = oi_detail.get('top_put_display', 'N/A')

        # Time distribution
        dte_0_7 = oi_detail.get('oi_0_7_days_percent', 0) or 0
        dte_8_21 = oi_detail.get('oi_8_21_days_percent', 0) or 0
        dte_22_35 = oi_detail.get('oi_22_35_days_percent', 0) or 0
        dte_36_60 = oi_detail.get('oi_36_60_days_percent', 0) or 0

        # P/C ratio by time bucket
        call_oi_0_7 = oi_detail.get('call_oi_0_7_days', 0) or 0
        put_oi_0_7 = oi_detail.get('put_oi_0_7_days', 0) or 0
        pc_0_7 = (put_oi_0_7 / call_oi_0_7) if call_oi_0_7 > 0 else 0

        call_oi_8_21 = oi_detail.get('call_oi_8_21_days', 0) or 0
        put_oi_8_21 = oi_detail.get('put_oi_8_21_days', 0) or 0
        pc_8_21 = (put_oi_8_21 / call_oi_8_21) if call_oi_8_21 > 0 else 0

        call_oi_22_35 = oi_detail.get('call_oi_22_35_days', 0) or 0
        put_oi_22_35 = oi_detail.get('put_oi_22_35_days', 0) or 0
        pc_22_35 = (put_oi_22_35 / call_oi_22_35) if call_oi_22_35 > 0 else 0

        call_oi_36_60 = oi_detail.get('call_oi_36_60_days', 0) or 0
        put_oi_36_60 = oi_detail.get('put_oi_36_60_days', 0) or 0
        pc_36_60 = (put_oi_36_60 / call_oi_36_60) if call_oi_36_60 > 0 else 0

        # Moneyness
        itm_call_pct = oi_detail.get('itm_call_pct', 0) or 0
        atm_call_pct = oi_detail.get('atm_call_pct', 0) or 0
        otm_call_pct = oi_detail.get('otm_call_pct', 0) or 0
        itm_put_pct = oi_detail.get('itm_put_pct', 0) or 0
        atm_put_pct = oi_detail.get('atm_put_pct', 0) or 0
        otm_put_pct = oi_detail.get('otm_put_pct', 0) or 0

        # Greeks
        net_delta = (oi_detail.get('net_delta_exposure', 0) or 0) / 1_000_000
        total_gamma = (oi_detail.get('total_gamma_exposure', 0) or 0) / 1_000_000
        max_gamma_strike = oi_detail.get('max_gamma_strike', 0)
        net_vega = (oi_detail.get('net_vega_exposure', 0) or 0) / 1_000

        # Max pain
        max_pain = oi_detail.get('max_pain_by_friday', 0)
        close_price = oi_detail.get('current_price', oi_detail.get('close_price', 0))  # Use current_price, fallback to close_price
        if max_pain and close_price:
            pain_distance = ((max_pain - close_price) / close_price) * 100
        else:
            pain_distance = 0

        # Build visual distribution text
        distribution_text = f"""
[bold cyan]═══ {self.symbol} - OI Distribution ═══[/bold cyan]

[bold]OPEN INTEREST BREAKDOWN[/bold]
{'─' * 70}
Total OI: [bold]{total_oi:,}[/bold] | Calls: [green]{total_call_oi:,}[/green] | Puts: [red]{total_put_oi:,}[/red]
Put/Call Ratio: [bold]{put_call_ratio:.2f}[/bold]

[green]Calls[/green] {self._make_bar((total_call_oi / total_oi * 100) if total_oi > 0 else 0)} {(total_call_oi / total_oi * 100) if total_oi > 0 else 0:.1f}%
[red]Puts [/red] {self._make_bar((total_put_oi / total_oi * 100) if total_oi > 0 else 0)} {(total_put_oi / total_oi * 100) if total_oi > 0 else 0:.1f}%

Top 5 Call Strikes: {top_calls}
Top 5 Put Strikes:  {top_puts}

[bold]TIME DISTRIBUTION (Days to Expiration)[/bold]
{'─' * 70}
[green]0-7 DTE  [/green] {self._make_bar(dte_0_7)} {dte_0_7:.1f}% (P/C {pc_0_7:.2f})
[yellow]8-21 DTE [/yellow] {self._make_bar(dte_8_21)} {dte_8_21:.1f}% (P/C {pc_8_21:.2f})
[cyan]22-35 DTE[/cyan] {self._make_bar(dte_22_35)} {dte_22_35:.1f}% (P/C {pc_22_35:.2f})
[blue]36-60 DTE[/blue] {self._make_bar(dte_36_60)} {dte_36_60:.1f}% (P/C {pc_36_60:.2f})

[bold]MONEYNESS DISTRIBUTION[/bold]
{'─' * 70}
[bold green]CALLS:[/bold green]
  ITM {self._make_bar(itm_call_pct, 30)} {itm_call_pct:.1f}%
  ATM {self._make_bar(atm_call_pct, 30)} {atm_call_pct:.1f}%
  OTM {self._make_bar(otm_call_pct, 30)} {otm_call_pct:.1f}%

[bold red]PUTS:[/bold red]
  ITM {self._make_bar(itm_put_pct, 30)} {itm_put_pct:.1f}%
  ATM {self._make_bar(atm_put_pct, 30)} {atm_put_pct:.1f}%
  OTM {self._make_bar(otm_put_pct, 30)} {otm_put_pct:.1f}%

[bold]GREEK EXPOSURES[/bold]
{'─' * 70}
Net Delta Exposure:   {net_delta:+.2f}M shares  {'[green]BULLISH[/green]' if net_delta > 0 else '[red]BEARISH[/red]'}
Total Gamma Exposure: {total_gamma:.2f}M
Max Gamma Strike:     [bold]${max_gamma_strike:.2f}[/bold] (pin risk zone)
Net Vega Exposure:    {net_vega:+.0f}K

[bold]MAX PAIN[/bold]
{'─' * 70}
Max Pain Price: [bold]${max_pain:.2f}[/bold]
Distance from Current (${close_price:.2f}): {pain_distance:+.1f}%

{'─' * 60}
[dim]Press ESC to return | ?: Help[/dim]
        """
        return distribution_text.strip()

    def action_back(self) -> None:
        """Return to symbol detail"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

