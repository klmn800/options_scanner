"""
Interactive UI Helpers for Symbol Lifecycle (ui.py)
----------------------------------------------------
Display formatting and prompt helpers for the lifecycle CLI.

PRD 0013 — Symbol Lifecycle Management
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def display_symbol_card(symbol, data):
    """Display a formatted symbol information card.

    Args:
        symbol: Stock ticker
        data: Dict with keys: company_name, sector, industry, market_cap,
              avg_volume, last_price, expirations (list), last_earnings
    """
    name = data.get('company_name', 'Unknown')
    sector = data.get('sector', 'N/A')
    industry = data.get('industry', 'N/A')
    market_cap = data.get('market_cap', 0)
    avg_volume = data.get('avg_volume', 0)
    last_price = data.get('last_price', 0)
    expirations = data.get('expirations') or []
    last_earnings = data.get('last_earnings', 'N/A')

    # Format market cap
    if market_cap and market_cap >= 1_000_000_000:
        cap_str = f'${market_cap / 1_000_000_000:.1f}B'
    elif market_cap and market_cap >= 1_000_000:
        cap_str = f'${market_cap / 1_000_000:.0f}M'
    else:
        cap_str = 'N/A'

    # Format volume
    if avg_volume and avg_volume >= 1_000_000:
        vol_str = f'{avg_volume / 1_000_000:.1f}M'
    elif avg_volume and avg_volume >= 1_000:
        vol_str = f'{avg_volume / 1_000:.0f}K'
    else:
        vol_str = str(avg_volume) if avg_volume else 'N/A'

    opt_str = f'YES ({len(expirations)} expirations)' if expirations else 'NO'

    vol_source = data.get('avg_volume_source')
    vol_label = "today's volume" if vol_source == 'today' else '20d avg'
    next_earnings = data.get('next_earnings')

    header = f'{symbol} — {name}'
    print(f'\n{"=" * 3} {header} {"=" * 3}')
    print(f'  Sector:         {sector}')
    print(f'  Industry:       {industry}')
    print(f'  Market Cap:     {cap_str}')
    print(f'  Avg Volume:     {vol_str} ({vol_label})')
    print(f'  Last Price:     ${last_price:.2f}' if last_price else '  Last Price:     N/A')
    print(f'  Optionable:     {opt_str}')
    print(f'  Last Earnings:  {last_earnings}')
    if next_earnings:
        print(f'  Next Earnings:  {next_earnings}')


def display_preflight_results(results):
    """Display pre-flight check results.

    Args:
        results: list[PreflightResult] namedtuples with check_name, passed, message
    """
    print('\nPre-flight checks:')
    for r in results:
        marker = '[OK]  ' if r.passed else '[WARN]'
        print(f'  {marker} {r.check_name}: {r.message}')


def display_progress_step(step_num, total, description, status='done'):
    """Display a single onboarding progress step.

    Args:
        step_num: Current step number (1-based)
        total: Total number of steps
        description: What this step does
        status: 'done', 'skip', 'fail', or detail string
    """
    padding = 50 - len(description)
    pad = ' ' * max(padding, 2)
    print(f'  [{step_num}/{total}] {description}{pad}{status}')


def prompt_yes_no(message, default='y'):
    """Prompt for a yes/no answer.

    Args:
        message: Question text
        default: Default answer ('y' or 'n')

    Returns:
        bool: True for yes, False for no
    """
    hint = '[Y/n]' if default == 'y' else '[y/N]'
    try:
        answer = input(f'\n{message} {hint}: ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled.')
        return False

    if not answer:
        return default == 'y'
    return answer in ('y', 'yes')


def prompt_choice(message, options):
    """Prompt user to select from numbered options.

    Args:
        message: Question text
        options: List of (value, label) tuples

    Returns:
        The selected value (first element of chosen tuple)
    """
    print(f'\n{message}')
    for i, (value, label) in enumerate(options, 1):
        print(f'  [{i}] {label}')

    while True:
        try:
            answer = input(f'Choice [1-{len(options)}]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nCancelled.')
            return None

        try:
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f'  Please enter a number 1-{len(options)}')


def prompt_text(message):
    """Prompt for free text input.

    Args:
        message: Prompt text

    Returns:
        str: User's input (stripped)
    """
    try:
        return input(f'\n{message}: ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ''


def prompt_archive_db(sector, industry):
    """Interactive archive database picker.

    Scans data/sector_archive/ for existing .db files, suggests a default
    based on sector/industry, and displays a numbered grid. User can pick
    a number or type a new name (which triggers creation prompt).

    Args:
        sector: Symbol's sector (e.g. 'Industrials')
        industry: Symbol's industry (e.g. 'Aerospace & Defense')

    Returns:
        str or None: Archive DB name (without .db), or None if cancelled
    """
    from tools.lifecycle.routing import determine_archive_db

    archive_dir = os.path.join(project_root, 'data', 'sector_archive')
    archives = sorted([f[:-3] for f in os.listdir(archive_dir) if f.endswith('.db')])

    if not archives:
        print('No archive databases found in data/sector_archive/')
        return prompt_text('Enter archive DB name (without .db)') or None

    # Get suggested default
    suggested = determine_archive_db(sector, industry)

    print(f'\nArchive routing for {sector} / {industry}:')
    print()

    # Display in 3-column grid
    cols = 3
    col_width = 24
    for row_start in range(0, len(archives), cols):
        parts = []
        for i in range(row_start, min(row_start + cols, len(archives))):
            num = f'[{i + 1:>2}]'
            name = archives[i]
            marker = ' *' if name == suggested else ''
            entry = f'{num} {name}{marker}'
            parts.append(f'{entry:<{col_width}}')
        print(f'  {"".join(parts)}')

    if suggested:
        print(f'\n  * = suggested default ({suggested})')

    while True:
        try:
            hint = f' (Enter={suggested})' if suggested else ''
            answer = input(f'\n  Choice [1-{len(archives)}] or new name{hint}: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nCancelled.')
            return None

        # Enter = accept default
        if not answer and suggested:
            return suggested

        # Number = pick from list
        try:
            idx = int(answer) - 1
            if 0 <= idx < len(archives):
                return archives[idx]
            print(f'  Please enter 1-{len(archives)} or a new name')
            continue
        except ValueError:
            pass

        # Text = new archive name
        name = answer.lower().replace(' ', '_').replace('.db', '')
        if not name:
            continue

        if name in archives:
            return name

        # New name — confirm creation
        if not prompt_yes_no(f'"{name}.db" doesn\'t exist. Create it?', default='n'):
            continue

        # Create the archive
        try:
            from data.health.create_sector_archive import create_sector_archive
            result = create_sector_archive(name, copy_reference=False, dry_run=False)
            if result == 0:
                print(f'  Created data/sector_archive/{name}.db')
                return name
            else:
                print(f'  Failed to create archive (exit code {result})')
        except Exception as e:
            print(f'  Failed to create archive: {e}')
        continue
