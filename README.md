# Options Scanner

**A personal options-flow research system: real-time flow monitoring, open-interest
analysis, and earnings intelligence over a ~820-symbol universe — running unattended
every trading day since 2025.**

> **Status: read, don't run.** This is a single-machine personal research system,
> published as a showcase of the architecture, data model, and operational history —
> not a turnkey product. There is no installer, no test suite, and no support; the
> databases it depends on do not ship. Everything here is shaped by one trader's
> workflow on one Windows machine.

## What it is

A Python system that watches the US options market for institutional footprints.
Every weekday, Windows Task Scheduler launches one orchestrated cycle (`main.py`)
that collects pre-market baselines, scans options chains every ~15–20 minutes during
market hours, detects unusual flow, tracks earnings setups, resolves yesterday's
alerts against today's open interest, and closes the day with backups, archives, and
performance tracking. SQLite is the storage engine throughout — the main scan table
alone holds 23M+ rows.

It is also an experiment in **AI-assisted operation**: the system files its own bug
reports (autofix), and a set of autonomous Claude Code agents audit its data quality
and research its trades overnight.

## The daily cycle

| Phase | When | What |
|-------|------|------|
| 1 | 6:35 AM | Pre-market: Option Pipeline, Earnings Intel, metadata, trade ingest, DB sync |
| 2 | 9:15 AM – close | Flow Monitor daemon: ~15–20 scan cycles, alerts, watchlists, news sentiment |
| 3 | 5:00 PM | Evening: trade ingest, Option Pipeline closing snapshot, final sync |
| 4 | post-close | Daily backup, autofix review of the day's queued errors |
| 5 | Fridays | Weekly backup, statistical baselines, earnings refresh, sector archives |
| 6 | post-close | Performance database, symbol health check |

Holiday-aware via the broker API; one cycle per day, exits when done.
Full detail: [ARCHITECTURE.md](ARCHITECTURE.md).

## The four pillars

- **[Flow Monitor](strategies/flow_monitor/README.md)** — intraday scanning of
  options chains (±20% strike band) against statistical baselines. Detects premium
  and volume surprises, dedupes rolls, resolves every alert against next-day open
  interest to grade whether the flow was opening or closing.
- **[Option Pipeline](strategies/option_pipeline/README.md)** — twice-daily
  end-of-day snapshots of every tracked contract (66 columns: OI, IV, Greeks),
  building the multi-day time series the other strategies lean on.
- **[Earnings Intel](strategies/earnings_intel/README.md)** — earnings calendar
  reconciliation across three data sources, IV-crush modeling, straddle
  underpricing signals driven by each symbol's recent-six-quarter move history,
  and T-7→T+5 snapshot windows around every event.
- **[Autofix](autofix/README.md)** — the system's self-healing loop. Runtime errors
  are queued (or, if critical, immediately dispatched) into Claude Code sessions
  that diagnose and propose fixes, with transient-error suppression and recurrence
  escalation.

## The agents

Five autonomous Claude Code agents run alongside the scanner — a nightly
data-quality auditor that files reviewed proposals, a morning trading advisor, an
evening market analyst, an earnings researcher triggered by the pipeline itself when
data sources disagree, and a roundtable orchestrator. Their workspaces are private
(months of personal research), but the full framework — launchers, write-guard
hooks, prompts, mailbox conventions — is published separately as
**[agent_lab](https://github.com/klmn800/agent_lab)**.
Overview and integration points: [agents/README.md](agents/README.md).

## Engineering highlights

- **Alert resolution loop** — every flow alert is graded against the next day's
  open-interest change, turning a stream of "unusual activity" into a labeled
  dataset of opening vs. closing flow.
- **[Earnings scenario calculator](docs/earnings-scenario-calculator.md)** —
  models option and straddle P/L across price/IV scenarios with tiered IV-crush
  assumptions, breakevens included.
- **[Symbol lifecycle management](tools/lifecycle/README.md)** — onboarding,
  offboarding, and ticker renames as first-class operations across every table and
  archive; the symbol universe lives in the database, not in code.
- **Sticky contracts** — once a contract is tracked, it stays tracked even when its
  strike drifts outside the collection band, so time series never silently truncate.
- **[Paper trading engine](docs/paper_trading/README.md)** — broker-sandbox
  positions with engine-managed exits (take-profit / stop-loss / max-hold) on a
  three-state machine, polled every two minutes.
- **[The Print](docs/reference/SOCIAL_POSTING_QUICKSTART.md)** — qualifying flow
  alerts auto-publish to X ([@ThePrintFlow](https://x.com/ThePrintFlow)) with
  filtering, dedup, and a daily cap.
- **[Sector-archive incident postmortem](docs/SECTOR_ARCHIVE_INCIDENT_2026-04-02.md)**
  — a full root-cause writeup of a data-loss incident: what broke, why, what
  changed. Included deliberately; operating a system means owning its failures.

## Project history

- **2025** — built incrementally: Flow Monitor first, then the open-interest
  pipeline, earnings intelligence, and the orchestrator that binds them.
- **Nov 2025** — autofix in production: the system starts filing and triaging its
  own runtime errors through Claude Code sessions.
- **Apr 2026** — git corruption forced a fresh repository (pre-2026 history lives
  only in that lost repo); SSD migration ended a long tail of HDD-era performance
  mysteries.
- **Jun 2026** — the working drive was accidentally reformatted; the system was
  restored from GitHub and agent transcripts, which is why backups and auto-push
  discipline feature so prominently here.
- **Aug 2026** — curated for public release: retired dormant subsystems (Oracle
  text-to-SQL, the Airline Play strategy, the multi-provider AI Council), scrubbed
  credentials from history, and wrote the visitor documentation you are reading.

Details: [docs/HISTORICAL_NOTES.md](docs/HISTORICAL_NOTES.md).

## Data and configuration

No databases ship with this repo. The schema (60+ tables across the datalake,
performance, and paper-trading databases) is documented in
[data/datalake_schema_2026-01-01.md](data/datalake_schema_2026-01-01.md), and the
two-database read/write split is covered in [ARCHITECTURE.md](ARCHITECTURE.md).
Configuration shape: [config.json.example](config.json.example) and
[credentials.json.example](credentials.json.example) mirror the real files with
redacted values. Data sources: Tradier (quotes, chains, calendar), Alpha Vantage
(news sentiment, earnings enrichment), yfinance and Finnhub (earnings dates),
FMP (symbol metadata).

## Built with Claude Code

The system is developed and operated in partnership with Claude Code.
[CLAUDE.md](CLAUDE.md) is the working contract — database rules, safety
restrictions, coding standards, and the handoff protocols the autonomous agents
follow. The autofix pipeline and the agent framework are both built on Claude Code
CLI sessions. Development history, including the AI-assisted parts, is visible in
the commit log.
