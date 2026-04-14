#!/usr/bin/env python3
"""
Market Context Manager for Morning View TUI

Fetches and caches AI-powered market intelligence from previous trading day.
Uses ai_market_analyzer.py for 4-round Claude API analysis.

Cache structure: cache/market_context_{YYYY-MM-DD}.json
Displays: Brief synthesis (3-4 lines) showing market environment, momentum, and regime.

Author: Ben
Date: 2025-10-14
"""

import os
import sys

# Configure UTF-8 output for Windows (handles checkmarks and emojis)
sys.stdout.reconfigure(encoding='utf-8')

import json
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.timezone_utils import now_eastern


def get_cache_path(trade_date: str) -> Path:
    """Get cache file path for specific date.

    Args:
        trade_date: Trade date in YYYY-MM-DD format

    Returns:
        Path to cache file
    """
    cache_dir = Path(__file__).parent.parent / 'cache'
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / f'market_context_{trade_date}.json'


def get_previous_trading_day(db_path: str) -> Optional[str]:
    """Get most recent trading day from market_daily_summary.

    Args:
        db_path: Path to database

    Returns:
        Trade date string (YYYY-MM-DD) or None if not found
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("""
            SELECT MAX(trade_date)
            FROM market_daily_summary
            WHERE regime_classification IS NOT NULL
        """)
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            return row[0]
        return None

    except Exception as e:
        print(f"ERROR: Failed to get previous trading day: {e}")
        return None


def load_cached_context(trade_date: str) -> Optional[Dict]:
    """Load cached market context for date.

    Args:
        trade_date: Trade date in YYYY-MM-DD format

    Returns:
        Cached context dict or None if not found/invalid
    """
    cache_path = get_cache_path(trade_date)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate structure
        if not isinstance(data, dict) or 'trade_date' not in data:
            return None

        return data

    except Exception as e:
        print(f"WARNING: Failed to load cached context: {e}")
        return None


def run_market_analyzer(trade_date: str, db_path: str) -> Optional[Dict]:
    """Run ai_market_analyzer.py to generate fresh analysis.

    Args:
        trade_date: Trade date to analyze (YYYY-MM-DD)
        db_path: Database path

    Returns:
        Analysis result dict or None if failed
    """
    print(f"INFO: Running market analyzer for {trade_date}...")
    print(f"DEBUG: Database path: {db_path}")

    # Get path to ai_market_analyzer.py (now in morning_view directory)
    analyzer_path = Path(__file__).parent / 'ai_market_analyzer.py'
    print(f"DEBUG: Analyzer path: {analyzer_path}")

    if not analyzer_path.exists():
        print(f"ERROR: ai_market_analyzer.py not found at {analyzer_path}")
        return None

    # Create temp output path
    temp_output = Path(__file__).parent.parent / 'cache' / f'temp_analysis_{trade_date}.json'
    print(f"DEBUG: Temp output path: {temp_output}")

    try:
        # Run analyzer with subprocess
        # Use --use-cache to automatically use cached results without prompting
        cmd = [sys.executable, str(analyzer_path),
               '--date', trade_date,
               '--db', db_path,
               '--output', str(temp_output),
               '--use-cache']  # Auto-use analyzer's own cache (logs dir)
        print(f"DEBUG: Running command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=120  # 2 minute timeout
        )

        print(f"DEBUG: Return code: {result.returncode}")
        if result.stdout:
            print(f"DEBUG: STDOUT preview: {result.stdout[:500]}")
        if result.stderr:
            print(f"DEBUG: STDERR preview: {result.stderr[:500]}")

        if result.returncode != 0:
            print(f"ERROR: Market analyzer failed with return code {result.returncode}")
            print(f"STDERR: {result.stderr}")
            return None

        # Load the output
        if not temp_output.exists():
            print("ERROR: Market analyzer did not create output file")
            print(f"ERROR: Full STDOUT: {result.stdout}")
            return None

        with open(temp_output, 'r', encoding='utf-8') as f:
            analysis_data = json.load(f)

        print(f"DEBUG: Loaded analysis data with keys: {list(analysis_data.keys())}")

        # Clean up temp file
        temp_output.unlink()

        cost = analysis_data.get('total_cost_estimate', 0)
        tokens = analysis_data.get('total_tokens_used', 0)
        print(f"INFO: Market analyzer completed (${cost:.4f}, {tokens} tokens)")
        return analysis_data

    except subprocess.TimeoutExpired:
        print("ERROR: Market analyzer timed out after 2 minutes")
        return None
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse analyzer output as JSON: {e}")
        if temp_output.exists():
            with open(temp_output, 'r', encoding='utf-8') as f:
                print(f"ERROR: Raw output file contents: {f.read()[:1000]}")
        return None
    except Exception as e:
        print(f"ERROR: Failed to run market analyzer: {e}")
        import traceback
        traceback.print_exc()
        return None


def cache_market_context(trade_date: str, analysis_data: Dict) -> None:
    """Save market context to cache file.

    Args:
        trade_date: Trade date in YYYY-MM-DD format
        analysis_data: Analysis result from ai_market_analyzer
    """
    cache_path = get_cache_path(trade_date)

    # Add cache metadata
    cache_data = {
        'trade_date': trade_date,
        'cached_at': datetime.now().isoformat(),
        'analysis': analysis_data
    }

    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
        print(f"INFO: Cached market context to {cache_path}")

    except Exception as e:
        print(f"ERROR: Failed to cache market context: {e}")


def format_brief_summary(analysis_data: Dict, trade_date: str) -> str:
    """Format analysis data into brief 3-4 line summary for TUI display.

    Args:
        analysis_data: Analysis result from ai_market_analyzer
        trade_date: Trade date being displayed

    Returns:
        Formatted text string for display
    """
    print(f"DEBUG: Formatting analysis data for {trade_date}")
    print(f"DEBUG: Analysis data keys: {list(analysis_data.keys())}")

    # Extract key fields and handle both string and nested dict responses
    market_env_raw = analysis_data.get('market_environment_summary', {})
    momentum_raw = analysis_data.get('momentum_and_trends', {})
    implications_raw = analysis_data.get('trading_implications', '')
    confidence_raw = analysis_data.get('confidence_assessment', 'medium')

    print(f"DEBUG: market_env_raw type: {type(market_env_raw)}")
    print(f"DEBUG: momentum_raw type: {type(momentum_raw)}")

    # Parse market environment (might be dict or string)
    if isinstance(market_env_raw, dict):
        # Extract from nested JSON
        classification = market_env_raw.get('classification', 'UNKNOWN')
        strength = market_env_raw.get('strength_rating', 'N/A')
        breadth = market_env_raw.get('breadth_quality', 'N/A')
        market_env = f"{classification} (Strength: {strength}, Breadth: {breadth})"
    else:
        market_env = str(market_env_raw)

    # Parse momentum (might be dict or string)
    if isinstance(momentum_raw, dict):
        sustainability = momentum_raw.get('sustainability_rating', 'N/A')
        timeframe = momentum_raw.get('timeframe', 'N/A')
        conviction = momentum_raw.get('conviction_level', 'N/A')
        momentum = f"Sustainability: {sustainability} ({timeframe}), Conviction: {conviction}"
    else:
        momentum = str(momentum_raw)

    # Parse confidence (might be dict or string)
    if isinstance(confidence_raw, dict):
        overall = confidence_raw.get('overall_rating', 'medium')
        basis = confidence_raw.get('numerical_basis', 'N/A')
        confidence_str = f"{overall} ({basis})"
    else:
        confidence_str = str(confidence_raw)

    # Truncate if too long (max ~60 chars per line for right panel)
    if len(market_env) > 200:
        market_env = market_env[:197] + '...'
    if len(momentum) > 200:
        momentum = momentum[:197] + '...'

    # Color confidence based on overall rating
    if 'high' in confidence_str.lower():
        confidence_colored = f"[bold green]{confidence_str}[/bold green]"
    elif 'low' in confidence_str.lower():
        confidence_colored = f"[dim]{confidence_str}[/dim]"
    else:
        confidence_colored = f"[yellow]{confidence_str}[/yellow]"

    # Extract cost info
    cost = analysis_data.get('total_cost_estimate', 0)
    tokens = analysis_data.get('total_tokens_used', 0)

    # Build summary
    summary = f"""[bold cyan]Market Context: {trade_date}[/bold cyan]

[bold]Environment:[/bold]
{market_env}

[bold]Momentum:[/bold]
{momentum}

[bold]Confidence:[/bold]
{confidence_colored}

[dim]Cost: ${cost:.4f} | {tokens} tokens[/dim]
"""

    print(f"DEBUG: Generated summary length: {len(summary)} chars")
    return summary.strip()


def get_market_context(db_path: str, force_refresh: bool = False) -> str:
    """Get market context summary for display in TUI.

    Fetches previous trading day's analysis from cache or runs fresh analysis.

    Args:
        db_path: Path to database
        force_refresh: Force fresh analysis even if cache exists

    Returns:
        Formatted text string for display
    """
    print(f"DEBUG: get_market_context called (force_refresh={force_refresh})")
    print(f"DEBUG: Database path: {db_path}")

    # Get previous trading day
    prev_day = get_previous_trading_day(db_path)
    print(f"DEBUG: Previous trading day: {prev_day}")

    if not prev_day:
        print("WARNING: No previous trading day found in database")
        return "[dim]Market context unavailable\n(No trading data found)[/dim]"

    # Try to load from cache (unless force refresh)
    analysis_data = None
    if not force_refresh:
        cached = load_cached_context(prev_day)
        if cached:
            analysis_data = cached.get('analysis')
            print(f"INFO: Using cached market context for {prev_day}")
        else:
            print(f"DEBUG: No cache found for {prev_day}")

    # If no cache, run analyzer
    if not analysis_data:
        print(f"INFO: Running fresh market analysis for {prev_day}")
        analysis_data = run_market_analyzer(prev_day, db_path)

        if not analysis_data:
            print(f"ERROR: Market analysis failed for {prev_day}")
            return f"[dim]Market context unavailable\n(Analysis failed for {prev_day})[/dim]"

        # Cache the result
        cache_market_context(prev_day, analysis_data)

    # Format for display
    print("DEBUG: Formatting analysis for display...")
    try:
        formatted = format_brief_summary(analysis_data, prev_day)
        print(f"DEBUG: Successfully formatted analysis ({len(formatted)} chars)")
        return formatted
    except Exception as e:
        print(f"ERROR: Failed to format analysis: {e}")
        import traceback
        traceback.print_exc()
        return f"[dim]Market context formatting error\n({str(e)})[/dim]"


def main():
    """CLI entry point for testing market context manager."""
    import argparse

    parser = argparse.ArgumentParser(description="Test market context manager")
    parser.add_argument('--db', default='data/datalake_query.db', help='Database path')
    parser.add_argument('--refresh', action='store_true', help='Force refresh (ignore cache)')

    args = parser.parse_args()

    # Get and display context
    context = get_market_context(args.db, force_refresh=args.refresh)
    print("\n" + "="*60)
    print(context)
    print("="*60)


if __name__ == '__main__':
    main()
