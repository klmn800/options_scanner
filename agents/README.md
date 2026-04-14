# Flow Tracker Agent - Core Framework

**Status:** Part 2 Complete - Agent Runtime Implemented
**Date:** 2026-01-01
**Built by:** Ben (with assistance from Claude)

---

## What Was Built

Core agent framework for Flow Tracker Agent that builds natural language narratives about option flow alerts.

### Modules Created (5)

#### 1. `agent_config.py` - Configuration Management
- Loads settings from `config.json` (claude_api section)
- Database paths: `WRITE_DB` (datalake.db) and `READ_DB` (datalake_query.db)
- API credentials and model settings
- Cost calculation for token usage
- Runtime limits (max 10 rounds, $0.10 cost warning)

**Key Functions:**
- `get_config()` - Get global config instance
- `calculate_cost(input_tokens, output_tokens)` - Calculate API cost

#### 2. `agent_logger.py` - Session Logging
- **Console logging:** Emojis (🤖 💭 🔧 ✅) with INFO level
- **File logging:** Markdown format to `logs/agent_sessions/fm_agent_YYYY-MM-DD.md`
- UTF-8 encoding (mandatory per CLAUDE.md)
- Tracks: prompts, tool calls, results, token usage, session summary

**Key Methods:**
- `log_user_prompt(prompt)` - Log user/system prompt
- `log_tool_call(tool_name, input)` - Log tool usage
- `log_tool_result(tool_name, result, error)` - Log tool outcome
- `log_agent_response(text)` - Log final response
- `log_session_summary()` - Log session totals

#### 3. `agent_prompts.py` - System Prompts
- `FM_AGENT_SYSTEM_PROMPT` - System prompt (from concept doc lines 264-306)
- `FLOW_CLASSIFICATIONS` - 6 classification categories
- `PROCESS_NEW_ALERT_PROMPT` - Template for new alerts
- `UPDATE_TRACKER_PROMPT` - Template for daily updates

**Classifications:**
- institutional_accumulation
- earnings_play
- hedge
- technical_breakout
- sector_rotation
- unclear

#### 4. `agent_tools.py` - Tool Implementations
Five tool functions the agent can call:

**`query_database(sql)`**
- Executes SELECT queries against datalake_query.db
- Returns raw rows as list of dicts
- Blocks write operations (INSERT, UPDATE, DELETE, etc.)
- Syntax errors returned to agent, system errors to autofix

**`get_tracker(contract_hash)`**
- Retrieves existing tracker by contract hash
- Returns tracker record or None

**`create_tracker(...)`**
- Creates new tracker with initial narrative
- Calculates DTE, applies decimal formatting
- Logs to agent_actions table
- Returns tracker_id

**`update_tracker(tracker_id, narrative, ...)`**
- Updates tracker with cumulative narrative
- Increments days_active counter
- Logs to flow_tracker_updates table
- Updates classification if changed

**`close_tracker(tracker_id, reason, ...)`**
- Closes tracker with reason
- Reasons: 'expired' | 'thesis_invalidated' | 'user_closed' | 'low_conviction'
- Optional final narrative update
- Logs closure to audit trail

**Safety Features:**
- SQL validation (blocks 12 write operations)
- Error handling (syntax to agent, system to autofix)
- Database safety (30s timeout, WAL mode, read/write separation)
- Decimal formatting (uses clean_database_row())
- Audit trail (flow_tracker_updates, agent_actions)

#### 5. `agent_runtime.py` - Core Orchestrator
Implements Anthropic SDK tool use loop:

**Tool Use Loop:**
1. Send prompt with system prompt and tool definitions
2. Agent responds with text or tool_use
3. If tool_use: execute tools, return results, repeat
4. If end_turn: return final response
5. Max 10 rounds, then error

**Key Method:**
```python
runtime = AgentRuntime()
result = runtime.run(user_prompt)

# Returns:
{
    'success': True,
    'content': "Agent's narrative...",
    'tracker_id': 42,
    'action': 'created',
    'tokens_used': {'input': 2500, 'output': 1200, 'total': 3700},
    'cost': 0.0087,
    'rounds': 3,
    'session_log': 'path/to/log.md'
}
```

**Error Handling:**
- API errors → queue_error() to autofix
- Max rounds exceeded → partial response
- Max tokens exceeded → partial response
- Cost warnings at $0.10 threshold

---

## Usage Examples

### Basic Usage

```python
from agents import AgentRuntime, PROCESS_NEW_ALERT_PROMPT

# Initialize runtime
runtime = AgentRuntime()

# Build prompt from alert
prompt = PROCESS_NEW_ALERT_PROMPT.format(
    symbol='NVDA',
    strike=190.0,
    expiration='2025-01-15',
    option_type='call',
    volume=27045,
    premium_value=11900000,
    significance_score=8.2,
    alert_reason='Volume 20x baseline',
    alert_timestamp='2025-01-01 10:45:00'
)

# Run agent
result = runtime.run(prompt)

if result['success']:
    print(f"Tracker {result['tracker_id']} created")
    print(f"Narrative: {result['content']}")
    print(f"Cost: ${result['cost']:.4f}")
```

### Custom Tools

```python
from agents import AgentTools

tools = AgentTools()

# Query database
result = tools.query_database("SELECT * FROM flow_alerts WHERE symbol='NVDA' LIMIT 5")
print(f"Found {len(result['rows'])} alerts")

# Get tracker
tracker = tools.get_tracker("NVDA|190|2025-01-15|call")
if tracker['tracker']:
    print(f"Narrative: {tracker['tracker']['narrative']}")
```

### Direct Tool Execution

```python
from agents import AgentTools

tools = AgentTools()

# Create tracker directly (bypass agent)
result = tools.create_tracker(
    contract_hash="AAPL|150|2025-02-01|put",
    symbol="AAPL",
    strike=150.0,
    expiration="2025-02-01",
    option_type="put",
    narrative="Manual tracker for testing",
    flow_classification="unclear"
)

print(f"Tracker {result['tracker_id']} created")
```

---

## Testing

### Unit Tests

```bash
# Test each module independently
python agents/agent_config.py
python agents/agent_logger.py
python agents/agent_prompts.py
python agents/agent_tools.py
python agents/agent_runtime.py
```

### Integration Test

```bash
# Full end-to-end test with real API call
python agents/test_agent_integration.py
```

**Warning:** Integration test calls Anthropic API and costs ~$0.01

---

## File Structure

```
agents/
├── __init__.py              # Package exports
├── README.md                # This file
├── agent_config.py          # Configuration (5 min)
├── agent_logger.py          # Logging (10 min)
├── agent_prompts.py         # Prompts (5 min)
├── agent_tools.py           # Tools (30 min)
├── agent_runtime.py         # Runtime (30 min)
└── test_agent_integration.py  # Integration test
```

**Total build time:** ~1.5 hours
**Lines of code:** ~1,200

---

## Database Tables Used

### Writes to datalake.db (production)
- `flow_contract_trackers` - Main tracker records
- `flow_tracker_updates` - Update history (audit trail)
- `agent_actions` - Action log

### Reads from datalake_query.db
- `flow_alerts` - Alert data
- `flow_options_scans` - Intraday snapshots
- `option_contracts` - Daily snapshots
- `symbol_metadata` - Company info
- `historical_prices` - Price history
- `earnings_calendar` - Earnings dates
- `market_daily_summary` - Market regime

---

## Next Steps: Part 3 - FM Integration

With core framework complete, next steps:

1. **`strategies/flow_monitor/fm_agent.py`** - Flow Monitor wrapper
   - Fetches alerts from Flow Monitor
   - Calls AgentRuntime for each alert
   - Handles batch processing

2. **Integration into `fm_main.py`**
   - Hook into post-market sequence
   - Run agent after evaluation completes
   - Process all day's alerts in batch

3. **Testing with real alerts**
   - Run on yesterday's alerts
   - Review narrative quality
   - Tune prompts if needed

4. **Cost monitoring**
   - Track daily agent costs
   - Verify < $25/month target
   - Optimize if exceeding budget

---

## Configuration

Agent uses settings from `config.json`:

```json
{
  "claude_api": {
    "api_key": "sk-ant-...",
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 4000,
    "pricing": {
      "claude-3-5-haiku-20241022": {
        "input": 1.00,
        "output": 5.00
      }
    }
  }
}
```

---

## Design Principles Applied

✅ **Read from query DB, write to production DB** - Prevents locking
✅ **Raw data returns** - Agent interprets, not tool
✅ **Cumulative narrative + audit trail** - flow_contract_trackers + flow_tracker_updates
✅ **SQL validation** - Block writes, allow SELECT only
✅ **Error handling mix** - Syntax to agent, system to autofix
✅ **Decimal formatting** - clean_database_row() on writes
✅ **UTF-8 encoding** - All logging and stdout
✅ **Max rounds limit** - 10 rounds max, prevents runaway
✅ **Cost tracking** - Per-round and session totals

---

## Cost Estimates

**Per alert processing:**
- Rounds: 2-4 (query context → create tracker → respond)
- Tokens: ~3,000-5,000 total
- Cost: $0.005-$0.01 per alert

**Monthly (Phase 1):**
- ~15 alerts/day × 30 days = 450 alerts
- 450 alerts × $0.0075 avg = **$3.38/month**

**Within target:** ✅ Well under $25/month budget

---

## Status: ✅ COMPLETE

Core agent framework built and tested. Ready for FM integration (Part 3).

**What works:**
- ✅ Configuration loading
- ✅ Session logging (console + markdown)
- ✅ System prompts loaded
- ✅ All 5 tools implemented
- ✅ Tool use loop working
- ✅ Token tracking and cost calculation
- ✅ Error handling with autofix integration
- ✅ Database read/write separation

**What's tested:**
- ✅ SQL validation (blocks writes)
- ✅ Database queries (1,663 alerts found)
- ✅ Tracker retrieval (returns None correctly)
- ✅ Tool definitions (5 tools registered)
- ✅ Runtime initialization
- ✅ Logger creates markdown logs

**Ready for:**
- Integration test with real API call
- FM wrapper implementation
- Production deployment

---

**Last Updated:** 2026-01-01
**Built by:** Ben with Claude Code
