"""AI Council Screen - Multi-advisor analysis system"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input
from textual.screen import Screen
from textual.binding import Binding
from textual import events

from morning_view import ai_council
from morning_view.tui_data import get_data


class AICouncilScreen(Screen):
    """AI Council - Multi-advisor analysis system"""

    BINDINGS = [
        Binding("1", "ask_advisor_1", "[1] General", show=True),
        Binding("2", "ask_advisor_2", "[2] Detective", show=True),
        Binding("3", "ask_advisor_3", "[3] Risk", show=True),
        Binding("4", "ask_advisor_4", "[4] Catalyst", show=True),
        Binding("space", "query_all", "[Space] All", show=True),
        Binding("5", "full_synthesis", "[5] Synthesis", show=True),
        Binding("a", "add_query", "Query", show=True),
        Binding("r", "remove_advisor", "Remove", show=True),
        Binding("c", "clear_analysis", "Clear", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
        self.council = ai_council.CouncilManager()

    def compose(self) -> ComposeResult:
        """Create 4-column layout for advisors"""
        yield Header()
        yield Horizontal(
            ScrollableContainer(Static("", id="advisor-1"), id="column-1"),
            ScrollableContainer(Static("", id="advisor-2"), id="column-2"),
            ScrollableContainer(Static("", id="advisor-3"), id="column-3"),
            ScrollableContainer(Static("", id="advisor-4"), id="column-4"),
            id="council-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize advisor columns and load cached analyses"""
        # Load cached analyses for each advisor (if any exist < 7 days old)
        self._load_cached_analyses()

        # Update column displays
        for i in range(1, 5):
            self._update_advisor_column(i)

    def _load_cached_analyses(self) -> None:
        """Load cached analyses from database for this symbol"""
        for advisor_id in range(1, 5):
            advisor = self.council.get_advisor(advisor_id)
            if not advisor:
                continue

            # Load all analyses from symbol_ai_council table (supports multiple analyses per day)
            advisor._load_from_db(self.symbol)

    def _update_advisor_column(self, advisor_id: int) -> None:
        """Update advisor column display

        Args:
            advisor_id: Advisor ID (1-4)
        """
        advisor = self.council.get_advisor(advisor_id)
        if not advisor:
            return

        content = self.query_one(f"#advisor-{advisor_id}", Static)

        # Build column header
        header = f"[bold cyan]{advisor.name}[/bold cyan]\n"
        header += f"[dim]{advisor.role}[/dim]\n"
        header += f"{'─' * 30}\n\n"

        # Add analyses if any
        if advisor.analysis_history:
            analyses_text = ""
            for idx, analysis in enumerate(advisor.analysis_history):
                analyses_text += f"[bold]Analysis {idx + 1}[/bold]\n"
                analyses_text += f"{analysis['text']}\n\n"
                analyses_text += f"[dim]Cost: ${analysis['usage']['cost_usd']:.4f}[/dim]\n"
                analyses_text += f"{'─' * 30}\n\n"

            # Footer with total cost
            footer = f"[yellow]Total Cost: ${advisor.get_total_cost():.4f}[/yellow]\n"
            footer += f"[dim]{advisor.get_analysis_count()} Ask{'s' if advisor.get_analysis_count() != 1 else ''}[/dim]"

            display_text = header + analyses_text + footer
        else:
            # Empty state
            display_text = header + f"[dim]Press [{advisor_id}] to consult this advisor[/dim]"

        content.update(display_text)

    def action_ask_advisor_1(self) -> None:
        """Ask advisor 1 (General Analyst)"""
        self._ask_advisor(1)

    def action_ask_advisor_2(self) -> None:
        """Ask advisor 2 (Advanced Detective)"""
        self._ask_advisor(2)

    def action_ask_advisor_3(self) -> None:
        """Ask advisor 3 (Risk Analyst)"""
        self._ask_advisor(3)

    def action_ask_advisor_4(self) -> None:
        """Ask advisor 4 (Catalyst Hunter)"""
        self._ask_advisor(4)

    def action_query_all(self) -> None:
        """Query all 4 advisors sequentially"""
        # Calculate total cost
        total_cost = sum(advisor.cost_estimate for advisor in self.council.advisors)

        self.app.push_screen(
            QueryAllConfirmDialog(self.symbol, total_cost),
            self._handle_query_all_confirmation
        )

    def _handle_query_all_confirmation(self, confirmed: bool) -> None:
        """Handle query all confirmation"""
        if not confirmed:
            return

        # Query each advisor sequentially
        total_cost = 0.0
        for advisor_id in range(1, 5):
            try:
                # Show loading state
                content = self.query_one(f"#advisor-{advisor_id}", Static)
                advisor = self.council.get_advisor(advisor_id)

                loading_text = f"[bold cyan]{advisor.name}[/bold cyan]\n"
                loading_text += f"[dim]{advisor.role}[/dim]\n"
                loading_text += f"{'─' * 30}\n\n"
                loading_text += f"⏳ Analyzing {self.symbol}...\n\n[dim]Querying all advisors...[/dim]"
                content.update(loading_text)
                self.refresh()

                # Query advisor
                analysis_text, usage = self.council.query_advisor(advisor_id, self.symbol)
                total_cost += usage['cost_usd']

                # Update column
                self._update_advisor_column(advisor_id)

            except Exception as e:
                self.notify(f"❌ {advisor.name} failed: {e}", severity="error")
                self._update_advisor_column(advisor_id)

        # Final notification
        self.notify(f"✅ All advisors complete | Total: ${total_cost:.4f}", severity="information", timeout=5)

    def _ask_advisor(self, advisor_id: int) -> None:
        """Show confirmation and ask advisor

        Args:
            advisor_id: Advisor ID (1-4)
        """
        advisor = self.council.get_advisor(advisor_id)
        if not advisor:
            return

        self.app.push_screen(
            AdvisorConfirmDialog(self.symbol, advisor),
            lambda confirmed: self._handle_advisor_confirmation(advisor_id, confirmed)
        )

    def _handle_advisor_confirmation(self, advisor_id: int, confirmed: bool) -> None:
        """Handle advisor confirmation

        Args:
            advisor_id: Advisor ID (1-4)
            confirmed: Whether user confirmed
        """
        if not confirmed:
            return

        try:
            # Show loading state
            content = self.query_one(f"#advisor-{advisor_id}", Static)
            advisor = self.council.get_advisor(advisor_id)

            loading_text = f"[bold cyan]{advisor.name}[/bold cyan]\n"
            loading_text += f"[dim]{advisor.role}[/dim]\n"
            loading_text += f"{'─' * 30}\n\n"
            loading_text += f"⏳ Analyzing {self.symbol}...\n\n[dim]This may take 2-3 seconds...[/dim]"
            content.update(loading_text)
            self.refresh()

            # Query advisor
            analysis_text, usage = self.council.query_advisor(advisor_id, self.symbol)

            # Update column
            self._update_advisor_column(advisor_id)

            # Notify
            self.notify(f"✅ {advisor.name} analysis complete | ${usage['cost_usd']:.4f}", severity="information", timeout=3)

        except Exception as e:
            self.notify(f"❌ Analysis failed: {e}", severity="error")
            self._update_advisor_column(advisor_id)

    def action_full_synthesis(self) -> None:
        """Open full synthesis screen"""
        # Check if any advisors have analyses
        has_analyses = any(adv.analysis_history for adv in self.council.advisors)
        if not has_analyses:
            self.notify("No advisor analyses available. Consult advisors first (press 1-4)", severity="warning")
            return

        self.app.push_screen(FullSynthesisScreen(self.symbol, self.council))

    def action_add_query(self) -> None:
        """Add user context/query"""
        self.app.push_screen(
            UserContextDialog(self.council.user_context),
            self._handle_context_update
        )

    def _handle_context_update(self, new_context: Optional[str]) -> None:
        """Handle user context update

        Args:
            new_context: New context string or None to clear
        """
        if new_context is not None:
            self.council.set_user_context(new_context)
            if new_context:
                self.notify(f"✅ User context set: {new_context[:50]}...", severity="information")
            else:
                self.notify("✅ User context cleared", severity="information")

    def action_remove_advisor(self) -> None:
        """Remove advisor analysis"""
        self.app.push_screen(
            RemoveAdvisorDialog(),
            self._handle_remove_advisor
        )

    def _handle_remove_advisor(self, advisor_id: Optional[int]) -> None:
        """Handle remove advisor

        Args:
            advisor_id: Advisor ID to remove or None
        """
        if advisor_id is not None:
            self.council.remove_advisor_history(advisor_id)
            self._update_advisor_column(advisor_id)
            self.notify(f"✅ Cleared advisor {advisor_id} analysis", severity="information")

    def action_clear_analysis(self) -> None:
        """Clear all analyses and delete cache"""
        import sqlite3
        from pathlib import Path

        try:
            # Clear in-memory analyses
            for advisor in self.council.advisors:
                advisor.analysis_history = []

            # Delete cache records from database
            cache_db = Path(__file__).parent.parent.parent / 'data' / 'analysis_cache.db'
            conn = sqlite3.connect(str(cache_db))
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM advisor_analysis_cache
                WHERE symbol = ?
            """, (self.symbol,))

            rows_deleted = cursor.rowcount
            conn.commit()
            conn.close()

            # Update all columns
            for i in range(1, 5):
                self._update_advisor_column(i)

            if rows_deleted > 0:
                self.notify(f"✅ Cleared {rows_deleted} cached analyses for {self.symbol}", severity="information")
            else:
                self.notify(f"✅ Analyses cleared (no cache to delete)", severity="information")

        except Exception as e:
            self.notify(f"❌ Error clearing analyses: {e}", severity="error")

    def action_back(self) -> None:
        """Return to symbol detail"""
        self.app.pop_screen()


class AdvisorConfirmDialog(Screen):
    """Confirmation dialog for advisor query"""

    def __init__(self, symbol: str, advisor: ai_council.Advisor):
        super().__init__()
        self.symbol = symbol
        self.advisor = advisor

    def compose(self) -> ComposeResult:
        """Create dialog widgets"""
        dialog_text = f"""
[bold cyan]Consult {self.advisor.name}?[/bold cyan]

Symbol: [bold]{self.symbol}[/bold]
Role: [dim]{self.advisor.role}[/dim]
Model: [bold]{self.advisor.provider}/{self.advisor.model}[/bold]
Estimated Cost: [yellow]~${self.advisor.cost_estimate:.4f}[/yellow]

Press [bold green]Y[/bold green] to consult or [bold red]N[/bold red] to cancel
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


class UserContextDialog(Screen):
    """Dialog for adding user context"""

    def __init__(self, current_context: str = ""):
        super().__init__()
        self.current_context = current_context

    def compose(self) -> ComposeResult:
        """Create dialog widgets"""
        yield Container(
            Static("[bold cyan]Add User Context/Focus[/bold cyan]\n\n[dim]Add focus or question for all analyses (leave empty to clear):[/dim]", id="dialog-title"),
            Input(value=self.current_context, placeholder="e.g., Focus on gamma exposure and IV crush risk", id="context-input"),
            Static("\n[dim]Press [bold]Enter[/bold] to save or [bold]ESC[/bold] to cancel[/dim]", id="dialog-help"),
            id="dialog-container"
        )

    def on_mount(self) -> None:
        """Focus input on mount"""
        self.query_one("#context-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        self.dismiss(event.value)

    def on_key(self, event: events.Key) -> None:
        """Handle escape key"""
        if event.key == "escape":
            self.dismiss(None)


class QueryAllConfirmDialog(Screen):
    """Confirmation dialog for querying all advisors"""

    def __init__(self, symbol: str, total_cost: float):
        super().__init__()
        self.symbol = symbol
        self.total_cost = total_cost

    def compose(self) -> ComposeResult:
        """Create dialog widgets"""
        dialog_text = f"""
[bold cyan]Query All 4 Advisors?[/bold cyan]

Symbol: [bold]{self.symbol}[/bold]
Total Estimated Cost: [yellow]~${self.total_cost:.4f}[/yellow]

Will consult:
  1. General Analyst (Haiku)
  2. Advanced Detective (Sonnet)
  3. Risk Analyst (GPT-4o-mini)
  4. Catalyst Hunter (Grok-2)

Press [bold green]Y[/bold green] to proceed or [bold red]N[/bold red] to cancel
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


class RemoveAdvisorDialog(Screen):
    """Dialog for removing advisor analysis"""

    def compose(self) -> ComposeResult:
        """Create dialog widgets"""
        dialog_text = """
[bold cyan]Remove Advisor Analysis[/bold cyan]

Press [bold]1-4[/bold] to remove that advisor's analysis
Press [bold]ESC[/bold] to cancel
        """

        yield Container(
            Static(dialog_text.strip(), id="dialog-content"),
            id="dialog-container"
        )

    def on_key(self, event: events.Key) -> None:
        """Handle key press"""
        if event.key in ["1", "2", "3", "4"]:
            self.dismiss(int(event.key))
        elif event.key == "escape":
            self.dismiss(None)


class FullSynthesisScreen(Screen):
    """Full synthesis from all advisors"""

    BINDINGS = [
        Binding("A", "addon_synthesis", "Add-On", show=True),
        Binding("m", "switch_model", "Model", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(self, symbol: str, council: ai_council.CouncilManager):
        super().__init__()
        self.symbol = symbol
        self.council = council
        self.model = 'sonnet'  # Default synthesis model
        self.synthesis_result = None
        self.synthesis_history = []  # Track all syntheses in this session

    def compose(self) -> ComposeResult:
        """Create synthesis view"""
        yield Header()
        yield ScrollableContainer(
            Static("", id="synthesis-content"),
            Static("", id="synthesis-status", classes="status-bar"),
            id="synthesis-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Load cached syntheses and display"""
        self._load_cached_syntheses()

        if self.synthesis_history:
            self._display_synthesis()
        else:
            self._show_blank_state()

    def _load_cached_syntheses(self) -> None:
        """Load all cached syntheses from database for today"""
        import json
        import sqlite3
        from pathlib import Path
        from tools.timezone_utils import now_eastern

        # Get database path (go up 3 levels: screens -> morning_view -> project_root)
        cache_db = Path(__file__).parent.parent.parent / 'data' / 'analysis_cache.db'
        trade_date = now_eastern().strftime('%Y-%m-%d')

        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Load all syntheses for this symbol from today
        cursor.execute(
            "SELECT synthesis FROM symbol_ai_council WHERE symbol = ? AND trade_date = ?",
            (self.symbol, trade_date)
        )
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            # Parse JSON array and load all syntheses
            syntheses = json.loads(row[0])
            for synth in syntheses:
                # Reconstruct synthesis entry with usage dict
                synthesis_entry = {
                    'text': synth['text'],
                    'timestamp': synth['timestamp'],
                    'model': synth.get('model', 'unknown'),
                    'usage': {
                        'cost_usd': 0.0  # Cost not stored per synthesis in DB
                    }
                }
                self.synthesis_history.append(synthesis_entry)

            # Set the latest one as the result
            if self.synthesis_history:
                self.synthesis_result = self.synthesis_history[-1]

    def _show_blank_state(self) -> None:
        """Show blank state with synthesis prompt"""
        content = self.query_one("#synthesis-content", Static)

        # Count advisor analyses
        advisor_summaries = []
        for advisor in self.council.advisors:
            if advisor.analysis_history:
                advisor_summaries.append(f"  • {advisor.name}: {advisor.get_analysis_count()} analysis(es)")

        summaries_text = "\n".join(advisor_summaries) if advisor_summaries else "  [dim]No advisor analyses[/dim]"

        blank_text = f"""
[bold cyan]═══ {self.symbol} - Full Synthesis ═══[/bold cyan]

[bold]Available Advisor Analyses:[/bold]
{summaries_text}

[bold]Current Synthesis Model:[/bold] {self.model.upper()}

[dim]Press [bold]ENTER[/bold] or [bold]SPACE[/bold] to generate synthesis[/dim]
[dim]Press [bold]M[/bold] to switch model (Sonnet/Opus/Gemini)[/dim]

[yellow]Note:[/yellow] Once generated, synthesis is shared with all advisors as consensus context.
Advisors can see this synthesis but not each other's raw analyses.

[yellow]Synthesis Cost Estimates:[/yellow]
  • Sonnet: ~$0.01 (high quality)
  • Opus: ~$0.04 (premium)
  • Gemini Pro: ~$0.01 (massive context)
        """

        content.update(blank_text.strip())
        self._update_status_bar()

    def _display_synthesis(self) -> None:
        """Display all synthesis results"""
        if not self.synthesis_history:
            return

        content = self.query_one("#synthesis-content", Static)

        # Build header
        header = f"[bold cyan]═══ {self.symbol} - Chief Strategist Synthesis ═══[/bold cyan]\n\n"
        header += f"[dim]ℹ This synthesis is shared with all advisors as consensus context[/dim]\n\n"

        # Show user context if set
        if self.council.user_context:
            header += f"[yellow]User Focus:[/yellow] {self.council.user_context}\n\n"

        # Display all syntheses
        display_parts = [header]

        for idx, synth in enumerate(self.synthesis_history):
            display_parts.append(f"Synthesis {idx + 1}")
            display_parts.append(synth['text'])
            display_parts.append(f"\n[dim]Cost: ${synth['usage']['cost_usd']:.4f}[/dim]")
            display_parts.append(f"{'─' * 70}\n")

        # Add cost footer
        cost_footer = self._build_cost_footer()
        display_parts.append(cost_footer)

        content.update("\n".join(display_parts))
        self._update_status_bar()

    def _build_cost_footer(self) -> str:
        """Build cost footer"""
        if not self.synthesis_result:
            return ""

        result = self.synthesis_result
        cost = result['usage']['cost_usd']

        # Calculate total session cost (council + syntheses)
        council_cost = self.council.get_total_cost()
        synthesis_cost = sum(s['usage']['cost_usd'] for s in self.synthesis_history)
        total_cost = council_cost + synthesis_cost

        footer = f"""
{'─' * 70}
[yellow]This Synthesis: ${cost:.4f}[/yellow]
[dim]Session Total (Council + Syntheses): ${total_cost:.4f}[/dim]
        """

        return footer.strip()

    def _update_status_bar(self) -> None:
        """Update status bar"""
        status = self.query_one("#synthesis-status", Static)

        if self.synthesis_result:
            cost = self.synthesis_result['usage']['cost_usd']
            status_text = (
                f"[bold]{self.symbol}[/bold] | "
                f"Model: {self.model.upper()} | "
                f"Cost: ${cost:.4f} | "
                f"[dim]A:Add-On M:Model ESC:Back[/dim]"
            )
        else:
            status_text = (
                f"[bold]{self.symbol}[/bold] | "
                f"Model: {self.model.upper()} | "
                f"[dim]SPACE/ENTER:Synthesize M:Model ESC:Back[/dim]"
            )

        status.update(status_text)

    def _run_synthesis(self) -> None:
        """Execute synthesis"""
        try:
            content = self.query_one("#synthesis-content", Static)

            # Show loading
            loading_text = f"[bold cyan]═══ {self.symbol} - Chief Strategist Synthesis ═══[/bold cyan]\n\n"
            loading_text += f"⏳ Synthesizing {len([a for a in self.council.advisors if a.analysis_history])} advisor perspectives...\n\n"
            loading_text += f"[dim]Model: {self.model.upper()}[/dim]\n"
            loading_text += f"[dim]This may take 3-5 seconds...[/dim]"

            content.update(loading_text)
            self.refresh()

            # Run synthesis
            synthesis_text, usage = self.council.synthesize(self.symbol, self.model)

            # Store result
            self.synthesis_result = {
                'text': synthesis_text,
                'usage': usage,
                'model': self.model
            }

            self.synthesis_history.append(self.synthesis_result)

            # Display
            self._display_synthesis()

            # Notify
            self.notify(f"✅ Synthesis complete | ${usage['cost_usd']:.4f}", severity="information", timeout=3)

        except Exception as e:
            content = self.query_one("#synthesis-content", Static)
            content.update(f"[red]❌ Synthesis failed: {e}[/red]")
            self.notify(f"❌ Synthesis failed: {e}", severity="error")

    def action_addon_synthesis(self) -> None:
        """Run add-on synthesis"""
        if not self.synthesis_result:
            self.notify("No existing synthesis. Press SPACE to create initial synthesis.", severity="warning")
            return

        # Just run another synthesis (council already has iterative context)
        self._run_synthesis()

    def action_switch_model(self) -> None:
        """Cycle through synthesis models"""
        models = ['sonnet', 'opus', 'gemini-pro']
        current_idx = models.index(self.model)
        next_idx = (current_idx + 1) % len(models)
        self.model = models[next_idx]

        # Update display
        if self.synthesis_result:
            self._update_status_bar()
        else:
            self._show_blank_state()

        self.notify(f"Switched to {self.model.upper()}", severity="information", timeout=2)

    def on_key(self, event: events.Key) -> None:
        """Handle space/enter for synthesis"""
        if event.key in ["space", "enter"] and not self.synthesis_result:
            self._run_synthesis()

    def action_back(self) -> None:
        """Return to council"""
        self.app.pop_screen()


