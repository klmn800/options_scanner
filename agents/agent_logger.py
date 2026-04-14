#!/usr/bin/env python3
"""
Agent Logger (agent_logger.py)
-------------------------------
Console and file logging for Flow Tracker Agent.

Logs agent sessions with emojis to console and detailed
markdown logs to logs/agent_sessions/fm_agent_YYYY-MM-DD.md

Author: Ben (with assistance from Claude)
Date: 2026-01-01
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Import timezone utilities
import os
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'tools'))
from timezone_utils import now_eastern, eastern_isoformat


class AgentLogger:
    """Dual console + file logger for agent sessions"""

    def __init__(self, session_name: str = "fm_agent"):
        """Initialize agent logger

        Args:
            session_name: Name for this logging session (default: "fm_agent")
        """
        # UTF-8 stdout for Windows emoji support (MANDATORY per CLAUDE.md)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')

        self.session_name = session_name
        self.session_start = now_eastern()

        # Create log directory
        self.log_dir = project_root / 'logs' / 'agent_sessions'
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Log file path: logs/agent_sessions/fm_agent_YYYY-MM-DD.md
        date_str = self.session_start.strftime('%Y-%m-%d')
        self.log_file = self.log_dir / f"{session_name}_{date_str}.md"

        # Set up loggers
        self.logger = logging.getLogger(f'agent.{session_name}')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # Clear existing handlers

        # Console handler with emojis
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # File handler with UTF-8 encoding (MANDATORY per CLAUDE.md)
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Session state
        self.round_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.tool_calls = []

        # Write session header
        self._write_session_header()

        self.logger.info(f"🤖 Agent session started: {eastern_isoformat()}")

    def _write_session_header(self):
        """Write markdown header to log file"""
        header = f"""# {self.session_name.upper()} - Agent Session Log

**Session Start:** {eastern_isoformat()}
**Log File:** {self.log_file}

---

"""
        # Write directly to file (not through logger to avoid duplication)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(header)

    def log_user_prompt(self, prompt: str):
        """Log user prompt that kicks off agent processing

        Args:
            prompt: User/system prompt for agent
        """
        self.logger.info(f"\n💭 User Prompt:\n{prompt}\n")

        # Write to markdown
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"## User Prompt\n\n```\n{prompt}\n```\n\n")

    def log_system_prompt(self, prompt: str):
        """Log system prompt (first time only)

        Args:
            prompt: System prompt defining agent behavior
        """
        # Only log to file (too verbose for console)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"## System Prompt\n\n```\n{prompt[:500]}...\n```\n\n")

    def log_round_start(self, round_num: int):
        """Log start of tool use round

        Args:
            round_num: Round number (1-indexed)
        """
        self.round_count = round_num
        self.logger.info(f"\n🔄 Round {round_num}")

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"### Round {round_num}\n\n")

    def log_tool_call(self, tool_name: str, tool_input: Dict[str, Any]):
        """Log agent tool call

        Args:
            tool_name: Name of tool being called
            tool_input: Input parameters for tool
        """
        self.logger.info(f"🔧 Tool call: {tool_name}")

        # Track call
        self.tool_calls.append({
            'round': self.round_count,
            'tool': tool_name,
            'input': tool_input,
            'timestamp': eastern_isoformat()
        })

        # Write to markdown
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"**Tool:** `{tool_name}`\n\n")
            f.write(f"**Input:**\n```json\n{self._format_dict(tool_input)}\n```\n\n")

    def log_tool_result(self, tool_name: str, result: Any, error: Optional[str] = None):
        """Log tool execution result

        Args:
            tool_name: Name of tool that was executed
            result: Result returned by tool
            error: Error message if tool failed
        """
        if error:
            self.logger.warning(f"⚠️  Tool error: {error[:100]}")
            status_emoji = "❌"
        else:
            self.logger.debug(f"✅ Tool result: {str(result)[:100]}...")
            status_emoji = "✅"

        # Write to markdown
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"**Result:** {status_emoji}\n\n")
            if error:
                f.write(f"```\nERROR: {error}\n```\n\n")
            else:
                # Format result based on type
                if isinstance(result, list):
                    f.write(f"Returned {len(result)} row(s)\n\n")
                elif isinstance(result, dict):
                    f.write(f"```json\n{self._format_dict(result)}\n```\n\n")
                else:
                    f.write(f"```\n{str(result)[:500]}\n```\n\n")

    def log_agent_response(self, response_text: str):
        """Log agent's final text response

        Args:
            response_text: Agent's narrative or analysis
        """
        self.logger.info(f"\n📝 Agent Response:\n{response_text[:200]}...\n")

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"## Agent Response\n\n{response_text}\n\n")

    def log_token_usage(self, input_tokens: int, output_tokens: int, cost: float):
        """Log token usage and cost for this round

        Args:
            input_tokens: Input tokens used
            output_tokens: Output tokens used
            cost: Cost in dollars
        """
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost

        self.logger.debug(
            f"📊 Tokens: {input_tokens}in/{output_tokens}out = ${cost:.4f}"
        )

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"**Tokens:** {input_tokens} in / {output_tokens} out = ${cost:.4f}\n\n")

    def log_session_summary(self):
        """Log final session summary with totals"""
        duration = (now_eastern() - self.session_start).total_seconds()
        total_tokens = self.total_input_tokens + self.total_output_tokens

        summary = f"""
✅ Session complete
   Rounds: {self.round_count}
   Total tokens: {total_tokens:,} ({self.total_input_tokens:,}in/{self.total_output_tokens:,}out)
   Total cost: ${self.total_cost:.4f}
   Duration: {duration:.1f}s
   Tool calls: {len(self.tool_calls)}
"""
        self.logger.info(summary)

        # Write summary to markdown
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n---\n\n## Session Summary\n\n")
            f.write(f"- **Rounds:** {self.round_count}\n")
            f.write(f"- **Total Tokens:** {total_tokens:,} ({self.total_input_tokens:,} in / {self.total_output_tokens:,} out)\n")
            f.write(f"- **Total Cost:** ${self.total_cost:.4f}\n")
            f.write(f"- **Duration:** {duration:.1f}s\n")
            f.write(f"- **Tool Calls:** {len(self.tool_calls)}\n")
            f.write(f"- **Session End:** {eastern_isoformat()}\n\n")

        return {
            'rounds': self.round_count,
            'total_tokens': total_tokens,
            'input_tokens': self.total_input_tokens,
            'output_tokens': self.total_output_tokens,
            'total_cost': self.total_cost,
            'duration_seconds': duration,
            'tool_calls': len(self.tool_calls)
        }

    def log_error(self, error: str, context: Optional[Dict] = None):
        """Log error with context

        Args:
            error: Error message
            context: Additional error context
        """
        self.logger.error(f"❌ Error: {error}")

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n## ERROR\n\n```\n{error}\n```\n\n")
            if context:
                f.write(f"**Context:**\n```json\n{self._format_dict(context)}\n```\n\n")

    def _format_dict(self, data: Dict, indent: int = 2) -> str:
        """Format dictionary as readable JSON

        Args:
            data: Dictionary to format
            indent: Indentation spaces

        Returns:
            str: Formatted JSON string
        """
        import json
        return json.dumps(data, indent=indent, default=str)


# Quick test
if __name__ == "__main__":
    # UTF-8 stdout for Windows (MANDATORY per CLAUDE.md)
    sys.stdout.reconfigure(encoding='utf-8')

    # Test logger
    print("Testing agent logger...")

    logger = AgentLogger(session_name="test_agent")

    logger.log_user_prompt("Process alert for NVDA $190 calls")
    logger.log_round_start(1)
    logger.log_tool_call("query_database", {"sql": "SELECT * FROM flow_alerts LIMIT 1"})
    logger.log_tool_result("query_database", [{"symbol": "NVDA", "strike": 190}])
    logger.log_token_usage(2500, 1200, 0.0087)

    logger.log_round_start(2)
    logger.log_tool_call("create_tracker", {"contract_hash": "NVDA|190|2025-01-15|call", "narrative": "Test narrative"})
    logger.log_tool_result("create_tracker", {"tracker_id": 42, "status": "created"})
    logger.log_token_usage(1800, 800, 0.0052)

    logger.log_agent_response("Created tracker for NVDA $190 calls with initial narrative.")

    summary = logger.log_session_summary()

    print(f"\n✅ Logger test complete. Check: {logger.log_file}")
    print(f"   Summary: {summary}")
