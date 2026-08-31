# Claude Code Reference — Detailed Documentation

**This file contains detailed reference material for Claude Code sessions.** It is NOT loaded automatically — Claude reads it on-demand when working on specific subsystems.

For the core operational guide (loaded every session), see the project root `CLAUDE.md`.

---

## Agent System Details

> **Note:** The five agent workspaces under `agents/` are separate **private** repos,
> gitignored in this repository. The sanitized framework skeleton (launchers, hooks,
> prompts, conventions for all five agents plus the roundtable orchestrator) is
> published at `github.com/klmn800/agent_lab`. Overview: `agents/README.md`.
> The sections below describe how the live local agents run on Ben's machine.

### System Analyst Agent

An autonomous Claude Code session that audits data quality, investigates pipeline behavior, and proposes system improvements. Runs daily at 9 PM via Task Scheduler. Read-only — never modifies code or databases outside its own workspace. Formerly "Strategic Advisor" (renamed 2026-04-22).

```bash
# Launch interactive session (Ben watches in real-time)
cd /d E:\options_scanner\agents\system_analyst
claude --permission-mode auto @PROMPT.md

# Or via launcher (handles date injection)
python agents/system_analyst/launcher.py
```

**Key files:**
- `agents/system_analyst/PROMPT.md` — the agent's prompt
- `agents/system_analyst/proposals/` — proposals (numbered: 001, 002, etc.)
- `agents/system_analyst/proposals/feedback/` — Ben's feedback on proposals
- `agents/system_analyst/memory/` — agent's persistent workspace (journal, agenda, observations)

**Proposal review workflow:** When Ben says "let's review the system analyst's proposals" or similar:
1. Read `agents/system_analyst/proposals/INDEX.md` — shows all proposals and their status (PENDING = unreviewed)
2. Read each PENDING proposal
3. Discuss with Ben — get his take on each one
4. Write feedback to `agents/system_analyst/proposals/feedback/{proposal_name}.md` with verdict and Ben's reasoning
5. Update `INDEX.md` with the new status (APPROVED, DECLINED, DEFERRED, IMPLEMENTED)
6. The agent reads feedback at the start of its next session and adjusts its work accordingly

### Trading Advisor Agent

An interactive Claude Code session that interprets options flow, earnings setups, and market data. Three modes: morning brief (orchestrator Step 2.2), interactive conversation (manual), and nightly research (Task Scheduler). Read-only to databases and code.

```bash
# Launch interactive session (manual)
agents\trading_advisor\trade.bat

# Morning brief mode (called by orchestrator Step 2.2)
agents\trading_advisor\trade_morning.bat

# Nightly research mode (via launcher with date injection)
python agents/trading_advisor/launcher.py --prompt PROMPT_RESEARCH.md
```

**Key files:**
- `agents/trading_advisor/CLAUDE.md` — role definition and database access patterns
- `agents/trading_advisor/PROMPT_RESEARCH.md` — nightly autonomous research session prompt
- `agents/trading_advisor/reference/` — self-curated knowledge library (mechanics, case studies, patterns)
- `agents/trading_advisor/memory/` — persistent state (trade calls, session notes, research backlog)
- `agents/trading_advisor/analysis/daily_briefs/` — archived morning briefs
- `agents/trading_advisor/analysis/research/` — research output artifacts
- `agents/trading_advisor/directive.md` — Ben's ad-hoc instructions (read and cleared each session)

### Agent Pattern

See `agents/AGENT_PATTERN.md` for the replicable pattern for building new agents. Covers workspace skeleton, guardrails (write guard, settings isolation, DB access, git isolation), communication channels, launching, session workflows, context injection, and output formats.

---

## Gmail Inbox (Email Reader)

```bash
# Check for unread messages
python tools/email_reader.py --check

# List recent messages
python tools/email_reader.py --list --count 10

# Read a specific message by ID
python tools/email_reader.py --read MSG_ID

# Search with Gmail query syntax
python tools/email_reader.py --search "from:ben subject:research"

# Save all unread to memory/inbox/ and mark read
python tools/email_reader.py --process

# Inbox management
python tools/email_reader.py --mark-read MSG_ID
python tools/email_reader.py --trash MSG_ID
python tools/email_reader.py --labels

# Verify auth status
python tools/email_reader.py --auth
```

## Database Backup & Archive Strategy

System maintains **two backup files** and **sector-based archives** for redundancy and performance:

**Backups:**
1. **Daily Backup** (`data/datalake_backup.db`)
   - Created every trading day after all data collection
   - Overwrites previous day's backup
   - Provides recovery point from yesterday

2. **Weekly Backup** (`data/datalake_backup_weekly.db`)
   - Created Friday nights after archive operations
   - Preserved until next Friday
   - Provides week-end recovery point

**Archives (Friday nights only):**
3. **Sector Archives** (`data/sector_archive/{sector}.db`)
   - Three-tier retention strategy (7d / 30d / 90d default + 300d per-table override for summary tables)
   - Routes data by symbol via `symbol_metadata.archive_db`
   - Runs Friday evening within 59-hour Monday-morning cutoff
   - **Canonical tier policy:** `data/health/db_archive_sector.py` module docstring + `TIER_POLICIES` dict (~line 282). Other docs mirror it.
   - Workflow detail: `data/health/DATABASE_HEALTH_WORKFLOWS.md`
   - Archive consumer view: `data/sector_archive/README.md`

**Archive Tiers (post-P028, 2026-05-15):**
- **Tier 1 (7d MOVE):** `flow_options_scans` (MOVE), `flow_alerts` (COPY override — kept in production)
- **Tier 2 (30d MOVE):** `option_contracts` only (hybrid expired-OR-old logic)
- **Tier 3 (COPY mode):**
  - 90d default: `historical_prices` (skip_cleanup), `earnings_events` (skip_cleanup), `news_symbol_sentiment`, `news_articles`, `market_daily_summary`
  - 300d override: `option_symbol_summary`, `flow_symbol_summary`, `flow_daily_aggregates`

**Recovery scenarios:**
- Recent data loss → restore from `datalake_backup.db` (yesterday)
- Week-long issue → restore from `datalake_backup_weekly.db` (last Friday)
- Historical sector analysis → query `data/sector_archive/{sector}.db`

---

## Database Archiving and Optimization Commands

```bash
# Sector-based archiving (active system - runs automatically Friday nights)
python data/health/db_archive_sector.py --all-tiers        # All 3 tiers
python data/health/db_archive_sector.py --tier 1           # Just Tier 1 (7-day)
python data/health/db_archive_sector.py --dry-run          # Analysis only
python data/health/db_archive_sector.py --test-mode        # Airlines only

# Sector archive optimization (standalone)
python data/health/db_optimize_sectors.py                  # All sectors
python data/health/db_optimize_sectors.py --sector airlines  # Specific sector
python data/health/db_optimize_sectors.py --list           # List available sectors
```

---

## Standalone Analysis Tools

**1. Volume Profile Calculator** (`tools/volume_profile_calculator.py`)
```bash
python tools/volume_profile_calculator.py --symbol NVDA
python tools/volume_profile_calculator.py --symbol KDP --lookback 90 --output profile.json
```
- Calculates Point of Control (POC), Value Area (70% volume), HVN/LVN levels
- Queries `historical_prices` directly (60-day lookback default)
- Identifies institutional price magnets for strike selection
- Integrated into Morning View symbol detail display

**2. Technical Levels Detector** (`tools/technical_levels.py`)
```bash
python tools/technical_levels.py --symbol MGM
python tools/technical_levels.py --symbol NVDA --lookback 90 --output levels.json
```
- 3-day confirmation algorithm for swing highs/lows
- Queries `historical_prices` directly (60-day lookback default)
- Strength calculation: volume weighting + recency factor
- Outputs: resistance_1, resistance_2, support_1, support_2 with strength ratings

**3. Earnings Scenario Calculator** (`tools/earnings_scenario.py`)
```bash
python tools/earnings_scenario.py "MRVL|85|2026-03-20|CALL" --cost 4.60
python tools/earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --live
python tools/earnings_scenario.py "DAY|62.5|2026-02-20|CALL" --cost 2.15 --crush 60 --no-guide
python tools/earnings_scenario.py "TOST|25|2026-04-17|CALL" --cost 1.04 --straddle --put-cost 0.50
```
- Models post-earnings option values accounting for IV crush (second-order Greek approximation)
- Straddle mode (`--straddle`): models both call+put at same strike with per-leg and combined output
- Answers "how much does the stock need to move for holding to beat selling now?"
- Scenario table with expected/historical moves, breakeven, and "vs Sell Now" column
- Crush sensitivity matrix across 5 EI severity tiers (minimal through severe)
- Two modes: database (previous close) or `--live` (current Greeks from Tradier API)
- Built-in interpretive guide (suppress with `--no-guide`)
- Full docs: `docs/earnings-scenario-calculator.md`

---

## TUI Development Accelerator

(`tools/launch_claude_dev.py`)
```bash
# Integrated into Morning View TUI - press Ctrl+E on any screen
```
- Global hotkey: `Ctrl+E` spawns Claude Code session with context
- Auto-detects current screen and file path
- Modal input for development requests
- Passes file reference, screen name, reproduction steps, log location
- Works in both query mode and admin mode
- Zero context switching - stays in TUI while Claude works in new window

**Files:**
- `tools/launch_claude_dev.py` - Launcher script (batch file approach)
- `morning_view/modals/claude_dev_modal.py` - Input modal component
- `mv_main.py` - Global hotkey binding at app level

**Usage:** Press `Ctrl+E` anywhere in Morning View TUI, type request, hit Enter

---

## Key Database Tables — Detailed Reference

**Full schema reference:** `data/datalake_schema_2026-01-01.md` — complete table definitions, column lists, and indexes.

- **flow_options_scans**: Intraday options scan data — the largest table (23M+ rows, ~100K rows/cycle). Updated every FM cycle (~15-20x/day). Archived via Tier 1 (15-day MOVE). **Use only when intra-day scan information is needed** (e.g., real-time position checks during market hours). For option-level data in analysis, reports, or enrichment pipelines, **prefer `option_contracts` or `option_symbol_summary`** — they have cleaner end-of-day snapshots with full Greeks, IV, volume, and OI for the entire KLMN universe (not just FM subset).
- **flow_alerts**: Options flow alerts with profitability tracking
- **flow_watchlist_daily**: Daily watchlist entries from flow alerts, with buy-the-dip detection and news sentiment enrichment (news_sentiment_score, news_sentiment_label, news_article_count — added Feb 2026)
- **flow_symbol_summary**: Focused daily alert tracking for Flow Monitor (10 columns, selective population, Oct 16 2025 migration)
- **market_daily_summary**: Daily market metrics with Bull/Bear direction and regime classifications
- **option_contracts**: Contract-level OI tracking with Greeks/IV (66 columns, 1.2M+ rows) - formerly oi_daily
- **option_symbol_summary**: Symbol-level OI/IV/Greek summaries (93 columns, universal coverage) - formerly oi_symbol_summary
- **symbol_metadata**: Company sector and fundamentals for KLMN 800 universe
- **earnings_upcoming**: Upcoming earnings with expected moves, relative underpricing (recent-6Q avg vs market expectation), play signals (AVOID/NEUTRAL/WATCH/BUY/STRONG BUY), and alerts (enriched by ei_moves_upcoming.py). `historical_avg_move_pct` = recent 6Q average (signal driver), `historical_avg_move_alltime_pct` = all-time average (transparency), `historical_quarters_used` = data depth (1-6). Config: `earnings_play.recent_quarters`.
- **historical_prices**: Daily OHLC price data
- **earnings_events**: Earnings archive with trading journal (notes, tags, sentiment) — archived to sector DBs via Tier 3. Denormalized outcome columns (Apr 2026): `actual_move_1day_pct`, `actual_max_move_pct`, `move_vs_expected_pct`, `iv_collapse_pct`, `outcome_updated_at` — written back from `ei_post_earnings_calc.py` for at-a-glance historical view.
- **earnings_snapshots**: End-of-day OHLC, IV, OI, volume snapshots around earnings (T-7 to T+5). Rewritten Apr 2026 — "yesterday alignment" captures previous complete trading day's data each morning. Sources: `historical_prices` (OHLC + stock volume) + `option_symbol_summary` (IV, OI, option volume). Schema includes `open_price`, `high_price`, `low_price`, `close_price`, `volume`, `option_volume`, `iv_30dte`, `iv_front_month`, `iv_45dte`. 1292+ rows, not in archive tiers.
- **earnings_moves**: Price moves, IV changes (buildup/collapse/crush), expected move, and move-vs-expected post-earnings (9K+ rows) — not in archive tiers. Primary source: `earnings_snapshots` for price moves, `option_symbol_summary` for IV metrics (fallback to `historical_prices` if snapshots missing).
- **earnings_sector_effects**: Sector sympathy and arbitrage opportunities — currently empty, not in archive tiers
- **industry_peer_mappings**: Industry-based peer relationships (742 symbols, reference data)
- **trade_executions**: Robinhood trade fills parsed from Gmail. One row per fill (immutable log). Dedup by `email_message_id`. `fill_price` is per-share (options: email_price/100). `position_key` = `SYMBOL|type|option_type|strike|expiry` for composite joins. Editable columns: `notes`, `trade_call_ref`, `review_status`.

**Performance Database (`data/performance.db`)** — operational metrics, not trading data:
- 16 tables tracking execution durations, sub-task breakdowns, item counts for every orchestrator step
- Written end-of-day by Phase 6 via `tools/performance_writer.py`
- Schema reference: `docs/performance_tracking_enhancement/performance_db_schema.md`
- Diagnostic queries: `autofix/reference/AUTOFIX_CHEAT_SHEET.md` (Performance Database section)
- All `run_*()` methods in `main_runners.py` return structured dicts (`{'success': bool, ...}`) not bools

---

## Database Health Scripts

- `data/health/db_backup.py`: Backup and query database sync
- `data/health/db_archive_sector.py`: Sector-based archiving (active)
- `data/health/db_optimize_sectors.py`: Sector archive optimization (ANALYZE)
- `data/health/backfill_earnings_tradier.py`: Backfill earnings events + moves from Tradier Corporate Calendars API (report dates, fiscal quarter info, BMO/AMC inference). Supports `--dry-run`, `--symbol`, `--moves-only`.
- `data/health/backfill_earnings_yfinance.py`: Backfill earnings events + moves from yfinance (broken for dates after May 2025)
- `data/tradier_historical_backfill.py`: Historical price backfill from Tradier (`--symbols`, `--backfill-2021`)

---

## Core Library Details

- `core/tradier_api.py`: Market data client
- `core/alphavantage_api.py`: Alpha Vantage news API client (25 calls/day)
- `core/symbols_klmn800.py`: Symbol universe definition — ~820 symbols organized by purpose. Source of truth is `symbol_metadata.universe_tier` in datalake.db. Use `get_specialty_list('klmn_800')` for full universe, `get_specialty_list('fm_scan')` for FM subset. **To add or remove symbols, always use `python tools/symbol_lifecycle.py` (--add, --offboard, --restore). Never edit symbol lists manually.** The CLI handles metadata, historical prices, earnings backfill, archive routing, FM baseline, and audit trail in one step.
- `tools/timezone_utils.py`: EST timezone utilities
- `tools/log_utils.py`: Console output toolkit — `beautiful_log()`, `create_status_box()`, `phase_header()`, and all formatted output helpers. Everything flows through this so output reaches both console and `.log` files. See `docs/CONSOLE_DEVELOPER_GUIDE.md` for patterns.
- `tools/decimal_formatter.py`: Database decimal formatting (MANDATORY)
- `tools/performance_writer.py`: End-of-day performance data collection into `data/performance.db` (16 tables)
- `tools/news_sentiment.py`: News sentiment collection and enrichment (replaces `strategies/news_collector/`)
- `tools/symbol_lifecycle.py`: CLI for symbol onboarding, offboarding, universe management. See `tools/lifecycle/README.md`.
- `tools/lifecycle/`: Package with onboarding, offboarding, routing, preflight checks, health check (Phase 6.2), audit trail, UI helpers.
- `tools/email_reader.py`: Gmail API inbox reader for the alerts inbox (config.json gmail_api.account) (OAuth2, full access)
- `tools/trade_ingest.py`: Trade execution parser — ingests Robinhood confirmation emails from Gmail into `trade_executions` table. Runs as orchestrator Steps 1.4 + 3.1. Design doc: `docs/_local/trade_ingest/BRAINSTORM.md (parked)`.
- `strategies/flow_monitor/fm_config.py` & `strategies/option_pipeline/op_config.py`: Strategy configurations
- `strategies/flow_monitor/fm_earnings_signals.py`: Intraday earnings signal tracker — recomputes straddle underpricing from live scan data every N cycles (~hourly), logs signal upgrades/downgrades vs morning baseline. Console only, config toggle.

---

## Subprocess UTF-8 Encoding Example

When using `subprocess.run()` or `subprocess.Popen()` with `capture_output=True` or `text=True`, ALWAYS specify `encoding='utf-8', errors='replace'` to prevent Windows cp1252 encoding errors:

```python
# CORRECT - with UTF-8 encoding
result = subprocess.run(
    [sys.executable, script_path],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace'
)

# WRONG - missing encoding on Windows
result = subprocess.run(
    [sys.executable, script_path],
    capture_output=True,
    text=True  # Will default to cp1252 on Windows!
)
```

---

## Additional Documentation Index

- **Console Output Developer Guide**: `docs/CONSOLE_DEVELOPER_GUIDE.md` - How to build modules with correct console output (toolkit, taxonomy, roles, patterns, checklist)
- **Database Tools**: `docs/database-tools.md` - Detailed tool usage and examples
- **Trading Style**: `docs/trading-style.md` - Ben's trading approach, constraints, and position management
- **News Sentiment Design**: `docs/news_sentiment.md` - Architecture decisions, relevance weighting, API budget, deprecation history
- **Earnings Intelligence Manual Operations**: `strategies/earnings_intel/docs/MANUAL_OPERATIONS.md` - Trading journal, SQL queries, and manual tasks
- **Performance Database Schema**: `docs/performance_tracking_enhancement/performance_db_schema.md` - 16-table schema for `data/performance.db`
- **Deprecation Notes**:
  - `Deprecated/chrome_extension/CHROME_EXTENSION_DEPRECATION.md` - Chrome extension (2025-10-14)
  - News Collector 3-tier system (2026-02-07) - replaced by `tools/news_sentiment.py`
  - Archived code: `tools/Deprecated/`, `strategies/news_collector/Deprecated/`, `Deprecated/`
