#!/usr/bin/env python3
"""
Flow Monitor Agent Integration (fm_agent.py)
----------------------------------------------
Batch process Flow Monitor alerts and create/update tracker narratives.

Uses Flow Tracker Agent (agents/) to analyze alerts and maintain
contract tracking with AI-generated narratives.

Author: Ben (with assistance from Claude)
Date: 2026-01-02
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tools.timezone_utils import now_eastern
from tools.autofix import queue_error
from agents.agent_runtime import AgentRuntime
from agents.agent_config import get_config
import sqlite3

logger = logging.getLogger('fm.agent')

# Schema hints to prevent agent from using wrong table names
SCHEMA_HINTS = """
## Available Database Tables

**CRITICAL: Use these EXACT column names (errors waste tokens!)**

**Price Data:**
- historical_prices
  Columns: symbol, trade_date, open_price, high_price, low_price, close_price, volume
  Note: Use close_price NOT close, high_price NOT high, etc.

**Earnings:**
- earnings_events
  Columns: event_id, symbol, earnings_date, fiscal_year, fiscal_period, actual_eps
  Note: No estimate_eps or report_time columns exist

**Symbol Info:**
- symbol_metadata
  Columns: symbol, company_name, sector
  Note: No market_cap or avg_volume columns

**Market Context:**
- market_daily_summary
  Columns: trade_date, regime_classification
  Note: Check schema for available columns - spx_close/vix_close may not exist

**Flow Monitor Data:**
- flow_alerts
  Columns: id, contract_hash, trade_date, symbol, strike, expiration_date, option_type,
           volume, premium_value, significance_score, alert_timestamp, moneyness,
           underlying_price, dte, iv, delta, gamma, theta, vega
- flow_symbol_summary
  Columns: symbol, trade_date, significant_contract_count, alert_count_5d, alert_count_20d

**Option Contracts:**
- option_contracts
  Columns: symbol, strike, expiration, option_type, trade_date, open_interest, volume,
           iv, delta, gamma, theta, vega, underlying_price, dte

**Flow Tracker Tables:**
- flow_contract_trackers
  Columns: tracker_id (PRIMARY KEY), contract_hash (UNIQUE), symbol, strike, expiration,
           option_type, flow_classification, narrative, status, close_reason, days_active,
           created_at, updated_at, initial_alert_score, alert_count, last_alert_id,
           sector, avg_daily_volume, earnings_date, days_to_earnings, user_notes
- flow_tracker_updates
  Columns: id, tracker_id, update_type, narrative, trade_date, created_at
"""


def build_new_alert_prompt(alert: Dict, existing_tracker: Dict = None) -> str:
    """Build prompt for processing flow alert

    Args:
        alert: Alert data from flow_alerts table
        existing_tracker: Existing tracker dict if found, None if new

    Returns:
        str: Formatted prompt for agent
    """
    # Format expiration date
    exp_date = alert.get('expiration_date', 'Unknown')

    # Build base context
    prompt_parts = [SCHEMA_HINTS]

    if existing_tracker:
        # Update existing tracker
        prompt_parts.append(f"""
## Update Existing Tracker

An existing tracker was found for this contract:
- Tracker ID: {existing_tracker.get('tracker_id')}
- Created: {existing_tracker.get('created_at')}
- Current Flow Classification: {existing_tracker.get('flow_classification', 'unclear')}
- Current Narrative: {existing_tracker.get('narrative', 'None')}

**New Alert Details:**
- Symbol: {alert['symbol']}
- Strike: ${alert['strike']}
- Expiration: {exp_date}
- Type: {alert['option_type']}
- Volume: {alert.get('volume', 0):,}
- Premium: ${alert.get('premium_value', 0):,.2f}
- Significance Score: {alert.get('significance_score', 0):.2f}
- Alert Reason: {alert.get('alert_reason', 'N/A')}
- Alert Time: {alert['alert_timestamp']}
- Moneyness: {alert.get('moneyness', 'N/A')}
- IV: {alert.get('iv', 0):.4f}
- Delta: {alert.get('delta', 0):.4f}

**Your task:**
1. Query relevant context (stock movement since tracker created, new earnings, sector trends)
2. Determine if flow classification should change
3. Build updated narrative that incorporates new information
4. Update tracker with revised narrative using update_tracker tool
""")
    else:
        # Create new tracker
        prompt_parts.append(f"""
## Process New Flow Alert

Create a tracker for this new flow alert:

**Alert Details:**
- Symbol: {alert['symbol']}
- Strike: ${alert['strike']}
- Expiration: {exp_date}
- Type: {alert['option_type']}
- Volume: {alert.get('volume', 0):,}
- Premium: ${alert.get('premium_value', 0):,.2f}
- Significance Score: {alert.get('significance_score', 0):.2f}
- Alert Reason: {alert.get('alert_reason', 'N/A')}
- Alert Time: {alert['alert_timestamp']}
- Moneyness: {alert.get('moneyness', 'N/A')}
- Underlying Price: ${alert.get('underlying_price', 0):.2f}
- DTE: {alert.get('dte', 0)} days
- IV: {alert.get('iv', 0):.4f}
- Delta: {alert.get('delta', 0):.4f}
- Gamma: {alert.get('gamma', 0):.4f}
- Theta: {alert.get('theta', 0):.4f}
- Vega: {alert.get('vega', 0):.4f}

**Your task:**
1. Query relevant context (stock movement, sector trends, earnings calendar)
2. Classify the flow (institutional_accumulation, earnings_play, hedge, technical_breakout, sector_rotation, unclear)
3. Build initial narrative (200-1000 chars) explaining what you observe
4. Create tracker record with narrative using create_tracker tool
""")

    return "\n".join(prompt_parts)


def process_daily_alerts(trade_date: str = None) -> Dict[str, Any]:
    """Process all flow alerts for a given date and create/update trackers

    Args:
        trade_date: YYYY-MM-DD format (defaults to today)

    Returns:
        dict: {
            'alerts_processed': int,
            'trackers_created': int,
            'trackers_updated': int,
            'errors': int,
            'total_cost': float,
            'total_tokens': int,
            'session_log_dir': str
        }
    """
    # Default to today
    if trade_date is None:
        trade_date = now_eastern().strftime('%Y-%m-%d')

    logger.info(f"Processing flow alerts for {trade_date}")

    # Get database paths from config
    config = get_config()
    read_db = config.get_db_path('read')

    # Query all alerts for the date
    try:
        conn = sqlite3.connect(read_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM flow_alerts
            WHERE trade_date = ?
            ORDER BY significance_score DESC
        """, (trade_date,))

        alerts = [dict(row) for row in cursor.fetchall()]
        conn.close()

        logger.info(f"Found {len(alerts)} alerts for {trade_date}")

    except sqlite3.Error as e:
        logger.error(f"Database error querying alerts: {e}")
        queue_error(
            error_type='fm_agent_db_error',
            context={'error': str(e), 'trade_date': trade_date},
            severity='ERROR'
        )
        return {
            'alerts_processed': 0,
            'trackers_created': 0,
            'trackers_updated': 0,
            'errors': 1,
            'total_cost': 0.0,
            'total_tokens': 0,
            'session_log_dir': None
        }

    # Initialize agent runtime (reuse for all alerts)
    try:
        runtime = AgentRuntime(session_name=f"fm_agent_{trade_date}")
        logger.info(f"Agent runtime initialized: {runtime.config.model}")
    except Exception as e:
        logger.error(f"Failed to initialize agent runtime: {e}")
        queue_error(
            error_type='fm_agent_init_error',
            context={'error': str(e)},
            severity='ERROR'
        )
        return {
            'alerts_processed': 0,
            'trackers_created': 0,
            'trackers_updated': 0,
            'errors': 1,
            'total_cost': 0.0,
            'total_tokens': 0,
            'session_log_dir': None
        }

    # Process each alert
    alerts_processed = 0
    trackers_created = 0
    trackers_updated = 0
    errors = 0
    total_cost = 0.0
    total_tokens = 0
    last_session_log = None

    for idx, alert in enumerate(alerts, 1):
        try:
            # Build contract hash
            contract_hash = f"{alert['symbol']}|{alert['strike']}|{alert['expiration_date']}|{alert['option_type']}"

            logger.info(f"[{idx}/{len(alerts)}] Processing {contract_hash}")

            # Check if tracker exists by querying directly
            # (Agent's get_tracker tool would work too, but this is more efficient)
            conn = sqlite3.connect(read_db)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM flow_contract_trackers
                WHERE contract_hash = ? AND status = 'active'
            """, (contract_hash,))

            existing_tracker_row = cursor.fetchone()
            if existing_tracker_row:
                existing_tracker = dict(existing_tracker_row)
                # Rename 'id' to 'tracker_id' for consistency with agent tools API
                if 'id' in existing_tracker:
                    existing_tracker['tracker_id'] = existing_tracker['id']
            else:
                existing_tracker = None
            conn.close()

            # Build prompt
            prompt = build_new_alert_prompt(alert, existing_tracker)

            # Run agent
            result = runtime.run(prompt)

            # Track results
            if result.get('success'):
                alerts_processed += 1

                if result.get('action') == 'created':
                    trackers_created += 1
                    logger.info(f"✅ Tracker created: ID={result.get('tracker_id')}")
                elif result.get('action') == 'updated':
                    trackers_updated += 1
                    logger.info(f"✅ Tracker updated: ID={result.get('tracker_id')}")
                else:
                    logger.info(f"✅ Agent completed (no tracker action)")

            else:
                errors += 1
                error_msg = result.get('error', 'Unknown error')
                logger.warning(f"❌ Agent failed: {error_msg}")
                queue_error(
                    error_type='fm_agent_processing_error',
                    context={
                        'alert_id': alert['id'],
                        'contract_hash': contract_hash,
                        'error': error_msg
                    },
                    severity='WARNING'
                )

            # Accumulate cost tracking
            total_cost += result.get('cost', 0.0)
            tokens = result.get('tokens_used', {})
            total_tokens += tokens.get('total', 0)
            last_session_log = result.get('session_log')

        except Exception as e:
            logger.error(f"Processing error for alert {alert['id']}: {e}")
            queue_error(
                error_type='fm_agent_processing_exception',
                context={
                    'alert_id': alert['id'],
                    'error': str(e)
                },
                severity='ERROR'
            )
            errors += 1
            # Continue processing other alerts

    # Log summary
    logger.info(f"✅ Batch processing complete:")
    logger.info(f"   Alerts processed: {alerts_processed}/{len(alerts)}")
    logger.info(f"   Trackers created: {trackers_created}")
    logger.info(f"   Trackers updated: {trackers_updated}")
    logger.info(f"   Errors: {errors}")
    logger.info(f"   Total cost: ${total_cost:.4f}")
    logger.info(f"   Total tokens: {total_tokens:,}")

    # Determine session log directory
    session_log_dir = None
    if last_session_log:
        session_log_dir = str(Path(last_session_log).parent)

    return {
        'alerts_processed': alerts_processed,
        'trackers_created': trackers_created,
        'trackers_updated': trackers_updated,
        'errors': errors,
        'total_cost': total_cost,
        'total_tokens': total_tokens,
        'session_log_dir': session_log_dir
    }


def run_agent_analysis(trade_date: str = None) -> Dict[str, Any]:
    """Entry point for FM orchestration

    Args:
        trade_date: YYYY-MM-DD format (defaults to today)

    Returns:
        dict: Processing results summary
    """
    if trade_date is None:
        trade_date = now_eastern().strftime('%Y-%m-%d')

    logger.info(f"🤖 Starting FM Agent analysis for {trade_date}")

    results = process_daily_alerts(trade_date)

    logger.info(f"✅ Agent analysis complete:")
    logger.info(f"   Alerts processed: {results['alerts_processed']}")
    logger.info(f"   Trackers created: {results['trackers_created']}")
    logger.info(f"   Trackers updated: {results['trackers_updated']}")
    logger.info(f"   Errors: {results['errors']}")
    logger.info(f"   Cost: ${results['total_cost']:.4f}")

    if results['session_log_dir']:
        logger.info(f"   Session logs: {results['session_log_dir']}")

    return results


# Quick test
if __name__ == "__main__":
    # UTF-8 stdout for Windows (MANDATORY per CLAUDE.md)
    sys.stdout.reconfigure(encoding='utf-8')

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s:%(name)s:%(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Check for command line args
    import argparse
    parser = argparse.ArgumentParser(description='Process flow alerts with agent')
    parser.add_argument('--date', type=str, help='Trade date (YYYY-MM-DD)')
    args = parser.parse_args()

    # Run analysis
    try:
        results = run_agent_analysis(trade_date=args.date)

        print("")
        print("BATCH PROCESSING SUMMARY")
        print(f"Date: {args.date or 'today'}")
        print(f"Alerts processed: {results['alerts_processed']}")
        print(f"Trackers created: {results['trackers_created']}")
        print(f"Trackers updated: {results['trackers_updated']}")
        print(f"Errors: {results['errors']}")
        print(f"Total cost: ${results['total_cost']:.4f}")
        print(f"Total tokens: {results['total_tokens']:,}")
        if results['session_log_dir']:
            print(f"Session logs: {results['session_log_dir']}")

    except Exception as e:
        print(f"\n❌ Agent analysis failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
