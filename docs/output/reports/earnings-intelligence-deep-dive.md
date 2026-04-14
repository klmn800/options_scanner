# Earnings Intelligence System - Deep Dive

**Document Version:** 1.0
**Last Updated:** 2025-10-29
**Author:** Ben (with Claude Code)

---

## Executive Summary

The **Earnings Intelligence (EI) System** is a comprehensive earnings analysis framework that:
1. Tracks upcoming earnings for all KLMN 800 symbols
2. Captures IV/price time series snapshots around earnings events (T-7 to T+3)
3. Calculates post-earnings price moves and IV crush metrics
4. Identifies sector sympathy and IV arbitrage opportunities
5. Provides pre-market actionable trade signals

**Current Integration Status:** ⚠️ **PARTIAL**
- ✅ Expected moves calculation runs nightly via `main.py`
- ❌ Snapshot collection, arbitrage scanner, and post-earnings calc are NOT integrated
- ❌ Requires manual execution via `ei_main.py`

---

## System Architecture

### Component Overview

The EI system consists of **5 core components** orchestrated by `ei_main.py`:

| Component | File | Purpose | Frequency | Integration Status |
|-----------|------|---------|-----------|-------------------|
| **1. Fetch Upcoming** | `ei_fetch_upcoming.py` | Pull next 90 days of earnings from yfinance | Weekly (Sundays) | ❌ Not integrated |
| **2. Snapshot Collector** | `ei_snapshot_collector.py` | Capture daily IV/price for events in T-7 to T+3 window | Daily (5:00 PM+) | ❌ Not integrated |
| **3. Post-Earnings Calculator** | `ei_post_earnings_calc.py` | Calculate moves/IV crush for completed events (T+3) | Daily (5:00 PM+) | ❌ Not integrated |
| **4. Expected Moves** | `ei_moves_upcoming.py` | Calculate expected vs historical moves | Daily (6:00 PM+) | ✅ **Integrated** |
| **5. Arbitrage Scanner** | `ei_arbitrage_scanner.py` | Find cheap IV in sector peers | Daily (6:30 AM) | ❌ Not integrated |

### Database Schema

The EI system uses **6 primary tables**:

```
earnings_upcoming (732 rows)
├─ symbol, earnings_date, earnings_days_ahead
├─ expected_move_pct (from current IV straddle)
├─ historical_avg_move_pct (from earnings_historical)
├─ move_difference_pct (historical - expected)
├─ earnings_play_signal (AVOID/NEUTRAL/BUY)
└─ updated_at (tracks freshness)

earnings_events (142 rows)
├─ event_id, symbol, earnings_date
├─ fiscal_year, fiscal_quarter
├─ estimated_eps, actual_eps, eps_surprise_pct
├─ notes, tags, sentiment (trading journal)
└─ earnings_time (BMO/AMC/Unknown)

earnings_snapshots (0 rows - NOT POPULATED)
├─ event_id, symbol, snapshot_date
├─ days_from_earnings (T-7 to T+3)
├─ close_price, volume
├─ iv_30dte, iv_front_month, iv_45dte
└─ total_open_interest, put_call_ratio

earnings_moves (9,250 rows - BACKFILLED)
├─ event_id, symbol
├─ move_1day_pct, move_2day_pct, move_3day_pct
├─ iv_buildup_pct, iv_collapse_pct, iv_crush_severity
└─ expected_move_pct, move_vs_expected_pct

earnings_sector_effects (0 rows - NOT POPULATED)
├─ primary_event_id, primary_symbol, peer_symbol
├─ primary_iv_buildup_pct, peer_iv_buildup_pct
├─ iv_arbitrage_delta (opportunity signal)
├─ correlation_strength, sample_size
└─ expected_peer_move_pct, arbitrage_quality

earnings_historical (aggregated from earnings_moves)
├─ symbol
├─ avg_move_pct, median_move_pct, max_move_pct
├─ avg_iv_crush_pct
└─ sample_size
```

---

## Component Details

### 1. Fetch Upcoming (`ei_fetch_upcoming.py`)

**Purpose:** Maintain fresh calendar of upcoming earnings for all KLMN 800 symbols

**What It Does:**
1. Queries yfinance for next 90 days of earnings for each symbol
2. Inserts/updates `earnings_upcoming` table
3. Cleans up past earnings (archives to `earnings_events`)

**Timing:** Weekly refresh (Sundays preferred)

**Dependencies:**
- Input: `core/symbols_klmn800.py` (symbol universe)
- Output: `earnings_upcoming` table
- External API: yfinance (free, no auth required)

**Current State:**
- ❌ Not integrated into `main.py`
- Last run: Unknown (table shows 732 upcoming earnings)
- Manual execution: `python ei_main.py --weekly-refresh`

**Integration Recommendation:**
- Add to `main.py` Sunday evening routine (~7:00 PM)
- Run AFTER archive operations complete
- Estimated runtime: ~5-10 minutes (800 symbols, rate-limited)

---

### 2. Snapshot Collector (`ei_snapshot_collector.py`)

**Purpose:** Build IV/price time series for upcoming earnings (T-7 to T+3 window)

**What It Does:**
1. Identifies earnings events in the collection window (7 days before to 3 days after)
2. For each event:
   - Pulls primary symbol IV metrics from `option_symbol_summary`
   - Pulls price data from `historical_prices`
   - Identifies top 4 industry peers from `industry_peer_mappings`
   - Collects same metrics for peers
3. Inserts daily snapshots into `earnings_snapshots` table
4. Skips duplicates (checks for existing snapshot_date + symbol combinations)

**Timing:** Daily after market close (5:00 PM+ when `option_symbol_summary` is fresh)

**Dependencies:**
- Input: `earnings_events` (upcoming events)
- Input: `option_symbol_summary` (IV metrics - populated by Option Pipeline)
- Input: `historical_prices` (price/volume data)
- Input: `industry_peer_mappings` (peer relationships)
- Output: `earnings_snapshots` table

**Current State:**
- ❌ Not running (table is empty)
- ❌ Blocking downstream analysis
- Missing data window: All events since system creation

**Integration Recommendation:**
- Add to `main.py` evening routine after Option Pipeline completes
- Run AFTER symbol summary is written (~5:45 PM)
- Run BEFORE expected moves update
- Estimated runtime: 2-5 minutes

**Critical Note:** Without snapshot data, IV buildup tracking and peer correlation analysis is impossible.

---

### 3. Post-Earnings Calculator (`ei_post_earnings_calc.py`)

**Purpose:** Calculate realized metrics for completed earnings events (at T+3 milestone)

**What It Does:**
1. Identifies events that are exactly 3 trading days past earnings
2. For each event:
   - Retrieves snapshots from T-7 to T+3
   - Calculates price moves: 1day, 2day, 3day, max_intraday
   - Calculates IV metrics: buildup%, collapse%, recovery%
   - Compares realized move vs expected move from straddle
   - Writes to `earnings_moves` table
3. For events with peers:
   - Analyzes peer sympathy moves
   - Calculates correlation strength
   - Identifies IV arbitrage opportunities (peer IV < primary IV)
   - Writes to `earnings_sector_effects` table

**Timing:** Daily after market close (5:00 PM+)

**Dependencies:**
- Input: `earnings_events` (event catalog)
- Input: `earnings_snapshots` (time series data)
- Input: `historical_prices` (price moves)
- Output: `earnings_moves` (primary symbol metrics)
- Output: `earnings_sector_effects` (peer relationships & arbitrage)

**Current State:**
- ❌ Not running
- `earnings_moves`: 9,250 backfilled rows (historical data)
- `earnings_sector_effects`: Empty (no peer analysis)

**Integration Recommendation:**
- Add to `main.py` evening routine
- Run AFTER snapshot collector
- Run BEFORE expected moves update
- Estimated runtime: 1-3 minutes

---

### 4. Expected Moves (`ei_moves_upcoming.py`)

**Purpose:** Calculate expected vs historical move comparison for upcoming earnings

**What It Does:**
1. For each symbol in `earnings_upcoming`:
   - Retrieves current IV from `option_symbol_summary` (iv_30dte or iv_front_month)
   - Calculates straddle-based expected move: `IV * sqrt(DTE/365) * 0.85`
   - Retrieves historical average move from `earnings_historical`
   - Calculates move_difference: `historical_avg - expected_move`
2. Sets earnings_play_signal:
   - **AVOID**: IV overpriced (negative difference > -2%)
   - **NEUTRAL**: Fairly priced (-2% to +2%)
   - **BUY**: IV underpriced (positive difference > +2%)
3. Sets earnings_alert flag if meets criteria:
   - Move difference ≥ 2% AND total_open_interest ≥ 4000
4. Updates `earnings_upcoming` table with all calculated fields

**Timing:** Daily after market close (~6:00 PM after Option Pipeline completes)

**Dependencies:**
- Input: `earnings_upcoming` (calendar)
- Input: `option_symbol_summary` (current IV)
- Input: `earnings_historical` (historical averages)
- Output: Updates `earnings_upcoming` table in-place

**Current State:**
- ✅ **INTEGRATED** into `main.py`
- ✅ Runs nightly automatically
- ✅ Last run: 2025-10-28 18:06-18:16
- ✅ Processed 732 symbols successfully

**Integration Note:** This is the ONLY EI component currently integrated.

---

### 5. Arbitrage Scanner (`ei_arbitrage_scanner.py`)

**Purpose:** Pre-market scan for IV arbitrage opportunities in sector sympathy plays

**What It Does:**
1. Identifies today's earnings events (earnings_date = current_date)
2. For each event with earnings today:
   - Retrieves historical IV buildup pattern for primary symbol
   - Identifies industry peers from `industry_peer_mappings`
   - Checks peer's current IV vs historical sympathy move
   - Calculates IV arbitrage opportunity:
     - **High Quality:** Strong correlation (>0.7) + large IV discount (>5%)
     - **Medium Quality:** Moderate correlation (0.5-0.7) + medium discount (3-5%)
     - **Low Quality:** Weak correlation (<0.5) or small discount (<3%)
3. Ranks opportunities by quality score
4. Flags top opportunities for Morning View

**Timing:** Pre-market scan (6:30 AM daily)

**Dependencies:**
- Input: `earnings_events` (today's earnings)
- Input: `earnings_snapshots` (IV buildup patterns)
- Input: `earnings_sector_effects` (peer correlation data)
- Input: `industry_peer_mappings` (peer relationships)
- Output: Console alerts + Morning View integration

**Current State:**
- ❌ Not running
- ❌ Cannot run without snapshot data
- ❌ No peer correlation data available

**Integration Recommendation:**
- Add to `main.py` morning routine (6:30 AM)
- Run BEFORE Flow Monitor starts
- Estimated runtime: 30-60 seconds
- Output: High-value pre-market alerts

---

## Trading Strategy & Philosophy

### Core Insight

**Options IV frequently misprices earnings risk.** The EI system identifies two types of opportunities:

#### 1. Direct Plays (Expected Moves Analysis)
- **Thesis:** Current IV straddle predicts expected move
- **Reality:** Historical move often differs significantly
- **Opportunity:**
  - When IV is too high (AVOID signal) → Sell premium
  - When IV is too low (BUY signal) → Buy directional/straddle

**Example from yesterday's analysis:**
- **META**: Historical avg move = 12.76%, IV pricing only 5.75%
  - **Signal:** NEUTRAL (slight buy opportunity, +7.01% underpriced)
  - **Play:** Long straddle or ATM calls/puts

- **AVTR**: Historical avg = 5.19%, IV pricing 12.85%
  - **Signal:** AVOID (-7.66% overpriced)
  - **Play:** Sell premium (credit spreads, iron condors)

#### 2. Sector Sympathy Plays (Arbitrage Scanner)
- **Thesis:** When Company A reports, peers in same industry often move
- **Reality:** Peer IV doesn't always price in sympathy risk
- **Opportunity:** Buy cheap peer options when primary reports

**Example scenario (hypothetical - not currently running):**
```
Primary: NVDA reports today
- IV buildup: +15% over past week
- Expected move: ±8%

Peer: AMD (semiconductor peer)
- Historical sympathy: Moves 60% of NVDA's move (0.6 correlation)
- Expected sympathy move: ±4.8%
- Current IV pricing: Only ±3.2% move
- Arbitrage: +1.6% IV discount

Signal: HIGH QUALITY BUY (strong correlation + large discount)
Play: AMD long straddle or ATM call/put spread
```

### Risk Management

**Position Sizing:**
- Earnings plays are volatile - use 0.5-1% of account per trade
- Spread the risk across 3-5 opportunities
- Avoid concentration in single sector

**Timing:**
- **Direct plays:** Enter day before earnings (T-1) when IV peaks
- **Sympathy plays:** Enter morning of primary's report (T+0)
- **Exit:** Close 50% at 50% profit, let rest run for 2-3 days

**Avoid These Scenarios:**
- Low open interest (<4,000) → Wide spreads, liquidity issues
- Very small expected moves (<3%) → Not worth the commissions
- High IV crush severity historically → Risk of total loss on long premium

---

## Data Flow & Dependencies

### Evening Pipeline (5:00 PM - 6:30 PM)

```
Option Pipeline completes (5:30 PM)
  ↓
option_symbol_summary populated with latest IV
  ↓
┌─────────────────────────────────────┐
│ 1. Snapshot Collector (5:45 PM)    │ ← NOT INTEGRATED
│    - Reads: option_symbol_summary   │
│    - Reads: historical_prices       │
│    - Writes: earnings_snapshots     │
└─────────────────────────────────────┘
  ↓
┌─────────────────────────────────────┐
│ 2. Post-Earnings Calc (5:50 PM)    │ ← NOT INTEGRATED
│    - Reads: earnings_snapshots      │
│    - Writes: earnings_moves         │
│    - Writes: earnings_sector_effects│
└─────────────────────────────────────┘
  ↓
┌─────────────────────────────────────┐
│ 3. Expected Moves (6:00 PM)         │ ✅ INTEGRATED
│    - Reads: option_symbol_summary   │
│    - Reads: earnings_historical     │
│    - Updates: earnings_upcoming     │
└─────────────────────────────────────┘
```

### Morning Pipeline (6:30 AM)

```
Pre-market (6:30 AM)
  ↓
┌─────────────────────────────────────┐
│ Arbitrage Scanner (6:30 AM)         │ ← NOT INTEGRATED
│    - Reads: earnings_upcoming       │
│    - Reads: earnings_snapshots      │
│    - Reads: earnings_sector_effects │
│    - Outputs: Console alerts        │
└─────────────────────────────────────┘
  ↓
Morning View displays opportunities
```

### Weekly Pipeline (Sundays, 7:00 PM)

```
Archive operations complete (6:30 PM)
  ↓
┌─────────────────────────────────────┐
│ Fetch Upcoming (7:00 PM)            │ ← NOT INTEGRATED
│    - Reads: symbols_klmn800         │
│    - API: yfinance                  │
│    - Writes: earnings_upcoming      │
│    - Archives: earnings_events      │
└─────────────────────────────────────┘
```

---

## Integration with Other Systems

### Option Pipeline (OP)
**Relationship:** Primary IV data source for EI system

- OP runs twice daily (6:35 AM, 5:00 PM+)
- OP populates `option_symbol_summary` with IV metrics
- EI reads IV from `option_symbol_summary.iv_30dte` or `iv_front_month`
- **Critical dependency:** EI snapshot collector MUST run after OP completes

**Timing coordination:**
```
5:00 PM: Option Pipeline starts
5:30 PM: OP completes, symbol summary written
5:45 PM: EI snapshot collector can safely read IV data
```

### Flow Monitor (FM)
**Relationship:** Complementary alert system

- FM tracks unusual options flow (volume spikes, large orders)
- EI tracks upcoming earnings calendar and IV mispricing
- **Overlap opportunity:** When FM detects flow spike on symbol with upcoming earnings
  - Cross-reference with `earnings_upcoming` table
  - Check if IV is mispriced
  - High-confidence signal if both systems align

**Potential integration:**
- Add earnings_days_ahead column to `flow_alerts` table
- Flag flow alerts that occur 1-3 days before earnings
- These are often informed flow (institutions positioning)

### Morning View (MV)
**Relationship:** Primary UI for EI insights

- MV "Earnings Browser" screen displays `earnings_upcoming` data
- MV shows expected vs historical moves
- MV highlights earnings_alert flagged opportunities
- **Missing:** Arbitrage scanner output not yet integrated into MV

**Enhancement opportunity:**
- Add "Sector Plays" tab to Morning View
- Display high-quality arbitrage opportunities from scanner
- Real-time alerts when scanner identifies Grade-A setups

### Oracle Intelligence
**Relationship:** AI-powered deep-dive analysis

- Oracle can query EI tables for narrative analysis
- Can explain WHY certain earnings show IV discrepancy
- Can research historical context (news, trends, sector rotation)
- **Use case:** "Oracle, analyze why NVDA's IV is so high before earnings"

---

## Optimal Call Times

Based on data dependencies and market timing:

### Daily Operations

| Component | Optimal Time | Reason | Duration |
|-----------|-------------|--------|----------|
| **Snapshot Collector** | 5:45 PM ET | After Option Pipeline completes | 2-5 min |
| **Post-Earnings Calc** | 5:50 PM ET | After snapshots collected | 1-3 min |
| **Expected Moves** | 6:00 PM ET | After calculations complete | 1-2 min |
| **Arbitrage Scanner** | 6:30 AM ET | Pre-market, before trader arrives | 30-60 sec |

### Weekly Operations

| Component | Optimal Time | Reason | Duration |
|-----------|-------------|--------|----------|
| **Fetch Upcoming** | Sunday 7:00 PM ET | After archive operations, fresh week ahead | 5-10 min |

### Manual Operations

- **Backfill historical:** Anytime (doesn't interfere with live data)
- **One-time setup:** Weekend preferred
- **Testing/debugging:** After-hours only (don't corrupt live data)

---

## Current Gaps & Missing Features

### Critical Gaps

1. **No Snapshot Collection** ❌
   - Impact: Cannot build IV time series
   - Impact: Cannot analyze IV buildup patterns
   - Impact: Cannot calculate post-earnings metrics
   - **Fix required:** Integrate snapshot collector into `main.py`

2. **No Arbitrage Scanner** ❌
   - Impact: Missing sector sympathy opportunities
   - Impact: No pre-market alerts for cheap peer IV
   - **Fix required:** Integrate scanner into `main.py` morning routine

3. **No Peer Correlation Data** ❌
   - Impact: `earnings_sector_effects` table is empty
   - Impact: Cannot rank sympathy play quality
   - **Fix required:** Post-earnings calculator needs to run

4. **Incomplete Integration** ⚠️
   - Only 1 of 5 components integrated into `main.py`
   - Requires manual execution via `ei_main.py`
   - **Fix required:** Wire up remaining 4 components

### Enhancement Opportunities

1. **Real-time IV Tracking** 💡
   - Current: Only tracks IV at EOD snapshot
   - Enhancement: Track IV every 30 minutes on earnings day
   - Benefit: Capture intraday IV expansion/contraction patterns

2. **Sentiment Integration** 💡
   - Current: No sentiment analysis
   - Enhancement: Scrape earnings call transcripts, news sentiment
   - Benefit: Understand WHY moves differ from expectations

3. **Options Greeks Analysis** 💡
   - Current: Only tracks IV
   - Enhancement: Track delta exposure, gamma walls, vanna levels
   - Benefit: Understand dealer hedging impact on price action

4. **Backtesting Engine** 💡
   - Current: No performance tracking
   - Enhancement: Simulate trades based on historical signals
   - Benefit: Validate strategy profitability, optimize thresholds

5. **Email/SMS Alerts** 💡
   - Current: Only console logging
   - Enhancement: Send morning alerts for high-quality opportunities
   - Benefit: Don't miss Grade-A setups when not at computer

---

## Next Steps for Full Integration

### Phase 1: Core Integration (Highest Priority)

**Goal:** Get snapshot collector and post-earnings calc running nightly

**Tasks:**
1. Add snapshot collector to `main.py` evening routine (~line 980, after Option Pipeline)
2. Add post-earnings calc immediately after snapshot collector
3. Test full evening pipeline (OP → Snapshot → Calc → Moves)
4. Verify `earnings_snapshots` table is populating
5. Verify `earnings_moves` and `earnings_sector_effects` are updating

**Estimated effort:** 2-3 hours
**Impact:** Unlocks historical analysis and peer correlation data

### Phase 2: Morning Scanner (High Priority)

**Goal:** Enable pre-market arbitrage opportunity alerts

**Tasks:**
1. Add arbitrage scanner to `main.py` morning routine (~line 640, before FM starts)
2. Integrate scanner output into Morning View "Sector Plays" tab
3. Test scanner with historical data (backtest mode)
4. Validate opportunity quality scoring
5. Add email/SMS alert capability

**Estimated effort:** 4-5 hours
**Impact:** Actionable pre-market trade signals

### Phase 3: Weekly Refresh (Medium Priority)

**Goal:** Automate earnings calendar updates

**Tasks:**
1. Add fetch_upcoming to `main.py` Sunday evening routine
2. Add archive logic (earnings_upcoming → earnings_events for past events)
3. Test with dry-run mode first
4. Schedule Sunday 7:00 PM execution

**Estimated effort:** 1-2 hours
**Impact:** Always have fresh earnings calendar

### Phase 4: Enhancements (Lower Priority)

**Goal:** Advanced features for power users

**Tasks:**
1. Intraday IV tracking (30-min snapshots on earnings day)
2. Sentiment scraping (earnings call transcripts, news)
3. Greeks analysis (delta/gamma exposure)
4. Backtesting engine (simulate historical performance)
5. Alert system (email/SMS for Grade-A opportunities)

**Estimated effort:** 10-15 hours
**Impact:** Professional-grade earnings intelligence platform

---

## Summary

The Earnings Intelligence system is **architecturally complete but operationally incomplete**:

✅ **What works:**
- Expected moves calculation (running nightly)
- Database schema (properly designed)
- Component modularity (clean separation of concerns)
- Historical backfill (9,250 earnings events)

❌ **What's missing:**
- Snapshot collector (blocking all time-series analysis)
- Arbitrage scanner (missing pre-market signals)
- Post-earnings calculator (no peer correlation data)
- Full integration into `main.py` (only 1 of 5 components)

🎯 **Critical path to unlock full value:**
1. Integrate snapshot collector → Unlocks time-series analysis
2. Run post-earnings calc → Builds peer correlation database
3. Integrate arbitrage scanner → Delivers actionable pre-market alerts

**Recommendation:** Prioritize Phase 1 integration (snapshot + calc) to start building the correlation database immediately. This data accumulates value over time - the sooner it starts running, the more valuable the system becomes.

---

**End of Deep Dive**

*For questions or integration planning, see `strategies/earnings_intel/MANUAL_OPERATIONS.md` and `CLAUDE.md`*
