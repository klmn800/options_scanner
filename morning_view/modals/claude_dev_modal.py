"""
Claude Dev Modal - Quick prompt entry for spawning Claude Code development sessions
"""
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static, Input
from textual.screen import ModalScreen
from textual.binding import Binding
from pathlib import Path
import subprocess
import sys


class ClaudeDevModal(ModalScreen):
    """Modal for entering Claude Code development prompt."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", show=False),
    ]

    CSS = """
    ClaudeDevModal {
        align: center middle;
    }

    #dialog {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        width: 100%;
        text-style: bold;
        color: $accent;
    }

    #detected-context {
        width: 100%;
        color: $text-muted;
        padding: 0;
        margin: 1 0 0 0;
    }

    #prompt-input {
        width: 100%;
        margin: 1 0;
        border: solid $primary;
    }

    #prompt-input:focus {
        border: solid $accent;
    }

    #controls-hint {
        width: 100%;
        color: $text-muted;
        text-align: center;
        margin: 0;
    }
    """

    def __init__(self, current_screen_name: str, current_file_path: str):
        """
        Initialize modal with detected context.

        Args:
            current_screen_name: Display name of current screen (e.g., "Flow Alerts")
            current_file_path: Relative path to screen's Python file (e.g., "morning_view/screens/flow_alerts.py")
        """
        super().__init__()
        self.current_screen_name = current_screen_name
        self.current_file_path = current_file_path

    def compose(self) -> ComposeResult:
        """Build modal UI."""
        detected_text = f"""Screen: {self.current_screen_name}
File: {self.current_file_path}"""

        yield Container(
            Vertical(
                Static("Edit Page With Claude", id="dialog-title"),
                Static(detected_text, id="detected-context"),
                Input(
                    placeholder="What do you want to fix/change?",
                    id="prompt-input"
                ),
                Static("[dim][Enter: Launch | ESC: Cancel][/dim]", id="controls-hint"),
                id="dialog"
            )
        )

    def on_mount(self) -> None:
        """Focus the input field when modal opens."""
        self.query_one("#prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input field."""
        if event.input.id == "prompt-input":
            self._launch_claude()

    def action_dismiss(self) -> None:
        """Handle ESC key to dismiss modal."""
        self.dismiss(None)

    def _today(self) -> str:
        """Get today's date string for log file hint."""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d')

    def _launch_claude(self) -> None:
        """Launch Claude Code with the entered prompt."""
        prompt_input = self.query_one("#prompt-input", Input)
        user_prompt = prompt_input.value.strip()

        if not user_prompt:
            self.app.notify("❌ Please enter a prompt", severity="error", timeout=3)
            return

        try:
            # Build launcher command
            launcher_path = Path(__file__).parent.parent.parent / "tools" / "launch_claude_dev.py"

            cmd = [
                sys.executable,
                str(launcher_path),
                "--file", self.current_file_path,
                "--prompt", user_prompt,
                "--screen", self.current_screen_name,
            ]

            # Launch in background (non-blocking)
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            self.app.notify("🚀 Claude Code launching in new window...", severity="information", timeout=3)
            self.dismiss(user_prompt)  # Return the prompt to caller

        except Exception as e:
            self.app.notify(f"❌ Launch failed: {e}", severity="error", timeout=5)
            self.dismiss(None)
