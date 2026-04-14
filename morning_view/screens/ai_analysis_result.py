"""AI Analysis Result Screen - Display AI recommendations from discovery analysis"""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding
from textual import events


class AIAnalysisResultScreen(Screen):
    """Display AI analysis results with scrollable content"""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close", show=False),
        Binding("f", "force_refresh", "Force Refresh", show=False),
    ]

    def __init__(self, analysis_text: str, raw_result: dict = None, parent_screen = None):
        """Initialize with formatted analysis text

        Args:
            analysis_text: Pre-formatted text from format_analysis_for_display()
            raw_result: Optional raw analysis result dict for debugging
            parent_screen: Reference to parent screen (Discovery) for refresh callback
        """
        super().__init__()
        self.analysis_text = analysis_text
        self.raw_result = raw_result
        self.parent_screen = parent_screen

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        yield Container(
            VerticalScroll(
                Static(self.analysis_text, id="analysis-content"),
                id="analysis-scroll"
            ),
            id="analysis-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Focus scroll container on mount"""
        try:
            scroll = self.query_one("#analysis-scroll", VerticalScroll)
            scroll.focus()
        except:
            pass

    def action_close(self) -> None:
        """Close the analysis screen"""
        self.app.pop_screen()

    def action_force_refresh(self) -> None:
        """Force refresh the AI analysis"""
        # Close this screen first
        self.app.pop_screen()

        # Trigger force refresh on parent Discovery screen
        if self.parent_screen:
            self.parent_screen._run_ai_analysis(force_refresh=True)

    def on_key(self, event: events.Key) -> None:
        """Handle additional key bindings"""
        if event.key == "escape" or event.key == "q":
            self.action_close()
