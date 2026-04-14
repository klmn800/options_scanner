# Auto-Fix System Implementation Plan

**Created:** 2025-11-01
**Status:** In Development
**Author:** Ben (with Claude)

---

## Overview

Self-healing code system that spawns autonomous Claude Code CLI sessions when runtime errors are detected. System uses decision heuristics (not rigid error taxonomies) to assess fixability on a case-by-case basis.

**Key Innovation:** Session memory via journal system - multiple spawns throughout the day build on each other's work.

---

## Trigger Mechanisms

### Immediate Mode (Real-Time Critical Errors)

**When:** During production operation when critical error detected
**Where:** Inside strategy code (Flow Monitor, Option Pipeline, etc.)
**How:** Strategy monitors its own health and triggers when something breaks

**Example - Flow Monitor:**
```
Location: fm_storage.py (after storing scan results)

Check: When was last alert generated?
If: (time_since_alert > 2 hours) AND (market_open)
Then: Trigger auto-fix immediately
```

**Example - Option Pipeline:**
```
Location: op_storage.py (after storing contracts)

Check: How many contracts stored this cycle?
If: (contracts_stored == 0) AND (API_calls_succeeded)
Then: Trigger auto-fix immediately (silent failure)
```

**Characteristics of Critical Errors:**
- Silent failures (system runs but produces no output)
- Data integrity violations (UNIQUE constraint errors)
- Repeated failures (same error 5+ times in 10 minutes)
- Resource exhaustion (disk <1GB, memory >90%)

### Batch Mode (Daily Error Review)

**When:** End of daily sequence (~7:00 PM)
**Where:** main.py orchestrator
**How:** Reviews accumulated errors from throughout the day

**Flow:**
```
7:00 PM - Daily cycle complete
↓
Check: Were there any errors today?
↓
Read error log (search for [AUTOFIX-TRIGGER] codeword)
↓
If errors found: Spawn Claude in BATCH mode
↓
Claude reviews overnight, fixes what it can, documents the rest
```

**You wake up to:** Email report with fixes applied and what needs human attention.

---

## Error Detection - The Codeword Approach

**Problem:** How do we identify errors worth spawning auto-fix for?

**Solution:** Use unique trigger phrase in error logs.

### The Trigger Codeword: `[AUTOFIX-TRIGGER]`

**Already implemented in existing system:**
- Current codeword: `[LOGANALYZER-ALERT]` (from error_logger.py)
- Used by log_analyzer.py to filter critical errors
- **Decision:** Keep this, works perfectly for auto-fix too

**How It Works:**

```python
# In any strategy code when critical error occurs:
from tools.error_logger import log_critical_error

try:
    risky_operation()
except Exception as e:
    log_critical_error(
        logger,
        "No alerts generated in 2 hours during market hours",
        exception=e,
        extra_context={'last_alert_time': '9:47 AM', 'symbols_scanned': 800}
    )
    # This automatically adds [LOGANALYZER-ALERT] prefix
    # Auto-fix launcher searches for this codeword
```

**Benefits:**
- No need to anticipate every error type
- Developers decide what's "critical" when writing code
- Simple grep search: `grep "[LOGANALYZER-ALERT]" logs/*.log`
- Already battle-tested in production

**Immediate vs Batch:**
- **Immediate trigger:** Call `error_manager.trigger_auto_fix()` right after logging
- **Batch trigger:** Launcher searches logs for codeword at end of day

---

## Knowledge Base Architecture

```
autofix/
├── instructions/                      # Standing instructions for Claude
│   ├── AUTO_FIX_INSTRUCTIONS.md       # Core workflow (already exists)
│   ├── DECISION_HEURISTICS.md         # When to fix/investigate/escalate
│   └── COMMON_PATTERNS.md             # Known error patterns & solutions
│
├── memory/                            # Session memory (journals)
│   ├── auto_fix_journal_2025-11-01.md
│   ├── auto_fix_journal_2025-10-31.md
│   └── archive/                       # 30+ days old
│
├── reference/                         # Static system knowledge
│   ├── database_schema.md             # Primary database schema
│   ├── sector_archive_schema.md       # Archive database schema
│   ├── system_architecture.md         # High-level system design
│   ├── strategy_guides/
│   │   ├── flow_monitor_guide.md
│   │   ├── option_pipeline_guide.md
│   │   └── earnings_intel_guide.md
│   └── table_relationships.md         # Which tables depend on each other
│
├── context/                           # Dynamic state (prepared before spawn)
│   ├── current_errors.json            # Today's accumulated errors
│   ├── recent_logs_excerpt.txt        # Last 500 lines from key logs
│   ├── database_stats.json            # Row counts, last updates
│   └── system_health.json             # API status, disk space, process status
│
├── tools/
│   ├── prepare_context.py             # Gather system state before spawn
│   └── search_journals.py             # Search past journals for patterns
│
├── logs/                              # Journal files (session memory)
│   └── auto_fix_journal_YYYY-MM-DD.md
│
├── main_fix_launcher.py               # Spawn coordinator (already exists)
├── test_autofix_trigger.py            # Test harness (already exists)
└── IMPLEMENTATION_PLAN.md             # This document
```

### Key Files to Create

**Decision Heuristics** (`instructions/DECISION_HEURISTICS.md`):
```markdown
## When to FIX vs INVESTIGATE vs ESCALATE

**Fix autonomously if:**
- Error has clear pattern in logs
- Fix is localized (<3 files, <50 lines changed)
- No schema changes required
- Similar to problems in journal with successful fixes

**Add diagnostics and DON'T restart if:**
- Root cause unclear from current logs
- Multiple competing hypotheses
- First time seeing this error type

**Escalate to human immediately if:**
- Requires database schema change
- Involves credentials, API keys, or security
- Needs business logic decision
- After 2 failed fix attempts in journal today
```

**Context Preparation** (`tools/prepare_context.py`):
- Database row counts
- Recent log excerpts (last 500 lines)
- System health (disk, memory, CPU)
- Current error summary

---

## How Strategies Self-Monitor

**Each strategy monitors itself, not main.py**

### Flow Monitor Example

**Location:** fm_storage.py (after storing scan results to database)

**Self-Check Logic:**
```
1. Store scan results to flow_options_scans table
2. Query: "SELECT MAX(alert_timestamp) FROM flow_alerts"
3. Calculate: time_since_last_alert
4. If (time_since_last_alert > 2 hours) AND (market_open):
     - Call error_manager.log_error(..., severity='CRITICAL')
     - Error manager checks thresholds
     - Triggers auto-fix spawn if threshold exceeded
5. Flow Monitor continues scanning (non-blocking)
```

**Why here?** Flow Monitor knows its own state best:
- How many alerts generated
- Database write success/failure
- API response quality
- Timing of scans

**Main.py doesn't know these details.** Main.py just coordinates the schedule.

### Option Pipeline Example

**Location:** op_storage.py (after contract collection)

**Self-Check Logic:**
```
1. Collect option contracts for all symbols
2. Store contracts to option_contracts table
3. Count: rows_inserted
4. If (rows_inserted == 0) AND (api_calls_succeeded):
     - CRITICAL: Silent failure (API worked but nothing stored)
     - Trigger auto-fix immediately
5. Continue with rollup operations
```

---

## Two Logging Systems

**Tier 1: Journal (Claude ↔ Claude)**
- Location: `autofix/memory/auto_fix_journal_YYYY-MM-DD.md`
- Purpose: Session memory for iterative debugging
- Audience: Future Claude Code sessions
- Retention: 30 days, then archive
- Updated: End of session, before email

**Tier 2: Detailed Reports (Claude → Human)**
- Location: `logs/claude_fixes_YYYY-MM-DD.md`
- Purpose: Complete technical writeup for audit trail
- Audience: Ben (human)
- Retention: Permanent (version controlled)
- Updated: End of session, before email

---

## Spawn Workflow

### Immediate Mode (Real-Time)

```
12:00 PM - Flow Monitor detects: no alerts in 2 hours

Strategy calls: error_manager.log_error(..., severity='CRITICAL')
↓
Error manager checks: Is this a critical error? Yes
↓
Launcher calls: prepare_context.py (gather diagnostics)
↓
Launcher spawns: Claude Code in new window (autonomous mode)
  - Minimal prompt: "No alerts in 2 hours. Read @AUTO_FIX_INSTRUCTIONS.md"
  - Claude reads instructions, journal, context files
  - Claude investigates in parallel
↓
Flow Monitor continues scanning (non-blocking)
↓
Claude works autonomously:
  - Checks journal (previous attempts today?)
  - Reviews logs and context
  - Identifies root cause
  - Applies fix, creates backup
  - Kills Flow Monitor, restarts with fix
  - Verifies startup, updates journal
  - Emails report
```

### Batch Mode (End of Day)

```
7:00 PM - Main.py daily cycle complete

Main.py calls: error_manager.trigger_batch_review()
↓
Launcher searches logs: grep "[LOGANALYZER-ALERT]" logs/*.log
↓
If errors found:
  - Launcher calls: prepare_context.py
  - Launcher spawns: Claude Code in BATCH mode
↓
Claude reviews overnight:
  - Read all errors from context/current_errors.json
  - Check journal for previous attempts
  - Fix what's fixable (max 5 edits total)
  - Add diagnostics for unclear errors
  - Document what needs human attention
  - Update journal, email report
↓
You wake up to: Email with fixes applied and analysis
```

---

## Decision Heuristics (Not Rigid Taxonomy)

**Philosophy:** Don't pre-define which errors are fixable. Let Claude assess case-by-case.

**Current Design:** Already generic
```python
error_manager.log_error(
    error_type='database_locked',  # Any string works
    context={'query': 'INSERT INTO ...', 'duration': 30},
    severity='CRITICAL'
)
```

Launcher doesn't care what the error is. It spawns Claude with context and says "fix this."

**Claude Self-Assesses:**
1. "Do I understand this error?" (check logs, journal)
2. "Is the fix within my scope constraints?" (3 files, no schema changes)
3. "Have we tried this before?" (check journal)
4. "What's the risk if I'm wrong?" (backups exist, protected files)
5. "Should I fix, investigate, or escalate?"

**Safety comes from constraints, not taxonomy:**
- Protected files (OS-level read-only)
- Session limits (3 edits, 1 restart, 10 minutes)
- Escalation (3 attempts then human)
- Mandatory backups before edits
- Process validation before killing

---

## Infrastructure Buildout

### Phase 1: Organize Knowledge Base (NOW)

1. **Create directory structure:**
   ```
   mkdir autofix/reference
   mkdir autofix/reference/strategy_guides
   mkdir autofix/context
   mkdir autofix/tools
   mkdir autofix/instructions
   ```

2. **Copy reference docs:**
   - Database schema → `reference/database_schema.md`
   - Sector archive schema → `reference/sector_archive_schema.md`
   - System architecture → `reference/system_architecture.md`

3. **Create decision heuristics:**
   - `instructions/DECISION_HEURISTICS.md`

4. **Create strategy guides (can be brief initially):**
   - Flow Monitor overview and common issues
   - Option Pipeline overview and common issues
   - Earnings Intel overview and common issues

### Phase 2: Build Helper Scripts (NEXT)

1. **Context preparation** (`tools/prepare_context.py`):
   - Database stats (row counts, last updates)
   - Recent log excerpts (last 500 lines)
   - System health (disk, memory, CPU, processes)
   - Current error summary

2. **Journal search** (`tools/search_journals.py`):
   - Search past journals for keywords
   - Return relevant entries
   - Useful for pattern detection

### Phase 3: Update Launcher (AFTER PHASE 2)

1. **Add batch mode support:**
   - `launch_auto_fix(error_type, context, mode='immediate')`
   - Different prompts for immediate vs batch
   - Batch mode: review all errors, fix what you can

2. **Call prepare_context.py before spawning:**
   - Ensure context/ directory populated
   - Reference context files in spawn prompt

### Phase 4: Integrate Error Manager (FINAL)

1. **Create centralized error manager** (`tools/error_manager.py`):
   - Accumulate errors throughout day
   - Check thresholds for immediate trigger
   - Trigger batch review at end of day

2. **Update strategies to use error manager:**
   - Flow Monitor: Check for "no alerts in 2 hours"
   - Option Pipeline: Check for "no contracts stored"
   - Replace ad-hoc error handling

---

## Reference Material to Provide

**System Documentation:**
- Database schema (primary and archives)
- System architecture overview
- Strategy guides for each module

**Strategy-Specific:**
- Flow Monitor: How it works, common errors
- Option Pipeline: How it works, common errors
- Earnings Intel: How it works, common errors

**Table Relationships:**
- Which tables depend on each other
- Safe to modify vs critical production tables
- Archive routing logic

**Common Patterns:**
- Duplicate contract handling
- Database locking solutions
- API rate limit handling
- Collection timeout solutions

---

## Current Status

**Completed:**
- ✅ Basic auto-fix system (proven in production 2025-10-31)
- ✅ Spawn launcher with rate limiting
- ✅ Autonomous operation mode
- ✅ Safety constraints (protected files, backups, validations)
- ✅ Error logger with trigger codeword ([LOGANALYZER-ALERT])
- ✅ Log analyzer (already searches for trigger codeword)
- ✅ Journal system design

**In Progress:**
- 🔄 Knowledge base organization (Phase 1)
- 🔄 Reference documentation preparation
- 🔄 Decision heuristics creation

**Not Started:**
- ⏳ Context preparation script
- ⏳ Journal search tool
- ⏳ Batch mode implementation
- ⏳ Centralized error manager
- ⏳ Strategy self-monitoring integration

---

## Key Design Decisions

1. **Use existing [LOGANALYZER-ALERT] codeword** - Already battle-tested
2. **Strategies self-monitor** - They know their state best, not main.py
3. **Generic error handling** - No rigid taxonomy, Claude assesses case-by-case
4. **Decision heuristics over rules** - Guide Claude's judgment, don't restrict
5. **Two-tier logging** - Journal for Claude, detailed reports for humans
6. **Session memory is the killer feature** - Multiple spawns build on each other

---

**Next Steps:**
1. Create directory structure
2. Copy/update reference documentation
3. Write DECISION_HEURISTICS.md
4. Build prepare_context.py helper script
5. Test with simulated errors

---

**Last Updated:** 2025-11-01
**Maintained By:** Ben
