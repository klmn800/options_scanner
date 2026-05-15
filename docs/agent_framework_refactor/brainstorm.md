# Agent Framework Refactor — Brainstorm

**Date:** 2026-04-26
**Origin:** Bundles SA Proposal 019 (Modular Agent Prompts) with cross-agent launcher infrastructure work surfaced during the same Sunday session.
**Status:** Brainstorm — not yet a spec, not yet sequenced for build.

---

## Why this is being written

We now have three instances of the "autonomous Claude Code agent" pattern in `agents/`:

- **System Analyst** (`agents/system_analyst/`) — nightly data quality audits, proposals
- **Trading Advisor** (`agents/trading_advisor/`) — morning briefs, conversation, nightly research
- **Earnings Researcher** (`agents/earnings_researcher/`) — disputed-date verification

Each was built independently and grew its own launcher, prompt convention, scheduled-task batch files, and window-launch mechanics. The pattern works. What it lacks is a shared scaffold — so changing one cross-cutting concern (e.g., switching from `--dangerously-skip-permissions` to `--permission-mode auto`, which prompted this brainstorm) means touching N files instead of 1, and adding a fourth agent means cargo-culting from whichever existing agent looks closest.

This is the natural reform moment: build the product, replicate it a few times, then go back and extract the framework. Doing it before three agents existed would have been speculative. Doing it after a fourth means churning four launchers instead of three.

---

## Two ideas, one bundle

### Idea A — Modular agent prompts (from SA Proposal 019)

SA conceived this Sunday Session 021 (2026-04-26). The original observation:

> Agent launchers today inject a single hardcoded prompt (`.session_prompt.md`). To support different session modes (daily research, workspace cleanup, Sunday introspection), the current path is **separate prompt files** — `PROMPT.md`, `PROMPT_SUNDAY.md`, etc. This works but has three issues:
>
> 1. **Boilerplate duplication.** Identity, workspace location, read-only rules, file inventory live in every prompt. When workspace structure changes, every prompt has to be updated. Drift is inevitable.
> 2. **No composition.** A Sunday session is "cleanup AND introspection." Today that requires a third file that re-states cleanup framing inline.
> 3. **Mental-mode collisions when tempted to merge.** Cramming all variants into one prompt with day-of-week branching produces friction.

SA's proposed shape: CLI-flag-composable prompts. `launcher.py` accepts mode flags; assembles the final prompt by concatenating fragments.

```
agents/<agent>/prompts/
├── base.md              # identity, workspace, read-only rules — always concatenated
├── analyze.md           # task-scope: daily investigation framing
├── cleanup.md           # task-scope: workspace hygiene framing
└── introspection.md     # mode: reflective wrapper, "step back" framing
```

```
launcher.py --analyze                    # default daily research
launcher.py --cleanup                    # Wednesday workspace hygiene
launcher.py --cleanup --introspection    # Sunday self-care
```

Two flag categories:
- **Task-scope flags** (`--analyze`, `--cleanup`): describe what work to do. Compose additively.
- **Mode flags** (`--introspection`): set mental frame. Mutually exclusive — at most one.

The launcher decides assembly order, not the user. `--introspection --cleanup` and `--cleanup --introspection` produce identical output.

Full proposal text: `agents/system_analyst/proposals/019_modular_agent_prompts.md`. SA's open questions are reproduced near the bottom of this file.

### Idea B — Shared launcher infrastructure (`agents/_launcher_lib.py`)

Surfaced when the divergence across the three launchers got an explicit comparison. The three launchers reimplement the same boilerplate three times:

| Concern | Where it lives today |
|---|---|
| UTF-8 stdout/stderr reconfigure | All three launchers, top of file |
| `tempfile.NamedTemporaryFile` batch-file dance | All three `spawn_visible()` |
| `subprocess.run('start "..." cmd /k "..."')` | All three `spawn_visible()` |
| `[claude_path, '-p', '--permission-mode', 'auto']` | SA + ER `spawn_headless()` |
| Date header injection (`**Today is...**`) | All three `main()` |
| `claude --permission-mode auto @prompt` flag | All three (six call sites total) |

Without extraction, every cross-cutting change touches 3-6 files. Examples that have already happened or will:

- Today: switching `bypassPermissions` → `auto` touched 11 launch sites + 2 docs. Should have been 1.
- Future: changing the date-header format. 3 files.
- Future: adding session telemetry (start/end timestamp, prompt hash, exit code) to `performance.db`. 3 files, easy to forget one.
- Future: adding a global agent kill-switch. 3 files.
- Future: a fourth agent. The author cargo-cults from whichever existing agent looks closest, and we get a fourth divergent launcher.

### Why bundle them

Idea A alone *creates* new duplication. The argparse-flag-parsing + fragment-loader machinery would be written into each agent's launcher independently. The pathology A fights against (boilerplate copy-paste) gets reintroduced one layer up — when SA adds a flag, TA's launcher needs the matching argparse line copy-pasted in.

Idea B alone doesn't solve A's pain. SA's prompt-content duplication is unaffected by where the spawn-batch-file code lives.

**Both together** is the only configuration where the triggering signal — "I had to touch N files for one change" — actually goes to 1. New flag? Edit one library file. New mode? One fragment file. New permission mode? One library constant. New agent? Copy the smallest possible shim, write the agent's prompts, done.

---

## What the bundled refactor produces

### `agents/_launcher_lib.py`

A small library, not a framework. Provides primitives, doesn't dictate flow.

Sketch of public surface (subject to change during implementation — write the lib by extracting from a real agent first, don't design it in the abstract):

```python
# Lib responsibilities — the things every agent's launcher needs

def configure_utf8():
    """Reconfigure stdout/stderr for Windows. Call once at module load."""

def assemble_prompt(
    fragments: list[Path],   # ordered list of fragment files to concatenate
    date_header: bool = True, # inject **Today is X** header
) -> str:
    """Read each fragment, concat with the date header on top."""

def spawn_visible(
    prompt_text: str,
    agent_dir: Path,
    title: str,
    permission_mode: str = "auto",
) -> bool:
    """Write prompt to .session_prompt.md, write batch file, spawn window."""

def spawn_headless(
    prompt_text: str,
    agent_dir: Path,
    timeout: int,
    permission_mode: str = "auto",
) -> tuple[bool, str]:
    """Launch claude headless, capture output, return (success, stdout)."""

# Optional helpers
def parse_mode_flags(parser, mode_flags: list[str]):
    """Add a mutually-exclusive group of mode flags to an argparse parser."""

def parse_scope_flags(parser, scope_flags: list[str]):
    """Add additive task-scope flags to an argparse parser."""
```

Per-agent specifics stay in the agent's `launcher.py`:
- ER's dispute pre-flight (query `performance.db`, bail if no work)
- SA's session-number tracking (scan proposals + journal)
- TA's prompt-flag-to-window-title mapping ("Research" / "Morning Brief" / "Session")

The agent launcher imports the lib, declares its agent-specific argparse flags, runs its pre-flight, calls `lib.assemble_prompt(...)`, then `lib.spawn_visible(...)` or `lib.spawn_headless(...)`. Maybe ~40 lines of agent-specific code per agent, vs ~150-220 today.

### `agents/<agent>/prompts/` directories

Per SA's 019 design:

```
agents/system_analyst/prompts/
├── base.md             # identity, workspace, read-only, file inventory
├── analyze.md          # daily investigation framing
├── cleanup.md          # workspace hygiene framing (NEW — was missing)
└── introspection.md    # reflective wrapper

agents/trading_advisor/prompts/
├── base.md             # identity, market knowledge, DB access, gotchas
├── analyze.md          # research-mode framing (was PROMPT_RESEARCH.md)
├── morning_brief.md    # morning-brief framing (was reference/morning_brief_prompt.md)
├── cleanup.md          # Saturday closure framing (was PROMPT_SATURDAY.md)
└── introspection.md    # Sunday housekeeping framing (was PROMPT_SUNDAY.md)

agents/earnings_researcher/prompts/
├── base.md             # identity, IR-source rules, dispute workflow
└── research.md         # the embedded PROMPT_TEMPLATE moves here
```

Each agent owns its own fragments. The *pattern* is shared via the lib; the *content* is not cross-agent.

### Scheduled task batch files

Become thin wrappers that differ only in the flag string:

```batch
:: scheduled_tasks/start_system_analyst.bat       — daily
python agents\system_analyst\launcher.py --analyze --visible

:: scheduled_tasks/start_system_analyst_wednesday.bat   — NEW (Ben planned)
python agents\system_analyst\launcher.py --cleanup --visible

:: scheduled_tasks/start_system_analyst_sunday.bat — Sunday
python agents\system_analyst\launcher.py --cleanup --introspection --visible

:: scheduled_tasks/start_trading_advisor_research.bat  — weekday nights
python agents\trading_advisor\launcher.py --analyze --visible

:: scheduled_tasks/start_trading_advisor_saturday.bat
python agents\trading_advisor\launcher.py --cleanup --visible

:: scheduled_tasks/start_trading_advisor_sunday.bat
python agents\trading_advisor\launcher.py --cleanup --introspection --visible
```

This also normalizes the window-launch mechanism — pick one (see open question below).

### `agents/AGENT_PATTERN.md` becomes a real spec

Today the doc is descriptive ("here's how agents tend to be built"). After this refactor it becomes prescriptive:

> To add a new agent:
> 1. `mkdir agents/<name>/{prompts,memory}`
> 2. Write `prompts/base.md` (identity, workspace rules, file inventory)
> 3. Write at least one task-scope fragment (`prompts/analyze.md`)
> 4. Create `agents/<name>/launcher.py` (~40 lines, see template)
> 5. Add `agents/<name>/.claude/settings.local.json` with the write guard hook path
> 6. Optionally add a scheduled-task `.bat` file
>
> Done. Permission mode, UTF-8 setup, window spawning, prompt assembly are inherited from `_launcher_lib.py`.

That's the consistency-enforcement payoff. Future agents are reproducible.

---

## Implementation sequencing

1. **Build `_launcher_lib.py`** with the minimum surface SA needs. Extract from SA's current `launcher.py` rather than designing in the abstract — let the existing code dictate the API shape, then refine.
2. **Refactor SA on top of the lib** — modular prompts (019 Phase 1) and lib adoption land together. SA is the test-bed because it's the simplest of the three (no multi-prompt, no pre-flight). Verify all three SA scheduled tasks produce equivalent prompts to today's bespoke files.
3. **Port TA** — mechanical work once the lib is right. TA has the most prompt fragments (analyze/morning/cleanup/introspection = 4), so it'll exercise the composition logic hardest.
4. **Port ER** — similar effort. ER's dispute pre-flight stays in its own launcher; only the spawn machinery moves to the lib.
5. **Update `AGENT_PATTERN.md`** to the new spec. Include the launcher template and a worked example.
6. **Update `docs/CLAUDE_REFERENCE.md`** Agent System sections to point at the new pattern.

Each step ends with the affected agent verified-launchable interactively before moving on. If the lib design proves wrong during step 3 or 4, redesign — it's much cheaper to redesign with one consumer than three.

---

## Open design questions

Some inherited from 019, some new from the bundling.

**Q1. `--mode <name>` argument vs separate boolean flags?** ✅ **DECIDED 2026-04-29: separate booleans.**
Separate booleans + argparse mutual-exclusion group. Reasoning: bat files like `start_system_analyst_sunday.bat` are themselves documentation of how Sunday mode is composed; explicit `--cleanup --introspection` makes the wiring legible six months from now. `--help` lists every mode as its own line. The mutual-exclusion group is ~3 lines of argparse — no real cost.

**Q2. Should fragments support inheritance/include?** ✅ **DECIDED 2026-04-29: no, v1.**
Fragments are flat files — what you see in the file is what gets concatenated. No `{{include: ...}}` directives. Reasoning: pre-emptive YAGNI. If duplication actually emerges across fragments we'll feel it editing two files for one change, and switching to inheritance later is a content-only refactor (no flag changes, no per-agent code). The one place duplication could conceivably matter — `base.md` boilerplate across agents — is a different problem (cross-agent), not the cross-fragment-within-an-agent problem this question is about. Out of scope.

**Q3. Where does the date header live?** ✅ **DECIDED 2026-04-29: always inject, in the lib.**
Every assembled prompt starts with the `**Today is X. Day of week: Y.**` header regardless of mode. Reasoning: every human knows what day it is when they wake up — this is the model's equivalent. The cost is ~50 tokens; the cost of being wrong is "agent thinks it's Tuesday, plans Wednesday work." Lib's `assemble_prompt()` injects unconditionally at the top. Keyword arg `inject_date=False` available as escape hatch but no current consumer needs it.

**Q4. Window-launch mechanism — `wt -w 0 new-tab` vs `start "" cmd /k`?** ✅ **DECIDED 2026-04-27: WT tabs**
Today SA uses Windows Terminal tabs (`wt -w 0 new-tab --title "..."`); TA and ER use separate cmd windows (`start "Title" cmd /k "..."`). Bundled refactor normalizes to **WT tabs** for all three agents. Reasoning: Ben actively watches agents as they run, so the tab strip serving as a live status board (Ctrl+Tab between agents, at-a-glance "what's running" via tab titles) is the dominant UX win as the fleet grows. Separate cmd windows compound taskbar clutter past three agents.

**Implementation note:** use a named window (`-w agents`) instead of `-w 0` to avoid the "attaches to most-recently-active WT" gotcha — agents always collect into a dedicated `agents` Windows Terminal window regardless of what other terminals Ben has open:

```
wt -w agents new-tab --title "System Analyst" cmd /k "..."
```

Lib should expose this via a `spawn_visible(..., terminal="wt", window_name="agents")` parameter so individual agents could opt out if a future need emerges.

**Q5. Headless mode — should the lib expose it, or only visible?**
TA has no headless. SA and ER do. If the lib exposes both, every agent can opt in. If only visible, ER and SA's headless paths stay agent-specific (small cost — the headless function is ~15 lines). Probably expose both — the cost is small and it future-proofs. *Tentative answer: both in lib.*

**Q6. Where does `--permission-mode` value live?**
Today after this morning's refactor it's hardcoded as `auto` in 11 places. Lib option: a module-level constant `DEFAULT_PERMISSION_MODE = "auto"` that `spawn_visible` / `spawn_headless` use unless overridden. Per-agent option: an agent could opt to `--permission-mode default` for sensitive sessions. *Tentative answer: lib constant, override per-call.*

**Q7. What happens to `.session_prompt.md`?**
Today the launcher writes the assembled prompt to `agents/<agent>/.session_prompt.md` and `claude` reads it via `@.session_prompt.md`. With fragment composition, this still happens — the lib just builds the file from N fragments instead of 1. The file path stays the same so existing scheduled tasks and inspection workflows aren't disrupted. *Tentative answer: keep `.session_prompt.md` as the assembled-prompt path.*

**Q8. How do `.gitignore`, `.session_limit`, `.session_injected` and similar agent-specific sentinels fit?**
ER writes `.session_limit` and `.session_injected`. These are pre-flight concerns specific to ER — they stay in `agents/earnings_researcher/launcher.py`, not in the lib. Lib doesn't need to know about them. *No change needed.*

**Q9. Should we also normalize `.claude/settings.local.json` and write-guard hook paths?**
Out of scope for this refactor — the write guards are correctly outside agent workspaces and the settings files are already consistent in the parts that matter. Flagging in case it comes up during implementation; defer unless it does.

---

## Risks

1. **Mode-flag collision.** `--introspection --crisis-mode` (if both ever existed) would layer two mental frames and probably contradict. Mitigation: enforce at-most-one mode flag in argparse. Document the exclusivity rule. (Inherited from 019.)
2. **Flag bloat.** With N task-scope flags you get 2^N combinations. Most won't be useful. Mitigation: document which combinations are *intended* in `prompts/README.md` per agent. Don't add a flag without a concrete session type that needs it. (Inherited from 019.)
3. **Initial cost vs payoff.** With current scope (3 agents × 2-4 modes each) this is borderline-worth-it on its own. Earns its keep when a fourth agent or a fifth mode arrives. **Stronger justification given Ben's stated intent to keep growing the agent fleet** — every new agent built without this scaffold inherits the divergence cost.
4. **Order-of-assembly bugs.** If `cleanup.md` and `introspection.md` overlap on a topic, the later-concatenated fragment wins. Mitigation: design fragments to be additive at clearly-different abstraction levels. Cleanup is task-scope; introspection wraps the task in a reflective frame. They shouldn't fight. (Inherited from 019.)
5. **Lib API churn during early agents.** The first agent (SA) shapes the lib; porting TA and ER might reveal needed changes that ripple back to SA. Mitigation: don't lock the lib API after step 2 — treat steps 3-4 as design-feedback, refactor freely. (New from bundling.)
6. **Window-launch normalization breaks Ben's mental model.** If Ben is used to `start cmd /k` separate windows and we switch to WT tabs (or vice versa), it's a UX change. Worth confirming before implementation. (New from bundling.)
7. **Scheduled task .bat file rewrites.** All five existing bat files in `scheduled_tasks/` get rewritten in this refactor. They were also just rewritten this morning for the permission-mode change. Two churns in one week. Acceptable but worth noting. (New from bundling.)

---

## Success criteria

- All three current agents (SA / TA / ER) launchable in all current modes via the new flag composition, producing prompts equivalent to today's bespoke files.
- `_launcher_lib.py` is the only place to edit when changing UTF-8 setup, batch-file template, subprocess args, date-header format, `--permission-mode` value, or window-spawn mechanism.
- Each agent's `launcher.py` is ≤ 60 lines (vs 150-220 today), with everything in it being agent-specific (pre-flight, agent-name strings, agent-specific argparse flags).
- `prompts/base.md` per agent is the only file that needs editing when that agent's workspace structure changes.
- `AGENT_PATTERN.md` describes the steps to create a new agent in ≤ 6 numbered steps.
- Adding a hypothetical fourth mode to any agent is a one-fragment-plus-one-argparse-line change.
- Adding a hypothetical fourth agent reuses the lib without modification.

---

## Out of scope (explicitly not this refactor)

- Changing what the agents *do*. This is plumbing.
- Migrating `agents/Deprecated/` — leave it alone.
- Changing the write-guard hook architecture.
- Changing `.claude/settings.local.json` per-agent contents.
- Cross-agent mailbox infrastructure (SA Proposal 018 territory).
- Telemetry / session logging to `performance.db` — flagged as a future "this is now a one-line lib edit" payoff but not built in this refactor.

---

## Provenance & next steps

- Original prompt-fragment idea: SA Session 021, 2026-04-26 (Sunday). Captured as Proposal 019.
- Bundle decision: Ben + dev session, 2026-04-26 (same Sunday).
- SA is no longer involved in this work — the idea has been promoted to a proper enhancement project. SA's job was to surface the observation; the bundling, design, and implementation happen here.
- Next concrete step: Ben reviews this brainstorm, decides on open questions Q1-Q9 (especially Q4), then a dev session takes step 1 of the implementation sequence above.
