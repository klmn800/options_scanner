#!/usr/bin/env python3
"""
Graduate a staged reference file from Market Analyst to Trading Advisor.

Workflow (Proposal 027):
  1. MA drafts a file in agents/market_analyst/reference/staging/<file>.md
     with required YAML frontmatter (schema in staging/README.md).
  2. MA sets frontmatter `status: ready_for_review`, pings Ben in notes_for_ben.md.
  3. Ben reviews, then runs this tool to promote.

What this tool does:
  - Reads the staged file
  - Validates frontmatter exists and status is `ready_for_review` (override with --force)
  - Strips the frontmatter from the body
  - Writes the body to agents/trading_advisor/reference/<file>.md
  - Moves the original staged file to agents/market_analyst/reference/staging/promoted/<file>.md

Refuses to overwrite an existing file in TA's reference/ unless --overwrite is passed.
Refuses to re-graduate a file already in promoted/ unless --force is passed.

Usage:
  python tools/graduate_reference.py <filename>
  python tools/graduate_reference.py pattern_x.md --overwrite       # replace existing TA reference doc
  python tools/graduate_reference.py pattern_x.md --force            # skip status check
  python tools/graduate_reference.py pattern_x.md --dry-run          # preview without changes
  python tools/graduate_reference.py --list                          # list staged files awaiting review
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MA_STAGING = PROJECT_ROOT / 'agents' / 'market_analyst' / 'reference' / 'staging'
MA_PROMOTED = MA_STAGING / 'promoted'
TA_REFERENCE = PROJECT_ROOT / 'agents' / 'trading_advisor' / 'reference'

FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?\n)---\s*\n?', re.DOTALL)
STATUS_RE = re.compile(r'^status:\s*(.+?)\s*$', re.MULTILINE)


def parse_frontmatter(text):
    """Return (frontmatter_dict, body_without_frontmatter) or (None, text) if no frontmatter."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, text
    fm_text = match.group(1)
    fm = {}
    for line in fm_text.splitlines():
        if ':' in line:
            key, _, value = line.partition(':')
            fm[key.strip()] = value.strip()
    body = text[match.end():]
    return fm, body


def list_staged():
    """List all .md files in staging/ that are at top level (not in promoted/declined/)."""
    if not MA_STAGING.exists():
        print(f"Staging directory does not exist: {MA_STAGING}")
        return
    files = sorted([p for p in MA_STAGING.iterdir()
                    if p.is_file() and p.suffix == '.md' and p.name != 'README.md'])
    if not files:
        print("No staged files awaiting review.")
        return
    print(f"Staged files in {MA_STAGING}:")
    for f in files:
        try:
            text = f.read_text(encoding='utf-8')
            fm, _ = parse_frontmatter(text)
            status = fm.get('status', '?') if fm else '(no frontmatter)'
            title = fm.get('title', f.stem) if fm else f.stem
            print(f"  - {f.name:50s} status={status:20s} title={title}")
        except Exception as e:
            print(f"  - {f.name:50s} (error reading: {e})")


def graduate(filename, overwrite=False, force=False, dry_run=False):
    staged_path = MA_STAGING / filename
    promoted_path = MA_PROMOTED / filename
    target_path = TA_REFERENCE / filename

    if not staged_path.exists():
        # Check if it's already in promoted/
        if promoted_path.exists() and not force:
            print(f"ERROR: {filename} not in staging/ but found in promoted/.")
            print(f"       Already graduated. Use --force to re-graduate.")
            return 1
        print(f"ERROR: {filename} not found in {MA_STAGING}")
        return 1

    text = staged_path.read_text(encoding='utf-8')
    fm, body = parse_frontmatter(text)

    if fm is None:
        print(f"ERROR: {filename} has no YAML frontmatter.")
        print(f"       Schema required (see {MA_STAGING}/README.md). Use --force to override.")
        if not force:
            return 1
        body = text  # no frontmatter to strip

    if fm and not force:
        status = fm.get('status', '').lower()
        if status != 'ready_for_review':
            print(f"ERROR: {filename} status is '{status}', not 'ready_for_review'.")
            print(f"       MA must bump status before graduation. Use --force to override.")
            return 1

    if target_path.exists() and not overwrite:
        print(f"ERROR: {target_path} already exists in TA's reference/.")
        print(f"       Use --overwrite to replace, or rename the staged file.")
        return 1

    if dry_run:
        print(f"[DRY RUN] Would copy: {staged_path} -> {target_path}")
        print(f"[DRY RUN] Would move staged: {staged_path} -> {promoted_path}")
        if fm:
            print(f"[DRY RUN] Frontmatter stripped ({len(fm)} keys):")
            for k, v in fm.items():
                print(f"            {k}: {v}")
        return 0

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(body, encoding='utf-8')
    print(f"Graduated: {target_path}")

    MA_PROMOTED.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged_path), str(promoted_path))
    print(f"Archived:  {promoted_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Graduate MA staged reference files into TA reference library.'
    )
    parser.add_argument('filename', nargs='?',
                        help='Staged filename (e.g. pattern_x.md). Resolved against staging/.')
    parser.add_argument('--list', action='store_true',
                        help='List all staged files and their statuses')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing file in TA reference/')
    parser.add_argument('--force', action='store_true',
                        help='Skip status==ready_for_review check')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without making changes')

    args = parser.parse_args()

    if args.list:
        list_staged()
        return 0

    if not args.filename:
        parser.print_help()
        return 1

    return graduate(args.filename,
                    overwrite=args.overwrite,
                    force=args.force,
                    dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
