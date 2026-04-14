"""Capital Planner Main Screen - Plan and track earnings positions"""

import logging
from datetime import datetime, timedelta, date

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
from textual.widgets import Header, Footer, Static, DataTable, Input, Button, Label
from textual.screen import Screen, ModalScreen
from textual.binding import Binding

from morning_view import capital_planner_data as cpd

logger = logging.getLogger(__name__)


class AddPositionModal(ModalScreen):
    """Modal for adding/editing a position"""

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    AddPositionModal {
        align: center middle;
    }

    #modal-dialog {
        width: 80;
        height: auto;
        background: $surface;
        border: thick $accent;
        padding: 1;
    }

    .modal-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }

    .modal-section {
        margin: 0;
    }

    .modal-row {
        height: auto;
        margin: 0;
    }

    .modal-label {
        width: 18;
        padding: 0 1 0 0;
        content-align: right middle;
    }

    .modal-input {
        width: 18;
        margin: 0 1 0 0;
    }

    Input {
        height: 3;
    }

    .modal-hint {
        color: $text-muted;
    }

    #notes-input {
        height: auto;
        min-height: 3;
        width: 1fr;
        margin: 0;
    }

    #button-row {
        margin-top: 1;
    }

    Button {
        margin: 0 1 0 0;
    }

    .calculator-section {
        border: solid $primary;
        padding: 0 1;
        margin: 0;
        height: auto;
    }

    #calc-result {
        height: 1;
        margin: 0;
    }

    .calc-result {
        text-style: bold;
        color: $accent;
    }

    .warning-text {
        color: $warning;
    }
    """

    def __init__(self, position_data: dict = None, earnings_date: str = None, symbol: str = None):
        super().__init__()
        self.position_data = position_data  # For editing
        self.earnings_date = earnings_date  # Pre-fill
        self.symbol = symbol  # Pre-fill
        self.input_fields = {}

    def compose(self) -> ComposeResult:
        """Create modal widgets"""
        is_edit = self.position_data is not None
        title = "Edit Position" if is_edit else "Add Position to Planner"

        with Container(id="modal-dialog"):
            yield Static(f"[bold cyan]{title}[/bold cyan]", classes="modal-title")

            # Symbol and earnings date (on same line to save space)
            with Horizontal(classes="modal-row"):
                yield Label("Symbol:", classes="modal-label")
                symbol_input = Input(
                    value=self.symbol or (self.position_data.get("symbol", "") if is_edit else ""),
                    id="symbol-input",
                    classes="modal-input",
                    disabled=is_edit
                )
                self.input_fields["symbol"] = symbol_input
                yield symbol_input

                yield Label("Earnings:", classes="modal-label")
                earnings_input = Input(
                    value=self.earnings_date or (self.position_data.get("earnings_date", "") if is_edit else ""),
                    id="earnings-input",
                    classes="modal-input",
                    placeholder="YYYY-MM-DD",
                    disabled=is_edit
                )
                self.input_fields["earnings_date"] = earnings_input
                yield earnings_input

            # Entry and exit dates (on same line)
            with Horizontal(classes="modal-row"):
                yield Label("Entry Date:", classes="modal-label")
                entry_input = Input(
                    value=self.position_data.get("entry_date", "") if is_edit else "",
                    id="entry-input",
                    classes="modal-input",
                    placeholder="YYYY-MM-DD"
                )
                self.input_fields["entry_date"] = entry_input
                yield entry_input
                yield Static("T-14", classes="modal-hint", id="entry-hint")

            with Horizontal(classes="modal-row"):
                yield Label("Exit Date:", classes="modal-label")
                exit_input = Input(
                    value=self.position_data.get("exit_date", "") if is_edit else "",
                    id="exit-input",
                    classes="modal-input",
                    placeholder="YYYY-MM-DD"
                )
                self.input_fields["exit_date"] = exit_input
                yield exit_input
                yield Static("T-2", classes="modal-hint", id="exit-hint")

            # Contracts and Price (on same line)
            with Horizontal(classes="modal-row"):
                yield Label("Contracts:", classes="modal-label")
                contracts_input = Input(
                    value=str(self.position_data.get("num_contracts", "")) if is_edit else "",
                    id="contracts-input",
                    classes="modal-input",
                    placeholder="2"
                )
                self.input_fields["num_contracts"] = contracts_input
                yield contracts_input

                yield Label("Price/each:", classes="modal-label")
                price_input = Input(
                    value=str(self.position_data.get("estimated_contract_price", "")) if is_edit else "",
                    id="price-input",
                    classes="modal-input",
                    placeholder="5.50"
                )
                self.input_fields["estimated_contract_price"] = price_input
                yield price_input

            # Calculator result
            yield Static("", id="calc-result")

            # Status and Notes
            with Horizontal(classes="modal-row"):
                yield Label("Status:", classes="modal-label")
                status_input = Input(
                    value=self.position_data.get("status", "planned") if is_edit else "planned",
                    id="status-input",
                    classes="modal-input",
                    placeholder="planned"
                )
                self.input_fields["status"] = status_input
                yield status_input
                yield Static("[dim]planned/watching/entered/closed[/dim]", classes="modal-hint")

            with Horizontal(classes="modal-row"):
                yield Label("Notes (500 char):", classes="modal-label")
                notes_input = Input(
                    value=self.position_data.get("notes", "") if is_edit else "",
                    id="notes-input",
                    placeholder="Thesis, key levels, strategy..."
                )
                self.input_fields["notes"] = notes_input
                yield notes_input

            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Save [S]", id="save-btn", variant="success")
                yield Button("Cancel [ESC]", id="cancel-btn")

    def on_mount(self) -> None:
        """Update calculator on mount"""
        self._update_hints()
        self._update_calculator()

        # Watch for input changes
        for input_widget in self.input_fields.values():
            input_widget.watch_value = True

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update calculator when inputs change"""
        if event.input.id in ["contracts-input", "price-input"]:
            self._update_calculator()
        elif event.input.id == "earnings-input":
            self._update_hints()

    def _update_hints(self) -> None:
        """Update entry/exit date hints based on earnings date"""
        try:
            earnings_str = self.input_fields["earnings_date"].value
            if not earnings_str:
                return

            earnings_date = date.fromisoformat(earnings_str)

            # Load config for defaults
            config = cpd.load_planner_config()
            entry_days = config["defaults"]["default_entry_days_before"]
            exit_days = config["defaults"]["default_exit_days_before"]

            entry_date = earnings_date - timedelta(days=entry_days)
            exit_date = earnings_date - timedelta(days=exit_days)

            # Update hints
            try:
                entry_hint = self.query_one("#entry-hint", Static)
                entry_hint.update(f"(hint: T-{entry_days} = {entry_date.strftime('%m/%d')})")

                exit_hint = self.query_one("#exit-hint", Static)
                exit_hint.update(f"(hint: T-{exit_days} = {exit_date.strftime('%m/%d')})")
            except:
                pass

        except (ValueError, KeyError):
            pass

    def _update_calculator(self) -> None:
        """Update calculator result"""
        try:
            contracts_str = self.input_fields["num_contracts"].value
            price_str = self.input_fields["estimated_contract_price"].value

            if not contracts_str or not price_str:
                return

            contracts = int(contracts_str)
            price = float(price_str)
            # Options contracts are 100 shares each
            total = contracts * price * 100

            # Load target from config
            config = cpd.load_planner_config()
            target = config["capital"]["target_position_size"]

            # Build result string
            result_text = f"[bold]Total Cost: ${total:.0f}[/bold] ({contracts}x @ ${price:.2f} × 100)"
            if total > target * 2:
                result_text += f" [red]⚠️ Way over target (${target})[/red]"
            elif total > target:
                result_text += f" [yellow]⚠️ Over target (${target})[/yellow]"
            else:
                result_text += f" [green]✓ Within target (${target})[/green]"

            calc_result = self.query_one("#calc-result", Static)
            calc_result.update(result_text)

        except (ValueError, KeyError):
            pass

    def _validate_form(self) -> tuple[bool, str]:
        """Validate form inputs"""
        # Required fields
        if not self.input_fields["symbol"].value.strip():
            return False, "Symbol is required"
        if not self.input_fields["earnings_date"].value.strip():
            return False, "Earnings date is required"
        if not self.input_fields["entry_date"].value.strip():
            return False, "Entry date is required"
        if not self.input_fields["exit_date"].value.strip():
            return False, "Exit date is required"

        # Numeric fields
        try:
            contracts = int(self.input_fields["num_contracts"].value)
            if contracts <= 0:
                return False, "Contracts must be positive"
        except ValueError:
            return False, "Contracts must be a number"

        try:
            price = float(self.input_fields["estimated_contract_price"].value)
            if price <= 0:
                return False, "Price must be positive"
        except ValueError:
            return False, "Price must be a number"

        # Date formats
        try:
            date.fromisoformat(self.input_fields["earnings_date"].value)
            date.fromisoformat(self.input_fields["entry_date"].value)
            date.fromisoformat(self.input_fields["exit_date"].value)
        except ValueError:
            return False, "Invalid date format (use YYYY-MM-DD)"

        # Notes length
        notes = self.input_fields.get("notes", Input()).value
        if len(notes) > 500:
            return False, "Notes exceed 500 character limit"

        return True, ""

    def _save_position(self) -> bool:
        """Save position (add or update)"""
        try:
            # Validate
            is_valid, error_msg = self._validate_form()
            if not is_valid:
                self.notify(f"Validation error: {error_msg}", severity="error")
                return False

            # Build position dict
            contracts = int(self.input_fields["num_contracts"].value)
            price = float(self.input_fields["estimated_contract_price"].value)

            position = {
                "symbol": self.input_fields["symbol"].value.strip().upper(),
                "earnings_date": self.input_fields["earnings_date"].value.strip(),
                "entry_date": self.input_fields["entry_date"].value.strip(),
                "exit_date": self.input_fields["exit_date"].value.strip(),
                "num_contracts": contracts,
                "estimated_contract_price": price,
                "estimated_total_cost": contracts * price * 100,  # Options are 100 shares each
                "status": self.input_fields["status"].value.strip() or "planned",
                "notes": self.input_fields["notes"].value.strip()
            }

            # Add or update
            if self.position_data:
                # Update existing
                success = cpd.update_position(self.position_data["id"], position)
                if success:
                    self.notify("✓ Position updated", severity="information")
                else:
                    self.notify("Failed to update position", severity="error")
                    return False
            else:
                # Add new
                position_id = cpd.add_position(position)
                self.notify(f"✓ Position added: {position_id}", severity="information")

            return True

        except Exception as e:
            logger.error(f"Error saving position: {e}")
            self.notify(f"Error: {str(e)}", severity="error")
            return False

    def action_save(self) -> None:
        """Save action via keyboard"""
        if self._save_position():
            self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel action via keyboard"""
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        if event.button.id == "save-btn":
            if self._save_position():
                self.dismiss(True)  # Return True to indicate save
        elif event.button.id == "cancel-btn":
            self.dismiss(False)


class CapitalPlannerScreen(Screen):
    """Capital Planner main screen - hybrid summary + table view"""

    CSS = """
    CapitalPlannerScreen {
        background: $surface;
    }

    #planner-container {
        height: 100%;
        padding: 1 2;
    }

    #planner-header {
        padding: 1 2;
        background: $panel;
        border: solid $primary;
        margin-bottom: 1;
    }

    #capital-summary {
        padding: 1 2;
        background: $surface-darken-1;
        border: solid $primary;
        margin-bottom: 1;
    }

    #positions-table {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
    }

    DataTable {
        height: 100%;
        min-height: 10;
    }

    DataTable > .datatable--header {
        background: $boost;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: $accent;
    }

    DataTable:focus > .datatable--cursor {
        background: $accent-darken-2;
    }
    """

    BINDINGS = [
        Binding("a", "add_position", "Add Position", show=True),
        Binding("enter", "view_position", "View Details", show=True),
        Binding("e", "edit_position", "Edit", show=True),
        Binding("d", "delete_position", "Delete", show=True),
        Binding("v", "view_timeline", "Timeline", show=True),
        Binding("f", "filter_status", "Filter", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.positions = []
        self.filter_status = "all"  # all, planned, watching, entered

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()

        with VerticalScroll(id="planner-container"):
            yield Static(id="planner-header")
            yield Static(id="capital-summary")
            yield DataTable(id="positions-table", zebra_stripes=True, cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize screen"""
        self._load_data()
        self._build_ui()
        # Set focus to table so arrow keys work
        table = self.query_one("#positions-table", DataTable)
        table.focus()

    def _load_data(self) -> None:
        """Load positions and config"""
        try:
            self.positions = cpd.load_positions()
            self.config = cpd.load_planner_config()
            logger.info(f"Loaded {len(self.positions)} positions")
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self.notify(f"Error loading data: {str(e)}", severity="error")
            self.positions = []
            self.config = {}

    def _build_ui(self) -> None:
        """Build all UI elements"""
        self._build_header()
        self._build_summary()
        self._build_table()

    def _build_header(self) -> None:
        """Build header section"""
        # Filter positions by status
        if self.filter_status == "all":
            filtered = self.positions
        else:
            filtered = [p for p in self.positions if p.get("status") == self.filter_status]

        filter_text = f" (filtered: {self.filter_status})" if self.filter_status != "all" else ""

        header_text = f"""[bold cyan]Capital Planner - {len(filtered)} Position{'s' if len(filtered) != 1 else ''} Planned[/bold cyan]{filter_text}

[dim]Press 'A' to add | 'E' to edit | 'D' to delete | 'V' for timeline | 'F' to filter | 'R' to refresh[/dim]"""

        header = self.query_one("#planner-header", Static)
        header.update(header_text)

    def _build_summary(self) -> None:
        """Build capital summary section with weekly bars"""
        try:
            # Get timeline
            timeline = cpd.get_capital_timeline(self.positions, days_ahead=28)  # 4 weeks
            weekly = timeline["weekly"]
            total_capital = self.config.get("capital", {}).get("total_capital", 3000)
            warning_pct = self.config.get("capital", {}).get("warning_threshold_pct", 80)

            # Build summary text
            summary_text = "[bold]Capital Summary (Next 4 Weeks)[/bold]\n\n"
            summary_text += "Week Starting    Deployed                   Positions\n"
            summary_text += "─" * 65 + "\n"

            # Get sorted weeks
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

                # Get positions for this week (simplified)
                # TODO: Show actual position symbols
                summary_text += f"{week_key:15} {bar} ${amount:5,.0f} ({pct:2.0f}%){warning}\n"

            # Peak info
            if timeline["peak_amount"] > 0:
                peak_pct = (timeline["peak_amount"] / total_capital * 100) if total_capital > 0 else 0
                summary_text += "\n"
                summary_text += f"[bold]Peak Week:[/bold] ${timeline['peak_amount']:,.0f} ({peak_pct:.0f}% of ${total_capital:,.0f})\n"

            summary = self.query_one("#capital-summary", Static)
            summary.update(summary_text)

        except Exception as e:
            logger.error(f"Error building summary: {e}")
            summary = self.query_one("#capital-summary", Static)
            summary.update(f"[red]Error building summary: {str(e)}[/red]")

    def _build_table(self) -> None:
        """Build positions table"""
        try:
            table = self.query_one("#positions-table", DataTable)
            table.clear(columns=True)

            # Add columns with explicit width
            table.add_column("Symbol", key="symbol", width=8)
            table.add_column("Entry", key="entry", width=10)
            table.add_column("Exit", key="exit", width=10)
            table.add_column("Days", key="days", width=5)
            table.add_column("Cost", key="cost", width=8)
            table.add_column("Status", key="status", width=10)
            table.add_column("Notes", key="notes", width=30)

            # Filter positions
            if self.filter_status == "all":
                filtered = self.positions
            else:
                filtered = [p for p in self.positions if p.get("status") == self.filter_status]

            # Sort by entry date
            filtered.sort(key=lambda x: x.get("entry_date", ""))

            # Add rows
            for pos in filtered:
                # Calculate days
                try:
                    entry = date.fromisoformat(pos["entry_date"])
                    exit_date = date.fromisoformat(pos["exit_date"])
                    days = (exit_date - entry).days
                except (ValueError, KeyError):
                    days = 0

                # Format dates
                try:
                    entry_dt = datetime.fromisoformat(pos["entry_date"])
                    entry_str = entry_dt.strftime("%m/%d %a")
                except (ValueError, KeyError):
                    entry_str = pos.get("entry_date", "?")

                try:
                    exit_dt = datetime.fromisoformat(pos["exit_date"])
                    exit_str = exit_dt.strftime("%m/%d %a")
                except (ValueError, KeyError):
                    exit_str = pos.get("exit_date", "?")

                # Truncate notes
                notes = pos.get("notes", "")
                if len(notes) > 38:
                    notes = notes[:35] + "..."

                table.add_row(
                    pos["symbol"],
                    entry_str,
                    exit_str,
                    str(days),
                    f"${pos.get('estimated_total_cost', 0):.0f}",
                    pos.get("status", ""),
                    notes,
                    key=pos["id"]
                )

        except Exception as e:
            logger.error(f"Error building table: {e}")
            self.notify(f"Error building table: {str(e)}", severity="error")

    def _get_selected_position(self) -> dict:
        """Get currently selected position"""
        table = self.query_one("#positions-table", DataTable)
        if table.cursor_row >= 0:
            # Filter positions same way as table
            if self.filter_status == "all":
                filtered = self.positions
            else:
                filtered = [p for p in self.positions if p.get("status") == self.filter_status]

            filtered.sort(key=lambda x: x.get("entry_date", ""))

            if table.cursor_row < len(filtered):
                return filtered[table.cursor_row]
        return None

    def action_view_position(self) -> None:
        """View position details"""
        position = self._get_selected_position()
        if not position:
            self.notify("No position selected", severity="warning")
            return

        # Build detail view
        notes = position.get("notes", "No notes")
        if len(notes) > 300:
            notes = notes[:300] + "..."

        detail_text = f"""[bold cyan]{position['symbol']} Position Details[/bold cyan]

[bold]Dates:[/bold]
  Earnings: {position['earnings_date']}
  Entry: {position['entry_date']}
  Exit: {position['exit_date']}

[bold]Position:[/bold]
  Contracts: {position['num_contracts']}
  Price/each: ${position['estimated_contract_price']:.2f}
  Total Cost: ${position['estimated_total_cost']:.0f}
  Status: {position['status']}

[bold]Notes:[/bold]
{notes}

[dim]Press ESC to close | Press E to edit[/dim]"""

        # Use a simple modal to show details
        from textual.widgets import Label
        from textual.screen import ModalScreen
        from textual.containers import Container

        class PositionDetailModal(ModalScreen):
            CSS = """
            PositionDetailModal {
                align: center middle;
            }
            #detail-dialog {
                width: 80;
                height: auto;
                background: $surface;
                border: thick $accent;
                padding: 2;
            }
            """

            BINDINGS = [
                Binding("escape", "dismiss_modal", "Close", show=False),
            ]

            def __init__(self, parent_screen):
                super().__init__()
                self.parent_screen = parent_screen

            def compose(self) -> ComposeResult:
                with Container(id="detail-dialog"):
                    yield Static(detail_text)

            def action_dismiss_modal(self) -> None:
                """Dismiss just the modal, not parent screen"""
                self.dismiss()

        self.app.push_screen(PositionDetailModal(self))

    def action_add_position(self) -> None:
        """Add new position"""
        self.app.push_screen(AddPositionModal(), callback=self._handle_modal_result)

    def action_edit_position(self) -> None:
        """Edit selected position"""
        position = self._get_selected_position()
        if not position:
            self.notify("No position selected", severity="warning")
            return

        self.app.push_screen(AddPositionModal(position_data=position), callback=self._handle_modal_result)

    def _handle_modal_result(self, result) -> None:
        """Handle result from add/edit modal"""
        if result:  # If saved
            self._load_data()
            self._build_ui()
        # Restore focus to table
        table = self.query_one("#positions-table", DataTable)
        table.focus()

    def action_delete_position(self) -> None:
        """Delete selected position"""
        position = self._get_selected_position()
        if not position:
            self.notify("No position selected", severity="warning")
            return

        # Confirm deletion (simple notification for now)
        success = cpd.delete_position(position["id"])
        if success:
            self.notify(f"✓ Deleted position: {position['symbol']}", severity="information")
            self._load_data()
            self._build_ui()
        else:
            self.notify("Failed to delete position", severity="error")

    def action_view_timeline(self) -> None:
        """View timeline detail (Gantt chart)"""
        from morning_view.screens.capital_timeline import CapitalTimelineScreen
        self.app.push_screen(CapitalTimelineScreen())

    def action_filter_status(self) -> None:
        """Cycle through status filters"""
        filters = ["all", "planned", "watching", "entered"]
        current_idx = filters.index(self.filter_status)
        next_idx = (current_idx + 1) % len(filters)
        self.filter_status = filters[next_idx]

        self._build_ui()
        self.notify(f"Filter: {self.filter_status}", severity="information", timeout=2)

    def action_refresh(self) -> None:
        """Refresh data"""
        self.notify("Refreshing...", severity="information", timeout=1)
        self._load_data()
        self._build_ui()
        self.notify("✓ Refreshed", severity="information", timeout=2)

    def action_back(self) -> None:
        """Go back to main menu"""
        self.app.pop_screen()
