#!/usr/bin/env python3
"""
Agent Enable/Disable Toggle (agent_toggle.py)
---------------------------------------------
Single switch for the autonomous agents that main.py auto-launches during the
daily pipeline. Reads config.json -> agents.<name>.enabled.

Currently gates the two agents triggered by main.py:
  - earnings_researcher  (spawned by ei_lite_refresh.py when earnings-date
                          disputes are found, EI sub-step 1/8)
  - trading_advisor      (launched pre-market by main_runners._launch_trading_advisor)

Task Scheduler sessions (weekday research, Saturday, Sunday) are NOT gated by
this switch — they are separate scheduled jobs, not launched by main.py.

Fail-open by design: a missing config file, missing 'agents' block, missing
entry, or a JSON parse error all return the default (True). A typo in
config.json can never silently disable every agent.

Usage (Python):
    from tools.agent_toggle import is_agent_enabled
    if is_agent_enabled('trading_advisor'):
        ...

Usage (CLI — exit 0 = enabled, 1 = disabled):
    python tools/agent_toggle.py trading_advisor
"""

import json
import logging
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, 'config.json')


def is_agent_enabled(name, default=True):
    """Return True if agent ``name`` is enabled in config.json.

    Looks up ``config['agents'][name]['enabled']``. Fail-open: any error or
    missing key returns ``default`` (True), so a malformed or incomplete
    config can never silently disable every agent.
    """
    try:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        entry = config.get('agents', {}).get(name)
        if not isinstance(entry, dict):
            return default
        return bool(entry.get('enabled', default))
    except Exception as e:
        logging.debug("agent_toggle: could not read config for '%s': %s", name, e)
        return default


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage: python tools/agent_toggle.py <agent_name>")
        sys.exit(2)
    sys.exit(0 if is_agent_enabled(sys.argv[1]) else 1)
