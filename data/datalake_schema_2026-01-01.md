# DataLake Schema Documentation

**Generated:** January 1, 2026
**Last Updated:** January 8, 2026 (Current Database State)
**Database:** datalake.db
**Total Tables:** 28 (25 active documented tables)
**Total Rows:** 24,900,000+ (including 23.5M flow scans, 1.34M option contracts, 19.9K option summaries, 1,757 flow alerts, 454 earnings events, 9.3K earnings moves)

## Table Summary

| Table Name | Row Count | Status |
|------------|-----------|---------|
| alert_contract_tracking | 1,283 | ✅ Active |
| earnings_events | 454 | ✅ Active |
| earnings_moves | 9,296 | ✅ Active |
| earnings_sector_effects | 0 | ✅ Active |
| earnings_snapshots | 0 | ✅ Active |
| earnings_upcoming | 368 | ✅ Active |
| flow_alerts | 1,757 | ✅ Active |
| flow_options_scans | 23,470,033 | ✅ Active |
| flow_symbol_summary | 2,210 | ✅ Active |
| flow_watchlist_daily | 21 | ✅ Active |
| flow_watchlist_daily_archive | 0 | ✅ Active |
| historical_prices | 48,713 | ✅ Active |
| industry_peer_mappings | 742 | ✅ Active |
| market_daily_summary | 57 | ✅ Active |
| news_articles | 5,165 | ✅ Active |
| news_symbol_sentiment | 12,173 | ✅ Active |
| option_contracts | 1,344,434 | ✅ Active |
| option_symbol_summary | 19,928 | ✅ Active |
| symbol_baselines | 754 | ✅ Active |
| symbol_metadata | 757 | ✅ Active |

**Note:** Tables excluded from this documentation: user_watchlist, social_posts. Tables `flow_contract_trackers`, `flow_tracker_updates`, and `agent_actions` were dropped 2026-04-22 (deprecated Flow Tracker Agent system).

## Migration Notes (October 2025 - January 2026)

**Alert Resolution Integration (Jan 7, 2026):**
- Added alert resolution tracking to `flow_alerts` (5 new columns)
  - Resolves alert ambiguity: are positions opening (BUILDING) or closing (CLOSING)?
  - Uses next-day OI data from Option Pipeline for classification
  - 70% threshold fuzzy logic for significance
- Added sentiment tracking to `flow_watchlist_daily` (3 new columns)
  - Recency-based sentiment (most recent signals matter most)
  - BUILDING (smart money entering), CLOSING (exiting), or NEUTRAL
  - Integrates into buy-the-dip detection workflow
- New module: `fm_alert_resolver.py` runs pre-market (9:15 AM)

**Alert Resolution Rollback (December 2025):**
- Removed alert resolution tracking columns from `flow_alerts` ONLY (next_day_oi, oi_resolution, oi_change_contracts, oi_change_pct, resolved_at)
- Kept sentiment tracking columns in `flow_watchlist_daily` (building_alerts_count, closing_alerts_count, alert_sentiment)
- Flow alerts reverted to simpler structure, watchlist sentiment tracking retained

**Flow Alerts Enhancement (Q4 2025):**
- Added `predictive_flag` INTEGER column to `flow_alerts` - manual user flag to mark alerts as predictive/forward-looking
- Added Greek values (delta, gamma, theta, vega) directly to `flow_alerts` table for easier analysis

**Earnings Intelligence Growth (Q4 2025):**
- `earnings_events` now populated with 454 historical events (was 0 in Oct 2025)
- `earnings_moves` now tracking 9,296 price movements post-earnings (was 0 in Oct 2025)
- Trading journal fields added: notes, tags, note_type, sentiment
- IV percentile tracking across multiple DTE buckets

**News Collection Expansion (Q4 2025):**
- `news_articles` grew from ~690 to 5,165 articles
- `news_symbol_sentiment` grew from ~2,800 to 12,173 sentiment records
- Added `topics_collected` field to news_symbol_sentiment

**Data Archiving Working (Q4 2025):**
- Flow scans reduced from 24.5M to 23.47M through sector archiving
- Option contracts reduced from 1.46M to 1.34M through sector archiving
- Option symbol summary reduced from 64K to 19.9K through sector archiving

**Flow Monitor Refactor (Oct 16-20, 2025):**
- Added `flow_options_scans` table - intraday scan snapshots with alert detection
- Refactored `flow_alerts` - simplified schema focused on alert lifecycle
- Updated `flow_symbol_summary` - selective population strategy

**Option Pipeline Refactor (Oct 19, 2025):**
- Renamed `oi_delta` → `option_pipeline` (directory)
- Renamed `oid_*.py` → `op_*.py` (7 files)
- Renamed `oi_daily` → `option_contracts` (table)
- Renamed `oi_symbol_summary` → `option_symbol_summary` (table)
- Renamed columns: `implied_volatility` → `iv`, `days_to_expiration` → `dte`

## Detailed Schema

### flow_options_scans
**Rows:** 23,470,033
**Purpose:** Intraday options flow scanning with alert detection (Flow Monitor Strategy)
**Populated By:** fm_scanner.py
**Historical Coverage:** Every scan during market hours (9:15 AM - 4:00 PM ET)

| Column | Type | Description |
|--------|------|-------------|
| contract_hash | TEXT | Contract identifier (Primary Key): SYMBOL\|STRIKE\|EXPIRATION\|TYPE |
| scan_timestamp | TEXT | When scan was performed (Primary Key) |
| trade_date | TEXT | Trading date |
| symbol | TEXT | Ticker symbol |
| strike | REAL | Strike price (2 decimals) |
| expiration_date | TEXT | Option expiration date |
| option_type | TEXT | CALL or PUT |
| moneyness | TEXT | ITM/ATM/OTM classification |
| dte | INTEGER | Days to expiration |
| open_interest | INTEGER | Open interest |
| bid | REAL | Bid price (2 decimals) |
| ask | REAL | Ask price (2 decimals) |
| volume | INTEGER | Trading volume |
| volume_change | INTEGER | Volume change since previous scan |
| volume_change_pct | REAL | Volume change percentage (2 decimals) |
| underlying_price | REAL | Stock price (2 decimals) |
| underlying_change | REAL | Stock price change (2 decimals) |
| underlying_change_pct | REAL | Stock price change percentage (2 decimals) |
| last_price | REAL | Last traded option price (2 decimals) |
| price_change | REAL | Option price change (2 decimals) |
| price_change_pct | REAL | Option price change percentage (2 decimals) |
| option_leverage | REAL | Option price % move / stock % move (4 decimals) |
| iv | REAL | Implied volatility (4 decimals) |
| iv_change | REAL | IV change since previous scan (4 decimals) |
| iv_change_pct | REAL | IV change percentage (2 decimals) |
| delta | REAL | Delta Greek (4 decimals) |
| gamma | REAL | Gamma Greek (4 decimals) |
| theta | REAL | Theta Greek (4 decimals) |
| vega | REAL | Vega Greek (4 decimals) |
| premium_value | REAL | Option premium value (2 decimals) |
| flow_percentage | REAL | Volume as % of OI (2 decimals) |
| volume_surprise_factor | REAL | Volume vs baseline (2 decimals) |
| significance_score | REAL | Statistical significance score (2 decimals) |
| alert_threshold_met | BOOLEAN | Whether alert thresholds met |
| alert_reason | TEXT | Why alert triggered (if applicable) |
| created_at | TEXT | Record creation timestamp |

**Primary Key:** (contract_hash, scan_timestamp)

**Indexes (production):**
- `idx_flow_scans_contract` ON (symbol, expiration_date, option_type)
- `idx_flow_scans_date_scan` ON (trade_date, scan_timestamp)
- `idx_flow_scans_scan_timestamp` ON (scan_timestamp)
- `idx_flow_scans_significance` ON (significance_score) WHERE significance_score IS NOT NULL

**Indexes (query DB — subset for faster quick-sync):**
- `idx_flow_scans_date_scan` ON (trade_date, scan_timestamp)
- `idx_flow_scans_scan_timestamp` ON (scan_timestamp)

**Key Features:**
1. **Intraday Time Series:** Captures multiple snapshots per contract per day
2. **Alert Detection:** Pre-computes significance scores and threshold checks
3. **Volume Tracking:** Tracks volume changes between scans
4. **Performance:** Indexes optimized for contract lookups and alert queries

**Usage:**
- Source data for `flow_alerts` (contracts that meet alert thresholds)
- Historical flow analysis and pattern detection
- Profitability evaluation (tracks price movements after alerts)

### flow_alerts
**Rows:** 1,757
**Purpose:** Unusual options activity alerts and their performance tracking
**Populated By:** fm_alerts.py (Flow Monitor Strategy)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier (Primary Key, Auto-increment) |
| contract_hash | TEXT | Contract identifier: SYMBOL\|STRIKE\|EXPIRATION\|TYPE |
| trade_date | TEXT | Trading date |
| symbol | TEXT | Ticker symbol |
| strike | REAL | Strike price (2 decimals) |
| expiration_date | TEXT | Option expiration date |
| option_type | TEXT | CALL or PUT |
| moneyness | TEXT | ITM/ATM/OTM classification |
| underlying_price | REAL | Stock price at alert time (2 decimals) |
| dte | INTEGER | Days to expiration |
| volume | INTEGER | Trading volume |
| open_interest | INTEGER | Open interest |
| iv | REAL | Implied volatility (4 decimals) |
| last_price | REAL | Last traded price (2 decimals) |
| premium_value | REAL | Option premium (2 decimals) |
| flow_percentage | REAL | Volume as % of OI (2 decimals) |
| volume_surprise_factor | REAL | Volume vs baseline (2 decimals) |
| significance_score | REAL | Overall alert score (2 decimals) |
| alert_reason | TEXT | Why alert triggered |
| alert_level | TEXT | Alert priority level |
| max_prof_1d_pct | REAL | Max profit % in 1 day (2 decimals) |
| max_prof_3d_pct | REAL | Max profit % in 3 days (2 decimals) |
| max_prof_7d_pct | REAL | Max profit % in 7 days (2 decimals) |
| max_prof_14d_pct | REAL | Max profit % in 14 days (2 decimals) |
| max_prof_30d_pct | REAL | Max profit % in 30 days (2 decimals) |
| days_to_max_prof | INTEGER | Days to peak profit |
| peak_hour_est | INTEGER | Hour of day when peak occurred (0-23) |
| max_loss_1d_pct | REAL | Max loss % in 1 day (2 decimals) |
| max_loss_3d_pct | REAL | Max loss % in 3 days (2 decimals) |
| max_loss_7d_pct | REAL | Max loss % in 7 days (2 decimals) |
| max_loss_14d_pct | REAL | Max loss % in 14 days (2 decimals) |
| max_loss_30d_pct | REAL | Max loss % in 30 days (2 decimals) |
| days_to_max_loss | INTEGER | Days to worst loss |
| evaluation_status | TEXT | Tracking status (pending/complete/expired) |
| final_quality_score | REAL | Post-analysis quality score (2 decimals) |
| last_evaluated_date | TEXT | Last evaluation timestamp |
| alert_timestamp | TEXT | When alert was generated |
| scan_timestamp | TEXT | When scan was performed |
| analyst_context | TEXT | AI analyst notes |
| social_posted | BOOLEAN | Whether posted to social media |
| social_post_id | INTEGER | Foreign key to social_posts table |
| predictive_flag | INTEGER | Manual user flag marking alert as predictive (user entry, not automated) |
| delta | REAL | Delta Greek (4 decimals) |
| gamma | REAL | Gamma Greek (4 decimals) |
| theta | REAL | Theta Greek (4 decimals) |
| vega | REAL | Vega Greek (4 decimals) |

**Primary Key:** id

**Indexes:**
- `idx_flow_alerts_evaluation` ON (evaluation_status, last_evaluated_date)
- `idx_flow_alerts_symbol_date` ON (symbol, trade_date DESC)

**Key Features:**
1. **Lifecycle Tracking:** From alert generation through evaluation completion
2. **Performance Metrics:** Profit/loss tracking at multiple time horizons (1d, 3d, 7d, 14d, 30d)
3. **Greek Integration:** Full Greek values captured at alert time
4. **Predictive Flag:** Manual user annotation for marking forward-looking signals
5. **Social Integration:** Links to social media posts for alerts
6. **AI Context:** Stores analyst reasoning and context

**Data Flow:**
1. fm_scanner.py detects unusual activity in flow_options_scans
2. fm_alerts.py creates alert record with initial metrics
3. fm_evaluator.py updates profit/loss metrics as contract evolves
4. fm_evaluator.py sets final_quality_score when evaluation complete

### flow_symbol_summary
**Rows:** 2,210
**Purpose:** Focused daily symbol-level flow tracking - ONLY symbols with alert activity
**Populated By:** fm_symbol_rollup.py (Flow Monitor Strategy)
**Optimization:** Selective population strategy - processes only ~50-100 symbols/day where `alert_threshold_met = 1`, reducing from prior universal 800-symbol approach

| Column | Type | Description |
|--------|------|-------------|
| trade_date | DATE | Trading date (Primary Key) |
| symbol | TEXT | Ticker symbol (Primary Key) |
| significant_contract_count | INTEGER | Number of contracts exceeding significance threshold |
| max_significance_score | REAL | Highest significance score among tracked contracts (2 decimals) |
| total_premium_tracked | REAL | Total premium value of significant contracts (2 decimals) |
| active_alert_count | INTEGER | Current active flow alerts (not expired) |
| new_alert_count | INTEGER | New alerts generated today |
| days_since_last_alert | INTEGER | Days since most recent alert |
| alert_count_5d | INTEGER | Pre-computed: Total alerts in past 5 trading days |
| alert_count_20d | INTEGER | Pre-computed: Total alerts in past 20 trading days |
| created_at | TEXT | Record creation timestamp |
| updated_at | TEXT | Last update timestamp |

**Primary Key:** (trade_date, symbol)

**Indexes:**
- `idx_flow_symbol_summary_date` ON (trade_date)
- `idx_flow_symbol_summary_symbol` ON (symbol)
- `idx_flow_symbol_summary_alert_count_5d` ON (alert_count_5d DESC)

**Key Features:**
1. **Selective Population:** Only processes symbols where `alert_threshold_met = 1` in flow_options_scans
2. **Pre-computed Rolling Windows:** `alert_count_5d` and `alert_count_20d` calculated during evening rollup (~5:30 PM) to eliminate expensive correlated subqueries in morning views (7:30 AM)
3. **Performance Benefit:** Morning view queries execute instantly via direct column lookup vs running COUNT() subqueries for 50-100 symbols

**Historical Coverage:** June 24, 2025 to present

**Migration Note (Oct 16, 2025):** Renamed from portions of deprecated `options_symbol_summary` table to focus exclusively on flow tracking metrics.

### flow_watchlist_daily
**Rows:** 21
**Purpose:** Symbol-level price tracking for buy-the-dip detection (Flow Monitor Strategy)
**Populated By:** fm_watchlist.py
**Retention:** 7-day rolling window (auto-archived to flow_watchlist_daily_archive)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier (Primary Key, Auto-increment) |
| symbol | TEXT | Ticker symbol |
| entry_date | TEXT | Date watchlist entry was created |
| entry_expiration_date | TEXT | Date entry expires (7 days after entry_date) |
| entry_ul_price | REAL | Underlying price at entry (2 decimals) |
| current_ul_price | REAL | Current underlying price (2 decimals) |
| price_diff_pct | REAL | Price change percentage (2 decimals) |
| option_type | TEXT | CALL, PUT, or MIXED |
| first_alert_id | INTEGER | ID of first alert that created this entry |
| alert_count_today | INTEGER | Number of alerts for this symbol today |
| max_significance_score | REAL | Highest alert significance score (2 decimals) |
| dip_detected | BOOLEAN | Whether 5% dip threshold met |
| dip_detected_date | TEXT | When dip was first detected |
| building_alerts_count | INTEGER | Count of BUILDING alerts (most recent date) |
| closing_alerts_count | INTEGER | Count of CLOSING alerts (most recent date) |
| alert_sentiment | TEXT | BUILDING, CLOSING, or NEUTRAL |
| created_at | TEXT | Record creation timestamp |
| last_updated | TEXT | Last price update timestamp |

**Primary Key:** id

**Unique Constraint:** (symbol, entry_date)

**Indexes:**
- `idx_watchlist_symbol` ON (symbol)
- `idx_watchlist_dip` ON (dip_detected)
- `idx_watchlist_expiration` ON (entry_expiration_date)

**Archive Table:** flow_watchlist_daily_archive (same schema + archived_at column)
**Archive Status:** 0 rows - archiving system working, no entries have expired yet (7-day retention)

**Key Features:**
1. **Daily Staggered Entries:** One entry per symbol per day prevents price anchor bias
2. **Price Tracking:** Monitors underlying price changes vs entry price
3. **Dip Detection:** Flags 5% moves based on option_type:
   - CALL: price drop >= 5% → buy-the-dip opportunity
   - PUT: price rise >= 5% → buy-the-dip opportunity
   - MIXED: any 5% move → signal
4. **Alert Sentiment Integration:** Tracks whether smart money is entering (BUILDING) or exiting (CLOSING)
5. **Recency-Based Sentiment:** Uses most recent alert resolutions to determine current sentiment
6. **7-Day Window:** Automatic expiration and archiving after 7 days

**Data Flow:**
1. fm_watchlist.py creates entry when flow alert fires
2. Price updates every market hours cycle (~60 seconds)
3. fm_alert_resolver.py updates sentiment each morning (9:15 AM) using next-day OI
4. Dip detection triggers email notifications with sentiment context
5. Post-market cleanup archives expired entries

**Created:** 2026-01-06
**Enhanced:** 2026-01-07 (Alert resolution integration)

### option_contracts
**Rows:** 1,344,434
**Purpose:** Daily open interest snapshots with time series analysis (Option Pipeline Strategy, formerly OID)
**Populated By:** op_collector.py, op_analyzer.py
**Strike Range:** ±20% from underlying price (data before 2025-09-18 used ±50%)

| Column | Type | Description |
|--------|------|-------------|
| contract_hash | TEXT | Contract identifier (Primary Key): SYMBOL\|STRIKE\|EXPIRATION\|TYPE |
| trade_date | TEXT | Trading date (Primary Key) |
| symbol | TEXT | Ticker symbol |
| strike | REAL | Strike price (2 decimals) |
| expiration_date | TEXT | Option expiration date |
| option_type | TEXT | CALL or PUT |
| moneyness | TEXT | ITM/ATM/OTM classification |
| underlying_price | REAL | Stock price (2 decimals) |
| dte | INTEGER | Days to expiration |
| volume | INTEGER | Trading volume |
| open_interest | INTEGER | Current open interest value |
| iv | REAL | Implied volatility (4 decimals) |
| last_price | REAL | Last traded option price (2 decimals) |
| bid | REAL | Bid price (2 decimals) |
| ask | REAL | Ask price (2 decimals) |
| bid_ask_spread_pct | REAL | Bid-ask spread percentage (2 decimals) |
| oi_build_start_date | TEXT | Date when OI build pattern started |
| oi_build_start_price | REAL | Stock price when OI build started (2 decimals) |
| build_pattern | TEXT | 'sudden' or 'gradual' position building |
| building_unwinding | TEXT | 'building', 'unwinding', or 'stable' |
| oi_change_1d | INTEGER | 1-day OI change |
| oi_change_5d | INTEGER | 5-day OI change |
| oi_change_10d | INTEGER | 10-day OI change |
| oi_change_pct_1d | REAL | 1-day OI change percentage (2 decimals) |
| oi_change_pct_5d | REAL | 5-day OI change percentage (2 decimals) |
| oi_change_pct_10d | REAL | 10-day OI change percentage (2 decimals) |
| oi_momentum_5d | REAL | 5-day momentum indicator (4 decimals) |
| volume_avg_5d | REAL | 5-day average volume (2 decimals) |
| volume_avg_20d | REAL | 20-day average volume (2 decimals) |
| volume_ratio_5d | REAL | Volume vs 5-day average (4 decimals) |
| volume_ratio_20d | REAL | Volume vs 20-day average (4 decimals) |
| volume_percentile_rank_20d | REAL | 20-day volume percentile (2 decimals) |
| volume_change_1d | INTEGER | 1-day volume change |
| volume_change_5d | INTEGER | 5-day volume change |
| volume_ratio_5d_change_1d | REAL | 1-day change in 5-day volume ratio (4 decimals) |
| iv_change_1d | REAL | 1-day IV change (4 decimals) |
| iv_change_5d | REAL | 5-day IV change (4 decimals) |
| iv_change_20d | REAL | 20-day IV change (4 decimals) |
| iv_change_pct_1d | REAL | 1-day IV change percentage (2 decimals) |
| iv_change_pct_5d | REAL | 5-day IV change percentage (2 decimals) |
| iv_change_pct_20d | REAL | 20-day IV change percentage (2 decimals) |
| iv_avg_5d | REAL | 5-day average IV (4 decimals) |
| iv_avg_20d | REAL | 20-day average IV (4 decimals) |
| iv_percentile_20day | REAL | 20-day IV percentile (2 decimals) |
| iv_momentum_1d | REAL | 1-day IV momentum (4 decimals) |
| iv_momentum_5d | REAL | 5-day IV momentum (4 decimals) |
| delta | REAL | Delta Greek (4 decimals) |
| delta_change_1d | REAL | 1-day delta change (4 decimals) |
| delta_change_5d | REAL | 5-day delta change (4 decimals) |
| delta_momentum | REAL | Delta momentum (4 decimals) |
| delta_acceleration | REAL | Delta acceleration (4 decimals) |
| gamma | REAL | Gamma Greek (4 decimals) |
| gamma_change_1d | REAL | 1-day gamma change (4 decimals) |
| gamma_change_5d | REAL | 5-day gamma change (4 decimals) |
| gamma_momentum | REAL | Gamma momentum (4 decimals) |
| theta | REAL | Theta Greek (4 decimals) |
| theta_change_1d | REAL | 1-day theta change (4 decimals) |
| theta_change_5d | REAL | 5-day theta change (4 decimals) |
| theta_momentum | REAL | Theta momentum (4 decimals) |
| theta_avg_5d | REAL | 5-day average theta (4 decimals) |
| theta_daily_change_avg_5d | REAL | 5-day average daily theta change (4 decimals) |
| vega | REAL | Vega Greek (4 decimals) |
| vega_change_1d | REAL | 1-day vega change (4 decimals) |
| vega_change_5d | REAL | 5-day vega change (4 decimals) |
| created_at | TEXT | Record creation timestamp |
| iv_percentile_rank_20d | REAL | 20-day IV percentile rank (2 decimals) |

**Primary Key:** (contract_hash, trade_date)

**Key Features:**
1. **Time Series Analysis:** Multiple lookback periods (1d, 5d, 10d, 20d) for all metrics
2. **OI Build Tracking:** Detects position building patterns (sudden vs gradual)
3. **Greeks Time Series:** Full Greek tracking with momentum and acceleration
4. **IV Analysis:** Comprehensive IV metrics including percentiles and momentum

**Historical Data Note:** Data before 2025-09-18 used ±50% strike range; data from 2025-09-18 onwards uses ±20% strike range for consistency with Flow Monitor.

**Migration Note (Oct 19, 2025):** Renamed from `oi_daily`. Column renames: `implied_volatility` → `iv`, `days_to_expiration` → `dte`.

### option_symbol_summary
**Rows:** 19,928
**Purpose:** Daily symbol-level aggregations of open interest data (Option Pipeline Strategy, formerly OID)
**Populated By:** op_symbol_rollup.py
**Coverage:** Universal - all 800 symbols in KLMN universe processed daily

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Stock ticker symbol (Primary Key) |
| trade_date | TEXT | Trading date (Primary Key) |
| close_price | REAL | Closing stock price (2 decimals) |
| total_open_interest | INTEGER | Sum of all contract OI for the symbol |
| total_call_oi | INTEGER | Sum of call contract OI |
| total_put_oi | INTEGER | Sum of put contract OI |
| put_call_ratio | REAL | Put OI / Call OI (4 decimals) |
| oi_balance_text | TEXT | Display text based on ratio thresholds |
| top_call_strike | REAL | Strike price of highest concentration call (2 decimals) |
| top_call_expiration | TEXT | Expiration date of top call concentration |
| top_call_oi | INTEGER | Open interest of top call strike |
| top_call_pct_of_total | REAL | Percent of total call OI for top call (2 decimals) |
| top_call_display | TEXT | Pre-formatted display string |
| top_put_strike | REAL | Strike price of highest concentration put (2 decimals) |
| top_put_expiration | TEXT | Expiration date of top put concentration |
| top_put_oi | INTEGER | Open interest of top put strike |
| top_put_pct_of_total | REAL | Percent of total put OI for top put (2 decimals) |
| top_put_display | TEXT | Pre-formatted display string |
| oi_0_7_days | REAL | Open interest expiring 0-7 days (2 decimals) |
| oi_8_21_days | REAL | Open interest expiring 8-21 days (2 decimals) |
| oi_22_35_days | REAL | Open interest expiring 22-35 days (2 decimals) |
| oi_36_60_days | REAL | Open interest expiring 36-60 days (2 decimals) |
| oi_0_7_days_percent | REAL | Percentage of OI expiring 0-7 days (2 decimals) |
| oi_8_21_days_percent | REAL | Percentage of OI expiring 8-21 days (2 decimals) |
| oi_22_35_days_percent | REAL | Percentage of OI expiring 22-35 days (2 decimals) |
| oi_36_60_days_percent | REAL | Percentage of OI expiring 36-60 days (2 decimals) |
| call_oi_0_7_days | REAL | Call OI expiring 0-7 days (2 decimals) |
| call_oi_8_21_days | REAL | Call OI expiring 8-21 days (2 decimals) |
| call_oi_22_35_days | REAL | Call OI expiring 22-35 days (2 decimals) |
| call_oi_36_60_days | REAL | Call OI expiring 36-60 days (2 decimals) |
| call_oi_0_7_days_percent | REAL | Percentage of call OI expiring 0-7 days (2 decimals) |
| call_oi_8_21_days_percent | REAL | Percentage of call OI expiring 8-21 days (2 decimals) |
| call_oi_22_35_days_percent | REAL | Percentage of call OI expiring 22-35 days (2 decimals) |
| call_oi_36_60_days_percent | REAL | Percentage of call OI expiring 36-60 days (2 decimals) |
| put_oi_0_7_days | REAL | Put OI expiring 0-7 days (2 decimals) |
| put_oi_8_21_days | REAL | Put OI expiring 8-21 days (2 decimals) |
| put_oi_22_35_days | REAL | Put OI expiring 22-35 days (2 decimals) |
| put_oi_36_60_days | REAL | Put OI expiring 36-60 days (2 decimals) |
| put_oi_0_7_days_percent | REAL | Percentage of put OI expiring 0-7 days (2 decimals) |
| put_oi_8_21_days_percent | REAL | Percentage of put OI expiring 8-21 days (2 decimals) |
| put_oi_22_35_days_percent | REAL | Percentage of put OI expiring 22-35 days (2 decimals) |
| put_oi_36_60_days_percent | REAL | Percentage of put OI expiring 36-60 days (2 decimals) |
| deep_itm_call_oi | INTEGER | Deep ITM call OI (delta > 0.8) |
| itm_call_oi | INTEGER | ITM call OI (0.5 < delta <= 0.8) |
| atm_call_oi | INTEGER | ATM call OI (0.4 <= delta <= 0.5) |
| otm_call_oi | INTEGER | OTM call OI (0.2 < delta < 0.4) |
| deep_otm_call_oi | INTEGER | Deep OTM call OI (delta <= 0.2) |
| deep_itm_put_oi | INTEGER | Deep ITM put OI (delta < -0.8) |
| itm_put_oi | INTEGER | ITM put OI (-0.8 <= delta < -0.5) |
| atm_put_oi | INTEGER | ATM put OI (-0.5 <= delta <= -0.4) |
| otm_put_oi | INTEGER | OTM put OI (-0.4 < delta < -0.2) |
| deep_otm_put_oi | INTEGER | Deep OTM put OI (delta >= -0.2) |
| deep_itm_call_pct | REAL | Percentage of total call OI that is deep ITM (2 decimals) |
| itm_call_pct | REAL | Percentage of total call OI that is ITM (2 decimals) |
| atm_call_pct | REAL | Percentage of total call OI that is ATM (2 decimals) |
| otm_call_pct | REAL | Percentage of total call OI that is OTM (2 decimals) |
| deep_otm_call_pct | REAL | Percentage of total call OI that is deep OTM (2 decimals) |
| deep_itm_put_pct | REAL | Percentage of total put OI that is deep ITM (2 decimals) |
| itm_put_pct | REAL | Percentage of total put OI that is ITM (2 decimals) |
| atm_put_pct | REAL | Percentage of total put OI that is ATM (2 decimals) |
| otm_put_pct | REAL | Percentage of total put OI that is OTM (2 decimals) |
| deep_otm_put_pct | REAL | Percentage of total put OI that is deep OTM (2 decimals) |
| option_volume | INTEGER | Total options volume for the symbol |
| call_volume | INTEGER | Total call volume |
| put_volume | INTEGER | Total put volume |
| volume_put_call_ratio | REAL | Put volume / Call volume (4 decimals) |
| call_iv_avg | REAL | Average implied volatility for calls (4 decimals) |
| put_iv_avg | REAL | Average implied volatility for puts (4 decimals) |
| iv_skew | REAL | Put IV - Call IV skew (4 decimals) |
| call_iv_weighted | REAL | Volume-weighted call IV (4 decimals) |
| put_iv_weighted | REAL | Volume-weighted put IV (4 decimals) |
| symbol_iv_percentile_30d | REAL | 30-day IV percentile for symbol (2 decimals) |
| iv_front_month | REAL | Front month IV (7-21 DTE bucket) (4 decimals) |
| iv_30dte | REAL | 30 DTE IV (22-35 DTE bucket) (4 decimals) |
| iv_45dte | REAL | 45 DTE IV (36-50 DTE bucket) (4 decimals) |
| iv_60dte | REAL | 60 DTE IV (51-70 DTE bucket) (4 decimals) |
| total_delta_exposure | REAL | Total delta exposure (sum of all contract deltas × OI) (4 decimals) |
| call_delta_exposure | REAL | Total call delta exposure (4 decimals) |
| put_delta_exposure | REAL | Total put delta exposure (4 decimals) |
| net_delta_exposure | REAL | Net delta exposure (calls - puts) (4 decimals) |
| total_gamma_exposure | REAL | Total gamma exposure (4 decimals) |
| max_gamma_strike | REAL | Strike price with highest gamma concentration (2 decimals) |
| total_theta_exposure | REAL | Total theta exposure (daily decay) (4 decimals) |
| total_vega_exposure | REAL | Total vega exposure (IV sensitivity) (4 decimals) |
| call_vega_exposure | REAL | Total call vega exposure (4 decimals) |
| put_vega_exposure | REAL | Total put vega exposure (4 decimals) |
| net_vega_exposure | REAL | Net vega exposure (calls - puts) (4 decimals) |
| building_contracts_count | INTEGER | Number of contracts showing building activity |
| unwinding_contracts_count | INTEGER | Number of contracts showing unwinding activity |
| avg_bid_ask_spread_pct | REAL | Average bid-ask spread percentage (2 decimals) |
| max_pain_by_friday | REAL | Max pain level for Friday expiration (2 decimals) |
| analysis_timestamp | TEXT | When the rollup calculation was performed |
| contracts_with_data | INTEGER | Number of contracts with complete data |

**Primary Key:** (symbol, trade_date)

**Key Features:**
1. **IV by DTE Bucket:** Primary IV source for system (front_month, 30dte, 45dte, 60dte)
2. **Greek Exposures:** Total delta, gamma, theta, vega exposures across all contracts
3. **Moneyness Distributions:** OI distributions by delta ranges
4. **Max Pain:** Calculated max pain level for Friday expiration
5. **OI Time Distributions:** OI bucketed by DTE ranges (0-7, 8-21, 22-35, 36-60 days)

**Primary IV Source:** As of Oct 16, 2025, this table is the primary IV source for Earnings Intel and other strategies (replaces deprecated `options_symbol_summary`).

**Migration Note (Oct 19, 2025):** Renamed from `oi_symbol_summary`. Streamlined to focus on Option Pipeline metrics.

### earnings_events
**Rows:** 454
**Purpose:** Historical earnings events with trading journal integration
**Populated By:** ei_archive.py (Earnings Intelligence Strategy)

| Column | Type | Description |
|--------|------|-------------|
| event_id | INTEGER | Unique event identifier (Primary Key, Auto-increment) |
| symbol | TEXT | Ticker symbol |
| earnings_date | DATE | Date earnings were reported |
| fiscal_year | INTEGER | Fiscal year |
| fiscal_quarter | INTEGER | Fiscal quarter (1-4) |
| estimated_eps | REAL | Analyst EPS estimate |
| actual_eps | REAL | Actual reported EPS |
| eps_surprise_pct | REAL | EPS surprise percentage |
| earnings_time | TEXT | BMO (before market) or AMC (after market close) |
| source | TEXT | Data source |
| is_backfilled | BOOLEAN | Whether event was backfilled vs live captured |
| created_at | TIMESTAMP | Record creation timestamp |
| notes | TEXT | Trading journal notes |
| tags | TEXT | Comma-separated tags for categorization |
| note_type | TEXT | Note category (observation/idea/trade/result) |
| sentiment | TEXT | Sentiment label (bullish/bearish/neutral) |

**Primary Key:** event_id

**Indexes:**
- `idx_earnings_events_fiscal` ON (fiscal_year, fiscal_quarter)
- `idx_earnings_events_symbol_date` ON (symbol, earnings_date)
- `idx_earnings_events_date` ON (earnings_date)
- `idx_earnings_events_symbol` ON (symbol)

**Key Features:**
1. **Trading Journal:** Notes, tags, note_type, sentiment fields for manual annotations
2. **EPS Surprise Tracking:** Estimated vs actual EPS with surprise percentage
3. **Timing Classification:** BMO/AMC earnings timing
4. **Backfill Support:** Distinguishes historical vs live-captured events

### earnings_moves
**Rows:** 9,296
**Purpose:** Price movements and IV changes post-earnings
**Populated By:** ei_move_calculator.py (Earnings Intelligence Strategy)
**Parent Table:** earnings_events (via event_id foreign key)

| Column | Type | Description |
|--------|------|-------------|
| move_id | INTEGER | Unique move record identifier (Primary Key, Auto-increment) |
| event_id | INTEGER | Foreign key to earnings_events |
| symbol | TEXT | Ticker symbol |
| move_1day_pct | REAL | 1-day price move percentage |
| move_2day_pct | REAL | 2-day price move percentage |
| move_3day_pct | REAL | 3-day price move percentage |
| move_5day_pct | REAL | 5-day price move percentage |
| max_intraday_move_pct | REAL | Maximum intraday move percentage |
| move_direction | TEXT | UP or DOWN |
| iv_buildup_pct | REAL | IV increase in days before earnings |
| iv_collapse_pct | REAL | IV decrease after earnings (IV crush) |
| iv_recovery_pct | REAL | IV recovery in days after earnings |
| iv_crush_severity | TEXT | Classification: mild/moderate/severe |
| expected_move_pct | REAL | Expected move from straddle pricing |
| move_vs_expected_pct | REAL | Actual move vs expected move |
| calculated_at | TIMESTAMP | When calculation was performed |

**Primary Key:** move_id

**Indexes:**
- `idx_moves_crush_severity` ON (iv_crush_severity)
- `idx_moves_direction` ON (move_direction)
- `idx_moves_symbol` ON (symbol)
- `idx_moves_event` ON (event_id)

**Key Features:**
1. **Multi-Period Moves:** 1d, 2d, 3d, 5d price movement tracking
2. **IV Crush Analysis:** Tracks IV buildup, collapse, and recovery
3. **Expected vs Actual:** Compares actual move to straddle-implied expected move
4. **Severity Classification:** Categorizes IV crush severity

### earnings_snapshots
**Rows:** 20,419
**Purpose:** Time series IV and price snapshots around earnings (T-7 to T+3)
**Populated By:** ei_snapshot_collector.py (Earnings Intelligence Strategy)
**Parent Table:** earnings_events (via event_id foreign key, populated by writer + nightly backfill in ei_main.py sub-step 3.5)

| Column | Type | Description |
|--------|------|-------------|
| snapshot_id | INTEGER | Unique snapshot identifier (Primary Key, Auto-increment) |
| event_id | INTEGER | Foreign key to earnings_events. NULL for pre-earnings rows whose event has not yet archived. Backfilled nightly. |
| symbol | TEXT | Ticker symbol (can be primary or peer) |
| snapshot_date | DATE | Date the snapshot was captured |
| earnings_date | DATE | Earnings date AS OF snapshot_date (estimate at capture). Drifts with yfinance revisions. **Not a join key** — join to `earnings_events` via `event_id`, or to `earnings_upcoming`/other tables on `(symbol)` with a fuzzy date window. See policy note in `ei_snapshot_collector.py` docstring. |
| days_from_earnings | INTEGER | Days before/after earnings (negative = before) |
| snapshot_type | TEXT | primary_symbol or peer_symbol |
| close_price | REAL | Closing price |
| volume | INTEGER | Trading volume |
| iv_30dte | REAL | 30-day IV (from option_symbol_summary) |
| iv_front_month | REAL | Front month IV (7-21 DTE) |
| iv_45dte | REAL | 45-day IV |
| total_open_interest | INTEGER | Total OI across all contracts |
| put_call_ratio | REAL | Put/Call OI ratio |
| is_primary_symbol | BOOLEAN | True if primary earnings symbol |
| created_at | TIMESTAMP | Record creation timestamp |

**Primary Key:** snapshot_id

**Indexes:**
- `idx_snapshots_type` ON (snapshot_type)
- `idx_snapshots_days_from` ON (days_from_earnings)
- `idx_snapshots_symbol_date` ON (symbol, snapshot_date)
- `idx_snapshots_symbol` ON (symbol)
- `idx_snapshots_event` ON (event_id)

**Key Features:**
1. **Time Series Coverage:** T-7 to T+3 snapshots around earnings dates
2. **Multi-Symbol Support:** Captures both primary and peer symbol data
3. **IV Term Structure:** Multiple DTE buckets for IV tracking
4. **OI Tracking:** Monitors open interest changes around earnings

### earnings_sector_effects
**Rows:** 0
**Purpose:** Sector sympathy and arbitrage opportunities based on peer earnings
**Populated By:** ei_sector_analyzer.py (Earnings Intelligence Strategy)
**Status:** System implemented but not yet analyzing sector effects (awaiting next earnings cycle or manual backfill)
**Parent Table:** earnings_events (via primary_event_id foreign key)

| Column | Type | Description |
|--------|------|-------------|
| effect_id | INTEGER | Unique effect record identifier (Primary Key, Auto-increment) |
| primary_event_id | INTEGER | Foreign key to earnings_events (company that reported) |
| primary_symbol | TEXT | Symbol that reported earnings |
| peer_symbol | TEXT | Peer symbol being analyzed |
| industry | TEXT | Industry classification |
| primary_iv_buildup_pct | REAL | Primary symbol IV buildup before earnings |
| peer_iv_buildup_pct | REAL | Peer symbol IV buildup (sympathy effect) |
| iv_arbitrage_delta | REAL | Difference in IV buildup (opportunity indicator) |
| primary_move_pct | REAL | Primary symbol price move post-earnings |
| peer_move_pct | REAL | Peer symbol price move (sympathy move) |
| correlation_strength | REAL | Historical correlation between symbols |
| sample_size | INTEGER | Number of historical events in correlation |
| expected_peer_move_pct | REAL | Expected peer move based on correlation |
| actual_vs_expected_diff | REAL | Actual peer move vs expected |
| arbitrage_quality | TEXT | Classification: high/medium/low |
| calculated_at | TIMESTAMP | When calculation was performed |

**Primary Key:** effect_id

**Indexes:**
- `idx_sector_effects_event` ON (primary_event_id)
- `idx_sector_effects_quality` ON (arbitrage_quality)
- `idx_sector_effects_industry` ON (industry)
- `idx_sector_effects_peer` ON (peer_symbol)
- `idx_sector_effects_primary` ON (primary_symbol)

**Key Features:**
1. **Sympathy Tracking:** Identifies peer symbols moving with earnings reports
2. **IV Arbitrage Detection:** Finds peers with mispriced IV relative to primary
3. **Correlation-Based Predictions:** Uses historical correlation for expected moves
4. **Quality Scoring:** Ranks arbitrage opportunities by quality

### earnings_upcoming
**Rows:** 368
**Purpose:** Upcoming earnings dates with expected move calculations
**Populated By:** ei_calendar.py (Earnings Intelligence Strategy)

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Ticker symbol (Primary Key) |
| earnings_date | DATE | Date earnings will be reported |
| earnings_days_ahead | INTEGER | Days until earnings |
| expected_move_pct | REAL | Expected move from IV formula (fallback) |
| straddle_expected_move_pct | REAL | Straddle-based expected move (primary) |
| historical_avg_move_pct | REAL | Recent 6-quarter average historical move (signal driver, Apr 2026) |
| historical_avg_move_alltime_pct | REAL | All-time average historical move (transparency) |
| historical_quarters_used | INTEGER | Quarters in recent average (1-6, data depth indicator) |
| move_difference_pct | REAL | Difference between expected and historical |
| relative_underpricing_pct | REAL | (recent_6Q - expected) / expected * 100 |
| earnings_play_signal | TEXT | Signal: AVOID/NEUTRAL/WATCH/BUY/STRONG BUY |
| earnings_time | TEXT | BMO or AMC |
| earnings_alert | BOOLEAN | Whether to alert on this earnings |
| eps_estimate | REAL | Consensus EPS estimate |
| revenue_estimate | REAL | Consensus revenue estimate |
| updated_at | TEXT | Last update timestamp |

**Primary Key:** symbol

**Key Features:**
1. **Expected Move Calculation:** Straddle-based expected move (primary), IV-based (fallback)
2. **Historical Comparison:** Recent 6Q average vs market expectation (configurable via `earnings_play.recent_quarters`)
3. **Signal Classification:** Identifies underpriced earnings opportunities
4. **Transparency:** All-time average and quarter count stored alongside recent average
4. **Alert Flags:** Marks high-priority earnings events

### market_daily_summary
**Rows:** 57
**Purpose:** Daily market environment metrics with regime classification
**Populated By:** Market data collection pipeline

| Column | Type | Description |
|--------|------|-------------|
| trade_date | DATE | Trading date (Primary Key) |
| regime_classification | TEXT | Market regime (trending/choppy/volatile) |
| regime_multiplier | REAL | Regime adjustment multiplier |
| market_direction | TEXT | Bull or Bear |
| advancing_stocks | INTEGER | Number of advancing stocks |
| declining_stocks | INTEGER | Number of declining stocks |
| advancing_volume | REAL | Volume in advancing stocks |
| declining_volume | REAL | Volume in declining stocks |
| new_highs | INTEGER | Stocks hitting new highs |
| new_lows | INTEGER | Stocks hitting new lows |
| spy_open | REAL | SPY opening price |
| spy_high | REAL | SPY high price |
| spy_low | REAL | SPY low price |
| spy_close | REAL | SPY closing price |
| spy_volume | REAL | SPY volume |
| spy_change_percent | REAL | SPY daily change percentage |
| vix_open | REAL | VIX opening value |
| vix_high | REAL | VIX high value |
| vix_low | REAL | VIX low value |
| vix_close | REAL | VIX closing value |
| vix_volume | REAL | VIX volume |
| vix_change_percent | REAL | VIX daily change percentage |
| qqq_close | REAL | QQQ closing price |
| qqq_change_percent | REAL | QQQ daily change percentage |
| iwm_close | REAL | IWM closing price |
| iwm_change_percent | REAL | IWM daily change percentage |
| xlf_close | REAL | XLF (Financial) closing price |
| xlf_change_percent | REAL | XLF daily change percentage |
| xle_close | REAL | XLE (Energy) closing price |
| xle_change_percent | REAL | XLE daily change percentage |
| xlk_close | REAL | XLK (Technology) closing price |
| xlk_change_percent | REAL | XLK daily change percentage |
| xlv_close | REAL | XLV (Healthcare) closing price |
| xlv_change_percent | REAL | XLV daily change percentage |
| xli_close | REAL | XLI (Industrial) closing price |
| xli_change_percent | REAL | XLI daily change percentage |
| xlp_close | REAL | XLP (Consumer Staples) closing price |
| xlp_change_percent | REAL | XLP daily change percentage |
| xly_close | REAL | XLY (Consumer Discretionary) closing price |
| xly_change_percent | REAL | XLY daily change percentage |
| xlu_close | REAL | XLU (Utilities) closing price |
| xlu_change_percent | REAL | XLU daily change percentage |
| xlb_close | REAL | XLB (Materials) closing price |
| xlb_change_percent | REAL | XLB daily change percentage |
| xlre_close | REAL | XLRE (Real Estate) closing price |
| xlre_change_percent | REAL | XLRE daily change percentage |
| tlt_close | REAL | TLT (Treasuries) closing price |
| tlt_change_percent | REAL | TLT daily change percentage |
| gld_close | REAL | GLD (Gold) closing price |
| gld_change_percent | REAL | GLD daily change percentage |
| uup_close | REAL | UUP (Dollar) closing price |
| uup_change_percent | REAL | UUP daily change percentage |
| created_at | TEXT | Record creation timestamp |

**Primary Key:** trade_date

**Indexes:**
- `idx_market_daily_summary_date_desc` ON (trade_date DESC)

**Key Features:**
1. **Regime Classification:** Trending/Choppy/Volatile market regimes
2. **Market Direction:** Bull/Bear classification
3. **Breadth Indicators:** Advancing/declining stocks and volume
4. **Sector Performance:** All 11 SPDR sector ETFs tracked
5. **Multi-Asset Coverage:** Equity indices, VIX, bonds, gold, dollar

### symbol_metadata
**Rows:** 757
**Purpose:** Symbol reference data and sector/industry classifications
**Populated By:** Symbol universe management tools

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Stock ticker symbol (Primary Key) |
| company_name | TEXT | Full company name |
| sector | TEXT | Broad sector classification (e.g., Technology, Healthcare) |
| industry | TEXT | Specific industry classification (e.g., Airlines, Asset Management) |
| is_etf | BOOLEAN | Whether symbol is an ETF |
| market_cap_category | TEXT | Market cap size category |
| liquidity_tier | TEXT | Liquidity classification |
| beta | REAL | Stock beta (volatility vs market) |
| options_available | BOOLEAN | Whether options trading is available |
| updated_at | TEXT | Last metadata update timestamp |
| news_last_fetched | TIMESTAMP | Last news fetch timestamp |
| archive_db | TEXT | Archive database routing (e.g., 'airlines', 'technology', 'asset_management') |
| universe_tier | TEXT | Universe membership: fm_universe, daily_only, purgatory, removed |
| protected_reason | TEXT | Protection category: adr, airline, cherry_pick (NULL if none) |
| tier_changed_date | DATE | Date when universe_tier was last changed |
| notes | TEXT | Free-form notes (cherry pick reason, removal context, etc.) |

**Primary Key:** symbol

**Key Features:**
1. **Archive Routing:** `archive_db` column determines which sector archive database receives the symbol's data
2. **Industry-Specific Archives:** Supports industry breakouts (airlines, asset_management) separate from broad sectors
3. **13 Archive Databases:** 11 sector-based + 2 industry-specific (airlines split from industrials, asset_management split from financial_services)
4. **Universe Source of Truth (PRD 0013):** `universe_tier` replaces Python list literals as the authoritative source for which symbols belong to FM_UNIVERSE vs DAILY_ONLY. `get_specialty_list()` queries this column.

**Archive Routing Logic:**
- Industry-specific: Airlines symbols → `airlines.db`, Asset Management symbols → `asset_management.db`
- Sector splits: Technology → `semiconductors.db` / `software.db` / `technology.db` by industry; Consumer Cyclical → `retail.db` / `travel_leisure.db` / `consumer_cyclical.db` by industry
- Sector-based: All other symbols route by normalized sector name (e.g., Healthcare → `healthcare.db`)

**Migration Notes:**
- (Oct 28, 2025) Added `archive_db` column to support sector-based archival system with industry-specific overrides.
- (Apr 16, 2026) PRD 0013: Added `universe_tier`, `protected_reason`, `tier_changed_date`, `notes` columns. Populated from Python list literals via `data/health/migrate_universe_to_db.py`.

### symbol_lifecycle_events
**Rows:** 0 (new table, grows over time)
**Purpose:** Audit trail for all symbol universe changes (onboarding, offboarding, purgatory moves, suspect detection)
**Populated By:** `tools/lifecycle/audit.py`, `tools/symbol_lifecycle.py`, Phase 6.2 health check

| Column | Type | Description |
|--------|------|-------------|
| event_id | INTEGER | Auto-incrementing primary key |
| symbol | TEXT NOT NULL | Stock ticker symbol (indexed) |
| event_type | TEXT NOT NULL | Event classification (see below) |
| event_date | DATE NOT NULL | Trading day of event (indexed) |
| event_timestamp | TEXT NOT NULL | Full timestamp of event |
| tier | TEXT | Universe tier at time of event |
| reason | TEXT | Free-form reason text |
| operator | TEXT NOT NULL | Who triggered: human, health_check, collector |
| metadata_json | TEXT | JSON blob with full context |

**Event Types:** `onboarded`, `offboarded`, `purgatory_added`, `purgatory_restored`, `suspect_detected`, `suspect_classified`, `rename_from`, `rename_to`

**Key Features:**
1. **Full Audit Trail:** Every symbol decision is recorded with timestamp, reason, and operator
2. **Suspect Tracking:** Health check flags symbols missing data; `get_pending_suspects()` finds unresolved ones
3. **Idempotent Logging:** `is_suspect_already_logged()` prevents duplicate suspect events

**Added:** Apr 16, 2026 (PRD 0013 — Symbol Lifecycle Management)

### historical_prices
**Rows:** 48,713
**Purpose:** Daily OHLC price data for all symbols
**Populated By:** Price data collection pipeline

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Ticker symbol (Primary Key) |
| trade_date | DATE | Trading date (Primary Key) |
| open_price | REAL | Opening price |
| high_price | REAL | High price |
| low_price | REAL | Low price |
| close_price | REAL | Closing price |
| adj_close_price | REAL | Adjusted closing price |
| volume | REAL | Trading volume |
| change_amount | REAL | Dollar change |
| change_percent | REAL | Percentage change |
| vwap | REAL | Volume-weighted average price |
| created_at | TEXT | Record creation timestamp |

**Primary Key:** (symbol, trade_date)

**Key Features:**
1. **Complete OHLCV Data:** Full daily bar information
2. **Adjusted Prices:** Includes split/dividend adjusted close
3. **Pre-computed Metrics:** Change amount, percentage, VWAP

### news_articles
**Rows:** 5,165
**Purpose:** News articles with overall sentiment scoring
**Populated By:** News collection pipeline (Alpha Vantage API)

| Column | Type | Description |
|--------|------|-------------|
| article_url | TEXT | Unique article URL (Primary Key) |
| title | TEXT | Article title |
| summary | TEXT | Article summary/excerpt |
| source | TEXT | News source |
| authors | TEXT | Article authors |
| time_published | TEXT | Publication timestamp |
| article_date | TEXT | Publication date |
| time_collected | TEXT | When article was collected |
| overall_sentiment_score | REAL | Overall sentiment score (-1 to 1) |
| overall_sentiment_label | TEXT | Overall sentiment label |
| symbols_mentioned | TEXT | Comma-separated list of symbols mentioned |
| created_at | TIMESTAMP | Record creation timestamp |

**Primary Key:** article_url

**Key Features:**
1. **Multi-Symbol Coverage:** Articles can mention multiple symbols
2. **Sentiment Scoring:** Both numeric score and label classification
3. **Source Tracking:** News source and author attribution

### news_symbol_sentiment
**Rows:** 12,173
**Purpose:** Symbol-specific sentiment scores from news articles
**Populated By:** News collection pipeline (Alpha Vantage API)
**Parent Table:** news_articles (via article_url foreign key)

| Column | Type | Description |
|--------|------|-------------|
| article_url | TEXT | Foreign key to news_articles (Primary Key) |
| symbol | TEXT | Ticker symbol (Primary Key) |
| article_date | TEXT | Publication date |
| relevance_score | REAL | How relevant article is to symbol (0-1) |
| symbol_sentiment_score | REAL | Sentiment score for this symbol (-1 to 1) |
| symbol_sentiment_label | TEXT | Sentiment label for this symbol |
| time_collected | TEXT | When sentiment was collected |
| created_at | TIMESTAMP | Record creation timestamp |
| topics_collected | TEXT | Topics/tags associated with article |

**Primary Key:** (article_url, symbol)

**Indexes:**
- `idx_symbol_date` ON (symbol, article_date)
- `idx_news_symbol_date` ON (symbol, article_date)
- `idx_symbol_article_date` ON (symbol, article_date)

**Key Features:**
1. **Symbol-Specific Scores:** Different sentiment for each symbol mentioned
2. **Relevance Weighting:** Scores weighted by relevance to symbol
3. **Topic Tracking:** Associated topics/themes from article

### symbol_baselines
**Rows:** 754
**Purpose:** Statistical baselines for volume and flow metrics
**Populated By:** Baseline calculation pipeline

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT | Ticker symbol (Primary Key) |
| volume_mean | REAL | Mean volume |
| volume_std | REAL | Volume standard deviation |
| volume_total_daily | REAL | Total daily volume |
| sample_size | INTEGER | Number of days in baseline |
| vol_oi_mean | REAL | Mean volume/OI ratio |
| vol_oi_std | REAL | Volume/OI ratio standard deviation |
| last_updated | TEXT | Last update timestamp |
| created_at | TEXT | Record creation timestamp |

**Primary Key:** symbol

**Key Features:**
1. **Statistical Baselines:** Mean and standard deviation for anomaly detection
2. **Volume/OI Ratios:** Baseline for flow percentage calculations
3. **Sample Size Tracking:** Number of observations in baseline

### industry_peer_mappings
**Rows:** 742
**Purpose:** Industry-based peer relationships for earnings sympathy analysis
**Populated By:** Peer mapping configuration

| Column | Type | Description |
|--------|------|-------------|
| mapping_id | INTEGER | Unique mapping identifier (Primary Key, Auto-increment) |
| industry | TEXT | Industry classification |
| symbol | TEXT | Ticker symbol |
| is_industry_leader | BOOLEAN | Whether symbol is industry leader |
| peer_type | TEXT | Type of peer relationship |
| weight | REAL | Peer weighting factor |
| is_active | BOOLEAN | Whether mapping is currently active |
| notes | TEXT | Additional notes |
| created_at | TIMESTAMP | Record creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

**Primary Key:** mapping_id

**Indexes:**
- `idx_peer_mappings_active` ON (is_active)
- `idx_peer_mappings_leader` ON (is_industry_leader)
- `idx_peer_mappings_symbol` ON (symbol)
- `idx_peer_mappings_industry` ON (industry)

**Key Features:**
1. **Industry Grouping:** Symbols grouped by industry for sympathy analysis
2. **Leader Identification:** Marks industry leaders whose earnings move peers
3. **Weighted Relationships:** Weight factors for correlation strength
4. **Active Management:** Can disable/enable mappings without deletion

### alert_contract_tracking
**Rows:** 1,283
**Purpose:** Profitability tracking metadata for flow alert contracts
**Populated By:** fm_evaluator.py (Flow Monitor Strategy)
**Parent Table:** flow_alerts (via alert_id foreign key)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Unique identifier (Primary Key, Auto-increment) |
| alert_id | INTEGER | Foreign key to flow_alerts |
| symbol | TEXT | Ticker symbol |
| strike | REAL | Strike price |
| expiration_date | TEXT | Option expiration date |
| option_type | TEXT | CALL or PUT |
| tracking_start_date | TEXT | When tracking began |
| tracking_end_date | TEXT | When tracking ended |
| last_price_update | TEXT | Last price data fetch timestamp |
| tracking_status | TEXT | Status (active/complete/failed) |
| successful_collections | INTEGER | Number of successful price fetches |
| failed_collections | INTEGER | Number of failed price fetches |
| alert_timestamp | TEXT | When alert was generated |
| scan_timestamp | TEXT | When scan was performed |

**Primary Key:** id

**Key Features:**
1. **Collection Monitoring:** Tracks success/failure rates for price data fetching
2. **Lifecycle Tracking:** From tracking start through completion
3. **Status Management:** Active, complete, or failed tracking states

---

*For historical table schemas and deprecated tables, see `datalake_schema_2025-10-16.md`*
