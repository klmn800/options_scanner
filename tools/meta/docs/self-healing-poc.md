# Self-Healing System - Proof of Concept

**Status:** 🧪 Experimental POC
**Created:** 2025-10-16
**Goal:** Demonstrate automated error detection and Claude Code spawning for fixes

## Overview

This POC demonstrates a self-healing system where:
1. A script fails with an error
2. Log analyzer detects the error
3. Claude Code is automatically spawned with error context
4. Claude fixes the bug
5. Script runs successfully

## Architecture

```
test_self_healing.py (fails on purpose)
    ↓ logs error with [LOGANALYZER-ALERT]
    ↓
log_analyzer_autofix.py (scans logs)
    ↓ finds error
    ↓
auto_fix_manager.py (checks safety limits)
    ↓ approves fix attempt
    ↓
Claude Code spawned in new window
    ↓ analyzes + fixes bug
    ↓
test_self_healing.py (runs successfully)
```

## Components

### 1. Auto-Fix State Manager (`tools/meta/auto_fix_manager.py`)
Prevents infinite loops and enforces safety limits.

**Safety Features:**
- Max 3 attempts per unique error
- 5-minute cooldown between attempts
- Circuit breaker after 3 consecutive failures
- Human override support

**CLI Commands:**
```bash
# Check status
python tools/meta/auto_fix_manager.py --status

# Disable auto-fix (manual override)
python tools/meta/auto_fix_manager.py --disable

# Re-enable
python tools/meta/auto_fix_manager.py --enable

# Reset circuit breaker
python tools/meta/auto_fix_manager.py --reset-breaker

# Run test
python tools/meta/auto_fix_manager.py --test
```

### 2. Test Script (`tools/meta/test_self_healing.py`)
Simple script with deliberate bug (division by zero).

**The Bug:**
```python
def buggy_calculation(x, y):
    result = x / y  # No check for y == 0
    return result
```

**Expected Fix:**
```python
def buggy_calculation(x, y):
    if y == 0:
        raise ValueError("Cannot divide by zero")
    result = x / y
    return result
```

### 3. Enhanced Log Analyzer (`tools/meta/log_analyzer_autofix.py`)
Detects errors and spawns Claude Code for fixes.

**Features:**
- Extracts error context from logs
- Checks auto-fix manager for approval
- Spawns Claude with detailed fix instructions
- Tracks fix attempts

## Testing the POC

### Step 1: Verify Auto-Fix Manager

```bash
# Check initial status
python tools/meta/auto_fix_manager.py --status
```

**Expected Output:**
```
AUTO-FIX SYSTEM STATUS
======================================================================
Enabled: ✅ YES
Circuit Breaker: ✅ Inactive
Consecutive Failures: 0
Total Errors Tracked: 0
Fixed Errors: 0
Active Errors: 0
Last Success: Never
```

### Step 2: Run Buggy Test Script

```bash
# This will fail on iteration 3
python tools/meta/test_self_healing.py
```

**Expected Behavior:**
- Runs iterations 1-2 successfully
- Fails on iteration 3 (division by zero)
- Logs error with [LOGANALYZER-ALERT] trigger
- Exits with error code 1

**Check Log:**
```bash
# View the error in logs
type logs\test_self_healing_2025-10-16.log
```

Look for:
```
ERROR - [LOGANALYZER-ALERT] Test calculation failed with division by zero
```

### Step 3: Run Auto-Fix Analyzer

```bash
# Scan logs and attempt auto-fix
python tools/meta/log_analyzer_autofix.py --hours 1
```

**Expected Behavior:**
1. Scans logs from past hour
2. Finds the division by zero error
3. Checks auto-fix manager (should approve)
4. Spawns Claude Code in new window
5. Claude appears with detailed error context and fix instructions

**What Claude Should See:**
```
🚨 AUTO-FIX MODE - Critical Error Detected

**Error Summary:**
- Message: Test calculation failed with division by zero
- File: test_self_healing.py
- Exception: ZeroDivisionError
- Log: test_self_healing_2025-10-16.log

**Error Context (from logs):**
[... error details ...]

**YOUR TASK:**
1. Analyze the error and identify root cause
2. Locate the buggy code
3. Fix the bug
4. Test your fix
5. Report what you fixed
```

### Step 4: Let Claude Fix the Bug

In the spawned Claude Code window:
1. Claude should analyze the error
2. Find `buggy_calculation()` function
3. Add validation for `y == 0`
4. Test the logic
5. Report completion

**Human Verification:**
After Claude reports the fix, check the code:
```bash
# View the fixed function
type test_self_healing.py | findstr /C:"def buggy_calculation" /C:"if y == 0"
```

### Step 5: Test the Fix

```bash
# Run test script again
python tools/meta/test_self_healing.py
```

**Expected Behavior:**
- All 5 iterations complete successfully
- No errors logged
- Script exits with code 0

**Success Message:**
```
======================================================================
✅ TEST COMPLETED SUCCESSFULLY
======================================================================
All 5 iterations passed without errors
Self-healing system test: PASSED
```

### Step 6: Verify Auto-Fix State

```bash
# Check updated status
python tools/meta/auto_fix_manager.py --status
```

**Expected Output:**
```
Enabled: ✅ YES
Total Errors Tracked: 1
Fixed Errors: 1
Active Errors: 0
```

## Testing Edge Cases

### Test Cooldown Period

```bash
# Revert the fix, run test again
python tools/meta/test_self_healing.py

# Try to auto-fix immediately
python tools/meta/log_analyzer_autofix.py --hours 1
```

**Expected:** Should see "Cooldown active (4 minutes remaining)"

### Test Max Attempts

```bash
# Revert fix, run test 3 times
python tools/meta/test_self_healing.py
python tools/meta/log_analyzer_autofix.py --hours 1

# Wait 5 minutes, repeat 2 more times
# After 3 attempts, should see:
```

**Expected:** "Max fix attempts reached (3)"

### Test Circuit Breaker

```bash
# Simulate 3 consecutive failures
python tools/meta/auto_fix_manager.py --test

# Check status
python tools/meta/auto_fix_manager.py --status
```

**Expected:** "Circuit Breaker: ⚠️ ACTIVE"

**Reset:**
```bash
python tools/meta/auto_fix_manager.py --reset-breaker
```

### Test Manual Override

```bash
# Disable auto-fix
python tools/meta/auto_fix_manager.py --disable

# Try to auto-fix
python tools/meta/log_analyzer_autofix.py --hours 1
```

**Expected:** "Auto-fix is disabled (human override active)"

**Re-enable:**
```bash
python tools/meta/auto_fix_manager.py --enable
```

## Safety Features Demonstrated

✅ **Max Attempts:** Prevents infinite fix loops
✅ **Cooldown Period:** Prevents rapid retry spam
✅ **Circuit Breaker:** Stops after consecutive failures
✅ **Human Override:** Manual disable/enable
✅ **Error Hashing:** Tracks unique errors
✅ **State Persistence:** Survives restarts

## Limitations (POC)

This POC demonstrates the concept but has limitations:

1. **Manual Success Recording:** Claude doesn't automatically report success
2. **Single Error Focus:** Stops after first fix attempt
3. **No Auto-Restart:** Doesn't restart test script automatically
4. **Basic Error Parsing:** Simple context extraction
5. **No Fix Verification:** Doesn't test the fix automatically

## Next Steps (Production System)

To make this production-ready:

1. **Claude Output Monitoring:**
   - Parse Claude's response for "AUTO-FIX COMPLETE"
   - Automatically record success/failure
   - Extract what was changed

2. **Automatic Restart:**
   - After Claude exits, restart failed script
   - Monitor for success/new errors
   - Loop until fixed or max attempts

3. **Integration with main.py:**
   - Run auto-fix between pipeline phases
   - Check for errors before starting next cycle
   - Schedule periodic health checks

4. **Enhanced Error Parsing:**
   - Extract stack traces
   - Identify function/line numbers
   - Correlate with git history

5. **Fix Verification:**
   - Run unit tests if available
   - Syntax check before running
   - Compare behavior before/after

6. **Notification System:**
   - Alert when auto-fix succeeds
   - Notify when circuit breaker trips
   - Daily summary of fixes

## Troubleshooting

### Claude Doesn't Spawn

**Check:**
```bash
# Verify Claude is in PATH
claude --version

# Test spawning manually
start cmd /k "claude 'hello'"
```

### Error Not Detected

**Check:**
```bash
# Verify error has trigger phrase
type logs\test_self_healing_2025-10-16.log | findstr "[LOGANALYZER-ALERT]"

# Check log file timestamp
dir logs\test_self_healing_*.log
```

### Auto-Fix Blocked

**Check status:**
```bash
python tools/meta/auto_fix_manager.py --status
```

**Common issues:**
- Circuit breaker active → `--reset-breaker`
- Manual override → `--enable`
- Max attempts → Edit `data/auto_fix_state.json`

## Files Created

- `tools/meta/auto_fix_manager.py` - State management and safety limits
- `tools/meta/test_self_healing.py` - Test script with deliberate bug
- `tools/meta/log_analyzer_autofix.py` - Enhanced analyzer with Claude spawning
- `tools/meta/docs/self-healing-poc.md` - This documentation
- `data/auto_fix_state.json` - Auto-generated state file (after first run)

## Cleanup

To reset the POC:

```bash
# Clear auto-fix state
del data\auto_fix_state.json

# Clear test logs
del logs\test_self_healing_*.log

# Revert any changes to test_self_healing.py
git checkout test_self_healing.py
```

## Feedback

After testing, consider:
- Did Claude successfully fix the bug?
- Were the safety limits effective?
- Is the error context sufficient for Claude?
- What would make this more robust?
- Should this be integrated into main.py?
