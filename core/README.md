# core/ - Shared Foundation Layer

The shared infrastructure that all strategies depend on. This is the **strategy-agnostic** foundation: API clients for external data sources and the symbol universe that defines what the system trades.

If something is only used by one strategy, it belongs in that strategy's folder, not here. If removing a file here would break multiple strategies, it belongs here.

## Active Files

### `tradier_api.py` - Market Data API Client
The primary data lifeline for the entire system. Provides real-time and historical market data from Tradier.

**Key exports:**
- `TradierDataClient` - Full-featured client used by main.py for market calendar, quotes, options chains
- `TradierAPI` - Lower-level API class used by data backfill scripts
- `RateLimiter` - Request throttling (120 req/min market data, 60 req/min trading)
- `BasicCache` - Local response caching to minimize API calls

**Used by:** `main.py`, `data/market_daily_summary.py`, `data/tradier_historical_backfill.py`

**Normal behavior:** Rate limiter logs are expected during heavy collection windows. Occasional timeout retries during market open are normal. Persistent 401/403 errors indicate an API key issue in `config.json`.

---

### `alphavantage_api.py` - News Sentiment API Client
Alpha Vantage NEWS_SENTIMENT endpoint client. Strict budget: **25 calls/day** on free tier, 5 req/min.

**Key exports:**
- `AlphaVantageNewsClient` - News fetching with topic/symbol filtering, database storage
- `AlphaVantageRateLimiter` - Per-minute and per-day rate tracking with persistent daily usage file
- `AlphaVantageCache` - Response caching to avoid duplicate API calls

**Used by:** `tools/news_sentiment.py` (the active news enrichment tool)

**Normal behavior:** Hitting the 25/day budget ceiling is expected and handled gracefully. The rate limiter writes usage to `cache/alphavantage_daily_usage.json`. If you see rate-limit responses despite budget remaining, it's IP-level throttling from Alpha Vantage (observed Feb 2026).

---

### `symbols_klmn800.py` - Symbol Universe Definition
The single source of truth for the ~800-symbol KLMN universe. The most widely imported file in the project (~20 importers across strategies, data, and tools).

**Key exports:**
- `KLMN_800_SYMBOLS` - Complete list (~800 symbols): S&P 500 + Russell selections + NASDAQ + preferred + ETFs + airlines
- `get_specialty_list(list_name)` - Primary accessor function (most common import across codebase)
- `is_symbol_in_klmn_800(symbol)` - Membership check
- `KLMN_800_SP500_COMPONENT`, `KLMN_800_RUSSELL_COMPONENT`, `KLMN_800_NASDAQ_COMPONENT` - Component lists
- `KLMN_PREFERRED`, `ETF_SYMBOLS`, `AIRLINE_PLAY_SYMBOLS` - Specialty sublists

**Used by:** Option Pipeline, Flow Monitor, Earnings Intel, data backfill, news sentiment, symbol metadata

**Normal behavior:** This is a static data file. It should only change when Ben intentionally adds/removes symbols. The "purgatory list" at the bottom contains 58 symbols removed for low liquidity (July 2025).

---

### `__init__.py`
Empty package init. Allows `from core.xxx import ...` syntax.

## What Belongs in core/

- API clients for external data sources (Tradier, Alpha Vantage, future providers)
- The symbol universe definition (KLMN 800)
- Cross-strategy shared infrastructure (rate limiters, caching patterns)

## What Does NOT Belong in core/

- Strategy-specific logic (goes in `strategies/`)
- One-off tools and utilities (goes in `tools/`)
- Database operations (goes in `data/`)

## Deprecated/

Contains 7 files moved out during Feb 2026 cleanup. None were imported by any active code:

- `ai_safety.py`, `ai_wrapper.py`, `ai_orchestrator.py` - Unused multi-model AI orchestration framework (GPT/Grok/Gemini with safety filtering). Never integrated into any strategy.
- `symbols_universes.py` - Russell 1000 list. Superseded by KLMN 800.
- `symbols_maximum.py` - 5,681-symbol Robinhood universe from old OID system. Superseded by KLMN 800.
- `scanner_sector_definitions.py` - Old sector scanning definitions. Had broken imports. Superseded by `data/symbol_metadata.py` and `symbol_metadata` database table.
- `symbols_sector_source.py` - JSON-based metadata loader. Referenced a JSON file that never existed.
