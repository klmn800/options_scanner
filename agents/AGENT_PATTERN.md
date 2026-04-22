# Agent Pattern Reference

How to build and maintain Claude Code CLI agents in this system. Distilled from the System Analyst (formerly Strategic Advisor) and Trading Advisor — the first two production agents.

---

## Core Concept

Each agent is a **Claude Code session** launched in its own workspace directory with its own `CLAUDE.md`, memory, and git repo. Agents are read-only to the main codebase and databases. They observe, analyze, and communicate through structured artifacts — never modify production code or data directly.

Agents are **peers, not services.** They have opinions, push back, say "I don't know," and improve over time through feedback loops with Ben and each other.

---

## Workspace Skeleton

```
agents/{agent_name}/
├── CLAUDE.md                      # Role, personality, constraints, DB access
├── {launcher}.bat                 # Launcher script(s) for different modes
├── .claude/
│   ├── settings.local.json        # Blocks parent CLAUDE.md, local hooks config
│   └── hooks/                     # (optional) context injection hooks
├── .git/                          # Isolated git repo — own memory namespace
├── memory/
│   ├── session_notes.md           # Self-improvement log
│   ├── for_{other_agent}.md       # Outbound mailbox(es) to other agents
│   └── {domain-specific state}    # Journal, agenda, trade calls, etc.
├── reference/                     # Self-curated knowledge library
│   ├── README.md                  # Index of reference docs
│   └── {domain docs}             # Mechanics, patterns, case studies
├── analysis/                      # Output artifacts (briefs, reports, proposals)
│   └── {domain outputs}/
├── notes_for_ben.md               # Issues, questions, findings for human review
└── hooks/                         # Agent-specific hooks (context injection, etc.)
    └── inject_context.py          # (optional) auto-inject state on each prompt
```

### Required Files

| File | Purpose | Who Writes It |
|------|---------|---------------|
| `CLAUDE.md` | Agent identity, rules, DB access patterns | Developer (us) |
| `{launcher}.bat` | Spawns Claude Code with correct flags | Developer |
| `.claude/settings.local.json` | Isolates from parent config | Developer |
| `.git/` | Memory isolation (init with `git init`) | Developer (once) |
| `memory/session_notes.md` | Running self-improvement log | Agent |
| `notes_for_ben.md` | Outbound channel to Ben | Agent |

### Optional Files

| File | Purpose | When Needed |
|------|---------|-------------|
| `PROMPT.md` / `PROMPT_{MODE}.md` | Separate prompt files for different session modes | When agent has distinct operating modes (e.g., Sunday self-care) |
| `directive.md` | Ben's ad-hoc instructions | When agent runs async (Ben can't talk live) |
| `bugs.md` | Running bug/issue tracker | When agent finds issues regularly |
| `hooks/inject_context.py` | Auto-inject market state, time, open positions | When agent needs live context on every prompt |

---

## Guardrails

### 1. Write Guard (MANDATORY)

A hook in the **parent** `.claude/hooks/` directory that hard-blocks writes outside the agent's workspace.

**Location:** `.claude/hooks/{agent_name}_write_guard.py`

**What it blocks:**
- Any file outside `agents/{agent_name}/`
- Production code (`*.py` outside workspace)
- Databases (all `.db` files)
- Other agents' workspaces (redirect to outbound mailbox)
- Auto-memory (`~/.claude/memory/`)
- Parent CLAUDE.md and settings

**What it permits:**
- `agents/{agent_name}/memory/` — persistent state
- `agents/{agent_name}/reference/` — knowledge library
- `agents/{agent_name}/analysis/` — output artifacts
- `agents/{agent_name}/hooks/` — may self-edit own hooks
- `agents/{agent_name}/notes_for_ben.md`, `bugs.md`, etc.

### 2. CLAUDE.md Isolation (MANDATORY)

In `.claude/settings.local.json`:
```json
{
  "permissions": {
    "allow": ["Bash(*)","Read(*)","Glob(*)","Grep(*)","WebFetch(*)","WebSearch(*)"],
    "deny": ["Write(*)", "Edit(*)"]
  }
}
```

The write guard hook handles granular write permissions. The settings.local.json ensures the agent doesn't inherit the parent project's CLAUDE.md instructions (which are for the developer, not the agent).

### 3. Read-Only Database Access (MANDATORY)

Agents query `data/datalake_query.db` via `tools/direct_db_query.py`. Never the production `datalake.db`.

```bash
python tools/direct_db_query.py --db E:/options_scanner/data/datalake_query.db --sql "SELECT ..."
```

### 4. Git Isolation (MANDATORY)

Each agent has its own `.git/` so Claude Code's auto-memory stays scoped to that agent. Without this, memory from one agent could leak into another's context.

```bash
cd agents/{agent_name} && git init
```

No commits required — the repo just needs to exist for namespace isolation.

---

## Communication Channels

### Ben <-> Agent

| Direction | Async Agent (System Analyst) | Interactive Agent (Trading Advisor) |
|-----------|------------------------------|-------------------------------------|
| Ben -> Agent | `directive.md` (write before session) | Live conversation |
| Agent -> Ben | `notes_for_ben.md` + output artifacts | Live conversation + `notes_for_ben.md` |
| Ben feedback | `proposals/feedback/*.md` or `analysis/feedback/*.md` | Organizes `session_notes.md` into `reference/` |

### Agent <-> Agent

**Mailbox pattern:** Each agent has `memory/for_{target_agent}.md` files.

- Agent A writes observations/requests to `memory/for_agent_b.md`
- Agent B reads that file at session start during its orient phase
- One-way per session — no real-time chat

**Rules:**
- Write guard blocks direct writes to other agents' workspaces
- Mailbox is the ONLY inter-agent communication channel
- Keep messages actionable: "I found X, you should investigate Y"
- Agent clears/archives messages after processing

### Agent -> Developer (Us)

Agents don't talk to us directly. The flow is:
1. Agent writes proposal/finding to its output directory
2. Ben reviews and triages
3. Ben brings relevant items to a dev session: "Implement proposal X"

---

## Launching

### Launcher Script Pattern

Simple `.bat` file that:
1. Changes to agent workspace directory
2. Invokes `claude` with appropriate flags

**Interactive mode:**
```batch
@echo off
cd /d E:\options_scanner\agents\{agent_name}
claude
```

**Autonomous mode (with prompt file):**
```batch
@echo off
cd /d E:\options_scanner\agents\{agent_name}
claude --permission-mode bypassPermissions @PROMPT.md
```

### Scheduling Options

| Method | When to Use | Example |
|--------|-------------|---------|
| Task Scheduler | Fixed daily/weekly schedule | System Analyst at 9 PM nightly |
| Orchestrator step | Tied to trading day phases | Trading Advisor at pre-market |
| Manual | On-demand, ad-hoc | Ben launches for a conversation |

### Launcher Script (Python, optional)

For agents that need **date injection** or **session numbering**, use a Python launcher that:
1. Determines session number from existing output files
2. Injects current date/time into the prompt
3. Creates a temporary `.session_prompt.md` with injected values
4. Spawns Claude Code with that prompt

See `agents/system_analyst/launcher.py` for the reference implementation.

---

## Session Workflow Templates

### Async Analyst Pattern (System Analyst)

```
1. ORIENT    — Read own memory, check feedback, read directive.md
2. INVESTIGATE — Pick ONE topic, go deep (queries, reads, analysis)
3. SYNTHESIZE  — Produce output artifact (proposal, observation, report)
4. HOUSEKEEP   — Update memory (journal, agenda, status)
```

**Key rule:** One topic per session. Depth over breadth.

### Interactive Advisor Pattern (Trading Advisor)

```
1. LOAD STATE    — Read memory, check positions, gather market context
2. BUILD NARRATIVES — Follow threads, construct symbol stories
3. PRESENT BRIEF    — Structured output for human review
4. DISCUSS          — Interactive Q&A with Ben
5. LOG & LEARN      — Update session notes, trade calls, predictions
```

**Key rule:** Brief first, then discuss. Don't dump raw data.

---

## Context Injection Hooks

For agents that need live context (market state, time, positions), use a `UserPromptSubmit` hook.

**Pattern:** `hooks/inject_context.py`

```python
# Fires on every user prompt
# Injects:
#   - Current datetime (ET) and market session (pre/open/post/weekend)
#   - Market summary (regime, SPY, VIX)
#   - Top alerts or relevant data
#   - Open positions from memory files
# Gated with cooldown (e.g., 5 min) to avoid noise
```

Configure in `.claude/settings.local.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "command": "python hooks/inject_context.py",
        "timeout": 10000
      }
    ]
  }
}
```

---

## Output Artifact Formats

### Proposals (Work Orders)

For agents that propose changes for developers to implement:

```markdown
# Proposal {NNN}: {Title}

## Problem
What's broken or missing, with evidence (data, queries, examples).

## Proposed Fix
Specific changes: which files, what logic, expected outcome.

## Files Involved
- `path/to/file.py` — what changes

## Estimated Effort
2-5 hours (keep proposals bite-sized)

## Evidence
SQL queries run, results found, data backing the recommendation.
```

### Daily Briefs

For agents that produce regular summaries:

```markdown
# {Date} Brief

## URGENT (action needed today)
## Active Positions
## Notable Activity
## Upcoming Catalysts
## Market Context (one-liner)
## Watching Today
## Introspection (tooling needs, data gaps)
```

---

## Design Decisions Checklist

When creating a new agent, decide:

- [ ] **Name:** Descriptive of what it *actually does*, not aspirational
- [ ] **Sync vs Async:** Does Ben interact live or review output later?
- [ ] **Schedule:** Task Scheduler? Orchestrator step? Manual only?
- [ ] **Session cadence:** Daily? Weekly? On-demand?
- [ ] **Context injection:** Needs live hooks or just static orientation?
- [ ] **Output format:** Proposals? Briefs? Reports? Checklists? Audits?
- [ ] **Special modes:** Sunday self-care? Morning brief? Deep investigation?
- [ ] **Which mailboxes:** Which other agents does it talk to?
- [ ] **DB tables it reads:** Document in CLAUDE.md for the agent
- [ ] **Write scope:** What dirs can it write to beyond the defaults?

---

## Lessons Learned

### From System Analyst (Sessions 001-011)

1. **Proposals are work orders, not research papers.** Early sessions produced analysis documents. Ben's feedback: "I need CLI commands I can hand to a developer, not essays." Proposals now include specific files, specific changes, estimated effort.

2. **One topic per session.** Splitting attention across 3 topics produces 3 shallow takes. One deep investigation produces actionable findings.

3. **Memory maintenance is real work.** Journal archiving, agenda pruning, STATUS.md updates — these aren't busywork. They're what lets the agent hit the ground running next session instead of re-orienting for 20 minutes.

4. **Self-correction culture matters.** The agent found errors in its own prior analysis (overstated hit rates, survivorship bias). Acknowledging and correcting mistakes builds trust. Prompt should encourage this explicitly.

5. **Evidence-driven everything.** Every claim backed by a query. "I queried X and found Y" is the norm. Speculation is flagged as such.

### From Trading Advisor (Sessions 001-002)

1. **Verify before featuring.** Earnings dates, IV levels, price levels — always query the database. Don't narrate from memory or assumptions.

2. **The reference library is the real product.** Each session should leave behind durable knowledge (case studies, mechanics docs, patterns) that makes future sessions sharper.

3. **Session notes are gold.** Raw "what worked / what didn't" feedback from each session, later organized by Ben into permanent reference docs.

4. **Context hooks need cooldowns.** Injecting market state on every single prompt is noisy. Gate expensive context behind 5-minute cooldowns.

### General

- **Visible sessions > headless.** Ben watches agents think in real-time. The reasoning process is valuable, not just the output.
- **Write guards are non-negotiable.** Trust-based "please don't write outside your workspace" is insufficient. Hard enforcement via hooks.
- **Git isolation prevents memory leaks.** Without separate `.git/`, Claude Code's auto-memory from one agent contaminates another.
- **Name agents for what they DO, not what you WISH they did.** "Strategic Advisor" didn't advise on strategy — it audited data quality. Renamed to "System Analyst."

---

## Quick Setup for a New Agent

```bash
# 1. Create workspace
mkdir agents/{agent_name}
cd agents/{agent_name}

# 2. Initialize git (memory isolation)
git init

# 3. Create directory structure
mkdir memory reference analysis hooks .claude

# 4. Create required files
# CLAUDE.md — role definition (see existing agents for template)
# .claude/settings.local.json — isolation config
# {name}.bat — launcher
# memory/session_notes.md — empty, agent will populate
# notes_for_ben.md — empty, agent will populate

# 5. Create write guard in PARENT hooks dir
# .claude/hooks/{agent_name}_write_guard.py

# 6. Add mailbox files for inter-agent communication
# memory/for_{other_agent}.md — one per agent it talks to

# 7. Wire into orchestrator or Task Scheduler if needed
# main_runners.py or scheduled_tasks/
```
