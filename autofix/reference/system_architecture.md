# Options Scanner System Architecture

**Updated:** February 7, 2026
**Purpose:** High-level system design for auto-fix reference

---

## System Overview

Comprehensive multi-strategy options analysis system centered around a datalake database with autonomous self-healing capabilities.

### Core Components

1. **Strategies** - Trading analysis modules (Flow Monitor, Option Pipeline, Earnings Intel)
2. **Data Layer** - SQLite databases with sector archiving
3. **AI Systems** - Oracle, AI Council, Morning View
4. **Auto-Fix** - Self-healing error detection and repair
5. **Main Orchestrator** - Daily cycle coordination

---

## Daily Workflow

### Morning Phase (6:30 AM - 9:00 AM)
```
6:30 AM - Earnings Intel: Arbitrage scanner
6:35 AM - Option Pipeline: Morning OI collection
7:20 AM - Database sync #1 (primary → query)
9:00 AM - Morning operations complete
```

### Trading Hours (9:15 AM - 4:00 PM)
```
9:15 AM - Flow Monitor daemon starts
↓
Continuous scanning loop:
  - Scan 800 symbols every 20 minutes
  - Detect unusual flow
  - Generate alerts
  - Self-monitor for errors ("no alerts in 2 hours")
↓
4:00 PM - Market close, Flow Monitor continues until 5:00 PM
```

### Evening Phase (5:00 PM - 7:00 PM)
```
5:00 PM - Option Pipeline: Evening OI operations
5:00 PM - Earnings Intel: Daily snapshot pipeline
5:30 PM - Flow Monitor: Symbol rollup
5:45 PM - Database sync #2 (primary → query)
6:00 PM - Evaluation systems run
7:00 PM - Database sync #3 (primary → query)
7:00 PM - Auto-fix batch review (if errors detected)
7:15 PM - Daily cycle complete
```

### Weekly Tasks (Sundays)
```
Earnings Intel: Weekly refresh (fetch/archive/cleanup)
Flow Monitor: Baseline updates
Database: Archive operations (if Friday)
```

---

## Strategy Modules

### Flow Monitor (`strategies/flow_monitor/`)

**Purpose:** Real-time options flow detection via continuous scanning

**Key Files:**
- `fm_main.py` - CLI entry point
- `fm_collector.py` - Data collection (API calls)
- `fm_analyzer.py` - Z-scoring and pattern analysis
- `fm_alerts.py` - Alert generation
- `fm_storage.py` - Database operations + **self-monitoring trigger**

**Self-Monitoring:**
- Location: `fm_storage.py` after storing scan results
- Check: "When was last alert generated?"
- Trigger: If >2 hours with no alerts during market hours → spawn auto-fix

**Database Tables:**
- Writes: `flow_options_scans`, `flow_alerts`, `flow_symbol_summary`
- Reads: `symbol_baselines`, `symbol_metadata`

**Strike Range:** ±20% from underlying price

### Option Pipeline (`strategies/option_pipeline/`)

**Purpose:** Open interest delta analysis and pattern detection

**Key Files:**
- `op_main.py` - CLI entry point (formerly oid_main.py)
- `op_collector.py` - OI collection
- `op_analyzer.py` - Delta correlation analysis
- `op_storage.py` - Database operations + **self-monitoring trigger**

**Self-Monitoring:**
- Location: `op_storage.py` after contract collection
- Check: "How many contracts stored?"
- Trigger: If 0 contracts stored but API succeeded → spawn auto-fix (silent failure)

**Database Tables:**
- Writes: `option_contracts`, `option_symbol_summary`
- Reads: `symbol_metadata`, `historical_prices`

**Strike Range:** ±20% from underlying price (since 2025-09-18)
**Historical Data:** Before 2025-09-18 used ±50% strike range

### Earnings Intel (`strategies/earnings_intel/`)

**Purpose:** Earnings event tracking with IV arbitrage detection

**Key Files:**
- `ei_main.py` - CLI orchestration
- `ei_snapshot_collector.py` - IV/price time series (T-7 to T+3)
- `ei_post_earnings_calc.py` - Post-earnings calculations
- `ei_arbitrage_scanner.py` - Sector sympathy opportunities

**Database Tables:**
- Writes: `earnings_events`, `earnings_snapshots`, `earnings_moves`, `earnings_sector_effects`
- Reads: `option_symbol_summary` (primary IV source), `historical_prices`, `symbol_metadata`

**Schedule:**
- Weekly refresh (Sundays): Fetch/archive/cleanup
- Daily pipeline (5 PM): Snapshots/calculations/moves
- Morning scan (6:30 AM): Arbitrage opportunities

---

## Database Architecture

### Two-Database System

**Primary Database:** `data/datalake.db`
- Production writes only
- Collection pipelines have exclusive access
- **NEVER query during collection windows** (6:30-8:00 AM, 4:30-6:00 PM)

**Query Database:** `data/datalake_query.db`
- Read-only analysis
- Synced 3x daily from primary (7:20 AM, 5:45 PM, 7:00 PM)
- Used by: Oracle, Morning View, auto-fix, all analysis tools
- **Default for auto-fix queries**

### Sector Archives (13 databases)

**Location:** `data/sector_archive/{sector}.db`

**Sector Databases:**
- Airlines (industry-specific: DAL, UAL, AAL, LUV, JBLU, ALK)
- Asset Management (industry-specific)
- Communication Services
- Consumer Discretionary
- Consumer Staples
- Energy
- Financial Services
- Healthcare
- Industrials
- Real Estate
- Technology
- Utilities
- Materials

**Archive Tiers:**
- **Tier 1 (15-day):** flow_options_scans, flow_alerts (MOVE)
- **Tier 2 (30-day):** option_contracts, option_symbol_summary, flow_symbol_summary (MOVE)
- **Tier 3 (90-day):** historical_prices, earnings_upcoming, market_daily_summary (COPY)

**Execution:** Friday nights (6:30 PM) through Monday morning (5:45 AM cutoff)

### Key Tables

**Flow Monitor:**
- `flow_options_scans` (24.5M rows) - Intraday scan snapshots
- `flow_alerts` (468 rows) - Alert tracking with profitability
- `flow_symbol_summary` (1.9K rows) - Daily symbol summaries (selective)

**Option Pipeline:**
- `option_contracts` (1.46M rows) - Daily OI snapshots
- `option_symbol_summary` (64K rows) - Symbol-level IV/OI/Greek summaries (universal)

**Reference:**
- `symbol_metadata` (740 rows) - Symbol universe, sectors, archive routing
- `historical_prices` (176K rows) - Daily OHLC data
- `market_daily_summary` (80 rows) - Market regime tracking

---

## Data Flow

```
Collection → Primary DB → Strategies → Analysis → AI Systems → User Interfaces
                ↓
           Query DB (synced 3x daily)
                ↓
     Oracle / Morning View / Auto-Fix
```

**Collection Sources:**
- Tradier API (options data, market calendar)
- Alpha Vantage (news sentiment)
- FMP / yfinance (historical prices, earnings)

**Analysis Layers:**
- Strategy-specific (Flow Monitor alerts, OI concentrations)
- Cross-strategy (Earnings Intel + Option Pipeline IV)
- AI-powered (Oracle queries, AI Council analysis)

---

## Auto-Fix Integration Points

### Error Detection

**Strategies self-monitor:**
- Flow Monitor checks: "No alerts in 2 hours?"
- Option Pipeline checks: "No contracts stored?"
- Earnings Intel checks: "IV snapshot failed?"

**Error logging (unified error queue):**
```python
# Non-critical errors (queued for end-of-day batch mode)
from tools.autofix import queue_error

queue_error(
    error_type='descriptive_error_name',
    context={'key': 'value', 'error': str(e)},
    severity='ERROR'
)

# Critical errors (immediate spawn + process exit)
from tools.autofix import handle_error

handle_error(
    error_type='descriptive_error_name',
    context={'key': 'value', 'error': str(e)},
    severity='CRITICAL',
    main_py_pid=os.getppid()
)
```

### Trigger Points

**Immediate Mode:**
- Location: Strategy code (fm_collector.py, op_main.py, ei_main.py, etc.)
- Timing: Immediately when CRITICAL error occurs
- Action: `handle_error(severity='CRITICAL')` → queues error, spawns Claude Code, exits process

**Batch Mode:**
- Location: main.py at end of daily cycle (Step 7.6)
- Timing: ~7:30 PM weekdays, ~10 PM Fridays
- Action: `check_and_spawn_batch_mode()` reads error queue, deduplicates, spawns sequential sessions

### Auto-Fix Safe Zones

**Safe to modify:**
- Strategy code in `strategies/` directories
- Analysis scripts in `tools/`
- Temporary files in `cache/`

**Protected (read-only enforced):**
- `config.json`, `credentials.json`
- `.claude/` directory
- `autofix/` system files
- Core libraries in `core/`
- `main.py` orchestrator
- All database files

---

## Common Issues and Solutions

### Duplicate Contract Errors

**Symptom:** UNIQUE constraint failed on (contract_hash, scan_timestamp/trade_date)

**Causes:**
1. Tradier API returning duplicates
2. Threading race condition
3. Batch data not deduplicated

**Solutions:**
1. Deduplicate at API response level
2. Deduplicate before ThreadPoolExecutor
3. Deduplicate before batch INSERT

**Auto-Fix Approach:**
- Add deduplication at earliest possible point
- Log duplicate occurrences for pattern detection
- Keep system running (immediate safety net)

### Silent Failures

**Symptom:** System runs but produces no output (no alerts, no contracts stored)

**Causes:**
1. Database write failures (permissions, disk space)
2. Logic errors (filtering too aggressively)
3. API changes (unexpected response format)

**Detection:**
- Flow Monitor: Count alerts generated per hour
- Option Pipeline: Count contracts stored per collection
- Compare against expected ranges

**Auto-Fix Approach:**
- Add diagnostic logging first (identify root cause)
- Fix if pattern clear, escalate if uncertain
- Don't restart until fix verified

### Database Locking

**Symptom:** OperationalError: database is locked

**Causes:**
1. Querying primary DB during collection windows
2. Archive operations in progress (Friday nights)
3. Long-running analysis queries

**Solutions:**
1. Use query DB (`datalake_query.db`) for analysis
2. Respect collection windows (6:30-8:00 AM, 4:30-6:00 PM)
3. Wait for archive operations to complete (Friday 6:30 PM - Monday 5:45 AM)

**Auto-Fix Approach:**
- Verify database path in queries (should be datalake_query.db)
- Add retry logic with backoff
- Escalate if locking persists

---

## Market Calendar Integration

**Tradier API provides:**
- Market open/close times
- Holiday schedules
- Early close dates

**Main.py coordination:**
- Checks market status before starting strategies
- Exits on holidays (is_trading_day() check at startup)
- Adjusts schedule for early closes
- Single daily cycle, launched by Task Scheduler each weekday

**Self-healing considerations:**
- Auto-fix should respect market hours
- No process restarts during active collection
- Batch review happens after market close

---

## Key File Locations

**Main Orchestrator:**
- `main.py` - Daily cycle coordinator

**Strategies:**
- `strategies/flow_monitor/` - Flow detection
- `strategies/option_pipeline/` - OI analysis
- `strategies/earnings_intel/` - Earnings intelligence

**Core Infrastructure:**
- `core/tradier_api.py` - Market data client
- `tools/timezone_utils.py` - EST/DST handling
- `tools/decimal_formatter.py` - Database decimal formatting
- `tools/error_logger.py` - Critical error logging

**Database:**
- `data/datalake.db` - Primary database
- `data/datalake_query.db` - Query database
- `data/sector_archive/{sector}.db` - Sector archives

**Auto-Fix:**
- `autofix/` - Self-healing system
- `autofix/reference/` - Static knowledge base
- `autofix/logs/` - Session journals, prompts, completion markers
- `autofix/context/` - Dynamic state (batch context files)
- `autofix/errors/` - Daily error queue JSON files

---

## Development Standards

**Decimal Precision:**
- Prices: 2 decimals
- Greeks/IV: 4 decimals
- Use `tools/decimal_formatter.py` for all DB operations

**Timezone:**
- Always use `now_eastern()` from `tools/timezone_utils.py`

**UTF-8 Encoding:**
- All logging: `encoding='utf-8'`
- Subprocess: `encoding='utf-8', errors='replace'`

**Error Handling:**
- Use `log_critical_error()` for critical errors
- Comprehensive logging at all levels
- Non-blocking error recovery where possible

---

*For database schema details, see `data/datalake_schema_2026-01-01.md`*
*For sector archive schema, see `data/sector_archive/README.md`*
