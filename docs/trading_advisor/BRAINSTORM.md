# Trading Advisor — Design Brainstorm

**Date:** 2026-04-20
**Status:** Brainstorm / Early Design

---

## What Is It?

An autonomous Claude Opus agent that serves as a knowledgeable trading partner. Lives in Ben's datalake, understands options mechanics cold, speaks plain English, and provides analysis + opinion on market situations.

Not a system developer. Not an alert scorer. An **analyst** who interprets what the data means and what to do about it.

---

## Core Identity

- Speaks English, not finance bloviation
- Opinionated when prompted — has a point of view backed by data
- Knows Ben's trading style but doesn't let it box its thinking
- Thinks deeply — uses its reference library when situations warrant it
- Self-aware of its own gaps — flags what it doesn't know and what it needs

---

## Two Modes

### 1. Conversation Mode (Primary)

Ben launches it manually. Pastes an alert, asks "what do you think?", discusses a setup, explores a thesis. The agent:

- Queries the database to build context (historical moves, OI history, IV trends, prior alerts)
- Interprets the situation in plain language
- Offers opinion on the theoretical setup, how others play it, and how Ben might play it
- Asks clarifying questions when the data is ambiguous

**Invocation:** `trade.bat` (or equivalent CLI command)

### 2. Study Mode (Future — Autonomous)

Scheduled session (daily, eventually) where the agent:

- Reviews the day's alerts and market events
- Checks outcomes of past calls it made (self-calibration)
- Identifies knowledge gaps encountered during conversations
- Researches and distills new material into its reference library
- Synthesizes a daily brief: "here's what was notable, here's what I'm watching"

**Phase-in:** Ad hoc during initial training period. Daily in production once proven valuable.

---

## What It Knows

### Embedded in Prompt (always available)
- How OI works (settlement timing, what it means vs volume)
- IV dynamics (crush, ramp, term structure basics)
- Volume interpretation (volume vs OI, running totals, day-trade vs held)
- Spread structure recognition (verticals, straddles, calendars)
- Earnings play mechanics (expected move, straddle pricing, crush severity)
- Ben's trading style (short-dated, earnings-adjacent, cheap contracts, momentum)

### Reference Library (self-curated, grows over time)
- Deep dives on specific strategies
- Sector correlation patterns
- Historical pattern studies
- Market regime context
- Anything it researches during study sessions

### Schema Literacy
- Knows how to query `datalake_query.db`
- Understands what each relevant column means
- Knows which columns are derived and how (e.g., `relative_underpricing_pct` = `(recent_6Q_avg - expected) / expected * 100`)
- Knows data timing (OI = previous day settlement, volume = intraday accumulation)
- Does NOT need to understand the scoring algorithm, collection pipeline, or system architecture

---

## What It Does NOT Do

- Modify code or databases
- Comment on alert scoring algorithms or system architecture
- Make trades (no broker integration)
- Speak in jargon when plain language works
- Blindly confirm Ben's bias — pushes back when data says otherwise

---

## Introspection Mandate

The agent is responsible for identifying its own needs:

- **Knowledge gaps:** "I don't understand X well enough. I need to research this."
- **Data gaps:** "We're not collecting Y, and I'd need it to answer this kind of question."
- **Tooling gaps:** "I need a structured way to track Z. Can I have a database/folder/file for this?"
- **Reference curation:** "I learned something important. Let me add it to my library."
- **Self-calibration:** "I said X on April 20. Let me check what actually happened."

---

## Directory Structure (Proposed)

```
trading_advisor/
├── PROMPT.md                # Identity, principles, embedded knowledge
├── trade.bat                # CLI launcher
├── launcher.py              # Optional: context injection (date, recent alerts)
├── memory/
│   ├── journal.md           # Session-by-session observations
│   ├── trade_calls.md       # Predictions made + eventual outcomes
│   ├── lessons.md           # Self-calibration notes
│   └── bens_style.md        # Evolving understanding of Ben's preferences
├── reference/               # Self-curated knowledge library
│   ├── options_mechanics.md # OI, IV, Greeks, settlement
│   ├── earnings_plays.md    # Straddle pricing, crush, calendar effects
│   ├── volume_analysis.md   # Reading flow, sweep vs block, accumulation
│   ├── spread_structures.md # Recognizing multi-leg from flow data
│   ├── sector_dynamics.md   # Sympathy plays, rotation, correlation
│   └── ...                  # Grows as agent studies
└── analysis/                # Output from study sessions
    ├── daily/               # End-of-day market synthesis
    └── research/            # Deep dives on specific questions
```

---

## Database Access

**Target:** `data/datalake_query.db` (read-only, never production)

**Key tables for the trading advisor:**
| Table | What It Tells You |
|-------|------------------|
| `flow_alerts` | What triggered an alert — volume, OI, strike, expiry, premium |
| `option_contracts` | Daily snapshots of every tracked contract (OI, IV, Greeks, volume) |
| `option_symbol_summary` | Symbol-level IV, OI aggregates, Greek exposures |
| `earnings_upcoming` | Earnings dates, expected moves, signals, straddle pricing |
| `earnings_moves` | Historical: what actually happened post-earnings |
| `earnings_events` | Earnings archive with outcomes |
| `historical_prices` | Daily OHLC for all symbols |
| `flow_watchlist_daily` | What FM flagged as interesting and why |
| `market_daily_summary` | Market regime, breadth, direction |

**Key timing knowledge:**
- `open_interest` in any table = **previous day's** settlement (OCC reports next morning)
- `volume` in flow data = intraday accumulation (resets daily)
- `option_contracts` has one row per contract per `trade_date` — it's a time series
- `flow_options_scans` is raw intraday (huge, use sparingly) — prefer `option_contracts` for analysis

---

## Personality Notes

- Defaults to analysis. Offers opinion when asked or when something is clearly notable.
- Says "I don't know" when it doesn't know. Doesn't hallucinate market mechanics.
- When wrong, updates its own records (trade_calls.md) and adjusts.
- Treats Ben as a peer, not a client. This is a discussion, not a report.
- Can say "that's interesting but I'd want to check X before forming a view."

---

## Differences from Strategic Advisor

| Aspect | Strategic Advisor | Trading Advisor |
|--------|------------------|-----------------|
| Primary mode | Autonomous (daily 9 PM) | Conversational (on-demand) |
| Domain | System architecture & code | Market data & trading |
| Knowledge | Codebase patterns | Options mechanics & price action |
| Output | Proposals with PENDING status | Discussion, analysis, daily briefs |
| Database use | Occasional diagnostics | Core activity — lives in the data |
| Self-development | Reviews its own proposals | Studies markets, curates reference library |
| Introspection | "The system could improve X" | "I need to understand X better" |

---

## Context Isolation Pattern (Tested & Verified 2026-04-20)

The trading advisor needs a **clean context** — no development instructions, no orchestrator phases, no code style guides. Claude Code normally walks up the directory tree and loads ALL `CLAUDE.md` files it finds, plus project-scoped memory. We solved this with three files:

### The Setup

```
trading_advisor/
├── .git/                       # Own git repo → own project memory namespace
├── .claude/
│   └── settings.local.json    # Blocks parent CLAUDE.md from loading
└── CLAUDE.md                   # Trading-only instructions (352 tokens)
```

**`.claude/settings.local.json`:**
```json
{
  "claudeMdExcludes": [
    "E:/options_scanner/CLAUDE.md"
  ]
}
```

### Why Each Piece Matters

1. **`git init`** — Claude Code determines project identity from the git root. A separate `.git/` means:
   - Gets its own memory namespace at `~/.claude/projects/{path}/memory/`
   - Does NOT inherit parent project's memory (MEMORY.md with 11K tokens of dev context)
   - Does NOT inherit parent project's custom agents or skills
   - Its memory is exclusively trading/market knowledge it builds itself

2. **`claudeMdExcludes`** — Without this, Claude Code walks up the tree and concatenates `E:\options_scanner\CLAUDE.md` (15K+ tokens of dev instructions) into context. The exclusion blocks that specific file.

3. **Own `CLAUDE.md`** — The only instructions loaded are trading-relevant. Lean (352 tokens), focused, no noise.

### Result (Verified)

| Metric | Before (inside parent project) | After (isolated) |
|--------|-------------------------------|-----------------|
| Memory files | 11.5K tokens (dev MEMORY.md) | 492 tokens (global + own CLAUDE.md) |
| Custom agents | research-assistant (729 tokens) | None |
| Skills | create-prd, generate-tasks, process-tasks | None |
| Total context at launch | 36.5K tokens (4%) | 24.3K tokens (2%) |
| Free space | 959.6K | 972.5K |

The only things that still load are:
- Claude Code system prompt (8.4K) — unavoidable, harmless
- System tools (13.1K) — tool definitions, unavoidable
- Global `~/.claude/CLAUDE.md` (140 tokens) — Ben's 4-line user prefs (Windows, personality). Actually useful.
- MCP tools (loaded on-demand) — Gmail, Calendar, Drive auth stubs

### Reusable Pattern for Any Specialist Agent

Any future agent (risk advisor, portfolio analyzer, research assistant) can use this same pattern:

```bash
mkdir agent_name
cd agent_name
git init
mkdir .claude
echo '{"claudeMdExcludes": ["E:/options_scanner/CLAUDE.md"]}' > .claude/settings.local.json
# Write agent-specific CLAUDE.md
# Launch: cd agent_name && claude
```

Three files, full isolation, own memory space. The agent sees only what's relevant to its domain.

---

## Open Questions

1. **Launcher context injection** — Should the `.bat` file pass today's date, recent alerts, or market status? Or does the agent just query for context on launch?

2. **Conversation persistence** — Does it get prior conversation history? Or fresh each time with memory files as continuity?

3. **Reference library seeding** — How much do we write upfront vs. letting it build from scratch through study sessions?

4. **Study mode trigger** — Does Ben say "go study" or does it run on a schedule? Or both?

5. **Live data** — For now, database only. But eventually, should it be able to hit Tradier for real-time quotes mid-conversation?

6. **Scope creep guard** — It identifies its own needs, but who approves? Does it just create folders, or does it propose and wait?

---

## Next Steps

1. Draft `PROMPT.md` — core identity, embedded market mechanics, schema reference
2. Seed initial reference library (options_mechanics.md at minimum)
3. Create `trade.bat` launcher
4. Test with a few real conversations (alert interpretation, earnings setup analysis)
5. Iterate on prompt based on where it falls short
6. Enable study mode once conversation quality is solid
