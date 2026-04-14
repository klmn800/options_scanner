#!/usr/bin/env python3
"""
Agent Integration Test (test_agent_integration.py)
---------------------------------------------------
End-to-end test of Flow Tracker Agent system.

Tests complete workflow:
1. Fetch recent alert from database
2. Run agent with alert data
3. Verify tracker created
4. Display results

Author: Ben (with assistance from Claude)
Date: 2026-01-01
"""

import sys
import logging
from pathlib import Path

# UTF-8 stdout for Windows (MANDATORY per CLAUDE.md)
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.agent_runtime import AgentRuntime
from agents.agent_prompts import PROCESS_NEW_ALERT_PROMPT
from agents.agent_tools import AgentTools

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)

logger = logging.getLogger('agent.test')


def get_recent_alert():
    """Get most recent flow alert from database for testing

    Returns:
        dict: Alert data or None
    """
    import sqlite3

    try:
        # Query from READ database
        conn = sqlite3.connect('data/datalake_query.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                symbol,
                strike,
                expiration_date,
                option_type,
                volume,
                premium_value,
                significance_score,
                alert_reason,
                alert_timestamp
            FROM flow_alerts
            WHERE symbol NOT IN ('SPY', 'QQQ')  -- Skip index ETFs
            ORDER BY alert_timestamp DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    except Exception as e:
        logger.error(f"Failed to fetch alert: {e}")
        return None


def main():
    """Run integration test"""
    print("=" * 70)
    print("Flow Tracker Agent - Integration Test")
    print("=" * 70)

    # Step 1: Get test alert
    print("\n1. Fetching recent alert from database...")
    alert = get_recent_alert()

    if not alert:
        print("   ❌ No alerts found in database")
        return

    print(f"   ✅ Found alert: {alert['symbol']} ${alert['strike']} {alert['option_type']}")
    print(f"      Score: {alert['significance_score']:.2f}")
    print(f"      Premium: ${alert['premium_value']:,.0f}")

    # Step 2: Build prompt
    print("\n2. Building agent prompt...")
    prompt = PROCESS_NEW_ALERT_PROMPT.format(
        symbol=alert['symbol'],
        strike=alert['strike'],
        expiration=alert['expiration_date'],
        option_type=alert['option_type'],
        volume=alert['volume'],
        premium_value=alert['premium_value'],
        significance_score=alert['significance_score'],
        alert_reason=alert['alert_reason'],
        alert_timestamp=alert['alert_timestamp']
    )
    print(f"   ✅ Prompt built ({len(prompt)} chars)")

    # Step 3: Initialize agent
    print("\n3. Initializing agent runtime...")
    runtime = AgentRuntime()
    print(f"   ✅ Agent ready: {runtime.config.model}")

    # Step 4: Run agent
    print("\n4. Running agent (this will call Anthropic API)...")
    print("   ⏳ Processing...")

    result = runtime.run(prompt)

    # Step 5: Display results
    print("\n5. Agent Results:")
    print("   " + "-" * 66)

    if result['success']:
        print(f"   ✅ Status: SUCCESS")
        print(f"   📊 Rounds: {result['rounds']}")
        print(f"   💰 Cost: ${result['cost']:.4f}")
        print(f"   🔢 Tokens: {result['tokens_used']['total']:,} ({result['tokens_used']['input']:,}in/{result['tokens_used']['output']:,}out)")

        if result.get('tracker_id'):
            print(f"   📝 Tracker ID: {result['tracker_id']}")
            print(f"   🎯 Action: {result['action']}")

        print(f"\n   📄 Response:")
        print("   " + "-" * 66)
        # Indent response
        for line in result['content'].split('\n'):
            print(f"   {line}")
        print("   " + "-" * 66)

        if result.get('session_log'):
            print(f"\n   📋 Session log: {result['session_log']}")

    else:
        print(f"   ❌ Status: FAILED")
        print(f"   ⚠️  Error: {result.get('error')}")
        print(f"   📊 Rounds: {result.get('rounds', 0)}")
        if 'cost' in result:
            print(f"   💰 Cost: ${result['cost']:.4f}")

    # Step 6: Verify tracker in database
    if result.get('tracker_id'):
        print("\n6. Verifying tracker in database...")
        tools = AgentTools()
        tracker_result = tools.get_tracker(f"{alert['symbol']}|{alert['strike']}|{alert['expiration_date']}|{alert['option_type']}")

        if tracker_result.get('tracker'):
            tracker = tracker_result['tracker']
            print(f"   ✅ Tracker {tracker['tracker_id']} confirmed in database")
            print(f"      Status: {tracker['status']}")
            print(f"      Classification: {tracker['flow_classification']}")
            print(f"      Narrative length: {len(tracker['narrative'])} chars")
        else:
            print("   ⚠️  Tracker not found in database (may be timing issue)")

    print("\n" + "=" * 70)
    print("Integration test complete!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
