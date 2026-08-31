# Autofix — A Self-Healing Production System

> When my options-trading pipeline throws an error at 7:40 AM, no human is awake to fix it.
> So I built a system that diagnoses the root cause, edits the code, restarts the orchestrator,
> and emails me a report — autonomously, using Claude Code as the repair engine.
>
> **In production since November 2025.**

---

## The one-sentence version

A production error fires `queue_error()` or `handle_error()` → the system routes it by severity →
spawns a Claude Code session with full diagnostic context → the agent finds the root cause, backs up
and edits the offending code, restarts the process, and emails a report. Rate limits, escalation caps,
and automatic backups keep it from doing anything reckless.

The rest of this document peels that back one layer at a time. You can stop at any depth.

---

## By the numbers

Seven months of real production operation, reconstructed from the system's own error queues
([`errors/`](errors/)) and fix reports ([`logs/`](logs/)):

- **53 active days** of error handling, **Nov 2025 → June 2026**
- **42 distinct error types** diagnosed and fixed across 7 subsystems
- Severity routing in practice: **10 CRITICAL** (immediate spawn) vs. **~1,060 ERROR/WARNING** (batched)
- Deduplication doing real work: on one bad day, **692 raw error events collapsed to a single
  actionable fix** (see the April 7 gallery entry)

Every fix is auditable — prompts, journals, retrospective `notes`, and completion markers are all on disk.

---

## Why this is interesting

Most "self-healing" systems retry, restart, or fail over — they paper over the symptom. This one
**reads its own source code, reasons about the failure, and rewrites the code that caused it.** The
repair engine is a Claude Code agent given a tightly-scoped prompt, a curated knowledge base, and a
strict set of safety rails. The engineering challenge wasn't "call an LLM" — it was building the
**harness** around the LLM so that an autonomous agent editing production code at 2 AM is *safe*,
*bounded*, and *auditable*.

---

## Case study #1 — the six-day race condition it diagnosed by spotting a pattern

Real incident, reconstructed from the error queues and [`logs/batch_fix_report_2025-12-04_01.md`](logs/batch_fix_report_2025-12-04_01.md).

### What happened

The database sync threw `query_sync_operation_failed` (a `WinError 32` file-lock error) at ~7:37 AM —
and then did it again the next day, and the next. **Six consecutive mornings**, same error, same time
window:

```
2025-11-25 07:36:55   query_sync_operation_failed
2025-11-26 07:37:56   query_sync_operation_failed
2025-12-01 07:27:03   query_sync_operation_failed
2025-12-02 07:29:07   query_sync_operation_failed
2025-12-03 07:31:19   query_sync_operation_failed
2025-12-04 07:39:33   query_sync_operation_failed   ← the session that cracked it
```

Because each batch session is handed **30 days of prior error queues**, the agent didn't treat this as a
one-off — it saw the streak and went looking for a *structural* cause.

### The diagnosis

It found a genuine **TOCTOU (time-of-check-to-time-of-use) race condition**. The old code opened the
query DB to verify it was unlocked, *closed the handle*, then attempted the atomic rename — and in the
millisecond gap, Morning Views (which runs right after sync) would grab the lock. The retry logic never
helped because it only kicked in *after* the rename already failed, by which point an analysis tool was
holding the file for longer than the timeout.

> *"Even with 'just checked' validations, race windows exist… millisecond-scale race windows are
> exploitable in production."*

### The fix

It restructured the operation to **hold the exclusive lock from check through rename** — eliminating the
race window — and shipped a full report with before/after code, a measured impact assessment
(**100% failure rate over 6 days → expected 99%+**), backward-compatibility notes, and a rollback plan.

**Why it's showcase-worthy:** pattern detection across days, a textbook concurrency diagnosis most humans
would misfile as "just a flaky lock, add a retry," and a finished engineering artifact at the end of it.

---

## Case study #2 — the time Autofix failed for 8 days, and then fixed *itself*

This is the incident I'm most proud of, and it's a story about the system **not** working. Full
writeup: [`logs/NEWS_COLLECTOR_AUTOFIX_GAP_FIXED.md`](logs/NEWS_COLLECTOR_AUTOFIX_GAP_FIXED.md).

### What happened

From **Dec 10–18, 2025**, news collection failed *every single day* with `No module named 'nc_main'` —
a relative-import bug that only manifested when the module was loaded as a package (i.e., in production).
News collection silently produced zero articles for eight days.

**Autofix never caught it.** And the reason is the uncomfortable, honest one: the exception handler
logged the failure but **never called `queue_error()`**. The error never reached the queue, so batch mode
had nothing to process, so no session ever spawned. Ben found it by hand.

```python
except Exception as e:
    logging.error("Collection failed: {}".format(e), exc_info=True)
    print_error("FATAL ERROR: {}".format(e))
    return False   # ← error logged, but never queued. Autofix's blind spot.
```

### The fix that mattered

The import bug was trivial. The *real* fix was the **meta-fix**: the agent plugged the blind spot in the
self-healing system itself, wired `queue_error()` into the catch-all handlers, and established a standing
rule —

> *"Every `except Exception as e:` block in strategy code MUST call `queue_error()`… Monitor the
> monitors: autofix gaps are invisible until you look for them."*

### Why this is the most important entry

A showcase that only shows clean wins is marketing. A **self-healing system that documents, in its own
logs, the eight days it failed to heal — and then closes the gap that blinded it** — is the honest shape
of agentic automation. It's also just good engineering: the lesson generalized into a coverage rule, not
a one-off patch. (Which directly motivated case study #3.)

---

## Gallery — the system's range, in one line each

| Date | Incident | What stands out |
|------|----------|-----------------|
| **2026-04-07** | A disk-corruption storm fired **692 `op_database_operation_failed` events in ~12 seconds**. The agent made the handler *fail fast* — collapsing 692 duplicates into **one** queued error — **and wrote a brand-new recovery tool** (`repair_option_contracts.py`) with rowid-scan, sub-batch micro-recovery down to 500-row chunks. It also matched the cause to a *prior March incident* (HDD + antivirus during heavy writes). | **Builds new tooling, not just edits.** Deduplication + cross-month pattern memory. |
| **2025-12-18** | Right after the News Collector blind spot (case study #2), a session **proactively audited a *different* strategy** (Earnings Intel) for the same missing-`queue_error()` gap class — and reported it was clean because of its centralized-orchestrator design. | **Generalizes a lesson** across the codebase instead of patching in place. |
| **2026-06-04** | A wrong API token (drive-recovery fallout) 401'd and cascaded into **three distinct errors** — including an `UnboundLocalError` where the error handler *itself* crashed on an unbound `trade_date`, masking the real failure. Three batch sessions coordinated; session 3 found and closed the **symmetric twin bug** in the evening pipeline. | **Multi-session coordination** + honest self-correction (it first mislabeled the 401 "transient," then corrected the record). |
| **2025-11-25** | A correct source fix kept *recurring* because Python was serving **stale `.pyc` bytecode** from before the change. The agent progressed from "restart will fix it" to identifying the bytecode cache as the true cause and clearing it. | **Root-cause depth** — distinguishing source from runtime state. |
| **2025-11-21** | A missing `v_morning_discovery` view cascaded into News Collector **burning all 125 API calls** retrying with no valid symbols. The fix added tier-symbol caching *and* an early-exit circuit breaker. | **Cascade tracing** across two subsystems + cost-aware defense. |

---

## Architecture

Two modes, routed by severity:

```
Production error
      │
      ▼
queue_error() / handle_error()   ──►  errors/errors_YYYY-MM-DD.json   (source of truth)
      │
      ├─ CRITICAL  ──►  Immediate Mode   spawn Claude now → fix → kill → restart → monitor → email
      │                 (rate-limited, escalates after 3 attempts/day)
      │
      └─ ERROR     ──►  Batch Mode        queue all day → ~7:30 PM: dedupe by type →
                        (non-blocking)    one session per unique error → fix → email
```

The full lifecycle — including the manual-vs-production execution modes, the critical-operation guard
that refuses to kill `main.py` mid-backup, and the batch-reviews-immediate QA loop — is in the
[**Mermaid workflow diagram →**](AUTOFIX_WORKFLOW.md).

### What the spawned agent actually receives

The agent isn't dropped in blind. Each session gets:

- The specific error + its full context dict and traceback
- A **fix protocol** ([`instructions/AUTO_FIX_INSTRUCTIONS.md`](instructions/)) and decision heuristics
  for *fix vs. investigate-further vs. escalate*
- A curated **knowledge base** ([`reference/`](reference/)) — system architecture, DB schema, per-strategy
  guides — so it reasons about *this* system, not a generic Python project
- **30 days of historical error queues**, so it can recognize "this is the sixth morning in a row" as a
  pattern rather than a fluke (exactly what cracked case study #1)

---

## Safety rails (the actual hard part)

An agent that edits production code autonomously is only acceptable if it *cannot* run away. The harness enforces:

| Rail | Behavior |
|------|----------|
| **Rate limit** | Max 5 immediate spawns/hour, system-wide |
| **Escalation cap** | Max 3 attempts per error-type per day, then it emails a human and stops |
| **Code backups** | Every edit is preceded by a `*.autofix_backup_*` snapshot |
| **Critical-op guard** | Never kills `main.py` during archive/backup operations |
| **Deduplication** | 692 identical errors collapse to 1 fix session (real number, April 7) |
| **Transient filtering** | Known self-healing errors (DB lock contention, memory pressure) are skipped unless they recur 3+ times — *then* it's a pattern worth fixing |
| **Manual-mode detection** | If `main.py` wasn't running (developer ran a script by hand), it fixes the code but **never** restarts anything or sends noise |

---

## How it's wired into the codebase

Adding autofix coverage to any part of the system is two lines:

```python
from tools.autofix import queue_error

queue_error(
    error_type='fm_baseline_update_error',
    context={'error': str(e), 'phase': 'friday_baseline'},
    severity='ERROR',          # → batched for end-of-day review
)
```

```python
from tools.autofix import handle_error
import os

handle_error(
    error_type='database_table_missing',
    context={'error': str(e), 'traceback': traceback.format_exc()},
    severity='CRITICAL',
    main_py_pid=os.getppid(),   # → immediate spawn; this process exits here
)
```

The core API (`queue_error`, `handle_error`, `mark_error_fixed`, `check_and_spawn_batch_mode`) lives in
`tools/autofix.py` (~765 lines). The spawners and coordination logic are ~1,000 lines across
`main_fix_launcher.py`, `batch_mode_spawner.py`, and `batch_mode_tracker.py`.

---

## What I'd want a reader to take away

- The interesting engineering in an agentic system is **the harness, not the model call** — context
  curation, severity routing, rate limiting, escalation, backups, deduplication, and auditability.
- **Honest failure modes beat polished demos.** The eight-day blind spot in case study #2 is the most
  valuable thing in this whole document.
- A well-scoped agent fed the right context does genuinely impressive work — diagnosing a six-day race
  condition, building its own recovery tooling, and generalizing a lesson across an entire codebase.

---

## Further reading

- [`AUTOFIX_WORKFLOW.md`](AUTOFIX_WORKFLOW.md) — full Mermaid lifecycle diagram
- [`README.md`](README.md) — operational reference (integration API, modes, file layout)
- [`logs/batch_fix_report_2025-12-04_01.md`](logs/batch_fix_report_2025-12-04_01.md) — the TOCTOU race report (case study #1)
- [`logs/NEWS_COLLECTOR_AUTOFIX_GAP_FIXED.md`](logs/NEWS_COLLECTOR_AUTOFIX_GAP_FIXED.md) — the blind-spot writeup (case study #2)
- [`reference/AUTOFIX_CHEAT_SHEET.md`](reference/AUTOFIX_CHEAT_SHEET.md) — comprehensive technical reference
- [`AUTOFIX_INTEGRATION_AUDIT.md`](AUTOFIX_INTEGRATION_AUDIT.md) — which scripts have coverage
