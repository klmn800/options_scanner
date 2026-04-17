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

    header = f'{symbol} — {name}'
    print(f'\n{"=" * 3} {header} {"=" * 3}')
    print(f'  Sector:         {sector}')
    print(f'  Industry:       {industry}')
    print(f'  Market Cap:     {cap_str}')
    print(f'  Avg Volume:     {vol_str} (20d)')
    print(f'  Last Price:     ${last_price:.2f}' if last_price else '  Last Price:     N/A')
    print(f'  Optionable:     {opt_str}')
    print(f'  Last Earnings:  {last_earnings}')


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
        print()
        return default == 'y'

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
            print()
            return options[0][0]  # Default to first option

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
