"""Trading Journal Screen - Add/edit earnings trade notes"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Static, Input, TextArea, RadioButton, RadioSet
from textual.screen import Screen
from textual.binding import Binding
from textual.validation import Function

from morning_view.admin_data import lookup_earnings_event, append_journal_note

logger = logging.getLogger(__name__)


class TradingJournalScreen(Screen):
    """Trading journal screen - log notes for earnings trades"""

    BINDINGS = [
        Binding("q", "request_quit", "Quit", show=True),
        Binding("escape", "back", "Back", show=True),
        Binding("l", "lookup", "Lookup", show=True),
        Binding("a", "append", "Append", show=False),
        Binding("o", "overwrite", "Overwrite", show=False),
        Binding("c", "create", "Create", show=False),
        Binding("s", "save", "Save", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.current_event: Optional[Dict] = None
        self.form_data: Dict = {}

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        with VerticalScroll(id="admin-container"):
            with Container(id="journal-main", classes="admin-mode"):
                yield Static("[bold red]ADMIN MODE - Trading Journal[/bold red]", classes="admin-header")
                yield Container(id="journal-content")
                yield Static("", id="status-bar", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize with lookup form"""
        self._show_lookup_form()

    def _show_lookup_form(self) -> None:
        """Show Step 1: Symbol/date lookup form"""
        container = self.query_one("#journal-content", Container)
        container.remove_children()

        # Create form rows
        row1 = Horizontal(classes="form-row")
        row2 = Horizontal(classes="form-row")

        container.mount(
            Static("[yellow]Find or create earnings event:[/yellow]\n"),
            Static("[dim]Note: Proof of concept. earnings_events table only has historical data through 2025-09-25.[/dim]\n"),
            row1,
            row2
        )

        # Add controls to rows
        row1.mount(
            Static("Symbol: ", classes="form-label"),
            Input(
                placeholder="NVDA",
                id="symbol-input",
                validators=[Function(self._validate_symbol, "Invalid symbol format")]
            )
        )

        row2.mount(
            Static("Date: ", classes="form-label"),
            Input(
                placeholder="2025-02-26",
                id="date-input",
                validators=[Function(self._validate_date, "Invalid date format (YYYY-MM-DD)")]
            )
        )

        self._update_status("[dim]L=Lookup | ESC=Back[/dim]")

    def _validate_symbol(self, value: str) -> bool:
        """Validate symbol format (1-5 uppercase letters)"""
        return bool(re.match(r'^[A-Z]{1,5}$', value.upper()))

    def _validate_date(self, value: str) -> bool:
        """Validate date format (YYYY-MM-DD)"""
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _update_status(self, message: str, success: Optional[bool] = None) -> None:
        """Update status bar with message"""
        status = self.query_one("#status-bar", Static)
        if success is True:
            status.update(f"[green]✓ {message}[/green]")
        elif success is False:
            status.update(f"[red]✗ {message}[/red]")
        else:
            status.update(message)

    async def _do_lookup(self) -> None:
        """Perform event lookup"""
        try:
            symbol_input = self.query_one("#symbol-input", Input)
            date_input = self.query_one("#date-input", Input)

            symbol = symbol_input.value.upper().strip()
            date = date_input.value.strip()

            # Validate
            if not symbol or not date:
                self._update_status("Error: Symbol and date are required", success=False)
                return

            if not self._validate_symbol(symbol):
                self._update_status("Error: Invalid symbol format (1-5 letters)", success=False)
                return

            if not self._validate_date(date):
                self._update_status("Error: Invalid date format (YYYY-MM-DD)", success=False)
                return

            # Lookup event
            self._update_status("Searching...")
            event = lookup_earnings_event(symbol, date)

            if event:
                self.current_event = event
                self._show_event_found()
            else:
                self.current_event = None
                self.form_data = {'symbol': symbol, 'earnings_date': date}
                self._show_event_not_found(symbol, date)

        except Exception as e:
            logger.error(f"Lookup error: {e}")
            self._update_status(f"Error: {str(e)}", success=False)

    def _show_event_found(self) -> None:
        """Show Step 2a: Event found with existing notes"""
        container = self.query_one("#journal-content", Container)
        container.remove_children()

        event = self.current_event
        notes = event.get('notes') or "(No notes yet)"
        notes_len = len(event.get('notes') or "")

        container.mount(
            Static(f"[bold green]Event Found:[/bold green] {event['symbol']} - {event['earnings_date']}\n"),
            Static(f"Earnings Date: {event['earnings_date']} | "
                        f"Estimated EPS: {event.get('estimated_eps') or 'N/A'} | "
                        f"Actual EPS: {event.get('actual_eps') or 'N/A'}\n"),
            Static(f"\n[bold]Existing Notes[/bold] ({notes_len} chars):"),
            Static(f"[dim]{notes}[/dim]\n", id="existing-notes")
        )

        self._update_status("[dim]A=Append | O=Overwrite | ESC=Back[/dim]")

    def _show_event_not_found(self, symbol: str, date: str) -> None:
        """Show Step 2b: Event not found, offer to create"""
        container = self.query_one("#journal-content", Container)
        container.remove_children()

        container.mount(
            Static(f"[yellow]No event found for {symbol} on {date}[/yellow]\n"),
            Static("[yellow]⚠️  This will create a new earnings event stub[/yellow]\n")
        )

        self._update_status("[dim]C=Create & Continue | ESC=Back[/dim]")

    def _show_note_form(self, append_mode: bool) -> None:
        """Show Step 3: Note entry form"""
        container = self.query_one("#journal-content", Container)
        container.remove_children()

        symbol = self.current_event['symbol'] if self.current_event else self.form_data.get('symbol', '')
        date = self.current_event['earnings_date'] if self.current_event else self.form_data.get('earnings_date', '')

        mode_text = "Append" if append_mode else "New"
        self.form_data['append_mode'] = append_mode

        # Create radiosets
        type_radioset = RadioSet(id="note-type")
        sentiment_radioset = RadioSet(id="sentiment")

        # Mount form widgets
        widgets = [
            Static(f"[bold red]{mode_text} Note:[/bold red] {symbol} {date}\n"),
            Static("\n[bold]Type:[/bold]"),
            type_radioset,
            Static("\n[bold]Sentiment:[/bold]"),
            sentiment_radioset,
            Static("\n[bold]Tags[/bold] (comma-separated, lowercase):"),
            Input(placeholder="iv-crush, tech-sympathy, earnings-beat", id="tags-input"),
            Static("\n[bold]Notes:[/bold]"),
            TextArea("", id="notes-textarea", language="markdown")
        ]

        if append_mode:
            widgets.append(Static("\n[dim](Note will be appended with timestamp separator)[/dim]"))

        container.mount(*widgets)

        # Mount children to radiosets
        type_radioset.mount(
            RadioButton("Trade", value=True),
            RadioButton("Observation"),
            RadioButton("Pattern"),
            RadioButton("Lesson")
        )

        sentiment_radioset.mount(
            RadioButton("Bullish"),
            RadioButton("Bearish", value=True),
            RadioButton("Neutral")
        )

        self._update_status(f"[dim]S=Save {mode_text} | ESC=Cancel[/dim]")

    async def _save_note(self) -> None:
        """Save note to database"""
        try:
            # Get form values
            note_type_radio = self.query_one("#note-type", RadioSet)
            sentiment_radio = self.query_one("#sentiment", RadioSet)
            tags_input = self.query_one("#tags-input", Input)
            notes_textarea = self.query_one("#notes-textarea", TextArea)

            # Get selected values
            note_type = str(note_type_radio.pressed_button.label) if note_type_radio.pressed_button else "Trade"
            sentiment = str(sentiment_radio.pressed_button.label) if sentiment_radio.pressed_button else "Neutral"
            tags = tags_input.value.strip().lower()
            notes = notes_textarea.text.strip()

            # Validate
            if not notes:
                self._update_status("Error: Notes field is required", success=False)
                return

            # Prepare note data
            symbol = self.current_event['symbol'] if self.current_event else self.form_data.get('symbol')
            date = self.current_event['earnings_date'] if self.current_event else self.form_data.get('earnings_date')

            note_data = {
                'notes': notes,
                'tags': tags,
                'note_type': note_type,
                'sentiment': sentiment
            }

            # Save to database
            self._update_status("Saving...")
            success, message = append_journal_note(symbol, date, note_data)

            if success:
                self._update_status(message, success=True)
                self.notify(f"✓ {message}", severity="information", timeout=3)
                self.app.pop_screen()  # Return to admin menu
            else:
                self._update_status(f"Error: {message}", success=False)

        except Exception as e:
            logger.error(f"Save error: {e}")
            self._update_status(f"Error: {str(e)}", success=False)

    async def action_lookup(self) -> None:
        """Trigger lookup with L key"""
        if self.query("#symbol-input"):
            await self._do_lookup()

    def action_append(self) -> None:
        """Trigger append with A key"""
        if self.current_event:
            self._show_note_form(append_mode=True)

    def action_overwrite(self) -> None:
        """Trigger overwrite with O key"""
        if self.current_event:
            self._show_note_form(append_mode=False)

    def action_create(self) -> None:
        """Trigger create with C key"""
        if self.form_data.get('symbol') and self.form_data.get('earnings_date'):
            self._show_note_form(append_mode=False)

    async def action_save(self) -> None:
        """Trigger save with S key"""
        if self.query("#notes-textarea"):
            await self._save_note()

    def action_back(self) -> None:
        """Go back to previous screen or admin menu"""
        # If we're in note form, go back to lookup
        if self.query("#notes-textarea"):
            self._show_lookup_form()
        else:
            self.app.pop_screen()
