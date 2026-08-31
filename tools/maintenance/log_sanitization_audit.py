"""
Verify orchestrator log sanitization against the 5 P1-P5 criteria
(from `docs/_local/orchestrator_text_log_refactor/`).

Checks the most recent N orchestrator logs for:
  1. Emoji / non-ASCII lines
  2. Duplicate consecutive lines
  3. Double timestamps (e.g. "[2026-05-14 06:35:01] [2026-05-14 06:35:01]")
  4. Banner lines (=== / --- / ### borders without content)
  5. Blank lines

Usage:
    python tools/maintenance/log_sanitization_audit.py
    python tools/maintenance/log_sanitization_audit.py --files 5
    python tools/maintenance/log_sanitization_audit.py --verbose
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


LOG_DIR = r'E:\options_scanner\logs'

# Pattern matches any character outside printable ASCII (0x20-0x7E) + tab/CR/LF.
NON_ASCII_RE = re.compile(r'[^\x09\x0a\x0d\x20-\x7e]')

# Matches two timestamps of the form [YYYY-MM-DD HH:MM:SS] or HH:MM:SS at line start
DOUBLE_TS_RE = re.compile(
    r'(\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]|\d{2}:\d{2}:\d{2})\s*'
    r'(\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]|\d{2}:\d{2}:\d{2})'
)

# Banner = a line that is all =, -, #, *, _ characters (border only, no content)
BANNER_RE = re.compile(r'^[=\-#*_\s]{20,}$')


def audit(filepath, verbose=False):
    with open(filepath, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8', errors='replace')
    lines = text.split('\n')

    emoji_lines = []
    blank_lines = 0
    double_ts_lines = []
    banner_lines = []
    duplicate_runs = []  # (line_num, line) for the 2nd+ occurrence in a run

    prev = None
    prev_count = 0
    for i, line in enumerate(lines, start=1):
        stripped = line.rstrip('\r')

        # Blank
        if stripped.strip() == '':
            blank_lines += 1
            prev = None
            prev_count = 0
            continue

        # Emoji / non-ASCII
        if NON_ASCII_RE.search(stripped):
            emoji_lines.append((i, stripped))

        # Double timestamp
        if DOUBLE_TS_RE.search(stripped):
            double_ts_lines.append((i, stripped))

        # Banner
        if BANNER_RE.match(stripped):
            banner_lines.append((i, stripped))

        # Duplicate consecutive
        if stripped == prev:
            prev_count += 1
            if prev_count >= 1:
                duplicate_runs.append((i, stripped))
        else:
            prev = stripped
            prev_count = 0

    total_lines = len(lines)
    results = {
        'file': os.path.basename(filepath),
        'total_lines': total_lines,
        'emoji': len(emoji_lines),
        'blank': blank_lines,
        'double_ts': len(double_ts_lines),
        'banner': len(banner_lines),
        'duplicates': len(duplicate_runs),
    }

    if verbose:
        if emoji_lines:
            # Count which non-ASCII chars appear, with frequency
            char_counter = Counter()
            for _, l in emoji_lines:
                for ch in l:
                    if NON_ASCII_RE.match(ch):
                        char_counter[ch] += 1
            print("\n  --- Non-ASCII char frequency ---")
            for ch, count in char_counter.most_common(15):
                name = 'U+{:04X}'.format(ord(ch))
                try:
                    display = ch
                except Exception:
                    display = '?'
                print("    {:>6}x  {}  ({})".format(count, display, name))
            print("\n  --- Emoji/non-ASCII line samples (first 5) ---")
            for n, l in emoji_lines[:5]:
                print("    L{}: {}".format(n, l[:160]))
        if double_ts_lines:
            print("\n  --- Double-timestamp samples (first 5) ---")
            for n, l in double_ts_lines[:5]:
                print("    L{}: {}".format(n, l[:140]))
        if banner_lines:
            print("\n  --- Banner samples (first 5) ---")
            for n, l in banner_lines[:5]:
                print("    L{}: {}".format(n, l[:140]))
        if duplicate_runs:
            print("\n  --- Duplicate samples (first 5) ---")
            for n, l in duplicate_runs[:5]:
                print("    L{}: {}".format(n, l[:140]))

    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--files', type=int, default=3, help='Number of recent logs to audit')
    p.add_argument('--verbose', action='store_true', help='Show sample offending lines')
    args = p.parse_args()

    pattern = os.path.join(LOG_DIR, 'orchestrator_*.log')
    files = sorted(glob.glob(pattern))
    if not files:
        print("No orchestrator logs found.")
        sys.exit(1)

    files = files[-args.files:]
    print("Auditing {} log(s):\n".format(len(files)))

    rows = []
    for f in files:
        print("--- {} ---".format(os.path.basename(f)))
        r = audit(f, verbose=args.verbose)
        rows.append(r)
        print("  Total lines: {:>7,}".format(r['total_lines']))
        print("  Emoji/non-ASCII: {}".format(r['emoji']))
        print("  Blank lines:     {}".format(r['blank']))
        print("  Double TS:       {}".format(r['double_ts']))
        print("  Banner lines:    {}".format(r['banner']))
        print("  Duplicates:      {}".format(r['duplicates']))
        print()

    # Summary across all
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in rows:
        flags = []
        if r['emoji']: flags.append("emoji")
        if r['blank']: flags.append("blank")
        if r['double_ts']: flags.append("double_ts")
        if r['banner']: flags.append("banner")
        if r['duplicates']: flags.append("dup")
        status = "CLEAN" if not flags else "DIRTY ({})".format(",".join(flags))
        print("  {}: {}".format(r['file'], status))


if __name__ == '__main__':
    main()
