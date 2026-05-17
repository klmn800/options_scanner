# Agent Pattern Reference

How to build and maintain Claude Code CLI agents in this system. Distilled from the System Analyst, Trading Advisor, and Market Analyst — the three production agents (plus the more narrowly-scoped Earnings Researcher). MA was split out of TA on 2026-05-17 per Proposal 027 (SA/TA/Ben roundtable 2026-05-13): TA shrank to morning + interactive, MA owns evening research + grading. The split introduced a new inter-agent pattern — the **graduation gate** — described below.

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

A hook in the **parent** `.claude/hooks/` directory that hard-blocks writes outside the agent's workspace. Lives outside the agent's workspace so the agent cannot edit its own guard.

**Location:** `.claude/hooks/{agent_name}_write_guard.py`

**What it blocks (with contextual guidance):**
- Production code (`*.py` outside workspace) — "write a proposal or update bugs.md"
- Databases (all `.db` files) — "use direct_db_query.py to read"
- Other agents' workspaces — "use your outbound mailbox instead"
- Settings files — "propose the change, Ben will review"
- Anything else outside workspace — "write to memory/, proposals/, or create a subdirectory"

**What it always permits:**
- `agents/{agent_name}/memory/` — persistent state
- `agents/{agent_name}/reference/` — knowledge library
- `agents/{agent_name}/analysis/` — output artifacts
- `agents/{agent_name}/hooks/` — may self-edit own hooks
- `agents/{agent_name}/notes_for_ben.md`, `bugs.md`, etc.

**Per-agent exceptions (configurable):**
Some agents may be granted write access beyond their workspace. For example, the System Analyst can write to:
- `~/.claude/projects/.../memory/` — to update auto-memory so Ben's dev sessions have context

Exceptions are added as additional allowed prefixes in the write guard script. Document them in the guard's header comment.

### 2. Settings Isolation (MANDATORY)

The agent's `.claude/settings.local.json` serves three purposes:

1. **Excludes the parent CLAUDE.md** (developer instructions, not for the agent)
2. **Configures hooks** (write guard + context injection)
3. **Controls permissions** (allow python for queries, deny sqlite3 CLI)

```json
{
  "permissions": {
    "allow": ["Bash(python *)"],
    "deny": ["Bash(sqlite3 *)"]
  },
  "claudeMdExcludes": ["E:/options_scanner/CLAUDE.md"],
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "python E:/options_scanner/agents/{agent_name}/hooks/inject_context.py",
          "timeout": 10000
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [{
          "type": "command",
          "command": "python E:/options_scanner/.claude/hooks/{agent_name}_write_guard.py",
          "timeout": 5000
        }]
      }
    ]
  }
}
```

The write guard hook (in the parent `.claude/hooks/`) handles granular write permissions. The `sqlite3` deny prevents direct database CLI access — agents should use `direct_db_query.py` which opens databases in read-only mode.

### 3. Read-Only Database Access (MANDATORY)

Agents query `data/datalake_query.db` via `tools/direct_db_query.py`. Never the production `datalake.db`.

```bash
python tools/direct_db_query.py --db E:/options_scanner/data/datalake_query.db --sql "SELECT ..."
```

### 4. Git Isolation (MANDATORY)

Each agent has its own `.git/` which serves two critical purposes:

1. **Project root detection:** Claude Code identifies the project root by finding the nearest `.git/`. Without it, the agent's `.claude/settings.local.json` would be ignored — Claude Code would walk up to the parent repo's `.git/` and load the parent's settings instead (which are Ben's dev settings, not the agent's).

2. **Memory isolation:** Claude Code's auto-memory is scoped per project. Without a separate `.git/`, memory from one agent could leak into another's context.

```bash
cd agents/{agent_name} && git init
```

No commits required — the repo just needs to exist. The parent `.gitignore` should include `agents/{agent_name}/` to prevent the parent repo from treating it as a submodule.

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
- Mailbox is the ONLY inter-agent communication channel (the graduation gate, below, is the OTHER cross-agent channel — Ben-mediated)
- Keep messages actionable: "I found X, you should investigate Y"
- Agent clears/archives messages after processing

### Graduation Gate (MA -> TA, Ben-mediated)

Introduced 2026-05-17 with the MA/TA split. Used when one agent needs to deliver durable reference material (patterns, lessons, mechanics, case studies) to another agent's read-only reference library.

**Flow:**
1. Source agent (e.g., MA) drafts content with YAML frontmatter in `agents/<source>/reference/staging/<file>.md`. Required keys: `title`, `type`, `hypothesis`, `sample_size`, `hit_rate`, `date_range`, `confidence`, `confidence_rationale`, `session`, `drafted`, `status`, `supersedes`.
2. Source agent iterates until `status: ready_for_review`, then pings Ben via `notes_for_ben.md`.
3. Ben runs `python tools/graduate_reference.py <filename>` (or copies manually). Tool copies file into the **target agent's** `reference/`, strips frontmatter, archives staged copy to `staging/promoted/`.
4. Target agent reads the graduated file in its own `reference/` at session start. Target's write guard blocks the agent from editing its own reference (mechanical enforcement of "Ben is the gate").

**Why a gate and not direct cross-agent writes:**
- Prevents the source agent from self-promoting findings (calibration discipline)
- Prevents the target agent from cherry-picking what to internalize (consistency discipline)
- Ben gets a per-file review checkpoint, with three outcomes: promote / send back with notes / decline

**When to use this pattern vs the mailbox:**
- Mailbox: transient/actionable signals ("watch for X tomorrow," "noticed Y, worth validating")
- Graduation: durable knowledge the target agent will rely on across many sessions
- If the source agent finds itself sending the same calibration nudge weekly, that's a graduation candidate

**When NOT to use:** for system-level changes (schema, pipelines, code), use proposals to the System Analyst instead. The graduation gate is for inter-agent knowledge transfer, not engineering work orders.

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
claude --permission-mode auto @PROMPT.md
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

Every agent needs a `UserPromptSubmit` hook to inject context. Two patterns exist:

### Pattern A: CLAUDE.md Injection (all agents)

Since each agent has its own `.git/` project root, it doesn't automatically load the parent project's CLAUDE.md. The hook reads and injects it so the agent has full system context (architecture, DB schemas, conventions).

```python
# hooks/inject_context.py — minimal version
# Reads E:\options_scanner\CLAUDE.md and outputs it as additionalContext
# See agents/system_analyst/hooks/inject_context.py
```

### Pattern B: Live Context (interactive agents)

For agents that interact during market hours, inject live state on top of CLAUDE.md:
- Current datetime (ET) and market session (pre/open/post/weekend)
- Market summary (regime, SPY, VIX)
- Top alerts or relevant data
- Open positions from memory files
- Gated with cooldown (e.g., 5 min) to avoid noise

```python
# See agents/trading_advisor/hooks/inject_context.py for full implementation
```

Configuration is in `.claude/settings.local.json` (see Settings Isolation section above).

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
