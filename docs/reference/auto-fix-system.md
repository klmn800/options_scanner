# Auto-Fix System: Self-Healing Code via Claude Code Integration

**Status**: ✅ Active Production System (as of 2025-10-31)
**Purpose**: Automated error detection, diagnosis, and repair using Claude Code CLI
**Author**: Ben (with Claude assistance)

---

## Overview

A novel self-healing code system that automatically spawns autonomous Claude Code CLI sessions when runtime errors are detected, providing full diagnostic context and repair capabilities with comprehensive safety constraints.

### Core Concept

When critical errors occur during production operation:

1. **Detect**: Error detection logic identifies the specific issue
2. **Protect**: Immediate safety net prevents crash (e.g., deduplication)
3. **Diagnose**: System gathers comprehensive diagnostic data (logs, duplicate details, context)
4. **Delegate**: Spawns Claude Code CLI in autonomous mode with full diagnostic context
5. **Continue**: System keeps running normally while Claude investigates in parallel
6. **Learn**: Claude checks journal for previous attempts today (session memory)
7. **Repair**: Claude Code analyzes root cause, commits checkpoint, fixes code autonomously
8. **Test**: Claude restarts main.py and verifies startup (60 seconds)
9. **Document**: Updates journal and detailed report logs
10. **Report**: Claude emails final report with root cause analysis and resolution

### Philosophy

Rather than gracefully degrading or requiring human intervention, the system **actively recruits AI assistance** to diagnose and repair issues autonomously. This creates a feedback loop where Claude Code learns from production failures and prevents recurrence.

---

## Current Implementation

### Use Case: Flow Monitor Duplicate Contract Detection

**Problem**: Flow Monitor occasionally generates duplicate contracts during batch data collection, violating SQLite UNIQUE constraints and crashing the system.

**Solution**: Auto-fix system with two-layer protection:

1. **Immediate Safety Net**: Deduplicate batch data before database insert (prevents crash)
2. **Root Cause Investigation**: Spawn Claude Code to find and fix the underlying bug

### File Structure

```
E:\options_scanner\
├── autofix/                              # Auto-fix system home
│   ├── logs/                             # Session memory (journal entries)
│   │   └── auto_fix_journal_YYYY-MM-DD.md   # Daily journal (Claude-to-Claude)
│   ├── AUTO_FIX_INSTRUCTIONS.md          # Standard operating procedures for Claude
│   ├── AUTOFIX_PLAN.md                   # System architecture and migration plan
│   ├── main_fix_launcher.py              # Spawns Claude Code with diagnostics
│   ├── main_fix_test.py                  # Test harness (deprecated - use test_autofix_trigger.py)
│   └── test_autofix_trigger.py           # Test harness for auto-fix system
├── logs/                                 # Detailed reports (Claude-to-Human)
│   ├── claude_fixes_YYYY-MM-DD.md        # Detailed technical writeups
│   ├── autofix_launches.json             # Rate limiting log (last 24 hours)
│   └── orchestrator_YYYY-MM-DD.log       # System logs
├── strategies/flow_monitor/
│   ├── fm_storage.py                     # Trigger point (_trigger_auto_fix() method)
│   └── fm_collector.py                   # Diagnostic logging for duplicate detection
└── docs/reference/
    └── auto-fix-system.md                # This technical reference
```

### Technical Architecture

#### 1. Error Detection (fm_storage.py)

```python
# Deduplicate batch data before INSERT
seen_hashes = set()
deduplicated_data = []
duplicates_found = []

for contract in contracts_data:
    if contract_hash in seen_hashes:
        duplicates_found.append({...})  # Track for diagnostics
    else:
        seen_hashes.add(contract_hash)
        deduplicated_data.append(contract)

if duplicates_found:
    # SAFETY: Use deduplicated data to prevent crash
    contracts_data = deduplicated_data

    # INVESTIGATION: Trigger auto-fix system
    self._trigger_auto_fix({
        'duplicate_count': len(duplicates_found),
        'duplicated_hashes': duplicates_found[:10]
    })
```

#### 2. Claude Code Launcher (autofix/main_fix_launcher.py)

Spawns Claude Code CLI in autonomous mode with minimal prompt that directs Claude to read instruction files.

**Safety Features**:
- **Rate limiting**: Maximum 5 launches per hour (prevents runaway spawning)
- **Launch tracking**: `logs/autofix_launches.json` logs all attempts
- **Autonomous mode**: `--permission-mode bypassPermissions` flag for hands-off operation

**Launch Mechanism**:
```python
# Check rate limit first
allowed, message = check_rate_limit()
if not allowed:
    print("❌ AUTO-FIX BLOCKED: {}".format(message))
    return False

# Check if claude CLI is available
claude_path = shutil.which('claude')
if not claude_path:
    print("❌ ERROR: 'claude' command not found in PATH")
    return False

# Create batch file with minimal escaped prompt
with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as f:
    f.write('@echo off\n')
    f.write('cd /d {}\n'.format(cwd))
    # CRITICAL: Autonomous mode for hands-off operation
    f.write('start "" cmd /k "claude --permission-mode bypassPermissions "{}"\n'.format(batch_escaped_prompt))
    batch_file = f.name

# Execute batch file (spawns new window)
result = subprocess.run(batch_file, shell=True, capture_output=True, encoding='utf-8')

if result.returncode == 0:
    # Log this launch for rate limiting
    log_launch(error_context)
```

**Prompt Format** (~300 characters, minimal for batch compatibility):
```
AUTO-FIX: Duplicate contracts. Read @AUTO_FIX_INSTRUCTIONS.md for protocol.
Main.py PID: 12345. ERROR: 2 duplicates (example: CCCS strike 10.0 expiring 2025-11-21).
Log: @logs/orchestrator_2025-10-31.log.
Suspects: @strategies/flow_monitor/fm_collector.py @strategies/flow_monitor/fm_storage.py.
Fix it.
```

**Key Design Change**: Instead of embedding logs and tasks inline (8000+ chars), the prompt is minimal and directs Claude to:
1. Read `@AUTO_FIX_INSTRUCTIONS.md` for complete protocol
2. Read `@logs/orchestrator_YYYY-MM-DD.log` for diagnostics
3. Check `@autofix/logs/auto_fix_journal_*.md` for previous attempts (session memory)

#### 3. Session Memory (Journal System)

**Purpose**: Allow multiple Claude spawns to learn from each other throughout the day.

**Daily Journal**: `autofix/logs/auto_fix_journal_YYYY-MM-DD.md`
- One journal file per day
- Each Claude session appends entry before emailing
- Future sessions read journal first to see what's been tried

**Entry Format**:
```markdown
## [HH:MM] Error Type - Brief Description

### Quick Summary
- **Trigger**: What caused the spawn
- **Hypothesis**: Root cause theory
- **Action Taken**: What was done
- **Outcome**: Restart successful / Fix applied / Diagnostics added

### Detailed Analysis
Evidence, reasoning, implementation details

### Next Steps
If error recurs → Try X
```

**Search Priority**:
1. Today's journal (most relevant)
2. Last 7 days (recent patterns)
3. Older entries (historical context, may reference outdated code)

**Two-Tier Logging**:
- **Journal** (`autofix/logs/`) - Claude-to-Claude, 30-day retention
- **Detailed Reports** (`logs/claude_fixes_*.md`) - Claude-to-Human, permanent

---

## Safety Constraints

### Protected Resources

**Never Modify**:
- Configuration files: `config.json`, `credentials.json`, `pyproject.toml`
- Claude Code configuration: `.claude/` directory
- Auto-fix system files: `main_fix_launcher.py`, `AUTO_FIX_INSTRUCTIONS.md`, `AUTOFIX_PLAN.md`
- Core libraries: `tradier_api.py`, `timezone_utils.py`, `decimal_formatter.py`
- **Exception**: CAN write to `autofix/logs/auto_fix_journal_*.md`

**Database Protection**:
- Read-only queries to `data/datalake.db`
- Use `data/datalake_query.db` for analysis
- No SQL DELETE, DROP, or TRUNCATE commands
- Never delete database files or backups

### Mandatory Validations

**Before killing main.py**:
```python
import psutil
proc = psutil.Process(pid)
assert 'main.py' in ' '.join(proc.cmdline()), "PID is not main.py!"
assert proc.name() in ['python.exe', 'python', 'pythonw.exe'], "PID is not Python!"
```

**Before restarting**:
- Verify in project root: `os.path.exists('main.py')`
- Check syntax: `python -m py_compile <modified_file>`

### Session Limits

- **Maximum 3 code edits per session** - prevents scope creep
- **Maximum 1 process restart per session** - no repeated loops
- **Maximum 10 minute session time** - prevents hanging
- **Maximum 5 launches per hour system-wide** - rate limiting

### Scope Constraints

- Only fix the specific error that triggered spawn
- No optimization, refactoring, or feature additions
- No broad changes (function renames, signature changes)
- Stay focused on immediate problem

### Audit Trail

All actions logged:
- Launch log: `logs/autofix_launches.json` (last 24 hours)
- Session details: `logs/claude_fixes_YYYY-MM-DD.md`
- Journal entries: `autofix/logs/auto_fix_journal_YYYY-MM-DD.md`

---

## Deployment Status

### Successfully Deployed (2025-10-31)

✅ **First Production Run**: Claude successfully diagnosed and fixed duplicate contract issue
- Root cause identified: Tradier API returning duplicate contracts
- Fix applied: Contract-level deduplication at source
- Process restarted successfully
- Email report sent with complete analysis

### Known Issues: None

Previous issue (Claude Code window not spawning) was resolved by:
1. Reducing prompt length from ~8000 to ~300 characters
2. Moving instructions to `AUTO_FIX_INSTRUCTIONS.md`
3. Proper batch file escaping for Windows command line

---

## Testing

### Test Harness (autofix/test_autofix_trigger.py)

Simulates duplicate contract error without running full main.py:

```bash
python test_autofix_trigger.py
```

**What it tests**:
1. Error context JSON serialization
2. Rate limiting check
3. Launcher script execution
4. Claude Code window spawning in autonomous mode
5. Batch file generation
6. Minimal prompt formatting

**What it provides**:
- Simulated duplicate contracts (TEST, AAPL, NVDA symbols)
- Dummy PID (won't actually kill anything)
- Safe testing without disrupting production

### Production Testing

**Successfully tested** (2025-10-31) with real duplicate contract error:
- ✅ Error detection triggered correctly
- ✅ Claude Code spawned autonomously
- ✅ Root cause identified (Tradier API duplicates)
- ✅ Fix applied (contract-level deduplication)
- ✅ Process restarted successfully
- ✅ Email report sent with analysis

**To trigger again**: Revert Claude's fix in `fm_collector.py` and wait for duplicate error.

---

## Design Principles

### 1. **Fail-Safe First**

Always protect production system before attempting repair:
- Deduplicate data to prevent crash
- Let system continue running (no shutdown)
- Non-blocking parallel investigation
- Extensive error handling and logging

### 2. **Minimal Context, Maximum Reference**

Provide Claude with directions, not inline data:
- Minimal prompt (~300 chars) to avoid Windows command line limits
- Direct Claude to read instruction files (`@AUTO_FIX_INSTRUCTIONS.md`)
- Reference log files instead of embedding excerpts
- Check journal for previous attempts (session memory)

### 3. **Autonomous Within Guardrails**

Full autonomy with comprehensive safety constraints:
- `--permission-mode bypassPermissions` for hands-off operation
- Protected files list (config, credentials, core libraries)
- Rate limiting (5 launches/hour max)
- Session limits (3 edits, 1 restart, 10 minutes)
- Mandatory validations before killing processes
- Syntax checks before restarting

### 4. **Parallel Investigation**

Investigate root cause without disrupting production:
- System continues running while Claude works
- Deduplication safety net prevents crashes
- Claude kills/restarts main.py when ready
- Log every action for audit trail

### 5. **Session Memory**

Enable learning across multiple spawns:
- Daily journal files in `autofix/logs/`
- Each Claude session appends findings
- Future sessions read journal first
- Build on previous hypotheses and diagnostics
- 30-day retention before archiving

### 6. **Human Oversight**

Final report via email ensures human visibility:
- Root cause hypothesis (not claims of "fixed")
- Code changes made with file references
- Restart status
- What to try next if error recurs

This creates accountability loop while maintaining autonomy.

---

## Completed Features (2025-10-31)

✅ **Autonomous Operation** - `--permission-mode bypassPermissions` flag with 15s auto-accept
✅ **Intelligent Rate Limiting** - 5 launches/hour with progress-based bypass
✅ **Failure Escalation** - 3 attempts/day max per error type, then urgent human alert
✅ **Session Memory** - Daily journal system for learning across spawns
✅ **Protected File List** - Instructional constraints for config, core libs, databases
✅ **Mandatory Backups** - Claude must backup before editing (timestamped naming)
✅ **Safety Constraints** - Protected files, validations, scope limits
✅ **Minimal Prompt** - Reduced from 8000 to 300 chars with journal enforcement
✅ **Standing Instructions** - `AUTO_FIX_INSTRUCTIONS.md` with complete protocol
✅ **Launch Reliability** - Resolved spawning issues with proper escaping
✅ **Generic Error Support** - Works with any error type, not hardcoded to duplicates

## Future Enhancements

### 1. File Migration

**Status**: Ready to migrate but pending testing

**Files to move**:
- `main_fix_launcher.py` → `autofix/`
- `test_autofix_trigger.py` → `autofix/`
- Update references in fm_storage.py

### 2. Expand Error Coverage

The auto-fix pattern is now **generic** and can be applied to other error types.

**Example: Database Locking**
```python
self._trigger_auto_fix({
    'error_type': 'database_locked',
    'query': 'INSERT INTO flow_options_scans ...',
    'lock_duration_seconds': 30,
    'retry_attempts': 5
})
```

**Example: API Rate Limit**
```python
self._trigger_auto_fix({
    'error_type': 'api_rate_limit',
    'endpoint': '/options/chains',
    'status_code': 429,
    'retry_after_seconds': 60
})
```

**Example: Collection Timeout**
```python
self._trigger_auto_fix({
    'error_type': 'collection_timeout',
    'symbol': 'AAPL',
    'timeout_seconds': 120,
    'worker_count': 10
})
```

**How It Works**:
- System automatically handles any `error_type` string
- Escalation tracking is per error type (3 attempts/day each)
- Prompt formats error type as display name ("Database Locked")
- All custom fields are passed to Claude in the prompt
- No launcher code changes needed!

### 3. Enhanced Diagnostics

**System State Capture**:
- Database row counts before/after
- Process tree snapshot
- Memory/CPU usage at error time
- Network request history

**Pattern Detection**:
- Analyze journals to find frequently recurring errors
- Identify symbols that cause problems
- Track fix success rates
- Most common error types

**Journal Search Tool**:
```bash
python autofix/search_journals.py "duplicate contracts"
# Returns all journal entries mentioning that error
```

### 4. Auto-Archive Old Journals

After 30 days, compress to `autofix/logs/archive/YYYY-MM.tar.gz`

---

## Dependencies

### Required Packages
- `subprocess` - Spawning Claude Code and batch files
- `tempfile` - Temporary batch file creation
- `json` - Error context serialization

### External Dependencies
- **Claude Code CLI** - Must be installed globally:
  ```bash
  npm install -g @anthropics/claude-code
  ```
- **Windows cmd.exe** - For batch file execution
- **Email configuration** - For final reports (tools/email_notifier.py)

### Environment Requirements
- Windows OS (batch file approach)
- Claude Code CLI in PATH
- SMTP credentials configured (for email reports)

---

## Security Considerations

### Authority Granted to Claude

When auto-fix triggers, Claude Code receives **autonomous operation** with:
- **Read access**: All project files
- **Write access**: Strategy code in `strategies/` directory only (protected files enforced via instructions)
- **Execute access**: Can run scripts and restart main.py (with validations)
- **Database access**: Read-only queries to `datalake_query.db`

### Safety Constraints (Multi-Layered)

**Layer 1: Protected File List (Instructional)**

Protected files are listed in `AUTO_FIX_INSTRUCTIONS.md` and must not be modified:
- Configuration: `config.json`, `credentials.json`, `pyproject.toml`
- Claude Code config: All files in `.claude/`
- Auto-fix system: `main_fix_launcher.py`, `AUTO_FIX_INSTRUCTIONS.md`, `AUTOFIX_PLAN.md`
- Core libraries: Everything in `core/`, `tools/timezone_utils.py`, `tools/decimal_formatter.py`, `tools/email_notifier.py`
- Databases: All `.db`, `.db-wal`, `.db-shm` files in `data/`
- Main orchestrator: `main.py`

**Result**: Claude follows the protected file list in instructions. Violations would be caught in code review and email reporting.

**Layer 2: Mandatory Backups (Recovery)**

Claude must create timestamped backups before editing:
- Format: `{filename}.autofix_backup_{YYYYMMDD_HHMMSS}.{ext}`
- Example: `fm_collector.autofix_backup_20251031_143025.py`
- Backups are never deleted (future sessions can reference them)
- Manual recovery: Copy backup over original file

**Layer 3: Failure Escalation (Circuit Breaker)**

3 attempts per error type per day:
- Attempt 1: LOW risk - explore freely
- Attempt 2: MEDIUM risk - focus on what was missed
- Attempt 3: HIGH risk - last chance before human escalation
- After 3rd: Urgent email with journal, no more spawns today

**Layer 4: Intelligent Rate Limiting (Progress Detection)**

5 launches per hour with smart bypass:
- Allows if last launch was successful (verified)
- Allows if last launch added diagnostics (making progress)
- Blocks repeated failures (no progress detected)

**Layer 5: Session Constraints (Scope Control)**

- Maximum 3 code edits per session (prevents scope creep)
- Maximum 1 process restart per session (no loops)
- Maximum 10 minute session time (prevents hanging)
- Only fix the triggering error (no optimization/refactoring)

**Layer 6: Mandatory Validations (Safety Checks)**

Before killing main.py:
```python
import psutil
proc = psutil.Process(pid)
assert 'main.py' in ' '.join(proc.cmdline())
assert proc.name() in ['python.exe', 'python', 'pythonw.exe']
```

Before restarting:
```bash
python -m py_compile <modified_file>  # Syntax check
```

### Safeguards Summary

1. **Protected File List**: Instructional constraints prevent editing critical files
2. **Mandatory Backups**: Every edit creates timestamped backup
3. **Escalation Protocol**: 3 strikes then human intervention
4. **Intelligent Rate Limits**: Distinguishes productive vs unproductive attempts
5. **Session Memory**: Learn from previous attempts, don't repeat mistakes
6. **Process Validation**: Can't accidentally kill wrong process
7. **Syntax Validation**: Catches errors before restart
8. **Scope Enforcement**: No broad refactoring allowed
9. **Audit Trail**: Complete logging in multiple locations
10. **Human Oversight**: Email after every session

### Risk Assessment

**Minimal Risk**:
- ✅ Protected files enforced via instructions (Claude follows consistently)
- ✅ All edits backed up automatically (timestamped recovery points)
- ✅ Escalation prevents infinite retry loops (3 attempts max)
- ✅ Rate limiting prevents runaway spawning (5/hour intelligent)
- ✅ Triggers only on detected errors (not proactively)
- ✅ Code changes logged and reviewable (email reports)
- ✅ System continues running (deduplication safety net)
- ✅ Database is read-only for Claude
- ✅ Daily backups provide additional recovery

**Trust Model**: "Autonomous within guardrails" - Claude operates hands-off following instructional constraints and session limits.

---

## Changelog

### 2025-10-31 - Initial Development & Enhancement

**Morning**: Initial implementation
- Duplicate contract detection and auto-fix trigger
- Batch data deduplication (immediate crash prevention)
- Comprehensive diagnostic prompt for Claude (8000+ chars)
- Email report requirement in task list
- Claude CLI availability check (`shutil.which()`)

**Afternoon**: Refinements and fixes
- Removed PID detection and auto-shutdown logic (too aggressive)
- System now continues running while Claude investigates in parallel
- Reduced prompt to ~300 characters (Windows command line limit issue)
- Created `AUTO_FIX_INSTRUCTIONS.md` with standing instructions
- Fixed batch file escaping for proper Claude Code spawning

**Evening**: Safety features and architecture
- Added autonomous operation mode (`--permission-mode bypassPermissions`)
- Implemented basic rate limiting (5 launches/hour max)
- Created comprehensive safety constraints (protected files, validations)
- Designed journal system for session memory
- Organized files into `autofix/` directory structure
- Documented complete system in `autofix/AUTOFIX_PLAN.md`

**First Production Run**: Successfully deployed ✅
- Claude Code spawned autonomously
- Root cause identified (Tradier API duplicates)
- Fix applied (contract-level deduplication)
- Process restarted successfully
- Email report sent with complete analysis

**Late Evening**: Major enhancements (analyst recommendations)
- Implemented read-only file protection (OS-level, broad coverage)
- Added mandatory backup creation before editing (timestamped)
- Implemented failure escalation protocol (3 attempts/day max per error type)
- Enhanced rate limiting with intelligent progress detection
- Journal checking enforced in spawn prompt (Step 0: MANDATORY)
- Automated keystroke acceptance (15s wait, "2" + Enter)
- Made system generic (supports any error type, not just duplicates)
- Updated AUTO_FIX_INSTRUCTIONS.md with complete workflow
- Multi-layered security (6 layers of protection)

---

## References

- **User Documentation**: `AUTO_FIX_SYSTEM.md` (root directory)
- **Technical Reference**: This document (`docs/reference/auto-fix-system.md`)
- **Standard Operating Procedures**: `autofix/AUTO_FIX_INSTRUCTIONS.md`
- **Architecture Plan**: `autofix/AUTOFIX_PLAN.md`
- **Test Script**: `autofix/test_autofix_trigger.py`
- **Launcher Implementation**: `autofix/main_fix_launcher.py`
- **Trigger Logic**: `strategies/flow_monitor/fm_storage.py` (line 116+)
- **Email Notifier**: `tools/email_notifier.py`

---

## Conclusion

The auto-fix system represents a novel approach to production error handling: **delegate diagnosis and repair to autonomous AI** rather than gracefully degrading or requiring human intervention.

**Successfully deployed** (2025-10-31) with comprehensive safety constraints that prevent catastrophic decisions while allowing intelligent bug fixes. The combination of fail-safe deduplication, minimal prompts with file references, autonomous operation, session memory, and rate limiting creates a robust self-healing feedback loop.

**Key Innovation**: Autonomous operation within guardrails - Claude operates hands-off with `--permission-mode bypassPermissions` but cannot modify protected files, has rate limits, session limits, and mandatory validations.

**Production Ready**: ✅
- Spawning issue resolved (prompt length reduction)
- End-to-end workflow tested successfully
- Email report generation verified
- Safety constraints prevent runaway behavior

**Next Steps**:
1. Integrate journal system into AUTO_FIX_INSTRUCTIONS.md workflow
2. Test session memory with multiple spawns in same day
3. Expand pattern to other error types (database locking, API rate limits)
4. Monitor long-term effectiveness and fix success rates

---

**Last Updated**: 2025-10-31
**Maintainer**: Ben
**Status**: ✅ Active Production System
