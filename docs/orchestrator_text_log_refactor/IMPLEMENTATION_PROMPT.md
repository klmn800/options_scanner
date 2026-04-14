# Text Log Sanitization — Implementation Prompt

Give this to a fresh Claude Code session.

---

## Prompt

I need you to fix our orchestrator text log output. Before asking me any questions, read these files to understand the context:

**Design docs (read in this order):**
1. `docs/orchestrator_text_log_refactor/KICKOFF.md` — the original design. 3 changes were planned. Changes 1 & 2 are done. Change 3 (subprocess forwarding) is not. Critically, the doc assumes `beautiful_log()` "already writes clean text, no emoji" to the file — this assumption turned out to be wrong.
2. `docs/orchestrator_text_log_refactor/TEXT_LOG_AUDIT_PUNCHLIST_2026-03-12.md` — audit comparing actual logs against the standard. Documents 9 problems (P1-P9) with evidence, line counts, and root causes.

**Code to read:**
3. `tools/log_utils.py` — the logging toolkit. Focus on `_write_to_file_handler()` (line 40), `beautiful_log()` (line 143, especially line 187 where it writes to file), and the `_LEADING_EMOJIS` set (line 90).
4. `strategies/flow_monitor/fm_main.py` — search for the duplicate log lines at the `beautiful_log()` calls near lines 1132 and 1155. Each has a `logging.info()` call producing the same message, causing duplicates in the log file.
5. `main_runners.py` — search for `_run_streaming_subprocess` and `run_metadata_collection` and `run_morning_views` to understand the subprocess forwarding gap (KICKOFF Change 3).

**Sample log to reference:**
6. `logs/orchestrator_2026-03-12.log` (or most recent) — look at actual output to verify your changes.

**After reading, here's what needs to happen:**

### Fix 1: Emoji stripping in `_write_to_file_handler()` (P1)
Add a helper function that strips Unicode emoji characters from the message before writing to the file handler. This should cover all emoji — not just the `_LEADING_EMOJIS` set, but any Unicode emoji codepoint. Apply it inside `_write_to_file_handler()` so all paths through it get cleaned. The goal: log file lines should be plain ASCII-safe text. The 364 emoji instances per day in the log file should become 0.

### Fix 2: Skip blank messages in `_write_to_file_handler()` (P5)
Add a guard: if `message.strip() == ""`, return without writing. This eliminates the 23 blank log lines per day.

### Fix 3: Remove duplicate `logging.info()` calls in `fm_main.py` (P2)
Find the places where `beautiful_log(msg)` is immediately followed by `logging.info(msg)` with the same content. Remove the `logging.info()` calls — `beautiful_log()` already writes to the file handler, so the `logging.info()` creates a duplicate line. There are at least 2 confirmed cases (alert resolution ~line 1132, watchlist sentiment ~line 1155). Search for others.

### Fix 4: Subprocess timestamp stripping (P3) — KICKOFF Change 3
In `main_runners.py`, the metadata collection subprocess output arrives with its own `HH:MM:SS - ` timestamp prefix. When forwarded via `logging.info()`, this creates double timestamps like `2026-03-11 07:01:22 - INFO - 07:01:22 - Configuration loaded`. Strip the subprocess timestamp prefix before logging. Regex pattern: `r'^\d{2}:\d{2}:\d{2}\s*-\s*'`

### Fix 5: Filter decorative subprocess banners (P4)
Lines of pure `===` or `---` separators (20+ chars) from subprocess output should be filtered out before reaching the log file. These are console decoration from the metadata collector and morning views scripts.

### NOT in scope (don't do these):
- P6 (coffee break noise), P7 (wait message repeats), P8 (morning views dump) — these are noise reduction tasks for a separate session.
- P9 (missing logging.info coverage) — deferred, not needed since we're keeping `beautiful_log()`'s file handler path.
- Do NOT remove `_write_to_file_handler(message, log_level)` from `beautiful_log()` line 187. That line stays. We're fixing what it writes, not removing it.
- Do NOT change console output. Console stays exactly as-is.

### After reading everything, ask me any clarifying questions before you start implementing.
