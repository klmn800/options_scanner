# Agentic Sector Rotation Agent - Implementation Plan

**FOR: Claude Code (future sessions)**
**DATE: 2025-10-29**
**STATUS: Ready to implement**

---

## Purpose of This Document

This document is written **for Claude Code to read in future sessions** when implementing the sector rotation agent. It contains all decisions, architecture, and step-by-step implementation instructions to stay on track after conversation memory fades.

**User (Ben) expects:**
- Natural language sector intelligence
- Actionable insights with specific numbers
- Cost-effective agentic exploration
- Production-ready with safety guardrails

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Problem Statement](#problem-statement)
3. [Solution Architecture](#solution-architecture)
4. [Data Schema](#data-schema)
5. [Tool Registry Implementation](#tool-registry-implementation)
6. [Agentic Loop Implementation](#agentic-loop-implementation)
7. [Caching Strategy](#caching-strategy)
8. [TUI Integration](#tui-integration)
9. [Testing Plan](#testing-plan)
10. [Oracle Evolution Path](#oracle-evolution-path)

---

## Quick Reference

**Files to create:**
```
tools/
├── agent_tools.py           # Tool registry (NEW)
└── executors/
    └── database_tools.py    # SQL execution wrappers (NEW)

morning_view/
├── sector_rotation_agent.py  # Agentic analysis engine (NEW)
├── sector_rotation_data.py   # Caching layer (NEW)
└── screens/
    └── sector_rotation.py    # TUI screen (NEW)

data/
└── analysis_cache.db
    └── sector_ai_rotation    # Cache table (CREATE)
```

**Key decisions made:**
- Use direct SQL (not Oracle/Vanna) for speed
- Sonnet 4.5 model for intelligence (not Haiku)
- 8 iteration max for cost control
- Cache results in analysis_cache.db indefinitely
- One-liner per sector + market summary
- Actionable language with specific numbers

**Cost targets:**
- Headline analysis: $0.003-0.005
- Market deep dive: $0.008-0.012
- Sector drill-down: $0.010-0.015

---

## Problem Statement

### User's Need

**From Ben:**
> "I'm no financial analyst. I'm a prompt user. I ask natural language questions,
> and hopefully get honest accurate actionable natural language answers in language
> I understand. TUI saves me money by putting data in front of me, but it's not like
> I know what it all means, or what's missing..."

**Translation:** User wants AI to BE the analyst, not just display data.

### Specific Use Case: Sector Rotation

**User wants to know:**
- Where is money moving in the market? (volume increasing/decreasing)
- Which sectors show momentum building? (early detection before IV spike)
- What does this mean for my trades? (actionable implications)

**Current gap:**
- Morning Views shows triggered symbols (data display)
- User must interpret patterns themselves (requires expertise)
- No cross-sector synthesis (can't see big picture)

**Solution:** Agentic analyst that explores data and provides clear recommendations.

---

## Solution Architecture

### Three-Tier Analysis System

```
┌─────────────────────────────────────────────┐
│ TIER 1: HEADLINE ANALYSIS                   │
│ Press SPACE → AI explores 11 sectors        │
│ Output: One sentence per sector             │
│ Cost: ~$0.005                                │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ TIER 2: MARKET DEEP DIVE                    │
│ Press M → AI analyzes cross-sector flows    │
│ Output: 3-4 paragraph market synthesis      │
│ Cost: ~$0.010                                │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ TIER 3: SECTOR/INDUSTRY DRILL-DOWN          │
│ Press S/I/A → AI deep-dives specific group  │
│ Output: Symbol-level analysis               │
│ Cost: ~$0.015                                │
└─────────────────────────────────────────────┘
```

### Agentic Flow (Tier 1 Example)

```
User: Press SPACE for sector analysis

Agent: [Iteration 1]
Tool Call: query_database(sql="
    SELECT sm.sector, AVG(hp.volume) as avg_vol_5d
    FROM historical_prices hp
    JOIN symbol_metadata sm ON hp.symbol = sm.symbol
    WHERE hp.trade_date >= date('now', '-5 days')
    GROUP BY sm.sector
")

Agent: [Receives results]
"Tech 120M/day, Healthcare 45M/day..."

Agent: [Iteration 2]
Tool Call: query_database(sql="
    SELECT sm.sector, AVG(hp.volume) as avg_vol_30d
    FROM historical_prices hp
    JOIN symbol_metadata sm ON hp.symbol = sm.symbol
    WHERE hp.trade_date >= date('now', '-30 days')
    AND hp.trade_date < date('now', '-5 days')
    GROUP BY sm.sector
")

Agent: [Receives results]
"Historical: Tech 90M/day avg, Healthcare 42M/day..."

Agent: [Iteration 3]
Tool Call: query_database(sql="
    SELECT sm.sector, AVG(oss.total_volume) as option_vol
    FROM option_symbol_summary oss
    JOIN symbol_metadata sm ON oss.symbol = sm.symbol
    WHERE oss.trade_date >= date('now', '-5 days')
    GROUP BY sm.sector
")

Agent: [Analyzes all data]
"Sufficient data for analysis. Generating sector summaries..."

Agent: [Returns final analysis]
Technology: Stock volume +33% (120M vs 90M avg), option volume +65% → Activity building before IV spike (still at 35th %ile) → Position now
Healthcare: Put volume doubled (1,200→2,400/day), price flat → Hedging activity suggests downside concern → Watch for breakdown
Energy: Volume declining -30% over 2wks, XLE up 2.1% but XOM down 0.5% → Sector strength artificial, avoid chasing
...
[All 11 sectors]

Overall: Tech/Healthcare showing sustained momentum builds (15+ days), Energy/Financials losing participation. Risk-on rotation favoring growth but defensive hedging building.
```

---

## Data Schema

### Primary Tables

**1. market_daily_summary (Sector ETFs)**
```sql
-- Sector ETF price data
xlf_close, xlf_change_percent  -- Financials
xle_close, xle_change_percent  -- Energy
xlk_close, xlk_change_percent  -- Technology
xlv_close, xlv_change_percent  -- Healthcare
xli_close, xli_change_percent  -- Industrials
xlp_close, xlp_change_percent  -- Consumer Staples
xly_close, xly_change_percent  -- Consumer Discretionary
xlu_close, xlu_change_percent  -- Utilities
xlb_close, xlb_change_percent  -- Materials
xlre_close, xlre_change_percent -- Real Estate

-- Note: SPY, QQQ, IWM also available for market context
```

**2. historical_prices (Individual Stock Volume/Price)**
```sql
symbol TEXT
trade_date DATE
open, high, low, close REAL
volume INTEGER  -- KEY: Daily volume by symbol
```

**3. option_symbol_summary (Option Activity)**
```sql
symbol TEXT
trade_date DATE
total_volume INTEGER  -- Total option volume
put_volume INTEGER
call_volume INTEGER
put_call_ratio REAL
iv_rank REAL  -- IV percentile (0-100)
```

**4. symbol_metadata (Sector Mapping)**
```sql
symbol TEXT PRIMARY KEY
sector TEXT  -- 11 sectors: Technology, Healthcare, Energy, etc.
industry TEXT  -- ~40-50 industries: Semiconductors, Airlines, Banks, etc.
archive_db TEXT  -- 13 curated groups: airlines, asset_management, etc.
```

### Available Sectors

```
1. Technology (128 symbols)
2. Healthcare (81 symbols)
3. Energy (42 symbols)
4. Financials (110 symbols)
5. Industrials (104 symbols)
6. Consumer Cyclical (101 symbols)
7. Consumer Defensive (50 symbols)
8. Utilities (32 symbols)
9. Real Estate (42 symbols)
10. Basic Materials (34 symbols)
11. Communication Services (25 symbols)
```

### Example Queries Agent Might Generate

**Stock volume trend by sector:**
```sql
SELECT
    sm.sector,
    AVG(hp.volume) as avg_volume_5d,
    COUNT(DISTINCT hp.symbol) as symbol_count
FROM historical_prices hp
JOIN symbol_metadata sm ON hp.symbol = sm.symbol
WHERE hp.trade_date >= date('now', '-5 days')
GROUP BY sm.sector
ORDER BY avg_volume_5d DESC
```

**Compare to historical baseline:**
```sql
SELECT
    sm.sector,
    AVG(CASE WHEN hp.trade_date >= date('now', '-5 days') THEN hp.volume END) as recent_vol,
    AVG(CASE WHEN hp.trade_date < date('now', '-5 days') THEN hp.volume END) as baseline_vol,
    (AVG(CASE WHEN hp.trade_date >= date('now', '-5 days') THEN hp.volume END) /
     AVG(CASE WHEN hp.trade_date < date('now', '-5 days') THEN hp.volume END) - 1) * 100 as pct_change
FROM historical_prices hp
JOIN symbol_metadata sm ON hp.symbol = sm.symbol
WHERE hp.trade_date >= date('now', '-30 days')
GROUP BY sm.sector
```

**Option activity by sector:**
```sql
SELECT
    sm.sector,
    AVG(oss.total_volume) as avg_option_vol,
    AVG(oss.put_call_ratio) as avg_pc_ratio,
    AVG(oss.iv_rank) as avg_iv_rank
FROM option_symbol_summary oss
JOIN symbol_metadata sm ON oss.symbol = sm.symbol
WHERE oss.trade_date >= date('now', '-5 days')
GROUP BY sm.sector
```

---

## Tool Registry Implementation

### Step 1: Create Tool Registry Module

**File: `tools/agent_tools.py`**

```python
#!/usr/bin/env python3
"""
Agentic Tool Registry
Centralized tool definitions for all agentic systems in options_scanner.

Tools are defined once here and imported by any agent that needs them.
This ensures consistency and eliminates duplicate tool definitions.
"""

import json
from typing import Dict, List, Any

# ========== Tool Definitions ==========

def get_database_query_tool() -> dict:
    """
    Define the query_database tool.

    Translation: This function returns a JSON schema that tells Claude
    it can query the database by providing SQL and a purpose description.
    """
    return {
        "name": "query_database",
        "description": """Execute SQL query against datalake_query.db.

Available tables:
- market_daily_summary: Sector ETF daily data (XLF, XLE, XLK, XLV, XLI, XLP, XLY, XLU, XLB, XLRE)
- historical_prices: Stock OHLC + volume (symbol, trade_date, volume)
- option_symbol_summary: Option metrics (symbol, total_volume, put_call_ratio, iv_rank)
- symbol_metadata: Symbol mappings (symbol, sector, industry, archive_db)

Only SELECT queries allowed. Use JOINs to combine tables.
Lookback windows: 5d (recent), 10d (short-term), 20d (medium), 30d+ (baseline)""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL SELECT query to execute"
                },
                "purpose": {
                    "type": "string",
                    "description": "What you're trying to learn from this query (for logging)"
                }
            },
            "required": ["sql"]
        }
    }

def get_all_tools() -> List[dict]:
    """
    Get all available tools for agents.

    Translation: Returns a list of all tool definitions. Agents can request
    all tools or filter to specific ones they need.
    """
    return [
        get_database_query_tool(),
        # Future: add more tools here (calculate_greeks, get_earnings, etc.)
    ]

def get_tools_for_agent(agent_type: str) -> List[dict]:
    """
    Get tools relevant for specific agent type.

    Translation: Different agents need different tools. This function
    returns the appropriate subset for each agent type.

    Args:
        agent_type: "sector_rotation", "oracle", "trade_recommender", etc.
    """
    tool_map = {
        "sector_rotation": [get_database_query_tool()],
        "oracle": [get_database_query_tool()],
        "trade_recommender": get_all_tools()
    }
    return tool_map.get(agent_type, get_all_tools())
```

### Step 2: Create Execution Layer

**File: `tools/executors/database_tools.py`**

```python
#!/usr/bin/env python3
"""
Database Tool Executors
Safely executes database queries requested by agentic systems.
"""

import sys
import json
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from tools.direct_db_query import DirectDBQuery

class SafeDatabaseExecutor:
    """
    Executes database queries with safety checks.

    Translation: This class wraps direct_db_query.py and adds safety
    mechanisms to prevent AI from running dangerous queries.
    """

    def __init__(self, db_path='data/datalake_query.db'):
        """
        Initialize executor with database path.

        Translation: Create connection to query database (read-only copy).
        """
        self.db = DirectDBQuery(db_path)
        self.forbidden_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE', 'CREATE']
        self.max_rows = 1000

    def execute(self, sql: str, purpose: str = None) -> dict:
        """
        Execute SQL query with safety checks.

        Translation: Run the SQL query but first verify it's safe (read-only,
        reasonable size limit). Return results as JSON.

        Args:
            sql: SQL query to execute
            purpose: Optional description of query intent (for logging)

        Returns:
            dict with "results", "row_count", or "error"
        """
        # Safety check 1: No dangerous keywords
        # Translation: Block any SQL that could modify or delete data
        if any(keyword in sql.upper() for keyword in self.forbidden_keywords):
            return {
                "error": f"Forbidden SQL keyword detected. Only SELECT queries allowed.",
                "sql": sql
            }

        # Safety check 2: Must start with SELECT
        # Translation: Only allow read queries, not CREATE TABLE etc.
        if not sql.strip().upper().startswith('SELECT'):
            return {
                "error": "Query must start with SELECT",
                "sql": sql
            }

        # Safety check 3: Add LIMIT if missing
        # Translation: Prevent accidentally querying millions of rows
        if 'LIMIT' not in sql.upper():
            sql += f' LIMIT {self.max_rows}'

        # Execute query
        # Translation: Run the SQL using existing direct_db_query.py utility
        try:
            results = self.db.execute_query(sql)

            if not results:
                return {
                    "results": [],
                    "row_count": 0,
                    "message": "Query returned no results"
                }

            # Check result size
            # Translation: If result is huge, truncate it to save tokens
            if len(results) > 100:
                return {
                    "results": results[:100],
                    "row_count": len(results),
                    "truncated": True,
                    "message": f"Results truncated to 100 rows (total: {len(results)})"
                }

            return {
                "results": results,
                "row_count": len(results)
            }

        except Exception as e:
            return {
                "error": f"Query execution failed: {str(e)}",
                "sql": sql
            }

# Global executor instance
# Translation: Create one executor that all agents can use
_executor = None

def execute_query_database(inputs: dict) -> dict:
    """
    Execute database query (called by agents).

    Translation: This is the function that agents actually call when they
    want to query the database. It uses the SafeDatabaseExecutor class.

    Args:
        inputs: Dict with "sql" and optional "purpose" keys

    Returns:
        Query results or error message
    """
    global _executor
    if _executor is None:
        _executor = SafeDatabaseExecutor()

    return _executor.execute(
        sql=inputs['sql'],
        purpose=inputs.get('purpose')
    )
```

### Step 3: Create Master Executor Router

**Add to `tools/agent_tools.py`:**

```python
# ========== Tool Execution Router ==========

def execute_tool(tool_name: str, inputs: dict) -> dict:
    """
    Execute any registered tool.

    Translation: This is the master routing function. Agents call this
    with a tool name, and it routes to the correct execution function.

    Args:
        tool_name: Name of tool to execute ("query_database", etc.)
        inputs: Parameters for the tool

    Returns:
        Tool execution results
    """
    if tool_name == "query_database":
        from tools.executors.database_tools import execute_query_database
        return execute_query_database(inputs)

    # Future tools go here
    # elif tool_name == "calculate_greeks":
    #     from tools.executors.analytics_tools import execute_calculate_greeks
    #     return execute_calculate_greeks(inputs)

    else:
        return {"error": f"Unknown tool: {tool_name}"}
```

---

## Agentic Loop Implementation

### Step 1: Create Agentic Analysis Engine

**File: `morning_view/sector_rotation_agent.py`**

```python
#!/usr/bin/env python3
"""
Sector Rotation Agentic Analyst
Autonomous database exploration for sector rotation intelligence.
"""

import sys
import json
from pathlib import Path
from typing import Dict, List

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from tools.agent_tools import get_tools_for_agent, execute_tool

class SectorRotationAgent:
    """
    Agentic analyst for sector rotation patterns.

    Translation: This class implements the agentic loop. It gives Claude
    tools to query the database, then lets Claude explore autonomously
    until it has enough data to provide an answer.
    """

    def __init__(self, config):
        """
        Initialize agent with configuration.

        Translation: Set up Claude API client, get tool definitions,
        and configure cost/iteration limits.
        """
        self.config = config
        claude_config = config.get('claude_api', {})

        self.client = anthropic.Anthropic(
            api_key=claude_config.get('api_key')
        )

        self.model = "claude-sonnet-4.5-20250929"  # Sonnet for intelligence
        self.tools = get_tools_for_agent("sector_rotation")

        # Cost controls
        self.max_iterations = 8
        self.max_cost_per_analysis = 0.05  # $0.05 safety limit

        # Session tracking
        self.session_tokens = 0
        self.session_cost = 0.0
        self.iteration_log = []

    def analyze_headline(self, trade_date: str) -> dict:
        """
        Generate headline analysis (one-liner per sector).

        Translation: This runs the agentic loop to analyze all 11 sectors.
        Claude autonomously queries data until it can provide one actionable
        sentence per sector.

        Args:
            trade_date: Date to analyze (YYYY-MM-DD)

        Returns:
            dict with "analysis", "iterations", "cost", "tokens"
        """
        system_prompt = self._build_headline_system_prompt()
        user_prompt = f"Analyze sector rotation patterns for {trade_date}. Provide one actionable sentence per sector (all 11 sectors) with specific numbers."

        messages = [{"role": "user", "content": user_prompt}]

        # Agentic loop
        # Translation: Keep looping until Claude says it's done or we hit limits
        for iteration in range(self.max_iterations):
            response = self.client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=messages,
                tools=self.tools,
                max_tokens=4000
            )

            # Track usage
            # Translation: Count tokens and calculate cost for this iteration
            self._track_usage(response.usage)

            # Log this iteration
            # Translation: Save what happened for debugging
            self.iteration_log.append({
                "iteration": iteration + 1,
                "stop_reason": response.stop_reason,
                "content_blocks": len(response.content)
            })

            # Check if Claude is done
            # Translation: Claude signals "end_turn" when it has final answer
            if response.stop_reason == "end_turn":
                final_analysis = self._extract_text(response)
                return {
                    "success": True,
                    "analysis": final_analysis,
                    "iterations": iteration + 1,
                    "tokens": self.session_tokens,
                    "cost": self.session_cost,
                    "log": self.iteration_log
                }

            # Claude wants to use tools
            # Translation: Claude requested database queries
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    # Execute tool
                    # Translation: Run the query Claude requested
                    result = execute_tool(block.name, block.input)

                    # Log tool call
                    self.iteration_log[-1]["tool_calls"] = self.iteration_log[-1].get("tool_calls", [])
                    self.iteration_log[-1]["tool_calls"].append({
                        "tool": block.name,
                        "input": block.input,
                        "result_rows": result.get("row_count", 0)
                    })

                    # Prepare tool result for Claude
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result)
                    })

            # Continue conversation
            # Translation: Add Claude's request and our results to conversation
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            # Cost safety check
            # Translation: Stop if cost exceeds limit
            if self.session_cost > self.max_cost_per_analysis:
                return {
                    "success": False,
                    "error": f"Cost limit exceeded: ${self.session_cost:.4f}",
                    "iterations": iteration + 1,
                    "log": self.iteration_log
                }

        # Max iterations reached
        # Translation: Claude didn't finish in 8 rounds
        return {
            "success": False,
            "error": "Max iterations reached without completion",
            "iterations": self.max_iterations,
            "tokens": self.session_tokens,
            "cost": self.session_cost,
            "log": self.iteration_log
        }

    def _build_headline_system_prompt(self) -> str:
        """
        Build system prompt for headline analysis.

        Translation: This tells Claude what its role is and how to
        analyze sectors. Includes output format requirements.
        """
        return """You are a quantitative sector rotation analyst providing actionable trading intelligence.

MISSION: Analyze sector rotation patterns to identify where money is moving in the market.

APPROACH:
1. Query database autonomously to gather sector data (volume, price, option activity)
2. Compare recent activity (5d) to baselines (20d, 30d) to identify changes
3. Identify momentum builds vs temporary spikes
4. Assess IV context (room for expansion = opportunity)

OUTPUT REQUIREMENTS:
- One actionable sentence per sector (ALL 11 sectors required)
- Include specific numbers (percentages, volume counts)
- Focus on IMPLICATIONS (what this means for trades)
- End with overall market summary (2-3 sentences)

SECTORS TO ANALYZE:
1. Technology
2. Healthcare
3. Energy
4. Financials
5. Industrials
6. Consumer Cyclical
7. Consumer Defensive
8. Utilities
9. Real Estate
10. Basic Materials
11. Communication Services

OUTPUT STYLE EXAMPLES:
✅ "Technology: Stock volume +45% (120M vs 85M avg), option volume +65% → Activity building before IV spike (35th %ile) → Position now"
✅ "Energy: Volume declining -30% over 2wks, XLE up 2.1% but volume weak → Unsustainable, avoid chasing"
✅ "Healthcare: Put volume doubled (1,200→2,400/day), price flat → Defensive positioning building, watch for breakdown"

❌ "Technology sector showing strength" (too vague)
❌ "Healthcare has mixed signals" (no numbers, no implication)

FORBIDDEN LANGUAGE: "nuanced", "suggests", "indicates", "underlying dynamics"
REQUIRED LANGUAGE: Specific numbers + directional assessment + trading implication

Query the database as many times as needed to gather sufficient data. Be thorough."""

    def _track_usage(self, usage):
        """
        Track token usage and cost.

        Translation: Count tokens and calculate cost for Sonnet 4.5.
        """
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens

        # Sonnet 4.5 pricing (per million tokens)
        cost = (input_tokens * 0.000003) + (output_tokens * 0.000015)

        self.session_tokens += (input_tokens + output_tokens)
        self.session_cost += cost

    def _extract_text(self, response) -> str:
        """
        Extract text from Claude's response.

        Translation: Pull out the analysis text from response blocks.
        """
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
```

---

## Caching Strategy

### Create Cache Table

**Execute this SQL against `data/analysis_cache.db`:**

```sql
CREATE TABLE IF NOT EXISTS sector_ai_rotation (
    trade_date TEXT PRIMARY KEY,
    headline_analysis TEXT NOT NULL,      -- Tier 1: One-liners for all sectors
    market_deep_dive TEXT,                -- Tier 2: Cross-sector synthesis (lazy-loaded)
    sector_drilldowns TEXT,               -- Tier 3: JSON {"Technology": "...", "Healthcare": "..."}
    industry_drilldowns TEXT,             -- Tier 3: JSON {"Semiconductors": "...", "Airlines": "..."}
    archive_drilldowns TEXT,              -- Tier 3: JSON {"airlines": "...", "technology": "..."}
    data_snapshot TEXT NOT NULL,          -- JSON: Raw metrics for reproducibility
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sector_rotation_date ON sector_ai_rotation(trade_date);
```

### Create Caching Layer

**File: `morning_view/sector_rotation_data.py`**

```python
#!/usr/bin/env python3
"""
Sector Rotation Data Layer
Caching and retrieval for sector rotation analyses.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

class SectorRotationCache:
    """
    Cache manager for sector rotation analyses.

    Translation: Handles saving and loading analyses from database.
    One row per trade_date with all analysis tiers in JSON columns.
    """

    def __init__(self, db_path='data/analysis_cache.db'):
        """Initialize cache with database path."""
        if not Path(db_path).is_absolute():
            project_root = Path(__file__).parent.parent
            db_path = project_root / db_path

        self.db_path = str(db_path)
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sector_ai_rotation (
                trade_date TEXT PRIMARY KEY,
                headline_analysis TEXT NOT NULL,
                market_deep_dive TEXT,
                sector_drilldowns TEXT,
                industry_drilldowns TEXT,
                archive_drilldowns TEXT,
                data_snapshot TEXT NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                cost_usd REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def get_headline(self, trade_date: str) -> dict:
        """
        Get cached headline analysis.

        Translation: Check if we already analyzed this date.
        Returns cached analysis or None if not found.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT headline_analysis, input_tokens, output_tokens, cost_usd, created_at
            FROM sector_ai_rotation
            WHERE trade_date = ?
        """, (trade_date,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "analysis": row["headline_analysis"],
            "tokens": row["input_tokens"] + row["output_tokens"],
            "cost": row["cost_usd"],
            "created_at": row["created_at"],
            "from_cache": True
        }

    def save_headline(self, trade_date: str, analysis: str, tokens: int, cost: float, data_snapshot: dict):
        """
        Save headline analysis to cache.

        Translation: Store analysis in database for future retrieval.
        """
        conn = sqlite3.connect(self.db_path)
        now = datetime.now().isoformat()

        conn.execute("""
            INSERT OR REPLACE INTO sector_ai_rotation
            (trade_date, headline_analysis, data_snapshot, input_tokens, output_tokens, cost_usd, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (trade_date, analysis, json.dumps(data_snapshot), tokens // 2, tokens // 2, cost, now, now))

        conn.commit()
        conn.close()
```

---

## TUI Integration

**File: `morning_view/screens/sector_rotation.py`**

```python
#!/usr/bin/env python3
"""
Sector Rotation TUI Screen
Interactive sector rotation analysis interface.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Button
from textual.containers import Container, ScrollableContainer
from textual.binding import Binding

from morning_view.sector_rotation_agent import SectorRotationAgent
from morning_view.sector_rotation_data import SectorRotationCache
from tools.timezone_utils import eastern_date_string

class SectorRotationScreen(Screen):
    """Sector rotation analysis screen"""

    BINDINGS = [
        Binding("space", "analyze", "Analyze Sectors", show=True),
        Binding("m", "market_deep_dive", "Market Deep Dive", show=True),
        Binding("escape", "back", "Back", show=True)
    ]

    def compose(self) -> ComposeResult:
        """Create screen layout."""
        yield Header()
        yield Container(
            Static("", id="analysis-display"),
            id="sector-container"
        )
        yield Footer()

    def on_mount(self):
        """Initialize screen on mount."""
        self._show_initial_state()

    def _show_initial_state(self):
        """Show empty state with instructions."""
        content = self.query_one("#analysis-display", Static)
        content.update("""[bold cyan]Sector Rotation Analysis[/bold cyan]

Press [bold]SPACE[/bold] to analyze sector rotation patterns

This will use AI to autonomously explore the database and identify:
• Where money is flowing (volume increases/decreases)
• Which sectors show momentum building
• Trading opportunities before IV spikes

Cost: ~$0.005 per analysis (cached for 1 day)
""")

    def action_analyze(self):
        """Run sector rotation analysis."""
        content = self.query_one("#analysis-display", Static)
        content.update("[yellow]Analyzing sectors... (this may take 30-60 seconds)[/yellow]")

        # Get current trade date
        trade_date = eastern_date_string()

        # Check cache
        cache = SectorRotationCache()
        cached = cache.get_headline(trade_date)

        if cached:
            self._display_analysis(cached["analysis"], cached["cost"], cached["tokens"], from_cache=True)
            return

        # Run agentic analysis
        try:
            import json
            config_path = Path(__file__).parent.parent.parent / 'config.json'
            with open(config_path) as f:
                config = json.load(f)

            agent = SectorRotationAgent(config)
            result = agent.analyze_headline(trade_date)

            if result["success"]:
                # Save to cache
                cache.save_headline(
                    trade_date=trade_date,
                    analysis=result["analysis"],
                    tokens=result["tokens"],
                    cost=result["cost"],
                    data_snapshot={"iterations": result["iterations"]}
                )

                self._display_analysis(
                    result["analysis"],
                    result["cost"],
                    result["tokens"],
                    from_cache=False
                )
            else:
                content.update(f"[red]Analysis failed: {result['error']}[/red]")

        except Exception as e:
            content.update(f"[red]Error: {str(e)}[/red]")

    def _display_analysis(self, analysis: str, cost: float, tokens: int, from_cache: bool):
        """Display analysis results."""
        content = self.query_one("#analysis-display", Static)

        cache_indicator = "[green](from cache - free)[/green]" if from_cache else f"[yellow](${cost:.4f}, {tokens} tokens)[/yellow]"

        display_text = f"""[bold cyan]Sector Rotation Analysis[/bold cyan]
{eastern_date_string()} {cache_indicator}

{analysis}

[dim]Press M for market deep dive | ESC to return[/dim]"""

        content.update(display_text)

    def action_market_deep_dive(self):
        """Placeholder for market deep dive."""
        # TODO: Implement in Phase 2
        pass

    def action_back(self):
        """Return to main menu."""
        self.app.pop_screen()
```

**Add to main menu (`morning_view/screens/main_menu.py`):**

```python
Binding("7", "sector_rotation", "Sector Rotation")

def action_sector_rotation(self):
    """Show sector rotation screen"""
    from morning_view.screens.sector_rotation import SectorRotationScreen
    self.app.push_screen(SectorRotationScreen())
```

---

## Testing Plan

### Phase 1: Tool Registry Testing

```bash
# Test tool definitions
python -c "from tools.agent_tools import get_all_tools; import json; print(json.dumps(get_all_tools(), indent=2))"

# Test database executor
python -c "from tools.executors.database_tools import execute_query_database; print(execute_query_database({'sql': 'SELECT COUNT(*) FROM market_daily_summary'}))"

# Test safety checks
python -c "from tools.executors.database_tools import execute_query_database; print(execute_query_database({'sql': 'DROP TABLE market_daily_summary'}))"  # Should fail
```

### Phase 2: Agentic Loop Testing

```bash
# Test headline analysis (command line)
python morning_view/sector_rotation_agent.py --date 2025-10-28

# Expected output:
# - 3-8 iterations
# - ~$0.005 cost
# - Analysis with all 11 sectors
```

### Phase 3: Caching Testing

```bash
# First run (should query database)
python morning_view/sector_rotation_agent.py --date 2025-10-28

# Second run (should use cache)
python morning_view/sector_rotation_agent.py --date 2025-10-28
# Should be instant and free
```

### Phase 4: TUI Testing

```bash
# Launch TUI and navigate to sector rotation
python morning_view/mv_main.py
# Press 7, then SPACE
# Verify analysis displays
```

---

## Oracle Evolution Path

### Current State (Oracle by Vanna)

**What exists:**
- `oracle/oracle_main.py` - Vanna-based SQL generator
- `tools/oracle_bridge.py` - Programmatic interface
- Single question → single answer pattern

**Why it's sitting unused:**
- Vanna adds complexity (extra AI layer for SQL generation)
- Claude Code's direct SQL is better (you understand the schema)
- Doesn't match original vision (omniscient analyst)

### Original Vision (Ben's Words)

> "Imagine an omniscient being that lives inside the stock market...
> you could ask it questions and it could review the entire universe
> of data to bring you an actionable answer, almost predicting the
> future, based on vast data it has access to, current and historic."

**Translation:** Oracle should be an agentic analyst that autonomously explores your entire data warehouse to answer any question about the market.

### Future: Oracle Rebuilt as Agentic System

**After sector rotation agent proves the pattern:**

1. **Strip Vanna dependency**
   - Keep oracle_bridge.py structure for compatibility
   - Replace Vanna SQL generation with direct Claude tool calling
   - Use same tool registry as sector rotation

2. **Expand tool capabilities**
   - query_database (same as sector rotation)
   - calculate_metrics (Greeks, IV percentiles)
   - get_earnings_info (earnings calendar queries)
   - analyze_historical_patterns (precedent matching)

3. **Build conversational interface**
   - Command line first: `oracle.ask("What should I trade today?")`
   - TUI integration second: "Ask Oracle" screen
   - Multi-turn conversations (follow-up questions)

4. **Architecture:**
```python
# oracle/agentic_oracle.py
class Oracle:
    """Omniscient market intelligence system"""

    def ask(self, question: str) -> dict:
        """
        Ask Oracle any question about market data.
        Oracle explores autonomously until it has high-confidence answer.
        """
        tools = get_tools_for_agent("oracle")  # All tools

        system_prompt = """You are the Oracle - omniscient market intelligence.

        You have access to vast market data:
        - 87 days of market history
        - 800 symbols with prices, volume, OI, flow
        - Sector ETFs and cross-asset data
        - Earnings calendar and historical moves

        Explore autonomously. Query multiple timeframes. Connect dots across tables.
        Provide high-confidence predictions based on historical patterns."""

        # Agentic loop (10-15 iterations for complex questions)
        result = self._agentic_exploration(question, system_prompt, tools)
        return result
```

5. **Cost management**
   - Simple questions: 3-5 iterations (~$0.01)
   - Complex questions: 10-15 iterations (~$0.05)
   - Max limit: $0.10 per question

6. **TUI Integration**
```
Main Menu:
[7] Sector Rotation
[O] Ask Oracle               ← NEW

Oracle Screen:
┌─────────────────────────────────────────┐
│ Oracle - Market Intelligence            │
├─────────────────────────────────────────┤
│ > What should I trade today?            │
│                                          │
│ [Oracle exploring... iteration 7/15]    │
│                                          │
│ [Shows analysis when complete]          │
│                                          │
│ Follow-up question: _                   │
└─────────────────────────────────────────┘
```

### Timeline

**Phase 1: Sector Rotation (Week 1)**
- Prove agentic pattern works
- Learn cost/iteration characteristics
- Build tool registry foundation

**Phase 2: Tool Expansion (Week 2)**
- Add more tools to registry
- Test with sector rotation agent
- Validate safety mechanisms

**Phase 3: Oracle Rebuild (Week 3-4)**
- Implement agentic Oracle
- Command-line interface first
- TUI integration second

**Phase 4: Additional Agents (Ongoing)**
- Trade recommender
- Earnings play scout
- Portfolio risk analyzer

---

## Success Criteria

### Minimum Viable Product (Phase 1)

**Must have:**
- ✅ Tool registry functional (`agent_tools.py`)
- ✅ Database executor with safety checks
- ✅ Agentic loop producing sector analysis
- ✅ Caching working (1 day persistence)
- ✅ TUI screen displaying results
- ✅ Cost < $0.01 per analysis
- ✅ Analysis quality: specific numbers, actionable language

**Nice to have:**
- Market deep dive (Tier 2)
- Sector drill-down (Tier 3)
- Historical comparison mode

### Quality Validation

**Analysis must include:**
1. All 11 sectors analyzed (no skipping)
2. Specific numbers (%, M/day volumes)
3. Comparisons (vs historical baseline)
4. Trading implications (what to do)
5. Overall market summary

**Example passing analysis:**
```
Technology: Stock volume +33% (120M vs 90M avg), option volume +65%
→ Sustained momentum building over 15 days → Position calls before IV expands (35th %ile)

Healthcare: Put volume doubled (1,200→2,400/day), price flat
→ Defensive hedging building → Watch for breakdown

[All 11 sectors...]

Overall: Tech/Healthcare showing sustained builds, Energy/Financials losing participation.
Risk-on rotation but defensive hedging suggests caution. Focus on tech with low IV.
```

**Example failing analysis:**
```
Technology looks strong
Healthcare showing mixed signals
Energy sector has declined

Overall the market is complicated
```
(No numbers, no implications, vague language)

---

## Implementation Checklist

### Day 1: Tool Registry
- [ ] Create `tools/agent_tools.py`
- [ ] Create `tools/executors/database_tools.py`
- [ ] Test tool definitions
- [ ] Test SQL safety checks
- [ ] Test query execution

### Day 2: Agentic Loop
- [ ] Create `morning_view/sector_rotation_agent.py`
- [ ] Implement agentic loop
- [ ] Test with real database
- [ ] Validate cost/iteration counts
- [ ] Review analysis quality

### Day 3: Caching & TUI
- [ ] Create cache table in analysis_cache.db
- [ ] Create `morning_view/sector_rotation_data.py`
- [ ] Create `morning_view/screens/sector_rotation.py`
- [ ] Integrate into main menu
- [ ] Test full workflow

### Day 4: Refinement
- [ ] Tune system prompts for better output
- [ ] Add error handling
- [ ] Improve logging
- [ ] Document learnings
- [ ] Prepare for Oracle rebuild

---

## Notes for Future Claude Code Sessions

**When you read this document in a future session:**

1. **All decisions are already made** - don't second-guess the architecture
2. **Ben expects this exact implementation** - follow the plan
3. **Cost targets matter** - track tokens and cost closely
4. **Safety is critical** - don't skip SQL validation
5. **This is a learning project** - Oracle rebuild depends on lessons learned here

**If something seems wrong:**
- Check this document first
- Check `docs/agentic-ai-fundamentals.md` for context
- Check `morning_view/SECTOR_ROTATION_ANALYSIS.md` for user requirements
- If still unclear, ask Ben rather than improvising

**Expected timeline:**
- Implementation: 3-4 days
- Testing & refinement: 1-2 days
- Documentation: 1 day
- Total: ~1 week for production-ready system

**Success = sector rotation agent becomes foundation for all future agentic systems in options_scanner**

---

**END OF IMPLEMENTATION PLAN**
