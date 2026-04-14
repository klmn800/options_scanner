# Vanna Slim - Schema-Aware Database Query Utility

**Purpose:** Lightweight Vanna wrapper for Morning View AI Council
**Source:** Extracted from `oracle/oracle_vanna.py` (1,450 lines → 200 lines)
**Location:** `morning_view/lib/schema_query/`

---

## 🎯 What Vanna Provides

### **1. Schema Awareness via RAG**

Vanna uses FAISS vector search to find relevant table schemas:

```python
# Training data: oracle/vanna_storage/complete_table_documentation.json
{
  "id": "flow_alerts_complete",
  "documentation": "Table: flow_alerts
  Description: Options flow alerts with profitability tracking

  Columns:
  - significance_score (REAL): 0-10 rating | Trading Context: >=5.0 = HIGH conviction, >=3.5 = alert threshold (v2 scoring, April 2026)
  - premium_value (REAL): Dollar value | Trading Context: >$100k = large flow
  ..."
}
```

When you ask: "Show me high-significance NVDA alerts"
- Vanna searches training docs for "significance" + "alerts"
- Finds `flow_alerts` table
- Generates SQL using relevant schema only

### **2. Domain Knowledge**

Your training data includes **trading context**, not just schema:
- "significance_score >=5.0 = HIGH conviction, >=3.5 = alert threshold (v2)"
- "VIX <20 = complacent, 20-30 = normal, >30 = fearful"
- "PREDICTIVE positioning = smart money, CHASING = retail"

This helps Vanna generate better SQL than generic LLMs.

### **3. Example Query Learning**

You can train Vanna on successful queries:

```python
vanna.train(
    question="Show me institutional NVDA flow",
    sql="SELECT * FROM flow_alerts WHERE symbol='NVDA' AND significance_score >= 5.0"
)
```

Future questions like "institutional AAPL flow" use this pattern.

---

## 📦 Slim Implementation

### **Core Code (~200 lines)**

```python
"""morning_view/lib/schema_query/vanna_query.py"""

from vanna.anthropic import Anthropic_Chat
from vanna.faiss import FAISS
import sqlite3
import json
from pathlib import Path

class SchemaQuery:
    """Lightweight Vanna wrapper for schema-aware SQL generation"""

    def __init__(self, api_key: str, training_dir: str = None):
        if training_dir is None:
            # Default to oracle/vanna_storage
            training_dir = Path(__file__).parent.parent.parent.parent / "oracle/vanna_storage"

        # Initialize Vanna with FAISS + Claude Haiku
        self.vn = FAISS(config={
            'api_key': api_key,
            'model': 'claude-3-5-haiku-20241022'
        })

        # Load training data (trading-aware schema)
        training_file = Path(training_dir) / "complete_table_documentation.json"
        if training_file.exists():
            with open(training_file) as f:
                docs = json.load(f)
                for doc in docs:
                    self.vn.train(documentation=doc['documentation'])

    def ask(self, question: str, db_path: str = "data/datalake_query.db"):
        """Generate SQL and execute query"""
        # Generate SQL using Vanna's RAG
        sql = self.vn.generate_sql(question)

        # Execute SQL
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            error = None
        except Exception as e:
            results = []
            error = str(e)
        finally:
            conn.close()

        return {
            'question': question,
            'sql': sql,
            'results': results,
            'row_count': len(results),
            'error': error
        }

    def train_example(self, question: str, sql: str):
        """Train Vanna on successful query patterns"""
        self.vn.train(question=question, sql=sql)

    def retrain_schema(self):
        """Update training data with current database schema"""
        # Implementation: Read current schema, update training data
        pass
```

### **Convenience Function**

```python
def query(question: str, api_key: str = None) -> dict:
    """One-off query without creating SchemaQuery instance"""
    if api_key is None:
        import json
        config = json.load(open("config.json"))
        api_key = config['claude_api']['api_key']

    sq = SchemaQuery(api_key)
    return sq.ask(question)
```

---

## 🔌 Integration with Morning View Advisors

### **Option 1: Pre-fetched Data + Optional Query**

```python
# In advisor_data.py

def get_advisor_data_with_db_access(symbol: str, advisor_config: dict):
    """Enhanced data gathering with optional database querying"""

    # Standard pre-fetched data (current approach)
    data = {
        'overview': get_overview(symbol),
        'oi_summary': get_oi_summary(symbol),
        'flow_alerts': get_flow_alerts(symbol),
        # ... etc
    }

    # If advisor allows DB queries, provide query function
    if advisor_config.get('allow_db_queries', False):
        from morning_view.lib.schema_query import query
        data['_query_function'] = query
        # Advisor can call: _query_function('Show me NVDA alerts last 30 days')

    return data
```

### **Advisor Prompt Update**

```json
{
  "id": 2,
  "name": "Advanced Detective",
  "allow_db_queries": true,
  "system_prompt_addition": "...

  ADVANCED CAPABILITY: Database Query Access
  You can query the database directly for data beyond your pre-fetched context.

  Use: _query_function('your natural language question')
  Returns: {sql, results, row_count, error}

  Examples:
  - _query_function('Show me all NVDA flow alerts from last 30 days where significance_score >= 5.0')
  - _query_function('Get historical prices for NVDA over last 90 days')

  Cost: ~$0.0005 per query (use sparingly, only when needed)"
}
```

### **Option 2: SQL Generation Only (No Execution)**

For advisors that need SQL but you want to review before executing:

```python
def generate_sql_only(question: str) -> str:
    """Generate SQL without executing (safer)"""
    sq = SchemaQuery(api_key)
    return sq.vn.generate_sql(question)
```

---

## 💰 Cost Analysis

### **Per Query Cost:**

| Component | Model | Tokens | Cost |
|-----------|-------|--------|------|
| Schema retrieval | FAISS | 0 | $0 (local) |
| SQL generation | Haiku | ~500 | $0.0005 |
| Execution | - | 0 | $0 |
| **TOTAL** | | | **$0.0005** |

Compare to full Oracle system:
- SQL gen (Haiku): $0.0007
- Analysis (Sonnet): $0.017
- **Total:** $0.0177

**Vanna Slim is 35x cheaper** because it skips analysis step.

### **Advisor Usage Estimate:**

Assume Advanced Detective uses DB queries for 20% of analyses:
- 10 symbols analyzed/week
- 2 use DB queries (20%)
- 2 queries × $0.0005 = **$0.001/week additional cost**

**Negligible cost impact.**

---

## 🔄 Updating Training Data

### **When to Update:**

1. After database schema changes (Oct 16 migration = UPDATE NEEDED)
2. When adding new tables
3. When query accuracy drops

### **How to Update:**

```python
# Manual approach: Edit complete_table_documentation.json
{
  "id": "flow_symbol_summary_complete",
  "documentation": "Table: flow_symbol_summary
  Description: Daily alert-focused metrics for Flow Monitor

  Columns:
  - alert_count_5d (INTEGER): Rolling 5-day alert count | Trading Context: >10 = hot symbol
  ..."
}

# Automated approach (future enhancement):
def auto_generate_training_data():
    """Read schema from datalake_schema.md, format for Vanna"""
    # Read markdown schema
    # Parse into Vanna documentation format
    # Update complete_table_documentation.json
    pass
```

### **Retraining Process:**

```python
sq = SchemaQuery(api_key)
sq.retrain_schema()  # Clear old training, load new data
```

---

## 📊 Vanna vs. Direct Claude Prompting

### **Why use Vanna instead of just sending schema to Claude?**

| Approach | Schema Size | Cost | Accuracy |
|----------|-------------|------|----------|
| **Vanna RAG** | Relevant tables only (~2KB) | $0.0005 | High (focused) |
| **Full schema** | All 20+ tables (~50KB) | $0.002 | Medium (distracted) |
| **No schema** | 0 | $0.0003 | Low (hallucination) |

**Vanna wins when:**
- ✅ Database is large (20+ tables) - focuses on relevant subset
- ✅ Schema includes domain knowledge (your trading context)
- ✅ You want to learn from successful queries over time

**Direct prompting wins when:**
- ✅ Database is small (<5 tables) - just send entire schema
- ✅ One-off queries (no learning needed)
- ✅ Simplicity over optimization

**For your 20+ table database with trading context, Vanna is the right choice.**

---

## 🧪 Testing Vanna Accuracy

### **Test Suite:**

```python
# tests/test_vanna_accuracy.py

test_cases = [
    {
        'question': 'Show me high-significance NVDA alerts',
        'expected_sql_contains': ['flow_alerts', 'NVDA', 'significance_score'],
        'expected_sql_not_contains': ['option_contracts', 'earnings']
    },
    {
        'question': 'Get NVDA option contracts expiring in 30 days',
        'expected_sql_contains': ['option_contracts', 'NVDA', 'expiration_date'],
        'min_columns': ['strike', 'option_type', 'open_interest']
    },
    # ... more test cases
]

def test_accuracy():
    sq = SchemaQuery(api_key)
    passed = 0

    for test in test_cases:
        result = sq.ask(test['question'])
        sql = result['sql'].lower()

        # Check SQL contains expected elements
        if all(term in sql for term in test['expected_sql_contains']):
            passed += 1

    accuracy = passed / len(test_cases)
    print(f"Accuracy: {accuracy:.1%}")

    return accuracy >= 0.80  # 80% threshold
```

**Run before deployment:**
```bash
python tests/test_vanna_accuracy.py
```

If accuracy <80%, consider:
1. Updating training data with better examples
2. Adding more domain context to schema docs
3. Training on successful query examples

---

## 🚀 Future Enhancements

### **1. Query Result Caching**

Cache frequent queries to avoid redundant API calls:

```python
# Cache: "Show me NVDA alerts" → SQL + results for 1 hour
cache = {
    'query_hash': {
        'sql': '...',
        'results': [...],
        'timestamp': '...'
    }
}
```

### **2. Query Pattern Learning**

Automatically learn from successful advisor queries:

```python
def log_successful_query(question: str, sql: str):
    """Train Vanna on queries that advisors use successfully"""
    sq.train_example(question, sql)

# After advisor uses DB query successfully, log it
```

### **3. Multi-Step Query Planning**

For complex questions, break into sub-queries:

```python
question = "Compare NVDA and AAPL flow alerts this week"

# Step 1: Get NVDA alerts
# Step 2: Get AAPL alerts
# Step 3: Compare results

# Vanna generates SQL for each step
```

### **4. Automated Schema Sync**

Keep training data in sync with database automatically:

```python
# Cron job: daily at 7 AM
python morning_view/lib/schema_query/update_training.py

# Reads: data/datalake_schema.md
# Writes: oracle/vanna_storage/complete_table_documentation.json
# Retrains: Vanna instance
```

---

## 📚 References

- **Vanna Documentation:** https://vanna.ai/docs/
- **Original Oracle Implementation:** `oracle/oracle_vanna.py` (archived)
- **Training Data:** `oracle/vanna_storage/complete_table_documentation.json`
- **Schema Source:** `data/datalake_schema_2025-10-16.md`

---

## ✅ Quick Start Checklist

- [ ] Copy slimmed Vanna code to `morning_view/lib/schema_query/vanna_query.py`
- [ ] Update training data with Oct 16+ schema changes
- [ ] Test accuracy with sample queries
- [ ] Enable for one advisor (Advanced Detective)
- [ ] Monitor costs and accuracy
- [ ] Expand to other advisors if successful
- [ ] Train on successful query patterns over time

---

**Questions? See full consolidation proposal:** `docs/AI_SYSTEMS_CONSOLIDATION_PROPOSAL.md`
