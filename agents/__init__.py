#!/usr/bin/env python3
"""
Agents Package (agents/__init__.py)
------------------------------------
Flow Tracker Agent - AI analyst that builds narratives for option flow alerts.

Main components:
- AgentRuntime: Core orchestrator with Anthropic SDK
- AgentTools: Tool implementations (query, create, update, close)
- AgentConfig: Configuration management
- AgentLogger: Session logging

Author: Ben (with assistance from Claude)
Date: 2026-01-01
"""

from agents.agent_runtime import AgentRuntime
from agents.agent_tools import AgentTools
from agents.agent_config import AgentConfig, get_config
from agents.agent_logger import AgentLogger
from agents.agent_prompts import (
    FM_AGENT_SYSTEM_PROMPT,
    FLOW_CLASSIFICATIONS,
    PROCESS_NEW_ALERT_PROMPT,
    UPDATE_TRACKER_PROMPT
)

__all__ = [
    'AgentRuntime',
    'AgentTools',
    'AgentConfig',
    'get_config',
    'AgentLogger',
    'FM_AGENT_SYSTEM_PROMPT',
    'FLOW_CLASSIFICATIONS',
    'PROCESS_NEW_ALERT_PROMPT',
    'UPDATE_TRACKER_PROMPT'
]

__version__ = '1.0.0'
