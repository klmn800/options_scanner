# Architecture

How the Options Scanner is put together: one orchestrator, four independent
strategy modules, a two-database SQLite core, and a self-healing loop.

## System shape

```
Windows Task Scheduler (weekdays)
        │
        ▼
     main.py ──────────────── orchestrator (main_ui / main_calendar / main_runners)
        │
        ├── strategies/flow_monitor/    intraday flow detection (daemon, Phase 2)
        ├── strategies/option_pipeline/ EOD open-interest snapshots (Phases 1 & 3)
        ├── strategies/earnings_intel/  earnings calendar, IV, signals (Phase 1)
        ├── tools/trade_ingest.py       broker-confirmation email parser (1.4, 3.1)
        ├── data/health/                backups, syncs, sector archives (4–5)
        └── tools/performance_writer.py performance.db metrics (Phase 6)

core/      Tradier + Alpha Vantage clients, symbol universe (DB-backed)
tools/     shared utilities: logging, decimal policy, timezone, lifecycle
autofix/   error queue → Claude Code fix sessions
agents/    autonomous Claude Code agents (private workspaces; see agents/README.md)
```

Design principles: each strategy is **self-contained** — its own collectors,
storage module, config section, and health reporting. Strategies never read each
other's tables during collection; anything cross-strategy happens at analysis time.
Direct SQL, no ORM.

## Orchestrator order

```
1.1 Option Pipeline (morning) → 1.2 Earnings Intel → 1.3 Metadata
→ 1.4 Trade Ingest → 1.5 Quick Sync
→ 2. Flow Monitor (market hours, ~15–20 cycles)
→ 3.1 Trade Ingest → 3.2 Option Pipeline (evening) → 3.4 Sync
→ 4.1 Daily Backup → 4.2 Autofix Review
→ 5.x Friday only: weekly backup, FM baselines, earnings refresh, sector archives
→ 6.1 Performance DB → exit
```

Each `run_*()` step in `main_runners.py` returns a structured result dict
(`{'success': bool, ...}`); the orchestrator owns all console framing (phase
headers, summary boxes) while strategies only emit progress lines — the split is
documented in `docs/CONSOLE_DEVELOPER_GUIDE.md`.

## The two collection strategies

Both scan a ±20% strike band around the underlying and collect **independently**
from the Tradier API — same contracts, different questions.

| Aspect | Flow Monitor | Option Pipeline |
|--------|--------------|-----------------|
| Question | "What unusual activity is happening *right now*?" | "How has this contract's OI evolved?" |
| Frequency | Every ~15–20 min during market hours | Twice daily (pre-market + post-close) |
| Granularity | ~10+ snapshots per contract per day | One row per contract per trade date |
| Writes | `flow_options_scans`, `flow_alerts`, `flow_symbol_summary` | `option_contracts`, `option_symbol_summary` |
| Retention | Ephemeral (days–weeks, then archived) | Long-term time series |

**Flow Monitor cycle:** collect fresh chains → write raw scans → analyze the
current scan against statistical baselines (premium + volume surprise) → write
alerts → roll up per-symbol at end of day. Alerts feed a watchlist with inline news
sentiment, an intraday earnings-signal tracker, and the X auto-publisher. Every
alert is resolved the next morning against actual open-interest change — did the
flow open new positions or close old ones? — so alert quality is measured, not
assumed.

**Option Pipeline:** end-of-day chain snapshots with OI deltas, IV momentum, and
Greek changes computed against prior trade dates. Its `option_symbol_summary`
(93 columns) is the primary IV source for Earnings Intel. Contracts already being
tracked stay in collection even if their strike drifts out of band ("sticky
contracts"), so no time series ends mid-life.

**Earnings Intel** consumes both: expected moves from live straddles, historical
moves from its own event archive, IV percentile context from the Option Pipeline.
Its signal compares what the market is pricing (straddle) against what the symbol
actually did over its recent six quarters, and flags underpricing. Earnings dates
are reconciled across yfinance, Finnhub, and Tradier — when sources disagree, the
dispute is logged and (if configured) an autonomous research agent is spawned to
investigate.

## Two-database workflow

```
collection pipelines ──write──▶ data/datalake.db        (production, WAL)
                                     │
                    quick sync (watermark, after each FM cycle)
                    pre-market targeted sync (UPDATE columns)
                    full sync (file-level, post-close)
                                     ▼
analysis / agents ───read───▶ data/datalake_query.db    (read-only replica)
```

Writers get an uncontended production DB; every reader (analysis tools, agents,
ad-hoc SQL) hits the replica. Three sync tiers keep the replica no more than
~15 minutes behind during market hours without ever interrupting live writes.
Separate databases hold performance metrics (`performance.db`) and paper-trading
state (`paper.db`).

**Retention** is tiered: high-volume scan data moves to per-sector archive
databases on Fridays (7/30/90-day tiers, with 300-day overrides for summary
tables); long-term tables are copied, not moved. Daily and weekly backup files are
taken with SQLite's hot-backup API so live connections are never blocked.

## Key tables

| Table | Purpose | Scale |
|-------|---------|-------|
| `flow_options_scans` | Raw intraday contract snapshots | 23M+ rows |
| `flow_alerts` | Detected flows + next-day OI resolution | per-alert grading |
| `option_contracts` | Contract-level EOD (OI, IV, Greeks) | 66 cols, 1M+ rows |
| `option_symbol_summary` | Symbol-level OI/IV aggregates | 93 cols, primary IV source |
| `earnings_upcoming` / `earnings_events` / `earnings_moves` | Calendar, archive, outcomes | 16K+ historical moves |
| `earnings_snapshots` | OHLC/IV window around events (T-7 → T+5) | per-event time series |
| `trade_executions` | Broker fills parsed from confirmation emails | immutable log |
| `historical_prices` | Daily OHLC, all symbols | 1M+ rows |
| `market_daily_summary` | Regime, SPY/VIX, breadth | daily |

One deliberate gotcha worth knowing: **open interest is point-in-time**, one row
per contract per trade date — summing it across dates is always wrong. Full schema:
`data/datalake_schema_2026-01-01.md`.

## Self-healing and agents

Runtime errors call `queue_error()` (batched into an end-of-day review) or
`handle_error()` (critical — spawns an immediate Claude Code fix session).
Transient classes (lock contention, memory) are auto-suppressed and only escalate
on recurrence. See `autofix/README.md`.

The autonomous agents live outside this repo's history (private workspaces,
published framework: [agent_lab](https://github.com/klmn800/agent_lab)) but plug in
through visible seams: the orchestrator's advisor launch, the earnings-dispute
spawn in `strategies/earnings_intel/ei_lite_refresh.py`, and the System Analyst's
inbox/proposal protocol described in `CLAUDE.md`.

## Conventions that keep it honest

- **Decimal policy** — every INSERT/UPDATE passes through
  `tools/decimal_formatter.py` (prices 2dp, Greeks/IV 4dp, scores 2dp).
- **Timezone** — all timestamps via `now_eastern()`; the machine runs in one
  market's clock.
- **UTF-8 everywhere** — explicit encodings on every file handler and subprocess
  (Windows cp1252 is the default footgun).
- **Diagnostic integrity** — no hardcoded or faked diagnostic values; health
  reports measure actual outcomes.
- **Console contract** — orchestrator owns structure, strategies own progress
  lines; all output flows through `tools/log_utils.py`.
