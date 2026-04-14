# Sector Rotation Analysis - Design Guidelines

**Purpose**: Agentic AI analysis to identify where money is moving in the market by analyzing sector-level volume, option activity, and price trends.

**Status**: Design phase - implementation pending

**Related Documentation**: See `AGENTIC_FRAMEWORK.md` (future) for technical implementation details

---

## Core Objective

Detect sector rotation patterns BEFORE IV spikes by analyzing:
1. **Stock volume trends** - Primary indicator of capital flow
2. **Option activity** - Secondary indicator of positioning
3. **Price momentum** - Context for direction
4. **IV percentile** - Opportunity sizing (low IV = room to expand)

**Goal**: Give trader actionable intelligence like:
- "Technology stock volume building +45% over 10 days, option volume +65%, IV still at 35th percentile → Get positioned now before premium inflation"
- "Energy sector volume declining -30% over 2 weeks, option activity dried up → Avoid new trades here"

---

## Analysis Architecture

### **Round 1: Headline Analysis**
- **Trigger**: User presses SPACE on sector rotation screen
- **Output**: One actionable sentence per sector (all 11 sectors)
- **Cost**: ~$0.003-0.005
- **Cache**: 1 day (regenerate when trade_date changes)

**Example Output:**
```
Technology: Stock volume +45% over 10d, option volume +65% → Activity building before IV spike (35th percentile)
Healthcare: Put buying doubled this week (1,200→2,400 contracts/day), price flat → Hedging activity, watch for breakdown
Energy: Volume declining -30% over 2wks, XLE up 2.1% but XOM (largest holding) down 0.5% → Sector strength artificial
Financials: No notable volume changes, 45M/day avg stable → Skip this sector
...
```

### **Round 2: Market Deep Dive**
- **Trigger**: User presses M
- **Output**: Cross-sector flow analysis with actionable implications
- **Cost**: ~$0.008-0.012
- **Focus**: Where money is MOVING (not just price direction)

**Example Output:**
```
Cross-Sector Capital Flows (5-day window):
• Money exodus from Financials (-$2.1B net volume) into Technology (+$1.8B)
• Defensive positioning building: Healthcare/Utilities put/call ratio rising to 1.8 (vs 1.2 avg)
• Energy showing price strength (+2%) but volume weakness (-15%) → Unsustainable move

Implications:
• Tech IV likely to compress as volume normalizes → Avoid buying tech calls now
• Healthcare put premiums inflating → Consider selling puts for income
• Energy calls overpriced relative to volume → Wait for pullback
```

### **Round 3: Sector/Industry/Archive Drill-Down**
- **Trigger**: User selects specific grouping
- **Three levels**:
  - **Sector** (11 choices): Technology, Healthcare, Energy, etc.
  - **Industry** (~40-50 choices): Semiconductors, Airlines, Banks, etc.
  - **Archive DB** (13 choices): airlines, asset_management, etc. (curated research groups)
- **Output**: Symbol-level breakdown within chosen group
- **Cost**: ~$0.010-0.015

**Example Output (Technology Sector):**
```
Technology Sector Breakdown:

Industry Performance:
• Semiconductors (NVDA, AMD, INTC): Heavy call volume +180% at +10% strikes, IV at 40th percentile → Bullish positioning with room for expansion
• Software (MSFT, ORCL): Muted activity, volume -20% vs avg, IV at 15th percentile → Dead zone, skip
• Hardware (AAPL): Unusual put buying +95% at -5% strikes, stock volume flat → Defensive positioning or hedge

Opportunity: Semiconductors show sustained momentum building (not a spike), enter before IV expands
Risk: Software sector looks stagnant, avoid new positions
```

---

## Data Sources

### **Primary Tables**
1. **`market_daily_summary`**: Sector ETF prices (XLF, XLE, XLK, XLV, XLI, XLP, XLY, XLU, XLB, XLRE)
2. **`historical_prices`**: Individual stock OHLC + volume (800 symbols in KLMN universe)
3. **`option_symbol_summary`**: Daily option volume, OI, IV percentile by symbol
4. **`symbol_metadata`**: Symbol mappings (sector, industry, archive_db)

### **Symbol Groupings**
- **Sector**: 11 broad categories (Technology, Healthcare, Energy, etc.)
- **Industry**: Granular subcategories (~40-50 unique industries)
- **Archive DB**: 13 curated research groups (airlines, asset_management, basic_materials, communication_services, consumer_cyclical, consumer_defensive, energy, financial_services, healthcare, industrials, real_estate, technology, utilities)

**Note**: `archive_db` refers to symbol groupings, not querying actual archive databases. Filters symbols via `WHERE symbol_metadata.archive_db = 'airlines'`.

---

## Historical Context (Critical for Early Detection)

AI receives **time-series data** to detect momentum building BEFORE spikes:

**Timeframes Provided:**
- 5-day: Recent momentum
- 10-day: Short-term pattern
- 20-day: Broader context
- 60-day baseline: Is current activity abnormal?

**Detection Examples:**
- "Technology volume building slowly over 15 days (+8%, +12%, +18%) → Sustained institutional accumulation"
- "Energy volume spiked 200% yesterday after 2 weeks decline → News-driven, not sustainable"

**Default lookback**: 5 days (AI can adjust 5-30 days based on what it discovers)

---

## Output Language Principles

### ❌ **Avoid Jargon Without Context**
- "IV compression across mega-caps" - What does this mean?
- "Defensive rotation building" - Am I supposed to know what that is?
- "Risk-on rotation favoring growth sectors" - Too vague

### ✅ **Use Clear + Actionable Language**
- Specific numbers (percentages, volume counts, dollar amounts)
- Comparisons (vs historical average, vs last week)
- Direct implications (what to do, what to avoid)
- Explicit reasoning (why this matters for option pricing)

**Good Examples:**
```
✅ "Stock volume +45% over 10 days → Building momentum, not a spike"
✅ "Put volume doubled (1,200 → 2,400/day) while price flat → Hedging activity"
✅ "XLE up 2.1% but XOM (largest holding) down 0.5% → Sector strength artificial"
✅ "IV at 35th percentile with volume surging → Room for premium expansion, enter now"
```

---

## Caching Strategy

**Database**: `data/analysis_cache.db`
**Table**: `sector_ai_rotation`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS sector_ai_rotation (
    trade_date TEXT PRIMARY KEY,
    headline_analysis TEXT NOT NULL,      -- Round 1: One-liners for all 11 sectors
    market_deep_dive TEXT,                -- Round 2: Cross-sector flows (lazy-loaded)
    sector_drilldowns TEXT,               -- JSON: {"Technology": "...", "Healthcare": "..."}
    industry_drilldowns TEXT,             -- JSON: {"Semiconductors": "...", "Airlines": "..."}
    archive_drilldowns TEXT,              -- JSON: {"airlines": "...", "technology": "..."}
    data_snapshot TEXT NOT NULL,          -- JSON: Raw metrics for reproducibility
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**Cache Policy:**
- **Headline**: Cached for 1 day, regenerate when trade_date changes
- **Deep dives**: Cached indefinitely, lazy-loaded on demand
- **No invalidation**: Historical analyses preserved for comparison

**AI Context**: Agent receives previous analysis from same trade_date (if re-running) or prior trade_date for sanity check/comparison.

---

## TUI Workflow

```
[Sector Rotation Screen]
  ├─ [SPACE] → Generate Headline Analysis (all 11 sectors)
  ├─ [M] → Market Deep Dive (cross-sector flows)
  ├─ [S] → Select Sector → Sector-level drill-down
  ├─ [I] → Select Industry → Industry-level drill-down
  ├─ [A] → Select Archive Group → Archive group drill-down
  └─ [ESC] → Back to main menu
```

**Initial State**: Empty screen with instructions to press SPACE
**After Analysis**: Display results with cost/token info at bottom
**Drill-downs**: Selectable list (not free-text input) for exact matching

---

## Agentic Implementation

This analysis uses **Anthropic's tool calling API** to enable agentic behavior:
- AI decides what SQL queries to run
- AI chooses lookback periods dynamically
- AI determines statistical significance thresholds
- AI iterates on queries until sufficient data gathered

See `AGENTIC_FRAMEWORK.md` for technical implementation details, cost controls, and safety guardrails.

**Estimated Costs:**
- Headline: $0.003-0.005 per analysis
- Market deep dive: $0.008-0.012 per analysis
- Sector drill-down: $0.010-0.015 per analysis

---

## Quality Validation

**Required Elements (all 11 sectors):**
- Technology, Healthcare, Energy, Financials, Industrials, Consumer Cyclical, Consumer Defensive, Utilities, Real Estate, Basic Materials, Communication Services

**Content Requirements:**
- ✅ Specific numbers (percentages, counts, dollar amounts)
- ✅ Comparisons (vs avg, vs last week, vs historical)
- ✅ Actionable implications (what to do)
- ❌ No vague jargon without explanation
- ❌ No generic statements ("sector looks good")

**Validation Example:**
```python
# Must contain all 11 sectors
# Must have numbers: \d+%|\d+M|\d+\.\d+
# Must have implications: "→" or "Implication:" markers
```

---

## Future Enhancements (Not Implemented)

- [ ] Correlation analysis between sectors
- [ ] Sector rotation cycle detection (12-18 month patterns)
- [ ] Unusual institutional flow alerts (13F data integration)
- [ ] Industry-level peer comparison within sectors
- [ ] Export analysis to trading journal

---

**Author**: Ben
**Date**: 2025-10-29
**Status**: Design complete, awaiting implementation
