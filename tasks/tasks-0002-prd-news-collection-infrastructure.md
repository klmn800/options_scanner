# Task List: News Collection Infrastructure

**PRD:** 0002-prd-news-collection-infrastructure.md
**Created:** 2025-10-04
**Status:** In Progress

---

## Relevant Files

### New Files to Create
- `strategies/news_collector/nc_main.py` - Main entry point for news collection module
- `strategies/news_collector/nc_config.py` - Configuration loader (similar to fm_config.py)
- `strategies/news_collector/nc_collector.py` - CTI pipeline for news collection with intelligent quota management
- `strategies/news_collector/nc_storage.py` - Database operations for news tables
- `strategies/news_collector/logs/` - Directory for collection logs

### Existing Files to Reference/Modify
- `core/alphavantage_api.py` - Alpha Vantage API client with rate limiting (already exists, will use)
- `tools/news_collector.py` - Existing news collection tool (reference for patterns)
- `data/datalake.db` - Tables: `news_articles`, `news_symbol_sentiment` (already exist)
- `core/symbols_klmn800.py` - KLMN 800 symbol universe (already exists)
- `morning_view/morning_views.py` - Consumer of news data (verify compatibility)
- `config.json` - Root configuration file (add news_collector section)

### Database Tables (Already Exist)
- `news_articles` - Stores article metadata (8,186 rows currently)
- `news_symbol_sentiment` - Stores per-symbol sentiment scores (22,462 rows currently)

---

## Tasks

- [ ] 1.0 Project Structure & Configuration Setup
- [ ] 2.0 Core Collection Logic with Intelligent Quota Management
- [ ] 3.0 Database Storage Integration
- [ ] 4.0 Main Orchestrator & Logging
- [ ] 5.0 Testing & Validation
- [ ] 6.0 Documentation & Integration

---

## Tasks

### 1.0 Project Structure & Configuration Setup
- [ ] 1.1 Create `strategies/news_collector/` directory structure with `__init__.py`
- [ ] 1.2 Create `strategies/news_collector/logs/` directory for collection logs
- [ ] 1.3 Create `nc_config.py` following `fm_config.py` pattern (config loader, path resolution, multi-key support)
- [ ] 1.4 Add 5 Alpha Vantage API keys to `credentials.json` as array (125 calls/day total)
- [ ] 1.5 Add `news_collector` section to root `config.json` with allocation: `{"tier1": 25, "tier2": 75, "tier3": 25}`
- [ ] 1.6 Add `news_last_fetched TIMESTAMP` column to `symbol_metadata` table via ALTER TABLE
- [ ] 1.7 Verify database schema for `news_articles` and `news_symbol_sentiment` tables (already exist, just document)

### 2.0 Core Collection Logic with Three-Tier Priority System
- [ ] 2.1 Create `nc_collector.py` with `NewsCollector` class (reuse patterns from `daily_analysis_symbol_news.py`)
- [ ] 2.2 Implement `get_tier1_symbols()` - query `v_morning_watchlist` for active watchlist symbols (Tier 1)
- [ ] 2.3 Implement `get_tier2_symbols()` - load KLMN_PREFERRED + AIRLINE_PLAY_SYMBOLS from `symbols_klmn800.py` (Tier 2: ~110 symbols)
- [ ] 2.4 Implement `get_tier3_symbols()` - get remaining KLMN_800 symbols not in Tier 1 or 2 (Tier 3: ~690 symbols)
- [ ] 2.5 Implement `calculate_quota_allocation()` - split 125 calls: 25 watchlist + 75 preferred + 25 universe (configurable)
- [ ] 2.6 Implement `rotate_tier_symbols()` - rotate through Tier 2/3 based on `symbol_metadata.news_last_fetched` (staleness priority)
- [ ] 2.7 Implement `collect_symbol_news()` - wrapper for `AlphaVantageNewsClient.get_symbol_news()` with 14-day lookback
- [ ] 2.8 Implement multi-key rotation - round-robin through 5 API keys, track usage per key (25 calls/day max each)
- [ ] 2.9 Add per-key usage tracking - prevent exceeding 25 calls/day on any single key
- [ ] 2.10 Support ad-hoc collection modes (`--symbol`, `--symbols`, `--tier`, `--watchlist-only`, `--max-age-days`)

### 3.0 Database Storage Integration
- [ ] 3.1 Create `nc_storage.py` with `NewsStorage` class for database operations
- [ ] 3.2 Implement `store_articles()` - insert into `news_articles` table (reuse from `av_news_symbol.py`)
- [ ] 3.3 Implement `store_symbol_sentiment()` - insert into `news_symbol_sentiment` table with decimal formatting
- [ ] 3.4 Implement `get_last_fetched()` - query `symbol_metadata.news_last_fetched` for rotation staleness
- [ ] 3.5 Implement `update_last_fetched()` - update `symbol_metadata.news_last_fetched` after successful fetch
- [ ] 3.6 Implement `cleanup_old_news()` - delete articles older than 30 days from both tables
- [ ] 3.7 Add duplicate prevention logic - use `INSERT OR IGNORE` on `article_url` primary key
- [ ] 3.8 Apply decimal formatter to `sentiment_score` and `relevance_score` before storage

### 4.0 Main Orchestrator & Logging
- [ ] 4.1 Create `nc_main.py` entry point with comprehensive argparse options
- [ ] 4.2 Add argparse flags: `--dry-run`, `--watchlist-only`, `--tier [preferred|universe]`, `--symbol`, `--symbols`, `--limit`, `--max-age-days`
- [ ] 4.3 Implement main execution flow: cleanup old news → load config → determine mode → allocate quota → collect news → log results
- [ ] 4.4 Add comprehensive logging to `strategies/news_collector/logs/news_collection_YYYY-MM-DD.log`
- [ ] 4.5 Implement quota breakdown reporting by tier (Tier 1: X calls, Tier 2: Y calls, Tier 3: Z calls, Total articles: N)
- [ ] 4.6 Add per-key API usage statistics (Key 1: 23/25, Key 2: 25/25, etc.)
- [ ] 4.7 Display rotation coverage percentage (e.g., "Tier 2: 73/110 symbols covered in last 2 days")
- [ ] 4.8 Implement loud error handling - print errors to console in red, continue on symbol failures, summary at end
- [ ] 4.9 Add dry-run mode showing allocation plan and next symbols to fetch without making API calls

### 5.0 Testing & Validation
- [ ] 5.1 Test with `--dry-run` flag to verify three-tier quota allocation (25/75/25 split across 5 API keys)
- [ ] 5.2 Run real collection with `--limit 5` to test database storage and API integration
- [ ] 5.3 Test ad-hoc modes: `--symbol DAL`, `--symbols DAL,UAL,AAL`, `--tier preferred`, `--watchlist-only`
- [ ] 5.4 Verify Morning Views shows updated news sentiment after collection (`python morning_view/morning_views.py`)
- [ ] 5.5 Test Tier 2 rotation - run daily for 2 days, verify all KLMN_PREFERRED symbols get coverage (1.5 day rotation cycle)
- [ ] 5.6 Verify decimal formatting on stored sentiment scores (query database, check precision)
- [ ] 5.7 Test error handling - simulate API failure, verify graceful degradation
- [ ] 5.8 Validate no duplicate articles in database after multiple runs
- [ ] 5.9 Test rotation staleness - verify symbols with oldest `last_fetched` get priority
- [ ] 5.10 Verify multi-key rotation - confirm each key stays under 25 calls/day, round-robin distribution works
- [ ] 5.11 Test news pruning - verify articles older than 30 days are deleted from both `news_articles` and `news_symbol_sentiment`

### 6.0 Documentation & Integration
- [ ] 6.1 Update `CLAUDE.md` with news_collector module usage and commands
- [ ] 6.2 Add docstrings to all classes and functions following existing patterns
- [ ] 6.3 Document quota allocation strategy in `nc_config.py` comments
- [ ] 6.4 Create example `config.json` section for news_collector settings
- [ ] 6.5 Add integration notes for future `main.py` orchestrator scheduling
- [ ] 6.6 Document Alpha Vantage sentiment score scale in code comments (investigate and document actual range)

---

## Implementation Notes

### Code Reuse Opportunities
- **`daily_analysis_symbol_news.py`**: Contains fully working collection logic, strategic allocation, priority scoring, and database storage
- **`av_news_symbol.py`**: Simpler backfill pattern, good reference for minimal implementation
- **`core/alphavantage_api.py`**: Already has rate limiting, caching, and API client - just use it
- **Flow Monitor patterns**: Use `fm_config.py` and `fm_main.py` as templates for structure

### Key Differences from Existing Code
- **Three-tier priority system**: Watchlist (Tier 1) → KLMN_PREFERRED + Airlines (Tier 2) → Full KLMN 800 (Tier 3)
- **Tier 2 focus**: ~110 preferred symbols under $65 with alert history get 75 API calls/day (complete rotation every ~1.5 days)
- **Multi-key API rotation**: 5 Alpha Vantage keys with round-robin distribution (125 calls/day total)
- **Staleness-based rotation**: Track `last_fetched` per symbol, prioritize symbols with oldest news data
- **Ad-hoc collection**: Support manual collection by symbol, tier, or watchlist-only
- **Configurable quota split**: 25/75/25 allocation between tiers (adjustable in config.json)
- **News pruning**: Automatic deletion of articles older than 30 days from both tables
- **Standalone operation**: No dependency on daily_analysis orchestrator

### Database Schema (Already Exists)
- **`news_articles`**: 8,186 rows, primary key = `article_url`
- **`news_symbol_sentiment`**: 22,462 rows, composite primary key = `(article_url, symbol)`
- **No schema changes needed** - existing tables are perfect

### Decimal Policy Compliance
- `sentiment_score`: 2 decimal places (percentage-like score)
- `relevance_score`: 2 decimal places (confidence metric)
- Use `tools/decimal_formatter.py` before all database writes
