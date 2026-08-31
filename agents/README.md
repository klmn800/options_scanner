# Agent System

Five autonomous Claude Code CLI agents work alongside the scanner. Each one lives in its
own workspace directory here (`agents/<name>/`), and each workspace is a **separate
private git repo** — they are gitignored in this repository because they contain months
of accumulated research notes, trade discussion, and personal context.

**The framework itself is published.** A sanitized skeleton of all five agents —
launchers, write-guard hooks, prompts, mailbox conventions, and the roundtable
orchestrator, with the domain content stripped — is available at
**[github.com/klmn800/agent_lab](https://github.com/klmn800/agent_lab)**. If you want to
see how these agents are wired, that's the repo to read.

## The pattern

Every agent follows the same shape (full write-up: [`AGENT_PATTERN.md`](AGENT_PATTERN.md)):

- **Workspace** — its own directory with `CLAUDE.md` role definition, prompt files,
  `memory/` for persistent state, and its own `.git/` for history.
- **Write guard** — a Claude Code hook (`.claude/hooks/<name>_write_guard.py`) that
  blocks the agent from writing anywhere outside its workspace. Agents read production
  databases and code; they never modify them.
- **Mailboxes** — `inbox/` directories for human→agent and agent→agent handoffs.
  Processed notes move to `inbox/processed/`.
- **Launcher + schedule** — a `launcher.py` (date injection) wrapped in a `.bat` file,
  fired by Windows Task Scheduler or by the orchestrator.

## The agents

- **System Analyst** (`system_analyst/`) — nightly data-quality auditor. Investigates
  pipeline behavior, files numbered proposals, and reads human feedback files at the
  start of each session to adjust course. The longest-running agent; dozens of its
  proposals have shipped.
- **Trading Advisor** (`trading_advisor/`) — morning briefs and interactive discussion.
  Launched by the orchestrator each market morning; stays open for conversation.
- **Market Analyst** (`market_analyst/`) — evening research and trade-call grading,
  split out of the Trading Advisor. Curates a knowledge library that graduates into the
  Trading Advisor's reference set through a staging gate.
- **Earnings Researcher** (`earnings_researcher/`) — deep-dive earnings dossiers on
  upcoming reports, plus a Sunday week-ahead session.
- **Roundtable** (`roundtable/`) — an orchestrator that convenes multiple agents into a
  moderated discussion on a single question.

## Integration example: the Earnings Researcher trigger

The clearest pipeline↔agent integration point is in the Earnings Intelligence strategy:
`strategies/earnings_intel/ei_lite_refresh.py` (`_spawn_earnings_researcher`). When the
daily earnings-date refresh flags disputes (sources disagreeing on when a company
reports), it spawns an Earnings Researcher session to investigate — fire-and-forget,
gated by `config.json` → `agents.earnings_researcher`. The agent resolves the disputes
in its own workspace; nothing in the production pipeline waits on it or depends on it.

The Trading Advisor launch works the same way (`main_runners.py`,
`_launch_trading_advisor`), gated by `config.json` → `agents.trading_advisor` via
`tools/agent_toggle.py`.
