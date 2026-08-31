# Database Tools - Detailed Reference

## Direct Database Query Tool (Primary)

**Tool**: `tools/direct_db_query.py` - Fast SQL execution without AI interpretation

### Basic Usage

```bash
# Raw SQL execution
python tools/direct_db_query.py --sql "SELECT COUNT(*) FROM flow_alerts WHERE symbol='NVDA'"

# Schema exploration
python tools/direct_db_query.py --schema flow_alerts
python tools/direct_db_query.py --tables

# Multiple queries in one call
python tools/direct_db_query.py --multi "SELECT COUNT(*) FROM flow_alerts; SELECT MAX(trade_date) FROM option_contracts"

# JSON output for structured data
python tools/direct_db_query.py --sql "SELECT * FROM flow_alerts LIMIT 5" --json

# Archive database access
python tools/direct_db_query.py --db archive_2025_07.db --sql "SELECT COUNT(*) FROM option_contracts"
```

**Defaults**: Queries `datalake_query.db` by default (safe for analysis)

### When to Use
- Fast SQL execution without interpretation overhead
- Schema exploration and table inspection
- Multi-query batch operations
- Structured JSON output for programmatic processing

## Key Database Tables Reference

### Flow Alerts & Market Data
- **flow_alerts**: Options flow alerts with profitability tracking (4,600+ rows)
- **flow_watchlist_daily**: What the system flagged as worth watching — includes news sentiment, dip detection, earnings context
- **flow_options_scans**: Raw intraday scan data (23M+ rows). Use sparingly; prefer `option_contracts` for analysis.
- **market_daily_summary**: Daily market metrics with Bull/Bear direction and regime classifications

### Options Data (OI, IV, Greeks)
- **option_contracts**: Contract-level EOD data — OI, volume, IV, Greeks, last price. One row per contract per trade_date. (1.3M+ rows)
- **option_symbol_summary**: Symbol-level OI/IV aggregates per day — total OI, IV by DTE bucket, Greek exposures, max pain. (19,900+ rows)

### Reference Data
- **symbol_metadata**: Company sector and fundamentals for KLMN 800 universe (800+ rows)
- **earnings_upcoming**: Current earnings calendar — dates, expected moves, straddle pricing, play signals (one row per symbol, overwritten daily)
- **earnings_events**: Full earnings archive — dates, outcomes, journal notes (450+ rows)
- **earnings_moves**: Historical earnings outcomes — actual moves, direction, expected move at the time (16,000+ rows)
- **historical_prices**: Daily OHLC + volume for all symbols

## Critical Column Distinctions

**Market Direction vs Volatility Regime:**
- `market_daily_summary.market_direction`: Bull/Strong Bull/Bear/Strong Bear/Neutral (market trend)
- `market_daily_summary.regime_classification`: low_vol/normal/high_vol (volatility environment)

**Open Interest Data:**
- `option_contracts`: Contract-level EOD data — OI, volume, IV, Greeks. One row per contract per trade_date.
- `option_symbol_summary`: Symbol-level OI/IV aggregates per day — total OI, IV by DTE bucket, Greek exposures, max pain.
- OI is point-in-time, reported by OCC after close and published the next morning. Never SUM(open_interest) across dates.
- `option_type` case: lowercase in `flow_alerts` ('call'/'put'), UPPERCASE in `option_contracts` ('CALL'/'PUT').

## Best Practices

### General Guidelines
1. **Use direct_db_query.py by default**
2. **Query database for analysis** - Use `datalake_query.db` (default), not `datalake.db`
3. **Batch related queries** - More efficient than multiple single queries
4. **Cache awareness** - Results cached for 1 hour (historical queries 24 hours)
5. **Verify column names** - Check schema first for complex queries

## Error Handling

### Database Locking
If queries fail during collection windows:
- Use `datalake_query.db` instead of `datalake.db`
- Check sync status: quick sync runs every FM cycle (~10-15 min during market hours), full sync runs daily post-close
- Wait for next sync cycle if data is stale

## Living Document Encouragement

Claude Code is explicitly encouraged to add new methods to `direct_db_query.py` for commonly used patterns:
- `get_symbol_alerts(symbol, days=7)`
- `get_high_volume_contracts(min_volume=1000)`
- `analyze_flow_patterns(date_range)`

The goal is to make database analysis faster and reduce code repetition. 

## Updating This Documentation

When you discover new usage patterns, table relationships, or common pitfalls, update this section to help future Claude Code sessions. Include:
- New useful query patterns you discover
- Common mistakes and how to avoid them
- Performance tips and optimization strategies
- Table relationship insights
