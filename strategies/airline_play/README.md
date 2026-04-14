# Airline Play Tracking System

**Status:** ✅ Production Ready (Development-Ready)
**Version:** 1.0
**Created:** 2025-10-01
**PRD:** tasks/0001-prd-airline-tracking-system.md

---

## Overview

The Airline Play tracking system isolates and analyzes 7 airline stocks from the larger KLMN 800 universe, providing focused data for pattern recognition and trading strategy development. The system tracks both symbol-level metrics and filtered options contracts with tiered strike ranges.

### Tracked Airlines

**Primary (±10% Strike Range):**
- **DAL** - Delta Air Lines
- **UAL** - United Airlines
- **AAL** - American Airlines

**Secondary (±5% Strike Range):**
- **LUV** - Southwest Airlines
- **JBLU** - JetBlue Airways
- **ALK** - Alaska Air Group

**ETF:**
- **JETS** - U.S. Global Jets ETF

### Key Features

- **Symbol-level tracking:** Daily aggregation from 6 data sources (prices, OI, IV, earnings, news, alerts)
- **Options filtering:** Contract-level data with tiered strike ranges and ≤60 DTE
- **Historical backfill:** Complete data from 2025-08-08 onwards
- **Pipeline integration:** Runs as Step 3.6 in evening sequence (after earnings, before daily_analysis)
- **Performance:** 11.7 seconds total (well under 5-minute target)

---

## Architecture

### Database Schema

**Two tracking tables:**

#### 1. airline_symbol_tracking
- **Purpose:** Daily symbol-level metrics
- **Primary Key:** (symbol, trade_date)
- **Rows:** 254 (38 dates × 6-7 symbols)
- **Data Sources:** historical_prices, oi_symbol_summary, options_symbol_summary, earnings_upcoming, news_symbol_sentiment, flow_alerts

#### 2. airline_options_tracking
- **Purpose:** Filtered options contracts
- **Primary Key:** (contract_hash, trade_date)
- **Rows:** 9,426 (37 trading days)
- **Data Source:** oi_daily (with strike/DTE filters)
- **Filters Applied:**
  - Primary airlines: ±10% strike range
  - Secondary airlines: ±5% strike range
  - All: ≤60 days to expiration

---

## How It Works

### Daily Data Flow

```
1. OID Evening Pipeline → oi_daily, oi_symbol_summary populated
2. Historical Prices → historical_prices updated
3. Earnings Pipeline → earnings_upcoming refreshed
4. ✈️ AIRLINE PLAY PHASE (Step 3.6)
   ├─ Symbol Tracking: Extract from 6 sources → airline_symbol_tracking
   └─ Options Tracking: Filter oi_daily → airline_options_tracking
5. Daily Analysis → Continues with full dataset
```

### Symbol-Level Extraction (ap_symbol_tracking.py)

**Process:**
1. Get airline symbols from `symbols_klmn800.py` (AIRLINE_PLAY_SYMBOLS)
2. Extract data from each source table:
   - **historical_prices:** close_price, volume, price_change_percent
   - **oi_symbol_summary:** OI totals, put/call ratios, time distributions
   - **options_symbol_summary:** IV metrics by DTE bucket
   - **earnings_upcoming:** days_to_earnings calculation
   - **news_symbol_sentiment:** sentiment scores and article counts
   - **flow_alerts:** active alert counts
3. Aggregate into single row per symbol/date
4. Apply decimal formatting (`clean_database_row()`)
5. INSERT with ON CONFLICT → UPDATE

**Command-line usage:**
```bash
# Track all airlines for yesterday
python ap_symbol_tracking.py

# Track specific symbol for specific date
python ap_symbol_tracking.py --symbol DAL --date 2025-10-01
```

---

### Options-Level Filtering (ap_options_tracking.py)

**Process:**
1. Get current underlying price (oi_daily → fallback to historical_prices)
2. Calculate strike range based on symbol:
   - Primary (DAL/UAL/AAL): `price * 0.90` to `price * 1.10`
   - Secondary (LUV/JBLU/ALK/JETS): `price * 0.95` to `price * 1.05`
3. Query oi_daily with filters:
   - Symbol match
   - Strike BETWEEN lower_strike AND upper_strike
   - Days to expiration ≤ 60
   - Trade date match
4. Add earnings proximity context
5. Batch insert into airline_options_tracking

**Strike Range Examples:**
```
DAL @ $56.11  →  $50.50 - $61.72 (±10%)
LUV @ $32.28  →  $30.67 - $33.89 (±5%)
JETS @ $24.53 →  $23.30 - $25.76 (±5%)
```

**Command-line usage:**
```bash
# Track all airlines for yesterday
python ap_options_tracking.py

# Track specific symbol with debug logging
python ap_options_tracking.py --symbol DAL --date 2025-10-01 --debug
```

---

### Historical Backfill (ap_backfill.py)

**Purpose:** Load historical data from 2025-08-08 through yesterday

**Process:**
1. Generate date range (2025-08-08 to yesterday by default)
2. For each date:
   - Run ap_symbol_tracking.py
   - Run ap_options_tracking.py
   - Log gaps and errors
3. Provide comprehensive summary statistics

**Command-line usage:**
```bash
# Default: backfill from 2025-08-08 to yesterday
python ap_backfill.py

# Custom date range
python ap_backfill.py --start-date 2025-09-01 --end-date 2025-09-15

# Dry run (preview without executing)
python ap_backfill.py --dry-run
```

**Backfill Results (2025-08-08 to 2025-09-30):**
- 254 symbol-day records
- 9,426 option contracts
- 37 trading days processed
- Gaps detected: JETS (limited historical_prices), JBLU (missing oi_symbol_summary early Sept)

---

## Pipeline Integration

### Main Orchestration (main.py)

**Step 3.6 - Airline Play Phase:**
```python
def run_airline_play_phase(self):
    """Run airline tracking extraction phase"""
    # Beautiful logging with status box
    self.create_status_box("🛫 AIRLINE PLAY TRACKING PHASE", [...])

    # Import modules
    from strategies.airline_play import ap_symbol_tracking, ap_options_tracking

    # Run both phases
    symbol_result = ap_symbol_tracking.run_symbol_tracking(trade_date)
    options_result = ap_options_tracking.run_options_tracking(trade_date)

    # Report results
    self.beautiful_log(f"Symbols: {symbol_result['symbols_processed']}")
    self.beautiful_log(f"Contracts: {options_result['total_contracts_tracked']}")
```

**Command-line flags:**
```bash
# Run airline play phase only
python main.py --airline-play

# Run full evening sequence (includes airline play as Step 3.6)
python main.py --oid-evening
```

**Evening Sequence Order:**
1. OID Operations
2. Historical Prices Collection
3. Earnings Alert Pipeline
4. **→ Airline Play Tracking (Step 3.6)**
5. Daily Analysis

---

## Data Quality

### Known Limitations

See `DATA_QUALITY_FINDINGS.md` for detailed documentation.

**Upstream Issues (not airline_play bugs):**
- `symbol_exp_type_hash` is NULL in oi_daily (affects grouping)
- `days_to_expiration` calculating as 0 in oi_daily (workaround implemented)
- `oi_balance_text` is NULL in oi_symbol_summary
- OI change metrics (oi_change_1d, 5d, 10d) partially NULL

**Symbol-Specific Gaps:**
- **JETS:** Limited oi_symbol_summary coverage (not tracked in OID system)
- **JBLU:** Missing oi_symbol_summary for early September dates

**Workarounds Implemented:**
```sql
-- DTE calculation with fallback
COALESCE(days_to_expiration,
         CAST(julianday(expiration_date) - julianday(trade_date) AS INTEGER)) as days_to_expiration

-- Underlying price with fallback
SELECT underlying_price FROM oi_daily  -- Try first
UNION
SELECT close_price FROM historical_prices  -- Fallback
```

### Data Completeness

**Symbol Tracking (airline_symbol_tracking):**
- ✅ Price/volume data: 100% complete (historical_prices)
- ✅ Earnings proximity: 100% complete (earnings_upcoming)
- ✅ News sentiment: Complete when articles available
- ⚠️ OI metrics: JETS has NULL values (not in OID universe)
- ⚠️ oi_balance_text: NULL for all (upstream bug)

**Options Tracking (airline_options_tracking):**
- ✅ Strike filtering: Working correctly (validated)
- ✅ DTE filtering: Working correctly (SQL workaround)
- ⚠️ OI momentum: Partial (some contracts have oi_change_Xd, others NULL)
- ⚠️ symbol_exp_type_hash: NULL for all (upstream bug)

---

## Expansion Roadmap

### Phase 1: Foundation (✅ COMPLETE)
- [x] Database schema with indexes
- [x] Symbol universe configuration
- [x] Symbol-level tracking from 6 sources
- [x] Options-level tracking with tiered strike ranges
- [x] Historical backfill utility
- [x] Main pipeline integration
- [x] Comprehensive testing

### Phase 2: Pattern Analysis (🔄 Next)
**Goal:** Identify airline industry movement patterns

**Planned Features:**
- **Correlation Analysis:**
  - Calculate daily correlation between airline symbols
  - Identify "lock-step" days (all move together)
  - Detect divergence patterns (one breaks from pack)

- **Earnings Analysis:**
  - Track historical earnings moves for each airline
  - Compare expected vs actual moves
  - IV crush analysis post-earnings

- **Options Flow Patterns:**
  - Identify unusual OI building in airline sector
  - Cross-symbol flow alerts (institutional sector bets)
  - Time-to-event analysis (earnings proximity effects)

**Implementation Approach:**
```sql
-- Example: Daily correlation calculation
SELECT
    a1.symbol as symbol1,
    a2.symbol as symbol2,
    CORR(a1.price_change_percent, a2.price_change_percent) OVER (
        ORDER BY a1.trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
    ) as rolling_20day_correlation
FROM airline_symbol_tracking a1
JOIN airline_symbol_tracking a2 ON a1.trade_date = a2.trade_date
WHERE a1.symbol < a2.symbol;  -- Avoid duplicates
```

### Phase 3: Trading Signals (🔮 Future)
**Goal:** Generate actionable trading opportunities

**Planned Features:**
- **Spread Strategies:**
  - Identify airline pairs with historically high correlation
  - Alert when correlation breaks (spread trade setup)
  - Track spread performance vs historical norms

- **Sector Momentum:**
  - Detect when entire airline sector shifts direction
  - OI-based confirmation signals
  - News sentiment alignment checks

- **Earnings Plays:**
  - Flag airlines with IV below historical pre-earnings levels
  - Compare current option pricing vs past earnings cycles
  - Identify asymmetric risk/reward setups

### Phase 4: Integration & Automation (🔮 Future)
**Goal:** Seamless integration with broader trading system

**Planned Features:**
- **Daily Analysis Integration:**
  - Airline-specific insights in daily_analysis_symbol_curated
  - Sector-wide analysis in daily_analysis_market_curated
  - Claude AI analysis of airline patterns

- **Chrome Extension Display:**
  - Airline sector summary overlay
  - Cross-symbol correlation indicators
  - Sector momentum visualization

- **Alert System:**
  - Email/SMS notifications for key airline patterns
  - Correlation breakdowns
  - Unusual sector-wide OI building

---

## Usage Examples

### Query Airline Data

```sql
-- Get latest airline metrics
SELECT symbol, close_price, put_call_ratio, iv_front_month, earnings_days_ahead
FROM airline_symbol_tracking
WHERE trade_date = '2025-10-01'
ORDER BY symbol;

-- Find contracts near earnings
SELECT symbol, strike, option_type, days_to_expiration, days_to_earnings, open_interest
FROM airline_options_tracking
WHERE trade_date = '2025-10-01'
  AND days_to_earnings IS NOT NULL
  AND days_to_earnings <= 10
ORDER BY symbol, days_to_earnings, open_interest DESC;

-- Compare airline price movements
SELECT
    symbol,
    price_change_percent,
    volume / LAG(volume, 1) OVER (PARTITION BY symbol ORDER BY trade_date) as volume_ratio
FROM airline_symbol_tracking
WHERE trade_date BETWEEN '2025-09-26' AND '2025-10-01'
ORDER BY trade_date, symbol;
```

### Programmatic Access

```python
from strategies.airline_play import ap_symbol_tracking, ap_options_tracking

# Run symbol tracking for specific date
result = ap_symbol_tracking.run_symbol_tracking(
    trade_date='2025-10-01',
    symbols=['DAL', 'UAL']  # Optional: specific symbols
)
print(f"Processed {result['symbols_processed']} symbols")

# Run options tracking
result = ap_options_tracking.run_options_tracking(
    trade_date='2025-10-01',
    symbols=['DAL']  # Optional: single symbol
)
print(f"Tracked {result['total_contracts_tracked']} contracts")
```

---

## Troubleshooting

### Common Issues

**1. "No historical_prices data for [symbol]"**
```bash
# Solution: Backfill historical prices
cd data
python fmp_historical_backfill.py --symbols JETS --backfill-2021 --no-interaction
```

**2. "No underlying price found"**
- Indicates missing data in both oi_daily AND historical_prices
- Check if symbol has recent price data
- Verify symbol is in KLMN 800 universe

**3. "No contracts found in range"**
- Normal for low-liquidity symbols
- Verify strike range calculation is correct:
  ```python
  # Primary: ±10%
  lower = price * 0.90
  upper = price * 1.10

  # Secondary: ±5%
  lower = price * 0.95
  upper = price * 1.05
  ```

**4. Days to expiration showing 0**
- Known upstream oi_daily bug
- Workaround implemented in SQL (COALESCE with calculated value)
- If still seeing 0, check that expiration_date > trade_date

### Validation Queries

```sql
-- Check data freshness
SELECT MAX(trade_date) as latest_symbol_date FROM airline_symbol_tracking;
SELECT MAX(trade_date) as latest_options_date FROM airline_options_tracking;

-- Verify strike ranges
SELECT
    symbol,
    underlying_price,
    MIN(strike) as min_strike,
    MAX(strike) as max_strike,
    ROUND((MAX(strike) - underlying_price) / underlying_price * 100, 1) as upper_pct,
    ROUND((underlying_price - MIN(strike)) / underlying_price * 100, 1) as lower_pct
FROM airline_options_tracking
WHERE trade_date = '2025-10-01'
GROUP BY symbol, underlying_price;

-- Check for gaps
SELECT
    s.symbol,
    s.trade_date,
    CASE
        WHEN a.symbol IS NULL THEN 'Missing in airline_symbol_tracking'
        ELSE 'Present'
    END as status
FROM (SELECT DISTINCT symbol, trade_date FROM historical_prices
      WHERE symbol IN ('DAL','UAL','AAL','LUV','JBLU','ALK','JETS')
        AND trade_date >= '2025-08-08') s
LEFT JOIN airline_symbol_tracking a ON s.symbol = a.symbol AND s.trade_date = a.trade_date
WHERE a.symbol IS NULL;
```

---

## File Reference

### Core Implementation
- `ap_symbol_tracking.py` - Symbol-level data extraction
- `ap_options_tracking.py` - Options contract filtering
- `ap_backfill.py` - Historical data backfill utility
- `ap_config.py` - Configuration (if needed for future enhancements)

### Database
- `airline_tracking_schema.sql` - Table definitions and indexes
- `data/datalake.db` - SQLite database

### Documentation
- `README.md` - This file (implementation guide)
- `DATA_QUALITY_FINDINGS.md` - Known data quality issues
- `tasks/0001-prd-airline-tracking-system.md` - Original PRD
- `tasks/tasks-0001-prd-airline-tracking-system.md` - Task list (69 tasks, all complete)

### Integration
- `main.py` - Pipeline integration (Step 3.6: run_airline_play_phase)
- `core/symbols_klmn800.py` - AIRLINE_PLAY_SYMBOLS definition

---

## Performance Metrics

**Runtime (Single Day):**
- Symbol tracking: 0.2 seconds (7 symbols)
- Options tracking: 11.5 seconds (500+ contracts)
- **Total: 11.7 seconds** ✅ (target: <5 minutes)

**Data Volume:**
- Symbol records per day: 7
- Option contracts per day: ~250-500 (varies by strike ranges)
- Historical coverage: 38 trading days (2025-08-08 to 2025-10-01)

**Storage:**
- airline_symbol_tracking: ~30 KB (254 rows)
- airline_options_tracking: ~2 MB (9,426 rows)

---

## Development Notes

### Adding New Airlines
To track additional airline symbols:

1. Add to `core/symbols_klmn800.py`:
```python
AIRLINE_PLAY_SYMBOLS = [
    'DAL', 'UAL', 'AAL',  # Primary
    'LUV', 'JBLU', 'ALK',  # Secondary
    'JETS',  # ETF
    'SAVE',  # NEW: Spirit Airlines
]
```

2. Determine strike range (primary ±10% or secondary ±5%):
```python
# In ap_options_tracking.py
PRIMARY_AIRLINES = ['DAL', 'UAL', 'AAL', 'SAVE']  # Add here if ±10%
```

3. Backfill historical data:
```bash
python ap_backfill.py --start-date 2025-08-08
```

### Modifying Strike Ranges
To adjust strike range percentages:

```python
# In ap_options_tracking.py, modify get_strike_range_pct()
def get_strike_range_pct(symbol: str) -> float:
    PRIMARY_AIRLINES = ['DAL', 'UAL', 'AAL']
    if symbol in PRIMARY_AIRLINES:
        return 0.15  # Changed from 0.10 (±15% instead of ±10%)
    else:
        return 0.05  # ±5% unchanged
```

Then re-run tracking to apply new filters.

### Extending Data Sources
To add new data sources to symbol tracking:

1. Create extraction function:
```python
def extract_new_data_source(conn, symbol, trade_date):
    cursor = conn.cursor()
    cursor.execute("SELECT metric1, metric2 FROM new_table WHERE ...")
    row = cursor.fetchone()
    return dict(row) if row else {}
```

2. Add to aggregation:
```python
new_data = extract_new_data_source(conn, symbol, trade_date)
row.update(new_data)  # Merge into aggregated row
```

3. Update schema and documentation.

---

## Support & Maintenance

**Data Quality Issues:** See `DATA_QUALITY_FINDINGS.md`
**Task Tracking:** See `tasks/tasks-0001-prd-airline-tracking-system.md`
**PRD Reference:** See `tasks/0001-prd-airline-tracking-system.md`

**Questions or Issues:** Document in project issues or update DATA_QUALITY_FINDINGS.md

---

**Status: Development-Ready** ✈️
All 69 implementation tasks complete. System is operational and extracting data correctly despite upstream data quality gaps. Ready for pattern analysis and strategy development (Phase 2).
