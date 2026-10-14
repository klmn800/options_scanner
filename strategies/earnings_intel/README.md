# Earnings Intelligence Strategy

Finds options that look mispriced ahead of earnings by comparing the market's straddle-implied move with each stock's recent (6-quarter) earnings moves. Maintains the earnings calendar for the KLMN universe (with a date-confirmation layer), captures IV/price snapshots around each event, records what actually happened afterwards, and publishes a daily `earnings_watchlist` of the best setups.

**Full technical reference:** [`docs/earnings_strategy_refactor/EARNINGS_INTELLIGENCE_TECHNICAL_GUIDE.md`](../../docs/earnings_strategy_refactor/EARNINGS_INTELLIGENCE_TECHNICAL_GUIDE.md). It covers the pipeline, signal math, tables, operations, queries, and troubleshooting. This README is only a map.

## Entry points

| When | What runs |
|------|-----------|
| Daily, Step 1.2 (pre-market) | `ei_main.run_daily_pipeline()`: lite date refresh → snapshots → archive → post-earnings calc → expected moves/signals → watchlist → news (the arbitrage step is currently disabled) |
| Fridays, Step 5.3 | `ei_collector.EarningsCollector.collect_weekly_earnings()`: archive, cleanup, full yfinance + Finnhub calendar refresh |

```bash
python main.py --earnings-intel
python strategies/earnings_intel/ei_main.py --daily-pipeline --no-interaction
python tools/earnings_confirm.py --list-unconfirmed
```

## Files

| File | Role |
|------|------|
| `ei_main.py` | Daily pipeline orchestrator |
| `ei_lite_refresh.py` | Near-term date verification, disputes, Earnings Researcher spawn |
| `ei_collector.py` | Weekly calendar refresh |
| `ei_moves_upcoming.py` | Straddle expected move, signals, alert flag |
| `ei_watchlist.py` | `earnings_watchlist` lifecycle |
| `ei_snapshot_collector.py` | T-7…T+5 snapshots |
| `ei_post_earnings_calc.py` | Post-earnings moves, IV crush, outcomes |
| `ei_arbitrage_scanner.py` | Sector sympathy scanner (not in the daily run) |
| `ei_health_reporter.py` | Health reporting |
| `ei_backfill_*.py` | One-time backfills |

## Other docs

- `docs/EARNINGS_TRADING_STRATEGIES.md`, `docs/EARNINGS_STRADDLE_PLAYBOOK.md`: how the signals are traded (not system docs).
- `../../docs/earnings-scenario-calculator.md`: the scenario calculator tool.
- `migrations/README.md`: schema migration files.
