# Auto-Fix Decision Heuristics

**Purpose:** Guide Claude's judgment on when to fix, investigate, or escalate errors
**Updated:** November 1, 2025

---

## Core Principle

**You are not expected to fix everything.** Your job is to assess each error and decide the appropriate action based on evidence, risk, and scope constraints.

---

## Decision Framework

### When to FIX Autonomously

✅ **Fix if ALL of these are true:**

1. **Root cause is clear from logs/journal**
   - Error pattern is obvious
   - Similar to previously solved problems
   - Evidence points to single cause

2. **Fix is localized and low-risk**
   - Changes required: <3 files
   - Lines changed: <50 total
   - No database schema modifications
   - No business logic decisions needed

3. **Fix is testable**
   - Can verify with syntax check
   - Can test with process restart
   - Success criteria are clear

4. **Within safety constraints**
   - No protected file modifications needed
   - No credential/security implications
   - Can be backed up and reversed

**Examples of fixable errors:**
- Duplicate contract hash (add deduplication)
- Missing error handling (add try/catch)
- Wrong database path (use query DB instead of primary)
- Incorrect variable type (add type conversion)
- Threading race condition (add lock or deduplicate)

---

### When to INVESTIGATE (Add Diagnostics)

🔍 **Investigate if ANY of these are true:**

1. **Root cause unclear**
   - Multiple competing hypotheses
   - Logs don't show clear failure point
   - Error is intermittent or timing-dependent

2. **First occurrence**
   - No previous journal entries for this error
   - Unknown territory
   - Need more data to understand

3. **Complex system interaction**
   - Multiple components involved
   - Unclear which layer is failing
   - Could be API, database, or code

4. **Approaching session limits**
   - Already made 2 edits (max 3 allowed)
   - Running low on time (8+ minutes elapsed)
   - Better to add logging for next spawn

**Investigation actions:**
- Add detailed logging at suspected failure points
- Add assertions to verify assumptions
- Add timing/performance measurements
- Add duplicate detection counters
- Document findings in journal for next spawn

**Examples:**
- "API returns 200 but data missing" → Add logging of API response
- "Alerts work sometimes but not always" → Add counters for each scan phase
- "Database writes fail randomly" → Add disk space check, lock detection logging

---

### When to ESCALATE to Human

🚨 **Escalate immediately if ANY of these are true:**

1. **Requires business logic decision**
   - "Which data source is correct?"
   - "Should we use IV from table A or table B?"
   - "What threshold should trigger alerts?"

2. **Database schema change needed**
   - Adding/removing columns
   - Changing primary keys
   - Creating new tables
   - Modifying indexes

3. **Security/credentials implications**
   - API key configuration
   - Authentication logic
   - Permission settings
   - Protected file modifications required

4. **Outside scope constraints**
   - Would require >3 file edits
   - Would require >50 line changes
   - Would require architectural refactoring
   - Would change function signatures broadly

5. **Already tried twice today**
   - Journal shows 2 previous attempts at this error
   - Different approaches didn't work
   - Need human to reassess approach

6. **Infrastructure issue (not code)**
   - Disk space exhausted
   - Tradier API is down
   - Database corruption detected
   - Network connectivity issues

**Escalation process:**
1. Update journal with analysis performed
2. Document what was ruled out
3. List what needs human decision
4. Email report with "ESCALATE" in subject
5. Do NOT restart process

**Examples:**
- "UNIQUE constraint on earnings_events" → Data integrity decision
- "Tradier API returns 401" → Credential issue
- "Need to refactor entire collection pipeline" → Too broad
- "Fix requires changing 8 files" → Exceeds scope

---

## Risk Assessment

Before taking action, assess risk level:

### Low Risk (Safe to fix autonomously)
- Adding deduplication logic
- Adding error handling
- Fixing variable types
- Adding validation checks
- Correcting database paths

### Medium Risk (Fix carefully, validate thoroughly)
- Modifying collection logic
- Changing SQL queries
- Adjusting thresholds
- Threading/concurrency changes
- Timeout/retry logic

### High Risk (Consider investigating instead)
- Modifying core libraries
- Changing API request logic
- Database transaction handling
- Strategy coordination
- Main orchestrator logic

**Rule of thumb:** If you're uncertain about risk level, choose to investigate rather than fix.

---

## Scope Limits (Enforced)

**Hard Limits:**
- Maximum 3 file edits per session
- Maximum 1 process restart per session
- Maximum 10 minute session time

**Soft Limits (use judgment):**
- Maximum 50 lines changed total
- Maximum 3 functions modified
- No function signature changes
- No broad refactoring

**If fix would exceed limits:**
1. Do partial fix (address immediate symptom)
2. Add diagnostics for deeper issues
3. Document in journal: "Partial fix applied, full solution needs X"
4. Next spawn can continue the work

---

## Common Error Patterns

### Pattern: Duplicate Contract Hash

**Symptom:** UNIQUE constraint failed: (contract_hash, trade_date)

**Decision:** FIX

**Approach:**
1. Add deduplication before INSERT
2. Log duplicate occurrences
3. Keep system running (safety net first)

**Why fixable:** Localized change, clear solution, low risk

---

### Pattern: No Alerts Generated (2+ hours)

**Symptom:** Flow Monitor running but no alerts in 2 hours during market hours

**Decision:** INVESTIGATE (first occurrence) or FIX (if journal shows clear pattern)

**Investigation approach:**
1. Add logging: "How many contracts scanned?"
2. Add logging: "How many met threshold?"
3. Add logging: "What were significance scores?"
4. Add logging: "Is baseline data present?"

**Fix approach (if pattern clear):**
- If baseline missing → regenerate baseline
- If threshold too high → adjust threshold
- If database write failing → fix write logic

**Why investigate first:** Multiple possible causes, need data to narrow down

---

### Pattern: Database Locked

**Symptom:** OperationalError: database is locked

**Decision:** FIX

**Approach:**
1. Check: Is code using datalake.db instead of datalake_query.db?
2. If yes: Change to query database
3. If no: Add retry logic with backoff
4. If persistent: Escalate (infrastructure issue)

**Why fixable:** Usually simple path correction, localized change

---

### Pattern: API Rate Limit

**Symptom:** Tradier API returns 429 Too Many Requests

**Decision:** INVESTIGATE or ESCALATE

**Investigation:**
- Check: How many requests in past minute?
- Check: Is batch size too large?
- Check: Are we retrying failed requests repeatedly?

**Escalate if:**
- Rate limit is lower than expected → Account configuration
- We're within documented limits → API issue

**Why not fixable:** Might be external (API), might need throttling redesign

---

### Pattern: Silent Failure (No Output)

**Symptom:** Collection runs successfully but stores 0 rows

**Decision:** INVESTIGATE

**Investigation:**
1. Add logging: "API response received: X contracts"
2. Add logging: "After filtering: Y contracts"
3. Add logging: "After deduplication: Z contracts"
4. Add logging: "Database INSERT result: N rows"

**Why investigate:** Need to find where data is lost in pipeline

---

## Journal Usage

**Before deciding, check journal:**

1. Has this error been seen today?
   - If yes: What approach was tried?
   - If failed: Don't repeat same fix
   - If succeeded: Why did it recur?

2. Any patterns in past week?
   - If yes: Learn from previous attempts
   - If no: First occurrence, investigate cautiously

3. What diagnostics were added?
   - If previous spawn added logging: Use that data
   - If logs now show root cause: Fix confidently

**Update journal with decision:**
- "Decided to FIX because: [reasoning]"
- "Decided to INVESTIGATE because: [reasoning]"
- "Decided to ESCALATE because: [reasoning]"

---

## Session Strategy

**First 2 minutes:**
1. Read journal (today + recent)
2. Read error context
3. Review relevant logs
4. Assess root cause clarity

**Next 3 minutes:**
5. Decide: Fix, Investigate, or Escalate
6. If fix: Identify exact changes needed
7. If investigate: Plan diagnostic additions
8. If escalate: Document analysis

**Next 3 minutes:**
9. Execute decision (make changes)
10. Create backups
11. Validate syntax

**Final 2 minutes:**
12. Restart if fixing (verify startup)
13. Update journal
14. Email report

**If running low on time (>8 minutes):**
- Don't start new investigation
- Finish current work
- Document partial progress
- Next spawn can continue

---

## Output Standards

**Journal Entry Template:**

```markdown
## [HH:MM] Error Type - Brief Description

### Decision: FIX / INVESTIGATE / ESCALATE

**Reasoning:**
- [Why this decision was made]
- [What evidence supports it]
- [What was ruled out]

**Action Taken:**
- [Specific changes made or diagnostics added]
- Files modified: path/to/file.py:line_number
- [Why this should work / what data it will provide]

**Outcome:**
- [Restart successful / Diagnostics added / Escalated]
- [Verification results]

**Next Steps:**
- [If error recurs → Try X]
- [If diagnostics added → Next spawn will have Y data]
- [If escalated → Human needs to decide Z]
```

---

## Remember

1. **Safety first:** Protected files, backups, validations
2. **Evidence-based:** Logs and journal guide decisions
3. **Scope awareness:** Stay within session limits
4. **Honesty:** Document uncertainty, don't claim certainty
5. **Continuity:** Each spawn builds on previous work

You're one session in a potential multi-session debugging effort. Do your part well, document clearly, and trust the next spawn to continue if needed.

---

**Last Updated:** November 1, 2025
