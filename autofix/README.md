# Autofix — Self-Healing Error System

Autofix is the autonomous error detection and repair system for the Options Scanner. When production errors occur, it queues them and spawns Claude Code sessions to diagnose and fix them without human intervention.

**In production since November 2025.**

---

## How It Works

```
Error occurs in production code
    ↓
Code calls queue_error() or handle_error() from tools/autofix.py
    ↓
Error written to autofix/errors/errors_YYYY-MM-DD.json
    ↓
Route based on severity:
    ├─ CRITICAL → Spawn Claude Code immediately → Fix → Restart → Email report
    └─ ERROR    → Queue for end-of-day batch mode → Fix → Email report
```

### Two Modes

**Immediate Mode** — For CRITICAL errors (system can't function). Spawns a Claude Code session in a new terminal window within seconds. The calling process exits, Claude fixes the code, restarts `main.py`, and emails a report.

**Batch Mode** — For non-critical ERRORs (system degraded but operational). Errors queue throughout the day. At end-of-day (~7:30 PM weekdays, ~10 PM Fridays), `main.py` triggers batch processing: deduplicates errors by type, then spawns one sequential Claude session per unique error.

---

## Quick Start — Adding Autofix to Your Code

```python
# Non-critical errors (queued for end-of-day batch review)
from tools.autofix import queue_error

queue_error(
    error_type='descriptive_error_name',
    context={'error': str(e), 'details': 'relevant diagnostic data'},
    severity='ERROR'
)

# Critical errors (immediate spawn + process exit)
from tools.autofix import handle_error
import os

handle_error(
    error_type='descriptive_error_name',
    context={'error': str(e), 'traceback': traceback.format_exc()},
    severity='CRITICAL',
    main_py_pid=os.getppid()
)
# handle_error() calls sys.exit(1) for CRITICAL — execution stops here
```

**Use CRITICAL when:** Zero data collected, database table missing, module import failure, API auth failure.
**Use ERROR when:** High failure rate, non-essential data missing, performance degradation.
**Use WARNING when:** Non-critical operational issues (news API hiccup, watchlist cleanup failure). Reviewed by batch mode on first occurrence.

### Transient Error Filtering

Some errors are known to self-heal on the next cycle (e.g., database lock contention during market hours, transient memory pressure). These are tagged with `error_category` in their context dict and filtered by `batch_mode_tracker.py`:

- **Transient categories**: `lock_error`, `memory_error`
- **Behavior**: Silently skipped by batch mode (no autofix session spawned)
- **Escalation**: If the same `error_type` recurs **3+ times in one day**, it's escalated for batch review — that's a pattern, not a fluke

To mark your error as transient, include `error_category` in the context:
```python
queue_error(
    error_type='my_sync_failed',
    context={'error_category': 'lock_error', 'error': str(e)},
    severity='WARNING'
)
```

Errors without a transient `error_category` (including all other WARNINGs) are always reviewed by batch mode.

---

## Directory Structure

```
autofix/
├── README.md                  ← You are here
├── AUTOFIX_WORKFLOW.md        ← Mermaid flowchart of the complete lifecycle
├── AUTOFIX_INTEGRATION_AUDIT.md ← Tracks which scripts have autofix coverage
│
├── instructions/              ← What spawned Claude sessions read
│   ├── AUTO_FIX_INSTRUCTIONS.md    ← Immediate mode: fix protocol
│   ├── BATCH_MODE_INSTRUCTIONS.md  ← Batch mode: review protocol
│   └── DECISION_HEURISTICS.md      ← Fix vs. investigate vs. escalate
│
├── reference/                 ← Static knowledge base for spawned agents
│   ├── AUTOFIX_CHEAT_SHEET.md      ← Comprehensive quick reference
│   ├── system_architecture.md      ← System overview for context
│   ├── database_schema.md          ← Schema reference
│   └── strategy_guides/            ← Per-strategy technical guides
│
├── errors/                    ← Daily error queues (source of truth)
│   └── errors_YYYY-MM-DD.json     ← One file per day
│
├── context/                   ← Batch mode context files
│   └── batch_context_YYYY-MM-DD.json
│
├── logs/                      ← Session artifacts
│   ├── auto_fix_journal_*.md       ← Immediate mode work logs
│   ├── batch_prompt_*_NN.txt       ← Prompts sent to batch sessions
│   ├── immediate_prompt_*_NN.txt   ← Prompts sent to immediate sessions
│   └── .batch_complete_*_NN.marker ← Sequential completion markers
│
├── main_fix_launcher.py       ← Immediate mode spawner
├── batch_mode_spawner.py      ← Batch mode spawner
├── batch_mode_tracker.py      ← Error discovery and coordination
│
└── deprecated/                ← Historical sandbox development artifacts
```

The core API lives in `tools/autofix.py` (not in this directory).

---

## Key Files

| File | Purpose |
|------|---------|
| **`tools/autofix.py`** | Core API: `queue_error()`, `handle_error()`, `mark_error_fixed()`, `check_and_spawn_batch_mode()` |
| `autofix/main_fix_launcher.py` | Builds diagnostic prompt, launches Claude Code for immediate fixes |
| `autofix/batch_mode_spawner.py` | Builds context, launches sequential Claude sessions for batch fixes |
| `autofix/batch_mode_tracker.py` | `find_todays_errors()`, `should_skip_batch_mode()` |

---

## Safety Rails

- **Rate limit**: Max 5 spawns/hour (immediate mode)
- **Escalation**: Max 3 attempts per error type per day, then human notified via email
- **Archive protection**: Never kills `main.py` during archive/backup operations
- **Backups**: Creates `.autofix_backup_*` file backups before editing any code
- **Deduplication**: 100 identical errors → 1 fix session (batch mode)

---

## For More Detail

- **Comprehensive reference**: `autofix/reference/AUTOFIX_CHEAT_SHEET.md`
- **Visual workflow**: `autofix/AUTOFIX_WORKFLOW.md`
- **Integration status**: `autofix/AUTOFIX_INTEGRATION_AUDIT.md`
- **CLAUDE.md**: Has an "Autofix" section with integration instructions for developers
