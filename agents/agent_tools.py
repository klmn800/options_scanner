#!/usr/bin/env python3
"""
Agent Tools (agent_tools.py)
-----------------------------
Tool implementations for Flow Tracker Agent.

Provides tools the agent can call via Anthropic SDK:
- query_database: Execute SELECT queries
- get_tracker: Retrieve existing tracker
- create_tracker: Create new tracker record
- update_tracker: Update existing tracker
- close_tracker: Close tracker with reason

Author: Ben (with assistance from Claude)
Date: 2026-01-01
"""

import sqlite3
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'tools'))
sys.path.insert(0, str(project_root))

from timezone_utils import eastern_isoformat
from decimal_formatter import clean_database_row
from tools.autofix import queue_error
from agents.agent_config import get_config

logger = logging.getLogger('agent.tools')

# SQL validation - block write operations
BLOCKED_SQL_KEYWORDS = [
    'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
    'GRANT', 'REVOKE', 'TRUNCATE', 'REPLACE', 'EXEC', 'EXECUTE'
]

# Tool definitions for Anthropic API
TOOL_DEFINITIONS = [
    {
        "name": "query_database",
        "description": "Execute SELECT query against datalake_query.db to gather context. Use this to query flow alerts, historical prices, sector trends, earnings calendar, market conditions, etc. Returns raw rows as list of dictionaries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SELECT query to execute. Only SELECT and WITH statements allowed. Query returns list of row dictionaries."
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "get_tracker",
        "description": "Retrieve existing tracker for a contract by contract_hash. Returns tracker record with current narrative and metadata, or null if tracker doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contract_hash": {
                    "type": "string",
                    "description": "Contract hash in format: SYMBOL|STRIKE|EXPIRATION|TYPE (e.g., 'NVDA|190|2025-01-15|call')"
                }
            },
            "required": ["contract_hash"]
        }
    },
    {
        "name": "create_tracker",
        "description": "Create new tracker for a contract with initial narrative. Use this after analyzing a new flow alert. Returns tracker_id of created record.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contract_hash": {
                    "type": "string",
                    "description": "Contract hash: SYMBOL|STRIKE|EXPIRATION|TYPE"
                },
                "symbol": {
                    "type": "string",
                    "description": "Stock symbol (e.g., 'NVDA')"
                },
                "strike": {
                    "type": "number",
                    "description": "Strike price"
                },
                "expiration": {
                    "type": "string",
                    "description": "Expiration date (YYYY-MM-DD)"
                },
                "option_type": {
                    "type": "string",
                    "description": "Option type: 'call' or 'put'"
                },
                "narrative": {
                    "type": "string",
                    "description": "Initial narrative explaining what you observe about this flow"
                },
                "flow_classification": {
                    "type": "string",
                    "description": "Classification: 'institutional_accumulation' | 'earnings_play' | 'hedge' | 'technical_breakout' | 'sector_rotation' | 'unclear'"
                },
                "initial_alert_score": {
                    "type": "number",
                    "description": "Significance score from initial alert"
                },
                "alert_id": {
                    "type": "integer",
                    "description": "ID of the flow_alerts record that triggered this tracker"
                }
            },
            "required": ["contract_hash", "symbol", "strike", "expiration", "option_type", "narrative", "flow_classification"]
        }
    },
    {
        "name": "update_tracker",
        "description": "Update existing tracker with new observations. Appends to narrative and updates metadata. Use this for daily check-ins on active trackers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tracker_id": {
                    "type": "integer",
                    "description": "ID of tracker to update"
                },
                "narrative": {
                    "type": "string",
                    "description": "New cumulative narrative (append new observations to existing narrative)"
                },
                "flow_classification": {
                    "type": "string",
                    "description": "Updated classification if it changed"
                },
                "status": {
                    "type": "string",
                    "description": "Status: 'active' or 'closed'"
                },
                "update_reason": {
                    "type": "string",
                    "description": "Brief reason for this update (e.g., 'daily_check', 'new_alert', 'major_move')"
                }
            },
            "required": ["tracker_id", "narrative"]
        }
    },
    {
        "name": "close_tracker",
        "description": "Close tracker when contract expires or becomes irrelevant. Marks status as 'closed' with reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tracker_id": {
                    "type": "integer",
                    "description": "ID of tracker to close"
                },
                "reason": {
                    "type": "string",
                    "description": "Why closing: 'expired' | 'thesis_invalidated' | 'user_closed' | 'low_conviction'"
                },
                "final_narrative": {
                    "type": "string",
                    "description": "Optional final narrative update explaining outcome"
                }
            },
            "required": ["tracker_id", "reason"]
        }
    },
    {
      "name": "read_reference",
      "description": "Read reference documentation (schema guides, best practices, examples)",
      "input_schema": {
          "type": "object",
          "properties": {
              "file_path": {
                  "type": "string",
                  "description": "Path to reference doc (e.g., 'docs/agent_guides/schema_reference.md')"
              }
          },
          "required": ["file_path"]
      }
    }
]


class AgentTools:
    """Tool implementations for agent runtime"""

    def __init__(self):
        """Initialize agent tools with database connections"""
        self.config = get_config()
        logger.info("Agent tools initialized")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for Anthropic API

        Returns:
            list: Tool definition schemas
        """
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool by name with input parameters

        Args:
            tool_name: Name of tool to execute
            tool_input: Input parameters for tool

        Returns:
            dict: Tool result or error
        """
        try:
            # Dispatch to appropriate tool function
            if tool_name == "query_database":
                return self.query_database(tool_input['sql'])

            elif tool_name == "get_tracker":
                return self.get_tracker(tool_input['contract_hash'])

            elif tool_name == "create_tracker":
                return self.create_tracker(
                    contract_hash=tool_input['contract_hash'],
                    symbol=tool_input['symbol'],
                    strike=tool_input['strike'],
                    expiration=tool_input['expiration'],
                    option_type=tool_input['option_type'],
                    narrative=tool_input['narrative'],
                    flow_classification=tool_input['flow_classification'],
                    initial_alert_score=tool_input.get('initial_alert_score'),
                    alert_id=tool_input.get('alert_id')
                )

            elif tool_name == "update_tracker":
                return self.update_tracker(
                    tracker_id=tool_input['tracker_id'],
                    narrative=tool_input['narrative'],
                    flow_classification=tool_input.get('flow_classification'),
                    status=tool_input.get('status'),
                    update_reason=tool_input.get('update_reason', 'daily_check')
                )

            elif tool_name == "close_tracker":
                return self.close_tracker(
                    tracker_id=tool_input['tracker_id'],
                    reason=tool_input['reason'],
                    final_narrative=tool_input.get('final_narrative')
                )
                
            elif tool_name == "read_reference":  # ← ADD THIS
                return self.read_reference(tool_input['file_path'])

            else:
                return {'error': f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {'error': str(e)}

    # ========================================================================
    # Tool Functions
    # ========================================================================

    def query_database(self, sql: str) -> Dict[str, Any]:
        """Execute SELECT query against datalake_query.db

        Args:
            sql: SELECT query to execute

        Returns:
            dict: {'rows': [...]} or {'error': '...'}
        """
        try:
            # Validate SQL - block write operations
            self._validate_sql(sql)

            # Execute against READ database
            conn = self._get_db_connection(mode='read')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(sql)
            rows = cursor.fetchall()
            conn.close()

            # Convert to list of dicts
            results = [dict(row) for row in rows]

            logger.debug(f"Query returned {len(results)} rows")
            return {'rows': results}

        except sqlite3.OperationalError as e:
            error_str = str(e).lower()

            # SQL syntax errors or "no such table" - let agent fix
            if any(keyword in error_str for keyword in ['syntax', 'no such', 'near', 'error']):
                logger.warning(f"SQL error (agent can fix): {e}")
                return {'error': str(e)}

            # System errors - queue for autofix
            else:
                logger.error(f"Database system error: {e}")
                queue_error(
                    error_type='agent_database_error',
                    context={'sql': sql[:200], 'error': str(e)},
                    severity='ERROR'
                )
                return {'error': f"Database error: {e}"}

        except ValueError as e:
            # SQL validation error
            logger.warning(f"SQL validation error: {e}")
            return {'error': str(e)}

        except Exception as e:
            logger.error(f"Unexpected query error: {e}")
            queue_error(
                error_type='agent_query_unexpected_error',
                context={'sql': sql[:200], 'error': str(e)},
                severity='ERROR'
            )
            return {'error': f"Unexpected error: {e}"}

    def read_reference(self, file_path: str) -> Dict[str, Any]:
        """Read reference documentation file

        Args:
          file_path: Path to reference doc (relative to project root)

        Returns:
          dict: {'content': str} or {'error': str}
        """
        try:
          from pathlib import Path

          # Security: Only allow reads from docs/agent_guides/
          if not file_path.startswith('docs/agent_guides/'):
              return {'error': 'Can only read from docs/agent_guides/ directory'}

          # Build path relative to project root (where this file is located)
          project_root = Path(__file__).parent.parent
          full_path = project_root / file_path

          if not full_path.exists():
              return {'error': f'File not found: {file_path}'}

          content = full_path.read_text(encoding='utf-8')

          logger.debug(f"Read reference doc: {file_path} ({len(content)} chars)")
          return {'content': content}

        except Exception as e:
          logger.error(f"Error reading reference: {e}")
          return {'error': str(e)}
    
    def get_tracker(self, contract_hash: str) -> Dict[str, Any]:
        """Retrieve existing tracker for contract

        Args:
            contract_hash: Contract hash (SYMBOL|STRIKE|EXPIRATION|TYPE)

        Returns:
            dict: Tracker record or {'tracker': None} if not found
        """
        try:
            conn = self._get_db_connection(mode='read')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM flow_contract_trackers
                WHERE contract_hash = ?
            """, (contract_hash,))

            row = cursor.fetchone()
            conn.close()

            if row:
                tracker = dict(row)
                logger.debug(f"Found tracker {tracker['tracker_id']} for {contract_hash}")
                return {'tracker': tracker}
            else:
                logger.debug(f"No tracker found for {contract_hash}")
                return {'tracker': None}

        except Exception as e:
            logger.error(f"Error retrieving tracker: {e}")
            queue_error(
                error_type='agent_get_tracker_error',
                context={'contract_hash': contract_hash, 'error': str(e)},
                severity='ERROR'
            )
            return {'error': str(e)}

    def create_tracker(
        self,
        contract_hash: str,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str,
        narrative: str,
        flow_classification: str,
        initial_alert_score: Optional[float] = None,
        alert_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create new tracker for contract

        Args:
            contract_hash: Contract hash
            symbol: Stock symbol
            strike: Strike price
            expiration: Expiration date (YYYY-MM-DD)
            option_type: 'call' or 'put'
            narrative: Initial narrative
            flow_classification: Classification category
            initial_alert_score: Significance score from alert
            alert_id: Flow alert ID that triggered this

        Returns:
            dict: {'tracker_id': ID, 'status': 'created'} or {'error': '...'}
        """
        try:
            # Prepare data
            data = {
                'contract_hash': contract_hash,
                'symbol': symbol,
                'strike': strike,
                'expiration': expiration,
                'option_type': option_type,
                'created_at': eastern_isoformat(),
                'updated_at': eastern_isoformat(),
                'status': 'active',
                'close_reason': None,
                'days_active': 0,
                'narrative': narrative,
                'flow_classification': flow_classification,
                'initial_alert_score': initial_alert_score,
                'alert_count': 1,
                'last_alert_id': alert_id
            }

            # Apply decimal formatting
            data = clean_database_row(data)

            # Insert into WRITE database
            conn = self._get_db_connection(mode='write')
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO flow_contract_trackers (
                    contract_hash, symbol, strike, expiration, option_type,
                    created_at, updated_at, status, close_reason, days_active,
                    narrative, flow_classification,
                    initial_alert_score, alert_count, last_alert_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['contract_hash'], data['symbol'], data['strike'],
                data['expiration'], data['option_type'],
                data['created_at'], data['updated_at'], data['status'],
                data['close_reason'], data['days_active'],
                data['narrative'], data['flow_classification'],
                data['initial_alert_score'], data['alert_count'],
                data['last_alert_id']
            ))

            tracker_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.info(f"Created tracker {tracker_id} for {symbol} {strike} {option_type}")

            # Log action to agent_actions table
            self._log_action(
                action_type='tracker_created',
                tracker_id=tracker_id,
                alert_id=alert_id,
                details={'contract_hash': contract_hash, 'classification': flow_classification},
                reasoning=f"Created tracker for new alert: {narrative[:100]}..."
            )

            return {
                'tracker_id': tracker_id,
                'status': 'created',
                'contract_hash': contract_hash
            }

        except sqlite3.IntegrityError as e:
            # Duplicate contract_hash
            logger.warning(f"Tracker already exists for {contract_hash}")
            return {'error': f"Tracker already exists: {e}"}

        except Exception as e:
            logger.error(f"Error creating tracker: {e}")
            queue_error(
                error_type='agent_create_tracker_error',
                context={
                    'contract_hash': contract_hash,
                    'symbol': symbol,
                    'error': str(e)
                },
                severity='ERROR'
            )
            return {'error': str(e)}

    def update_tracker(
        self,
        tracker_id: int,
        narrative: str,
        flow_classification: Optional[str] = None,
        status: Optional[str] = None,
        update_reason: str = 'daily_check'
    ) -> Dict[str, Any]:
        """Update existing tracker with new observations

        Args:
            tracker_id: ID of tracker to update
            narrative: New cumulative narrative
            flow_classification: Updated classification (if changed)
            status: Updated status (if changed)
            update_reason: Reason for update

        Returns:
            dict: {'tracker_id': ID, 'status': 'updated'} or {'error': '...'}
        """
        try:
            # Build update SQL dynamically
            updates = ['narrative = ?', 'updated_at = ?']
            params = [narrative, eastern_isoformat()]

            if flow_classification:
                updates.append('flow_classification = ?')
                params.append(flow_classification)

            if status:
                updates.append('status = ?')
                params.append(status)

            # Increment days_active
            updates.append('days_active = days_active + 1')

            params.append(tracker_id)  # For WHERE clause

            # Execute update
            conn = self._get_db_connection(mode='write')
            cursor = conn.cursor()

            sql = f"UPDATE flow_contract_trackers SET {', '.join(updates)} WHERE tracker_id = ?"
            cursor.execute(sql, params)

            rows_updated = cursor.rowcount
            conn.commit()
            conn.close()

            if rows_updated == 0:
                logger.warning(f"Tracker {tracker_id} not found for update")
                return {'error': f"Tracker {tracker_id} not found"}

            logger.info(f"Updated tracker {tracker_id}")

            # Log update to flow_tracker_updates
            self._log_tracker_update(
                tracker_id=tracker_id,
                update_narrative=narrative,
                trigger_type=update_reason,
                previous_status=None,  # Could query this if needed
                new_status=status
            )

            # Log action
            self._log_action(
                action_type='tracker_updated',
                tracker_id=tracker_id,
                details={'update_reason': update_reason},
                reasoning=f"Updated tracker: {narrative[:100]}..."
            )

            return {
                'tracker_id': tracker_id,
                'status': 'updated'
            }

        except Exception as e:
            logger.error(f"Error updating tracker: {e}")
            queue_error(
                error_type='agent_update_tracker_error',
                context={'tracker_id': tracker_id, 'error': str(e)},
                severity='ERROR'
            )
            return {'error': str(e)}

    def close_tracker(
        self,
        tracker_id: int,
        reason: str,
        final_narrative: Optional[str] = None
    ) -> Dict[str, Any]:
        """Close tracker with reason

        Args:
            tracker_id: ID of tracker to close
            reason: Close reason ('expired' | 'thesis_invalidated' | 'user_closed' | 'low_conviction')
            final_narrative: Optional final narrative update

        Returns:
            dict: {'tracker_id': ID, 'status': 'closed'} or {'error': '...'}
        """
        try:
            # Build update
            updates = ['status = ?', 'close_reason = ?', 'updated_at = ?']
            params = ['closed', reason, eastern_isoformat()]

            if final_narrative:
                updates.append('narrative = ?')
                params.append(final_narrative)

            params.append(tracker_id)  # For WHERE clause

            # Execute update
            conn = self._get_db_connection(mode='write')
            cursor = conn.cursor()

            sql = f"UPDATE flow_contract_trackers SET {', '.join(updates)} WHERE tracker_id = ?"
            cursor.execute(sql, params)

            rows_updated = cursor.rowcount
            conn.commit()
            conn.close()

            if rows_updated == 0:
                logger.warning(f"Tracker {tracker_id} not found for closing")
                return {'error': f"Tracker {tracker_id} not found"}

            logger.info(f"Closed tracker {tracker_id}: {reason}")

            # Log update
            self._log_tracker_update(
                tracker_id=tracker_id,
                update_narrative=final_narrative or f"Closed: {reason}",
                trigger_type='manual_close',
                previous_status='active',
                new_status='closed'
            )

            # Log action
            self._log_action(
                action_type='tracker_closed',
                tracker_id=tracker_id,
                details={'close_reason': reason},
                reasoning=f"Closed tracker: {reason}"
            )

            return {
                'tracker_id': tracker_id,
                'status': 'closed',
                'reason': reason
            }

        except Exception as e:
            logger.error(f"Error closing tracker: {e}")
            queue_error(
                error_type='agent_close_tracker_error',
                context={'tracker_id': tracker_id, 'error': str(e)},
                severity='ERROR'
            )
            return {'error': str(e)}

    # ========================================================================
    # Helper Functions
    # ========================================================================

    def _validate_sql(self, sql: str) -> None:
        """Validate SQL query - block write operations

        Args:
            sql: SQL query to validate

        Raises:
            ValueError: If SQL contains blocked operations
        """
        sql_upper = sql.strip().upper()

        for keyword in BLOCKED_SQL_KEYWORDS:
            if keyword in sql_upper:
                raise ValueError(f"SQL operation not allowed: {keyword}")

    def _get_db_connection(self, mode: str = 'read') -> sqlite3.Connection:
        """Get database connection with proper settings

        Args:
            mode: 'read' or 'write'

        Returns:
            sqlite3.Connection: Database connection
        """
        db_path = self.config.get_db_path(mode)
        conn = sqlite3.connect(db_path)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')  # 30 seconds
        return conn

    def _log_tracker_update(
        self,
        tracker_id: int,
        update_narrative: str,
        trigger_type: str,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
        alert_id: Optional[int] = None
    ):
        """Log update to flow_tracker_updates table

        Args:
            tracker_id: Tracker ID
            update_narrative: Narrative update for this event
            trigger_type: Type of trigger
            previous_status: Previous status
            new_status: New status
            alert_id: Alert ID if triggered by alert
        """
        try:
            conn = self._get_db_connection(mode='write')
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO flow_tracker_updates (
                    tracker_id, update_timestamp, trigger_type, alert_id,
                    update_narrative, previous_status, new_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tracker_id, eastern_isoformat(), trigger_type, alert_id,
                update_narrative, previous_status, new_status
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.warning(f"Failed to log tracker update: {e}")

    def _log_action(
        self,
        action_type: str,
        tracker_id: Optional[int] = None,
        alert_id: Optional[int] = None,
        details: Optional[Dict] = None,
        reasoning: Optional[str] = None
    ):
        """Log action to agent_actions table

        Args:
            action_type: Type of action
            tracker_id: Tracker ID
            alert_id: Alert ID
            details: Action details (JSON)
            reasoning: Why agent took this action
        """
        try:
            import json

            conn = self._get_db_connection(mode='write')
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO agent_actions (
                    action_timestamp, action_type, tracker_id, alert_id,
                    details, reasoning
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                eastern_isoformat(), action_type, tracker_id, alert_id,
                json.dumps(details) if details else None, reasoning
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.warning(f"Failed to log agent action: {e}")


# Quick test
if __name__ == "__main__":
    import sys
    # UTF-8 stdout for Windows (MANDATORY per CLAUDE.md)
    sys.stdout.reconfigure(encoding='utf-8')

    logging.basicConfig(level=logging.INFO)

    print("Testing agent tools...")
    print("=" * 70)

    try:
        tools = AgentTools()

        # Test 1: SQL validation
        print("\n1. Testing SQL validation...")
        try:
            tools._validate_sql("SELECT * FROM flow_alerts LIMIT 5")
            print("   ✅ SELECT allowed")
        except ValueError as e:
            print(f"   ❌ SELECT blocked: {e}")

        try:
            tools._validate_sql("DELETE FROM flow_alerts WHERE id = 1")
            print("   ❌ DELETE allowed (should be blocked!)")
        except ValueError as e:
            print(f"   ✅ DELETE blocked: {e}")

        # Test 2: Query database
        print("\n2. Testing query_database...")
        result = tools.query_database("SELECT COUNT(*) as total FROM flow_alerts")
        if 'error' in result:
            print(f"   ⚠️  Query error: {result['error']}")
        else:
            print(f"   ✅ Query successful: {result['rows'][0]['total']} alerts in database")

        # Test 3: Get non-existent tracker
        print("\n3. Testing get_tracker (non-existent)...")
        result = tools.get_tracker("TEST|100|2025-12-31|call")
        if result['tracker'] is None:
            print("   ✅ Correctly returned None for non-existent tracker")
        else:
            print(f"   ⚠️  Unexpected result: {result}")

        # Test 4: Tool definitions
        print("\n4. Testing tool definitions...")
        definitions = tools.get_tool_definitions()
        print(f"   ✅ {len(definitions)} tool definitions loaded")
        for tool_def in definitions:
            print(f"      - {tool_def['name']}")

        print("\n" + "=" * 70)
        print("✅ Agent tools test complete")

    except Exception as e:
        print(f"\n❌ Tools test failed: {e}")
        import traceback
        traceback.print_exc()
