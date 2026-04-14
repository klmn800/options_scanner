# Autofix Enhancement Ideas

**Source:** Batch fix session 2026-02-10, discussion between Ben and batch agent about recurring `quick_sync_operation_failed` error (15 occurrences, 5 dates).

---

## 1. Severity Filtering in Batch Spawner

**Problem:** `find_todays_errors()` in `batch_mode_tracker.py:60` filters only on `fix_status == 'pending'` and ignores severity entirely. The Jan 21 agent downgraded lock errors to WARNING severity intending to prevent batch autofix from spawning, but it had zero effect — every pending error gets a session regardless.

**Fix:** Add severity filtering to `find_todays_errors()` or `check_and_spawn_batch_mode()`. Options:
- Skip WARNING severity errors in batch mode (simplest)
- Add a configurable severity threshold
- Or better: use the `decision_type` approach below

## 2. Decision Classification for Error Resolutions

**Problem:** When an agent concludes "this error is by design, the fallback handles it," that conclusion is buried in free-text notes. Future agents re-investigate the same issue because there's no structured way to say "this was already decided."

**Proposal:** Add a `decision_type` field to `mark_error_fixed()`:
- `"fixed"` — Code was changed, error should not recur
- `"by_design"` — System handles this gracefully, no fix needed
- `"needs_monitoring"` — Added diagnostics, check next occurrence
- `"deferred"` — Needs human input or more data

The batch spawner could then skip errors whose `error_type` has been classified as `by_design` in the past N days, unless frequency increases significantly.

## 3. Note Truncation in Batch Context

**Problem:** The `same_error_history` in `batch_context_*.json` truncates notes with `[TRUNCATED - see error file for full notes]`. This means agents don't see the full reasoning from previous sessions without manually reading old error files.

**Fix options:**
- Remove truncation (notes are usually 500-1000 chars, not huge)
- Preserve at least the first section (ROOT CAUSE + FIX APPLIED) untruncated
- Add a `summary` field (one-liner) that's always shown in full, separate from detailed `notes`

## 4. Agent Reasoning Preservation

**Problem:** The notes template captures WHAT was done but not WHY a decision was made. The Jan 21 agent had a nuanced conversation with Ben about "the fallback mechanism works, this isn't really a problem" — but that reasoning was lost. Future agents only see "no code changes required."

**Proposal:** Add a `RATIONALE:` section to the notes template in `BATCH_MODE_INSTRUCTIONS.md`. Specifically prompt agents to explain:
- Why they chose their approach over alternatives
- What they considered and rejected
- Whether the error should continue triggering autofix or not

## 5. "Known Issues" Registry

**Problem:** Recurring transient errors (like quick_sync lock failures) repeatedly spawn batch sessions that all reach the same conclusion. This wastes API budget and produces no value.

**Proposal:** A simple `autofix/known_issues.json` file that batch agents check before investigating:
```json
{
  "quick_sync_operation_failed": {
    "classification": "by_design",
    "last_reviewed": "2026-02-10",
    "summary": "Transient lock during market hours. Fallback retry + next-cycle sync handles it.",
    "suppress_batch_until": "2026-03-10",
    "reopen_if": "frequency > 5 per day or severity escalates"
  }
}
```

The batch spawner checks this before spawning. If the error type is listed and conditions haven't changed, it skips. Agents can update this file when they resolve errors.

---

## Implementation Priority (suggested)

1. **Severity filtering or known issues registry** — Stops the bleeding (no more wasted sessions on known transients)
2. **Decision classification** — Structured data > free text for future agents
3. **Note truncation fix** — Quick win, preserves context
4. **Rationale section in template** — Cultural change, improves over time
