"""Write guard hook for Earnings Researcher agent.

Allows file writes only within the agents/earnings_researcher/ workspace.
Blocks writes to any other location with contextual guidance.

This script lives OUTSIDE the agent workspace intentionally --
the agent cannot edit its own guard.

Receives hook JSON on stdin, outputs permission decision to stdout.
"""
import json
import os
import sys

ALLOWED_PREFIX = os.path.normpath("E:/options_scanner/agents/earnings_researcher").lower()
PROJECT_PREFIX = os.path.normpath("E:/options_scanner").lower()

# Additional paths the agent may write to
AUTO_MEMORY_PREFIX = os.path.normpath(
    "C:/Users/TRO/.claude/projects/E--options-scanner/memory"
).lower()

hook_input = json.load(sys.stdin)
tool_input = hook_input.get("tool_input", {})
file_path = tool_input.get("file_path", "")

normalized = os.path.normpath(file_path).lower()

# Allow: own workspace, Claude Code auto-memory
if (normalized.startswith(ALLOWED_PREFIX)
        or normalized.startswith(AUTO_MEMORY_PREFIX)):
    json.dump({}, sys.stdout)
    sys.exit(0)


def guidance(path):
    """Return targeted guidance based on what the agent tried to write."""
    p = path.lower()

    if 'claude.md' in p or 'settings' in p:
        return (
            "System configuration files are managed by Ben. "
            "Write your findings to memory/research_log.md instead."
        )

    if p.endswith('.py'):
        return (
            "Earnings Researcher cannot modify code. "
            "Use the CLI tools (earnings_confirm.py, direct_db_query.py) "
            "to write to databases. Log findings to memory/research_log.md."
        )

    if 'data' in p and (p.endswith('.db') or 'datalake' in p):
        return (
            "Cannot write to databases directly. Use the CLI tools: "
            "python E:\\options_scanner\\tools\\earnings_confirm.py for confirmations, "
            "python E:\\options_scanner\\tools\\direct_db_query.py for other updates."
        )

    if 'system_analyst' in p or 'trading_advisor' in p:
        return "That's another agent's workspace. Write to your own workspace instead."

    if p.startswith(PROJECT_PREFIX):
        return (
            "Earnings Researcher can only write inside its own workspace at "
            "E:\\options_scanner\\agents\\earnings_researcher\\. "
            "Use memory/research_log.md for findings, analysis/ for outputs."
        )

    return (
        "That path is outside the project. Your workspace is "
        "E:\\options_scanner\\agents\\earnings_researcher\\ -- write there instead."
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
