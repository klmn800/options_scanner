"""Write guard hook for Market Analyst.

Allows file writes only within the agents/market_analyst/ workspace.
Blocks writes to any other location with contextual guidance.

This script lives OUTSIDE the market_analyst workspace intentionally —
the agent cannot edit its own guard.

Receives hook JSON on stdin, outputs permission decision to stdout.
"""
import json
import os
import sys

ALLOWED_PREFIX = os.path.normpath("E:/options_scanner/agents/market_analyst").lower()
PROJECT_PREFIX = os.path.normpath("E:/options_scanner").lower()

# Additional paths the market analyst may write to (Ben-approved exceptions)
AUTO_MEMORY_PREFIX = os.path.normpath(
    "C:/Users/TRO/.claude/projects/E--options-scanner/memory"
).lower()

# Roundtable state dir — orchestrator polls per-turn result JSON files here.
# Only the state subtree is writable; transcripts/ and logs/ stay orchestrator-owned.
ROUNDTABLE_STATE_PREFIX = os.path.normpath(
    "E:/options_scanner/agents/roundtable/state"
).lower()

hook_input = json.load(sys.stdin)
tool_input = hook_input.get("tool_input", {})
file_path = tool_input.get("file_path", "")

normalized = os.path.normpath(file_path).lower()

# Allow: own workspace, Claude Code auto-memory, roundtable result files
if (normalized.startswith(ALLOWED_PREFIX)
        or normalized.startswith(AUTO_MEMORY_PREFIX)
        or normalized.startswith(ROUNDTABLE_STATE_PREFIX)):
    json.dump({}, sys.stdout)
    sys.exit(0)


def guidance(path):
    """Return targeted guidance based on what the agent tried to write."""
    p = path.lower()

    # Claude Code auto-memory
    if '.claude' in p and 'memory' in p:
        return (
            "That path is Claude Code's auto-memory directory — it's managed by the "
            "agent layer across all sessions, not by you. Your persistent state belongs "
            "in E:\\options_scanner\\agents\\market_analyst\\ (memory/, reference/, analysis/). "
            "Write there instead."
        )

    # CLAUDE.md or settings files
    if 'claude.md' in p or 'settings' in p:
        return (
            "System configuration files (CLAUDE.md, settings) are managed by Ben. "
            "If you need a config change, write a note in notes_for_ben.md."
        )

    # Trading Advisor workspace
    if 'trading_advisor' in p:
        return (
            "That's the Trading Advisor's workspace. To send TA information, write to "
            "your outbound mailbox at E:\\options_scanner\\agents\\market_analyst\\memory\\for_trading_advisor.md. "
            "Promoted reference docs go through staging (reference/staging/) and Ben's "
            "graduation gate, not direct writes."
        )

    # System Analyst workspace
    if 'system_analyst' in p:
        return (
            "That's the System Analyst's workspace. To send SA information, write to "
            "your outbound mailbox at E:\\options_scanner\\agents\\market_analyst\\memory\\for_system_analyst.md."
        )

    # Production code
    if p.endswith('.py'):
        return (
            "Market Analyst is a researcher, not a developer. You cannot modify "
            "production code. If you find a system issue, write to "
            "memory/for_system_analyst.md (SA writes proposals). For your own "
            "analysis scripts, use your tools/ directory."
        )

    # Data files
    if 'data' in p and (p.endswith('.db') or 'datalake' in p):
        return (
            "Database files are read-only for you. Use direct_db_query.py to read."
        )

    # Anything else in the project
    if p.startswith(PROJECT_PREFIX):
        return (
            "Market Analyst can only write inside its own workspace at "
            "E:\\options_scanner\\agents\\market_analyst\\. Try memory/, reference/, or "
            "analysis/ depending on what you're storing."
        )

    # Completely outside the project
    return (
        "That path is outside the project entirely. Your workspace is "
        "E:\\options_scanner\\agents\\market_analyst\\ — write there instead."
    )


reason = "BLOCKED: " + guidance(file_path)

json.dump({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason
    }
}, sys.stdout)

sys.exit(0)
