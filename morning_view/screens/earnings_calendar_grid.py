"""Earnings Calendar Screen - CSS Grid Version (cleaner, structured layout)"""

from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.widgets import Header, Footer, Static, Label
from textual.screen import Screen
from textual.binding import Binding
from datetime import datetime, timedelta

from morning_view.tui_data import get_data


def get_next_trading_days(start_date: datetime, num_days: int = 10):
    """Get next N trading days (excluding weekends)"""
    trading_days = []
    current = start_date

    while len(trading_days) < num_days:
        # Skip weekends (5=Sat, 6=Sun)
        if current.weekday() < 5:
            trading_days.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    return trading_days


# Sector emoji mapping
SECTOR_EMOJI = {
    'Financial Services': '🏦',
    'Banks': '🏦',
    'Healthcare': '🏥',
    'Technology': '💻',
    'Communication Services': '📱',
    'Consumer Cyclical': '🍕',
    'Consumer Defensive': '🛒',
    'Industrials': '⚙️',
    'Energy': '⛽',
    'Utilities': '💡',
    'Real Estate': '🏢',
    'Basic Materials': '🏗️',
    'Airlines': '✈️',
    'Automotive': '🚗',
    'Semiconductors': '💾',
    'Restaurants': '🍕',
    'Retail': '🛍️',
    'Transportation': '🚚',
    'Media': '📺',
    'Software': '☁️',
    'Biotechnology': '💊',
    'Pharmaceuticals': '💊',
    'Insurance': '📋',
}


def get_sector_emoji(sector: str, industry: str = None) -> str:
    """Get emoji for sector/industry, with fallback logic"""
    if not sector:
        return '📊'

    if sector in SECTOR_EMOJI:
        return SECTOR_EMOJI[sector]

    if industry and industry in SECTOR_EMOJI:
        return SECTOR_EMOJI[industry]

    sector_lower = sector.lower()
    for key, emoji in SECTOR_EMOJI.items():
        if key.lower() in sector_lower or sector_lower in key.lower():
            return emoji

    return '📊'


class DayCell(Static):
    """Individual day cell widget - focusable and interactive"""

    DEFAULT_CSS = """
    DayCell {
        width: 25;
        height: 15;
        border: solid $primary;
        padding: 1;
        overflow: hidden;
    }

    DayCell:focus {
        background: $boost;
        border: thick $accent;
    }

    DayCell .day-header {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    DayCell .earnings-item {
        margin-left: 1;
    }

    DayCell .earnings-item-strong-buy {
        color: $success;
        text-style: bold;
    }

    DayCell .earnings-item-buy {
        color: $success;
    }

    DayCell .earnings-item-watch {
        color: $warning;
    }

    DayCell .count-summary {
        color: $text-muted;
        margin-top: 1;
        text-style: italic;
    }

    DayCell .overflow-indicator {
        color: $text-muted;
        text-style: dim;
    }
    """

    def __init__(self, date_str: str, earnings_list: list, **kwargs):
        super().__init__(**kwargs)
        self.date_str = date_str
        self.earnings_list = earnings_list
        self.can_focus = True  # Make focusable for navigation

    def render(self) -> str:
        """Render day cell content"""
        dt = datetime.strptime(self.date_str, '%Y-%m-%d')
        day_name = dt.strftime('%a')
        day_month = dt.strftime('%m/%d')

        # Header
        lines = [f"[bold]{day_name} {day_month}[/bold]"]
        lines.append("─" * 15)

        # Show up to 5 earnings
        max_display = 5
        for idx, earnings in enumerate(self.earnings_list[:max_display]):
            symbol = earnings['symbol']
            sector = earnings.get('sector', '')
            industry = earnings.get('industry', '')
            emoji = get_sector_emoji(sector, industry)
            signal = earnings.get('earnings_play_signal', 'NEUTRAL')

            # Color based on signal
            if signal == 'STRONG BUY':
                lines.append(f"[bold green]{emoji} {symbol}[/bold green]")
            elif signal == 'BUY':
                lines.append(f"[green]{emoji} {symbol}[/green]")
            elif signal == 'WATCH':
                lines.append(f"[yellow]{emoji} {symbol}[/yellow]")
            else:
                lines.append(f"{emoji} {symbol}")

        # Overflow indicator
        overflow_count = len(self.earnings_list) - max_display
        if overflow_count > 0:
            lines.append(f"[dim]...+{overflow_count} more[/dim]")

        # Count summary
        lines.append("")
        if len(self.earnings_list) == 0:
            lines.append("[dim](no earnings)[/dim]")
        else:
            lines.append(f"[dim]{len(self.earnings_list)} earnings[/dim]")

        return "\n".join(lines)

    def on_click(self) -> None:
        """Handle click - open day detail"""
        self.screen.action_select_day(self.date_str, self.earnings_list)


class EarningsCalendarGridScreen(Screen):
    """Earnings calendar - CSS Grid version with proper structure"""

    CSS = """
    EarningsCalendarGridScreen {
        background: $surface;
    }

    #calendar-scroll {
        height: 100%;
        overflow-y: auto;
    }

    #calendar-info {
        dock: top;
        height: auto;
        padding: 1 2;
        background: $panel;
        color: $text;
    }

    #calendar-grid {
        layout: grid;
        grid-size: 5;  /* 5 columns = Mon-Fri */
        grid-gutter: 1 1;
        padding: 2;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("left", "navigate_left", "← Prev", show=True),
        Binding("right", "navigate_right", "→ Next", show=True),
        Binding("up", "navigate_up", "↑ Up", show=True),
        Binding("down", "navigate_down", "↓ Down", show=True),
        Binding("enter", "select_focused_day", "View Details", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("escape", "back", "Back", show=True),
        Binding("?", "help", "Help", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.earnings_by_date = {}
        self.sorted_dates = []
        self.day_cells = []  # Track cell widgets

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        with VerticalScroll(id="calendar-scroll"):
            yield Static(id="calendar-info")
            yield Grid(id="calendar-grid")

        yield Footer()

    def on_mount(self) -> None:
        """Load data and build grid on mount"""
        self._build_calendar()

    def _build_calendar(self) -> None:
        """Build calendar grid with day cells"""
        data = get_data()

        # Generate next 20 trading days
        today = datetime.now()
        trading_days = get_next_trading_days(today, num_days=20)
        last_day = trading_days[-1]

        # Get earnings data
        all_earnings = data.get_earnings_calendar(end_date=last_day, tradeable_only=False)

        # Filter to tradeable earnings
        self.earnings_by_date = {}
        for date_str in trading_days:
            earnings_list = all_earnings.get(date_str, [])
            tradeable = [
                e for e in earnings_list
                if e.get('close_price') and e.get('total_open_interest') and
                   e['close_price'] <= data.max_underlying_price and
                   e['total_open_interest'] >= data.min_open_interest
            ]
            self.earnings_by_date[date_str] = tradeable

        self.sorted_dates = trading_days

        # Update info panel
        total_tradeable = sum(len(self.earnings_by_date[d]) for d in trading_days)
        info_text = (
            f"[bold cyan]Earnings Calendar - Next 4 Weeks (20 Trading Days)[/bold cyan] "
            f"[dim]({total_tradeable} tradeable)[/dim]\n"
            f"[dim]Filters: <${data.max_underlying_price:.0f} price, {data.min_open_interest}+ OI | "
            f"Arrow keys navigate, ENTER for details[/dim]"
        )
        self.query_one("#calendar-info", Static).update(info_text)

        # Build grid cells
        grid = self.query_one("#calendar-grid", Grid)
        grid.remove_children()  # Clear existing cells
        self.day_cells = []

        for date_str in trading_days:
            earnings_list = self.earnings_by_date[date_str]
            cell = DayCell(date_str, earnings_list)
            grid.mount(cell)
            self.day_cells.append(cell)

        # Focus first cell
        if self.day_cells:
            self.day_cells[0].focus()

    def action_navigate_left(self) -> None:
        """Navigate to previous day"""
        focused = self.focused
        if focused and isinstance(focused, DayCell):
            try:
                current_idx = self.day_cells.index(focused)
                if current_idx > 0:
                    self.day_cells[current_idx - 1].focus()
            except ValueError:
                pass

    def action_navigate_right(self) -> None:
        """Navigate to next day"""
        focused = self.focused
        if focused and isinstance(focused, DayCell):
            try:
                current_idx = self.day_cells.index(focused)
                if current_idx < len(self.day_cells) - 1:
                    self.day_cells[current_idx + 1].focus()
            except ValueError:
                pass

    def action_navigate_up(self) -> None:
        """Navigate up one week (5 days)"""
        focused = self.focused
        if focused and isinstance(focused, DayCell):
            try:
                current_idx = self.day_cells.index(focused)
                target_idx = current_idx - 5
                if target_idx >= 0:
                    self.day_cells[target_idx].focus()
            except ValueError:
                pass

    def action_navigate_down(self) -> None:
        """Navigate down one week (5 days)"""
        focused = self.focused
        if focused and isinstance(focused, DayCell):
            try:
                current_idx = self.day_cells.index(focused)
                target_idx = current_idx + 5
                if target_idx < len(self.day_cells):
                    self.day_cells[target_idx].focus()
            except ValueError:
                pass

    def action_select_focused_day(self) -> None:
        """Open day detail for currently focused cell"""
        focused = self.focused
        if focused and isinstance(focused, DayCell):
            self.action_select_day(focused.date_str, focused.earnings_list)

    def action_select_day(self, date_str: str, earnings_list: list) -> None:
        """Open day detail screen"""
        if not earnings_list:
            self.notify("No tradeable earnings on this day", severity="warning", timeout=2)
            return

        from morning_view.screens.earnings_day_detail import EarningsDayDetailScreen
        self.app.push_screen(EarningsDayDetailScreen(date_str, earnings_list))

    def action_refresh(self) -> None:
        """Refresh calendar data"""
        try:
            self._build_calendar()
            self.notify("✅ Calendar refreshed", severity="information", timeout=2)
        except Exception as e:
            self.notify(f"❌ Refresh failed: {e}", severity="error")

    def action_back(self) -> None:
        """Go back to main menu"""
        self.app.pop_screen()

    def action_help(self) -> None:
        """Show help"""
        from morning_view.screens.help import HelpScreen
        self.app.push_screen(HelpScreen())
