# tools/

Reusable utilities for the options scanner system. This folder contains tools that are used repeatedly — either imported by production pipelines at runtime, or invoked on-demand for system maintenance and analysis.

**What belongs here:** Tools that serve a recurring purpose across the system.
**What does NOT belong here:** One-time scripts, migration helpers, backfill jobs, or throwaway debugging files. Those go in `Deprecated/`, `data/migrations/`, or get deleted.

---

## Production Infrastructure

These modules are imported by strategies, pipelines, and the main orchestrator during daily operations. Modifying them affects live system behavior.

| Module | Purpose | Key Consumers |
|--------|---------|---------------|
| `timezone_utils.py` | `now_eastern()` and date/time formatting for Eastern time | Everything (60+ imports) |
| `decimal_formatter.py` | Enforces decimal precision (2-4 places) on all DB writes | All storage modules, strategies |
| `autofix.py` | Error queuing, auto-fix spawning, collection health checks | main.py, all strategies, data health |
| `base_health_reporter.py` | Base class for strategy health report generation | Flow Monitor, Option Pipeline, Earnings Intel |
| `realized_volatility.py` | Annualized RV using log returns (rv_5d, rv_10d, rv_20d) | Option Pipeline symbol rollup |
| `news_sentiment.py` | Alpha Vantage news fetch + relevance-weighted sentiment scoring | Flow Monitor (enriches watchlist entries on creation) |
| `email_notifier.py` | SMTP email sending using config.json credentials | Flow Monitor watchlist alerts |
| `social_content_generator.py` | Generates enriched social posts from flow alerts | social_poster.py |
| `social_poster.py` | Posts to Reddit/Twitter with dedup and engagement tracking | Flow Monitor social notifier |

### What's Normal

- `autofix.py` spawning Claude Code sessions for errors is expected behavior — it has rate limiting built in (3 attempts/error/day, 5 spawns/hour)
- `news_sentiment.py` uses 25 Alpha Vantage API calls/day; running out of budget by mid-afternoon on busy days is normal, not an error
- `email_notifier.py` failures are non-fatal — the system logs them and continues

### What Needs Attention

- If `autofix.py` circuit-breaker activates (logged as `[AUTOFIX] Circuit breaker tripped`), the same error is recurring and needs manual investigation
- If `decimal_formatter.py` raises errors, a storage module is passing unexpected data types — fix the upstream source, not the formatter
- If `news_sentiment.py` gets rate-limited on the first call of the day, Alpha Vantage may be IP-throttling (observed Feb 2026)

---

## Operator & Maintenance Tools

These are invoked on-demand by Ben or Claude Code for analysis, maintenance, and system operations. They are not imported by production pipelines (except where noted).

### Database

| Tool | Purpose | Usage |
|------|---------|-------|
| `direct_db_query.py` | SQL query CLI — primary tool for all database analysis | `python tools/direct_db_query.py --sql "..."` |

`direct_db_query.py` defaults to `datalake_query.db` (the safe query database). Use `--db data/datalake.db` only when you explicitly need production. Key flags: `--schema TABLE`, `--tables`, `--multi "Q1; Q2"`.

### Analysis

| Tool | Purpose | Usage |
|------|---------|-------|
| `volume_profile_calculator.py` | POC, Value Area, HVN/LVN from historical prices | `python tools/volume_profile_calculator.py --symbol NVDA` |
| `technical_levels.py` | Support/resistance via 3-day confirmation swing detection | `python tools/technical_levels.py --symbol MGM` |

`volume_profile_calculator.py` is also imported by Morning View for symbol detail display. `technical_levels.py` is standalone CLI only (not yet integrated).

### Email

| Tool | Purpose | Usage |
|------|---------|-------|
| `email_reader.py` | Gmail API reader for the alerts inbox | `python tools/email_reader.py --check` |

`email_reader.py` requires OAuth2 token (`gmail_token.json`). See CLAUDE.md for full CLI reference.

### Development

| Tool | Purpose | Usage |
|------|---------|-------|
| `launch_claude_dev.py` | Ctrl+E in Morning View TUI spawns Claude Code with context | Invoked by TUI hotkey |

------|---------|-------|
| `add_position.py` | Standalone options position tracker with P&L management | `python tools/add_position.py --interactive` |

Not currently integrated into the main system. Self-contained with its own database table.

---

## Subfolders

| Folder | Purpose |
|--------|---------|
| `Deprecated/` | Graveyard for retired scripts: old migration tools, superseded utilities, one-time jobs. Do not add new tools here — if it's not reusable, it shouldn't be in `tools/` at all. |

---

## Guidelines for AI Agents

**Before creating a file in this directory**, ask:
1. Will this tool be used more than once?
2. Does it serve a purpose that no existing tool covers?
3. Is it a utility (belongs here) or a data operation (belongs in `data/`) or a core library (belongs in `core/`)?

If the answer to #1 is no, put it somewhere else or don't save it at all. This folder is for tools that earn their keep.
