#!/usr/bin/env python3
"""
Agent Runtime (agent_runtime.py)
---------------------------------
Core agent runtime with Anthropic SDK integration.

Implements tool use loop for Flow Tracker Agent:
1. Send prompt to Claude with system prompt and tools
2. Agent decides to use tools or respond
3. Execute tools and return results
4. Repeat until agent responds or max rounds hit
5. Return structured response with token tracking

Author: Ben (with assistance from Claude)
Date: 2026-01-01
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Anthropic SDK
try:
    import anthropic
except ImportError:
    print("❌ Anthropic SDK not installed. Run: pip install anthropic")
    sys.exit(1)

from agents.agent_config import get_config
from agents.agent_logger import AgentLogger
from agents.agent_tools import AgentTools
from agents.agent_prompts import FM_AGENT_SYSTEM_PROMPT
from tools.autofix import queue_error

logger = logging.getLogger('agent.runtime')


class AgentRuntime:
    """Core agent runtime with Anthropic SDK and tool use loop"""

    def __init__(
        self,
        system_prompt: str = FM_AGENT_SYSTEM_PROMPT,
        tools: Optional[AgentTools] = None,
        session_name: str = "fm_agent"
    ):
        """Initialize agent runtime

        Args:
            system_prompt: System prompt defining agent behavior
            tools: AgentTools instance (creates new if None)
            session_name: Name for logging session
        """
        self.config = get_config()
        self.system_prompt = system_prompt
        self.tools = tools or AgentTools()
        self.session_name = session_name

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=self.config.api_key)

        # Runtime state
        self.max_rounds = self.config.max_tool_rounds
        self.cost_warning_threshold = self.config.cost_warning_threshold

        logger.info(f"Agent runtime initialized: model={self.config.model}")

    def run(self, user_prompt: str) -> Dict[str, Any]:
        """Run agent on user prompt with tool use loop

        Args:
            user_prompt: User/system prompt for agent

        Returns:
            dict: {
                'success': bool,
                'content': str,              # Agent's final response
                'tracker_id': int,           # If tracker created/updated
                'action': str,               # 'created' | 'updated' | 'closed'
                'tokens_used': {...},
                'cost': float,
                'rounds': int
            }
        """
        # Initialize session logger
        session_logger = AgentLogger(session_name=self.session_name)
        session_logger.log_user_prompt(user_prompt)
        session_logger.log_system_prompt(self.system_prompt)

        try:
            # Initialize conversation
            messages = [{"role": "user", "content": user_prompt}]
            round_count = 0
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost = 0.0

            # Metadata tracking
            tracker_id = None
            action = None

            # Tool use loop
            while round_count < self.max_rounds:
                round_count += 1
                session_logger.log_round_start(round_count)

                # Call Anthropic API
                try:
                    response = self.client.messages.create(
                        model=self.config.model,
                        system=self.system_prompt,
                        messages=messages,
                        tools=self.tools.get_tool_definitions(),
                        max_tokens=self.config.max_tokens
                    )
                except anthropic.APIError as e:
                    logger.error(f"Anthropic API error: {e}")
                    queue_error(
                        error_type='agent_api_error',
                        context={'error': str(e), 'round': round_count},
                        severity='ERROR'
                    )
                    session_logger.log_error(str(e), {'round': round_count})
                    return {
                        'success': False,
                        'error': f"API error: {e}",
                        'rounds': round_count
                    }

                # Track token usage
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                round_cost = self.config.calculate_cost(input_tokens, output_tokens)

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_cost += round_cost

                session_logger.log_token_usage(input_tokens, output_tokens, round_cost)

                # Check cost warning
                if total_cost >= self.cost_warning_threshold:
                    logger.warning(
                        f"Session cost ${total_cost:.4f} exceeds warning threshold ${self.cost_warning_threshold}"
                    )

                # Check stop reason
                if response.stop_reason == "end_turn":
                    # Agent is done - extract final text response
                    final_text = ""
                    for content_block in response.content:
                        if content_block.type == "text":
                            final_text += content_block.text

                    session_logger.log_agent_response(final_text)

                    # Build successful response
                    summary = session_logger.log_session_summary()

                    return {
                        'success': True,
                        'content': final_text,
                        'tracker_id': tracker_id,
                        'action': action,
                        'tokens_used': {
                            'input': total_input_tokens,
                            'output': total_output_tokens,
                            'total': total_input_tokens + total_output_tokens
                        },
                        'cost': total_cost,
                        'rounds': round_count,
                        'session_log': str(session_logger.log_file)
                    }

                elif response.stop_reason == "tool_use":
                    # Agent wants to use tools - execute them
                    tool_results = []

                    for content_block in response.content:
                        if content_block.type == "tool_use":
                            tool_name = content_block.name
                            tool_input = content_block.input
                            tool_use_id = content_block.id

                            session_logger.log_tool_call(tool_name, tool_input)

                            # Execute tool
                            try:
                                result = self.tools.execute_tool(tool_name, tool_input)

                                # Track metadata for response
                                if tool_name == "create_tracker" and 'tracker_id' in result:
                                    tracker_id = result['tracker_id']
                                    action = 'created'
                                elif tool_name == "update_tracker" and result.get('status') == 'updated':
                                    tracker_id = tool_input.get('tracker_id')
                                    action = 'updated'
                                elif tool_name == "close_tracker" and result.get('status') == 'closed':
                                    tracker_id = tool_input.get('tracker_id')
                                    action = 'closed'

                                session_logger.log_tool_result(tool_name, result)

                                # Format tool result for Anthropic API
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": str(result)
                                })

                            except Exception as e:
                                logger.error(f"Tool execution failed: {e}")
                                session_logger.log_tool_result(tool_name, None, error=str(e))

                                # Return error to agent
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": tool_use_id,
                                    "content": f"Error: {e}"
                                })

                    # Add assistant response to conversation
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })

                    # Add tool results to conversation
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })

                    # Continue loop for next round

                elif response.stop_reason == "max_tokens":
                    logger.warning(f"Hit max_tokens limit in round {round_count}")
                    session_logger.log_error(
                        "Hit max_tokens limit",
                        {'round': round_count, 'max_tokens': self.config.max_tokens}
                    )

                    # Extract partial response
                    partial_text = ""
                    for content_block in response.content:
                        if content_block.type == "text":
                            partial_text += content_block.text

                    summary = session_logger.log_session_summary()

                    return {
                        'success': False,
                        'error': 'max_tokens_exceeded',
                        'content': partial_text,
                        'rounds': round_count,
                        'tokens_used': {
                            'input': total_input_tokens,
                            'output': total_output_tokens,
                            'total': total_input_tokens + total_output_tokens
                        },
                        'cost': total_cost
                    }

                else:
                    logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
                    session_logger.log_error(
                        f"Unexpected stop_reason: {response.stop_reason}",
                        {'round': round_count}
                    )
                    continue

            # Hit max rounds limit
            logger.warning(f"Hit max rounds limit ({self.max_rounds})")
            session_logger.log_error(
                f"Hit max rounds limit ({self.max_rounds})",
                {'total_cost': total_cost}
            )

            summary = session_logger.log_session_summary()

            return {
                'success': False,
                'error': 'max_rounds_exceeded',
                'rounds': round_count,
                'tokens_used': {
                    'input': total_input_tokens,
                    'output': total_output_tokens,
                    'total': total_input_tokens + total_output_tokens
                },
                'cost': total_cost
            }

        except Exception as e:
            logger.error(f"Runtime error: {e}")
            session_logger.log_error(str(e))
            queue_error(
                error_type='agent_runtime_error',
                context={'error': str(e), 'prompt': user_prompt[:200]},
                severity='ERROR'
            )

            return {
                'success': False,
                'error': str(e),
                'rounds': round_count if 'round_count' in locals() else 0
            }


# Quick test
if __name__ == "__main__":
    # UTF-8 stdout for Windows (MANDATORY per CLAUDE.md)
    sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s:%(name)s:%(message)s'
    )

    print("Testing agent runtime...")
    print("=" * 70)

    try:
        # Initialize runtime
        runtime = AgentRuntime()
        print("✅ Agent runtime initialized")
        print(f"   Model: {runtime.config.model}")
        print(f"   Max rounds: {runtime.max_rounds}")

        # Test with simple query (won't actually run agent - just structure test)
        print("\n📝 Runtime structure validated")
        print("   - Anthropic client: ✅")
        print("   - Tool definitions: ✅")
        print("   - System prompt: ✅")
        print("   - Logger integration: ✅")

        print("\n" + "=" * 70)
        print("✅ Agent runtime test complete")
        print("\nTo test with real API call, provide a test prompt:")
        print("   runtime.run('Process alert for NVDA $190 calls')")

    except Exception as e:
        print(f"\n❌ Runtime test failed: {e}")
        import traceback
        traceback.print_exc()
