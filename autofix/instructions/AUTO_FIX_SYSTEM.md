# Auto-Fix System — Original Design Document

> **Note**: This was the original design document for the Flow Monitor duplicate contract use case.
> The system has since been generalized to handle all error types across all strategies.
> For the current comprehensive reference, see `autofix/reference/AUTOFIX_CHEAT_SHEET.md`.

## Overview (Original Scope)
Self-healing code system that automatically spawns Claude Code when duplicate contract errors are detected in Flow Monitor storage operations.

## How It Works

### 1. Error Detection (`fm_storage.py`)
- Detects duplicate contracts in batch data before database insertion
- Deduplicates to prevent constraint violations
- If duplicates found, triggers auto-fix system

### 2. Claude Code Launcher (`main_fix_launcher.py`)
- Spawns Claude Code in **visible window** with diagnostic context
- Provides:
  - Last 150 lines of today's orchestrator log
  - Duplicate contract details
  - File references (@fm_storage.py, @fm_collector.py)
  - Specific tasks to complete
- Window title: "Claude Code Auto-Fix Session"

### 3. System Continues Running
- **No shutdown** - system keeps running normally
- Deduplication already prevented the crash
- Claude Code analyzes root cause **in parallel** with production
- Safer approach - no process termination required

## Diagnostic Information Provided to Claude

Claude Code receives:
- **Error count**: Number of duplicate contracts detected
- **System status**: Confirmed still running (deduplication prevented crash)
- **Duplicate details**: Sample of duplicated contract hashes (symbol, strike, expiration, type)
- **Log excerpt**: Last 150 lines from today's orchestrator log
- **File locations**: Exact paths to fm_storage.py and fm_collector.py
- **Tasks**:
  1. Analyze duplicate contract details
  2. Find root cause (collection logic, parallel processing, API behavior, caching bug, etc.)
  3. Fix the code to prevent duplicates at source
  4. Test the fix when convenient (system continues running with safety net)
  5. Log all changes to `logs/claude_fixes_YYYY-MM-DD.md`
  6. Email final report using `tools/email_notifier.py`

## Authority Granted to Claude

- **Read**: Full access to all files
- **Edit**: Can modify fm_storage.py, fm_collector.py, and related files
- **Run**: Can execute scripts and restart main.py
- **Log**: Must document all changes in daily fix log

## Workflow

```
Flow Monitor Cycle
    ↓
Duplicate Contracts Detected in fm_storage.py
    ↓
Deduplicate Batch Data (prevent crash)
    ↓
Trigger Auto-Fix System
    ↓
Launch Claude Code (visible window)
    └─→ Diagnostic context loaded
        └─→ Claude begins parallel analysis
            ↓
        Flow Monitor Continues Running
            ↓
        Claude Investigates & Fixes Root Cause
            ↓
        Claude Emails Report
```

## Testing

Run the test script to see the system in action:

```bash
python main_fix_test.py
```

This will:
1. Simulate a duplicate contract error
2. Launch Claude Code in a visible window with diagnostic prompt
3. Demonstrate the full diagnostic context passed to Claude
4. Let you observe the launcher mechanism

## Production Behavior

When duplicates are detected during normal Flow Monitor operation:

1. **Immediate**: Deduplication prevents database crash
2. **Within 1 second**: Claude Code window spawns with diagnostics
3. **System continues**: Flow Monitor keeps running normally
4. **Parallel investigation**: Claude analyzes root cause while production runs
5. **Code fix**: Claude modifies source files to prevent duplicates at origin
6. **Email report**: Claude sends final report with root cause and resolution
7. **Self-healing**: Next deployment/restart runs with the fix applied

## Change Log Location

All automated fixes are logged to:
```
logs/claude_fixes_YYYY-MM-DD.md
```

Each entry should include:
- Timestamp
- Error detected
- Root cause analysis
- Code changes made
- Test results
- Restart status

## Files

- `main_fix_launcher.py` - Spawns Claude Code with diagnostic context
- `main_fix_test.py` - Test script to see the system in action
- `fm_storage.py` - Trigger point (`_trigger_auto_fix()` method with inline countdown)
- `AUTO_FIX_SYSTEM.md` - This documentation
- ~~`main_fix_shutdown.py`~~ - Deprecated (replaced by inline background thread)

## Future Enhancements

This pattern can be extended to other error types:
- Database locking issues
- API rate limit violations
- Collection timeouts
- Data validation failures

Simply add new trigger calls in the appropriate error handlers.
