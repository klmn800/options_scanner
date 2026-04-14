"""Discovery Screen - Trigger-based symbol feed"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class DiscoveryScreen(Screen):
    """Symbol Discovery screen - trigger-based feed with temporal sorting"""

    BINDINGS = [
        Binding("enter", "select", "Detail"),
        Binding("escape", "back", "Back", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("v", "view_toggle", "Watchlist"),
        Binding("w", "add_to_watchlist", "Add to Watchlist"),
        Binding("a", "ai_analyze", "AI Analyze"),
        Binding("f", "ai_analyze_refresh", "AI Force Refresh", show=False),
        Binding("?", "help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.watchlist_data = []
        self.filter_active = None
        self.sort_column = None
        self.cached_ai_analysis = None  # Session cache for AI analysis

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Static("[bold cyan]SYMBOL DISCOVERY[/bold cyan]", id="watchlist-title"),
            DataTable(id="watchlist-table", zebra_stripes=True, cursor_type="row"),
            Static("", id="status-bar", classes="status-bar"),
            id="watchlist-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table when screen is mounted"""
        self._load_discovery()
        self._update_status_bar()

    def _load_discovery(self) -> None:
        """Load and display discovery data (trigger-based feed)"""
        table = self.query_one("#watchlist-table", DataTable)
        table.clear(columns=True)

        # Add columns with Triggers column for badge display and temporal context
        table.add_columns(
            "#", "Symbol", "Triggers", "Alerts", "New", "Recent", "Last", "Score", "Bias", "Earn", "Price", "5d %"
        )

        # Load discovery data (no limit - show all triggered symbols)
        data = get_data()
        all_discovery = data.get_discovery()

        # Filter out symbols already on user's watchlist (Issue #6)
        watchlist_symbols = {row['symbol'] for row in data.get_my_watchlist()}
        self.watchlist_data = [row for row in all_discovery if row['symbol'] not in watchlist_symbols]

        if not self.watchlist_data:
            table.add_row("No watchlist data available")
            return

        # Populate table with color-coded rows
        for idx, row in enumerate(self.watchlist_data, 1):
            # Format values
            symbol = row.get('symbol', 'N/A')
            score = row.get('confluence_score', 0)
            bias = row.get('direction_bias', 'N/A')
            active_alerts = row.get('active_alert_count', 0)
            price = row.get('current_price', row.get('close_price', 0))  # Use current_price, fallback to close_price
            price_chg = row.get('price_change_5d_pct', 0)

            # Build trigger badges
            trigger_flow = row.get('trigger_flow_alert', 0)
            trigger_earnings = row.get('trigger_earnings_play', 0)
            trigger_badges = ""
            if trigger_flow:
                trigger_badges += "🚨"
            if trigger_earnings:
                trigger_badges += "📅"
            if not trigger_badges:
                trigger_badges = "─"  # No triggers

            # Temporal context - new alerts, recent alerts (5d), and days since last
            new_alert_count = row.get('new_alert_count', 0) or 0
            recent_alert_count_5d = row.get('recent_alert_count_5d', 0) or 0
            days_since_last = row.get('days_since_last_alert', 999)

            # Earnings context
            earnings_days_ahead = row.get('earnings_days_ahead', None)

            # Format new alerts (today only) with highlighting
            if new_alert_count > 0:
                new_display = f"[bold green]{new_alert_count}[/bold green]"
            else:
                new_display = "─"

            # Format recent alerts (last 5 days) with highlighting
            if recent_alert_count_5d > 0:
                recent_display = f"[cyan]{recent_alert_count_5d}[/cyan]"
            else:
                recent_display = "─"

            # Format days since last alert
            if days_since_last < 999:
                if days_since_last == 0:
                    days_display = f"[bold green]Today[/bold green]"
                elif days_since_last <= 3:
                    days_display = f"[green]{days_since_last}d[/green]"
                elif days_since_last <= 7:
                    days_display = f"[yellow]{days_since_last}d[/yellow]"
                else:
                    days_display = f"[dim]{days_since_last}d[/dim]"
            else:
                days_display = "─"

            # Add visual indicators with truncated bias names
            if 'SOMEWHAT_BULLISH' in bias:
                bias_display = f"[green]🟢 BULL-ish[/green]"
            elif 'SOMEWHAT_BEARISH' in bias:
                bias_display = f"[red]🔴 BEAR-ish[/red]"
            elif 'BULLISH' in bias:
                bias_display = f"[green]🟢 BULLISH[/green]"
            elif 'BEARISH' in bias:
                bias_display = f"[red]🔴 BEARISH[/red]"
            else:
                bias_display = f"[yellow]⚪ {bias}[/yellow]"

            # Score with stars
            score_display = f"{score}"
            if score >= 4:
                score_display = f"[bold green]{score} ⭐⭐⭐[/bold green]"
            elif score >= 3:
                score_display = f"[bold yellow]{score} ⭐⭐[/bold yellow]"
            elif score >= 2:
                score_display = f"{score} ⭐"

            # Alerts indicator (Active alerts)
            alerts_display = str(active_alerts) if active_alerts == 0 else f"[bold]{active_alerts}[/bold]"

            # Price change color
            if price_chg is not None and price_chg != 0:
                if price_chg > 0:
                    price_chg_display = f"[green]+{price_chg:.1f}%[/green]"
                else:
                    price_chg_display = f"[red]{price_chg:.1f}%[/red]"
            else:
                price_chg_display = "N/A"

            # Earnings days ahead display with color coding
            if earnings_days_ahead is not None:
                if earnings_days_ahead == 0:
                    earnings_display = f"[bold magenta]TODAY[/bold magenta]"
                elif earnings_days_ahead == 1:
                    earnings_display = f"[bold yellow]TMR[/bold yellow]"
                elif earnings_days_ahead <= 3:
                    earnings_display = f"[yellow]{earnings_days_ahead}d[/yellow]"
                elif earnings_days_ahead <= 7:
                    earnings_display = f"[cyan]{earnings_days_ahead}d[/cyan]"
                elif earnings_days_ahead <= 14:
                    earnings_display = f"{earnings_days_ahead}d"
                else:
                    earnings_display = f"[dim]{earnings_days_ahead}d[/dim]"
            else:
                earnings_display = "─"

            table.add_row(
                str(idx),
                f"[bold]{symbol}[/bold]",
                trigger_badges,
                alerts_display,
                new_display,
                recent_display,
                days_display,
                score_display,
                bias_display,
                earnings_display,
                f"${price:.2f}",
                price_chg_display
            )

        # Focus table for keyboard navigation
        table.focus()

    def _update_status_bar(self) -> None:
        """Update status bar with context"""
        try:
            status = self.query_one("#status-bar", Static)
            data = get_data()
            market_ctx = data.get_market_context()
            latest_scan = data.get_latest_scan_time()

            market_dir = market_ctx.get('market_direction', 'Unknown')
            regime = market_ctx.get('market_regime', 'Unknown')

            # Format latest scan time
            if latest_scan:
                from datetime import datetime
                scan_dt = datetime.strptime(latest_scan, '%Y-%m-%d %H:%M:%S')
                scan_time = scan_dt.strftime('%I:%M %p').lstrip('0')
                freshness = f"Scan: {scan_time}"
            else:
                freshness = "No scans"

            # Color code market direction
            if market_dir == 'BULLISH':
                market_color = "green"
            elif market_dir == 'BEARISH':
                market_color = "red"
            else:
                market_color = "yellow"

            # AI analysis cache status
            ai_status = ""
            if self.cached_ai_analysis:
                if self.cached_ai_analysis.get('from_cache'):
                    age_min = self.cached_ai_analysis.get('cache_age_minutes', 0)
                    if age_min < 60:
                        ai_status = f"[dim]AI: {age_min}m ago[/dim] | "
                    else:
                        age_hours = age_min // 60
                        ai_status = f"[dim]AI: {age_hours}h ago[/dim] | "
                else:
                    ai_status = "[dim]AI: just now[/dim] | "

            status_text = (
                f"[{market_color}]Market: {market_dir}[/{market_color}] | "
                f"Regime: {regime} | "
                f"{freshness} | "
                f"{ai_status}"
                f"[bold cyan]Discovery:[/bold cyan] {len(self.watchlist_data)} triggered | "
                f"[dim]A: AI Analyze | Enter: Detail | W: Add | V: Watchlist | R: Refresh | ESC: Back[/dim]"
            )
            status.update(status_text)
        except NoMatches:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection"""
        self.action_select()

    def action_select(self) -> None:
        """Show detail for selected symbol"""
        table = self.query_one("#watchlist-table", DataTable)
        row_index = table.cursor_row
        if 0 <= row_index < len(self.watchlist_data):
            symbol = self.watchlist_data[row_index]['symbol']
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

    def action_refresh(self) -> None:
        """Refresh discovery data from database"""
        try:
            # Re-fetch discovery data (no limit)
            data = get_data()
            self.watchlist_data = data.get_discovery()

            # Rebuild table
            self._load_discovery()

            # Update status bar with new data
            self._update_status_bar()

            self.notify("✅ Discovery refreshed", severity="information", timeout=2)
        except Exception as e:
            self.notify(f"❌ Refresh failed: {e}", severity="error")

    def action_view_toggle(self) -> None:
        """Toggle to My Watchlist screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.my_watchlist import MyWatchlistScreen
        # Pop current screen and push My Watchlist screen
        self.app.pop_screen()
        self.app.push_screen(MyWatchlistScreen())

    def action_ai_analyze(self) -> None:
        """Run AI analysis on entire discovery feed (use cache if available)"""
        self._run_ai_analysis(force_refresh=False)

    def action_ai_analyze_refresh(self) -> None:
        """Force refresh AI analysis (Shift+A)"""
        self._run_ai_analysis(force_refresh=True)

    def _run_ai_analysis(self, force_refresh: bool = False) -> None:
        """Internal method to run AI analysis with caching support

        Args:
            force_refresh: If True, bypass all caches and force new API call
        """
        try:
            # Import analyzer
            from morning_view.ai_discovery_analyzer import analyze_discovery_feed, format_analysis_for_display

            # Check session cache first (unless force_refresh)
            if not force_refresh and self.cached_ai_analysis:
                result = self.cached_ai_analysis
                # Show from session cache
                formatted_text = format_analysis_for_display(result)
                from morning_view.screens.ai_analysis_result import AIAnalysisResultScreen
                self.app.push_screen(AIAnalysisResultScreen(formatted_text, raw_result=result, parent_screen=self))
                return

            # Show loading notification
            if force_refresh:
                self.notify("🤖 Refreshing AI analysis...", severity="information", timeout=3)
            else:
                self.notify("🤖 AI analyzing discovery feed...", severity="information", timeout=3)

            # Run analysis (will check database cache unless force_refresh)
            result = analyze_discovery_feed(max_recommendations=5, force_refresh=force_refresh)

            # Store in session cache
            self.cached_ai_analysis = result

            # Update status bar to show cache info
            self._update_status_bar()

            # Format for display
            formatted_text = format_analysis_for_display(result)

            # Show result screen
            from morning_view.screens.ai_analysis_result import AIAnalysisResultScreen
            self.app.push_screen(AIAnalysisResultScreen(formatted_text, raw_result=result, parent_screen=self))

        except Exception as e:
            self.notify(f"❌ AI analysis failed: {e}", severity="error", timeout=5)

    def action_add_to_watchlist(self) -> None:
        """Add selected symbol to My Watchlist"""
        table = self.query_one("#watchlist-table", DataTable)
        row_index = table.cursor_row

        # Check if valid row selected
        if row_index < 0 or row_index >= len(self.watchlist_data):
            self.notify("No symbol selected. Use arrow keys to select a symbol first.", severity="warning")
            return

        symbol_data = self.watchlist_data[row_index]
        symbol = symbol_data['symbol']

        # Check if already on watchlist
        data = get_data()
        if data.is_on_watchlist(symbol):
            self.notify(f"ℹ️ {symbol} is already on My Watchlist", severity="information", timeout=2)
            return

        # Build added_reason from triggers
        reasons = []
        trigger_flow = symbol_data.get('trigger_flow_alert', 0)
        trigger_earnings = symbol_data.get('trigger_earnings_play', 0)
        if trigger_flow:
            reasons.append("FLOW_ALERT")
        if trigger_earnings:
            reasons.append("EARNINGS_PLAY")

        added_reason = " + ".join(reasons) if reasons else "Manual add from Discovery"

        # Add to database
        try:
            success = data.add_to_watchlist(symbol, added_reason)
            if success:
                # Reload discovery to remove the symbol from this list
                self._load_discovery()
                self._update_status_bar()
                self.notify(f"✅ {symbol} added to My Watchlist", severity="information", timeout=2)
            else:
                self.notify(f"❌ Failed to add {symbol}", severity="error")
        except Exception as e:
            self.notify(f"❌ Add failed: {e}", severity="error")