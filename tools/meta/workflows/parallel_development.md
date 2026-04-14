# Parallel Development Workflow

**Created:** 2025-10-20
**Purpose:** Safe, repeatable process for refactoring/rebuilding production code
**First Use Case:** main.py refactor (main_v2/)

---

## Overview

When refactoring critical production code, we need:
- ✅ Production never touched during development
- ✅ Clear separation between old and new
- ✅ Incremental progress with review gates
- ✅ Easy testing and comparison
- ✅ Simple cutover when ready

This workflow provides that framework.

---

## Directory Structure

```
E:\options_scanner\
├── main.py                          # Production (keep running) ⚠️ DO NOT MODIFY
├── main.bat                         # Points to production
│
├── main_v2/                         # Development sandbox ✅ WORK HERE
│   ├── README.md                    # What's different from production
│   ├── STATUS.md                    # Current state and progress
│   ├── orchestrator.py              # New lightweight orchestrator
│   ├── scheduler.py                 # Time-based triggers
│   ├── phase_runner.py              # Strategy execution wrapper
│   ├── display_utils.py             # Beautiful logging (extracted)
│   ├── config/
│   │   └── daily_schedule.json      # Declarative schedule
│   └── tests/
│       ├── test_display_utils.py
│       ├── test_scheduler.py
│       └── comparison_tests/
│           └── compare_runs.py      # Old vs new validation
│
└── tools/meta/
    ├── workflows/
    │   ├── parallel_development.md  # This file
    │   └── task_templates/          # Standard task formats
    └── reports/
        └── main_v2_progress/        # Daily progress reports
            ├── 2025-10-20.md
            ├── 2025-10-21.md
            └── ...
```

---

## Setup Process

### Step 1: Initialize Development Area

```bash
# Create main_v2 directory
mkdir main_v2
mkdir main_v2\config
mkdir main_v2\tests
mkdir main_v2\tests\comparison_tests

# Create tracking structure
mkdir tools\meta\reports\main_v2_progress
```

### Step 2: Create Status Files

**main_v2/README.md:**
```markdown
# main.py Refactor (v2)

**Status:** In Development
**Started:** 2025-10-20
**Target:** Lightweight event-driven orchestrator

## Differences from Production main.py

### Architecture
- Production: 2000+ lines, monolithic
- V2: ~500 lines across 4 modules

### Components
- `orchestrator.py` - Main entry point (~200 lines)
- `scheduler.py` - Time-based triggers (~150 lines)
- `phase_runner.py` - Strategy execution (~100 lines)
- `display_utils.py` - Logging/display (~50 lines)
- `config/daily_schedule.json` - Declarative schedule

### Not Yet Implemented
- [ ] Email notifications
- [ ] Database backup logic
- [ ] Weekly archive operations

See STATUS.md for current progress.
```

**main_v2/STATUS.md:**
```markdown
# Development Status

**Last Updated:** 2025-10-20
**Current Phase:** Phase 1 - Display Utils Extraction

## Completed
- [ ] Directory structure created
- [ ] Status tracking in place

## In Progress
- [ ] Extract display_utils.py from main.py

## Blocked
None

## Next Up
- Phase 2: Extract phase_runner.py
- Phase 3: Create scheduler.py

## Notes
- Production main.py still running normally
- All development isolated in main_v2/
```

---

## Development Phases

Based on `MAIN_REFACTOR_NOTES.md`:

### Phase 1: Display Utils Extraction
**Goal:** Extract beautiful logging to standalone module

**Tasks:**
1. Identify all display/logging functions in main.py
2. Create display_utils.py with clean interfaces
3. Fix beautiful_log to write to file AND console
4. Create tests for display functions
5. Validate output matches production

**Success Criteria:**
- display_utils.py has all logging functions
- Tests pass
- Output identical to production logging

**Risk:** LOW
**Estimated Time:** 2-3 sessions

---

### Phase 2: Phase Runner Extraction
**Goal:** Standardize strategy execution

**Tasks:**
1. Create phase_runner.py
2. Define standard Phase interface
3. Wrap strategy calls (fm_main.py, op_main.py, ei_main.py)
4. Add error handling and status reporting
5. Test with each strategy

**Success Criteria:**
- All strategies executable through phase_runner
- Error handling consistent
- Status reporting works

**Risk:** MEDIUM
**Estimated Time:** 3-4 sessions

---

### Phase 3: Scheduler Creation
**Goal:** Time-based trigger system

**Tasks:**
1. Create scheduler.py
2. Implement time-based triggers
3. Add market calendar integration
4. Handle skip conditions (late start, etc.)
5. Test timing logic

**Success Criteria:**
- Strategies trigger at correct times
- Market calendar respected
- Skip logic works

**Risk:** MEDIUM
**Estimated Time:** 3-4 sessions

---

### Phase 4: Declarative Config
**Goal:** Move schedule to JSON

**Tasks:**
1. Create daily_schedule.json
2. Implement config loader
3. Migrate hardcoded schedule
4. Validate equivalent behavior
5. Document config format

**Success Criteria:**
- All timing in JSON config
- Easy to add new strategies
- Behavior identical to production

**Risk:** LOW
**Estimated Time:** 2-3 sessions

---

### Phase 5: Orchestrator Assembly
**Goal:** Wire everything together

**Tasks:**
1. Create orchestrator.py
2. Integrate scheduler + phase_runner + display_utils
3. Add command-line arguments
4. Migrate remaining logic (email, backup)
5. End-to-end testing

**Success Criteria:**
- Single daily cycle works end-to-end
- All strategies execute correctly
- Output identical to production

**Risk:** HIGH
**Estimated Time:** 5-6 sessions

---

## Task Format

Each development session focuses on 1-3 specific tasks.

**Task File Template:** `tools/meta/reports/main_v2_progress/task_YYYYMMDD_N.md`

```markdown
# Task: Extract display_utils.py

**Date:** 2025-10-20
**Phase:** 1 - Display Utils
**Assigned:** AI Engineer + AI Critic
**Estimated Time:** 30 minutes

## Objective
Extract all beautiful logging functions from main.py into display_utils.py

## Context
- main.py lines 150-250 contain display functions
- Need to maintain exact output format
- Fix bug where beautiful_log doesn't write to file

## Acceptance Criteria
- [ ] display_utils.py created with all logging functions
- [ ] beautiful_log writes to both console and log file
- [ ] No duplication in console output
- [ ] Tests pass

## Files to Modify
- Create: main_v2/display_utils.py
- Read: main.py (lines 150-250)
- Create: main_v2/tests/test_display_utils.py

## Testing Plan
1. Run test_display_utils.py (unit tests)
2. Compare output format with production
3. Verify file logging works

## Rollback Plan
If issues found:
1. Delete display_utils.py
2. Preserve learnings in task notes
3. Revise approach

## Success Metrics
- All tests pass
- Output format identical
- Code reviewer approval
```

---

## Daily Workflow

### Night: AI Development Session

```
23:00 - AI reads task list for today
23:05 - Design Loop: Architect + Engineer plan approach
23:15 - Implementation Loop: Engineer codes, Critic reviews
23:45 - Testing: Engineer validates
23:55 - Report Generation: AI writes completion report
00:00 - Sleep (awaiting human review)
```

### Morning: Human Review

```
06:30 - Read morning report
06:35 - Review code changes in main_v2/
06:40 - Run tests if needed
06:45 - Decision:
        ✅ Approve → AI continues tonight
        🔄 Revise → AI fixes tonight
        ❌ Reject → AI tries alternative approach

Time: ~15 minutes
```

---

## Testing Strategy

### Unit Tests
Each module has tests:
```
main_v2/tests/
├── test_display_utils.py      # Logging functions
├── test_scheduler.py           # Time triggers
├── test_phase_runner.py        # Strategy execution
└── test_orchestrator.py        # Integration
```

### Comparison Tests
Validate new version matches production:

```python
# main_v2/tests/comparison_tests/compare_runs.py

def test_output_format():
    """Ensure v2 output matches production format"""
    prod_log = run_production("--once")
    v2_log = run_v2("--once")

    assert_log_format_identical(prod_log, v2_log)

def test_strategy_timing():
    """Ensure v2 triggers at same times"""
    prod_timing = extract_timestamps(prod_log)
    v2_timing = extract_timestamps(v2_log)

    assert_timing_equivalent(prod_timing, v2_timing)

def test_database_operations():
    """Ensure v2 performs same DB operations"""
    prod_queries = capture_db_activity(production_run)
    v2_queries = capture_db_activity(v2_run)

    assert_db_operations_identical(prod_queries, v2_queries)
```

### Integration Tests
Full cycle validation:

```bash
# Run v2 with dry-run mode (doesn't actually execute strategies)
python main_v2/orchestrator.py --once --dry-run

# Compare timing output with production
python main_v2/tests/comparison_tests/compare_timing.py

# If timing matches, run full test (non-production database)
python main_v2/orchestrator.py --once --test-mode
```

---

## Safety Checklist

Before each development session:

- [ ] Production main.py has not been modified
- [ ] All work is in main_v2/ directory
- [ ] No changes to production database
- [ ] No changes to strategy modules (fm_main.py, op_main.py, etc.)
- [ ] Tests exist for new code
- [ ] Rollback plan documented

---

## Progress Tracking

### Daily Report Template

**File:** `tools/meta/reports/main_v2_progress/YYYY-MM-DD.md`

```markdown
# Development Report - October 20, 2025

**Phase:** 1 - Display Utils
**Status:** ✅ Completed

## Tasks Completed

### Task 1: Extract display_utils.py
**Time:** 35 minutes
**Risk:** LOW

**Changes:**
- Created `main_v2/display_utils.py` (150 lines)
- Extracted 8 functions from main.py
- Fixed beautiful_log file logging bug
- Added unit tests

**Files Modified:**
- Created: main_v2/display_utils.py
- Created: main_v2/tests/test_display_utils.py

**Testing:**
- ✅ All unit tests pass (8/8)
- ✅ Output format matches production
- ✅ File logging works correctly

**Review Notes:**
Check display_utils.py:15-45 for the beautiful_log fix

---

## Tomorrow's Plan

**Task:** Create phase_runner.py
**Phase:** 2 - Phase Runner
**Estimated Time:** 40 minutes

---

## Blockers
None

## Questions for Human
None

## Learning Notes
- The beautiful_log bug was deeper than expected - had to remove StreamHandler
- Found 3 unused display functions in main.py - omitted from extraction
- Discovered emoji encoding issue in Windows console - added reconfigure
```

---

## Cutover Process

When all phases complete and testing passes:

### Pre-Cutover Checklist

- [ ] All 5 phases completed
- [ ] All unit tests pass
- [ ] All comparison tests pass
- [ ] Full cycle tested in non-production environment
- [ ] Code reviewed and approved
- [ ] Rollback plan prepared
- [ ] Backup of production main.py created

### Cutover Steps

```bash
# 1. Create backup
copy main.py main_legacy.py
copy main.bat main_legacy.bat

# 2. Prepare new version
copy main_v2\orchestrator.py main.py

# 3. Update batch file
# Edit main.bat to point to main.py (if needed)

# 4. Test immediately
python main.py --once

# 5. If successful, schedule for next full cycle
# If issues, rollback:
#   copy main_legacy.py main.py
```

### Post-Cutover Monitoring

**First 3 days:**
- Monitor logs closely
- Compare timing with historical runs
- Validate all strategies execute
- Check database operations

**After 1 week:**
- Archive main_legacy.py
- Remove main_v2/ directory
- Update CLAUDE.md
- Document lessons learned

---

## Rollback Strategy

### During Development (main_v2/ stage)
- Simply delete problematic code
- Production unaffected
- No rollback needed

### After Cutover (main.py replaced)
```bash
# Immediate rollback
copy main_legacy.py main.py

# Restart orchestrator
# System back to production within 1 minute
```

### Partial Rollback (hybrid)
If some components work but others don't:
- Keep working components from v2
- Revert problematic components to legacy
- Document hybrid state
- Plan fix for next cycle

---

## Lessons Learned Template

After completing the refactor, document:

**File:** `tools/meta/reports/main_v2_lessons_learned.md`

```markdown
# main.py Refactor - Lessons Learned

## What Worked Well
- Parallel development kept production safe
- Incremental phases allowed frequent review
- Comparison tests caught subtle bugs
- AI loop system maintained forward progress

## What Didn't Work
- Initial task estimates were too optimistic
- Some design loops took longer than expected
- Needed more iteration on testing strategy

## Process Improvements
- Add buffer to time estimates (1.5x)
- Create test strategy before coding
- More frequent check-ins during complex phases

## For Next Time
- Start with tests/specs, then implement
- Create comparison framework earlier
- Document assumptions more explicitly
```

---

## Related Documents

- `MAIN_REFACTOR_NOTES.md` - Technical vision and requirements
- `tools/meta/workflows/autonomous_development_loops.md` - AI loop architecture
- `tools/meta/docs/vision.md` - Overall Meta-AI system vision

---

## Summary

This workflow provides:
1. **Safety:** Production never touched
2. **Progress:** Clear phases and milestones
3. **Review:** Daily checkpoints
4. **Testing:** Comprehensive validation
5. **Rollback:** Easy reversion if needed

**Use this as the template for any major refactor or rebuild.**
