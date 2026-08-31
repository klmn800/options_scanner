"""Symbol Detail Screen - Hub for symbol analysis views"""

import logging
from typing import Dict

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data

logger = logging.getLogger(__name__)


class SymbolDetailScreen(Screen):
    """Symbol detail hub - menu for drilling into various views"""

    BINDINGS = [
        Binding("1", "oi_distribution", "OI Distribution"),
        Binding("2", "oi_timing", "OI Timing"),
        Binding("3", "compare", "Compare Strikes"),
        Binding("5", "flow_alerts", "Flow Alerts"),
        Binding("p", "add_to_planner", "Add to Planner"),
        Binding("w", "toggle_watchlist", "Watchlist"),
        Binding("c", "toggle_confluence", "Confluence"),
        Binding("escape", "back", "Back"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
        self.show_confluence_breakdown = False

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield ScrollableContainer(
            Static(self._build_detail_menu(), id="symbol-detail"),
            Static("", id="status-bar", classes="status-bar"),
            id="symbol-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Update status bar on mount"""
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        """Update status bar with symbol context"""
        try:
            status = self.query_one("#status-bar", Static)
            data = get_data()
            overview = data.get_symbol_overview(self.symbol)

            if overview:
                signal = overview.get('primary_signal', 'N/A')
                alerts = overview.get('active_alert_count', 0)

                # Check watchlist status (Task 5.5)
                is_on_watchlist = data.is_on_watchlist(self.symbol)
                watchlist_indicator = "[bold green]★ On Watchlist[/bold green] | " if is_on_watchlist else ""

                status_text = (
                    f"[bold]{self.symbol}[/bold] | "
                    f"{watchlist_indicator}"
                    f"Signal: {signal} | "
                    f"Active Alerts: {alerts} | "
                    f"[dim]W: Watchlist | 1-4: Views | ESC: Back[/dim]"
                )
                status.update(status_text)
        except NoMatches:
            pass

    def _build_confluence_breakdown(self, overview: Dict) -> str:
        """Build confluence score factor breakdown"""
        if not overview:
            return ""

        factors = []

        # Factor 1: Flow Alert
        alerts = overview.get('active_alert_count', 0) or 0
        if alerts > 0:
            factors.append(("✓", f"Has Flow Alert ({alerts} active)", "+1", "green"))
        else:
            factors.append(("✗", "Has Flow Alert", " 0", "dim"))

        # Factor 2: Volume Surge
        volume_surge = overview.get('volume_surge_factor', 0) or 0
        if volume_surge > 1.5:
            factors.append(("✓", f"Volume Surge {volume_surge:.1f}x >1.5x", "+1", "green"))
        else:
            factors.append(("✗", f"Volume Surge {volume_surge:.1f}x", " 0", "dim"))

        # Factor 3: Earnings Catalyst
        earnings_days = overview.get('earnings_days_ahead', None)
        if earnings_days and 1 <= earnings_days <= 30:
            factors.append(("✓", f"Earnings Catalyst {earnings_days}d ahead", "+1", "green"))
        else:
            factors.append(("✗", "Earnings Catalyst 1-30d", " 0", "dim"))

        # Factor 4: News Sentiment
        news_sentiment = overview.get('news_sentiment_avg', 0) or 0
        if abs(news_sentiment) > 0.3:
            sentiment_str = f"{news_sentiment:+.2f}"
            factors.append(("✓", f"Strong News Sentiment {sentiment_str}", "+1", "green"))
        else:
            factors.append(("✗", f"News Sentiment {news_sentiment:+.2f}", " 0", "dim"))

        # Factor 5: High OI Conviction
        # Fetch OI distribution to check top strike concentration
        data = get_data()
        oi_detail = data.get_oi_distribution(overview['symbol'])
        high_conviction = False
        conviction_pct = 0

        if oi_detail:
            top_call_pct = oi_detail.get('top_call_pct_of_total', 0) or 0
            top_put_pct = oi_detail.get('top_put_pct_of_total', 0) or 0
            conviction_pct = max(top_call_pct, top_put_pct)
            if conviction_pct > 30:
                high_conviction = True

        if high_conviction:
            factors.append(("✓", f"High OI Conviction {conviction_pct:.0f}% >30%", "+1", "green"))
        else:
            factors.append(("✗", f"OI Conviction {conviction_pct:.0f}%", " 0", "dim"))

        # Build display
        breakdown_text = f"\n[bold yellow]Confluence Score Breakdown:[/bold yellow]\n{'─' * 50}\n"
        for check, label, points, color in factors:
            if color == "green":
                breakdown_text += f"[green]{check} {label:<42} {points}[/green]\n"
            else:
                breakdown_text += f"[dim]{check} {label:<42} {points}[/dim]\n"

        breakdown_text += f"{'─' * 50}\n[dim]Press C to hide breakdown[/dim]\n"

        return breakdown_text

    def _build_detail_menu(self) -> str:
        """Build symbol detail menu text"""
        data = get_data()
        overview = data.get_symbol_overview(self.symbol)

        if not overview:
            return f"[bold red]Symbol {self.symbol} data not available[/bold red]"

        # Build menu
        price = overview.get('current_price', overview.get('close_price', 0))  # Use current_price, fallback to close_price
        price_chg = overview.get('price_change_5d_pct', 0)
        score = overview.get('confluence_score', 0)
        bias = overview.get('direction_bias', 'N/A')
        conviction = overview.get('conviction_level', 'N/A')
        sector = overview.get('sector', 'N/A')
        industry = overview.get('industry', 'N/A')

        # Color-code bias
        if 'BULL' in bias:
            bias_color = "green"
        elif 'BEAR' in bias:
            bias_color = "red"
        else:
            bias_color = "yellow"

        # Color-code price change
        if price_chg > 0:
            price_chg_display = f"[green]+{price_chg:.1f}%[/green]"
        elif price_chg < 0:
            price_chg_display = f"[red]{price_chg:.1f}%[/red]"
        else:
            price_chg_display = f"{price_chg:.1f}%"

        # Score with visual indicator
        score_display = f"{score}/5"
        if score >= 4:
            score_display = f"[bold green]{score}/5 ⭐⭐⭐[/bold green]"
        elif score >= 3:
            score_display = f"[bold yellow]{score}/5 ⭐⭐[/bold yellow]"

        # Check watchlist status (Task 5.1)
        is_on_watchlist = data.is_on_watchlist(self.symbol)
        if is_on_watchlist:
            watchlist_status = "[bold green]★ On My Watchlist[/bold green] | Press [bold]W[/bold] to remove"
        else:
            watchlist_status = "Press [bold]W[/bold] to add to My Watchlist"

        # Build menu with optional confluence breakdown
        menu_text = f"""
[bold cyan]═══ {self.symbol} - Symbol Detail ═══[/bold cyan]
[dim]{sector} - {industry}[/dim]

[bold]Price:[/bold] ${price:.2f} | [bold]5d Change:[/bold] {price_chg_display}
[bold]Confluence Score:[/bold] {score_display} | [bold]Bias:[/bold] [{bias_color}]{bias}[/{bias_color}] ([bold]{conviction}[/bold] conviction)

{watchlist_status}
"""

        # Add breakdown if toggled on
        if self.show_confluence_breakdown:
            menu_text += self._build_confluence_breakdown(overview)

        menu_text += f"""
{'─' * 60}

   [bold cyan][1][/bold cyan] OI Distribution           [dim](Strikes, Greeks, Time)[/dim]
   [bold cyan][2][/bold cyan] OI Timing Analysis        [dim](Smart Money vs Retail)[/dim]
   [bold cyan][3][/bold cyan] Compare Strikes           [dim](Pick best contract)[/dim]
   [bold cyan][4][/bold cyan] AI Analysis               [dim](Claude trading insights)[/dim]
   [bold cyan][5][/bold cyan] Flow Alerts               [dim](Recent institutional activity)[/dim]

   [bold][ESC][/bold] Back to Watchlist

{'─' * 60}

[dim]Navigate: Press number keys | [bold]P:[/bold] Add to Planner | C: Confluence | W: Watchlist | ESC: Back | ?: Help[/dim]
        """
        return menu_text.strip()

    def action_toggle_confluence(self) -> None:
        """Toggle confluence score breakdown display"""
        self.show_confluence_breakdown = not self.show_confluence_breakdown

        # Refresh the detail menu display
        try:
            detail_static = self.query_one("#symbol-detail", Static)
            detail_static.update(self._build_detail_menu())

            # Show notification
            if self.show_confluence_breakdown:
                self.notify("✅ Showing confluence breakdown", severity="information", timeout=1)
            else:
                self.notify("✅ Hiding confluence breakdown", severity="information", timeout=1)
        except NoMatches:
            pass

    def action_toggle_watchlist(self) -> None:
        """Add or remove symbol from watchlist (Tasks 5.3 & 5.4)"""
        data = get_data()
        is_on_watchlist = data.is_on_watchlist(self.symbol)

        if is_on_watchlist:
            # Remove from watchlist (Task 5.4) - with confirmation
            # Import dialog class
            from morning_view.screens.my_watchlist import ConfirmRemoveDialog
            self.app.push_screen(
                ConfirmRemoveDialog(self.symbol),
                lambda confirmed: self._handle_watchlist_removal(confirmed)
            )
        else:
            # Add to watchlist (Task 5.3)
            self._add_to_watchlist()

    def _add_to_watchlist(self) -> None:
        """Add symbol to watchlist"""
        try:
            data = get_data()
            overview = data.get_symbol_overview(self.symbol)

            # Build added_reason from active triggers
            reasons = []
            if overview:
                trigger_flow = overview.get('trigger_flow_alert', 0)
                trigger_earnings = overview.get('trigger_earnings_play', 0)
                if trigger_flow:
                    reasons.append("FLOW_ALERT")
                if trigger_earnings:
                    reasons.append("EARNINGS_PLAY")

            added_reason = " + ".join(reasons) if reasons else "Manual add from detail view"

            # Add to database
            success = data.add_to_watchlist(self.symbol, added_reason)

            if success:
                # Refresh display
                self._refresh_display()
                self.notify(f"✅ {self.symbol} added to My Watchlist", severity="information", timeout=2)
            else:
                self.notify(f"❌ Failed to add {self.symbol}", severity="error")
        except Exception as e:
            self.notify(f"❌ Add failed: {e}", severity="error")

    def _handle_watchlist_removal(self, confirmed: bool) -> None:
        """Handle watchlist removal confirmation"""
        if not confirmed:
            return

        try:
            data = get_data()
            success = data.remove_from_watchlist(self.symbol)

            if success:
                # Refresh display
                self._refresh_display()
                self.notify(f"✅ {self.symbol} removed from My Watchlist", severity="information", timeout=2)
            else:
                self.notify(f"❌ Failed to remove {self.symbol}", severity="error")
        except Exception as e:
            self.notify(f"❌ Removal failed: {e}", severity="error")

    def _refresh_display(self) -> None:
        """Refresh detail menu and status bar"""
        try:
            detail_static = self.query_one("#symbol-detail", Static)
            detail_static.update(self._build_detail_menu())
            self._update_status_bar()
        except NoMatches:
            pass

    def action_oi_timing(self) -> None:
        """Show OI timing screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.oi_timing import OITimingScreen
        self.app.push_screen(OITimingScreen(self.symbol))

    def action_oi_distribution(self) -> None:
        """Show OI distribution screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.oi_distribution import OIDistributionScreen
        self.app.push_screen(OIDistributionScreen(self.symbol))

    def action_compare(self) -> None:
        """Show compare strikes screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.compare_strikes import CompareStrikesScreen
        self.app.push_screen(CompareStrikesScreen(self.symbol))

    def action_flow_alerts(self) -> None:
        """Show Flow Alerts screen filtered to this symbol"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.flow_alerts import FlowAlertsScreen
        self.app.push_screen(FlowAlertsScreen(symbol=self.symbol))

    async def action_add_to_planner(self) -> None:
        """Add this symbol to capital planner"""
        try:
            # Query earnings_upcoming for this symbol
            data = get_data()

            import sqlite3
            with sqlite3.connect(data.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT earnings_date, earnings_time
                    FROM earnings_upcoming
                    WHERE symbol = ?
                      AND earnings_date >= date('now')
                    ORDER BY earnings_date
                    LIMIT 1
                """, (self.symbol,))

                results = cursor.fetchall()

            if results:
                earnings_date = results[0][0]
                earnings_time = results[0][1]

                # Launch add position modal with pre-filled data
                from morning_view.screens.capital_planner import AddPositionModal
                result = await self.app.push_screen_wait(
                    AddPositionModal(
                        symbol=self.symbol,
                        earnings_date=earnings_date
                    )
                )

                if result:  # If saved
                    self.notify(
                        f"✓ {self.symbol} added to Capital Planner",
                        severity="information",
                        timeout=3
                    )
            else:
                self.notify(
                    f"No upcoming earnings found for {self.symbol}",
                    severity="warning",
                    timeout=3
                )

        except Exception as e:
            logger.error(f"Error adding to planner: {e}")
            self.notify(f"Error: {str(e)}", severity="error")

    def action_back(self) -> None:
        """Return to watchlist"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

