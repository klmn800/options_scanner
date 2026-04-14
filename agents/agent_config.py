#!/usr/bin/env python3
"""
Agent Configuration (agent_config.py)
--------------------------------------
Configuration management for Flow Tracker Agent.

Loads settings from config.json and exposes database paths,
API credentials, and runtime parameters.

Author: Ben (with assistance from Claude)
Date: 2026-01-01
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger('agent.config')

class AgentConfig:
    """Configuration loader for agent runtime"""

    def __init__(self, config_path: str = "config.json"):
        """Initialize configuration from config.json

        Args:
            config_path: Path to config.json file
        """
        self.config_path = Path(config_path)
        self.config_data = self._load_config()

        # Database paths
        self.WRITE_DB = "data/datalake.db"         # Production writes
        self.READ_DB = "data/datalake_query.db"    # Agent queries

        # Claude API settings
        claude_config = self.config_data.get('claude_api', {})
        self.api_key = claude_config.get('api_key')
        self.model = claude_config.get('model', 'claude-3-5-haiku-20241022')
        self.max_tokens = claude_config.get('max_tokens', 4000)

        # Pricing for cost tracking
        pricing = claude_config.get('pricing', {})
        self.pricing = pricing.get(self.model, {'input': 1.00, 'output': 5.00})

        # Runtime limits
        self.max_tool_rounds = 10
        self.cost_warning_threshold = 0.10  # $0.10 per session

        # Validate critical settings
        self._validate()

        logger.info(f"Agent config loaded: model={self.model}, max_tokens={self.max_tokens}")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file

        Returns:
            dict: Configuration data
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            raise

    def _validate(self):
        """Validate critical configuration values"""
        if not self.api_key:
            raise ValueError("Claude API key not found in config.json")

        if not self.api_key.startswith('sk-ant-'):
            logger.warning(f"API key format looks incorrect: {self.api_key[:10]}...")

        # Check database paths exist
        write_db_path = Path(self.WRITE_DB)
        read_db_path = Path(self.READ_DB)

        if not write_db_path.exists():
            logger.warning(f"Write database not found: {self.WRITE_DB}")

        if not read_db_path.exists():
            logger.warning(f"Read database not found: {self.READ_DB}")

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for token usage

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            float: Cost in dollars
        """
        input_cost = (input_tokens / 1_000_000) * self.pricing['input']
        output_cost = (output_tokens / 1_000_000) * self.pricing['output']
        return input_cost + output_cost

    def get_db_path(self, mode: str = 'read') -> str:
        """Get database path for specified mode

        Args:
            mode: 'read' or 'write'

        Returns:
            str: Database path
        """
        if mode == 'read':
            return self.READ_DB
        elif mode == 'write':
            return self.WRITE_DB
        else:
            raise ValueError(f"Invalid mode: {mode}. Use 'read' or 'write'")


# Global config instance (initialized on import)
_config = None

def get_config() -> AgentConfig:
    """Get global configuration instance

    Returns:
        AgentConfig: Configuration object
    """
    global _config
    if _config is None:
        _config = AgentConfig()
    return _config


# Quick test
if __name__ == "__main__":
    # UTF-8 stdout for Windows (MANDATORY per CLAUDE.md)
    sys.stdout.reconfigure(encoding='utf-8')
    logging.basicConfig(level=logging.INFO)

    try:
        config = AgentConfig()
        print("✅ Agent configuration loaded successfully")
        print(f"   Model: {config.model}")
        print(f"   Max tokens: {config.max_tokens}")
        print(f"   Write DB: {config.WRITE_DB}")
        print(f"   Read DB: {config.READ_DB}")
        print(f"   Max rounds: {config.max_tool_rounds}")

        # Test cost calculation
        test_cost = config.calculate_cost(2500, 1200)
        print(f"   Sample cost (2500in/1200out): ${test_cost:.4f}")

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
