#!/usr/bin/env python3
"""
Strategic Advisor Launcher
===========================
Spawns a Claude Code session for the Strategic Advisor in a visible window.

The advisor reads the system, queries databases, and produces strategic
recommendations. It writes ONLY to its own workspace (strategic_advisor/).

Usage:
    python strategic_advisor/launcher.py              # Launch in visible window
    python strategic_advisor/launcher.py --headless   # Run headless (no window)

Author: Ben (with Claude)
Date: 2026-04-17
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Project root is parent of this script's directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Configure UTF-8 encoding for Windows compatibility (MANDATORY)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Paths
PROMPT_FILE = PROJECT_ROOT / 'strategic_advisor' / 'PROMPT.md'
REVIEWS_DIR = PROJECT_ROOT / 'strategic_advisor' / 'reviews'
MEMORY_DIR = PROJECT_ROOT / 'strategic_advisor' / 'memory'


def get_session_number():
    """Determine the next session number from existing reviews and journal."""
    # Check reviews for highest numbered file
    max_num = 0
    if REVIEWS_DIR.exists():
        for f in REVIEWS_DIR.glob('*.md'):
            name = f.stem
            # Extract leading number from filenames like "003_feedback-loop-design"
            parts = name.split('_', 1)
            if parts[0].isdigit():
                max_num = max(max_num, int(parts[0]))

    # Also check journal for session references
    journal = MEMORY_DIR / 'journal.md'
    if journal.exists():
        import re
        text = journal.read_text(encoding='utf-8')
        # Find "Session NNN" patterns
        for match in re.finditer(r'Session\s+(\d+)', text):
            max_num = max(max_num, int(match.group(1)))

    return max_num + 1


def spawn_visible(prompt_file):
    """Spawn Claude Code in a visible window.

    Args:
        prompt_file: Path to the prompt file

    Returns:
        bool: True if spawned successfully
    """
    claude_path = shutil.which('claude')
    if not claude_path:
        print("ERROR: 'claude' command not found in PATH")
        return False

    print(f"Found claude at: {claude_path}")

    # Create batch file to spawn visible window
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write(f'cd /d {PROJECT_ROOT}\n')
        f.write('echo ================================================\n')
        f.write('echo  Strategic Advisor Session Starting...\n')
        f.write('echo ================================================\n')
        f.write('echo.\n')
        f.write(f'claude --permission-mode bypassPermissions @{prompt_file}\n')
        batch_file = f.name

    print(f"Launching Claude Code in new window...")

    # Use start to open in a new window
    result = subprocess.run(
        f'start "Strategic Advisor" cmd /k "{batch_file}"',
        shell=True,
        cwd=str(PROJECT_ROOT)
    )

    if result.returncode == 0:
        print("Claude Code launched successfully")
        return True
    else:
        print(f"Failed to launch (exit code {result.returncode})")
        return False


def spawn_headless(prompt_file):
    """Spawn Claude Code headless (no window, captures output).

    Args:
        prompt_file: Path to the prompt file

    Returns:
        tuple: (success: bool, output: str)
    """
    claude_path = shutil.which('claude')
    if not claude_path:
        print("ERROR: 'claude' command not found in PATH")
        return False, ""

    print("Running Strategic Advisor headless (this may take several minutes)...")

    prompt_text = Path(prompt_file).read_text(encoding='utf-8')

    result = subprocess.run(
        [claude_path, '-p', '--dangerously-skip-permissions'],
        input=prompt_text,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=1800,  # 30 minute timeout
        cwd=str(PROJECT_ROOT)
    )

    if result.returncode == 0:
        print("Strategic Advisor session completed successfully")
        return True, result.stdout
    else:
        print(f"Session failed (exit code {result.returncode})")
        if result.stderr:
            print(f"stderr: {result.stderr[:500]}")
        return False, result.stdout


def main():
    parser = argparse.ArgumentParser(
        description='Strategic Advisor — Launch an autonomous analysis session'
    )
    parser.add_argument('--headless', action='store_true',
                        help='Run headless (no visible window)')

    args = parser.parse_args()

    # Verify prompt exists
    if not PROMPT_FILE.exists():
        print(f"ERROR: Prompt file not found: {PROMPT_FILE}")
        return

    # Ensure workspace directories exist
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEWS_DIR / 'feedback').mkdir(exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    (MEMORY_DIR / 'observations').mkdir(exist_ok=True)

    session_num = get_session_number()

    # Build session prompt: date context + main prompt
    # Date injection prevents Claude's day-of-week confusion
    now = datetime.now()
    date_header = (
        f"**Today is {now.strftime('%A, %B %d, %Y')}. "
        f"Day of week: {now.strftime('%A')}. "
        f"This is a fact, not an estimate.**\n\n"
    )

    prompt_text = date_header + PROMPT_FILE.read_text(encoding='utf-8')

    # Write combined prompt to temp file
    session_prompt = PROJECT_ROOT / 'strategic_advisor' / f'.session_prompt.md'
    session_prompt.write_text(prompt_text, encoding='utf-8')

    print(f"{'=' * 50}")
    print(f"  Strategic Advisor — Session {session_num:03d}")
    print(f"  {now.strftime('%A, %B %d, %Y %I:%M %p')}")
    print(f"{'=' * 50}")
    print(f"  Prompt: {PROMPT_FILE}")
    print(f"  Workspace: {MEMORY_DIR.parent}")
    print(f"  Reviews: {REVIEWS_DIR}")
    print()

    if args.headless:
        success, output = spawn_headless(session_prompt)
        if output:
            print(f"\n{'=' * 50}")
            print("Session Output:")
            print(f"{'=' * 50}")
            print(output[-2000:] if len(output) > 2000 else output)
    else:
        success = spawn_visible(session_prompt)
        if success:
            print("Watch the Claude Code window for progress.")
            print(f"Proposals will appear in: {REVIEWS_DIR}")


if __name__ == '__main__':
    main()
