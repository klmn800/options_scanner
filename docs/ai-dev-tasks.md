# AI Dev Tasks - Structured Feature Development

## Overview
options_scanner uses the AI Dev Tasks workflow for building complex features systematically. This structured approach ensures clear requirements, comprehensive planning, and methodical implementation with verification checkpoints.

## 🚨 MANDATORY: Always Offer PRD Workflow for Big Tasks

**When Ben proposes a major task, ALWAYS ask if he wants to use the PRD workflow before diving into implementation.**

**Detection criteria - if any of these apply, suggest PRD:**
- New strategy module or significant system component
- Features spanning multiple files/systems (>5 files)
- Database schema changes + new business logic
- Unclear scope or requirements ("build a tracking system", "integrate X with Y")
- Work that will take >30 minutes to implement
- Features mentioned in roadmap: airline_play, daily_analysis AI, sector rotation

**How to ask:**
```text
This looks like a complex feature. Would you like to:
1. Use the PRD workflow (structured planning → task list → implementation)
2. Start implementing directly (I'll use TodoWrite to track progress)

The PRD workflow is recommended for features like this to ensure we don't miss requirements.
```

**When NOT to ask:**
- Ben explicitly requests TodoWrite approach
- Ben references an existing PRD/task list
- Simple bug fixes or minor tweaks
- Quick database queries or one-off analysis scripts
- Documentation-only updates

## When to Use AI Dev Tasks

Use this workflow for:
- **Major new features** (new strategy modules, significant system components)
- **Complex integrations** (multi-system features spanning database, APIs, UI)
- **Architectural changes** (database migrations, system refactoring)
- **Features with unclear scope** (when requirements need clarification)

Skip this workflow for:
- **Simple bug fixes** (use TodoWrite tool directly)
- **Minor enhancements** (small tweaks to existing features)
- **Quick one-off scripts** (analysis scripts, database queries)
- **Documentation updates** (unless part of larger feature)

## The 3-Step Workflow

### Step 1: Create a PRD (Product Requirements Document)
Start by defining what you're building, why, and for whom.

**Usage:**
```text
Use @ai-dev-tasks/create-prd.md
Here's the feature I want to build: [Describe your feature]
Reference these files: [Optional: @relevant_file1.py @relevant_file2.py]
```

**What happens:**
1. Claude Code asks clarifying questions about requirements
2. You answer to define scope, goals, success criteria
3. PRD is saved as `/tasks/[n]-prd-[feature-name].md`

**Example PRD names:**
- `tasks/0001-prd-airline-tracking-system.md`
- `tasks/0002-prd-sector-rotation-strategy.md`
- `tasks/0003-prd-daily-analysis-ai-integration.md`

### Step 2: Generate Task List from PRD
Break down the PRD into granular, actionable implementation tasks.

**Usage:**
```text
Take @tasks/0001-prd-airline-tracking-system.md and create tasks using @ai-dev-tasks/generate-tasks.md
```

**What happens:**
1. Claude Code analyzes the PRD and existing codebase
2. Generates 5-7 high-level parent tasks
3. Asks for confirmation ("Ready to generate sub-tasks? Respond with 'Go'")
4. Breaks each parent task into detailed sub-tasks (3-8 per parent)
5. Task list saved as `/tasks/tasks-[n]-prd-[feature-name].md`

**Task structure example:**
```markdown
1. Database Schema & Models
   1.1 Create airline_tracking table with required columns
   1.2 Add indexes for performance optimization
   1.3 Create database migration script

2. Data Collection Pipeline
   2.1 Implement airline options data fetcher
   2.2 Add filtering logic for relevant contracts
   2.3 Integrate with existing Tradier API client
```

### Step 3: Process Task List (Implementation)
Execute tasks one at a time with verification checkpoints.

**Usage (First task only):**
```text
Please start on task 1.1 and use @ai-dev-tasks/process-task-list.md
```

**What happens:**
1. Claude Code implements task 1.1 only
2. Marks task 1.1 as completed in the task list
3. Asks "Task 1.1 complete. Review?"
4. You respond "yes" to proceed or provide feedback
5. Claude Code moves to task 1.2 automatically
6. When all sub-tasks complete, runs tests and creates git commit
7. Process continues until all tasks completed

**Important:**
- Only reference `@process-task-list.md` for the **first task** - it guides subsequent tasks automatically
- Review each task before approving continuation
- Claude Code will commit after each parent task completion (all sub-tasks done)

## Workflow Benefits

**For Complex Features:**
- ✅ Clear scope definition before coding
- ✅ Comprehensive task breakdown (nothing forgotten)
- ✅ Systematic progress tracking across sessions
- ✅ Quality verification at each checkpoint
- ✅ Prevents scope creep and feature drift

**For Communication:**
- ✅ Ben approves the plan before implementation
- ✅ Claude Code has full context of requirements
- ✅ Easy to pause/resume work across multiple sessions
- ✅ Clear visibility into what's done vs. pending

**For Quality:**
- ✅ Each task reviewed before proceeding
- ✅ Tests run after each parent task completion
- ✅ Git commits with descriptive context
- ✅ Reduced rework from unclear requirements

## Example: Airline Play Transformation

**Current situation:** `strategies/airline_play/` exists but needs full research/tracking system

**With AI Dev Tasks workflow:**
```text
1. Use @ai-dev-tasks/create-prd.md
   "Transform airline_play into comprehensive tracking system with:
   - Historical earnings move analysis
   - Real-time alert generation
   - Integration with daily_analysis
   - Performance tracking and reporting"

2. Answer clarifying questions about:
   - Data sources (earnings API, options data)
   - Alert criteria (what triggers a signal?)
   - Integration points (Oracle, Chrome extension?)
   - Success metrics (what defines "working"?)

3. Review generated PRD (tasks/0001-prd-airline-tracking.md)

4. Generate task list: @ai-dev-tasks/generate-tasks.md

5. Review 20-30 detailed implementation tasks

6. Start implementation: "Begin task 1.1 and use @ai-dev-tasks/process-task-list.md"

7. Systematic implementation with checkpoints
```

## Files & Storage

**AI Dev Tasks Templates:**
- `ai-dev-tasks/create-prd.md` - PRD generation guide
- `ai-dev-tasks/generate-tasks.md` - Task list creation guide
- `ai-dev-tasks/process-task-list.md` - Implementation workflow

**Generated Documents:**
- `/tasks/[n]-prd-*.md` - Product Requirements Documents
- `/tasks/tasks-[n]-prd-*.md` - Task lists for each PRD
- Naming convention: `0001`, `0002`, `0003` (zero-padded 4-digit sequence)

## Integration with TodoWrite

AI Dev Tasks **complements** the built-in TodoWrite tool:
- **AI Dev Tasks**: For large features requiring upfront planning (PRD → Tasks)
- **TodoWrite**: For tracking sub-tasks during implementation and smaller work

During step 3 (process-task-list), Claude Code may use TodoWrite internally to track sub-task progress, but the main task list remains in markdown files under `/tasks/`.
