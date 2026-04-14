# Meta-AI System

**Autonomous AI development pipeline for the options scanner project**

## Overview

The Meta-AI system orchestrates multiple AI agents to handle development tasks autonomously - strategic planning, quality review, implementation, and reporting - all while you sleep.

**Status:** 🔬 Research & Design Phase
**Proven Concept:** Self-healing error detection and autonomous bug fixing (10/17/2025)

## Directory Structure

```
tools/meta/
├── __init__.py                    # Package initialization
├── README.md                      # This file
├── auto_fix_manager.py            # State management for self-healing
├── log_analyzer_autofix.py        # Error detection and Claude spawning
├── test_self_healing.py           # POC test script
└── docs/
    ├── vision.md                  # Complete vision and architecture
    ├── self-healing-poc.md        # Self-healing system documentation
    └── ai-task-spawning.md        # AI task spawning patterns
```

## Quick Start - Test the Self-Healing System

```bash
# 1. Run the buggy test script
python tools/meta/test_self_healing.py

# 2. Detect and auto-fix the error
python tools/meta/log_analyzer_autofix.py --hours 1

# 3. Approve Claude's fix in the spawned window

# 4. Verify the fix works
python tools/meta/test_self_healing.py
```

See `docs/self-healing-poc.md` for complete testing guide.

## Components

### Auto-Fix Manager (`auto_fix_manager.py`)
Prevents infinite loops and enforces safety limits:
- Max 3 attempts per unique error
- 5-minute cooldown between attempts
- Circuit breaker after consecutive failures
- Human override support

**CLI:**
```bash
python tools/meta/auto_fix_manager.py --status    # Check system status
python tools/meta/auto_fix_manager.py --disable   # Manual override
python tools/meta/auto_fix_manager.py --enable    # Re-enable
```

### Log Analyzer with Auto-Fix (`log_analyzer_autofix.py`)
Detects critical errors and spawns Claude Code to fix them:
- Scans logs for `[LOGANALYZER-ALERT]` trigger
- Extracts error context
- Checks safety limits
- Spawns Claude Code with fix instructions

**Usage:**
```bash
python tools/meta/log_analyzer_autofix.py --hours 1    # Scan last hour
python tools/meta/log_analyzer_autofix.py --no-spawn   # Detect only
```

### Test Script (`test_self_healing.py`)
Deliberately fails to test the auto-fix system:
- Simulates division-by-zero error
- Logs with alert trigger
- Waits for autonomous fix

## Vision

The Meta-AI system will eventually:

1. **Analyze** codebase nightly (AI Product Manager)
2. **Review** tasks for safety (AI Tech Lead)
3. **Execute** approved changes (AI Engineer via Claude Code)
4. **Report** results each morning (AI Reporter)

**Your Role:** Strategic director who reviews and approves
**AI Role:** Implementation team that executes and reports

## Documentation

- **Vision & Architecture:** `docs/vision.md` - Complete system design
- **Self-Healing POC:** `docs/self-healing-poc.md` - Proven implementation
- **Task Spawning Patterns:** `docs/ai-task-spawning.md` - Broader use cases

## Safety First

All Meta-AI work is:
- ✅ Reviewed before deployment
- ✅ Sandboxed execution
- ✅ Read-only access to production data
- ✅ Rollback-ready
- ✅ Human approval gates

## Next Steps

Review `docs/vision.md` for the full roadmap and discuss:
- Safety framework details
- Task scope limits
- Approval workflows
- Learning mechanisms

---

**Questions or feedback?** This is genuinely novel work. Let's iterate and make it bulletproof before expanding beyond error-fixing.
