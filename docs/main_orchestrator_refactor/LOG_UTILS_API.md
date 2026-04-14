# log_utils.py Public API Reference

> Quick-reference card for `tools/log_utils.py`. Each function writes to **both** console and log file, but with different formats: the console gets visual structure, the log file gets plain greppable text.

## Quick Reference

| Function | Console Output | Log File Output |
|---|---|---|
| `beautiful_log()` | Emoji + HH:MM:SS + message | Plain message (logging formatter adds timestamp) |
| `create_status_box()` | Full Unicode-bordered box | Title + indented content lines (no borders) |
| `phase_header()` | Full-width `═══` banner | Single `--- [PHASE N] TITLE ---` marker |
| `log_to_file()` | Nothing (file only) | Plain message |

## Import

```python
from tools.log_utils import beautiful_log, create_status_box, phase_header, log_to_file
```

---

## log_to_file

```python
def log_to_file(message: str, level: int = logging.INFO) -> None
```

Writes a message to the log file only, bypassing console. Use when output is already going to the console through another path (e.g., subprocess streaming via `sys.stdout.write()`).

**Output destination:** Log file only.

```python
log_to_file("Subprocess line forwarded to log")
log_to_file("Something went wrong", level=logging.WARNING)
```

---

## beautiful_log

```python
def beautiful_log(message: str, level: str = 'info') -> None
```

Writes a single formatted log line. Console gets `emoji HH:MM:SS - message`; log file gets the raw message through the standard logging formatter. Auto-detects if `message` already starts with an emoji and skips prepending a duplicate.

**`level` values:** `'info'` (default), `'success'`, `'error'`, `'warning'`, `'phase'`

**Output destination:** Console + log file.

```python
beautiful_log("Processing 800 symbols", level='info')
# Console: ℹ️ 09:15:32 - Processing 800 symbols
# Log file: 2026-02-19 09:15:32 - INFO - Processing 800 symbols

beautiful_log("Pipeline complete", level='success')
# Console: ✅ 09:18:44 - Pipeline complete
# Log file: 2026-02-19 09:18:44 - INFO - Pipeline complete

beautiful_log("✅ Already has emoji")
# Console: 09:18:44 - ✅ Already has emoji  (no double emoji)
# Log file: 2026-02-19 09:18:44 - INFO - ✅ Already has emoji
```

---

## create_status_box

```python
def create_status_box(title: str, content_lines: list[str], success: bool = True) -> None
```

Console: Unicode-bordered box. `success=True` uses double-line borders (`╔═╗`), `success=False` uses single-line borders (`┌─┐`). Box width auto-sizes to content (minimum 60 chars).

Log file: Title + indented content lines. No borders.

**Output destination:** Console (full box) + log file (plain content).

```python
create_status_box("MORNING PIPELINE COMPLETE", [
    "Symbols processed: 800",
    "Errors: 0",
    "Duration: 12m 34s",
])
# Console:
# ╔══════════════════════════════════════════════════════════╗
# ║ MORNING PIPELINE COMPLETE                               ║
# ╠══════════════════════════════════════════════════════════╣
# ║ Symbols processed: 800                                  ║
# ║ Errors: 0                                               ║
# ║ Duration: 12m 34s                                       ║
# ╚══════════════════════════════════════════════════════════╝
#
# Log file:
# 2026-02-19 07:16:33 - INFO - MORNING PIPELINE COMPLETE
# 2026-02-19 07:16:33 - INFO -   Symbols processed: 800
# 2026-02-19 07:16:33 - INFO -   Errors: 0
# 2026-02-19 07:16:33 - INFO -   Duration: 12m 34s
```

---

## phase_header

```python
def phase_header(title: str, phase_number: int | None = None) -> None
```

Console: Full-width centered banner between `═══` separators. If `phase_number` is provided, output reads `PHASE N: TITLE`.

Log file: Single compact marker line with `---` separators and `[PHASE N]` tag for greppability.

**Output destination:** Console (full banner) + log file (compact marker).

```python
phase_header("PRE-MARKET OPERATIONS", phase_number=1)
# Console:
# ════════════════════════════════════════════════════════════
#                  PHASE 1: PRE-MARKET OPERATIONS
# ════════════════════════════════════════════════════════════
#
# Log file:
# 2026-02-19 06:35:01 - INFO - --- [PHASE 1] PRE-MARKET OPERATIONS ---

phase_header("COFFEE BREAK")
# Console:
# ════════════════════════════════════════════════════════════
#                        COFFEE BREAK
# ════════════════════════════════════════════════════════════
#
# Log file:
# 2026-02-19 07:16:33 - INFO - --- COFFEE BREAK ---
```
