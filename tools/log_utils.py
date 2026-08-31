"""
Shared Logging Utilities (tools/log_utils.py)
=============================================
Standalone logging functions for the options scanner.

Provides:
- beautiful_log: Formatted console + clean log file output
- create_status_box: Visual boxes (console) / plain content (log file)
- phase_header: Banners (console) / compact markers (log file)

Each function produces two outputs: a formatted version for the console
(sys.stdout) and a clean version for the log file (via the root logger's
file handler). The console gets visual structure (boxes, emojis, banners).
The log file gets plain, greppable text.

Usage:
    from tools.log_utils import beautiful_log, create_status_box, phase_header

    beautiful_log("Processing complete", level='success')
    create_status_box("STEP COMPLETE", ["Line 1", "Line 2"])
    phase_header("PRE-MARKET OPERATIONS", phase_number=1)
"""

import re
import sys
import logging
import threading
import unicodedata

# Add project tools to path for timezone_utils
import os
_tools_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_tools_dir)
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from timezone_utils import now_eastern

# Serializes multi-line console/log emission so a status box or phase header
# printed from one thread can't be torn apart by lines from another (e.g. the
# Friday 5.1 weekly-backup thread racing the main flow into 5.2). RLock so a
# nested call from inside a held section can't deadlock. Uncontended cost is
# negligible in the single-threaded case.
_OUTPUT_LOCK = threading.RLock()


# --- Internal helpers ---

class _CleanFileFilter(logging.Filter):
    """Logging filter that strips emojis and suppresses blank lines.

    Installed on the root logger's FileHandler to sanitize ALL paths to the
    log file — both direct logging.info() calls and _write_to_file_handler().
    """
    def filter(self, record):
        if isinstance(record.msg, str):
            record.msg = _strip_emojis(record.msg)
            if not record.msg.strip():
                return False
        return True


_file_filter_installed = False


def _write_to_file_handler(message, level=logging.INFO):
    """Write directly to the root logger's file handler, skipping console.

    This avoids double console output when beautiful_log has already
    written a formatted version to sys.stdout.

    Applies two sanitization steps before writing:
    1. Skips blank/empty messages (no information value in log)
    2. Strips Unicode emoji characters (log file should be plain text)

    On first call, also installs _CleanFileFilter on the FileHandler so that
    direct logging.info() calls with emojis are also cleaned.
    """
    global _file_filter_installed

    if not message or not message.strip():
        return

    message = _strip_emojis(message)

    if not message.strip():
        return

    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            # Install emoji/blank filter for direct logging.info() calls too
            if not _file_filter_installed:
                handler.addFilter(_CleanFileFilter())
                _file_filter_installed = True
            record = root.makeRecord(root.name, level, '', 0, message, (), None)
            handler.emit(record)
            break


def _display_width(text):
    """Calculate terminal display width, accounting for wide (emoji) characters.

    Wide characters (East Asian Width 'W' or 'F') occupy 2 terminal columns
    but Python's len() counts them as 1. This returns the true column count.
    """
    extra = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            extra += 1
    return len(text) + extra


def _pad_to_width(text, width):
    """Left-align text to given display width, accounting for wide characters."""
    current = _display_width(text)
    padding = max(0, width - current)
    return text + ' ' * padding


def _safe_print(message=""):
    """Safe print that won't crash on closed stdout"""
    try:
        sys.stdout.write(message + "\n")
        sys.stdout.flush()
    except (ValueError, OSError, IOError, UnicodeEncodeError):
        try:
            # Fallback: strip non-ASCII and try again
            safe_msg = message.encode('ascii', errors='replace').decode('ascii')
            sys.stdout.write(safe_msg + "\n")
            sys.stdout.flush()
        except:
            pass


# Compiled pattern for stripping all Unicode emoji from log file output.
# Covers emoticons, symbols, pictographs, transport, dingbats, misc symbols,
# misc technical (timers), variation selectors, and zero-width joiners.
# The trailing \s? eats the space that typically follows a leading emoji.
_EMOJI_PATTERN = re.compile(
    '['
    '\U0000FE0F'            # variation selector-16
    '\U0000200D'            # zero-width joiner
    '\U00002139'            # ℹ
    '\U00002300-\U000023FF' # misc technical (⏰, ⏱)
    '\U00002600-\U000026FF' # misc symbols (☕, ⚠, ✈)
    '\U00002700-\U000027BF' # dingbats (✅, ❌)
    '\U00002B50'            # ⭐
    '\U0001F300-\U0001F9FF' # main emoji blocks
    '\U0001FA00-\U0001FAFF' # extended emoji
    r']+\s?',
    flags=re.UNICODE
)


def _strip_emojis(text):
    """Remove Unicode emoji characters from text for clean log file output.

    Strips all emoji codepoints and one trailing space after each emoji group,
    so '🎯 COMPLETE' becomes 'COMPLETE' (not ' COMPLETE').
    """
    return _EMOJI_PATTERN.sub('', text)


# Emoji set used for stutter detection
_LEADING_EMOJIS = {
    '\u2705',      # ✅
    '\u274c',      # ❌
    '\u26a0\ufe0f', # ⚠️
    '\u26a0',      # ⚠ (without variation selector)
    '\U0001f525',  # 🔥
    '\u2139\ufe0f', # ℹ️
    '\u2139',      # ℹ (without variation selector)
    '\U0001f680',  # 🚀
    '\U0001f4c8',  # 📈
    '\U0001f4ca',  # 📊
    '\U0001f3af',  # 🎯
    '\U0001f4be',  # 💾
    '\U0001f4e6',  # 📦
    '\u2615',      # ☕
    '\U0001f504',  # 🔄
    '\U0001f6a8',  # 🚨
    '\U0001f4a5',  # 💥
    '\U0001f6d1',  # 🛑
    '\u23f0',      # ⏰
    '\u23f1\ufe0f', # ⏱️
    '\u2b50',      # ⭐
    '\U0001f31f',  # 🌟
}


def _message_starts_with_emoji(message):
    """Check if message already starts with an emoji to avoid stutter."""
    if not message:
        return False
    # Check against known emoji set
    for emoji in _LEADING_EMOJIS:
        if message.startswith(emoji):
            return True
    return False


# --- Public API ---

def log_to_file(message, level=logging.INFO):
    """Write a message to the log file only, bypassing console.

    Use this when output is already going to the console through another
    path (e.g., subprocess streaming via sys.stdout.write) and you need
    it to also reach the log file without duplicating on console.

    Args:
        message: Text to log
        level: logging level (default: logging.INFO)
    """
    _write_to_file_handler(message, level)


def beautiful_log(message, level='info'):
    """Formatted logging to both console and log file.

    Console output: emoji + HH:MM:SS + message
    Log file output: standard format (timestamp - LEVEL - message)

    Handles the "stutter" bug: if the message already starts with an emoji
    (e.g. "✅ COMPLETED"), the level emoji is not prepended.

    Args:
        message: Text to log
        level: 'info', 'success', 'error', 'warning', 'phase'
    """
    timestamp = now_eastern().strftime("%H:%M:%S")

    emoji_map = {
        'success': '\u2705',      # ✅
        'error': '\u274c',        # ❌
        'warning': '\u26a0\ufe0f', # ⚠️
        'phase': '\U0001f525',    # 🔥
        'info': '\u2139\ufe0f',   # ℹ️
    }

    log_level_map = {
        'success': logging.INFO,
        'error': logging.ERROR,
        'warning': logging.WARNING,
        'phase': logging.INFO,
        'info': logging.INFO,
    }

    emoji = emoji_map.get(level, emoji_map['info'])
    log_level = log_level_map.get(level, logging.INFO)

    # Fix stutter: don't prepend emoji if message already starts with one
    if _message_starts_with_emoji(message):
        console_line = "{} - {}".format(timestamp, message)
    else:
        console_line = "{} {} - {}".format(emoji, timestamp, message)

    with _OUTPUT_LOCK:
        # Console (formatted with emoji + timestamp)
        _safe_print(console_line)

        # Log file (clean message — logging formatter adds its own timestamp)
        _write_to_file_handler(message, log_level)


def create_status_box(title, content_lines, success=True):
    """Visual status box for console, plain content lines for log file.

    Console: Full Unicode-bordered box (╔═╗ or ┌─┐).
    Log file: Title + indented content lines (no borders).

    Args:
        title: Box header text
        content_lines: List of strings for box body
        success: True for double-line borders, False for single-line
    """
    try:
        border_char = "\u2550" if success else "\u2500"  # ═ or ─
        corner_tl = "\u2554" if success else "\u250c"    # ╔ or ┌
        corner_tr = "\u2557" if success else "\u2510"    # ╗ or ┐
        corner_bl = "\u255a" if success else "\u2514"    # ╚ or └
        corner_br = "\u255d" if success else "\u2518"    # ╝ or ┘
        side_char = "\u2551" if success else "\u2502"    # ║ or │
        mid_left = "\u2560" if success else "\u251c"     # ╠ or ├
        mid_right = "\u2563" if success else "\u2524"    # ╣ or ┤

        # Calculate box width (using display width to account for wide emojis)
        all_lines = [title] + content_lines
        max_width = max(60, max(_display_width(line) for line in all_lines) + 4)
        inner_width = max_width - 4

        # Build console box lines
        box_lines = []
        box_lines.append("")
        box_lines.append("{}{}{}".format(corner_tl, border_char * (max_width - 2), corner_tr))
        box_lines.append("{} {} {}".format(side_char, _pad_to_width(title, inner_width), side_char))
        box_lines.append("{}{}{}".format(mid_left, border_char * (max_width - 2), mid_right))

        for line in content_lines:
            box_lines.append("{} {} {}".format(side_char, _pad_to_width(line, inner_width), side_char))

        box_lines.append("{}{}{}".format(corner_bl, border_char * (max_width - 2), corner_br))
        box_lines.append("")

        with _OUTPUT_LOCK:
            # Console: full box with borders
            for line in box_lines:
                _safe_print(line)

            # Log file: plain title + indented content (no borders)
            _write_to_file_handler(title.strip())
            for line in content_lines:
                if line.strip():
                    _write_to_file_handler("  {}".format(line.strip()))

    except (ValueError, OSError, IOError):
        # Stdout closed or redirected — silently continue
        pass


def phase_header(title, phase_number=None):
    """Visual phase transition banner for console, compact marker for log file.

    Console: Full-width centered banner between ═══ separators.
    Log file: Single marker line: --- [PHASE N] TITLE ---

    Args:
        title: Phase name (e.g., "PRE-MARKET OPERATIONS")
        phase_number: Optional phase number (e.g., 1)
    """
    if phase_number is not None:
        header_text = " PHASE {}: {} ".format(phase_number, title)
    else:
        header_text = " {} ".format(title)

    width = max(60, len(header_text) + 4)
    separator = "\u2550" * width  # ═
    padded = header_text.center(width)

    with _OUTPUT_LOCK:
        # Console: full banner with ═══ separators
        console_lines = ["", separator, padded, separator, ""]
        for line in console_lines:
            _safe_print(line)

        # Log file: single compact marker
        if phase_number is not None:
            _write_to_file_handler("--- [PHASE {}] {} ---".format(phase_number, title))
        else:
            _write_to_file_handler("--- {} ---".format(title.strip()))
