"""
Admin Screen Helper Functions - Style 1 Patterns

Reusable components for building keyboard-first admin TUI screens.
"""

from typing import Optional, List, Tuple
from textual.widgets import Static, Input, Select
from textual.containers import Horizontal


def create_form_row(label: str, widget) -> Horizontal:
    """
    Create a form row with label and widget.

    Usage:
        row = create_form_row("Symbol:", Input(placeholder="NVDA", id="symbol-input"))
        container.mount(row)
        # Then populate the row
        row.mount(
            Static(f"{label} ", classes="form-label"),
            widget
        )

    Better approach: Just mount everything directly to container in proper order.
    """
    pass  # Not used - see helper pattern below


def format_status(message: str, success: Optional[bool] = None) -> str:
    """
    Format status message with color coding.

    Args:
        message: Status message text
        success: True (green check), False (red X), None (neutral)

    Returns:
        Formatted status string with markup
    """
    if success is True:
        return f"[green]✓ {message}[/green]"
    elif success is False:
        return f"[red]✗ {message}[/red]"
    else:
        return message


def build_info_block(title: str, data: dict) -> Static:
    """
    Build formatted info display block.

    Args:
        title: Block title
        data: Dictionary of label:value pairs

    Returns:
        Static widget with formatted text
    """
    lines = [f"[yellow]{title}:[/yellow]\n"]
    for label, value in data.items():
        lines.append(f"[bold]{label}:[/bold] {value}")

    return Static("\n".join(lines))


class NavigationStack:
    """
    Simple navigation stack for managing screen hierarchy.

    Tracks which sub-screen you're on for context-aware back behavior.
    """

    def __init__(self):
        self._stack: List[str] = []

    def push(self, screen_name: str):
        """Enter a sub-screen"""
        self._stack.append(screen_name)

    def pop(self) -> Optional[str]:
        """Exit current sub-screen, return previous"""
        return self._stack.pop() if self._stack else None

    def current(self) -> Optional[str]:
        """Get current screen name"""
        return self._stack[-1] if self._stack else None

    def clear(self):
        """Clear entire stack (return to main menu)"""
        self._stack.clear()

    def in_subscreen(self) -> bool:
        """Are we in a sub-screen?"""
        return len(self._stack) > 0


# Hotkey hint templates
HINTS = {
    'main_menu': "[dim]See footer for available hotkeys[/dim]",
    'lookup': "[dim]ENTER or L=Lookup | ESC=Back[/dim]",
    'save': "[dim]S=Save | ESC=Cancel[/dim]",
    'estimate': "[dim]ENTER or E=Estimate | ESC=Cancel[/dim]",
    'create': "[dim]ENTER or C=Create | ESC=Cancel[/dim]",
    'refresh': "[dim]R=Refresh | ESC=Back[/dim]",
    'confirm': "[dim]M=Execute | ESC=Cancel[/dim]",
    'yes_no': "[dim]Y=Yes | N=No | ESC=Skip[/dim]",
}


def get_hint(hint_type: str) -> str:
    """Get standard hotkey hint for screen type"""
    return HINTS.get(hint_type, "[dim]ESC=Back | Q=Quit[/dim]")
