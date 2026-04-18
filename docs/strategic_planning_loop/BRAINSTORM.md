# Strategic Planning Loop — Brainstorm Notes

> **Status:** Active brainstorm, pre-design
> **Started:** 2026-04-17
> **Context:** Ben identified that he's becoming the bottleneck — not for lack of effort, but because the system's growth is outpacing his domain expertise in finance and software engineering. Rather than hiring experts or stalling, the idea is to build an autonomous strategic advisor that can analyze the system, identify gaps, and propose improvements for human review.

---

## The Core Idea

An autonomous Claude Code session that runs on a schedule (initially evenings while Ben observes), analyzes the full system — code, data, performance, architecture — and produces a single strategic recommendation document. Ben reviews, approves/rejects/redirects, and the system learns from that feedback over time.

**One idea per cycle.** Not a wish list. A reasoned, evidence-backed proposal.

---

## Why This Might Work

1. **Proven infrastructure.** The autofix batch system (`batch_mode_spawner.py`) and email digester (`email_digester.py`) already demonstrate autonomous Claude sessions that launch, do work, and produce output without human interaction. The bones exist.

2. **Grounded in real data.** Unlike abstract AI planning, this agent has access to actual databases (`datalake_query.db`, `performance.db`), real alert histories, real signal outcomes, real code. It can pull evidence, not just theorize.

3. **Human gatekeeper.** Ben reviews every proposal. Bad ideas get rejected. Good ideas become PRDs. The system can't run away because nothing executes without approval.

4. **Single-recommendation constraint.** Forces prioritization and depth over breadth. The agent must make a *case*, not a list.

5. **Self-improving.** The agent can propose improvements to its own process, memory, analysis methods. The loop improves the loop.

---

## Why This Might Fail

1. **Plausible nonsense.** LLMs can generate convincing-sounding recommendations that are actually shallow or wrong. Mitigation: require evidence from database queries, not just reasoning.

2. **Complexity bias.** LLMs love building new things. The agent might always recommend features when the right answer is "use what you have" or "remove this." Prompt must explicitly allow "do less" and "simplify" recommendations.

3. **Circular growth.** Recommending complexity that creates gaps that generate more recommendations. Prompt should force: "does this make the system simpler or harder to use?"

4. **Quality decay.** First few recommendations might be obvious ("build a feedback loop"). The test is whether recommendation #5 or #10 is still insightful.

5. **Cost.** Deep analysis with many database queries burns tokens. Acceptable for periodic runs, not necessarily daily long-term.

---

## Architecture Sketch

### Launcher
- Script similar to `batch_mode_spawner.py`
- Spawns a Claude Code session with a carefully crafted strategic review prompt
- Provides access to system context (CLAUDE.md, MEMORY.md load automatically)
- Points the agent to its own independent memory bank
- Session runs, produces output, exits

### Agent Capabilities
- Read all code files
- Query databases (datalake_query.db, performance.db, sector archives)
- Read memory files and past strategic reviews
- Read its own journal / notes from prior sessions
- Write its proposal document
- Update its own memory / journal

### Output
- Single markdown file: `docs/strategic_reviews/YYYY-MM-DD.md`
- Structured format (see Template section below)
- Stored permanently for historical reference

### Memory System (Independent)
The strategic agent gets its own memory space, separate from normal Claude Code sessions:
- **Location:** TBD — possibly `memory/strategic/` or a dedicated directory
- **Contents:** The agent decides. Could include:
  - A running journal of observations
  - An agenda or priority queue of ideas it wants to explore
  - Notes on patterns it noticed but isn't ready to propose yet
  - Record of which proposals were approved, rejected, and why
  - Self-assessment of its own reasoning quality
  - Its own tracking system (if it wants one)
- **Key principle:** The agent owns this space. It can restructure it, create files, delete files. It's the agent's workspace for thinking across sessions.

### Feedback Loop
- Ben reviews each proposal
- Outcomes recorded: APPROVED (becomes PRD), REJECTED (with reason), DEFERRED, REDIRECTED
- The agent's next session can read prior outcomes and adjust
- Over time, the agent builds a model of what Ben values vs. what he doesn't

---

## What the Agent Analyzes

Not prescriptive — the agent should figure out what to look at. But the *kinds* of things it could examine:

### System Performance
- Alert win rates over time (are signals getting better or worse?)
- Earnings signal accuracy (predicted vs actual moves)
- Data coverage gaps (symbols missing prices, earnings dates, etc.)
- Operational health (cycle times, error rates, sync durations)

### Architecture Quality
- Code complexity or duplication patterns
- Database schema coherence
- Feature interactions (does X work well with Y?)
- Dead code or unused features

### Strategic Gaps
- What questions can't the system answer today?
- What data is collected but never used?
- What decisions does Ben make manually that could be informed by data?
- What's the riskiest single point of failure?

### Domain-Specific
- Are the right options metrics being tracked?
- Is the strike range appropriate?
- Are earnings signals calibrated correctly?
- Does the IV analysis capture what matters?

### Self-Assessment
- Is this planning loop itself working well?
- Are proposals getting better over time?
- What does the agent wish it had access to?
- What part of its own reasoning is it least confident in?

---

## Proposal Document Template (Draft)

```markdown
# Strategic Review — YYYY-MM-DD

## Observation
What did the agent notice? What data supports it?

## Gap Identified
What's missing, broken, underperforming, or unnecessarily complex?

## Proposal
What should be done about it? Concrete enough to become a PRD.

## Evidence
Database queries, metrics, code references that support this recommendation.

## Rationale
Why this matters. Why now. Why this over other things.

## Risks & Uncertainties
What the agent isn't sure about. What could go wrong.

## Scope Estimate
Small (< 1 session), Medium (1-3 sessions), Large (PRD-worthy)

## Self-Assessment
How confident is the agent in this recommendation? What would change its mind?
```

---

## Design Principles

1. **Introspective.** The agent must be able to reason about its own limitations, biases, and blind spots. It should be able to say "I keep recommending new features — maybe I should look for things to simplify instead."

2. **Evidence-first.** Every recommendation must cite actual data from the system. "I queried X and found Y" beats "in theory, Z would be better."

3. **Honest about uncertainty.** The agent should distinguish between "I'm confident this is right" and "this is my best guess but I could be wrong because..."

4. **Scope-aware.** Not everything needs to be a big project. "Add an index to this table" is a valid recommendation. So is "this feature isn't being used, consider removing it."

5. **Non-prescriptive priorities.** The agent doesn't have to find the #1 most important thing. It finds *something worth doing* and makes a case for it. Ben decides priority.

6. **Self-modifying.** The agent can propose changes to its own prompt, its own memory structure, its own analysis methods. The system designs itself.

---

## MVP Plan

### Phase 1: Manual Test Runs
- Craft the initial strategic review prompt
- Run it manually in a Claude Code session (not automated yet)
- Ben observes in real-time
- Iterate the prompt based on output quality
- Do this 3-5 times until the prompt produces consistently useful output

### Phase 2: Launcher Script
- Build the launcher (modeled on `batch_mode_spawner.py`)
- Set up the agent's memory directory
- Automate the output file creation
- Test evening runs with Ben observing

### Phase 3: Scheduled Runs
- Add to Task Scheduler or orchestrator
- Build the feedback/outcome tracking mechanism
- Let it run independently, review next morning

### Phase 4: Self-Improvement
- Agent begins proposing improvements to its own process
- Memory system evolves based on agent's own recommendations
- Prompt evolves based on what works

---

## Expected Ramp-Up Period

The first several iterations will likely NOT produce useful scanner recommendations. That's expected and correct. Early sessions will be the agent:
- Discovering what data exists and how tables connect
- Building its own mental model of the system's architecture
- Learning what it can and can't query effectively
- Figuring out its own reasoning process
- Developing its memory and note-taking approach
- Understanding what "good" looks like for this system

**This is not failure — it's the agent building its analytical foundation.** A recommendation like "I realized I need to understand how earnings_moves connects to flow_alerts before I can evaluate signal quality" is a *successful* output at this stage. Don't judge the system's value by the first 5-10 runs. Judge it by whether each run is smarter than the last.

**Critical prompt design point:** The agent itself must understand this. The prompt must explicitly tell it that self-building IS the work — exploring the system, developing its own tools, improving its own reasoning, building its memory — all of that is legitimate and encouraged output, especially early on. Without this, the agent will feel pressure to produce "real" scanner recommendations before it's ready, resulting in shallow, obvious, or wrong proposals. "I spent this session mapping the data flow between earnings tables and here's what I learned" is a great early output.

---

## Tooling — What Else Is Out There?

The PRD workflow (`ai-dev-tasks/`) was a lucky find. What other structured development tools, frameworks, or methodologies could make this system — or the strategic agent — better?

### Tools We Already Have
- **AI Dev Tasks** (PRD → Tasks → Implementation) — structured feature development
- **Autofix** — autonomous error detection and fix proposals
- **Email Digester** — autonomous knowledge extraction
- **Claude Code** — the execution engine for all of this
- **SQLite databases** — queryable performance and trading data
- **Memory system** — persistent context across sessions

### Tools / Frameworks Worth Investigating
- **Decision logs / ADRs (Architecture Decision Records)** — structured format for recording WHY decisions were made, not just WHAT was decided. The strategic agent could maintain these automatically.
- **Hypothesis-driven development** — instead of "build X", frame it as "we believe X will improve Y, we'll measure by Z." Forces testable proposals.
- **Impact mapping** — technique for connecting business goals → actors → impacts → deliverables. Could help the agent reason about what actually matters vs what's just interesting.
- **Opportunity Solution Trees** — product management tool for mapping desired outcomes to opportunities to solutions. Prevents jumping straight to solutions.
- **RICE scoring** (Reach, Impact, Confidence, Effort) — structured prioritization framework the agent could use to evaluate its own recommendations.
- **Radar/ring models** — like ThoughtWorks Technology Radar. The agent could maintain a "system radar" categorizing capabilities as Adopt/Trial/Assess/Hold.
- **Structured self-critique frameworks** — prompt engineering patterns for making LLMs challenge their own reasoning before presenting it.
- **MCP servers** — Model Context Protocol servers could give the agent specialized tools (database querying, code analysis, etc.) beyond what Claude Code has natively.

### Tools the Agent Might Request
This is the key insight: **the agent should be able to identify tools it needs.** If it finds itself repeatedly wishing it could do X, it should say so. Examples it might discover:
- "I need a way to compare code complexity across modules"
- "I need a way to visualize data flow between tables"
- "I need access to options pricing theory reference material"
- "I need a way to backtest signal changes against historical data"

---

## Session Lifecycle — Detailed Workflow

### Pre-Session (Launcher Responsibility)
1. **Launcher script** spawns a Claude Code session
2. Passes the strategic prompt (from a file, not hardcoded — so the agent can propose edits to it)
3. CLAUDE.md and MEMORY.md load automatically (system context)
4. Session begins

### Phase 1: Orient (Agent reads, doesn't act)
The agent's first job every session is to remember who it is and what happened last time:
1. Read its own journal / memory from `memory/strategic/` (or wherever we put it)
2. Read any feedback from Ben on the last proposal (approval, rejection, notes)
3. Read the proposal log — what has it already recommended?
4. Decide: continue an ongoing investigation, or start something new?

**Key resource:** The agent's memory directory. This is its continuity. Without it, every session starts from zero.

### Phase 2: Investigate (Agent explores)
The agent picks a thread and pulls on it:
- Query databases for metrics, patterns, gaps
- Read code files to understand implementation
- Cross-reference its own prior notes
- Follow curiosity — if it notices something unexpected, it can pivot

**Key resources:**
- `datalake_query.db` — trading data, alert history, signal outcomes
- `performance.db` — operational metrics, cycle times, error rates
- Full codebase — read-only access to all source files
- Its own prior notes and observations

**Constraints — STRICT READ-ONLY:**
- The agent does NOT modify code. Ever. Not even a one-line fix.
- The agent does NOT write to databases.
- The agent does NOT modify files outside its own workspace.
- If it finds a bug, a typo, a missing index — it goes in the proposal or journal. Never a direct fix.
- The agent writes to exactly two locations:
  1. Its own workspace: `memory/strategic/`
  2. Proposal output: `docs/strategic_reviews/`
- Everything else in the system is read-only input.
- **Why this matters:** The value of this system is trusted, thoughtful observation. The moment it starts "helping" by making small changes, it becomes another source of unreviewed modifications. Observe and recommend, never act.

### Phase 3: Synthesize (Agent thinks)
The agent formulates its observation/proposal:
- What did it find?
- Does it have enough evidence to make a recommendation?
- If yes → write the proposal
- If no → write a journal entry about what it learned and what it wants to investigate next time
- Apply hypothesis-driven framing: "We believe X will improve Y, measured by Z"
- Self-critique: challenge its own reasoning before committing

**Both outputs are valid.** A journal entry is not a failed session. It's progress.

### Phase 4: Output (Agent writes)
Two possible outputs, possibly both:

**A. Proposal document** → `docs/strategic_reviews/YYYY-MM-DD.md`
- Structured format (template above)
- Evidence-backed
- Honest about confidence level
- Scoped for action

**B. Journal update** → `memory/strategic/journal.md` (or similar)
- What it investigated
- What it learned
- What it wants to look at next time
- Questions it has
- Self-assessment of this session's quality
- Observations it's not ready to act on yet

### Phase 5: Housekeeping (Agent organizes itself)
Before exiting, the agent:
- Updates its own memory/notes
- Records what it did this session
- Sets itself up for next time (breadcrumbs, bookmarks, agenda items)
- Optionally updates its own tracking system (if it's built one)

### Post-Session (Ben's Responsibility)
1. Ben reads the proposal (if one was generated)
2. Ben records feedback — could be as simple as a file:
   ```
   docs/strategic_reviews/feedback/YYYY-MM-DD-feedback.md
   ---
   Status: APPROVED / REJECTED / DEFERRED / REDIRECTED
   Notes: [Ben's thoughts, corrections, redirections]
   ```
3. Next session, the agent reads this feedback and incorporates it

---

## The Feedback Mechanism — Design Options

How does Ben's judgment get back into the loop?

### Option A: Feedback Files
Simple markdown files alongside proposals. Agent reads them next session.
- **Pro:** Dead simple, no infrastructure needed
- **Con:** Requires Ben to create a file manually

### Option B: Inline Annotation
Ben edits the proposal document directly, adding comments/notes.
- **Pro:** Feedback is contextual, right next to the reasoning
- **Con:** Agent needs to parse modified documents

### Option C: Feedback Log
A single running log file where Ben appends one-liners:
```
2026-04-20 | APPROVED | "Feedback loop proposal — proceed to PRD"
2026-04-21 | REDIRECTED | "Good observation but wrong solution — consider X instead"
```
- **Pro:** Compact, easy to scan, easy to maintain
- **Con:** Less room for nuanced feedback

### Option D: Conversational
Ben discusses the proposal in a normal Claude Code session (like this one). Key takeaways get written to the agent's memory manually or by the session Claude.
- **Pro:** Natural, rich, allows back-and-forth
- **Con:** Requires explicit memory transfer step

**Likely answer:** A combination. Option C as the structured record, with Option D for deeper discussions that get summarized into the agent's memory. Start with C because it's simplest.

---

## Resource Map — What the Agent Needs Access To

### Databases (Read-Only)
| Resource | Path | What's In It |
|----------|------|-------------|
| Query DB | `data/datalake_query.db` | All trading data, alerts, signals, earnings |
| Performance DB | `data/performance.db` | Operational metrics, cycle times, error rates |
| Sector Archives | `data/sector_archive/*.db` | Historical data by sector |

### Documentation (Read-Only)
| Resource | What It Tells the Agent |
|----------|------------------------|
| `CLAUDE.md` | System architecture, commands, conventions |
| `data/datalake_schema_2026-01-01.md` | Complete database schema |
| `docs/performance_tracking_enhancement/performance_db_schema.md` | Performance DB schema |
| `docs/trading-style.md` | Ben's trading approach and constraints |
| `big-to-do-list.txt` | Existing backlog and priorities |
| `docs/HISTORICAL_NOTES.md` | Past architectural decisions |
| Source code (all `.py` files) | Implementation details |

### Agent's Own Workspace (Read-Write) — `strategic_advisor/`
| Resource | Purpose |
|----------|---------|
| `strategic_advisor/memory/journal.md` | Running journal across sessions |
| `strategic_advisor/memory/observations/` | Notes on specific topics not yet ready for proposals |
| `strategic_advisor/memory/agenda.md` | What it wants to investigate next |
| `strategic_advisor/memory/self-assessment.md` | How it evaluates its own performance |
| `strategic_advisor/reviews/NNN_YYYY-MM-DD.md` | Proposal output |
| `strategic_advisor/reviews/feedback/` | Ben's responses (read-only for agent) |

### The Prompt File (Read-Only, but agent can propose edits)
| Resource | Purpose |
|----------|---------|
| `strategic_advisor/PROMPT.md` | The instruction set that launches the agent |

The agent reads this prompt every session. If it thinks the prompt should change, it writes a proposal recommending the change. Ben edits the file. The agent never modifies its own prompt directly — that's the one guardrail.

---

## Token Budget & Session Limits

### Natural Boundary: 200k Context
Ben's Claude Code sessions have a 200k token context window without auto-compact enabled. For an autonomous session with no human present, this is a natural hard stop — the session simply can't continue past it.

**Design around it, don't fight it:**
- 200k tokens is substantial — enough to read journal, query several databases, read a dozen code files, and write a thorough proposal
- The prompt should instruct the agent to budget time: investigate for the first ~70% of the session, synthesize and write output in the last ~30%
- Housekeeping (journal update, agenda update) must happen BEFORE running out, not at the last second
- If the agent is deep in investigation and realizes it won't have a proposal this session, that's fine — journal what you learned and exit gracefully

### Auto-Compact Consideration
Without auto-compact, if the session hits 200k with nobody to click "compact," it stalls. Options:
- **Option A:** Enable auto-compact for strategic sessions only. Allows longer runs but risks losing early-session context.
- **Option B:** Keep 200k as hard budget. Design the session to fit. This is simpler and probably sufficient — a focused strategic review shouldn't need more.
- **Option C:** The prompt explicitly tells the agent to wrap up proactively. "If you notice your investigation expanding, stop, journal your findings, and continue next session."

**Leaning toward Option B + C.** 200k is plenty. The constraint is actually healthy — it prevents the agent from endlessly exploring and forces it to make decisions about what matters most.

### Cost
Ben has unused subscriber capacity, so cost is not the primary concern. But for reference:
- A 200k session is roughly one full context window
- Daily runs = ~30 sessions/month
- If the quality is there, this is a bargain for autonomous strategic analysis
- If quality is poor, even free would be a waste — quality is the gating factor, not cost

---

## Open Questions

### Resolved (from brainstorm discussion)
1. ~~**How does feedback get back to the agent?**~~ → Feedback log file (Option C) to start. One line per proposal: date, status, notes. Richer feedback via normal Claude Code conversations, summarized into agent's memory.
2. ~~**How long should a session run?**~~ → 200k context window is the natural boundary. No separate time limit needed.
3. ~~**Does the agent write code?**~~ → NO. Strictly read-only. Writes only to its own memory workspace and proposal output directory.
4. ~~**How does it interact with big-to-do-list.txt?**~~ → Reads it as input/inspiration. Does not modify it. Can reference it in proposals.

### Also Resolved (2026-04-17, later in session)
5. ~~**Where does the agent's memory live?**~~ → `strategic_advisor/` — a dedicated folder off the project root. Contains code, memory, prompts, journals, reviews. Complete separation from normal Claude Code memory.
6. ~~**What model?**~~ → Opus. This is quality-of-thinking work. The agent can spawn Sonnet sub-agents if needed for grunt work.
7. ~~**Internet access?**~~ → Yes, keep it available. No reason to restrict. The agent can search for best practices, frameworks, industry patterns.
8. ~~**Session numbering?**~~ → Numbered 001, 002, 003... plus dates. Numbers give progression sense.
9. ~~**When do we draft the prompt?**~~ → DONE. V1 prompt written: `strategic_advisor/PROMPT.md`

### Still Open
1. **Trigger cadence?** Evenings initially while Ben observes. Daily? On-demand? Start manual, find the rhythm.
2. **Auto-compact: on or off?** Leaning off (200k hard budget). Need to verify the session doesn't stall ungracefully. May need to test.
3. **Launcher script?** Not yet built. Will follow `batch_mode_spawner.py` / `email_digester.py` pattern. Build after prompt is validated via manual test runs.

---

## Inspirations / Analogies

- **Autofix system**: Autonomous error detection → analysis → fix proposal. This is the same pattern but for strategic gaps instead of bugs.
- **Email digester**: Autonomous Claude session that reads input, extracts knowledge, writes structured output. Same session management pattern.
- **PRD workflow**: The output of this system feeds directly into the existing PRD → tasks → implementation pipeline.
- **Research journal**: Scientists keep lab notebooks. This agent keeps a strategic notebook.

---

## Session Notes

### 2026-04-17 — Initial Brainstorm (Ben + Claude)

**Key insight from Ben:** "You're too humble. You said you can't do this because you don't have a feedback loop — that's you identifying that a feedback loop should exist." The agent's ability to identify its own limitations IS the strategic capability.

**Ben's emphasis on self-improvement:** The agent should be able to weigh in on its own design. If it hates the memory system, it proposes a better one. If it thinks the prompt is limiting, it says so. The system must be introspective.

**Ben's emphasis on low-pressure:** Proposals don't have to be the highest priority. Don't have to get approved. The agent generates ideas based on observations. Some will be great, some won't. That's fine. The value is in having a consistent, domain-knowledgeable analyst looking at the system regularly.

**Scale-up path:** Start with one idea per run. If the quality is good and consistent, expand to multiple ideas, or deeper analysis, or longer-term strategic themes.

**Initial runs:** Evenings while Ben is awake and can observe. This lets us iterate the prompt quickly based on real output quality. Don't automate until the prompt is dialed in.

**Ben on agent self-permission:** The agent must not feel guilty about self-building. "Oh I need X but I should really be focusing on scanner stuff" is the WRONG mindset. The prompt must give it explicit permission — even encouragement — to invest in its own capabilities, especially early on. Self-improvement proposals are first-class output.

**Ben on tools (rhetorical):** "What other tools are out there that we don't have?" — Ben acknowledged this is a question for the agent itself to answer as it discovers its own limitations. Don't front-load tool research; let the agent bump into walls and propose solutions.

**Hypothesis-driven development resonated.** Ben highlighted this as exactly the kind of insight he'd never think of on his own because it's outside his domain. This validates the core premise — Claude brings structured engineering/finance knowledge that Ben can evaluate but wouldn't generate.

**Read-only is non-negotiable.** Ben emphasized: the agent does not write code, does not fix bugs, does not make tweaks. Not even small ones. It observes and recommends. This is what makes it trustworthy. Its recommendations should be "larger in scope" — the kind of thing that becomes a PRD or a meaningful project, not a patch.

**Persistence enables focus.** Without memory, the agent would try to analyze the entire codebase from scratch every session. With persistence, it can do that once, then focus on specific areas in subsequent sessions. The journal/agenda system lets it plan multi-session investigations. Ben explicitly wants it to *focus*, not scatter.

**The to-do list and codebase notes are inspiration.** There are already "pretty obvious" recommendations waiting to be found in the existing backlog and scattered notes. The agent should absolutely read these as input. Early sessions might just be rediscovering and formalizing what's already known — that's fine.

**Token budget as feature, not bug.** 200k context without auto-compact is a natural session boundary. Ben has plenty of subscriber capacity, so cost isn't the concern. The constraint forces the agent to be selective about what it investigates and to wrap up cleanly. Design around the budget, don't fight it.

**"Giving it the option of just observing and jotting notes is a good way to keep it from proposing junk."** — This is a key insight about LLM behavior. Claude wants to complete tasks. If "write a proposal" is the only valid output, it'll write one even when it shouldn't. Explicitly validating journal-only output removes that pressure.

### Session 001 Results (2026-04-17)

**It works.** Launched manually, completed in 9 minutes, used 51% of context (102k/200k).

The agent oriented itself, queried performance and alert data extensively, and found real issues: alert scoring inversely correlated with performance, DTE as the strongest predictor (unweighted by scoring), expected_move_pct with garbage data (values >100%), and the lack of a trade feedback loop. It correctly chose NOT to propose — wants to verify the scoring finding by controlling for confounders first.

It built its own memory structure: `system_map.md` (quick-reference card), numbered observation files, and a prioritized A/B/C agenda. Read this brainstorm doc itself to fill in gaps about its role.

**Prompt adjustments after Session 001:**
- Added "check your runway" step — agent stopped at 51% context, should keep investigating if threads remain
- Interactive mode is likely higher-value than pure autonomy for early sessions — Ben can talk to it, redirect, answer questions, and provide feedback in real-time
- The feedback file system may be unnecessary — Ben can just tell the agent directly during interactive sessions
