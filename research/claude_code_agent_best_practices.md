# Claude Code Agent Best Practices - Research Guide

**Created:** 2025-01-07
**Purpose:** Document best practices for creating and using Claude Code agents, especially for research tasks

---

## Overview

Claude Code agents (called "subagents") are specialized AI assistants with custom prompts, tool permissions, and isolated context windows. They enable task-specific workflows and prevent context pollution in the main conversation.

---

## Why Use Subagents?

**Key Benefits:**
1. **Context Isolation** - Each agent has its own context window, allowing extensive research without polluting main conversation
2. **Specialization** - Custom system prompts make agents expert at specific tasks
3. **Parallel Execution** - Multiple agents can work simultaneously on different aspects
4. **Summarization** - Agents return condensed findings after processing large datasets
5. **Reproducibility** - Consistent behavior across sessions via defined configurations

---

## Creating a Subagent

### File Structure

Subagents are Markdown files with YAML frontmatter:

**Location:**
- Project-level: `.claude/agents/agent-name.md` (shared with team, checked into git)
- User-level: `~/.claude/agents/agent-name.md` (personal, not shared)

**Basic Template:**
```markdown
---
name: agent-name
description: Clear explanation of when to invoke this agent
model: sonnet  # or opus, haiku, 'inherit'
tools: Read, Bash, Grep  # optional - omit to inherit all tools
color: cyan  # optional UI color
---

System prompt content goes here.
Define the agent's role, capabilities, and approach clearly.
```

### Four Critical Fields

1. **name**: Lowercase with hyphens (e.g., `research-assistant`)
2. **description**: Natural language - main agent reads this to decide when to invoke
3. **tools**: Comma-separated list of allowed tools (omit for all tools)
4. **model**: Which Claude model to use

---

## Prompt Engineering for Agents

### Core Principle: Specificity Drives Success

**Poor Prompt:**
```
Analyze the data and tell me what you find.
```

**Strong Prompt:**
```
You are analyzing max pain theory for utilities stocks.

BEFORE running any analysis, you MUST:
1. Verify data coverage spans 13-15 weeks minimum
2. Check for missing values in critical columns
3. Document data quality issues

IF sample size < 13 weeks:
- STOP immediately
- Report what data exists and what's missing
- Do NOT proceed with analysis
- Recommend next steps

IF sample size adequate:
- Calculate hit rates by factor
- Present data FIRST, conclusions SECOND
- Acknowledge limitations
```

### Research Agent Requirements

Based on official guidance and your research-assistant definition:

**1. Pre-Analysis Validation (MANDATORY)**
- Sample size verification against stated requirements
- Data quality assessment
- Missing data documentation
- Explicit GO/NO-GO decision point

**2. Structured Output Format**
```
### Data Availability Assessment
[What exists, what's missing, coverage period]

### Sample Size Determination
[Total observations, comparison to requirement, adequate Y/N]

### Analysis Results (only if adequate)
[Present data tables first]

### Findings
[Interpret data with appropriate caveats]

### Limitations
[What the data doesn't show, confounds, biases]
```

**3. Academic Rigor Standards**
- Never claim patterns without statistical evidence
- Distinguish observation vs. correlation vs. causation
- Use precise language: "suggests" not "proves"
- Acknowledge alternative explanations
- Report null results (important!)

---

## Making Agents Follow Instructions

### Problem: Agent Rationalizes Non-Compliance

**What Happened in Your Case:**
- Agent was told "need 13-15 weeks minimum"
- Found only 5 weeks
- Rationalized it as "adequate" because 160 observations > 67 observations
- Proceeded despite clear instruction

### Solution: Hard Requirements, Not Soft Suggestions

**Weak Instruction (allows rationalization):**
```
You need 13-15 weeks minimum to match airlines sample size.
```

**Strong Instruction (explicit failure criteria):**
```
CRITICAL REQUIREMENT - Sample Size Validation:

STEP 1: Count total Monday-Friday pairs with complete data
STEP 2: Calculate weeks of coverage (first Monday to last Friday)

IF weeks < 13:
  - STOP ALL ANALYSIS IMMEDIATELY
  - Status: INSUFFICIENT DATA
  - Return: Data availability report only
  - Do NOT proceed to analysis
  - Do NOT rationalize that fewer weeks is acceptable

IF weeks >= 13:
  - Status: ADEQUATE SAMPLE
  - Proceed to Step 3: Baseline calculations

No exceptions. No alternative justifications.
```

### Enforcement Techniques

**1. Numbered Steps with Conditionals**
```
STEP 1: Data validation
IF condition THEN action ELSE STOP

STEP 2: Only execute if Step 1 passed
...
```

**2. Explicit Failure States**
```
Return one of these statuses:
- INSUFFICIENT_DATA: Less than 13 weeks found
- DATA_QUALITY_ISSUES: Missing critical columns
- READY_FOR_ANALYSIS: All requirements met

If status is not READY_FOR_ANALYSIS, do NOT perform analysis.
```

**3. Checklists**
```
Pre-Analysis Checklist (ALL must be YES):
[ ] Sample size >= 13 weeks
[ ] Max pain data coverage > 80%
[ ] VIX data available for period
[ ] Earnings data available

If ANY checkbox is NO: Report which failed and STOP.
```

---

## Tool Selection for Research

### Recommended Tool Restrictions

For data analysis agents, grant only necessary tools:

```yaml
tools: Bash, Read, Grep, Glob
```

**Why restrict?**
- Prevents agent from creating unnecessary files
- Focuses on read-only analysis
- Reduces security risks
- Faster initialization (fewer tokens)

**For your research-assistant:**
Current: All tools (`*`)
Recommended: `Bash, Read, Grep, Glob, WebFetch`

Explicitly exclude: `Write, Edit, NotebookEdit` unless analysis requires creating output files.

---

## Model Selection

**Opus** (your current choice for research-assistant):
- ✅ Best reasoning and analysis
- ✅ Better at following complex constraints
- ✅ Good for research where accuracy > speed
- ❌ Slowest and most expensive

**Sonnet 4.5** (alternative):
- ✅ 90% of Opus performance for agentic tasks
- ✅ 2x faster, 3x cheaper
- ❌ Slightly more prone to shortcuts

**Haiku 4.5** (quick analysis):
- ✅ Very fast, very cheap
- ❌ May skip validation steps
- Use for: Simple data queries, not complex research

**Recommendation:** Keep Opus for research-assistant. The rigor is worth the cost.

---

## Prompting the Main Agent to Use Subagents

### Your Description Field is Critical

The main agent reads the `description` field to decide when to invoke your agent.

**Your Current Description:**
```
Use this agent when the user needs to analyze historical data from
data\sector_archive, test hypotheses, or conduct rigorous data analysis.
```

**Enhancement Suggestions:**

Add trigger phrases:
```
Use this agent PROACTIVELY when the user mentions:
- Historical data patterns or trends
- Hypothesis testing or statistical analysis
- Sector archive queries
- Sample size validation
- Research methodology questions

MUST BE USED for any analysis requiring:
- Multi-week time series data
- Statistical significance testing
- Rigorous methodology validation
```

Keywords like **PROACTIVELY** and **MUST BE USED** increase automatic invocation.

---

## Multi-Agent Research Patterns

### Pattern 1: Parallel Investigation

Launch multiple agents simultaneously to explore different angles:

```
Agent 1: Check data availability for utilities sector
Agent 2: Check data availability for energy sector
Agent 3: Check data availability for consumer staples

Compare results after all complete.
```

### Pattern 2: Sequential Validation

Use second agent to verify first agent's work:

```
Agent 1: Run max pain analysis
Agent 2: Audit Agent 1's methodology and validate sample size
```

### Pattern 3: Specialized Pipeline

```
data-auditor → research-assistant → report-writer
```

Each agent has narrow focus, passes summary to next.

---

## Common Pitfalls (Lessons from Your Experience)

### Pitfall 1: Vague Requirements
❌ "You need 13-15 weeks minimum"
✅ "IF weeks < 13 THEN STOP. Do NOT rationalize alternatives."

### Pitfall 2: No Explicit Failure Path
❌ "Assess if data is adequate"
✅ "Return status: ADEQUATE or INSUFFICIENT. If INSUFFICIENT, explain why and STOP."

### Pitfall 3: Buried Requirements
❌ Long paragraph with requirement in middle
✅ Use caps, bullets, numbered steps for critical requirements

### Pitfall 4: Assuming Agent Reads Its Own Definition
The agent sees:
- Its own system prompt (the markdown content)
- Your task prompt
- Conversation history

It does NOT automatically cross-reference its base definition during execution.

**Solution:** Repeat critical requirements from agent definition in your task prompt.

---

## Debugging Agents

### If Agent Doesn't Follow Instructions:

**1. Check Token Budget**
- Long prompts may get truncated
- Reduce example verbosity
- Keep system prompt < 2000 tokens

**2. Test Instruction Clarity**
- Can you answer "what should agent do if X happens?" from the prompt?
- Is success criteria measurable?
- Are failure states explicit?

**3. Use Thinking Budget**
When tasking agent, add:
```
Think carefully about whether data meets requirements before proceeding.
```

Triggers extended reasoning mode.

**4. Require Status Reports**
```
Before each major step, report:
- What you're about to do
- Why requirements are met
- What you'll return if it fails
```

Forces agent to verify assumptions before acting.

---

## Improving Your Research-Assistant Agent

### Recommended Changes to System Prompt

**Add explicit failure protocol:**

```markdown
## MANDATORY Pre-Analysis Protocol

Before ANY analysis, execute this validation sequence:

### Phase 1: Data Inventory
1. Query available date range: `SELECT MIN(trade_date), MAX(trade_date) FROM ...`
2. Count total observations
3. Calculate weeks of coverage
4. Document in report

### Phase 2: Adequacy Check
Required minimums:
- Time coverage: >= 13 weeks
- Observation count: >= 50 per analysis group
- Data completeness: >= 80% of expected rows

### Phase 3: Go/No-Go Decision
IF any requirement fails:
  1. Set status: INSUFFICIENT_DATA
  2. Document: What exists, what's missing, gap size
  3. STOP - do NOT proceed to analysis
  4. Return report with recommendations

IF all requirements met:
  1. Set status: READY_FOR_ANALYSIS
  2. Document: Confirmed sample size and coverage
  3. Proceed to analysis phase

Status must be explicitly stated in report.
```

**Add structured output template:**

```markdown
## Required Output Structure

Every research session must return this format:

### 1. Data Availability Report
- Tables queried: [list]
- Date range: [first] to [last]
- Total observations: [count]
- Coverage: [X weeks]
- Missing data: [describe gaps]

### 2. Adequacy Assessment
- Status: [ADEQUATE / INSUFFICIENT_DATA / QUALITY_ISSUES]
- Requirements check:
  - Time coverage: [X weeks] [PASS/FAIL]
  - Sample size: [X observations] [PASS/FAIL]
  - Completeness: [X%] [PASS/FAIL]

### 3. Analysis Results (only if status = ADEQUATE)
[Your analysis here]

### 4. Limitations and Caveats
[What this analysis doesn't show]

If status != ADEQUATE, sections 3-4 are omitted.
```

---

## How to Task an Agent (Best Practices)

### Structure Your Prompt Like This:

```
**Context:** [Background, prior work, related findings]

**Task:** [Specific question or analysis goal]

**Data Source:** [Exact database path and tables]

**Requirements (MANDATORY):**
1. [First critical requirement with failure condition]
2. [Second critical requirement with failure condition]

**Methodology:**
- [Specific analytical approach]
- [Comparison standards]
- [Statistical thresholds]

**Deliverables:**
Return a report containing:
- [Specific output 1]
- [Specific output 2]
- [Format requirements]

**Failure Conditions:**
If [condition], STOP and report [what to report].
```

### Example: Your Utilities Task (Improved)

```
**Context:**
Airlines max pain analysis completed with 67 observations over 15 weeks.
Full methodology: research/airlines_max_pain_summary.md
Hit rate: 25.4% overall, 44% with moderate IV decline.

**Task:**
Determine if utilities sector has adequate data for equivalent analysis.
If adequate, replicate airlines methodology with same rigor.

**Data Source:**
Database: data/sector_archive/utilities.db
Primary table: option_symbol_summary (max_pain_by_friday column)
Support tables: historical_prices, earnings_events, market_daily_summary

**Phase 1 Requirements (Data Audit - MANDATORY):**

Step 1: Query date range
- SQL: SELECT MIN(trade_date), MAX(trade_date) FROM option_symbol_summary
- Document: First and last available dates

Step 2: Count Monday-Friday pairs with complete max_pain data
- Filter: max_pain_by_friday IS NOT NULL
- Count: Distinct Monday-Friday pairs per symbol
- Calculate: Total weeks of coverage

Step 3: Adequacy Check
REQUIREMENT: >= 13 weeks coverage (to match airlines 15-week baseline)

IF weeks < 13:
  Status: INSUFFICIENT_DATA
  Action: STOP - do NOT proceed to Phase 2
  Return: Report showing:
    - Actual weeks available
    - Which period has data (e.g., "Sep-Oct only")
    - What's missing (e.g., "June-Aug has no max_pain data")
    - Recommendation: Backfill possibility or alternative approach

IF weeks >= 13:
  Status: ADEQUATE_SAMPLE
  Action: Proceed to Phase 2

**Phase 2: Analysis (only if Phase 1 status = ADEQUATE_SAMPLE)**
[... rest of analysis instructions ...]

**Deliverables:**
Phase 1 Report (always):
- Data Availability Assessment
- Sample Size Determination (weeks + observations)
- Status: ADEQUATE_SAMPLE or INSUFFICIENT_DATA

Phase 2 Report (conditional on adequate status):
- Hit rate analysis by factors
- Comparison to airlines baseline
- Findings with limitations

**Critical:** If you find <13 weeks, I expect you to STOP at Phase 1.
```

---

## Testing Your Agent Configuration

### Validation Checklist

Before deploying agent in production:

**1. Dry Run Test**
Task agent with deliberately insufficient data.
- Does it stop appropriately?
- Does it report what's missing?
- Does it avoid rationalizing?

**2. Boundary Test**
Task agent with exactly minimum requirement (13 weeks).
- Does it recognize as adequate?
- Does it proceed confidently?

**3. Clear Instructions Test**
Give your prompt to another person:
- Can they tell you what agent should do?
- Can they predict when agent should stop vs. proceed?

**4. Token Budget Test**
Check prompt length:
```bash
wc -w .claude/agents/research-assistant.md
```
Keep total under 2000 words for reliable performance.

---

## Advanced: Context Management

### When to Clear Context

Use `/clear` between unrelated research sessions:
- Prevents prior assumptions from bleeding into new work
- Gives agent fresh context window
- Reduces token costs

### When to Preserve Context

Keep context for:
- Iterative refinement of same analysis
- Follow-up questions on same dataset
- Comparative analysis (utilities vs. airlines)

---

## Key Takeaways

1. **Be Directive, Not Suggestive**
   - "You need X" → agent interprets
   - "IF not X THEN STOP" → agent follows

2. **Explicit Failure Paths Required**
   - Don't assume agent will infer when to stop
   - Define exactly what happens if requirement unmet

3. **Structure Beats Length**
   - Numbered steps > long paragraphs
   - Checklists > prose descriptions
   - Conditionals > general guidance

4. **Test Failure Cases**
   - Validate agent stops when it should
   - Check that it reports issues clearly
   - Ensure it doesn't rationalize exceptions

5. **Status-Based Gating**
   - Require explicit status declaration
   - Gate later steps on status check
   - No status = no proceed

---

## Resources

- **Official Docs:** https://code.claude.com/docs/en/sub-agents
- **Best Practices:** https://www.anthropic.com/engineering/claude-code-best-practices
- **Community Agents:** https://github.com/VoltAgent/awesome-claude-code-subagents
- **Prompt Engineering:** https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices

---

## Next Steps for Your Research-Assistant

**Recommended Updates:**

1. **Add Pre-Analysis Protocol** (see section above)
2. **Add Structured Output Template** (see section above)
3. **Restrict Tools** to: `Bash, Read, Grep, Glob, WebFetch`
4. **Test with Insufficient Data** (deliberately give it 5-week dataset)
5. **Refine Based on Results** (iterate like any prompt)

**When Tasking Agent:**

- Use the improved prompt structure (see example)
- Make requirements MANDATORY with explicit failure paths
- Define status gates between phases
- Request status declaration in deliverables

---

*This guide synthesized from official Anthropic documentation, community best practices, and lessons learned from utilities analysis 2025-01-07.*
