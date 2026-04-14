#!/usr/bin/env python3
"""
AI Symbol Analyzer for Morning Views TUI

Provides on-demand AI analysis of symbols using Claude API.
Analysis is cached for 7 days to avoid redundant API calls.

Architecture:
- Data gathering: Reuses tui_data.py methods (no new queries)
- AI layer: Claude API with simple prompt engineering
- Cache: Stored in datalake.db (survives sync to datalake_query.db)
- Models: Haiku (testing), Sonnet (production), Opus (advanced)

Usage:
    from ai_analyzer import analyze_symbol

    # Basic analysis
    analysis = analyze_symbol('AAPL')

    # Force refresh
    analysis = analyze_symbol('AAPL', force_refresh=True)

    # Use different model
    analysis = analyze_symbol('AAPL', model='opus')

Author: Ben
Date: 2025-10-08
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import morning view data layer
from morning_view.tui_data import get_data

# Import prompts
from morning_view import ai_prompts

# Import Anthropic SDK
try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed")
    print("Install with: pip install anthropic")
    sys.exit(1)

# ========== Configuration ==========

# Model definitions (check anthropic.com/docs for latest)
MODELS = {
    'haiku': 'claude-3-5-haiku-20241022',      # Fast, cheap - testing
    'sonnet': 'claude-3-5-sonnet-20241022',    # High quality - production
    'opus': 'claude-3-opus-20240229',          # Most capable - advanced analysis
}

# Cache settings
CACHE_DAYS = 7
DB_PATH = "data/analysis_cache.db"  # Separate cache database (no lock conflicts)

# ========== Cache Management ==========

def _get_db_path():
    """Get absolute path to database

    Returns:
        str: Absolute path to datalake.db
    """
    # If relative path, make it relative to project root
    if not os.path.isabs(DB_PATH):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        return os.path.join(project_root, DB_PATH)
    return DB_PATH

def get_cached_analysis(symbol):
    """Check if recent analysis exists in cache

    Args:
        symbol: Stock symbol

    Returns:
        dict or None: Cached analysis record if found and fresh, else None
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol, analysis_text, model_used, created_at, previous_analysis
            FROM symbol_ai_analysis
            WHERE symbol = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (symbol,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Check if expired (> 7 days)
        created_at = datetime.fromisoformat(row['created_at'])
        age_days = (datetime.now() - created_at).days

        if age_days >= CACHE_DAYS:
            return None

        return {
            'symbol': row['symbol'],
            'analysis_text': row['analysis_text'],
            'model_used': row['model_used'],
            'created_at': row['created_at'],
            'previous_analysis': row['previous_analysis'],
            'age_days': age_days
        }

    except Exception as e:
        print(f"Warning: Cache check failed: {e}")
        return None

def cache_analysis(symbol, analysis_text, model_used, previous_analysis=None):
    """Store analysis in cache

    Args:
        symbol: Stock symbol
        analysis_text: Analysis markdown text
        model_used: Claude model identifier
        previous_analysis: Previous analysis text (optional)

    Returns:
        bool: True if cached successfully
    """
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        # Delete old analysis for this symbol
        cursor.execute("DELETE FROM symbol_ai_analysis WHERE symbol = ?", (symbol,))

        # Insert new analysis
        cursor.execute("""
            INSERT INTO symbol_ai_analysis (symbol, analysis_text, model_used, created_at, previous_analysis)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, analysis_text, model_used, now, previous_analysis))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"Warning: Cache write failed: {e}")
        return False

# ========== Data Gathering ==========

def gather_symbol_data(symbol):
    """Gather all available data for symbol using existing tui_data methods

    Args:
        symbol: Stock symbol

    Returns:
        dict: Compiled data ready for prompt building
    """
    data = get_data()

    # Get symbol overview
    overview = data.get_symbol_overview(symbol)
    if not overview:
        return None

    # Get OI timing
    oi_timing = data.get_oi_timing(symbol, limit=10)

    # Get OI distribution
    oi_dist = data.get_oi_distribution(symbol)

    # Get market context
    market_ctx = data.get_market_context()

    return {
        'overview': overview,
        'oi_timing': oi_timing,
        'oi_distribution': oi_dist,
        'market_context': market_ctx
    }

# ========== Prompt Building ==========

def build_prompt(symbol, data, cached_analysis=None):
    """Build analysis prompt from gathered data

    Args:
        symbol: Stock symbol
        data: Dict from gather_symbol_data()
        cached_analysis: Previous analysis record (optional)

    Returns:
        str: Formatted prompt ready for Claude
    """
    overview = data['overview']
    oi_timing = data['oi_timing']
    oi_dist = data['oi_distribution']
    market_ctx = data['market_context']

    # Build OI timing summary
    oi_timing_summary = ai_prompts.build_oi_timing_summary(oi_timing)

    # Build earnings context
    earnings_context = ai_prompts.build_earnings_context(overview)

    # Calculate call/put percentages
    total_call_oi = oi_dist.get('total_call_oi', 0) or 0
    total_put_oi = oi_dist.get('total_put_oi', 0) or 0
    total_oi = total_call_oi + total_put_oi

    if total_oi > 0:
        call_pct = (total_call_oi / total_oi) * 100
        put_pct = (total_put_oi / total_oi) * 100
    else:
        call_pct = 0
        put_pct = 0

    # Delta bias
    net_delta = (oi_dist.get('net_delta_exposure', 0) or 0) / 1_000_000
    delta_bias = "BULLISH" if net_delta > 0 else "BEARISH"

    # Max pain distance
    max_pain = oi_dist.get('max_pain_by_friday', 0) or 0
    close_price = overview.get('close_price', 0) or 0
    if max_pain and close_price:
        pain_distance = ((max_pain - close_price) / close_price) * 100
    else:
        pain_distance = 0

    # Previous analysis context
    previous_analysis_context = ""
    if cached_analysis:
        previous_analysis_context = ai_prompts.format_previous_analysis(
            cached_analysis['analysis_text'],
            cached_analysis['created_at']
        )

    # Build prompt from template
    prompt = ai_prompts.ANALYSIS_PROMPT_TEMPLATE.format(
        symbol=symbol,
        price=overview.get('close_price', 0) or 0,
        price_change_5d=overview.get('price_change_5d_pct', 0) or 0,
        sector=overview.get('sector', 'Unknown'),
        industry=overview.get('industry', 'Unknown'),
        confluence_score=overview.get('confluence_score', 0) or 0,
        direction_bias=overview.get('direction_bias', 'N/A'),
        conviction_level=overview.get('conviction_level', 'N/A'),
        primary_signal=overview.get('primary_signal', 'N/A'),
        active_alert_count=overview.get('active_alert_count', 0) or 0,
        earnings_context=earnings_context,
        market_direction=market_ctx.get('market_direction', 'Unknown'),
        market_regime=market_ctx.get('market_regime', 'Unknown'),
        oi_timing_summary=oi_timing_summary,
        total_oi=total_oi,
        put_call_ratio=oi_dist.get('put_call_ratio', 0) or 0,
        call_oi=total_call_oi,
        call_pct=call_pct,
        put_oi=total_put_oi,
        put_pct=put_pct,
        top_calls=oi_dist.get('top_call_display', 'N/A'),
        top_puts=oi_dist.get('top_put_display', 'N/A'),
        dte_0_7=oi_dist.get('oi_0_7_days_percent', 0) or 0,
        dte_8_21=oi_dist.get('oi_8_21_days_percent', 0) or 0,
        dte_22_35=oi_dist.get('oi_22_35_days_percent', 0) or 0,
        dte_36_60=oi_dist.get('oi_36_60_days_percent', 0) or 0,
        net_delta=net_delta,
        delta_bias=delta_bias,
        max_gamma_strike=oi_dist.get('max_gamma_strike', 0) or 0,
        max_pain=max_pain,
        pain_distance=pain_distance,
        previous_analysis_context=previous_analysis_context
    )

    return prompt

# ========== Claude API Integration ==========

def call_claude(prompt, model='haiku'):
    """Call Claude API with analysis prompt

    Args:
        prompt: Analysis prompt text
        model: Model identifier ('haiku', 'sonnet', 'opus')

    Returns:
        tuple: (analysis_text, usage_dict) where usage_dict contains:
            - input_tokens: Number of input tokens
            - output_tokens: Number of output tokens
            - cost_usd: Estimated cost in USD

    Raises:
        Exception: If API call fails
    """
    # Load API key from config
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config.json'
    )

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            api_key = config['claude_api']['api_key']
    except Exception as e:
        raise Exception(f"Failed to load Claude API key from config.json: {e}")

    # Get model ID
    model_id = MODELS.get(model)
    if not model_id:
        raise Exception(f"Unknown model: {model}. Available: {list(MODELS.keys())}")

    # Initialize client
    client = anthropic.Anthropic(api_key=api_key)

    # Pricing per million tokens (as of Oct 2024)
    PRICING = {
        'claude-3-5-haiku-20241022': {'input': 1.00, 'output': 5.00},     # $1/$5 per MTok
        'claude-3-5-sonnet-20241022': {'input': 3.00, 'output': 15.00},   # $3/$15 per MTok
        'claude-3-opus-20240229': {'input': 15.00, 'output': 75.00},      # $15/$75 per MTok
    }

    # Call API
    try:
        message = client.messages.create(
            model=model_id,
            max_tokens=4000,
            system=ai_prompts.SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract text from response
        analysis_text = message.content[0].text

        # Extract usage stats
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        # Calculate cost
        pricing = PRICING.get(model_id, {'input': 3.00, 'output': 15.00})  # Default to Sonnet pricing
        cost_usd = (
            (input_tokens / 1_000_000) * pricing['input'] +
            (output_tokens / 1_000_000) * pricing['output']
        )

        usage = {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cost_usd': cost_usd
        }

        return analysis_text, usage

    except Exception as e:
        raise Exception(f"Claude API call failed: {e}")

# ========== Main Analysis Function ==========

def analyze_symbol(symbol, model='haiku', force_refresh=False):
    """Analyze symbol using Claude AI

    Main entry point for TUI and testing. Handles cache checking,
    data gathering, prompt building, and API calls.

    Args:
        symbol: Stock symbol to analyze
        model: Claude model to use ('haiku', 'sonnet', 'opus')
        force_refresh: If True, bypass cache and force new analysis

    Returns:
        dict: Analysis result with keys:
            - symbol: Stock symbol
            - analysis_text: Markdown analysis from Claude
            - model_used: Claude model identifier
            - created_at: ISO timestamp
            - from_cache: Boolean indicating if result was cached
            - age_days: Age of cached result (0 if fresh)
            - input_tokens: Number of input tokens (0 if cached)
            - output_tokens: Number of output tokens (0 if cached)
            - cost_usd: Estimated cost in USD (0.0 if cached)

    Raises:
        Exception: If analysis fails
    """
    # Step 1: Check cache (unless forced refresh)
    if not force_refresh:
        cached = get_cached_analysis(symbol)
        if cached:
            cached['from_cache'] = True
            cached['input_tokens'] = 0
            cached['output_tokens'] = 0
            cached['cost_usd'] = 0.0
            return cached

    # Step 2: Gather data
    data = gather_symbol_data(symbol)
    if not data:
        raise Exception(f"No data found for symbol: {symbol}")

    # Step 3: Build prompt (include previous analysis if exists)
    cached_for_context = get_cached_analysis(symbol)
    prompt = build_prompt(symbol, data, cached_for_context)

    # Step 4: Call Claude
    analysis_text, usage = call_claude(prompt, model)

    # Step 5: Cache result
    previous_text = cached_for_context['analysis_text'] if cached_for_context else None
    cache_analysis(symbol, analysis_text, MODELS[model], previous_text)

    # Step 6: Return result
    return {
        'symbol': symbol,
        'analysis_text': analysis_text,
        'model_used': MODELS[model],
        'created_at': datetime.now().isoformat(),
        'from_cache': False,
        'age_days': 0,
        'input_tokens': usage['input_tokens'],
        'output_tokens': usage['output_tokens'],
        'cost_usd': usage['cost_usd']
    }

# ========== CLI Testing ==========

def main():
    """Command-line testing interface"""
    import argparse

    parser = argparse.ArgumentParser(
        description='AI Symbol Analyzer - On-demand Claude analysis',
        epilog="""
Examples:
  python ai_analyzer.py AAPL                    # Analyze AAPL with Haiku
  python ai_analyzer.py NVDA --model sonnet     # Use Sonnet model
  python ai_analyzer.py TSLA --refresh          # Force new analysis
  python ai_analyzer.py SPY --model opus        # Advanced analysis with Opus
        """
    )

    parser.add_argument('symbol', help='Stock symbol to analyze')
    parser.add_argument('--model', default='haiku',
                       choices=['haiku', 'sonnet', 'opus'],
                       help='Claude model to use (default: haiku)')
    parser.add_argument('--refresh', action='store_true',
                       help='Force new analysis (bypass cache)')
    parser.add_argument('--cache-only', action='store_true',
                       help='Only show cached analysis (no API call)')

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"AI Symbol Analysis: {args.symbol}")
    print(f"{'='*70}\n")

    try:
        if args.cache_only:
            # Check cache only
            cached = get_cached_analysis(args.symbol)
            if not cached:
                print(f"No cached analysis found for {args.symbol}")
                return

            result = cached
            result['from_cache'] = True
        else:
            # Run analysis
            result = analyze_symbol(
                args.symbol,
                model=args.model,
                force_refresh=args.refresh
            )

        # Display result
        print(f"Symbol: {result['symbol']}")
        print(f"Model: {result['model_used']}")
        print(f"Created: {result['created_at'][:19]}")
        print(f"Source: {'CACHE' if result['from_cache'] else 'NEW ANALYSIS'}")
        if result['age_days'] > 0:
            print(f"Age: {result['age_days']} days")
        print(f"\n{'='*70}\n")

        print(result['analysis_text'])

        print(f"\n{'='*70}\n")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
