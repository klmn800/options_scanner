"""AI Discovery Analyzer - Prioritizes symbols from discovery feed

Analyzes all triggered symbols in discovery feed and recommends top 3-5
opportunities worth deeper investigation.
"""

import os
import sys
import json
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from morning_view.tui_data import get_data

# Import Anthropic SDK
try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed")
    print("Install with: pip install anthropic")
    sys.exit(1)

# Cache configuration
CACHE_DB_PATH = "data/analysis_cache.db"  # Same as symbol analyzer
CACHE_HOURS = 24  # Cache is valid for 24 hours


# ========== Database Cache Functions ==========

def _get_cache_db_path():
    """Get absolute path to cache database"""
    if not os.path.isabs(CACHE_DB_PATH):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        return os.path.join(project_root, CACHE_DB_PATH)
    return CACHE_DB_PATH


def _init_cache_table():
    """Initialize discovery_analysis cache table if it doesn't exist"""
    db_path = _get_cache_db_path()

    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discovery_analysis (
            trade_date TEXT PRIMARY KEY,

            analysis_text TEXT NOT NULL,

            total_analyzed INTEGER NOT NULL,
            market_direction TEXT,
            market_regime TEXT,

            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,

            recommendations_json TEXT,
            raw_response TEXT,

            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_discovery_date
        ON discovery_analysis(trade_date DESC)
    """)

    conn.commit()
    conn.close()


def get_cached_discovery_analysis(trade_date: str = None) -> Optional[Dict[str, Any]]:
    """Retrieve cached discovery analysis if valid

    Args:
        trade_date: Trade date (YYYY-MM-DD). If None, uses today's date.

    Returns:
        Cached analysis dict or None if not found/stale
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')

    try:
        _init_cache_table()
        db_path = _get_cache_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM discovery_analysis
            WHERE trade_date = ?
        """, (trade_date,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        # Check if cache is still valid
        created_at = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')
        age_hours = (datetime.now() - created_at).total_seconds() / 3600

        if age_hours > CACHE_HOURS:
            return None  # Cache is stale

        # Reconstruct analysis dict from new schema
        analysis = {
            'recommendations': json.loads(row['recommendations_json']) if row['recommendations_json'] else [],
            'total_analyzed': row['total_analyzed'],
            'timestamp': created_at.isoformat(),
            'market_context': {
                'market_direction': row['market_direction'],
                'market_regime': row['market_regime']
            },
            'raw_analysis': row['raw_response'],
            'from_cache': True,
            'cache_age_minutes': int((datetime.now() - created_at).total_seconds() / 60)
        }

        # Add usage if available
        if row['cost_usd'] is not None:
            analysis['usage'] = {
                'input_tokens': row['input_tokens'],
                'output_tokens': row['output_tokens'],
                'cost_usd': row['cost_usd']
            }

        return analysis

    except Exception as e:
        print(f"Cache retrieval error: {e}")
        return None


def save_discovery_analysis_to_cache(analysis_result: Dict[str, Any], trade_date: str = None):
    """Save discovery analysis to cache

    Args:
        analysis_result: Analysis result from analyze_discovery_feed()
        trade_date: Trade date (YYYY-MM-DD). If None, uses today's date.
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y-%m-%d')

    try:
        _init_cache_table()
        db_path = _get_cache_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Extract components for new schema
        recommendations = analysis_result.get('recommendations', [])
        market_ctx = analysis_result.get('market_context', {})
        usage = analysis_result.get('usage', {})

        # Build clean analysis_text (prose format)
        analysis_text_parts = []
        for rec in recommendations:
            symbol = rec.get('symbol', 'N/A')
            rank = rec.get('rank', '?')
            reasoning = rec.get('reasoning', '')
            key_factors = rec.get('key_factors', [])
            risk_note = rec.get('risk_note', '')

            text_block = f"{rank}. {symbol}\n{reasoning}\n"
            if key_factors:
                text_block += f"Key Factors: {', '.join(key_factors)}\n"
            if risk_note:
                text_block += f"Risk: {risk_note}\n"

            analysis_text_parts.append(text_block)

        analysis_text = "\n".join(analysis_text_parts) if analysis_text_parts else "No recommendations"

        # Standard timestamp format
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            INSERT OR REPLACE INTO discovery_analysis (
                trade_date, analysis_text, total_analyzed,
                market_direction, market_regime,
                input_tokens, output_tokens, cost_usd,
                recommendations_json, raw_response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_date,
            analysis_text,
            analysis_result.get('total_analyzed', 0),
            market_ctx.get('market_direction'),
            market_ctx.get('market_regime'),
            usage.get('input_tokens'),
            usage.get('output_tokens'),
            usage.get('cost_usd'),
            json.dumps(recommendations) if recommendations else None,
            analysis_result.get('raw_analysis'),
            created_at
        ))

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"Cache save error: {e}")


def analyze_discovery_feed(max_recommendations: int = 5, force_refresh: bool = False) -> Dict[str, Any]:
    """Analyze all symbols in discovery feed and recommend top opportunities.

    Args:
        max_recommendations: Maximum number of symbols to recommend (default 5)
        force_refresh: If True, bypass cache and force new analysis

    Returns:
        Dict with:
            - recommendations: List of top symbols with reasoning
            - total_analyzed: Total symbols analyzed
            - timestamp: When analysis was performed
            - market_context: Current market regime/direction
            - from_cache: True if loaded from cache
            - cache_age_minutes: Age of cached result (if from cache)
    """
    # Check cache first (unless force_refresh)
    if not force_refresh:
        cached = get_cached_discovery_analysis()
        if cached:
            return cached

    # Get discovery data
    data = get_data()
    discovery_symbols = data.get_discovery()
    market_context = data.get_market_context()

    if not discovery_symbols:
        return {
            "recommendations": [],
            "total_analyzed": 0,
            "timestamp": datetime.now().isoformat(),
            "market_context": market_context,
            "error": "No symbols in discovery feed"
        }

    # Build analysis payload for Claude
    analysis_data = {
        "market_regime": market_context.get('market_regime', 'Unknown'),
        "market_direction": market_context.get('market_direction', 'Unknown'),
        "total_symbols": len(discovery_symbols),
        "symbols": []
    }

    # Extract key metrics for each symbol (focus on raw metrics, not composite scores)
    for symbol_data in discovery_symbols:
        symbol_summary = {
            "symbol": symbol_data.get('symbol'),
            # Activity metrics (raw counts, not scores)
            "active_alert_count": symbol_data.get('active_alert_count', 0),
            "new_alert_count": symbol_data.get('new_alert_count', 0),  # Today's fresh alerts
            "recent_alert_count_5d": symbol_data.get('recent_alert_count_5d', 0),  # Sustained interest
            "days_since_last_alert": symbol_data.get('days_since_last_alert', 999),  # Recency
            # Trigger types
            "trigger_flow_alert": bool(symbol_data.get('trigger_flow_alert', 0)),
            "trigger_earnings_play": bool(symbol_data.get('trigger_earnings_play', 0)),
            # Market context
            "direction_bias": symbol_data.get('direction_bias', 'NEUTRAL'),  # Sentiment from flow
            "earnings_days_ahead": symbol_data.get('earnings_days_ahead'),  # Event timing
            # Price metrics
            "current_price": symbol_data.get('current_price', symbol_data.get('close_price', 0)),
            "price_change_5d_pct": symbol_data.get('price_change_5d_pct', 0)  # Recent momentum
        }
        analysis_data["symbols"].append(symbol_summary)

    # Build prompt for Claude
    prompt = _build_analysis_prompt(analysis_data, max_recommendations)

    # Send to Claude API
    try:
        # Load API key from config.json
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config.json'
        )

        with open(config_path, 'r') as f:
            config = json.load(f)
            api_key = config['claude_api']['api_key']

        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",  # Use Haiku for cost efficiency
            max_tokens=2048,
            system="You are an expert options trader analyzing opportunity feeds to identify the highest-probability setups. Focus on confluence of signals, timing, and risk/reward.",
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # Extract text from response
        response_text = response.content[0].text

        # Calculate cost
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # Haiku pricing: $1.00 per MTok input, $5.00 per MTok output
        cost_usd = (input_tokens / 1_000_000 * 1.00) + (output_tokens / 1_000_000 * 5.00)

        # Parse response
        result = {
            "recommendations": _parse_recommendations(response_text),
            "total_analyzed": len(discovery_symbols),
            "timestamp": datetime.now().isoformat(),
            "market_context": market_context,
            "raw_analysis": response_text,
            "from_cache": False,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 4)
            }
        }

        # Save to cache
        save_discovery_analysis_to_cache(result)

        return result

    except Exception as e:
        return {
            "recommendations": [],
            "total_analyzed": len(discovery_symbols),
            "timestamp": datetime.now().isoformat(),
            "market_context": market_context,
            "error": f"Analysis failed: {str(e)}"
        }


def _build_analysis_prompt(data: Dict[str, Any], max_recommendations: int) -> str:
    """Build prompt for Claude API"""

    prompt = f"""You are analyzing {data['total_symbols']} symbols that triggered our scanner today.

MARKET CONTEXT:
- Regime: {data['market_regime']}
- Direction: {data['market_direction']}

YOUR TASK:
Identify the top {max_recommendations} symbols worth deeper investigation. Focus on RAW METRICS that tell a story:
1. **Activity patterns**: Fresh alerts (today) vs sustained interest (5d window) vs stale (>10 days)
2. **Event timing**: Earnings windows, flow alert recency
3. **Confluence**: Multiple independent signals (flow + earnings, sustained alerts + price action)
4. **Market alignment**: Does direction_bias align with market regime?

CRITICAL: Ignore any "score" fields. Focus on the raw metrics that compose those scores:
- Alert counts (new, recent, active) tell the story of interest and timing
- Days since last alert tells freshness/staleness
- Price change % tells if price is confirming flow sentiment
- Earnings timing tells event catalyst proximity

DISCOVERY FEED DATA:
{json.dumps(data['symbols'], indent=2)}

METRIC DEFINITIONS:
- **active_alert_count**: Total flow alerts still relevant (shows cumulative interest)
- **new_alert_count**: Alerts triggered TODAY (shows fresh institutional interest - VERY IMPORTANT)
- **recent_alert_count_5d**: Alerts in last 5 days (shows sustained vs one-off activity)
- **days_since_last_alert**: 0 = today, 1-3 = very recent, 7-10 = getting stale, >25 = stale/ignore
- **trigger_flow_alert**: Symbol triggered due to significant options flow
- **trigger_earnings_play**: Symbol triggered due to upcoming earnings event
- **direction_bias**: BULLISH/BEARISH/NEUTRAL sentiment derived from call/put flow ratios
- **earnings_days_ahead**: Days until earnings (if applicable). 1-7 = entry window, 8-14 = watch zone
- **price_change_5d_pct**: Recent price momentum (confirms or contradicts flow bias)

INTERPRETATION GUIDANCE:
- **Fresh interest**: new_alert_count > 0 (today's activity is most valuable signal)
- **Sustained interest**: recent_alert_count_5d >= 3 (not just one-off flow)
- **Stale setup**: days_since_last_alert > 10 (probably already played out)
- **Earnings timing**: 3-7 days ahead is optimal entry window for volatility plays
- **Alignment**: Bullish flow + positive price_change_5d_pct in bullish regime = strong confluence

OUTPUT FORMAT (VALID JSON - USE FIELDS FOR EXPLANATIONS):
{{
  "top_picks": [
    {{
      "symbol": "TICKER",
      "rank": 1,
      "reasoning": "2-3 sentence explanation of why this is compelling",
      "key_factors": ["Fresh flow", "Earnings in 3d", "Bullish regime alignment"],
      "risk_note": "Brief risk consideration"
    }}
  ],
  "honorable_mentions": [
    {{"symbol": "TICKER1", "note": "Why worth mentioning"}},
    {{"symbol": "TICKER2", "note": "Why worth mentioning"}}
  ],
  "avoid_today": [
    {{"symbol": "TICKER3", "reason": "Stale alerts"}},
    {{"symbol": "TICKER4", "reason": "Weak confluence"}}
  ]
}}

CRITICAL: Return ONLY valid JSON. Do NOT use // or /* */ comments inside the JSON.
If you want to add explanatory notes, use object fields like "note" or "reason".

Focus on actionable opportunities. If a symbol has high confluence but stale alerts (>10 days), flag it. If fresh activity but low confluence, explain what's missing. Be honest about weak setups.
"""

    return prompt


def _parse_recommendations(response: str) -> List[Dict[str, Any]]:
    """Parse Claude's response into structured recommendations

    Claude often returns: JSON object + explanatory commentary
    We want to parse the JSON but preserve the commentary as metadata
    """
    try:
        # Try to extract JSON from response
        # Claude might wrap it in markdown code blocks or include explanatory text
        if "```json" in response:
            json_start = response.index("```json") + 7
            json_end = response.index("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "```" in response:
            json_start = response.index("```") + 3
            json_end = response.index("```", json_start)
            json_str = response[json_start:json_end].strip()
        else:
            # JSON might be embedded in text - find the object boundaries
            # Use a more robust approach: find matching braces
            first_brace = response.find('{')
            if first_brace == -1:
                raise ValueError("No JSON object found in response")

            # Find the matching closing brace by counting depth
            brace_depth = 0
            in_string = False
            escape_next = False

            for i in range(first_brace, len(response)):
                char = response[i]

                # Handle string escaping
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue

                # Track if we're in a string
                if char == '"':
                    in_string = not in_string
                    continue

                # Only count braces outside of strings
                if not in_string:
                    if char == '{':
                        brace_depth += 1
                    elif char == '}':
                        brace_depth -= 1
                        # Found matching closing brace
                        if brace_depth == 0:
                            json_str = response[first_brace:i+1]
                            break
            else:
                # Didn't find matching brace, fallback to rfind
                last_brace = response.rfind('}')
                if last_brace != -1:
                    json_str = response[first_brace:last_brace+1]
                else:
                    json_str = response

        # Try to parse the extracted JSON
        try:
            parsed = json.loads(json_str)
            return parsed.get("top_picks", [])
        except json.JSONDecodeError:
            # Fallback: Claude might have added // comments despite instructions
            # Try stripping them and re-parsing
            cleaned_lines = []
            for line in json_str.split('\n'):
                # Find // outside of strings and strip from there
                in_string = False
                for i, char in enumerate(line):
                    if char == '"' and (i == 0 or line[i-1] != '\\'):
                        in_string = not in_string
                    elif char == '/' and i+1 < len(line) and line[i+1] == '/' and not in_string:
                        # Found comment, take everything before it
                        cleaned_lines.append(line[:i].rstrip())
                        break
                else:
                    # No comment found, keep whole line
                    cleaned_lines.append(line)

            json_str_cleaned = '\n'.join(cleaned_lines)
            parsed = json.loads(json_str_cleaned)  # Let this raise if it still fails
            return parsed.get("top_picks", [])

    except (json.JSONDecodeError, ValueError, AttributeError) as e:
        # Fallback: return raw response as single recommendation
        return [{
            "symbol": "PARSE_ERROR",
            "rank": 0,
            "reasoning": f"Failed to parse AI response: {str(e)}",
            "key_factors": [],
            "risk_note": "See raw_analysis field for full response"
        }]


def format_analysis_for_display(analysis_result: Dict[str, Any]) -> str:
    """Format analysis result for TUI display

    Args:
        analysis_result: Output from analyze_discovery_feed()

    Returns:
        Formatted string ready for display in Textual Static widget
    """
    if "error" in analysis_result:
        return f"[red]Analysis Error[/red]\n\n{analysis_result['error']}"

    # Header
    market_ctx = analysis_result['market_context']
    market_dir = market_ctx.get('market_direction', 'Unknown')
    market_regime = market_ctx.get('market_regime', 'Unknown')

    if market_dir == 'BULLISH':
        market_color = 'green'
    elif market_dir == 'BEARISH':
        market_color = 'red'
    else:
        market_color = 'yellow'

    timestamp = datetime.fromisoformat(analysis_result['timestamp']).strftime('%I:%M %p').lstrip('0')

    # Usage and cost info
    usage_info = ""
    if 'usage' in analysis_result:
        usage = analysis_result['usage']
        input_k = usage['input_tokens'] / 1000
        output_k = usage['output_tokens'] / 1000
        cost = usage['cost_usd']
        usage_info = f" | [dim]Cost: ${cost:.4f} ({input_k:.1f}k in / {output_k:.1f}k out)[/dim]"

    # Cache status
    cache_info = ""
    if analysis_result.get('from_cache'):
        age_min = analysis_result.get('cache_age_minutes', 0)
        if age_min < 60:
            cache_info = f" | [dim]Cached: {age_min}m ago[/dim]"
        else:
            age_hours = age_min // 60
            cache_info = f" | [dim]Cached: {age_hours}h ago[/dim]"

    output = f"""[bold cyan]AI DISCOVERY ANALYSIS[/bold cyan]
[{market_color}]Market: {market_dir}[/{market_color}] | Regime: {market_regime}
Analyzed: {analysis_result['total_analyzed']} symbols | Time: {timestamp}{cache_info}{usage_info}

"""

    # Recommendations
    recommendations = analysis_result.get('recommendations', [])

    if not recommendations:
        output += "[yellow]No recommendations generated[/yellow]\n"
        return output

    output += "[bold green]TOP OPPORTUNITIES:[/bold green]\n\n"

    for rec in recommendations:
        rank = rec.get('rank', '?')
        symbol = rec.get('symbol', 'N/A')
        reasoning = rec.get('reasoning', 'No reasoning provided')
        key_factors = rec.get('key_factors', [])
        risk_note = rec.get('risk_note', 'N/A')

        output += f"[bold white]{rank}. {symbol}[/bold white]\n"
        output += f"   {reasoning}\n"

        if key_factors:
            output += f"   [dim]Factors: {', '.join(key_factors)}[/dim]\n"

        output += f"   [yellow]Risk: {risk_note}[/yellow]\n\n"

    # Footer with cache refresh hint
    if analysis_result.get('from_cache'):
        output += "\n[dim]Press ESC to close | F: Force Refresh | Enter on symbol: Deep-dive[/dim]"
    else:
        output += "\n[dim]Press ESC to close | Press ENTER on symbol in Discovery to deep-dive[/dim]"

    return output


if __name__ == "__main__":
    # CLI testing
    import argparse

    parser = argparse.ArgumentParser(description="Analyze discovery feed with AI")
    parser.add_argument('--max', type=int, default=5, help='Max recommendations to generate')
    parser.add_argument('--json', action='store_true', help='Output raw JSON')
    args = parser.parse_args()

    print("Analyzing discovery feed...")
    result = analyze_discovery_feed(max_recommendations=args.max)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_analysis_for_display(result))
