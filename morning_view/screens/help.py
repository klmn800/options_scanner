"""Help Screen - Keyboard shortcuts"""

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding


class HelpScreen(Screen):
    """Keyboard shortcuts help"""

    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield ScrollableContainer(
            Static(self._build_help(), id="help-content"),
            id="help-container"
        )
        yield Footer()

    def _build_help(self) -> str:
        """Build help text"""
        help_text = """
[bold cyan]Morning Views TUI - Keyboard Shortcuts[/bold cyan]

[bold]NAVIGATION[/bold]
{'─' * 60}
Arrow Keys / ↑↓  Navigate tables and menus
Enter            Select item / drill down
ESC              Go back to previous screen
Q                Quit (from main menu only)
R                Refresh data (fetch latest from database)
?                Show this help screen

[bold]SCREENS[/bold]
{'─' * 60}
1. Main Menu
   - Press 1: Today's Watchlist
   - Press 2: Search Symbol
   - Press R: Refresh market data
   - Press Q: Quit

2. Watchlist
   - Arrow keys to navigate
   - Enter to view symbol detail
   - Press R: Refresh watchlist

3. Symbol Detail
   - Press 1: OI Timing Analysis
   - Press 2: OI Distribution
   - Press 3: Compare Strikes
   - Press 4: AI Analysis (Claude insights)
   - Press c: Toggle Confluence Score breakdown
   - Press W: Add/Remove from My Watchlist

4. My Watchlist
   - ⚠️  Stale indicator: No alerts in 25+ days or no active alerts
   - 🆕 New Activity badge: Shows count of recent changes
   - Press X: Remove symbol (with confirmation)
   - Press S: Cycle sort modes (Relevance/Date/Alpha)

5. AI Analysis
   - Press Shift+N: Generate new analysis (with confirmation)
   - Press Shift+M: Switch model (Haiku → Sonnet → Opus)
   - Press Shift+A: Add-on analysis (iterative context)
   - First analysis: ~$0.001 (Haiku), cached for 7 days

5. Search
   - Type symbol and press Enter
   - Select from results

[bold]TIPS[/bold]
{'─' * 60}
- Tables are keyboard-navigable (arrow keys)
- All screens support ESC to go back
- Help (?) available on every screen
- Press R to refresh data (Flow Monitor updates every 15 min)
- Keep TUI open all day - data syncs in background

{'─' * 60}
[dim]Press ESC to close this help screen[/dim]
        """
        return help_text.strip()

    def action_back(self) -> None:
        """Close help screen"""
        self.app.pop_screen()
