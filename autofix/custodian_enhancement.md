# Autofix Custodian Enhancement Proposal

**Date:** 2026-02-10
**Status:** DRAFT - Needs implementation planning
**Author:** Ben + Claude Code discussion

---

## The Gap We Identified

**Current state:** Autofix is purely reactive (error → fix → stop)

**Problem:**
- No verification that fixes actually worked
- No celebration when 8-day battles are won
- No distinction between bandaid fixes and robust solutions
- No dedicated time for developing solutions to recurring issues
- No follow-up on whether fixes held up over time
- No cleanup or refinement phase after fixing

**The Insight:**
> "If we spend 8 days working on an issue and finally fix it, there's no celebration, acknowledgement, followup, maintenance, feedback, QA, or cleanup afterwards. What if the fix is just a bandaid? There's no dedicated agent time to developing solutions to issues that pop up."

---

## Vision: Nightly Custodian Mode

Transform autofix from a **firefighter** into a **system custodian** that runs every night to:

1. ✅ Verify systems are healthy
2. 🔍 Follow up on recent fixes
3. 🩹 Identify bandaids that need upgrading
4. 🎉 Celebrate wins when battles are won
5. 🔧 Suggest architectural improvements
6. 📊 Build institutional knowledge about system patterns

---

## Primary Goals (User-Confirmed)

1. **Verification of fixes** - Did they actually work?
2. **Proactive issue detection** - Catch problems before they become critical
3. **Code quality improvement** - Upgrade bandaids to robust solutions
4. **Foundation for autonomous development** - Enable autofix to propose and implement improvements

---

## Proposed Three-Phase Nightly Run

### Phase 1: Verification (5-10 min)
**Question:** Did yesterday's systems run successfully?

- Check all pipeline completion markers
- Verify recent fixes are still working
- Scan error logs for new issues
- Review database health metrics

**Output:** ✅ Healthy / ⚠️ Issues detected

### Phase 2: Follow-Up (10-15 min)
**Question:** Are our recent fixes holding up?

- Track "fixed" issues for 7 days post-resolution
- Assess fix quality on 1-10 scale
- Flag bandaids that need refinement
- Celebrate wins when fixes prove stable

**Output:** 🎉 Wins / 🩹 Bandaids to upgrade / ⚠️ Regressions

### Phase 3: Maintenance (15-20 min)
**Question:** What patterns are emerging? What should we improve?

- Detect recurring issue patterns
- Suggest architectural improvements
- Identify technical debt to address
- Propose proactive refactoring

**Output:** 🔧 Recommendations / 📊 Pattern analysis

**Total runtime:** ~30-45 minutes per night

---

## Output Format (User Preference)

**Markdown journal** - open to other ideas

Proposed structure:
```
autofix/logs/custodian_journal_YYYY-MM-DD.md

# System Custodian Report - YYYY-MM-DD

## Status Summary
✅ Systems healthy | ⚠️ Issues found | 🔥 Critical problems

## Phase 1: Verification
- Option Pipeline: ✅ Completed successfully
- Flow Monitor: ✅ Ran 9:15 AM - 4:00 PM
- Database health: ⚠️ Query lag detected

## Phase 2: Follow-Up (Last 7 Days)
### Wins to Celebrate 🎉
- Fix #47 (news_collector encoding): 7 days stable!

### Bandaids to Upgrade 🩹
- Fix #45 (IV calculation): Temporary workaround, needs refactor
  - Quality score: 4/10
  - Recommendation: Refactor calc_implied_volatility()

### Regressions ⚠️
- None detected

## Phase 3: Maintenance Recommendations
### Recurring Patterns Detected
- UTF-8 encoding errors: 3 instances in 30 days
  - Suggest: Add subprocess encoding standard to code reviewer

### Technical Debt
- flow_alerts table: Consider indexing on significance_score
- Cache cleanup: 847 MB of expired Alpha Vantage cache

### Architectural Suggestions
- Consider extracting news sentiment to standalone module
```

---

## Chattiness Level

**User preference:** Depends on scope

**Options to decide later:**
1. Report every night regardless (build historical record)
2. Only alert when issues found (quiet unless needed)
3. Weekly summary + daily alerts (hybrid)
4. Configurable verbosity levels

---

## Integration Points

**User preference:** Integrate with main.py, but could also be scheduled job (both are easy)

### Option A: Integrated with main.py
```python
# New phase in main.py endless loop
if now_eastern().hour == 2 and now_eastern().minute < 30:
    run_system_custodian()
```

**Pros:**
- Unified scheduling
- Uses existing market calendar awareness
- Consistent logging infrastructure

**Cons:**
- Adds complexity to main.py
- Another thing to monitor in main loop

### Option B: Standalone Scheduled Job
```bash
# Windows Task Scheduler: 2:00 AM daily
python autofix/custodian.py
```

**Pros:**
- Separation of concerns
- Independent failure domain
- Can run even if main.py is stopped

**Cons:**
- Another scheduled task to manage
- Duplicate infrastructure

### Recommendation
Start with Option B (standalone), migrate to Option A after proven stable.

---

## Technical Implementation Ideas

### Fix Quality Scoring (1-10 scale)
```python
def assess_fix_quality(fix_record):
    score = 5  # baseline

    # Positive indicators
    if "test coverage added": score += 2
    if "root cause addressed": score += 2
    if "no recurrence in 7 days": score += 1

    # Negative indicators
    if "try/except bandaid": score -= 2
    if "TODO: refactor": score -= 1
    if "temporary workaround": score -= 2

    return max(1, min(10, score))
```

### Pattern Detection
```python
def detect_recurring_patterns(error_logs, window_days=30):
    """Find issues that keep coming back"""
    patterns = {}

    # Group by error type/location
    # Count occurrences in time window
    # Flag if frequency > threshold

    return patterns
```

### Win Celebration Criteria
```python
def check_for_wins(fix_history):
    """Identify completed victories"""
    wins = []

    for fix in fix_history:
        if fix.days_since_fixed == 7 and fix.no_recurrence:
            wins.append(fix)

    return wins
```

---

## Cost Estimation

**Claude API usage:**
- 3 phases × ~15-20K tokens/phase = ~60K tokens/night
- ~$0.02-0.05 per night
- ~$0.60-1.50 per month

**Value proposition:**
- Catch one critical issue early: Priceless
- Prevent one 8-day debugging marathon: Worth it
- Build institutional knowledge: Compounding returns

---

## Open Questions to Resolve Later

1. **What defines "healthy"?**
   - Pipeline completion markers?
   - Database row counts?
   - Error log patterns?
   - Response time thresholds?

2. **How do we track fix history?**
   - New table: `autofix_fix_history`?
   - Structured markdown parsing?
   - JSON metadata files?

3. **What triggers a bandaid upgrade?**
   - Quality score below threshold?
   - Manual review?
   - Recurrence count?

4. **How deep should maintenance go?**
   - Just suggestions?
   - Automated refactoring?
   - Test generation?
   - Documentation updates?

5. **How do we prevent alert fatigue?**
   - Severity levels?
   - Aggregation strategies?
   - Weekly digests?

6. **Should custodian self-improve?**
   - Learn from false positives?
   - Adjust thresholds over time?
   - Build knowledge base of patterns?

---

## Success Metrics

**How will we know this is working?**

1. **Reduced MTTR (Mean Time To Resolution)**
   - Catch issues earlier → faster fixes
   - Better context → smarter fixes

2. **Improved Fix Quality**
   - Fewer regressions
   - More robust solutions
   - Less technical debt

3. **Knowledge Accumulation**
   - Pattern library grows
   - Recurring issues decrease
   - Architectural improvements compound

4. **Developer Experience**
   - Fewer 8-day battles
   - More celebration moments
   - Better system understanding

---

## Next Steps (When Ready)

1. **Design database schema for fix tracking**
   - `autofix_fix_history` table
   - Quality scoring metadata
   - Pattern detection state

2. **Build Phase 1: Verification**
   - Define "healthy" criteria
   - Implement health checks
   - Generate status reports

3. **Build Phase 2: Follow-Up**
   - Fix quality assessment
   - 7-day tracking logic
   - Win detection

4. **Build Phase 3: Maintenance**
   - Pattern detection algorithms
   - Recommendation engine
   - Tech debt identification

5. **Integration & Scheduling**
   - Standalone script first
   - Test nightly runs
   - Refine output format
   - Consider main.py integration

6. **Feedback Loop**
   - Review first week of journals
   - Adjust chattiness
   - Tune scoring algorithms
   - Add new checks as needed

---

## Notes from Discussion

- "I kind of want autofix to run every night if only to check in and confirm that everything is alright"
- The celebration aspect is important - 8 days of work deserves acknowledgment
- Bandaid fixes are fine in the moment, but need dedicated time to refine
- This creates space for autonomous development and continuous improvement
- Foundation for autofix to evolve from reactive to proactive

**User's verdict:** "This is something we really need to do"

---

## Related Files

- `autofix/main.py` - Current autofix implementation
- `autofix/batch_mode_tracker.py` - Error tracking
- `autofix/logs/` - Error and fix journals
- `main.py` - Main orchestrator (potential integration point)

---

**END OF PROPOSAL**

Come back to this when you have time and focus. The foundation is solid - just needs implementation planning and execution.
