"""Write guard hook for Trading Advisor.

Allows file writes only within the agents/trading_advisor/ workspace.
Blocks writes to any other location with contextual guidance.

This script lives OUTSIDE the trading_advisor workspace intentionally —
the agent cannot edit its own guard.

Receives hook JSON on stdin, outputs permission decision to stdout.
"""
import json
import os
import sys

ALLOWED_PREFIX = os.path.normpath("E:/options_scanner/agents/trading_advisor").lower()
PROJECT_PREFIX = os.path.normpath("E:/options_scanner").lower()

# Reference library is read-only to TA (since 2026-05-17, Proposal 027).
# New patterns/lessons must come from MA via the graduation gate (Ben copies
# from agents/market_analyst/reference/staging/ to here). Prompt discipline
# alone wasn't enough — TA noticed itself reflex-writing during morning sessions.
TA_REFERENCE_PREFIX = os.path.normpath(
    "E:/options_scanner/agents/trading_advisor/reference"
).lower()

# Additional paths the trading advisor may write to (Ben-approved exceptions)
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

# Block writes to reference/ FIRST (subset of ALLOWED_PREFIX, so check before allow).
# Read-only post-MA-split: graduation flows from MA's staging through Ben.
if normalized.startswith(TA_REFERENCE_PREFIX):
    reason = (
        "BLOCKED: reference/ is read-only since the MA split (2026-05-17, Proposal 027). "
        "New patterns, lessons, mechanics, and case studies come from MA via the "
        "graduation gate — Ben promotes them from agents/market_analyst/reference/staging/. "
        "If you've noticed something worth documenting, write it to "
        "E:\\options_scanner\\agents\\trading_advisor\\memory\\for_market_analyst.md instead "
        "(e.g., 'noticed X, worth validating'). MA will research it, stage it, and Ben "
        "will graduate the validated version back into reference/."
    )
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }, sys.stdout)
    sys.exit(0)

# Allow: own workspace (minus reference/), Claude Code auto-memory, roundtable result files
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
            "in E:\\options_scanner\\agents\\trading_advisor\\ (memory/, reference/, analysis/). "
            "Write there instead."
        )

    # CLAUDE.md or settings files
    if 'claude.md' in p or 'settings' in p:
        return (
            "System configuration files (CLAUDE.md, settings) are managed by Ben in "
            "his main Claude Code session. If you need a config change, tell Ben what "
            "you want and why."
        )

    # System analyst workspace
    if 'system_analyst' in p:
        return (
            "That's the System Analyst's workspace — a different agent. To send it "
            "information, write to your outbound mailbox at "
            "E:\\options_scanner\\agents\\trading_advisor\\memory\\for_system_analyst.md."
        )

    # Production code
    if p.endswith('.py'):
        return (
            "Trading Advisor is a market analyst, not a developer. You cannot modify "
            "production code. If you've found a bug or want a feature, document it in "
            "your workspace (e.g. agents/trading_advisor/memory/) and tell Ben."
        )

    # Data files
    if 'data' in p and (p.endswith('.db') or 'datalake' in p):
        return (
            "Database files are read-only for you. Use direct_db_query.py to read. "
            "If you need data written somewhere, ask Ben."
        )

    # Anything else in the project
    if p.startswith(PROJECT_PREFIX):
        return (
            "Trading Advisor can only write inside its own workspace at "
            "E:\\options_scanner\\agents\\trading_advisor\\. Try memory/, reference/, or "
            "analysis/ depending on what you're storing."
        )

    # Completely outside the project
    return (
        "That path is outside the project entirely. Your workspace is "
        "E:\\options_scanner\\agents\\trading_advisor\\ — write there instead."
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
