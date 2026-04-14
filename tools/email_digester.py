"""
Email Knowledge Digester
========================
Reads unread emails from klmn800alerts@gmail.com and spawns a Claude Code
session to extract and save relevant knowledge to the memory system.

Flow:
1. Fetch unread emails via GmailReader
2. Save email content to temp files
3. Build a prompt referencing the emails + digest instructions
4. Spawn Claude Code in a visible window (like autofix)
5. Claude reads, extracts knowledge, writes to memory/knowledge/
6. Mark processed emails as read after spawn

Usage:
    python tools/email_digester.py                  # Process all unread
    python tools/email_digester.py --label newsletters  # Only labeled messages
    python tools/email_digester.py --dry-run        # Show what would be processed
    python tools/email_digester.py --headless       # Run with -p (no window)
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure UTF-8 encoding for Windows compatibility (MANDATORY)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from tools.email_reader import GmailReader
from tools.timezone_utils import now_eastern

# Paths
KNOWLEDGE_DIR = PROJECT_ROOT / 'memory' / 'knowledge'
DIGEST_INSTRUCTIONS = PROJECT_ROOT / 'memory' / 'DIGEST_INSTRUCTIONS.md'
LOGS_DIR = PROJECT_ROOT / 'logs'


def fetch_emails(label_filter=None, max_count=20):
    """Fetch unread emails and return list of message dicts with full content."""
    reader = GmailReader()
    unread = reader.get_unread(max_results=max_count, label_filter=label_filter)

    if not unread:
        return [], reader

    messages = []
    for msg_meta in unread:
        msg = reader.get_message(msg_meta['id'])
        messages.append(msg)

    return messages, reader


def save_emails_to_temp(messages):
    """Save email messages to temp directory as markdown files.

    Returns:
        Path to temp directory containing the email files.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix='email_digest_'))

    for i, msg in enumerate(messages, 1):
        # Build clean filename
        subject_clean = "".join(c if c.isalnum() or c in ' -_' else '' for c in msg['subject'][:60]).strip()
        subject_clean = subject_clean.replace(' ', '_') or 'no_subject'
        filename = f"{i:02d}_{subject_clean}.md"

        content = f"# {msg['subject']}\n\n"
        content += f"- **From:** {msg['from']}\n"
        content += f"- **To:** {msg['to']}\n"
        content += f"- **Date:** {msg['date']}\n"
        content += f"- **Message ID:** {msg['id']}\n\n"
        content += "---\n\n"
        content += msg['body']

        filepath = temp_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    return temp_dir


def build_prompt(temp_dir, email_count):
    """Build the prompt for the Claude Code digest session."""
    # List the email files
    email_files = sorted(temp_dir.glob('*.md'))
    file_list = '\n'.join(f'- @{f}' for f in email_files)

    prompt = (
        f"TASK: Digest {email_count} email(s) into the knowledge base.\n\n"
        f"INSTRUCTIONS: Read @{DIGEST_INSTRUCTIONS} for full protocol.\n\n"
        f"EMAILS TO PROCESS:\n{file_list}\n\n"
        f"KNOWLEDGE DIRECTORY: {KNOWLEDGE_DIR}\n\n"
        f"Read each email file listed above. For each one, extract useful knowledge "
        f"and save it to the appropriate topic file in the knowledge directory, "
        f"following the instructions. Skip emails with no useful content. "
        f"When finished, print a summary of what you saved."
    )

    return prompt


def spawn_claude_visible(prompt_file):
    """Spawn Claude Code in a visible window (like autofix).

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

    cwd = PROJECT_ROOT

    # Create batch file to spawn visible window
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write(f'cd /d {cwd}\n')
        f.write('echo Starting Email Digest Session...\n')
        f.write(f'start "" cmd /k "claude --model haiku --permission-mode bypassPermissions @{prompt_file}"\n')
        batch_file = f.name

    print(f"Launching Claude Code in new window...")

    result = subprocess.run(batch_file, shell=True)

    if result.returncode == 0:
        print("Claude Code launched successfully")
        return True
    else:
        print(f"Failed to launch Claude Code (exit code {result.returncode})")
        return False


def spawn_claude_headless(prompt_file):
    """Spawn Claude Code in headless mode (no window, captures output).

    Args:
        prompt_file: Path to the prompt file

    Returns:
        tuple: (success: bool, output: str)
    """
    claude_path = shutil.which('claude')
    if not claude_path:
        print("ERROR: 'claude' command not found in PATH")
        return False, ""

    print(f"Running Claude Code headless (this may take a minute)...")

    result = subprocess.run(
        [claude_path, '-p', '--dangerously-skip-permissions',
         '--allowedTools', 'Read Write Edit Glob Grep',
         '--model', 'sonnet'],
        input=Path(prompt_file).read_text(encoding='utf-8'),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=300,
        cwd=str(PROJECT_ROOT)
    )

    if result.returncode == 0:
        print("Claude Code completed successfully")
        return True, result.stdout
    else:
        print(f"Claude Code failed (exit code {result.returncode})")
        if result.stderr:
            print(f"stderr: {result.stderr[:500]}")
        return False, result.stdout


def main():
    parser = argparse.ArgumentParser(
        description='Email Knowledge Digester - spawns Claude Code to extract knowledge from emails'
    )
    parser.add_argument('--label', metavar='LABEL',
                        help='Only process emails with this Gmail label')
    parser.add_argument('--count', type=int, default=20,
                        help='Max emails to process (default: 20)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without spawning')
    parser.add_argument('--headless', action='store_true',
                        help='Run headless with -p instead of visible window')
    parser.add_argument('--no-mark-read', action='store_true',
                        help='Do not mark emails as read after processing')

    args = parser.parse_args()

    now = now_eastern()
    print(f"{'=' * 60}")
    print(f"Email Knowledge Digester - {now.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"{'=' * 60}\n")

    # Step 1: Fetch emails
    print("Fetching unread emails...")
    messages, reader = fetch_emails(label_filter=args.label, max_count=args.count)

    if not messages:
        print("No unread emails to process.")
        return

    print(f"Found {len(messages)} unread email(s):\n")
    for i, msg in enumerate(messages, 1):
        sender = msg['from'].split('<')[0].strip()[:30]
        print(f"  {i}. {sender:<30}  {msg['subject'][:50]}")
    print()

    if args.dry_run:
        print("DRY RUN - no Claude session spawned, no emails marked read.")
        return

    # Step 2: Save emails to temp files
    print("Saving emails to temp files...")
    temp_dir = save_emails_to_temp(messages)
    print(f"Saved to: {temp_dir}\n")

    # Step 3: Build and save prompt
    prompt = build_prompt(temp_dir, len(messages))

    LOGS_DIR.mkdir(exist_ok=True)
    date_str = now.strftime('%Y-%m-%d')
    prompt_file = LOGS_DIR / f'email_digest_prompt_{date_str}.txt'
    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(prompt)
    print(f"Prompt saved to: {prompt_file}")
    print(f"Prompt length: {len(prompt)} characters\n")

    # Step 4: Spawn Claude Code
    if args.headless:
        success, output = spawn_claude_headless(prompt_file)
        if output:
            print(f"\n{'=' * 60}")
            print("Claude Output:")
            print(f"{'=' * 60}")
            print(output)
    else:
        success = spawn_claude_visible(prompt_file)

    # Step 5: Mark emails as read (only for visible mode, since we can't confirm completion)
    if success and not args.no_mark_read:
        if args.headless:
            # Headless completed, safe to mark read
            print("\nMarking processed emails as read...")
            for msg in messages:
                reader.mark_read(msg['id'])
            print(f"Marked {len(messages)} email(s) as read.")
        else:
            # Visible window - Claude is still running, mark read now
            # (emails were already fetched, Claude has copies in temp files)
            print("\nMarking emails as read (Claude has copies in temp files)...")
            for msg in messages:
                reader.mark_read(msg['id'])
            print(f"Marked {len(messages)} email(s) as read.")

    print(f"\nDone. Temp files at: {temp_dir}")
    if not args.headless:
        print("Watch the Claude Code window for progress.")


if __name__ == '__main__':
    main()
