# Meta-AI System Implementation Roadmap

**Created:** 2025-10-20
**Goal:** Build autonomous development loop system incrementally
**First Project:** main.py refactor (proving ground)

---

## Philosophy

**Build the process, not just the product.**

Each phase:
1. Builds minimal working infrastructure
2. Tests with real work (main.py refactor)
3. Captures learnings
4. Refines before scaling

---

## Phase 0: Foundation (Week 1)

**Goal:** Manual process with documentation

### Build
- [x] `workflows/autonomous_development_loops.md` - Architecture vision
- [x] `workflows/parallel_development.md` - Practical workflow
- [ ] `workflows/task_templates/` - Standard task formats
- [ ] `main_v2/` directory structure

### Test
- [ ] Manually write task for display_utils extraction
- [ ] Manually execute task (human codes)
- [ ] Manually write completion report
- [ ] Validate workflow steps

### Success Criteria
- ✅ Process feels repeatable
- ✅ Documentation clear enough to follow
- ✅ Task format captures right information
- ✅ Review process takes <15 min

### Deliverable
**Working manual process** - A human can follow the docs and complete a task following the workflow

---

## Phase 1: Single-Agent Loop (Week 2)

**Goal:** One AI agent that iterates until task complete

### Build
```
tools/meta/
├── loop_engine.py              # Core loop execution
├── agents/
│   ├── __init__.py
│   ├── base_agent.py           # Agent interface
│   └── engineer_agent.py       # Implementation agent
├── state/
│   ├── __init__.py
│   └── loop_state.py           # Track loop progress
└── templates/
    └── engineer_prompt.txt     # System prompt
```

**Core Components:**

**1. loop_engine.py**
```python
class DevelopmentLoop:
    def __init__(self, task, agent, max_iterations=10):
        self.task = task
        self.agent = agent
        self.max_iterations = max_iterations
        self.state = LoopState()

    def run(self):
        """Execute loop until exit condition"""
        while self.state.iteration < self.max_iterations:
            # Agent works on task
            result = self.agent.execute(self.task, self.state)

            # Check exit conditions
            exit_decision = self.check_exit_conditions(result)

            if exit_decision.should_exit:
                return self.finalize(exit_decision)

            # Continue loop
            self.state.update(result)
            self.state.iteration += 1

        # Timeout
        return self.timeout_exit()

    def check_exit_conditions(self, result):
        """Determine if loop should continue or exit"""
        if result.status == "complete":
            return ExitDecision(should_exit=True, reason="success")
        if result.status == "blocked":
            return ExitDecision(should_exit=True, reason="blocked")
        if result.has_progress:
            return ExitDecision(should_exit=False, reason="continue")
        # No progress
        return ExitDecision(should_exit=True, reason="no_progress")
```

**2. base_agent.py**
```python
class BaseAgent:
    def __init__(self, name, persona_prompt):
        self.name = name
        self.persona_prompt = persona_prompt

    def execute(self, task, state):
        """Agent does work, returns result"""
        # Build prompt with persona + task + state
        prompt = self.build_prompt(task, state)

        # Call Claude Code or Claude API
        response = self.invoke_ai(prompt)

        # Parse response into structured result
        return self.parse_response(response)

    def build_prompt(self, task, state):
        """Combine persona, task, and loop state"""
        return f"""
        {self.persona_prompt}

        Task: {task.description}

        Previous Iterations:
        {state.format_history()}

        Your turn - what's next?
        """
```

**3. loop_state.py**
```python
class LoopState:
    def __init__(self):
        self.iteration = 0
        self.history = []
        self.decisions = []
        self.current_progress = 0

    def update(self, result):
        """Record this iteration"""
        self.history.append({
            "iteration": self.iteration,
            "agent": result.agent_name,
            "action": result.action,
            "outcome": result.outcome,
            "progress": result.progress
        })

    def format_history(self):
        """Format for next agent"""
        return "\n".join([
            f"Iteration {h['iteration']}: {h['agent']} - {h['action']}"
            for h in self.history
        ])
```

### Test
- [ ] Create simple task: "Extract 1 function from main.py"
- [ ] Run loop_engine with engineer_agent
- [ ] Verify agent iterates until function extracted
- [ ] Check exit conditions work (success/timeout)
- [ ] Validate state tracking across iterations

### Success Criteria
- ✅ Loop runs without human intervention
- ✅ Exit conditions work correctly
- ✅ State persists across iterations
- ✅ Output is reviewable
- ✅ Timeout prevents infinite loops

### Deliverable
**Working single-agent loop** - Engineer agent can complete a simple extraction task autonomously

---

## Phase 2: Multi-Agent Loop (Week 3)

**Goal:** Multiple agents collaborate in one loop

### Build
```
tools/meta/agents/
├── architect_agent.py          # Design perspective
├── critic_agent.py             # Review perspective
├── pragmatist_agent.py         # Scope/time perspective
└── facilitator_agent.py        # Loop manager
```

**Key Addition: Agent Turns**

```python
class MultiAgentLoop:
    def __init__(self, task, agents, max_iterations=10):
        self.task = task
        self.agents = agents  # [architect, engineer, critic]
        self.facilitator = FacilitatorAgent()
        self.state = LoopState()

    def run(self):
        while self.state.iteration < self.max_iterations:
            # Each agent gets a turn
            for agent in self.agents:
                result = agent.execute(self.task, self.state)
                self.state.update(result)

            # Facilitator decides: continue or exit?
            decision = self.facilitator.make_decision(self.state)

            if decision.should_exit:
                return self.finalize(decision)

            self.state.iteration += 1

        return self.timeout_exit()
```

### Test
- [ ] Create task: "Design and extract display_utils.py"
- [ ] Run with 3 agents: Architect → Engineer → Critic
- [ ] Verify each agent provides different perspective
- [ ] Check facilitator makes reasonable decisions
- [ ] Validate consensus emerges

### Success Criteria
- ✅ Agents collaborate effectively
- ✅ Different perspectives add value
- ✅ Facilitator breaks ties sensibly
- ✅ Loop converges to solution
- ✅ No circular arguments

### Deliverable
**Working multi-agent loop** - Architect + Engineer + Critic complete display_utils extraction with quality

---

## Phase 3: Self-Prompting (Week 4)

**Goal:** Agents trigger additional loops autonomously

### Build
```
tools/meta/
├── triggers/
│   ├── __init__.py
│   ├── quality_gate.py         # Critic triggers refinement
│   ├── scope_check.py          # Pragmatist triggers re-scope
│   └── design_conflict.py      # Architect triggers debate
└── loop_manager.py             # Manages nested loops
```

**Key Addition: Loop Triggers**

```python
class CriticAgent(BaseAgent):
    def execute(self, task, state):
        result = super().execute(task, state)

        # Self-prompting: Quality check
        if result.code_quality < 7.0:
            result.trigger = LoopTrigger(
                type="refinement_loop",
                reason="Code quality below threshold",
                max_additional_iterations=3
            )

        return result

class LoopManager:
    def handle_trigger(self, trigger, current_loop):
        """Spawn new loop based on trigger"""
        if trigger.type == "refinement_loop":
            return RefinementLoop(
                task=current_loop.task,
                agents=[EngineerAgent(), CriticAgent()],
                max_iterations=trigger.max_additional_iterations
            )
```

### Test
- [ ] Create task with intentional quality issue
- [ ] Verify Critic detects issue and triggers refinement
- [ ] Check refinement loop spawns correctly
- [ ] Validate loop completes before returning to main loop
- [ ] Confirm quality improves after refinement

### Success Criteria
- ✅ Agents can trigger new loops
- ✅ Nested loops execute correctly
- ✅ State preserved across loop transitions
- ✅ Quality improvements measurable
- ✅ No infinite loop nesting

### Deliverable
**Self-prompting loops** - System autonomously identifies issues and spawns correction loops

---

## Phase 4: Full Autonomy (Week 5-6)

**Goal:** Complete main.py Phase 1 with zero human intervention during execution

### Build
```
tools/meta/
├── scheduler/
│   ├── __init__.py
│   ├── nightly_scheduler.py    # Runs at 11 PM
│   └── task_queue.py           # Manages task list
├── reporters/
│   ├── __init__.py
│   └── morning_brief.py        # Generates report
└── meta_orchestrator.py        # Top-level coordinator
```

**Key Addition: Full Pipeline**

```python
class MetaOrchestrator:
    def run_nightly_development(self):
        """11 PM - Autonomous development session"""

        # 1. Load today's task
        task = self.load_next_task()

        # 2. Execute with appropriate loop type
        loop = self.create_loop_for_task(task)
        result = loop.run()

        # 3. Generate morning report
        report = self.generate_morning_brief(result)
        self.save_report(report)

        # 4. Update task queue
        if result.success:
            self.mark_task_complete(task)
        else:
            self.flag_for_human_review(task, result)

    def create_loop_for_task(self, task):
        """Choose loop type based on task"""
        if task.type == "extraction":
            return MultiAgentLoop(
                task=task,
                agents=[ArchitectAgent(), EngineerAgent(), CriticAgent()]
            )
        elif task.type == "design":
            return DesignLoop(task)
        # ... etc
```

### Test
- [ ] Load Phase 1 task queue (display_utils extraction)
- [ ] Run meta_orchestrator.run_nightly_development()
- [ ] Sleep (no human intervention)
- [ ] Wake up to morning brief
- [ ] Review results
- [ ] Approve or request revision

### Success Criteria
- ✅ Full session runs unattended
- ✅ Morning brief has all needed info
- ✅ Review takes <15 minutes
- ✅ Can approve/reject confidently
- ✅ System handles errors gracefully

### Deliverable
**Autonomous nightly development** - Complete main.py Phase 1 (display_utils) with AI-only execution

---

## Phase 5: Learning & Scaling (Week 7-8)

**Goal:** Improve based on feedback, handle Phases 2-5 of main.py

### Build
```
tools/meta/
├── learning/
│   ├── __init__.py
│   ├── feedback_tracker.py     # Track approvals/rejections
│   └── preference_learner.py   # Adapt to human preferences
└── analytics/
    ├── __init__.py
    └── performance_metrics.py  # Track success rates
```

**Key Addition: Feedback Loop**

```python
class FeedbackTracker:
    def record_human_decision(self, task, result, decision):
        """Learn from human review"""
        self.feedback_db.insert({
            "task_id": task.id,
            "task_type": task.type,
            "agents_used": result.agents,
            "iterations": result.iterations,
            "human_decision": decision,  # approve/reject/revise
            "human_notes": decision.notes,
            "timestamp": now()
        })

    def get_patterns(self):
        """What does human approve vs reject?"""
        return {
            "preferred_agents": self.most_approved_agent_combos(),
            "optimal_iterations": self.avg_iterations_for_approval(),
            "common_rejections": self.rejection_reasons(),
            "style_preferences": self.extract_style_patterns()
        }

class PreferenceLearner:
    def adapt_next_task(self, task, patterns):
        """Adjust approach based on learnings"""
        if patterns["preferred_agents"] == ["engineer", "critic"]:
            # Human prefers simpler 2-agent loops
            task.agents = ["engineer", "critic"]
        if patterns["optimal_iterations"] < 5:
            # Human prefers concise work
            task.max_iterations = 5
```

### Test
- [ ] Complete main.py Phases 2-5
- [ ] Track approval rates per phase
- [ ] Identify patterns in human feedback
- [ ] Adjust approach based on learnings
- [ ] Measure improvement over time

### Success Criteria
- ✅ Approval rate increases over time
- ✅ Fewer iterations needed per task
- ✅ Human review time decreases
- ✅ System adapts to preferences
- ✅ main.py refactor complete

### Deliverable
**Complete main.py refactor** - All 5 phases done autonomously with learning applied

---

## Phase 6: Generalization (Week 9-12)

**Goal:** Apply process to other projects beyond main.py

### Build
- [ ] Generalized task templates
- [ ] Project setup automation
- [ ] Comparison test framework
- [ ] Process documentation for new projects

### Test Projects
1. **Small:** Extract another utility module
2. **Medium:** Build new feature (alert scoring system)
3. **Large:** Second major refactor (oracle_main.py)

### Success Criteria
- ✅ Process works for diverse projects
- ✅ Setup time < 1 hour per project
- ✅ Success rate > 80%
- ✅ Documented for reproducibility

### Deliverable
**Proven repeatable process** - Can autonomously develop any similar-scope project

---

## Success Metrics

### Development Velocity
**Baseline:** ~5 hours/week coding
**Target:** 15-20 features/fixes completed per month
**Measure:** Tasks completed per week

### Quality
**Baseline:** Human codes everything
**Target:** >80% AI tasks approved first try
**Measure:** Approval rate on first submission

### Efficiency
**Baseline:** N/A (new process)
**Target:** Morning review < 15 minutes
**Measure:** Time spent reviewing per morning

### Learning
**Baseline:** Static process
**Target:** Approval rate increases 10% over 3 months
**Measure:** Week-over-week improvement

---

## Risk Mitigation

### Technical Risks

**Risk:** Infinite loops
**Mitigation:** Hard iteration limits + timeouts + facilitator oversight

**Risk:** Poor quality output
**Mitigation:** Multi-agent review + quality gates + human approval

**Risk:** Scope creep
**Mitigation:** Pragmatist agent + explicit task boundaries

**Risk:** System degradation over time
**Mitigation:** Learning feedback + performance monitoring

### Process Risks

**Risk:** Human review becomes bottleneck
**Mitigation:** Keep review < 15 min + batch low-risk approvals

**Risk:** AI decisions misaligned with human intent
**Mitigation:** Clear personas + learning from feedback + override ability

**Risk:** Over-reliance on automation
**Mitigation:** Critical tasks still require human design + regular audits

---

## Cost Projections

### Phase 0-1 (Manual + Single Agent)
- Development: ~$2-5 per task
- Testing: Minimal
- **Total: ~$20-50 for phase**

### Phase 2-3 (Multi-Agent + Self-Prompting)
- Development: ~$5-10 per task
- Multiple iterations: 2-3x cost
- **Total: ~$50-100 for phase**

### Phase 4 (Full Autonomy)
- Nightly sessions: $0.50-2.00 per night
- main.py Phase 1: ~5 nights = $2.50-10
- **Total: ~$10-50 for Phase 1**

### Phase 5 (All Phases)
- 5 phases × ~5 nights each = 25 nights
- @$1.00 per night = $25-50 total
- **Total: ~$25-100 for complete refactor**

### Phase 6 (Scaling)
- Monthly: ~$20-40 for ongoing development
- ROI: 10-15 hours saved @ $50/hr = $500-750 value
- **ROI: ~15-30x**

---

## Decision Points

### After Each Phase

**Questions to answer:**
1. Did this phase add value?
2. Is the process repeatable?
3. Can we document it clearly?
4. Should we continue to next phase?
5. What needs refinement?

**Go/No-Go Criteria:**
- ✅ Success criteria met
- ✅ Learning captured
- ✅ Process documented
- ✅ Confidence in next phase
- ❌ Fundamental blocker → re-evaluate approach

---

## Timeline Summary

| Phase | Duration | Goal | Deliverable |
|-------|----------|------|-------------|
| 0 | Week 1 | Manual process | Working workflow docs |
| 1 | Week 2 | Single agent | Engineer loop works |
| 2 | Week 3 | Multi-agent | Collaborative loops |
| 3 | Week 4 | Self-prompting | Autonomous refinement |
| 4 | Week 5-6 | Full autonomy | Phase 1 complete |
| 5 | Week 7-8 | Learning | All phases complete |
| 6 | Week 9-12 | Generalize | Repeatable process |

**Total: ~3 months to fully autonomous, repeatable system**

---

## Next Immediate Steps

1. **Create task templates** (this week)
2. **Set up main_v2/ structure** (this week)
3. **Manually complete Phase 1 task** (this week)
4. **Document learnings** (this week)
5. **Build loop_engine.py** (next week)

---

## Questions to Resolve

1. **Which AI API to use for agents?**
   - Claude API (cheaper, more control)
   - Claude Code spawning (proven, more expensive)
   - Hybrid approach?

2. **How much detail in loop state?**
   - Full transcript (expensive, complete context)
   - Summary only (cheaper, less context)
   - Adaptive (detailed when needed)?

3. **Human review frequency?**
   - Daily (full control, more overhead)
   - Weekly (less overhead, slower feedback)
   - On-demand (flag only issues)?

4. **Loop timeout values?**
   - Conservative (5 iterations, fail fast)
   - Generous (15 iterations, thorough)
   - Adaptive (based on task complexity)?

5. **Agent count per loop?**
   - Minimal (2 agents, faster)
   - Standard (3-4 agents, balanced)
   - Comprehensive (5+ agents, thorough)?

---

## Related Documents

- `workflows/autonomous_development_loops.md` - Architecture vision
- `workflows/parallel_development.md` - Practical workflow
- `docs/vision.md` - Original Meta-AI vision
- `MAIN_REFACTOR_NOTES.md` - First use case

---

**Philosophy:** Build incrementally, test thoroughly, learn continuously, scale confidently.

**Goal:** Wake up every morning to completed, reviewed, tested code ready for approval.

**Timeline:** 3 months to autonomous development system.

Let's build it.
