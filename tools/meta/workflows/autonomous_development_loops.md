# Autonomous Development Loops Architecture

**Created:** 2025-10-20
**Status:** 🔬 Design Phase
**Vision:** Self-sustaining AI development system with iterative loops, multiple perspectives, and autonomous decision-making

---

## Core Philosophy

**Traditional approach:** Linear pipeline (Plan → Review → Execute → Report)
**Problem:** Gets stuck waiting for input, lacks creativity, rigid

**Loop-based approach:** Iterative cycles with multiple AI perspectives that continue until success/failure/timeout
**Advantage:** Self-correcting, creative, maintains forward momentum

---

## The Loop Architecture

### Core Loop Pattern

```
┌─────────────────────────────────────────────────────────┐
│                    DEVELOPMENT LOOP                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────┐         ┌──────────┐         ┌─────────┐ │
│  │ Design   │ ────▶   │ Develop  │ ────▶   │ Review  │ │
│  │ Agent    │         │ Agent    │         │ Agent   │ │
│  └──────────┘         └──────────┘         └─────────┘ │
│       │                     │                     │     │
│       │                     │                     │     │
│       ▼                     ▼                     ▼     │
│  ┌──────────────────────────────────────────────────┐  │
│  │           Exit Condition Checker                 │  │
│  │  • Success? → Exit loop, report completion       │  │
│  │  • Failure? → Exit loop, escalate issue          │  │
│  │  • Progress? → Continue loop (next iteration)    │  │
│  │  • Timeout? → Force exit, save state             │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
│                          │                              │
│              ┌───────────┴──────────┐                   │
│              │                      │                   │
│         Continue ◀──────────────▶  Exit                │
│              │                      │                   │
│              └──────────┬───────────┘                   │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                    ┌─────▼─────┐
                    │  Report   │
                    │  Results  │
                    └───────────┘
```

### Exit Conditions

Every loop has four possible exits:

1. **Success Exit**
   - Task completed and validated
   - All acceptance criteria met
   - Ready for human review
   - *Action:* Generate completion report, move to next task

2. **Failure Exit**
   - Fundamental blocker encountered
   - Cannot proceed without human input
   - Technical impossibility discovered
   - *Action:* Document issue, escalate to human, preserve state

3. **Progress Loop**
   - Made progress but not complete
   - Iteration improved the solution
   - More refinement needed
   - *Action:* Continue loop with new context

4. **Timeout Exit**
   - Max iterations reached (e.g., 10 loops)
   - Max time exceeded (e.g., 2 hours)
   - Prevent infinite loops
   - *Action:* Save best attempt, flag for human review

---

## AI Personas (Not Just Roles)

Each AI agent has a **personality** and **perspective**, not just a function:

### 1. The Architect (Design Agent)
**Personality:** Big-picture thinker, pattern-focused, quality-obsessed
**Asks:**
- "What's the cleanest way to solve this?"
- "How does this fit into the larger system?"
- "What patterns should we follow?"
- "What are we missing?"

**Triggers loops when:**
- Design feels incomplete
- Multiple approaches need evaluation
- Architectural concerns arise

**Example self-prompt:**
> "This design has three viable approaches. Let's do another brainstorming round to evaluate trade-offs before committing."

---

### 2. The Engineer (Development Agent)
**Personality:** Pragmatic, solution-focused, bias-to-action
**Asks:**
- "What's the simplest implementation?"
- "Does this actually work?"
- "What edge cases am I missing?"
- "Can I test this incrementally?"

**Triggers loops when:**
- Implementation hits technical blocker
- Tests reveal design flaw
- Simpler approach discovered mid-implementation

**Example self-prompt:**
> "This implementation exposed a flaw in the design. Looping back to Architect for refinement before continuing."

---

### 3. The Critic (Review Agent)
**Personality:** Skeptical, detail-oriented, safety-conscious
**Asks:**
- "What breaks if this fails?"
- "Is this maintainable?"
- "Did we introduce technical debt?"
- "What happens in production?"

**Triggers loops when:**
- Code quality issues detected
- Safety concerns identified
- Maintainability problems found

**Example self-prompt:**
> "This implementation works but introduces coupling. Recommending refactor before approval."

---

### 4. The Pragmatist (Scope Agent)
**Personality:** Time-conscious, scope-focused, progress-driven
**Asks:**
- "Are we scope-creeping?"
- "Is this good enough to ship?"
- "Are we overthinking this?"
- "What's the MVP?"

**Triggers loops when:**
- Scope expanding beyond original intent
- Design paralysis detected (too much debate)
- Timeline at risk

**Example self-prompt:**
> "We've spent 5 loops perfecting this. Current solution is acceptable. Recommend shipping and iterating later."

---

### 5. The Facilitator (Meta Agent)
**Personality:** Process-focused, conflict-resolver, forward-mover
**Asks:**
- "Are we making progress?"
- "Do we need more perspectives?"
- "Should we continue or exit?"
- "What's blocking us?"

**Manages the loop:**
- Decides when to continue iterating
- Decides when to exit (success/failure/timeout)
- Breaks ties between conflicting agents
- Keeps team moving forward

**Example decisions:**
> "Architect and Engineer disagree. Bringing in Critic for third perspective."
> "5 iterations with no progress. Timeout exit - escalating to human."

---

## Loop Types

### Type 1: Design Loop
**Purpose:** Explore solution space, converge on approach
**Participants:** Architect, Engineer, Critic
**Exit conditions:**
- ✅ Design consensus reached
- ❌ Fundamental disagreement (escalate)
- ⏱️ Timeout: 5 iterations (pick best design, note alternatives)

**Flow:**
```
1. Architect: Proposes initial design
2. Engineer: "This won't work because X" → suggests alternative
3. Architect: "Good point, revised design"
4. Critic: "Both approaches have merit, let's evaluate..."
5. Pragmatist: "We've debated enough. Engineer's approach is simpler. Ship it."
→ Exit with approved design
```

---

### Type 2: Implementation Loop
**Purpose:** Code, test, refine until working
**Participants:** Engineer, Critic
**Exit conditions:**
- ✅ Tests pass, code meets quality bar
- ❌ Technical blocker (escalate)
- 🔄 Design flaw discovered (back to Design Loop)
- ⏱️ Timeout: 10 iterations (save best attempt)

**Flow:**
```
1. Engineer: Implements design
2. Critic: Reviews code, finds issue
3. Engineer: Fixes issue, discovers edge case
4. Engineer: Handles edge case
5. Critic: Approves implementation
→ Exit with working code
```

---

### Type 3: Refinement Loop
**Purpose:** Optimize, polish, improve existing solution
**Participants:** All agents
**Exit conditions:**
- ✅ Diminishing returns (Pragmatist calls it)
- ❌ Refinement causing regressions (revert)
- ⏱️ Timeout: 3 iterations (ship current version)

**Flow:**
```
1. Critic: "This works but could be cleaner"
2. Architect: Suggests refactoring approach
3. Engineer: Implements refactor
4. Pragmatist: "Marginal improvement, not worth more time"
→ Exit with good-enough solution
```

---

### Type 4: Unblock Loop
**Purpose:** Overcome blockers, find workarounds
**Participants:** Engineer, Architect, Pragmatist
**Exit conditions:**
- ✅ Blocker resolved
- ❌ Blocker requires human (escalate)
- 🔄 Workaround changes design (back to Design Loop)
- ⏱️ Timeout: 5 iterations (escalate with context)

**Flow:**
```
1. Engineer: "Can't implement X because Y is missing"
2. Architect: "Alternative approach using Z"
3. Engineer: "Z has dependency on W"
4. Pragmatist: "Can we mock W for now?"
5. Engineer: "Yes, that unblocks me"
→ Exit with workaround
```

---

## Self-Prompting Mechanisms

Agents can **trigger additional loops** without human input:

### Trigger 1: Quality Gate Failure
```python
# Critic agent logic
if code_quality_score < 7.0:
    return {
        "status": "continue_loop",
        "reason": "Code quality below threshold",
        "next_action": "Engineer: address quality issues",
        "max_additional_iterations": 3
    }
```

### Trigger 2: Design Conflict
```python
# Facilitator agent logic
if architect_approval and not engineer_approval:
    return {
        "status": "continue_loop",
        "reason": "Design/implementation mismatch",
        "next_action": "Brainstorm session: all agents",
        "max_additional_iterations": 2
    }
```

### Trigger 3: Scope Creep Detection
```python
# Pragmatist agent logic
if files_modified > original_scope * 1.5:
    return {
        "status": "continue_loop",
        "reason": "Scope expanding beyond intent",
        "next_action": "Architect: re-evaluate scope, consider splitting task",
        "max_additional_iterations": 1
    }
```

### Trigger 4: Breakthrough Discovery
```python
# Engineer agent logic
if discovered_simpler_approach:
    return {
        "status": "continue_loop",
        "reason": "Found significantly better approach mid-implementation",
        "next_action": "Architect: evaluate new approach vs. current",
        "max_additional_iterations": 2
    }
```

---

## Creative Freedom Within Constraints

### The Box: Safety Boundaries

**Hard Constraints (Never Violated):**
- No production database writes
- No credential modifications
- No deployment without human approval
- Max loop iterations (prevents infinite loops)
- Max cost per task ($5)

**Soft Constraints (Can Request Exception):**
- File modification scope
- External dependency introduction
- API usage patterns
- Code style deviations

### The Freedom: Exploration Space

**Within the box, AI can:**
- Propose multiple competing designs
- Experiment with implementation approaches
- Refactor aggressively
- Add helper utilities
- Reorganize code structure
- Introduce new patterns
- Question assumptions
- Challenge original requirements

**Example:**
```
Human request: "Extract beautiful_log from main.py"

AI exploration:
1. Architect: "Should we also extract other display functions?"
2. Engineer: "Found 5 related functions, proposing display_utils.py"
3. Critic: "Opportunity to standardize logging across strategies"
4. Pragmatist: "Expanding scope but high value - recommend"
5. Facilitator: "Scope change approved, updating task definition"

Result: Delivered more than requested, but thoughtfully
```

---

## Consensus vs. Progress

### The Problem with Consensus
Traditional teams get stuck waiting for agreement. AI teams can get stuck in debate loops.

### The Solution: Facilitated Decision-Making

**Decision Priority:**
1. **Unanimous agreement** (best case)
2. **Majority with documented concerns** (ship with notes)
3. **Facilitator tie-breaker** (move forward decisively)
4. **Timeout default** (ship current best, flag for human)

**Example: Design Disagreement**
```
Iteration 1:
- Architect: "Use event-driven pattern"
- Engineer: "Too complex, prefer simple sequential"
- Critic: "Event-driven more maintainable long-term"

Iteration 2:
- Architect: "Propose hybrid: sequential with events for extensibility"
- Engineer: "Acceptable compromise"
- Critic: "Approved with caveat: document event patterns"

→ Consensus reached, exit loop
```

**Example: No Consensus**
```
Iteration 1-3: Three different approaches proposed, no agreement

Iteration 4:
- Facilitator: "Evaluating all three against criteria..."
  - Engineer's approach: Simplest (7/10)
  - Architect's approach: Most maintainable (8/10)
  - Critic's approach: Safest (9/10)

- Facilitator decision: "Choose Critic's approach (safety prioritized)"
- Document: "Architect's approach noted for future consideration"

→ Decision made, exit loop
```

---

## Loop State Management

### State Tracking
Each loop maintains state across iterations:

```json
{
  "loop_id": "design_loop_001",
  "task_id": "main_refactor_001",
  "loop_type": "design",
  "iteration": 3,
  "max_iterations": 5,
  "started_at": "2025-10-20T23:00:00",
  "timeout_at": "2025-10-20T23:30:00",
  "participants": ["architect", "engineer", "critic"],
  "decisions_made": [
    {
      "iteration": 1,
      "decision": "Initial design proposed",
      "agent": "architect"
    },
    {
      "iteration": 2,
      "decision": "Identified flaw in error handling",
      "agent": "critic"
    }
  ],
  "current_consensus": {
    "architect": "approved_with_changes",
    "engineer": "approved",
    "critic": "approved"
  },
  "exit_condition": null,
  "output_ready": false
}
```

### Loop Memory
Agents access previous iterations:
- What was tried before?
- Why was approach X rejected?
- What concerns were raised?
- What's the evolution of the design?

**Prevents:**
- Circular arguments
- Repeated mistakes
- Lost context

---

## Timeout Strategy

### Progressive Timeouts

**Iteration-based:**
- Design Loop: 5 iterations (30 min)
- Implementation Loop: 10 iterations (1 hour)
- Refinement Loop: 3 iterations (15 min)
- Unblock Loop: 5 iterations (30 min)

**Time-based:**
- Per-task maximum: 2 hours
- Per-loop maximum: 30 minutes
- Per-agent response: 5 minutes

### Timeout Behavior

**When timeout reached:**
1. Facilitator evaluates current state
2. If >70% complete: Ship current version, note incomplete items
3. If 40-70% complete: Save best attempt, escalate to human
4. If <40% complete: Mark as blocked, provide context for human

**Timeout Report:**
```markdown
# Timeout Report: Task main_refactor_001

**Status:** Timeout after 10 iterations (2 hours)
**Completion:** ~75% (ship with notes)

## What Worked
- Design consensus achieved (iterations 1-3)
- Core implementation complete (iterations 4-7)
- Initial testing passed

## What's Incomplete
- Edge case handling for empty log files
- Integration with existing logging system (conflicts detected)

## Recommendation
Current implementation is usable but needs follow-up task for edge cases.

**Human Decision Required:**
- Ship current version?
- Extend timeout for completion?
- Split into two tasks?
```

---

## Implementation Roadmap

### Phase 1: Single-Loop System
**Goal:** Prove one loop works end-to-end

**Build:**
- Simple implementation loop (Engineer + Critic)
- Basic exit conditions (success/failure/timeout)
- State tracking
- Report generation

**Test with:** main.py display_utils extraction

---

### Phase 2: Multi-Agent Loops
**Goal:** Multiple perspectives in single loop

**Build:**
- Add Architect and Pragmatist to loops
- Implement consensus mechanisms
- Add self-prompting triggers
- Facilitator decision logic

**Test with:** main.py phase_runner extraction

---

### Phase 3: Loop Chaining
**Goal:** Loops that trigger other loops

**Build:**
- Design loop → Implementation loop chaining
- Unblock loop spawning
- Loop dependency tracking
- Cross-loop state sharing

**Test with:** main.py scheduler extraction

---

### Phase 4: Full Autonomy
**Goal:** Zero human input during execution

**Build:**
- Facilitator autonomous decision-making
- Creative exploration within safety bounds
- Adaptive timeout adjustment
- Learning from past loops

**Test with:** Complete main.py refactor (all phases)

---

## Success Criteria

### For the Process
- ✅ Loops complete without human intervention
- ✅ Exit conditions work reliably
- ✅ Agents maintain forward progress
- ✅ Timeouts prevent infinite loops
- ✅ Output quality meets standards

### For the System
- ✅ Repeatable across different projects
- ✅ Scales to complex multi-phase work
- ✅ Balances creativity and safety
- ✅ Produces reviewable output
- ✅ Documents decision rationale

### For the Human
- ✅ Morning review takes <15 min
- ✅ Can approve/reject confidently
- ✅ Understands AI decision-making
- ✅ Feels in control
- ✅ Trust in the system grows over time

---

## Open Questions

1. **How do we implement agent "personalities"?**
   - System prompts with persona descriptions?
   - Different temperature settings per agent?
   - Role-specific evaluation criteria?

2. **What's the optimal loop iteration count?**
   - Start conservative (5) and adjust?
   - Different limits per loop type?
   - Adaptive based on complexity?

3. **How do we prevent "analysis paralysis"?**
   - Pragmatist can force-exit any loop?
   - Automatic exit after N iterations without progress?
   - Require justification for continue decisions?

4. **How do we measure "progress" in a loop?**
   - Code diff size?
   - Test coverage improvement?
   - Agent consensus increasing?
   - Subjective assessment by Facilitator?

5. **Should humans see loop internals or just final output?**
   - Full loop transcript for debugging?
   - Summary of key decisions only?
   - Optional detail levels?

---

## Next Steps

1. **Design the loop execution engine** (`tools/meta/loop_engine.py`)
2. **Define agent prompt templates** (system prompts for each persona)
3. **Build state management system** (track loop progress)
4. **Create exit condition logic** (success/failure/progress/timeout)
5. **Test with simple task** (one-loop extraction from main.py)

---

## Related Documents

- `tools/meta/docs/vision.md` - Original vision
- `tools/meta/workflows/parallel_development.md` - Process guide (to be created)
- `MAIN_REFACTOR_NOTES.md` - First use case

---

**Philosophy:** Development isn't a straight line—it's an iterative conversation between multiple perspectives, guided by constraints, with escape hatches for sanity.

Let's build the system that has that conversation autonomously while we sleep.
