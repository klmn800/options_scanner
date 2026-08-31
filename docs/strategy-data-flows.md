# Strategy Data Flows

**Purpose:** Document the data collection architecture, table ownership, and relationships between Flow Monitor and Option Pipeline strategies.

**Last Updated:** 2025-10-22

---

## Core Architecture Principle

Both strategies operate **independently** and collect data **directly from Tradier API**. They do not read from each other's tables.

## Strategy Comparison

| Aspect | Flow Monitor | Option Pipeline |
|--------|--------------|-----------------|
| **Purpose** | Intraday flow detection | Daily OI/IV baseline snapshots |
| **Collection Source** | Tradier API (fresh quotes) | Tradier API (end-of-day) |
| **Frequency** | Every ~20 minutes | Twice daily (morning + evening) |
| **Runs During** | Market hours (9:30 AM - 4:00 PM) | Pre-market (6:35 AM) + Post-market (5:00 PM) |
| **Records Per Day** | ~10 scans per contract | 1 snapshot per contract |
| **Strike Range** | ±20% (ITM to OTM) | ±20% (ITM to OTM) |
| **DTE Range** | 7-60 days | 0-56 days |

## Data Flow Diagrams

### Flow Monitor Pipeline

```
[Tradier API]
     ↓
[Fresh Intraday Quotes]
     ↓
[fm_collector.py] ← Collects option chains + underlying prices
     ↓
[fm_storage.py] → Writes to flow_options_scans (raw contract data)
     ↓
[fm_analyzer.py] ← Reads flow_options_scans for THIS scan
     ↓              Runs unified algorithm (premium + volume surprise, v2 since 2026-04)
     ↓
[fm_storage.py] → Writes to flow_alerts (significant flows only)
     ↓
[fm_symbol_rollup.py] ← Aggregates alerts by symbol (end of day)
     ↓
[fm_storage.py] → Writes to flow_symbol_summary (daily metrics)
```

**Tables Written:**
- `flow_options_scans` - Every contract scanned (~95K rows per scan)
- `flow_alerts` - Only significant institutional flows detected
- `flow_symbol_summary` - Daily alert-focused metrics (50-100 symbols with alerts)

**Tables Read:**
- `flow_options_scans` - Reads contracts from current scan_timestamp only
- `flow_alerts` - Historical alerts for profitability tracking

### Option Pipeline

```
[Tradier API]
     ↓
[End-of-Day Snapshots]
     ↓
[op_collector.py] ← Collects option chains + underlying prices
     ↓
[op_storage.py] → Writes to option_contracts (with time series calculations)
     ↓              Calculates OI changes, IV momentum, Greek deltas
     ↓
[op_symbol_rollup.py] ← Aggregates contracts by symbol
     ↓
[op_storage.py] → Writes to option_symbol_summary (symbol-level metrics)
```

**Tables Written:**
- `option_contracts` - All contracts tracked (1.2M+ rows, 66 columns)
- `option_symbol_summary` - Universal symbol-level daily metrics (800 symbols, 93 columns)

**Tables Read:**
- `option_contracts` - Historical rows for time series calculations (OI momentum, IV changes)

## Table Ownership Matrix

| Table | Writer | Primary Readers | Update Frequency | Purpose |
|-------|--------|-----------------|------------------|---------|
| **flow_options_scans** | Flow Monitor | Flow Monitor analyzer | ~20min during market | Raw intraday contract snapshots |
| **flow_alerts** | Flow Monitor | Analysis tools | ~20min during market | Significant institutional flows |
| **flow_symbol_summary** | Flow Monitor | Analysis tools | 1x per trade_date (EOD) | Daily alert metrics by symbol |
| **option_contracts** | Option Pipeline | Option Pipeline (time series), Earnings Intel, Analysis | 1x per trade_date | Daily OI/IV/Greek baseline |
| **option_symbol_summary** | Option Pipeline | Earnings Intel, Analysis | 1x per trade_date | Symbol-level OI/IV aggregations |

## Key Differences Explained

### Collection Timing
- **Flow Monitor:** Runs continuously during market hours to catch intraday price/volume changes
  - Example: If NVDA has unusual call buying at 2:30 PM, Flow Monitor detects it in real-time
- **Option Pipeline:** Runs twice daily to create stable baseline snapshots
  - Morning (6:35 AM): Capture opening interest
  - Evening (5:00 PM): Capture closing interest

### Data Granularity
- **Flow Monitor:** Many records per contract per day (~10 scans)
  - Tracks how bid/ask/volume/OI change throughout the trading session
  - Each scan_timestamp creates a full snapshot
- **Option Pipeline:** One record per contract per trade_date
  - Single "truth" for what the contract looked like at day's end
  - Time series built across multiple trade_dates, not within a single day

### Strike Range Alignment
Both strategies use **±20% strike ranges** for consistency:
- Example: Stock at $100 → collects strikes from $80 to $120
- Historical note: Option Pipeline used ±50% before 2025-09-18

### Use Cases
- **Flow Monitor:** "What unusual activity is happening RIGHT NOW?"
  - Real-time alerts for traders
  - Intraday pattern detection
- **Option Pipeline:** "How has this contract's OI evolved over time?"
  - Multi-day momentum analysis
  - IV percentile calculations
  - Baseline data for other strategies

## Cross-Strategy Dependencies

**None for data collection** - both fetch independently from Tradier.

**Indirect relationships:**
- **Earnings Intel** reads from `option_symbol_summary` (Option Pipeline) for IV metrics
- **Analysis tools** may join data from both strategies for multi-dimensional views

## Why Separate Tables?

1. **Different Update Patterns:** Flow Monitor updates same contracts ~10x per day; Option Pipeline updates once
2. **Different Retention:** Flow Monitor data is ephemeral (7-30 days); Option Pipeline is long-term (365+ days)
3. **Different Query Patterns:** Flow Monitor needs fast recent scans; Option Pipeline needs efficient time series
4. **Database Locking:** Prevents write conflicts during simultaneous collection
5. **Data Integrity:** Each strategy owns its schema and can evolve independently

## Common Confusion Points

### "Why doesn't Flow Monitor just read option_contracts?"
- **Timing mismatch:** option_contracts has end-of-day data, Flow Monitor needs current prices
- **Frequency mismatch:** option_contracts updates 2x/day, Flow Monitor runs every 20 min
- **Different metrics:** Flow Monitor needs fresh bid/ask/volume, not historical OI momentum

### "Why collect the same contracts twice?"
- **Different purposes:** One for intraday alerts, one for multi-day trends
- **Different transformations:** Flow Monitor computes smart money scores; Option Pipeline computes OI momentum
- **API efficiency:** Collecting once per strategy is simpler than complex data sharing logic

### "Can I analyze them together?"
- **Yes!** They're complementary:
  - Use Flow Monitor to find interesting symbols today
  - Use Option Pipeline to see historical context for those symbols
  - Example: "NVDA had unusual call buying today (Flow Monitor) + OI has been building for 5 days (Option Pipeline)"

---

## Summary

- **Both strategies collect independently from Tradier API**
- **No table sharing between strategies during collection**
- **Flow Monitor = Real-time intraday monitoring**
- **Option Pipeline = Daily baseline snapshots for time series**
- **Complementary, not redundant**
