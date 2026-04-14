# PRD: News Collection Infrastructure

**Document ID:** 0002
**Created:** 2025-10-03
**Status:** Draft
**Owner:** Ben

## 1. Introduction/Overview

The News Collection Infrastructure is a standalone strategy module that systematically collects, processes, and stores financial news data from Alpha Vantage API. Currently, news collection happens ad-hoc through the daily_analysis module, which is being deactivated for maintenance. This leaves a critical gap in data availability for Morning Views and other analysis modules that rely on news sentiment for symbol ranking and decision-making.

**Problem:** News data collection is buried in daily_analysis and will become unavailable when that module goes offline. Morning Views (`morning_view/morning_views.py`) depends on news sentiment data from `news_symbol_sentiment` and `news_articles` tables to rank symbols and provide context.

**Solution:** Extract news collection into a dedicated strategy module with its own CTI (Collect-Transform-Insert) pipeline, running independently to ensure continuous news data availability.

## 2. Goals

1. **Ensure continuity**: News data collection continues when daily_analysis is offline
2. **Support Morning Views**: Populate `news_symbol_sentiment` and `news_articles` tables for symbol ranking
3. **Enable future features**: Create foundation for news links in reports, multiple news APIs, alerts, etc.
4. **Maintain data quality**: Preserve existing Alpha Vantage sentiment scoring and relevance metrics
5. **Standalone operation**: Module runs independently like flow_monitor or oi_delta strategies

## 3. User Stories

**As a trader using Morning Views:**
- I want news sentiment data available every morning so I can see bullish/bearish rankings for symbols
- I want continuous news collection even when other modules are down so my watchlist remains informed

**As a system developer:**
- I want a dedicated news module so I can enhance news features without touching daily_analysis
- I want the CTI pattern so news collection follows the same architecture as other strategies

**As Ben (planning future enhancements):**
- I want news infrastructure in place so I can easily add new features like news alerts, multiple APIs, or article links in reports
- I want to spend more time understanding Alpha Vantage's sentiment calibration and improve the scoring system

## 4. Functional Requirements

### 4.1 Module Structure
1. Create `strategies/news_collector/` directory following standard strategy pattern
2. Include standard files: `nc_main.py` (entry point), `nc_config.py` (configuration), `nc_collector.py` (CTI pipeline)
3. Module must be callable independently: `python strategies/news_collector/nc_main.py`

### 4.2 Data Collection (CTI Pipeline)
4. Collect news from Alpha Vantage API using intelligent quota allocation strategy
5. **Priority-based collection**: Query watchlist symbols more frequently/deeply than general universe
6. **Broad coverage**: Ensure all KLMN 800 symbols get some news data (even if less frequent)
7. Extract news data: headlines, links, publish dates, source
8. Extract per-symbol metrics: relevance score, sentiment score, sentiment label
9. Store raw articles in `news_articles` table (avoid duplicates by article URL)
10. Store symbol-sentiment pairs in `news_symbol_sentiment` table (one row per symbol per article)

### 4.3 Alpha Vantage Integration & Quota Management
11. Use existing `core/news_fetcher.py` if suitable, or create new fetcher in module
12. Respect API rate limits (Alpha Vantage free tier: 25 requests/day)
13. **Intelligent quota allocation**:
    - Prioritize watchlist symbols (from `v_morning_watchlist`) for deeper coverage
    - Rotate through remaining KLMN 800 symbols for broad baseline coverage
    - Example strategy: 15 calls for watchlist symbols, 10 calls rotating through universe
14. Handle API errors gracefully with retry logic
15. Cache responses to avoid redundant API calls (don't re-fetch same symbol same day)

### 4.4 Database Operations
16. Write to `news_articles` table: article_id (URL hash?), headline, url, publish_date, source, summary
17. Write to `news_symbol_sentiment` table: symbol, article_id, relevance_score, sentiment_score, sentiment_label, trade_date
18. Use decimal formatter (`tools/decimal_formatter.py`) for sentiment_score and relevance_score
19. Apply timezone consistency (`tools/timezone_utils.py`) for publish_date and trade_date
20. Track collection metadata: last_fetched timestamp per symbol to support intelligent rotation

### 4.5 Scheduling & Execution
21. Support manual execution: `python nc_main.py`
22. Support scheduled execution via main.py orchestrator (future integration point)
23. Log all collection activity to `strategies/news_collector/logs/`
24. Provide summary statistics: articles collected, symbols processed, API calls made, quota breakdown (watchlist vs universe)

## 5. Non-Goals (Out of Scope)

1. **News alerts**: Not building real-time alert system (just data collection)
2. **Article display**: Not rendering news articles in UI (Morning Views shows sentiment only)
3. **Sentiment analysis**: Not doing custom AI analysis (using Alpha Vantage's built-in scores)
4. **Multiple news APIs**: Alpha Vantage only for v1 (foundation for future expansion)
5. **Historical backfill**: Not collecting historical news (start from today forward)
6. **News-triggered trading**: No automated trading logic based on news

## 6. Design Considerations

### 6.1 Module Location
- Path: `strategies/news_collector/`
- Follows existing strategy pattern (flow_monitor, oi_delta, airline_play)

### 6.2 Configuration
- `nc_config.py` should include:
  - Alpha Vantage API key (read from `credentials.json`)
  - Symbol universe (KLMN 800 from `core/symbols.py`)
  - Collection frequency (daily)
  - Sentiment lookback window (3 days for Morning Views)

### 6.3 User Interface
- Console output with progress indicators (like Flow Monitor)
- Emoji-safe logging (Windows compatibility)
- Summary report: "Collected 47 articles for 23 symbols (12 API calls, 2 errors)"

## 7. Technical Considerations

### 7.1 Existing Code Reuse
- **Check `core/news_fetcher.py`**: Does it already handle Alpha Vantage? If yes, import and use.
- **If not**: Create new fetcher class in `strategies/news_collector/nc_fetcher.py`
- **Database schema**: Verify `news_articles` and `news_symbol_sentiment` tables exist and have correct columns

### 7.2 Data Quality
- **Sentiment score calibration**: Ben doesn't fully understand Alpha Vantage's scale yet - document in code comments
- **Relevance filtering**: Articles with relevance_score < 0.5 might be noise (TBD, make configurable)
- **Duplicate detection**: Use article URL as unique key to prevent re-inserting same article

### 7.3 Integration Points
- **Morning Views**: Already queries `news_symbol_sentiment` table - should work immediately
- **Daily Analysis**: Will continue to work when reactivated (reads same tables)
- **Future modules**: Any module can query news tables for context

### 7.4 Dependencies
- Alpha Vantage API (existing subscription)
- `core/symbols.py` (KLMN 800 universe)
- `tools/decimal_formatter.py` (decimal policy)
- `tools/timezone_utils.py` (EST consistency)
- Database: `data/datalake.db` (tables: `news_articles`, `news_symbol_sentiment`)

## 8. Success Metrics

**Primary Success Criteria:**
1. ✅ News data populates `news_symbol_sentiment` and `news_articles` tables daily
2. ✅ Morning Views shows news sentiment without errors
3. ✅ Module runs independently (doesn't require daily_analysis)

**Quality Indicators:**
4. No duplicate articles in database (URL-based deduplication works)
5. API rate limits respected (no 429 errors from Alpha Vantage)
6. Sentiment scores follow decimal policy (2 decimal places)
7. Logs show clear collection statistics with quota breakdown
8. Watchlist symbols have fresher news data than general universe symbols
9. Over time, all KLMN 800 symbols accumulate some news coverage (rotation working)

**Operational Success:**
- Ben can deactivate daily_analysis without losing news data
- Ben can run `python nc_main.py` manually to refresh news on-demand
- Morning Views continues to show "Bullish" / "Bearish" sentiment rankings

## 9. Open Questions

1. **Current `core/news_fetcher.py` capabilities**: Does it already collect from Alpha Vantage? What's its current structure?
2. **Database schema verification**: Do `news_articles` and `news_symbol_sentiment` tables have the expected columns? Need migration?
3. **Sentiment score calibration**: What's Alpha Vantage's sentiment scale? (-1 to +1? 0 to 100?) Document in code.
4. **Collection frequency**: Daily at what time? Morning before market open? Evening after close?
5. **Relevance threshold**: Should we filter out low-relevance articles (e.g., relevance_score < 0.3)? Or store everything?
6. **API quota split**: What's the optimal split between watchlist depth and universe breadth? (60/40? 50/50? Make configurable?)
7. **Rotation strategy**: For universe coverage, should we rotate alphabetically, by volume, or by last_fetched timestamp?
8. **Error handling**: What happens if Alpha Vantage API is down? Retry? Skip day? Alert Ben?

---

## Next Steps

1. **Review this PRD** with Ben for approval
2. **Investigate existing code**: Check `core/news_fetcher.py` and database schema
3. **Generate task list** using `ai-dev-tasks/generate-tasks.md`
4. **Begin implementation** using `ai-dev-tasks/process-task-list.md`
