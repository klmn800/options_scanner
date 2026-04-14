"""My Watchlist Screen - User-curated watchlist"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static, DataTable
from textual.screen import Screen
from textual.binding import Binding
from textual import events
from textual.css.query import NoMatches

from morning_view.tui_data import get_data


class MyWatchlistScreen(Screen):
    """My Watchlist screen - user-curated persistent watchlist with trigger context"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "sort", "Sort"),
        Binding("x", "remove", "Remove"),
        Binding("v", "view_toggle", "Discovery"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.watchlist_data = []
        self.sort_mode = 'relevance'

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Static("[bold cyan]MY WATCHLIST[/bold cyan]", id="my-watchlist-title"),
            DataTable(id="my-watchlist-table", zebra_stripes=True, cursor_type="row"),
            Static("", id="status-bar", classes="status-bar"),
            id="my-watchlist-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize table when screen is mounted"""
        self._load_my_watchlist()
        self._update_status_bar()

    def _load_my_watchlist(self) -> None:
        """Load and display user watchlist data with trigger context and sorting"""
        table = self.query_one("#my-watchlist-table", DataTable)
        table.clear(columns=True)

        # Add columns with Triggers column for badge display
        table.add_columns(
            "#", "Symbol", "Triggers", "Earn", "New", "Recent (5d)", "Active", "Days", "Price", "Added"
        )

        # Load watchlist data from database
        data = get_data()
        self.watchlist_data = data.get_my_watchlist()

        if not self.watchlist_data:
            table.add_row("", "No symbols on watchlist", "", "", "", "", "", "")
            return

        # Apply sort mode
        if self.sort_mode == 'relevance':
            # Already sorted by relevance score from database (default)
            pass
        elif self.sort_mode == 'date_added':
            # Sort by added_date descending (most recent first)
            self.watchlist_data = sorted(self.watchlist_data, key=lambda x: x.get('added_date', ''), reverse=True)
        elif self.sort_mode == 'alphabetical':
            # Sort by symbol alphabetically
            self.watchlist_data = sorted(self.watchlist_data, key=lambda x: x.get('symbol', ''))

        # Populate table with watchlist rows
        for idx, row in enumerate(self.watchlist_data, 1):
            # Extract values
            symbol = row.get('symbol', 'N/A')
            price = row.get('current_price', row.get('close_price', 0))  # Use current_price, fallback to close_price
            added_date = row.get('added_date', 'N/A')
            earnings_days_ahead = row.get('earnings_days_ahead', None)

            # Temporal context - new alerts, recent alerts (5d), and days since last
            new_alert_count = row.get('new_alert_count', 0) or 0
            recent_alert_count_5d = row.get('recent_alert_count_5d', 0) or 0
            days_since_last = row.get('days_since_last_alert', 999)
            active_alerts = row.get('active_alert_count', 0) or 0

            # Task 4.4 - Check for stale conditions
            is_stale = (days_since_last > 25) or (active_alerts == 0)

            # Build trigger badges (🚨 for flow alerts, 📅 for earnings plays)
            trigger_flow = row.get('trigger_flow_alert', 0)
            trigger_earnings = row.get('trigger_earnings_play', 0)
            trigger_badges = ""

            # Task 4.4 - Add stale warning badge first if stale
            if is_stale:
                if active_alerts == 0:
                    trigger_badges = "⚠️ "  # Stale: no triggers
                else:
                    trigger_badges = "⚠️ "  # Stale: old alerts (>25 days)

            # Add regular trigger badges
            if trigger_flow:
                trigger_badges += "🚨"
            if trigger_earnings:
                trigger_badges += "📅"
            if not trigger_badges or trigger_badges == "⚠️ ":
                trigger_badges = "⚠️" if is_stale else "─"  # No triggers

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

            # Format days since last alert with stale warning
            if days_since_last < 999:
                if days_since_last == 0:
                    days_display = f"[bold green]Today[/bold green]"
                elif days_since_last <= 3:
                    days_display = f"[green]{days_since_last}d[/green]"
                elif days_since_last <= 7:
                    days_display = f"[yellow]{days_since_last}d[/yellow]"
                elif days_since_last > 25:
                    # Task 4.4 - Stale warning for old alerts
                    days_display = f"[dim]{days_since_last}d (stale)[/dim]"
                else:
                    days_display = f"[dim]{days_since_last}d[/dim]"
            else:
                days_display = "[dim]─ (stale)[/dim]" if active_alerts == 0 else "─"

            # Alerts indicator with stale handling
            if active_alerts == 0:
                alerts_display = "[dim]0 (stale)[/dim]"
            else:
                alerts_display = f"[bold]{active_alerts}[/bold]"

            # Format added date (show as MM/DD)
            if added_date and added_date != 'N/A':
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(added_date, '%Y-%m-%d')
                    added_display = date_obj.strftime('%m/%d')
                except:
                    added_display = added_date
            else:
                added_display = "N/A"

            # Format earnings days ahead (color code like Discovery page)
            if earnings_days_ahead is not None and earnings_days_ahead >= 0:
                if 1 <= earnings_days_ahead <= 7:
                    # T-7 to T-1 = entry window (green)
                    earnings_display = f"[bold green]{earnings_days_ahead}d[/bold green]"
                elif 8 <= earnings_days_ahead <= 14:
                    # T-14 to T-8 = watch zone (yellow)
                    earnings_display = f"[yellow]{earnings_days_ahead}d[/yellow]"
                elif 15 <= earnings_days_ahead <= 30:
                    # T-30 to T-15 = planning horizon (dim)
                    earnings_display = f"[dim]{earnings_days_ahead}d[/dim]"
                else:
                    # Beyond 30 days
                    earnings_display = f"[dim]{earnings_days_ahead}d[/dim]"
            else:
                earnings_display = "[dim]─[/dim]"

            # Task 4.4 - Use dim color for stale rows
            if is_stale:
                table.add_row(
                    f"[dim]{idx}[/dim]",
                    f"[dim]{symbol}[/dim]",
                    trigger_badges,
                    earnings_display,
                    new_display,
                    recent_display,
                    alerts_display,
                    days_display,
                    f"[dim]${price:.2f}[/dim]",
                    f"[dim]{added_display}[/dim]"
                )
            else:
                table.add_row(
                    str(idx),
                    f"[bold]{symbol}[/bold]",
                    trigger_badges,
                    earnings_display,
                    new_display,
                    recent_display,
                    alerts_display,
                    days_display,
                    f"${price:.2f}",
                    added_display
                )

        # Focus table for keyboard navigation
        table.focus()

    def _update_status_bar(self) -> None:
        """Update status bar with watchlist context"""
        try:
            status = self.query_one("#status-bar", Static)
            data = get_data()
            market_ctx = data.get_market_context()

            market_dir = market_ctx.get('market_direction', 'Unknown')
            regime = market_ctx.get('market_regime', 'Unknown')

            # Color code market direction
            if market_dir == 'BULLISH':
                market_color = "green"
            elif market_dir == 'BEARISH':
                market_color = "red"
            else:
                market_color = "yellow"

            status_text = (
                f"[{market_color}]Market: {market_dir}[/{market_color}] | "
                f"Regime: {regime} | "
                f"[bold cyan]My Watchlist:[/bold cyan] {len(self.watchlist_data)} symbols | "
                f"[dim]Enter: Detail | S: Sort | X: Remove | R: Refresh | ESC: Back[/dim]"
            )
            status.update(status_text)
        except NoMatches:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection"""
        # Get selected symbol
        row_index = event.cursor_row
        if 0 <= row_index < len(self.watchlist_data):
            symbol = self.watchlist_data[row_index]['symbol']
            # Lazy import to avoid circular dependency
            from morning_view.screens.symbol_detail import SymbolDetailScreen
            # Navigate to symbol detail
            self.app.push_screen(SymbolDetailScreen(symbol))

    def action_sort(self) -> None:
        """Cycle through sort modes"""
        # Cycle through sort modes
        sort_modes = ['relevance', 'date_added', 'alphabetical']
        current_idx = sort_modes.index(self.sort_mode)
        next_idx = (current_idx + 1) % len(sort_modes)
        self.sort_mode = sort_modes[next_idx]

        # Reload table with new sort
        self._load_my_watchlist()
        self._update_status_bar()

        # Show notification with sort mode name
        mode_names = {
            'relevance': 'Relevance (activity score)',
            'date_added': 'Date Added (newest first)',
            'alphabetical': 'Alphabetical (A-Z)'
        }
        self.notify(f"✅ Sorted by: {mode_names[self.sort_mode]}", severity="information", timeout=2)

    def action_remove(self) -> None:
        """Remove symbol from watchlist with confirmation"""
        # Get selected symbol from table cursor
        table = self.query_one("#my-watchlist-table", DataTable)
        row_index = table.cursor_row

        # Check if valid row selected
        if row_index < 0 or row_index >= len(self.watchlist_data):
            self.notify("No symbol selected. Use arrow keys to select a symbol first.", severity="warning")
            return

        symbol = self.watchlist_data[row_index]['symbol']

        # Show confirmation dialog
        self.app.push_screen(
            ConfirmRemoveDialog(symbol),
            lambda confirmed: self._handle_remove_confirmation(symbol, confirmed)
        )

    def _handle_remove_confirmation(self, symbol: str, confirmed: bool) -> None:
        """Handle removal confirmation callback"""
        if not confirmed:
            return

        try:
            # Remove from database
            data = get_data()
            success = data.remove_from_watchlist(symbol)

            if success:
                # Reload watchlist
                self._load_my_watchlist()
                self._update_status_bar()
                self.notify(f"✅ {symbol} removed from My Watchlist", severity="information", timeout=2)
            else:
                self.notify(f"❌ Failed to remove {symbol}", severity="error")
        except Exception as e:
            self.notify(f"❌ Removal failed: {e}", severity="error")

    def action_back(self) -> None:
        """Return to main menu"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        """Refresh watchlist data from database"""
        try:
            # Reload table (_load_my_watchlist fetches fresh data)
            self._load_my_watchlist()

            # Update status bar with new data
            self._update_status_bar()

            self.notify("✅ My Watchlist refreshed", severity="information", timeout=2)
        except Exception as e:
            self.notify(f"❌ Refresh failed: {e}", severity="error")

    def action_view_toggle(self) -> None:
        """Toggle to Discovery screen"""
        # Lazy import to avoid circular dependency
        from morning_view.screens.discovery import DiscoveryScreen
        # Pop current screen and push Discovery screen
        self.app.pop_screen()
        self.app.push_screen(DiscoveryScreen())


class ConfirmRemoveDialog(Screen):
    """Confirmation dialog for removing symbol from watchlist"""

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def compose(self) -> ComposeResult:
        """Create dialog widgets"""
        dialog_text = f"""
[bold cyan]Remove from My Watchlist?[/bold cyan]

Symbol: [bold]{self.symbol}[/bold]

This will remove the symbol from your watchlist.
You can always add it back later.

Press [bold green]Y[/bold green] to remove or [bold red]N[/bold red] to cancel
        """

        yield Container(
            Static(dialog_text.strip(), id="dialog-content"),
            id="dialog-container"
        )

    def on_key(self, event: events.Key) -> None:
        """Handle key press"""
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)
