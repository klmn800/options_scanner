"""Capital Timeline Screen - Vertical Gantt chart visualization"""

import logging
from datetime import datetime, date, timedelta

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding

from morning_view import capital_planner_data as cpd

logger = logging.getLogger(__name__)


class CapitalTimelineScreen(Screen):
    """Timeline detail view - vertical Gantt chart showing position durations"""

    CSS = """
    CapitalTimelineScreen {
        background: $surface;
    }

    #timeline-container {
        height: 100%;
        padding: 1 2;
    }

    #timeline-content {
        padding: 2;
        background: $surface-darken-1;
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("d", "toggle_granularity", "Daily/Weekly"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self):
        super().__init__()
        self.show_daily = True  # Toggle between daily and weekly view

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        with VerticalScroll(id="timeline-container"):
            yield Static(id="timeline-content")

        yield Footer()

    def on_mount(self) -> None:
        """Build timeline on mount"""
        self._build_timeline()

    def _build_timeline(self) -> None:
        """Build vertical Gantt chart timeline"""
        try:
            # Load data
            positions = cpd.load_positions()
            config = cpd.load_planner_config()

            # Filter to active positions (not closed)
            active_positions = [p for p in positions if p.get("status") != "closed"]

            if not active_positions:
                content = self.query_one("#timeline-content", Static)
                content.update("[bold cyan]Position Timeline - Next 90 Days[/bold cyan]\n\n[dim]No active positions to display[/dim]")
                return

            # Calculate timeline range
            today = date.today()
            timeline_days = 90

            # Find earliest entry and latest exit in positions
            earliest_entry = None
            latest_exit = None

            for pos in active_positions:
                try:
                    entry = date.fromisoformat(pos["entry_date"])
                    exit_date = date.fromisoformat(pos["exit_date"])

                    if earliest_entry is None or entry < earliest_entry:
                        earliest_entry = entry
                    if latest_exit is None or exit_date > latest_exit:
                        latest_exit = exit_date
                except (ValueError, KeyError):
                    continue

            # Use today as start if it's earlier than earliest entry
            start_date = min(today, earliest_entry) if earliest_entry else today
            end_date = latest_exit if latest_exit else (today + timedelta(days=timeline_days))

            # Ensure we show at least 30 days
            if (end_date - start_date).days < 30:
                end_date = start_date + timedelta(days=30)

            # Build timeline text
            timeline_text = self._build_gantt_chart(active_positions, start_date, end_date)

            # Add capital summary
            timeline_text += "\n\n" + self._build_capital_summary(active_positions)

            # Update content
            content = self.query_one("#timeline-content", Static)
            content.update(timeline_text)

        except Exception as e:
            logger.error(f"Error building timeline: {e}")
            content = self.query_one("#timeline-content", Static)
            content.update(f"[red]Error building timeline: {str(e)}[/red]")

    def _build_gantt_chart(self, positions: list[dict], start_date: date, end_date: date) -> str:
        """Build vertical Gantt chart"""
        # Header
        gantt_text = "[bold cyan]Position Timeline - Next 90 Days[/bold cyan]\n"
        granularity = "Daily" if self.show_daily else "Weekly"
        gantt_text += f"[dim]View: {granularity} | Press 'D' to toggle[/dim]\n\n"

        # Calculate timeline width
        total_days = (end_date - start_date).days
        if total_days <= 0:
            return gantt_text + "[dim]No timeline to display[/dim]"

        # Build date markers (every 7 days for readability)
        chart_width = 60  # Characters for the timeline bar
        gantt_text += "Position          "

        # Date markers
        marker_dates = []
        current = start_date
        while current <= end_date:
            marker_dates.append(current)
            current += timedelta(days=7)

        # Build date header
        date_markers = ""
        for marker_date in marker_dates:
            marker_str = marker_date.strftime("%m/%d")
            # Calculate position in chart
            days_from_start = (marker_date - start_date).days
            char_pos = int(days_from_start / total_days * chart_width)

            # Pad to position
            while len(date_markers) < char_pos:
                date_markers += " "
            date_markers += marker_str

        gantt_text += date_markers[:chart_width] + "\n"
        gantt_text += "─" * (17 + chart_width) + "\n"

        # Sort positions by entry date
        sorted_positions = sorted(positions, key=lambda x: x.get("entry_date", ""))

        # Build position rows
        for pos in sorted_positions:
            try:
                symbol = pos["symbol"]
                entry = date.fromisoformat(pos["entry_date"])
                exit_date = date.fromisoformat(pos["exit_date"])
                cost = pos.get("estimated_total_cost", 0)

                # Calculate bar position and length
                entry_days = (entry - start_date).days
                exit_days = (exit_date - start_date).days

                entry_pos = max(0, int(entry_days / total_days * chart_width))
                exit_pos = min(chart_width, int(exit_days / total_days * chart_width))
                bar_length = exit_pos - entry_pos

                # Build bar
                bar = " " * entry_pos + "█" * bar_length

                # Position line
                gantt_text += f"{symbol:8} ${cost:6,.0f} {bar[:chart_width]}\n"

                # Entry/exit labels
                entry_label = f"Entry: {entry.strftime('%m/%d')}"
                exit_label = f"Exit: {exit_date.strftime('%m/%d')}"
                label_line = " " * 17 + " " * entry_pos + entry_label + " " * (bar_length - len(entry_label) - len(exit_label)) + exit_label
                gantt_text += f"[dim]{label_line[:17 + chart_width]}[/dim]\n\n"

            except (ValueError, KeyError) as e:
                logger.error(f"Error rendering position: {e}")
                continue

        gantt_text += "─" * (17 + chart_width) + "\n"

        return gantt_text

    def _build_capital_summary(self, positions: list[dict]) -> str:
        """Build daily capital summary"""
        try:
            # Get timeline data
            timeline = cpd.get_capital_timeline(positions, days_ahead=90)
            config = cpd.load_planner_config()
            total_capital = config.get("capital", {}).get("total_capital", 3000)
            warning_pct = config.get("capital", {}).get("warning_threshold_pct", 80)

            # Build summary
            summary_text = "[bold]Daily Capital Locked:[/bold]\n\n"

            if self.show_daily:
                # Daily view - group by week for readability
                daily = timeline["daily"]
                today = date.today()

                # Show next 4 weeks
                for week in range(4):
                    week_start = today + timedelta(weeks=week)
                    week_end = week_start + timedelta(days=6)

                    summary_text += f"[bold]Week starting {week_start.strftime('%m/%d')}:[/bold]\n"

                    for day_offset in range(7):
                        day = week_start + timedelta(days=day_offset)
                        day_str = day.isoformat()

                        if day_str in daily:
                            amount = daily[day_str]
                            pct = (amount / total_capital * 100) if total_capital > 0 else 0

                            # Build bar
                            bar_length = 20
                            filled = int(pct / 100 * bar_length)
                            bar = "█" * filled + "░" * (bar_length - filled)

                            # Warning indicator
                            warning = " ⚠️" if pct >= warning_pct else ""

                            # Color based on utilization
                            if pct >= warning_pct:
                                day_line = f"[red]{day.strftime('%m/%d %a'):12} {bar} ${amount:5,.0f} ({pct:2.0f}%){warning}[/red]"
                            elif pct >= 50:
                                day_line = f"[yellow]{day.strftime('%m/%d %a'):12} {bar} ${amount:5,.0f} ({pct:2.0f}%)[/yellow]"
                            else:
                                day_line = f"{day.strftime('%m/%d %a'):12} {bar} ${amount:5,.0f} ({pct:2.0f}%)"

                            summary_text += day_line + "\n"

                    summary_text += "\n"

            else:
                # Weekly view
                weekly = timeline["weekly"]
                sorted_weeks = sorted(weekly.keys())[:4]  # First 4 weeks

                for week_key in sorted_weeks:
                    amount = weekly[week_key]
                    pct = (amount / total_capital * 100) if total_capital > 0 else 0

                    # Build bar
                    bar_length = 20
                    filled = int(pct / 100 * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)

                    # Warning indicator
                    warning = " ⚠️" if pct >= warning_pct else ""

                    summary_text += f"{week_key:15} {bar} ${amount:5,.0f} ({pct:2.0f}%){warning}\n"

            # Add peak info
            if timeline["peak_amount"] > 0:
                peak_pct = (timeline["peak_amount"] / total_capital * 100) if total_capital > 0 else 0
                summary_text += f"\n[bold]Peak:[/bold] ${timeline['peak_amount']:,.0f} ({peak_pct:.0f}% of ${total_capital:,.0f}) on {timeline['peak_date']}\n"
                summary_text += f"[bold]Average:[/bold] ${timeline['average']:,.0f}/day\n"

            return summary_text

        except Exception as e:
            logger.error(f"Error building capital summary: {e}")
            return f"[red]Error: {str(e)}[/red]"

    def action_toggle_granularity(self) -> None:
        """Toggle between daily and weekly view"""
        self.show_daily = not self.show_daily
        self._build_timeline()

        granularity = "Daily" if self.show_daily else "Weekly"
        self.notify(f"View: {granularity}", severity="information", timeout=2)

    def action_refresh(self) -> None:
        """Refresh timeline"""
        self.notify("Refreshing...", severity="information", timeout=1)
        self._build_timeline()
        self.notify("✓ Refreshed", severity="information", timeout=2)

    def action_back(self) -> None:
        """Go back to capital planner"""
        self.app.pop_screen()
