#!/usr/bin/env python3
"""
Batch Mode Spawner - Claude Code Session Launcher for Batch Error Fixes
========================================================================
Spawns Claude Code sessions to fix errors queued throughout the day.

Key Functions:
- spawn_batch_fix_for_error(): Spawn fix session for one error from queue
- build_fix_prompt(): Create prompt for batch fix agent
- build_fix_context(): Prepare structured context with error history

Author: Ben (with Claude)
Date: 2025-11-11
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Configure UTF-8 encoding for Windows compatibility (MANDATORY)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Import tracker functions
from batch_mode_tracker import (
    eastern_date_string,
    load_historical_journals
)


def get_next_batch_sequence_number(date_str):
    """Get next sequential number for batch prompts on given date

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        int: Next sequence number (1, 2, 3, etc.)
    """
    logs_dir = Path('autofix/logs')
    if not logs_dir.exists():
        return 1

    # Count existing batch_prompt files for this date
    pattern = f'batch_prompt_{date_str}_*.txt'
    existing_files = list(logs_dir.glob(pattern))

    if not existing_files:
        return 1

    # Extract sequence numbers and find max
    sequence_numbers = []
    for file in existing_files:
        # Extract number from batch_prompt_2025-11-18_01.txt -> 01
        parts = file.stem.split('_')
        if len(parts) >= 4:  # batch_prompt_2025-11-18_01
            try:
                seq_num = int(parts[-1])
                sequence_numbers.append(seq_num)
            except ValueError:
                continue

    return max(sequence_numbers) + 1 if sequence_numbers else 1


def spawn_batch_fix_for_error(error, wait_for_completion=True):
    """Spawn Claude Code to fix one error from the queue

    Args:
        error: Error dict from error queue (errors_YYYY-MM-DD.json)
            Required fields: timestamp, error_type, severity, context, source_file
        wait_for_completion: If True, blocks until fix completes (sequential mode)
                            If False, spawns and returns immediately (parallel mode)

    Returns:
        bool: True if spawned successfully, False otherwise
    """
    print(f"\n{'='*70}")
    print(f"🔧 SPAWNING BATCH FIX: {error['error_type']}")
    print(f"{'='*70}")
    print(f"Timestamp: {error['timestamp']}")
    print(f"Severity: {error['severity']}")
    print(f"Source: {error['source_file']}:{error['source_line']}")
    if error.get('occurrence_count', 1) > 1:
        print(f"Occurrences: {error['occurrence_count']} instances of this error today")

    try:
        # Build context
        context = build_fix_context(error)

        # Write context file
        context_file = Path(f'autofix/context/batch_context_{eastern_date_string()}.json')
        context_file.parent.mkdir(exist_ok=True, parents=True)

        with open(context_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, indent=2)

        print(f"✅ Context file created: {context_file}")

        # Get current working directory
        cwd = Path.cwd()

        # Get sequential number for this date
        date_str = eastern_date_string()
        sequence_num = get_next_batch_sequence_number(date_str)

        # Save prompt to file - Claude Code will read it via @file reference
        prompt_file = Path('autofix/logs') / f'batch_prompt_{date_str}_{sequence_num:02d}.txt'
        prompt_file.parent.mkdir(exist_ok=True, parents=True)

        # Build prompt with sequential completion marker
        prompt = build_fix_prompt(error, context_file, date_str, sequence_num)

        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)

        print(f"📝 Prompt saved to: {prompt_file}")
        print(f"📏 Prompt length: {len(prompt)} characters")

        # Create temporary batch file to spawn Claude Code
        # Use @file reference instead of inline prompt to avoid quote escaping issues
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
            f.write('@echo off\n')
            f.write(f'cd /d {cwd}\n')
            f.write('echo Starting Batch Mode Fix...\n')
            f.write(f'echo Error: {error["error_type"]} @ {error["timestamp"]}\n')
            f.write('echo Prompt file: {}\n'.format(prompt_file))
            f.write('start "" cmd /k "claude --permission-mode bypassPermissions @{}"\n'.format(prompt_file))
            batch_file = f.name

        # Save copy of batch file for inspection
        import shutil
        batch_copy = Path('logs') / 'batch_mode_launcher.bat'
        shutil.copy(batch_file, batch_copy)
        print(f"📝 Batch file saved to: {batch_copy}")

        # Execute the batch file (spawns new window, returns immediately)
        print(f"🚀 Launching Claude Code in new window...")
        result = subprocess.run(batch_file, shell=True)

        if result.returncode == 0:
            print(f"✅ Batch fix spawned successfully")
            print(f"🔧 Claude is now fixing: {error['error_type']}")

            # Wait for completion if sequential mode
            if wait_for_completion:
                print(f"\n⏳ SEQUENTIAL MODE: Waiting for fix to complete...")
                print(f"   Close the Claude Code window when fix is finished")
                print(f"   (Or press Ctrl+C to skip waiting and continue)")

                # Create completion marker file path (matches prompt filename)
                completion_marker = Path(f'autofix/logs/.batch_complete_{date_str}_{sequence_num:02d}.marker')

                # Wait for either:
                # 1. Completion marker file to be created (agent finished)
                # 2. User presses Ctrl+C (manual skip)
                # 3. 30 minute timeout (safety)
                import time
                wait_seconds = 0
                max_wait = 1800  # 30 minutes

                try:
                    while wait_seconds < max_wait:
                        if completion_marker.exists():
                            print(f"✅ Fix completed (marker file detected)")
                            completion_marker.unlink()  # Clean up marker
                            break

                        # Show progress every 60 seconds
                        if wait_seconds % 60 == 0 and wait_seconds > 0:
                            print(f"   Still waiting... ({wait_seconds // 60} min elapsed)")

                        time.sleep(5)
                        wait_seconds += 5

                    if wait_seconds >= max_wait:
                        print(f"⚠️  Timeout reached (30 min) - continuing to next error")

                except KeyboardInterrupt:
                    print(f"\n⏭️  Manual skip - continuing to next error")

            return True
        else:
            print(f"❌ Failed to launch batch fix")
            return False

    except Exception as e:
        print(f"❌ Error spawning batch fix: {e}")
        return False


def build_fix_prompt(error, context_file, date_str, sequence_num):
    """Build prompt for fixing an error - SINGLE LINE for batch compatibility

    Args:
        error: Error dict from error queue
        context_file: Path to context JSON file
        date_str: Date string (YYYY-MM-DD) for sequential numbering
        sequence_num: Sequential number for this batch session

    Returns:
        str: Single-line prompt for Claude Code (batch file compatible)
    """
    error_type = error['error_type']
    timestamp = error['timestamp']
    severity = error['severity']
    source_file = error['source_file']
    source_line = error['source_line']
    occurrence_count = error.get('occurrence_count', 1)

    # Build SINGLE LINE prompt (critical for batch file compatibility)
    # Include completion marker instruction for sequential spawning
    completion_marker = f'autofix/logs/.batch_complete_{date_str}_{sequence_num:02d}.marker'

    # Build occurrence info
    occurrence_info = f" (occurred {occurrence_count} times today)" if occurrence_count > 1 else ""

    prompt = "BATCH MODE FIX - Error: {} @ {}{} | Severity: {} | Source: {}:{} | CRITICAL FIRST STEP: Read @autofix/instructions/BATCH_MODE_INSTRUCTIONS.md for your complete workflow checklist. After reading instructions, proceed with error investigation using: Context: @{} | Error Queue: @autofix/errors/errors_{}.json | Historical errors: @autofix/errors/errors_*.json (past 30 days for patterns) | You are an end-of day error and performance reviewer, spawned automatically when errors have been detected in the day's main.py process. Your job is to examine errors and provide long-term, smart, intentional, durable fixes to them to ensure the integrity of the system. Some critical errors may have already been 'handled_by' an 'immediate' Autofix mode, but that mode is intended to quickly repair the error to restore service to the Option Scanner system; therefore, you must review their fix and consider whether it is sufficient for long-term operations or if a more comprehensive fix is required. You are responsible for ONLY THIS SPECIFIC ERROR (timestamp: {}). Other batch mode sessions spawn for each unique error. After fixing THIS error only, mark it as fixed using mark_error_fixed('{}', notes='your fix description'). IMPORTANT: When fix is complete, create completion marker: Write('{}', 'DONE'). Please investigate and resolve this error. Take the time needed to understand the root cause and implement a proper solution, not just a workaround.".format(
        error_type,
        timestamp,
        occurrence_info,
        severity,
        source_file,
        source_line,
        context_file,
        eastern_date_string(),
        timestamp,
        timestamp,
        completion_marker
    )

    return prompt


def build_fix_context(error):
    """Prepare structured context for error fixing

    Args:
        error: Error dict from error queue

    Returns:
        dict: Context with error details, historical patterns, logs
    """
    # Load historical errors for pattern detection (past 30 days)
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from tools.autofix import get_error_history
        error_history = get_error_history(days=30)
    except Exception as e:
        print(f"⚠️  Warning: Could not load error history: {e}")
        error_history = {}

    # Reference to orchestrator log (Claude can read it directly if needed)
    # Don't embed large log excerpts - context file must stay under 25K tokens
    orchestrator_log = Path(f'logs/orchestrator_{eastern_date_string()}.log')
    log_file_path = str(orchestrator_log) if orchestrator_log.exists() else None

    # Check if this error has occurred before
    # Truncate notes to prevent token bloat - full details available in error files
    same_error_history = []
    for date, errors in error_history.items():
        for hist_error in errors:
            if hist_error['error_type'] == error['error_type']:
                notes = hist_error.get('notes', '')
                same_error_history.append({
                    'date': date,
                    'timestamp': hist_error['timestamp'],
                    'fix_status': hist_error.get('fix_status', 'unknown'),
                    # Truncate notes to first 500 chars - full notes in @autofix/errors/errors_DATE.json
                    'notes': notes[:500] + '... [TRUNCATED - see error file for full notes]' if len(notes) > 500 else notes
                })

    # Build error type summary (counts by type, without full error objects)
    error_type_summary = {}
    for date, errors in error_history.items():
        for hist_error in errors:
            error_type = hist_error['error_type']
            if error_type not in error_type_summary:
                error_type_summary[error_type] = {'count': 0, 'dates': []}
            error_type_summary[error_type]['count'] += 1
            if date not in error_type_summary[error_type]['dates']:
                error_type_summary[error_type]['dates'].append(date)

    return {
        'error': error,
        'error_type_summary': error_type_summary,  # Lightweight summary instead of full history
        'same_error_history': same_error_history,  # Filtered to this error type (with truncated notes)
        'orchestrator_log': log_file_path,  # Reference only - Claude reads if needed
        'instructions': 'See autofix/instructions/BATCH_MODE_INSTRUCTIONS.md',
        'note': 'Full error history available in @autofix/errors/errors_*.json files',
        'pattern_detected': len(same_error_history) >= 3  # 3+ occurrences = pattern
    }




if __name__ == '__main__':
    # Test mode - demonstrate usage
    print("Batch Mode Spawner - Test Mode")
    print("=" * 70)
    print()

    # Create a test error
    test_error = {
        'timestamp': datetime.now().isoformat(),
        'error_type': 'test_batch_mode',
        'severity': 'ERROR',
        'source_file': 'test_file.py',
        'source_line': 100,
        'context': {'message': 'Test error'},
        'handled_by': 'none',
        'fix_status': 'pending'
    }

    print("Test error:")
    print(json.dumps(test_error, indent=2))
    print()

    # Test context building (don't spawn)
    print("Building context...")
    context = build_fix_context(test_error)
    print(f"Context keys: {list(context.keys())}")
    print(f"Error type summary: {len(context['error_type_summary'])} unique error type(s)")
    print(f"Same error history: {len(context['same_error_history'])} occurrence(s)")
    print()

    # Test prompt building
    print("Building prompt...")
    date_str = eastern_date_string()
    prompt = build_fix_prompt(test_error, Path('autofix/context/test.json'), date_str, 1)
    print(f"Prompt length: {len(prompt)} characters")
    print()
    print("Prompt preview:")
    print(prompt[:500] + "...")
