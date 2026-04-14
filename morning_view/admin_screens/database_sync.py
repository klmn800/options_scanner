"""Database Sync Screen - Sync production to query database"""

import subprocess
import sys
import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal
from textual.widgets import Header, Footer, Static, Button
from textual.screen import Screen
from textual.binding import Binding

logger = logging.getLogger(__name__)


class DatabaseSyncScreen(Screen):
    """Database sync screen - sync production → query database"""

    BINDINGS = [
        Binding("1", "run_full_sync", "Full Sync", show=False),
        Binding("2", "run_quick_sync", "Quick Sync", show=False),
        Binding("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        with VerticalScroll(id="admin-container"):
            yield Static(self._build_menu(), id="admin-menu", classes="admin-mode")
        yield Footer()

    def _build_menu(self) -> str:
        """Build database sync menu"""
        menu_text = f"""
[bold red]ADMIN MODE - Database Sync[/bold red]
[yellow]Sync production database → query database[/yellow]

{"─" * 60}

[bold cyan]Sync Options:[/bold cyan]

   [bold][1][/bold] Full Sync [dim](~14 minutes)[/dim]
        Complete database copy: datalake.db → datalake_query.db
        Use when: Query DB is stale or corrupted

   [bold][2][/bold] Quick Sync [dim](~seconds)[/dim]
        Incremental sync: Only new flow_alerts & flow_options_scans
        Use when: Need latest flow data without full sync overhead

{"─" * 60}

[bold]Current Status:[/bold]

   Production DB: data/datalake.db
   Query DB:      data/datalake_query.db

{"─" * 60}

[dim]Navigate: Press 1 or 2 | ESC: Back[/dim]
        """
        return menu_text.strip()

    def action_run_full_sync(self) -> None:
        """Run full database sync"""
        self._launch_sync("--sync", "--auto", sync_type="Full Sync")

    def action_run_quick_sync(self) -> None:
        """Run quick database sync"""
        self._launch_sync("--quick-sync", sync_type="Quick Sync")

    def _launch_sync(self, *args, sync_type: str) -> None:
        """
        Launch database sync in new terminal window.

        Args:
            *args: Arguments to pass to db_backup.py
            sync_type: Human-readable sync type for notifications
        """
        project_root = Path(__file__).parent.parent.parent
        script_path = project_root / "data" / "health" / "db_backup.py"

        if not script_path.exists():
            self.notify(
                f"❌ Sync script not found:\n   {script_path}",
                severity="error",
                timeout=5
            )
            return

        # Build command for new terminal window
        command = [
            'cmd', '/c', 'start',
            'cmd', '/k',
            sys.executable,
            str(script_path)
        ] + list(args)

        try:
            # Launch detached process
            subprocess.Popen(
                command,
                cwd=str(project_root),
                shell=True  # Required for 'start' command on Windows
            )
            logger.info(f"Launched database sync: {sync_type}")

            self.notify(
                f"✅ {sync_type} started in new terminal window\n\n"
                f"   Switch to that window to monitor progress.\n"
                f"   This can run independently of the TUI.",
                severity="information",
                timeout=8
            )

        except Exception as e:
            logger.error(f"Failed to launch {sync_type}: {e}")
            self.notify(
                f"❌ Failed to launch {sync_type}:\n   {str(e)}",
                severity="error",
                timeout=5
            )

    def action_back(self) -> None:
        """Go back to admin menu"""
        self.app.pop_screen()
