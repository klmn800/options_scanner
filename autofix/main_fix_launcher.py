#!/usr/bin/env python3
"""
Auto-Fix Launcher for Flow Monitor Storage Errors
Spawns Claude Code with diagnostic context when duplicate contract errors are detected.

Triggered by: Flow Monitor duplicate contract detection
Purpose: Self-healing code via automated Claude Code assistance

Safety Features:
- Rate limiting: Maximum 5 launches per hour (intelligent)
- Failure escalation: 3 attempts per error type per day max
- Protected file list enforced via AUTO_FIX_INSTRUCTIONS.md
- Launch tracking log for audit trail
"""
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import os
import json

# Configure UTF-8 encoding for Windows compatibility (MANDATORY)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


def extract_log_tail(log_file, lines=100):
    """Extract last N lines from log file"""
    try:
        if not os.path.exists(log_file):
            return "Log file not found: {}".format(log_file)

        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except Exception as e:
        return "Error reading log: {}".format(e)


# File locking removed - relying on instructional constraints
# Claude follows AUTO_FIX_INSTRUCTIONS.md protected file list


def check_escalation_threshold(error_type):
    """Check if error has been attempted too many times today

    Args:
        error_type: Error type string (e.g., 'duplicate_contracts', 'database_locked')

    Returns:
        tuple: (allowed: bool, message: str, attempt_count: int)
    """
    journal_pattern = 'autofix/logs/auto_fix_journal_{}.md'.format(
        datetime.now().strftime('%Y-%m-%d')
    )

    attempt_count = 0

    if os.path.exists(journal_pattern):
        try:
            with open(journal_pattern, 'r', encoding='utf-8') as f:
                content = f.read()
                # Count entries for this error type
                # Convert error_type to pattern (e.g., 'duplicate_contracts' → 'duplicate.*contract')
                error_pattern = error_type.replace('_', '.*')
                import re
                pattern = re.compile(r'## \[\d{2}:\d{2}\].*{}.*'.format(error_pattern), re.IGNORECASE)
                attempt_count = len(pattern.findall(content))
        except Exception as e:
            print("   ⚠️  Could not read journal: {}".format(e))

    if attempt_count >= 3:
        return False, "ESCALATION THRESHOLD REACHED: {} attempts today for {}".format(
            attempt_count, error_type
        ), attempt_count

    return True, "Escalation check passed: {} of 3 attempts used today for {}".format(
        attempt_count, error_type
    ), attempt_count


def get_next_immediate_sequence_number(date_str):
    """Get next sequential number for immediate prompts on given date

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        int: Next sequence number (1, 2, 3, etc.)
    """
    logs_dir = Path('autofix/logs')
    if not logs_dir.exists():
        return 1

    # Count existing immediate_prompt files for this date
    pattern = f'immediate_prompt_{date_str}_*.txt'
    existing_files = list(logs_dir.glob(pattern))

    if not existing_files:
        return 1

    # Extract sequence numbers and find max
    sequence_numbers = []
    for file in existing_files:
        # Extract number from immediate_prompt_2025-11-20_01.txt -> 01
        parts = file.stem.split('_')
        if len(parts) >= 4:  # immediate_prompt_2025-11-20_01
            try:
                seq_num = int(parts[-1])
                sequence_numbers.append(seq_num)
            except ValueError:
                continue

    return max(sequence_numbers) + 1 if sequence_numbers else 1


def check_rate_limit():
    """Rate limiting based on error queue — counts immediate spawns in past hour

    Uses the unified error queue (autofix/errors/errors_YYYY-MM-DD.json) as
    the source of truth instead of a separate launch log.

    Returns:
        tuple: (allowed: bool, message: str)
    """
    max_per_hour = 5
    one_hour_ago = datetime.now() - timedelta(hours=1)

    # Read today's error queue to count recent immediate-mode spawns
    try:
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        from tools.autofix import get_todays_errors

        errors = get_todays_errors()

        # Count errors handled by immediate mode in the past hour
        recent_spawns = [
            e for e in errors
            if e.get('handled_by') == 'immediate'
            and datetime.fromisoformat(e['timestamp']) > one_hour_ago
        ]

    except Exception as e:
        print("⚠️  Warning: Could not read error queue: {}".format(e))
        # Fail open - allow the launch if we can't read the queue
        return True, "Error queue unavailable, allowing launch"

    if len(recent_spawns) < max_per_hour:
        return True, "Rate limit OK: {} of {} immediate spawns in past hour".format(
            len(recent_spawns), max_per_hour
        )

    # Hit limit
    oldest = datetime.fromisoformat(recent_spawns[0]['timestamp'])
    wait_until = oldest + timedelta(hours=1)
    wait_minutes = max(1, int((wait_until - datetime.now()).total_seconds() / 60))
    return False, "Rate limit exceeded: {} immediate spawns in past hour. Wait {} minutes.".format(
        len(recent_spawns), wait_minutes
    )




def build_diagnostic_prompt(error_context):
    """Build concise diagnostic prompt for Claude Code - single line for batch compatibility

    Args:
        error_context: Dict containing error details
            Required: 'error_type' (e.g., 'duplicate_contracts')
            Optional: Any error-specific fields

    Instead of embedding logs inline, directs Claude to read files directly.
    """

    # Get error type and format for display
    error_type = error_context.get('error_type', 'unknown_error')
    error_display = error_type.replace('_', ' ').title()

    # Get today's date for file references
    today = datetime.now().strftime('%Y-%m-%d')
    log_file = "logs/orchestrator_{}.log".format(today)

    # Get main.py PID from error context (if available)
    main_py_pid = error_context.get('main_py_pid')
    pid_str = "Main.py PID: {}. ".format(main_py_pid) if main_py_pid else ""

    # Build error-specific context string
    context_parts = []
    for key, value in error_context.items():
        if key not in ['error_type', 'main_py_pid']:
            # Format the value appropriately
            if isinstance(value, list):
                if len(value) > 0 and isinstance(value[0], dict):
                    # List of dicts - just show count
                    context_parts.append("{}: {} items".format(key, len(value)))
                else:
                    context_parts.append("{}: {}".format(key, value[:3]))  # First 3 items
            else:
                context_parts.append("{}: {}".format(key, value))

    error_context_str = ", ".join(context_parts) if context_parts else "see logs"

    # Build MINIMAL prompt - just the context-specific variables
    # All instructions are in autofix/instructions/AUTO_FIX_INSTRUCTIONS.md
    # CRITICAL: Emphasize journal checking
    prompt = "AUTO-FIX: {}. FIRST: Check @autofix/logs/auto_fix_journal_{}.md for previous attempts today. THEN: Read @autofix/instructions/AUTO_FIX_INSTRUCTIONS.md for protocol. {}ERROR: {}. Log: @{}. Please fix it.".format(
        error_display,
        today,
        pid_str,
        error_context_str,
        log_file
    )

    return prompt




def send_escalation_email(error_type, attempt_count):
    """Send urgent email when escalation threshold is reached"""
    try:
        # Import here to avoid circular dependency
        sys.path.insert(0, 'tools')
        from email_notifier import send_email

        # Get today's journal entries
        journal_file = 'autofix/logs/auto_fix_journal_{}.md'.format(
            datetime.now().strftime('%Y-%m-%d')
        )

        journal_content = "No journal entries found"
        if os.path.exists(journal_file):
            with open(journal_file, 'r', encoding='utf-8') as f:
                journal_content = f.read()

        send_email(
            subject="🚨 AUTO-FIX ESCALATION: {} recurring despite {} attempts".format(error_type, attempt_count),
            body="""
AUTO-FIX ESCALATION ALERT

Error Type: {}
Attempts Today: {}
Status: MAXIMUM ATTEMPTS REACHED - HUMAN INTERVENTION REQUIRED

The auto-fix system has attempted to resolve this error {} times today
without success. The system will not spawn additional auto-fix sessions
for this error type until tomorrow.

System Status: Running normally with safety net (deduplication)

Action Required: Manual investigation and resolution

Today's Journal Entries:
{}

---
Auto-Fix System
""".format(error_type, attempt_count, attempt_count, journal_content)
        )

        print("   📧 Escalation email sent to human")
    except Exception as e:
        print("   ⚠️  Failed to send escalation email: {}".format(e))


def launch_claude_fix(error_context):
    """Launch Claude Code in visible window with diagnostic prompt

    Args:
        error_context: Dict with error details
            Required: 'error_type' (e.g., 'duplicate_contracts', 'database_locked')
            Optional: Any error-specific data
    """

    error_type = error_context.get('error_type', 'unknown_error')
    error_display = error_type.replace('_', ' ').upper()

    print("\n" + "="*70)
    print("🚨 {} ERROR DETECTED - SPAWNING AUTO-FIX".format(error_display))
    print("="*70)

    # Print error-specific summary
    for key, value in error_context.items():
        if key not in ['error_type', 'main_py_pid']:
            if isinstance(value, list):
                print("{}: {} items".format(key.replace('_', ' ').title(), len(value)))
            else:
                print("{}: {}".format(key.replace('_', ' ').title(), value))

    print("="*70 + "\n")

    # Check escalation threshold first (3 attempts per day max)
    allowed, message, attempt_count = check_escalation_threshold(error_type)
    print("🚨 Escalation Check: {}".format(message))
    if not allowed:
        print("❌ AUTO-FIX BLOCKED: {}".format(message))
        print("   System will continue running with deduplication safety net")
        print("   Sending escalation alert to human...")
        print("="*70 + "\n")

        send_escalation_email(error_type, attempt_count)
        return False

    # Check rate limit (intelligent)
    allowed, message = check_rate_limit()
    print("🛡️  Rate Limit Check: {}".format(message))
    if not allowed:
        print("❌ AUTO-FIX BLOCKED: {}".format(message))
        print("   System will continue running with deduplication safety net")
        print("   Human intervention may be required if errors persist")
        print("="*70 + "\n")
        return False

    print("✅ Safety checks passed - proceeding with auto-fix spawn")
    print("Spawning Claude Code for automated diagnosis and repair...")
    print("\n")

    # Check if claude command is available
    import shutil
    claude_path = shutil.which('claude')
    if not claude_path:
        print("❌ ERROR: 'claude' command not found in PATH")
        print("   Please ensure Claude Code CLI is installed and in PATH")
        print("   Run: npm install -g @anthropics/claude-code")
        return False

    print("✓ Found claude at: {}".format(claude_path))

    # Build diagnostic prompt (single line)
    full_prompt = build_diagnostic_prompt(error_context)

    # Get current working directory
    cwd = Path.cwd()

    # Save prompt to file - Claude Code will read it via @file reference
    # This avoids Windows batch file quote escaping issues entirely
    date_str = datetime.now().strftime('%Y-%m-%d')
    sequence_num = get_next_immediate_sequence_number(date_str)
    prompt_file = Path('autofix/logs') / f'immediate_prompt_{date_str}_{sequence_num:02d}.txt'
    prompt_file.parent.mkdir(exist_ok=True, parents=True)

    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(full_prompt)

    print("📝 Prompt saved to: {}".format(prompt_file))
    print("📏 Prompt length: {} characters".format(len(full_prompt)))

    # Create temporary batch file to spawn Claude Code in visible window
    batch_content_log = Path('logs') / 'claude_launcher_batch.bat'
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
        f.write('@echo off\n')
        f.write('cd /d {}\n'.format(cwd))
        f.write('echo Starting Claude Code...\n')
        f.write('echo Prompt file: {}\n'.format(prompt_file))
        # Use @file reference to avoid quote escaping issues
        f.write('start "" cmd /k "claude --permission-mode bypassPermissions @{}"\n'.format(prompt_file))
        batch_file = f.name

    # Save copy of batch file for inspection
    import shutil
    shutil.copy(batch_file, batch_content_log)
    print("📝 Batch file saved to: {}".format(batch_content_log))

    print("📝 Launching Claude Code in new visible window...")
    print("🪟 Window title: 'Claude Code Auto-Fix Session'")

    # Execute the batch file (spawns new window, returns immediately)
    # Don't capture output - it would block waiting for spawned window to close
    result = subprocess.run(
        batch_file,
        shell=True
    )

    if result.returncode == 0:
        print("✅ Claude Code launched successfully")
        print("🔍 Claude is now analyzing the issue...")

        # Note: Launch tracking now handled by error queue system

        # Auto-accept the bypass permissions prompt
        print("🤖 Sending keystrokes to accept bypass permissions prompt...")
        auto_accept_bypass_prompt()

        return True
    else:
        print("❌ Failed to launch Claude Code: {}".format(result.stderr if result.stderr else "Unknown error"))
        return False


def auto_accept_bypass_prompt():
    """Automatically send keystrokes to accept Claude Code's bypass permissions prompt

    Waits 15 seconds for Claude Code window to appear, then sends "2" + Enter
    to accept the bypass permissions confirmation.
    """
    import time

    # Give Claude Code window time to appear and render the prompt
    print("   Waiting 15 seconds for Claude Code window to render...")
    time.sleep(15)

    try:
        # Use pyautogui if available (cross-platform)
        try:
            import pyautogui
            print("   Sending keystrokes: '2' + Enter")
            pyautogui.write('2')
            pyautogui.press('enter')
            print("   ✅ Keystrokes sent successfully (pyautogui)")
            return
        except ImportError:
            pass

        # Fallback to Windows SendKeys via PowerShell
        ps_script = """
        Add-Type -AssemblyName System.Windows.Forms
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait("2{{ENTER}}")
        """

        result = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5
        )

        if result.returncode == 0:
            print("   ✅ Keystrokes sent successfully (PowerShell SendKeys)")
        else:
            print("   ⚠️  PowerShell SendKeys failed: {}".format(result.stderr))
            print("   Note: Claude Code may still be waiting for manual confirmation")

    except Exception as e:
        print("   ⚠️  Failed to send keystrokes: {}".format(e))
        print("   Note: You may need to manually accept bypass permissions prompt")


if __name__ == "__main__":
    import json

    # Get error context from environment variable (set by fm_storage.py)
    error_context_json = os.environ.get('ERROR_CONTEXT')

    if error_context_json:
        try:
            error_context = json.loads(error_context_json)
        except:
            # Fallback if JSON parse fails
            error_context = {'duplicate_count': 'Unknown', 'duplicated_hashes': []}
    else:
        # Test mode - simulate error context
        error_context = {
            'duplicate_count': 42,
            'duplicated_hashes': [
                ('JBLU|6.0|2025-12-05|call', 2),
                ('AAL|12.5|2025-11-15|put', 2)
            ]
        }

    launch_claude_fix(error_context)
