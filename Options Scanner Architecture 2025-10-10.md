# Options Scanner Full Architecture - October 2025

## Overview
The Options Scanner is a comprehensive multi-strategy options analysis system centered around a datalake database. The system includes standalone strategy modules, AI-powered analysis engines, a daily analysis orchestrator, and multiple AI consultation systems for market intelligence.

## Core Design Principles
Each strategy module is self-contained with its own:
- Data collection logic (no shared collectors)
- Progress tracking (simple logging, not complex threading)
- Configuration management (module-specific config sections)
- Database operations (direct SQL, no abstraction layers)
- Performance evaluation system

The system leverages AI at multiple levels:
- AI Orchestrator for safe, monitored AI interactions
- Oracle system for natural language database queries
- AI Council for multi-model consensus analysis
- Morning View with AI-powered insights

## Actual File Structure

```
options_scanner/                       # Project root (proper Python package)
│
├── pyproject.toml                     # Python package configuration
├── config.json                        # Global configuration
├── credentials.json                   # API keys and credentials
├── main.py                            # Primary orchestrator - daily trading cycles
├── __init__.py files throughout       # Package structure support
│
├── strategies/                        # Trading Strategy Modules
│   ├── flow_monitor/                  # Volume flow detection strategy
│   │   ├── fm_main.py                 # CLI & process coordination
│   │   ├── fm_config.py               # Configuration management
│   │   ├── fm_storage.py              # Database operations
│   │   ├── fm_collector.py            # Data collection (20min cycles)
│   │   ├── fm_analyzer.py             # Z-scoring & pattern analysis
│   │   ├── fm_alerts.py               # Alert generation & delivery
│   │   ├── fm_baseline_generator.py   # Statistical baseline calculations
│   │   ├── fm_symbol_rollup.py        # Daily summary aggregations
│   │   ├── fm_health_reporter.py      # Health and performance statistics
│   │   ├── fm_performance_tracker.py  # Performance tracking utilities
│   │   ├── fm_social_notifier.py      # Social media integration
│   │   ├── cache/                     # Local API response caching
│   │   ├── logs/                      # Strategy-specific logs
│   │   └── evaluation/                # Alert performance system
│   │       ├── fm_evaluator.py        # Alert performance tracking
│   │       ├── fm_backfill_evaluator.py # Historical performance analysis
│   │       ├── evaluation_config.py   # Evaluation configuration
│   │       ├── evaluation_reports.py  # Performance reporting
│   │       ├── run_daily_evaluation.py # Automated evaluation runner
│   │       ├── backfill_alert_performance.py # Backfill system
│   │       └── logs/                  # Evaluation system logs
│   │
│   ├── oi_delta/                      # Open Interest Delta analysis strategy
│   │   ├── oid_main.py                # CLI & process coordination
│   │   ├── oid_config.py              # Configuration management
│   │   ├── oid_storage.py             # Database operations
│   │   ├── oid_collector.py           # Data collection and concentration analysis
│   │   ├── oid_analyzer.py            # OI delta analysis & pattern detection
│   │   ├── oid_symbol_rollup.py       # OI symbol-level summary aggregations
│   │   ├── oid_health_reporter.py     # Health and performance statistics
│   │   ├── oid_universe.py            # Symbol universe management
│   │   ├── oid_timing_calculator.py   # Timing and scheduling logic
│   │   ├── cache/                     # Local API response caching
│   │   └── logs/                      # Strategy-specific logs
│   │
│   ├── earnings_play/                 # Earnings intelligence system
│   │   ├── ep_main.py                 # CLI & orchestration
│   │   ├── ep_fetch_upcoming.py       # Upcoming earnings calendar
│   │   ├── ep_collector.py            # Data collection coordination
│   │   ├── ep_snapshot_collector.py   # IV/price time series (T-7 to T+3)
│   │   ├── ep_post_earnings_calc.py   # Post-earnings calculations
│   │   ├── ep_moves_historical.py     # Historical earnings moves
│   │   ├── ep_moves_upcoming.py       # Expected move calculations
│   │   ├── ep_arbitrage_scanner.py    # Sector sympathy opportunities
│   │   ├── ep_populate_peer_mappings.py # Industry peer relationships
│   │   ├── ep_backfill_events.py      # Event archive backfill
│   │   ├── ep_backfill_moves.py       # Moves backfill
│   │   └── MANUAL_OPERATIONS.md       # Trading journal and manual tasks
│   │
│   ├── news_collector/                # News sentiment strategy
│   │   ├── nc_main.py                 # CLI & process coordination
│   │   ├── nc_config.py               # Configuration management
│   │   ├── nc_storage.py              # Database operations
│   │   ├── nc_collector.py            # News data collection
│   │   └── logs/                      # Strategy-specific logs
│   │
│   ├── airline_play/                  # Airline-specific tracking (experimental)
│   │   ├── airline_config.py          # Configuration
│   │   ├── ap_symbol_tracking.py      # Symbol tracking
│   │   ├── ap_options_tracking.py     # Options tracking
│   │   └── ap_backfill.py             # Historical backfill
│   │
│   └── logs/                          # Strategy-level logs
│
├── oracle/                            # AI Database Interface System
│   ├── oracle_main.py                 # CLI entry point
│   ├── oracle_config.py               # Configuration
│   ├── oracle_data_access.py          # Database query layer
│   ├── claude_api.py                  # Claude API integration
│   ├── oracle_vanna.py                # Vanna AI integration
│   └── ollama/                        # Local LLM support
│       └── chat.py                    # Ollama chat interface
│
├── daily_analysis/                    # Comprehensive Daily Analysis System
│   ├── daily_analysis_orchestrator.py # Main orchestration
│   │
│   ├── Market Analysis Components
│   │   ├── daily_analysis_market_core.py         # Core market metrics
│   │   ├── daily_analysis_market_analysis.py     # Market regime analysis
│   │   ├── daily_analysis_market_correlation.py  # Inter-market correlations
│   │   ├── daily_analysis_market_timeseries.py   # Time series analysis
│   │   └── daily_analysis_sector_performance.py  # Sector performance
│   │
│   ├── Symbol Analysis Components
│   │   ├── daily_analysis_symbol_core.py         # Core symbol data
│   │   ├── daily_analysis_symbol_analysis.py     # Symbol scoring
│   │   ├── daily_analysis_symbol_catalysts.py    # Catalyst detection
│   │   ├── daily_analysis_symbol_momentum.py     # Momentum indicators
│   │   ├── daily_analysis_symbol_news.py         # News sentiment
│   │   ├── daily_analysis_symbol_openinterest.py # OI analysis
│   │   └── daily_analysis_symbol_options.py      # Options activity
│   │
│   ├── Options Analysis Components
│   │   ├── daily_analysis_options_core.py        # Core options data
│   │   ├── daily_analysis_options_flow.py        # Flow analysis
│   │   ├── daily_analysis_options_greeks.py      # Greeks calculations
│   │   ├── daily_analysis_options_oi.py          # OI metrics
│   │   ├── daily_analysis_options_positions.py   # Position analysis
│   │   ├── daily_analysis_options_timing.py      # Timing analysis
│   │   └── daily_analysis_options_valuation.py   # Valuation metrics
│   │
│   ├── Position Analysis Components
│   │   ├── daily_analysis_positions_flow.py      # Position flow analysis
│   │   ├── daily_analysis_positions_signals.py   # Entry/exit signals
│   │   ├── daily_analysis_positions_timing.py    # Position timing
│   │   └── daily_analysis_positions_valuation.py # Position valuation
│   │
│   └── Utilities
│       ├── database_validator.py      # Schema validation
│       ├── sector_mapping.py          # Sector utilities
│       └── test_*.py files            # Integration tests
│
├── morning_view/                      # Morning Watchlist & Analysis UI
│   ├── mv_main.py                     # TUI entry point
│   ├── morning_views.py               # View orchestration
│   ├── tui_data.py                    # Data layer
│   ├── ai_analyzer.py                 # AI analysis integration
│   ├── ai_council.py                  # Multi-AI council integration
│   ├── ai_prompts.py                  # Prompt templates
│   ├── ai_providers.py                # AI provider abstraction
│   └── advisor_data.py                # Advisor data structures
│
├── ai_council/                        # Multi-AI Consultation System
│   ├── council.py                     # Council orchestration
│   └── base_personality.py            # AI personality framework
│
├── core/                              # Shared Infrastructure
│   ├── tradier_api.py                 # Tradier API client
│   ├── alphavantage_api.py            # Alpha Vantage API client
│   ├── symbols_klmn800.py             # KLMN 800 universe
│   ├── symbols_universes.py           # Major indexes
│   ├── symbols_sector_source.py       # Sector mappings
│   ├── scanner_sector_definitions.py  # Legacy sector mappings
│   ├── ai_orchestrator.py             # AI interaction orchestrator
│   ├── ai_wrapper.py                  # AI provider wrapper
│   └── ai_safety.py                   # AI safety guardrails
│
├── data/                              # Central Data Repository
│   ├── datalake.db                    # Primary database (production writes)
│   ├── datalake_query.db              # Query database (read-only, synced 3x daily)
│   ├── datalake_schema_2025-10-01.md  # Database schema documentation
│   ├── archive_2025_*.db              # Monthly archives
│   │
│   ├── Data Collection Scripts
│   │   ├── fmp_historical_backfill.py        # Historical price data
│   │   ├── fmp_symbol_metadata.py            # Symbol metadata
│   │   ├── yfinance_historical_backfill.py   # yfinance historical data
│   │   ├── yfinance_earnings_historical.py   # Historical earnings
│   │   ├── market_daily_summary.py           # Market regime tracking
│   │   ├── av_news_symbol.py                 # Alpha Vantage news
│   │   └── daily_csv_transfer.py             # CSV data transfer
│   │
│   ├── health/                        # Database Health Management
│   │   ├── db_backup.py               # Backup and sync utilities
│   │   ├── db_archive_expired.py      # Archive old data
│   │   ├── query_archives.py          # Query archived data
│   │   └── fix_archive_schema.py      # Schema migration utilities
│   │
│   ├── migrations/                    # Database Migrations
│   └── cache/                         # API response caching
│
├── tools/                             # Utility Scripts
│   ├── Core Utilities
│   │   ├── timezone_utils.py          # EST/DST handling
│   │   ├── decimal_formatter.py       # Database decimal formatting
│   │   ├── debug.py                   # System debugging
│   │   ├── project_search.py          # Codebase search
│   │   └── generic_endpoint_tester.py # API testing
│   │
│   ├── Database Tools
│   │   ├── direct_db_query.py         # Fast SQL execution
│   │   ├── oracle_bridge.py           # Natural language queries
│   │   └── calculate_oi_time_series.py # OI calculations
│   │
│   ├── AI Advisors
│   │   ├── advisor_sonnet.py          # Claude Sonnet advisor
│   │   ├── advisor_chatgpt.py         # ChatGPT advisor
│   │   ├── advisor_gemini.py          # Gemini advisor
│   │   └── code_reviewer.py           # ChatGPT code review
│   │
│   ├── Communication Tools
│   │   ├── market_report_emailer.py   # Market report delivery
│   │   ├── research_report_emailer.py # Research report delivery
│   │   ├── document_emailer.py        # Document delivery
│   │   ├── social_content_generator.py # Social media content
│   │   └── social_poster.py           # Social media posting
│   │
│   ├── Trading Tools
│   │   ├── add_position.py            # Position tracking
│   │   └── news_collector.py          # News collection
│   │
│   └── Deprecated/                    # Archived utilities
│
├── ai-dev-tasks/                      # PRD Workflow System
│   ├── create-prd.md                  # PRD creation workflow
│   ├── generate-tasks.md              # Task generation workflow
│   └── process-task-list.md           # Task execution workflow
│
├── tasks/                             # PRD and Task Files
│   ├── *-prd-*.md                     # Product requirement documents
│   └── tasks-*-prd-*.md               # Generated task lists
│
├── docs/                              # Documentation
│   ├── ai-dev-tasks.md                # PRD workflow guide
│   ├── chrome-extension.md            # Extension architecture
│   ├── database-tools.md              # Database tool usage
│   ├── trading-style.md               # Trading approach guide
│   ├── social-posting.md              # Social media guide
│   └── morning-view-watchlist-redesign.md # Morning view design
│
├── scheduled_tasks/                   # Automated Tasks
│   ├── run_fmp_symbol_metadata.bat    # Symbol metadata updates
│   ├── run_weekly_baseline_update.bat # Statistical baseline updates
│   └── run_yfinance_earnings_upcoming.bat # Earnings data updates
│
├── chrome_extension/                  # Browser Extension
│   ├── manifest.json                  # Extension manifest
│   ├── background.js                  # Background service worker
│   ├── popup.html / popup.js          # Settings UI
│   │
│   ├── content-scripts/               # Page injections
│   │   ├── chain_page.js              # Options chain enhancements
│   │   ├── detail_page.js             # Detail page features
│   │   ├── symbol_page.js             # Symbol page features
│   │   └── shared_utils.js            # Shared utilities
│   │
│   ├── api/                           # Backend API
│   │   ├── api_server.py              # Flask API server
│   │   ├── simple_flow_api.py         # Simplified flow API
│   │   ├── Procfile                   # Railway deployment
│   │   └── requirements.txt           # Python dependencies
│   │
│   ├── icons/                         # Extension icons
│   └── DEVELOPMENT_GUIDE.md           # Extension development guide
│
├── logs/                              # System-wide logs
├── cache/                             # System-wide cache
└── reports/                           # Generated reports


## Strategy Module Details

### Flow Monitor
- **Purpose**: Real-time volume flow detection via continuous scanning
- **Schedule**: 20-minute collection cycles during market hours (9:15 AM - 5:00 PM)
- **Analysis**: Z-scoring against statistical baselines, pattern detection
- **Alerts**: Real-time unusual flow notifications with social media integration
- **Evaluation**: 30-day performance tracking with profitability analysis
- **Strike Range**: ±20% from underlying price

### OI Delta (Open Interest Delta)
- **Purpose**: Open Interest change analysis and pattern detection
- **Schedule**: Morning analysis (6:35-9:00 AM), Evening operations (5:00 PM+)
- **Analysis**: OI change tracking, delta correlation, concentration analysis
- **Universe**: Custom symbol universe management
- **Strike Range**: ±20% from underlying price (since 2025-09-18)

### Earnings Play (Intelligence System)
- **Purpose**: Earnings event tracking with IV arbitrage opportunities
- **Components**:
  - IV tracking (T-7 to T+3 snapshots)
  - Historical earnings moves database
  - Sector sympathy detection
  - Arbitrage scanner for mispriced IV
  - Trading journal with notes and tags
- **Schedule**:
  - Weekly refresh (Sundays): fetch/archive/cleanup
  - Daily pipeline (5 PM): snapshots/calculations/moves
  - Morning scan (6:30 AM): arbitrage opportunities

### News Collector
- **Purpose**: News sentiment collection and analysis
- **Sources**: Alpha Vantage, other news APIs
- **Storage**: Sentiment scores in news_symbol_sentiment table

## Data Pipeline Flow

```
Data Collection → datalake.db → Daily Analysis → Strategy Analysis → AI Intelligence → User Interfaces
     ↓              ↓                ↓                  ↓                ↓                ↓
  Scheduled     Production      Comprehensive      Flow/OI/EP      Oracle/Council   Morning View
  Scripts        Database        Curated Tables     Alerts         AI Analysis    Chrome Extension
                    ↓
              datalake_query.db ← Synced 3x daily for safe querying
```

### Collection Layer (Production Database)
**Primary Database**: `datalake.db` (production writes only)

**Scheduled Collections**:
- Historical price data (FMP, yfinance)
- Symbol metadata and sector mappings
- Earnings calendar and historical events
- Market regime and daily summaries
- News sentiment data
- Most collections orchestrated through `main.py`
- Weekly/monthly tasks via Windows Task Scheduler

**Real-time Collections**:
- Flow Monitor: 20-minute cycles during market hours
- OI Delta: Morning (6:35-9:00 AM) and Evening (5:00 PM+)
- Options contracts: Full chain snapshots

### Analysis Layer (Curated Tables)
**Daily Analysis System**: Comprehensive multi-level analysis orchestrator

**Symbol-Level Analysis** (`daily_analysis_symbol_curated`):
- Core metrics, momentum indicators, catalyst detection
- News sentiment integration, OI analysis
- Mathematical opportunity scoring

**Options-Level Analysis** (`daily_analysis_options_curated`):
- Flow metrics, Greeks calculations, OI tracking
- Valuation analysis, timing indicators
- Position recommendations with entry/exit signals

**Market-Level Analysis** (`daily_analysis_market_curated`):
- Market regime classification (Bull/Bear/Neutral)
- Sector performance and correlations
- Time series analysis and trend detection

### Strategy Layer
**Flow Monitor**:
- Z-score analysis against statistical baselines
- Real-time alert generation
- Social media notifications
- 30-day performance evaluation

**OI Delta**:
- Open interest concentration analysis
- Delta correlation and momentum tracking
- Symbol rollup summaries

**Earnings Play**:
- IV tracking and arbitrage detection
- Sector sympathy opportunities
- Trading journal with performance tracking

**News Collector**:
- Sentiment scoring and storage
- Symbol-level news aggregation

### AI Intelligence Layer
**Oracle System**: Natural language database queries
- Claude API integration for SQL generation
- Vanna AI for complex analysis
- Ollama support for local LLMs

**AI Council**: Multi-model consensus analysis
- Multiple AI personality framework
- Consensus-based decision making
- Morning View integration

**AI Orchestrator**: Safe, monitored AI interactions
- Request/response logging
- Error handling and retry logic
- Token usage tracking

### User Interface Layer
**Morning View (TUI)**:
- Interactive watchlist with AI insights
- Multi-AI council integration
- Real-time market analysis
- Position tracking and recommendations

**Chrome Extension**:
- Options chain enhancements
- OI graphs and concentration visuals
- Flow indicators and alerts
- Symbol page integrations

**Database Tools**:
- `direct_db_query.py`: Fast SQL execution
- `oracle_bridge.py`: Natural language queries
- Query database for safe concurrent access

## Database Architecture

### Two-Database System
**Primary Database** (`datalake.db`):
- Production data collection only
- Direct writes by collection pipelines
- Locked during collection windows

**Query Database** (`datalake_query.db`):
- Read-only analysis database
- Synced 3x daily from primary (~7:20 AM, ~5:45 PM, ~7:00 PM)
- Used by: Oracle, Morning View, all analysis tools
- Prevents locking conflicts during collection

**Monthly Archives** (`archive_2025_*.db`):
- Automated archival of expired data
- Queryable via `query_archives.py`
- Maintains system performance

### Key Database Tables
**Raw Data Tables**:
- `option_contracts`: Individual contract details (1.2M+ rows)
- `flow_alerts`: Options flow alerts with profitability
- `oi_daily`: Open interest delta tracking
- `historical_prices`: Daily OHLC data
- `earnings_calendar`: Upcoming earnings dates

**Curated Analysis Tables**:
- `daily_analysis_symbol_curated`: Symbol-level comprehensive analysis
- `daily_analysis_options_curated`: Options-level analysis (time-series)
- `daily_analysis_market_curated`: Market regime and trends

**Earnings Intelligence Tables**:
- `earnings_events`: Event archive with trading journal
- `earnings_snapshots`: IV/price time series (T-7 to T+3)
- `earnings_moves`: Historical price moves and IV changes
- `earnings_sector_effects`: Sector sympathy opportunities
- `industry_peer_mappings`: Industry-based peer relationships

**Reference Tables**:
- `symbol_metadata`: Company sectors and fundamentals (KLMN 800)
- `oi_symbol_summary`: Symbol-level OI summaries
- `market_daily_summary`: Daily market metrics with regime
- `news_symbol_sentiment`: News sentiment scores

## AI Integration Architecture

### AI Orchestrator (Core)
**Purpose**: Centralized, safe AI interaction layer
- Monitors all AI requests and responses
- Handles errors and retries
- Tracks token usage and costs
- Provides consistent interface across all AI providers

### Oracle System
**Purpose**: Natural language database interface
- Converts questions to SQL via Claude API
- Executes queries against query database
- Formats results in natural language
- Supports Vanna AI for complex analysis

### AI Council
**Purpose**: Multi-model consensus analysis
- Multiple AI personalities (Conservative, Aggressive, Technical)
- Parallel analysis from different perspectives
- Consensus voting system
- Integrated into Morning View

### Morning View AI Features
**Purpose**: AI-powered watchlist and analysis
- Real-time AI commentary on positions
- Multi-model analysis integration
- Automated opportunity detection
- Position recommendations with reasoning

## PRD Workflow System

### AI Dev Tasks Framework
**Purpose**: Structured feature development workflow

**Workflow Steps**:
1. **Create PRD** (`@ai-dev-tasks/create-prd.md`)
   - Document requirements and scope
   - Define success criteria
   - Store in `tasks/` directory

2. **Generate Tasks** (`@ai-dev-tasks/generate-tasks.md`)
   - Break down PRD into actionable tasks
   - Create task list file
   - Prioritize and sequence tasks

3. **Execute Tasks** (`@ai-dev-tasks/process-task-list.md`)
   - Work through task list systematically
   - Track progress and completion
   - Document changes

**When to Use**:
- New strategy modules or significant components
- Features spanning >5 files or database schema changes
- Unclear scope requiring upfront planning
- Work estimated >30 minutes

## System Coordination

### Daily Schedule (main.py orchestration)
**Morning Phase (6:30-9:00 AM)**:
- 6:30 AM: Earnings Play arbitrage scanner
- 6:35 AM: OI Delta morning analysis
- Database sync #1 (~7:20 AM)

**Trading Hours (9:15 AM-5:00 PM)**:
- 9:15 AM: Flow Monitor daemon starts
- 20-minute collection cycles
- Real-time alert generation

**Evening Phase (5:00 PM+)**:
- 5:00 PM: Earnings Play daily pipeline
- 5:00 PM: OI Delta evening operations
- Database sync #2 (~5:45 PM)
- Flow Monitor evaluation
- Database sync #3 (~7:00 PM)

**Weekly Tasks (Sundays)**:
- Earnings Play weekly refresh
- Statistical baseline updates
- Data archival

### Market Calendar Integration
- Market open/close detection via Tradier API
- Holiday awareness (is_trading_day() check at startup)
- Automatic schedule adjustment
- Single daily cycle, launched by Task Scheduler each weekday

## Development Standards

### Decimal Precision Policy (MANDATORY)
**Prices**: 2 decimals (strike, bid, ask, premium_value)
**Percentages**: 2 decimals (price_change_percent, flow_percentage)
**Greeks & IV**: 4 decimals (delta, gamma, theta, vega, implied_volatility)
**Ratios**: 4 decimals (oi_ratio, concentration_ratio)
**Scores**: 2 decimals (significance_score, quality_score)

**Enforcement**: Use `tools/decimal_formatter.py` for all database operations

### Code Standards
**Timezone**: Always use `now_eastern()` from `tools/timezone_utils.py`
**UTF-8**: All logging with `encoding='utf-8'`
**Subprocess**: Always specify `encoding='utf-8', errors='replace'`
**Database**: Document all table reads/writes in docstrings
**Error Handling**: Comprehensive logging and error recovery

### Testing Approach
- Manual testing and validation scripts
- Integration tests in `daily_analysis/test_*.py`
- Health reporters for system monitoring
- Performance evaluation for alert systems

This architecture reflects a mature, production-ready system with multiple strategy modules, comprehensive AI integration, and robust data management following consistent design patterns.