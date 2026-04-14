"""Main Menu Screen - Entry point for TUI"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding
from pathlib import Path

from morning_view.tui_data import get_data
from morning_view.market_context import get_market_context
from morning_view.live_market_data import get_live_market_snapshot, format_market_snapshot
from tools.timezone_utils import eastern_date_string


class MainMenuScreen(Screen):
    """Main menu screen - entry point for TUI"""

    BINDINGS = [
        Binding("1", "my_watchlist", "My Watchlist"),
        Binding("2", "watchlist", "Discovery"),
        Binding("3", "earnings_calendar", "Earnings"),
        Binding("4", "earnings_browser", "Earnings Browser"),
        Binding("5", "capital_planner", "Capital Planner"),
        Binding("6", "flow_alerts", "Flow Alerts"),
        Binding("9", "settings", "Settings"),
        Binding("m", "load_market_context", "Market Analysis", show=True),
        Binding("l", "toggle_panel", "Toggle Panel", show=True),
        Binding("x", "admin_mode", "Admin Mode", show=True),
        Binding("r", "refresh", "Refresh Data"),
        Binding("f", "force_refresh", "Force AI Refresh"),
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self):
        """Initialize main menu screen with state tracking"""
        super().__init__()
        self.ai_loaded = False  # Track if AI analysis has been loaded
        self.manual_override = None  # 'ai' or 'live' if user toggled manually

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            Horizontal(
                Static(self._build_menu(), id="main-menu"),
                Static(self._build_market_context(), id="market-context-panel"),
            ),
            id="main-container"
        )
        yield Footer()

    def _build_menu(self) -> str:
        """Build main menu text"""
        data = get_data()
        market_ctx = data.get_market_context()
        display_date = data.get_display_date()
        latest_scan = data.get_latest_scan_time()

        # Format latest scan time
        if latest_scan:
            from datetime import datetime
            scan_dt = datetime.strptime(latest_scan, '%Y-%m-%d %H:%M:%S')
            scan_time = scan_dt.strftime('%I:%M%p').lstrip('0')  # No space between time and AM/PM
            freshness_text = f"Last scan: {scan_time}"
        else:
            freshness_text = "No recent scans"

        # Capitalize regime for display
        regime = market_ctx.get('market_regime', 'Unknown')
        regime_display = regime.capitalize() if regime else 'Unknown'

        menu_text = f"""
[bold cyan]Morning Views - Interactive Terminal[/bold cyan]
{eastern_date_string()} | Data: {display_date} | {freshness_text}
Market: {market_ctx.get('market_direction', 'Unknown')} | Regime: {regime_display}

{'─' * 50}

   [bold][1][/bold] My Watchlist              (Your curated symbols)
   [bold][2][/bold] Symbol Discovery          (Triggered symbols)
   [bold][3][/bold] Earnings Calendar         (90-day grid view)
   [bold][4][/bold] Earnings Browser          (90-day list view)
   [bold][5][/bold] Capital Planner           (Plan earnings trades)
   [bold][6][/bold] Flow Alerts               (Recent options flow)
   [bold][9][/bold] Settings                  (Edit configuration)

   [bold]\\[X][/bold] Admin Mode                (Production database)

{'─' * 50}

[dim]Navigate: Press number keys | M: Market | L: Toggle | R: Refresh | F: Force AI | ?: Help[/dim]
        """
        return menu_text.strip()

    def _get_db_path(self) -> str:
        """Get database path from config"""
        import json
        config_path = Path(__file__).parent.parent / 'config.json'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return str(Path(__file__).parent.parent.parent / config['database']['path'])
        except Exception:
            return 'data/datalake_query.db'

    def _build_market_context(self) -> str:
        """Build market context panel - time-aware display with state tracking"""
        from tools.timezone_utils import now_eastern

        hour = now_eastern().hour

        # Determine default panel based on time
        # 6:00 AM - 9:30 AM: AI Analysis (yesterday's context for planning)
        # 9:30 AM - 6:00 PM: Live Market Snapshot (active trading)
        # 6:00 PM - 11:59 PM: AI Analysis (today's completed session)
        if 6 <= hour < 9 or hour >= 18:
            default_panel = 'ai'
        else:
            default_panel = 'live'

        # Use manual override if set, otherwise use time-based default
        active_panel = self.manual_override or default_panel

        if active_panel == 'ai':
            if self.ai_loaded:
                return self._build_ai_loaded_panel()
            else:
                return self._build_ai_placeholder_panel()
        else:  # live
            return self._build_live_panel()

    def _build_ai_placeholder_panel(self) -> str:
        """AI Analysis panel - not yet loaded"""
        return """[bold cyan]AI Market Analysis[/bold cyan]

[dim]Press [bold]M[/bold] to load AI market analysis
(uses cache if available - free & instant)

Press [bold]F[/bold] to force fresh analysis
(costs ~$0.002, takes 30-60 seconds)

Press [bold]L[/bold] to view live market snapshot[/dim]"""

    def _build_ai_loaded_panel(self) -> str:
        """AI Analysis panel - already loaded (fetched from market_context module)"""
        db_path = self._get_db_path()

        # Get AI context (should be cached after initial load)
        try:
            ai_context_text = get_market_context(db_path, force_refresh=False)

            # Add navigation hints
            footer_hints = "\n\n[dim]Press [bold]L[/bold] to view live snapshot | [bold]F[/bold] to refresh AI[/dim]"
            return ai_context_text + footer_hints

        except Exception as e:
            return f"[dim red]AI analysis error:\n{str(e)}[/dim red]"

    def _build_live_panel(self) -> str:
        """Live Market Snapshot panel (trading hours)"""
        db_path = self._get_db_path()

        # Get live market snapshot
        snapshot = get_live_market_snapshot(db_path)
        live_data = format_market_snapshot(snapshot)

        # Add navigation hints (positioned on second-to-last line)
        footer_hints = "\n\n\n\n\n[dim]Press [bold]M[/bold] to load AI analysis[/dim]"

        return f"""[bold cyan]Live Market Snapshot[/bold cyan]

{live_data}{footer_hints}"""

    def action_watchlist(self) -> None:
        """Show discovery screen"""
        # LAZY IMPORT - avoids circular imports
        from morning_view.screens.discovery import DiscoveryScreen
        self.app.push_screen(DiscoveryScreen())

    def action_my_watchlist(self) -> None:
        """Show my watchlist screen"""
        # LAZY IMPORT
        from morning_view.screens.my_watchlist import MyWatchlistScreen
        self.app.push_screen(MyWatchlistScreen())

    def action_earnings_calendar(self) -> None:
        """Show earnings calendar screen (90-day grid)"""
        # LAZY IMPORT
        from morning_view.screens.earnings_calendar_90day import EarningsCalendar90DayScreen
        self.app.push_screen(EarningsCalendar90DayScreen())

    def action_flow_alerts(self) -> None:
        """Show flow alerts screen"""
        # LAZY IMPORT
        from morning_view.screens.flow_alerts import FlowAlertsScreen
        self.app.push_screen(FlowAlertsScreen())

    def action_search(self) -> None:
        """Show search screen"""
        # LAZY IMPORT
        from morning_view.screens.search import SearchScreen
        self.app.push_screen(SearchScreen())

    def action_settings(self) -> None:
        """Show settings screen"""
        # LAZY IMPORT
        from morning_view.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen())

    def action_capital_planner(self) -> None:
        """Show capital planner screen"""
        # LAZY IMPORT
        from morning_view.screens.capital_planner import CapitalPlannerScreen
        self.app.push_screen(CapitalPlannerScreen())

    def action_earnings_browser(self) -> None:
        """Show earnings browser screen"""
        # LAZY IMPORT
        from morning_view.screens.earnings_browser import EarningsBrowserScreen
        self.app.push_screen(EarningsBrowserScreen())

    def action_quit(self) -> None:
        """Quit application"""
        self.app.exit()

    def action_help(self) -> None:
        """Show help screen"""
        # LAZY IMPORT
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        """Fast refresh: menu + live data only (no AI re-run)"""
        try:
            # Refresh menu data
            menu_static = self.query_one("#main-menu", Static)
            menu_static.update(self._build_menu())

            # Refresh right panel (preserves AI loaded state, updates live data if showing)
            context_static = self.query_one("#market-context-panel", Static)
            context_static.update(self._build_market_context())

            self.notify("✅ Data refreshed", severity="information", timeout=2)

        except Exception as e:
            self.notify(f"❌ Refresh failed: {e}", severity="error")

    def action_force_refresh(self) -> None:
        """Force refresh: menu + live data + AI analysis (costs ~$0.002)"""
        try:
            self.notify("⏳ Force-refreshing all data including AI (~30-60s, costs ~$0.002)...",
                       severity="information", timeout=10)

            # Refresh menu
            menu_static = self.query_one("#main-menu", Static)
            menu_static.update(self._build_menu())

            # Get database path
            db_path = self._get_db_path()

            # Force refresh AI analysis
            ai_context_text = get_market_context(db_path, force_refresh=True)
            self.ai_loaded = True  # Mark as loaded
            self.manual_override = 'ai'  # Show AI panel after refresh

            # Rebuild right panel (will show newly loaded AI)
            context_static = self.query_one("#market-context-panel", Static)
            context_static.update(self._build_market_context())

            self.notify("✅ All data refreshed (new AI analysis complete)",
                       severity="information", timeout=3)

        except Exception as e:
            self.notify(f"❌ Force refresh failed: {e}", severity="error")
            self.ai_loaded = False  # Reset state on failure

    def action_load_market_context(self) -> None:
        """Load AI market analysis on demand (uses cache if available)"""
        self.notify("⏳ Loading market analysis...", severity="information", timeout=5)

        try:
            # Get database path
            db_path = self._get_db_path()

            # Get AI market context (uses cache if available, otherwise runs fresh)
            ai_context_text = get_market_context(db_path, force_refresh=False)

            # Mark as loaded and switch to AI panel
            self.ai_loaded = True
            self.manual_override = 'ai'

            # Update the panel to show AI
            context_static = self.query_one("#market-context-panel", Static)
            context_static.update(self._build_market_context())

            self.notify("✅ Market analysis loaded", severity="information", timeout=2)

        except Exception as e:
            error_msg = f"[dim red]Market analysis failed:\n{str(e)}[/dim red]"
            context_static = self.query_one("#market-context-panel", Static)
            context_static.update(error_msg)
            self.notify(f"❌ Analysis failed: {e}", severity="error")
            self.ai_loaded = False

    def action_toggle_panel(self) -> None:
        """Toggle between AI and live market panels"""
        try:
            # Toggle the manual override
            if self.manual_override == 'ai':
                self.manual_override = 'live'
                panel_name = "live market snapshot"
            elif self.manual_override == 'live':
                self.manual_override = 'ai'
                panel_name = "AI analysis"
            else:
                # No override set - determine current default and toggle to opposite
                from tools.timezone_utils import now_eastern
                hour = now_eastern().hour
                if 6 <= hour < 9 or hour >= 18:
                    # Currently showing AI by default, toggle to live
                    self.manual_override = 'live'
                    panel_name = "live market snapshot"
                else:
                    # Currently showing live by default, toggle to AI
                    self.manual_override = 'ai'
                    panel_name = "AI analysis"

            # Rebuild panel
            context_static = self.query_one("#market-context-panel", Static)
            context_static.update(self._build_market_context())

            self.notify(f"Switched to {panel_name}", severity="information", timeout=2)

        except Exception as e:
            self.notify(f"❌ Toggle failed: {e}", severity="error")

    def action_admin_mode(self) -> None:
        """Enter admin mode - write access to production database"""
        # LAZY IMPORT
        from morning_view.admin_screens import AdminMenuScreen
        self.app.push_screen(AdminMenuScreen())
