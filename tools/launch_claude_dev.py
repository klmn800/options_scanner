#!/usr/bin/env python3
"""
Claude Code Development Launcher
Spawns a new Claude Code window with pre-filled context for TUI development.

Usage:
    python tools/launch_claude_dev.py --file "path/to/file.py" --prompt "Fix the table alignment" --screen "FlowPage"
"""
import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path
import logging

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"claude_dev_launcher_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def build_claude_prompt(file_path: str, user_prompt: str, screen_name: str, log_hint: str) -> str:
    """Build the formatted prompt for Claude Code as natural text."""

    # Simple natural language prompt - Claude is good at parsing blobs of text
    prompt = (
        f"I need help with @{file_path}. "
        f"{user_prompt}. "
        f"This is the {screen_name} screen. "
        f"To reproduce, run python morning_view/mv_main.py and navigate to this screen. "
        f"Check {log_hint} for recent errors."
    )

    return prompt


def launch_claude(file_path: str, user_prompt: str, screen_name: str = "Unknown", log_hint: str = None) -> int:
    """Launch Claude Code in new terminal window with pre-filled context."""

    try:
        # Auto-detect log file hint if not provided
        if not log_hint:
            today = datetime.now().strftime('%Y-%m-%d')
            log_hint = f"logs/morning_view_{today}.log (last 10 minutes)"

        logger.info(f"🚀 Launching Claude Code for development task")
        logger.info(f"   File: {file_path}")
        logger.info(f"   Screen: {screen_name}")
        logger.info(f"   Prompt: {user_prompt}")

        # Build the full prompt
        full_prompt = build_claude_prompt(file_path, user_prompt, screen_name, log_hint)

        # Get current working directory
        cwd = Path.cwd()

        logger.info(f"📝 Full prompt: {full_prompt}")

        # Create a temporary batch file using the exact pattern from start_claude_code.bat
        # Escape quotes in prompt using batch-style: " becomes ""
        batch_escaped_prompt = full_prompt.replace('"', '""')

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
            f.write('@echo off\n')
            f.write(f'cd /d {cwd}\n')
            f.write(f'start "" cmd /k "claude "{batch_escaped_prompt}""\n')
            batch_file = f.name

        logger.info(f"📝 Batch file created: {batch_file}")

        # Execute the batch file
        result = subprocess.run(
            batch_file,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if result.returncode == 0:
            logger.info(f"✅ Claude Code launched successfully")
            return 0
        else:
            logger.error(f"❌ Claude Code launch failed with exit code {result.returncode}")
            if result.stderr:
                logger.error(f"STDERR: {result.stderr}")
            return 1

    except Exception as e:
        logger.error(f"💥 Exception during launch: {type(e).__name__}: {e}", exc_info=True)
        return 1


def main():
    """Entry point for CLI usage."""
    parser = argparse.ArgumentParser(description="Launch Claude Code for TUI development")
    parser.add_argument("--file", required=True, help="File path to edit (e.g., morning_view/pages/flow_page.py)")
    parser.add_argument("--prompt", required=True, help="User's development request")
    parser.add_argument("--screen", default="Unknown", help="Current screen name")
    parser.add_argument("--log-hint", help="Log file hint (auto-detected if not provided)")

    args = parser.parse_args()

    exit_code = launch_claude(
        file_path=args.file,
        user_prompt=args.prompt,
        screen_name=args.screen,
        log_hint=args.log_hint
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
