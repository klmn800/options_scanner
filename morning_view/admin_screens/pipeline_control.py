"""Pipeline Control Screen - Manually trigger pipelines"""

import subprocess
import sys
import logging
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Header, Footer, Static
from textual.screen import Screen
from textual.binding import Binding

logger = logging.getLogger(__name__)

# Pipeline definitions
PIPELINES = [
    {
        "id": "ei_weekly",
        "name": "Weekly Refresh",
        "category": "Earnings Intelligence",
        "script": "strategies/earnings_intel/ei_main.py",
        "args": ["--weekly-refresh"],
        "description": "Fetch upcoming earnings, archive old events",
        "runtime": "60-90 min",
        "key": "1"
    },
    {
        "id": "ei_daily",
        "name": "Daily Pipeline",
        "category": "Earnings Intelligence",
        "script": "strategies/earnings_intel/ei_main.py",
        "args": ["--daily-pipeline"],
        "description": "Collect snapshots, calculate moves",
        "runtime": "15-20 min",
        "key": "2"
    },
    {
        "id": "ei_morning",
        "name": "Morning Arbitrage Scan",
        "category": "Earnings Intelligence",
        "script": "strategies/earnings_intel/ei_main.py",
        "args": ["--morning-scan"],
        "description": "Scan for IV discount opportunities",
        "runtime": "1-2 min",
        "key": "3"
    },
    {
        "id": "oid_morning",
        "name": "Morning Analysis",
        "category": "OID Strategy",
        "script": "strategies/oi_delta/oid_main.py",
        "args": ["--oid-morning"],
        "description": "Analyze morning open interest changes",
        "runtime": "5-10 min",
        "key": "4"
    },
    {
        "id": "oid_evening",
        "name": "Evening Operations",
        "category": "OID Strategy",
        "script": "strategies/oi_delta/oid_main.py",
        "args": ["--oid-evening"],
        "description": "Process end-of-day OI data",
        "runtime": "10-15 min",
        "key": "5"
    },
    {
        "id": "fm_run",
        "name": "Run Flow Monitor",
        "category": "Flow Monitor",
        "script": "strategies/flow_monitor/fm_main.py",
        "args": [],
        "description": "Options flow analysis workflow",
        "runtime": "30-60 sec",
        "key": "6"
    },
    {
        "id": "db_sync",
        "name": "Database Sync",
        "category": "System",
        "script": "data/health/db_backup.py",
        "args": ["--sync", "--auto"],
        "description": "Sync production → query database",
        "runtime": "2-5 min",
        "key": "7"
    }
]


def launch_pipeline_in_new_window(pipeline: dict) -> bool:
    """
    Launch pipeline in new terminal window.

    Args:
        pipeline: Pipeline dict with 'script' and 'args'

    Returns:
        True if launched successfully, False otherwise
    """
    project_root = Path(__file__).parent.parent.parent
    script_path = project_root / pipeline['script']

    if not script_path.exists():
        logger.error(f"Pipeline script not found: {script_path}")
        return False

    # Build command for new terminal window
    # Windows: Use 'start cmd /k' to keep window open after completion
    command = [
        'cmd', '/c', 'start',
        'cmd', '/k',
        sys.executable,
        str(script_path)
    ] + pipeline['args']

    try:
        # Launch detached process
        subprocess.Popen(
            command,
            cwd=str(project_root),
            shell=True  # Required for 'start' command on Windows
        )
        logger.info(f"Launched pipeline: {pipeline['name']}")
        return True

    except Exception as e:
        logger.error(f"Failed to launch pipeline {pipeline['name']}: {e}")
        return False


class PipelineControlScreen(Screen):
    """Pipeline control screen - trigger pipelines manually"""

    BINDINGS = [
        Binding("1", "run_pipeline_1", "", show=False),
        Binding("2", "run_pipeline_2", "", show=False),
        Binding("3", "run_pipeline_3", "", show=False),
        Binding("4", "run_pipeline_4", "", show=False),
        Binding("5", "run_pipeline_5", "", show=False),
        Binding("6", "run_pipeline_6", "", show=False),
        Binding("7", "run_pipeline_7", "", show=False),
        Binding("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets"""
        yield Header()
        with VerticalScroll(id="admin-container"):
            yield Static(self._build_menu(), id="admin-menu", classes="admin-mode")
        yield Footer()

    def _build_menu(self) -> str:
        """Build pipeline selection menu"""
        menu_lines = [
            "[bold red]ADMIN MODE - Pipeline Controls[/bold red]",
            "[yellow]Select pipeline to run in new terminal window:[/yellow]",
            "",
            "─" * 60,
            ""
        ]

        # Group by category
        categories = {}
        for pipeline in PIPELINES:
            cat = pipeline['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(pipeline)

        for category, pipes in categories.items():
            menu_lines.append(f"[bold cyan]{category}:[/bold cyan]")
            for pipe in pipes:
                menu_lines.append(f"   [bold][{pipe['key']}][/bold] {pipe['name']} [dim]({pipe['runtime']})[/dim]")
                menu_lines.append(f"        [dim]{pipe['description']}[/dim]")
                menu_lines.append("")

        menu_lines.extend([
            "─" * 60,
            "",
            "[dim]Navigate: Press number keys 1-7 | ESC: Back[/dim]"
        ])

        return "\n".join(menu_lines)

    def _launch_pipeline(self, pipeline_index: int) -> None:
        """Launch pipeline by index"""
        if 0 <= pipeline_index < len(PIPELINES):
            pipeline = PIPELINES[pipeline_index]
            success = launch_pipeline_in_new_window(pipeline)

            if success:
                self.notify(
                    f"✅ Pipeline started in new terminal window:\n   {pipeline['name']}",
                    severity="information",
                    timeout=5
                )
            else:
                self.notify(
                    f"❌ Failed to launch pipeline:\n   {pipeline['name']}",
                    severity="error",
                    timeout=5
                )

    # Action handlers for each pipeline
    def action_run_pipeline_1(self) -> None:
        self._launch_pipeline(0)

    def action_run_pipeline_2(self) -> None:
        self._launch_pipeline(1)

    def action_run_pipeline_3(self) -> None:
        self._launch_pipeline(2)

    def action_run_pipeline_4(self) -> None:
        self._launch_pipeline(3)

    def action_run_pipeline_5(self) -> None:
        self._launch_pipeline(4)

    def action_run_pipeline_6(self) -> None:
        self._launch_pipeline(5)

    def action_run_pipeline_7(self) -> None:
        self._launch_pipeline(6)

    def action_back(self) -> None:
        """Go back to admin menu"""
        self.app.pop_screen()
