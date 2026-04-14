#!/usr/bin/env python3
"""
AI Analysis Prompts for Morning Views TUI

All prompts are stored here for easy editing and iteration.
System prompts define Claude's role and capabilities.
Analysis prompts are templates that get filled with symbol data.

Author: Ben
Date: 2025-10-08
"""

# ========== System Prompts ==========

SYSTEM_PROMPT = """You are an expert options trading analyst specializing in analyzing complex market data.

Your role is to:
1. Analyze options flow, open interest, and market positioning data
2. Identify key patterns, risks, and opportunities
3. Provide clear, actionable insights for traders
4. Flag unusual activity or significant changes

Analysis Style:
- Be concise and direct - traders value clarity over length
- Use bullet points for key findings
- Highlight unusual or noteworthy patterns
- Include specific data points (strikes, dates, OI levels)
- Note any red flags or risks
- Provide context about what the data suggests

Data Context:
- You have access to curated morning views data from a comprehensive options scanner
- Data includes: OI timing (smart money vs retail), OI distribution (strikes/greeks), flow alerts
- Market regime and direction are tracked (Bull/Bear, trending/choppy)
- Symbol fundamentals (sector, industry) are available

Trading Context - User's Style and Constraints:
- **Only trades LONG OPTIONS** (buying calls for bullish, buying puts for bearish)
- **NEVER sells options** - Do not suggest spreads, covered calls, cash-secured puts, or any strategy requiring selling
- **Swing trading timeframe**: Positions held days to weeks (not day trades, not LEAPs)
- **Profit target**: 25% gain on options (mention this as benchmark exit)
- **Exit discipline**: Close positions well before expiration - never hold to expiration
- **Portfolio size**: ~$4,000 total capital
- **Position sizing**: <$300 per trade (maximum ~7.5% of portfolio)
- **Trading platform**: Robinhood (commission-free, limited analytics vs professional platforms)
- **Symbol preference**: Stock price < $60 preferred (more affordable options premiums)

When Providing Trade Recommendations:
- Only suggest BUYING calls (bullish setups) or BUYING puts (bearish setups)
- Consider affordability: Options premium should fit within $300 position size
- Recommend strikes and expirations appropriate for 2-4 week swing trades
- Frame profit targets around 25% gain level
- Account for Robinhood's limitations (no complex order types, basic Greeks display)
- Prioritize symbols under $60 when possible
- Be specific: "Consider buying $25 calls expiring 11/15" not "Consider call spreads"

Output Format:
- Use markdown formatting
- Start with a 1-2 sentence executive summary
- Use sections with headers (## Header)
- Bold important metrics or findings
- Keep total analysis under 500 words unless complexity demands more
"""

# ========== Analysis Prompt Templates ==========

# Main symbol analysis prompt - gets filled with data from tui_data.py
ANALYSIS_PROMPT_TEMPLATE = """Analyze the following options data for {symbol}:

## SYMBOL OVERVIEW
Price: ${price:.2f}
5d Price Change: {price_change_5d:+.1f}%
Sector: {sector}
Industry: {industry}

Confluence Score: {confluence_score}/5
Direction Bias: {direction_bias}
Conviction Level: {conviction_level}
Primary Signal: {primary_signal}

Active Alerts: {active_alert_count}
{earnings_context}

## MARKET CONTEXT
Market Direction: {market_direction}
Market Regime: {market_regime}

## OI TIMING ANALYSIS (Smart Money vs Retail)
{oi_timing_summary}

## OI DISTRIBUTION
Total Open Interest: {total_oi:,}
Put/Call Ratio: {put_call_ratio:.2f}

Call OI: {call_oi:,} ({call_pct:.1f}%)
Put OI: {put_oi:,} ({put_pct:.1f}%)

Top Call Strikes: {top_calls}
Top Put Strikes: {top_puts}

Time Distribution:
- 0-7 DTE: {dte_0_7:.1f}%
- 8-21 DTE: {dte_8_21:.1f}%
- 22-35 DTE: {dte_22_35:.1f}%
- 36-60 DTE: {dte_36_60:.1f}%

Greek Exposures:
- Net Delta: {net_delta:+.2f}M shares ({delta_bias})
- Max Gamma Strike: ${max_gamma_strike:.2f}
- Max Pain: ${max_pain:.2f} ({pain_distance:+.1f}% from current)

{previous_analysis_context}

Please provide:
1. Executive summary (1-2 sentences)
2. Key findings from the data
3. Notable patterns or unusual activity
4. Potential risks or opportunities
5. Overall assessment and what this setup suggests
"""

# Prompt for when previous analysis exists (iteration/update)
ITERATION_CONTEXT_TEMPLATE = """
## PREVIOUS ANALYSIS (from {analysis_date})
{previous_analysis}

Note: Compare current data to previous analysis. Highlight any significant changes or developments since last analysis.
"""

# Simplified prompt for symbols with limited data
BASIC_ANALYSIS_PROMPT_TEMPLATE = """Analyze the following options data for {symbol}:

## SYMBOL OVERVIEW
Price: ${price:.2f}
Sector: {sector}

Confluence Score: {confluence_score}/5
Direction Bias: {direction_bias}
Primary Signal: {primary_signal}

## AVAILABLE DATA
{available_data_summary}

Note: Limited data available for this symbol. Provide analysis based on available information and note any gaps that limit the assessment.

Please provide a concise analysis of what the available data suggests.
"""

# ========== Helper Functions ==========

def build_oi_timing_summary(oi_timing_data):
    """Build text summary of OI timing data for prompt

    Args:
        oi_timing_data: List of OI timing records from tui_data.py

    Returns:
        str: Formatted summary text
    """
    if not oi_timing_data:
        return "No significant OI timing data available"

    summary_lines = []

    # Count predictive vs chasing
    predictive = sum(1 for row in oi_timing_data if 'PREDICTIVE' in row.get('positioning_type', ''))
    chasing = sum(1 for row in oi_timing_data if 'CHASING' in row.get('positioning_type', ''))

    summary_lines.append(f"Predictive positions: {predictive}")
    summary_lines.append(f"Chasing positions: {chasing}")
    summary_lines.append("")

    # Top 3-5 notable positions
    summary_lines.append("Notable positions:")
    for row in oi_timing_data[:5]:
        strike = row.get('strike', 0)
        opt_type = row.get('option_type', 'N/A')
        oi = row.get('open_interest', 0)
        positioning = row.get('positioning_type', 'N/A')
        days_since = row.get('oi_build_days_since', 0)

        summary_lines.append(
            f"- ${strike:.0f} {opt_type}, OI: {oi:,}, {positioning}, built {days_since} days ago"
        )

    return "\n".join(summary_lines)

def build_earnings_context(overview_data):
    """Build earnings context string if relevant

    Args:
        overview_data: Symbol overview dict from tui_data.py

    Returns:
        str: Earnings context or empty string
    """
    earnings_days = overview_data.get('earnings_days_ahead')

    if earnings_days is None:
        return ""

    if earnings_days <= 0:
        return "**Earnings: Recently reported**"
    elif earnings_days <= 7:
        return f"**Earnings: {earnings_days} days ahead (NEAR-TERM)**"
    elif earnings_days <= 14:
        return f"**Earnings: {earnings_days} days ahead**"
    else:
        return f"Earnings: {earnings_days} days ahead"

def format_previous_analysis(previous_analysis_text, analysis_date):
    """Format previous analysis for iteration context

    Args:
        previous_analysis_text: Previous analysis markdown
        analysis_date: ISO date string of previous analysis

    Returns:
        str: Formatted iteration context
    """
    if not previous_analysis_text:
        return ""

    return ITERATION_CONTEXT_TEMPLATE.format(
        analysis_date=analysis_date[:10],  # Just date, not time
        previous_analysis=previous_analysis_text
    )
