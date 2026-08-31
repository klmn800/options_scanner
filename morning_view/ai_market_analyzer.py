#!/usr/bin/env python3
"""
AI Market Analyzer - Standalone Tool
=====================================

AI-powered market intelligence using Claude API to analyze comprehensive market data.
Implements a 3-round persistent memory analysis framework for sophisticated market insights.

Extracted from daily_analysis system (deprecated 2025-10-13)
Queries market_daily_summary directly (no curated tables required)

Architecture:
- Round 1: Today's Market Snapshot (no time series)
- Round 2: Time Series Analysis (5-day metrics focus)
- Round 4: Synthesis & Memory Formation (actionable intelligence)

Usage:
    python morning_view/ai_market_analyzer.py --date 2025-10-13
    python morning_view/ai_market_analyzer.py --date 2025-10-13 --output analysis_output.json

Author: Ben (With assistance from Claude)
Date: 2025-09-16 (Original), 2025-10-13 (Extracted)
"""

import sys
import os
import json
import sqlite3
import logging
from datetime import datetime, timedelta
import argparse

# Add parent directory to path for core imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic


class MarketAnalysisEngine:
    """
    AI-powered market analysis engine with 3-round persistent memory framework.
    """

    def __init__(self, config, logs_directory=None):
        """Initialize the analysis engine with configuration and logging."""
        self.config = config
        self.claude_config = config.get('claude_api', {})

        # Initialize Claude client
        self.claude_client = anthropic.Anthropic(
            api_key=self.claude_config.get('api_key')
        )

        # Analysis session tracking
        self.session_tokens = 0
        self.session_cost = 0.0
        self.round_results = {}
        self.detailed_round_logs = {}

        # Debug logging configuration
        self.debug_logging_enabled = config.get('debug_logging', True)
        self.logs_directory = logs_directory or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

        # Create logs directory if it doesn't exist
        os.makedirs(self.logs_directory, exist_ok=True)

        print("INFO: Market Analysis Engine initialized with model: {}".format(
            self.claude_config.get('model', 'claude-3-5-haiku-20241022')
        ))

    def save_round_details(self, round_name, prompt, response, input_data=None, trade_date=None):
        """Save detailed round information for debugging."""
        if not self.debug_logging_enabled:
            return

        round_info = {
            'round_name': round_name,
            'timestamp': datetime.now().isoformat(),
            'prompt': prompt,
            'response': response,
            'input_data_summary': self.summarize_input_data(input_data) if input_data else None,
            'tokens_used': self.session_tokens,
            'cost_so_far': self.session_cost,
            'model': self.claude_config.get('model', 'claude-3-5-haiku-20241022')
        }

        self.detailed_round_logs[round_name] = round_info

        # Save to file if we have a trade_date
        if trade_date:
            self.save_logs_to_file(trade_date)

    def summarize_input_data(self, data):
        """Create a summary of input data for logging."""
        if not data:
            return None

        if isinstance(data, dict):
            return {
                'field_count': len(data),
                'key_fields': list(data.keys())[:10],  # First 10 keys
                'sample_values': {k: str(v)[:100] for k, v in list(data.items())[:5]}  # First 5 values, truncated
            }
        else:
            return {'type': type(data).__name__, 'length': len(str(data))}

    def save_logs_to_file(self, trade_date):
        """Save all round logs to a JSON file."""
        if not self.detailed_round_logs:
            return

        try:
            log_filename = "market_analysis_{}_rounds.json".format(trade_date)
            log_path = os.path.join(self.logs_directory, log_filename)

            log_data = {
                'trade_date': trade_date,
                'analysis_timestamp': datetime.now().isoformat(),
                'model_used': self.claude_config.get('model', 'claude-3-5-haiku-20241022'),
                'total_tokens': self.session_tokens,
                'total_cost': self.session_cost,
                'rounds': self.detailed_round_logs
            }

            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)

            print("INFO: Round-by-round logs saved to: {}".format(log_path))

        except Exception as e:
            print("ERROR: Failed to save round logs: {}".format(str(e)))

    def get_today_market_data(self, conn, trade_date):
        """Retrieve today's complete market data from market_daily_summary."""
        query = """
        SELECT trade_date,
               CAST(strftime('%w', trade_date) AS INTEGER) as day_of_week,
               regime_classification, market_direction,
               spy_high, spy_low, spy_close, spy_change_percent,
               vix_high, vix_low, vix_close, vix_change_percent,
               qqq_change_percent, iwm_change_percent, tlt_change_percent, gld_change_percent, uup_change_percent,
               advancing_stocks, declining_stocks, advancing_volume, declining_volume,
               new_highs, new_lows
        FROM market_daily_summary
        WHERE trade_date = ?
        """

        cursor = conn.execute(query, (trade_date,))
        row = cursor.fetchone()

        if not row:
            print("ERROR: No market data found for {}".format(trade_date))
            return None

        # Convert to dictionary using column names
        columns = [description[0] for description in cursor.description]
        market_data = dict(zip(columns, row))

        # Add calculated time series metrics if we have enough historical data
        market_data = self.add_time_series_metrics(conn, trade_date, market_data)

        print("INFO: Retrieved market data for {} with {} fields".format(trade_date, len(market_data)))
        return market_data

    def add_time_series_metrics(self, conn, trade_date, market_data):
        """Add 5-day time series metrics to market data."""
        # Calculate VIX 5-day average and trend
        vix_query = """
        WITH recent_vix AS (
            SELECT vix_close, ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
            FROM market_daily_summary
            WHERE trade_date <= ? AND vix_close IS NOT NULL
            LIMIT 10
        )
        SELECT
            ROUND(AVG(CASE WHEN rn <= 5 THEN vix_close END), 3) as vix_5day_avg,
            ROUND(AVG(CASE WHEN rn <= 5 THEN vix_close END) -
                  AVG(CASE WHEN rn BETWEEN 6 AND 10 THEN vix_close END), 3) as vix_5day_trend
        FROM recent_vix
        """
        cursor = conn.execute(vix_query, (trade_date,))
        vix_row = cursor.fetchone()
        if vix_row:
            market_data['vix_5day_avg'] = vix_row[0]
            market_data['vix_5day_trend'] = vix_row[1]

        # Calculate advance/decline ratio and trend
        adv_dec_query = """
        WITH today AS (
            SELECT
                CASE WHEN declining_stocks > 0
                THEN ROUND(CAST(advancing_stocks AS REAL) / declining_stocks, 3)
                ELSE advancing_stocks END as adv_dec_ratio
            FROM market_daily_summary
            WHERE trade_date = ?
        ),
        recent_adv_dec AS (
            SELECT
                CASE WHEN declining_stocks > 0
                     THEN ROUND(CAST(advancing_stocks AS REAL) / declining_stocks, 3)
                     ELSE advancing_stocks
                END as daily_ratio,
                ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
            FROM market_daily_summary
            WHERE trade_date <= ? AND advancing_stocks IS NOT NULL
            LIMIT 10
        )
        SELECT
            (SELECT adv_dec_ratio FROM today),
            ROUND(AVG(CASE WHEN rn <= 5 THEN daily_ratio END) -
                  AVG(CASE WHEN rn BETWEEN 6 AND 10 THEN daily_ratio END), 3) as adv_dec_5day_trend
        FROM recent_adv_dec
        """
        cursor = conn.execute(adv_dec_query, (trade_date, trade_date))
        adv_dec_row = cursor.fetchone()
        if adv_dec_row:
            market_data['adv_dec_ratio'] = adv_dec_row[0]
            market_data['adv_dec_5day_trend'] = adv_dec_row[1]

        # Calculate consecutive market direction days
        direction_query = """
        SELECT market_direction
        FROM market_daily_summary
        WHERE trade_date <= ? AND market_direction IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 20
        """
        cursor = conn.execute(direction_query, (trade_date,))
        direction_rows = cursor.fetchall()

        if direction_rows:
            current_direction = direction_rows[0][0]
            consecutive_days = 1
            for row in direction_rows[1:]:
                if row[0] == current_direction:
                    consecutive_days += 1
                else:
                    break
            market_data['consecutive_market_direction_days'] = consecutive_days

        return market_data

    def filter_snapshot_data(self, market_data):
        """Filter out time series fields for Round 1 snapshot analysis."""
        if not market_data:
            return {}

        # Time series indicators to exclude from Round 1
        time_series_indicators = [
            '5day', '5d', 'consecutive', 'consistency', 'trend', 'momentum', 'weekly'
        ]

        snapshot_data = {}
        for key, value in market_data.items():
            # Skip time series fields
            if any(indicator in key.lower() for indicator in time_series_indicators):
                continue

            snapshot_data[key] = value

        print("INFO: Filtered snapshot data: {} fields (removed time series)".format(len(snapshot_data)))
        return snapshot_data

    def call_claude_api(self, prompt, round_name, max_tokens=1500):
        """Make Claude API call with usage tracking."""
        try:
            message = self.claude_client.messages.create(
                model=self.claude_config.get('model', 'claude-3-5-haiku-20241022'),
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Track usage
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens
            total_tokens = input_tokens + output_tokens

            # Claude 3.5 Haiku pricing (per million tokens)
            cost = (input_tokens * 0.00000025) + (output_tokens * 0.00000125)  # $0.25/$1.25 per million

            self.session_tokens += total_tokens
            self.session_cost += cost

            print("INFO: {} completed: {} tokens (${:.4f})".format(round_name, total_tokens, cost))

            return message.content[0].text

        except Exception as e:
            print("ERROR: {} API call failed: {}".format(round_name, str(e)))
            return None

    def execute_round_1_analysis(self, snapshot_data, trade_date=None):
        """Round 1: Today's Market Context Analysis - Focus on TODAY ONLY."""
        print("INFO: Starting Round 1: Today's Market Snapshot Analysis")

        # Enhanced financial intelligence framework for actionable analysis
        intelligence_framework = """
=== ACTIONABLE INTELLIGENCE FRAMEWORK ===

BREADTH ANALYSIS:
• adv_dec_ratio >1.2=strong participation, 0.8-1.2=mixed, <0.8=poor (breadth divergence warning)
• new_highs_lows_net >50=healthy expansion, 0-50=weak, <0=deteriorating leadership

CROSS-ASSET SIGNAL STRENGTH:
• Rate each signal: STRONG/MODERATE/WEAK/CONFLICTING

VIX REGIME: <15=complacent, 15-25=normal, 25-35=elevated fear, >35=panic

FORBIDDEN LANGUAGE: ❌ "nuanced," "subtle complexity," "underlying dynamics," "market environment," "suggests caution"
REQUIRED STYLE: ✅ "[Specific observation] + [Trading implication]" - Be direct and actionable
"""

        prompt = """You are a quantitative equity strategist providing actionable trading intelligence, not market commentary.

CONTEXT: This is ROUND 1 of 4: TODAY'S MARKET SNAPSHOT ONLY.

{}

TODAY'S MARKET SNAPSHOT:
{}

=== REQUIRED OUTPUT STRUCTURE ===

1. **Market Type**: [Bull/Bear/Neutral] + breadth quality assessment
2. **Cross-Asset Check**: Rate signal strength (STRONG/MODERATE/WEAK) and trading implications
3. **Volume/Risk Assessment**: Conviction level and regime classification

=== STYLE REQUIREMENTS ===
• Maximum 3 sentences
• Include specific numbers and thresholds from framework
• Focus on "what does this mean for positioning?"
• End each point with clear trading implication

Provide your assessment following this exact structure and style.""".format(
            intelligence_framework,
            json.dumps(snapshot_data, indent=2)
        )

        response = self.call_claude_api(prompt, "Round_1", max_tokens=400)
        self.round_results['round_1'] = response

        # Save detailed logs
        self.save_round_details("round_1", prompt, response, snapshot_data, trade_date)

        return response

    def execute_round_2_analysis(self, market_data, round_1_notes, trade_date=None):
        """Round 2: Time Series Analysis (5-day metrics focus)."""
        print("INFO: Starting Round 2: Time Series Analysis")

        # Time series interpretation framework
        time_series_framework = """
=== 5-DAY MOMENTUM INTELLIGENCE FRAMEWORK ===

TREND SUSTAINABILITY:
• consecutive_market_direction_days: 1=fresh, 2-3=developing, >3=established trend
• vix_5day_trend: positive=building stress, negative=calming environment
• adv_dec_5day_trend: >0.3=strengthening breadth, <-0.3=deteriorating participation

REGIME STABILITY:
• vix_5day_avg: compare to current VIX for volatility regime assessment

FORBIDDEN: "nuanced," "complexity," "suggests," "indicates potential"
REQUIRED: Numbers + directional assessment + sustainability rating
"""

        prompt = """You are a quantitative momentum analyst providing 5-day trend sustainability assessment.

ROUND 1 BASELINE:
{}

{}

5-DAY METRICS DATA:
{}

=== REQUIRED ANALYSIS STRUCTURE ===

1. **Trend Persistence**: consecutive_market_direction_days + sustainability rating (STRONG/MODERATE/WEAK)
2. **Breadth Momentum**: adv_dec_5day_trend + participation trajectory assessment
3. **Regime Stability**: VIX trends + regime transition risk

=== OUTPUT REQUIREMENTS ===
• Maximum 3 sentences, robotic precision
• Include specific threshold numbers from framework
• Rate each factor: STRENGTHENING/STABLE/DETERIORATING
• End with momentum sustainability verdict (SUSTAINABLE/QUESTIONABLE/UNSUSTAINABLE)

Provide assessment using exact structure and robotic precision.""".format(
            round_1_notes,
            time_series_framework,
            json.dumps(market_data, indent=2)
        )

        response = self.call_claude_api(prompt, "Round_2", max_tokens=500)
        self.round_results['round_2'] = response

        # Save detailed logs
        input_data = {'market_data': market_data, 'round_1_notes': round_1_notes}
        self.save_round_details("round_2", prompt, response, input_data, trade_date)

        return response

    def execute_round_4_synthesis(self, trade_date=None):
        """Round 4: Final synthesis and structured output.

        Kept as "round_4" in logs/keys for continuity; Round 3 (Oracle/Vanna
        database exploration) was retired 2026-08-31.
        """
        print("INFO: Starting Round 4: Synthesis & Memory Formation")

        # Final synthesis framework for robotic intelligence output
        synthesis_framework = """
=== TRADING INTELLIGENCE SYNTHESIS FRAMEWORK ===

MARKET CLASSIFICATION:
• Environment: BULL/BEAR/NEUTRAL + strength rating (STRONG/MODERATE/WEAK)
• Breadth quality: HEALTHY/MIXED/POOR + participation level
• Regime: STABLE/TRANSITION/UNSTABLE + sustainability timeframe

MOMENTUM ASSESSMENT:
• Trend strength: rate 1-10 + sustainability outlook (DAYS/WEEKS/MONTHS)
• Cross-asset alignment: SUPPORTIVE/NEUTRAL/CONFLICTING

FORBIDDEN: "suggests," "environment shows," "market appears"
REQUIRED: Specific ratings + numerical confidence levels
"""

        prompt = """You are a quantitative trading intelligence synthesizer providing final position recommendations.

ROUND 1 MARKET TYPE: {}
ROUND 2 MOMENTUM DATA: {}

{}

SYNTHESIS TASK: Convert analysis into actionable trading intelligence using EXACT JSON format.

CRITICAL: All JSON field values must be PLAIN TEXT STRINGS, NOT nested objects or arrays.

JSON REQUIREMENTS (all values are plain text strings):
• market_environment_summary: Single string like "BEAR market, strength 7/10, healthy breadth (1.2 adv/dec ratio)"
• momentum_and_trends: Single string like "Momentum sustainable for 3-5 days, high conviction, cross-assets supportive"
• key_nuances_discovered: Single string summarizing non-obvious patterns
• trading_implications: Single string describing position sizing and risk
• confidence_assessment: Single string like "high confidence (0.75 numerical basis)"

EXAMPLE VALID JSON:
{{
  "market_environment_summary": "NEUTRAL market, moderate strength (6/10), healthy breadth with 1.15 adv/dec ratio",
  "momentum_and_trends": "Weak momentum sustainability (2-3 days), low conviction, mixed cross-asset signals",
  "key_nuances_discovered": "VIX compression to 15-day lows despite declining breadth suggests complacency risk",
  "trading_implications": "Reduce position size 30%, favor defensive sectors, tight stops below support",
  "confidence_assessment": "medium confidence (0.62 numerical basis from breadth divergence)"
}}

ROBOTIC PRECISION REQUIRED - no market commentary, only trading intelligence.
Respond ONLY with valid JSON object matching the example structure. No nested objects. No additional text.""".format(
            self.round_results.get('round_1', 'No Round 1 data'),
            self.round_results.get('round_2', 'No Round 2 data'),
            synthesis_framework
        )

        response = self.call_claude_api(prompt, "Round_4_Synthesis", max_tokens=800)

        # Save detailed logs
        input_data = {
            'round_1_results': self.round_results.get('round_1'),
            'round_2_results': self.round_results.get('round_2'),
        }
        self.save_round_details("round_4", prompt, response, input_data, trade_date)

        if not response:
            return self.create_error_synthesis("Round 4 API call failed")

        # Parse JSON response
        try:
            synthesis_json = json.loads(response)

            # Add metadata
            synthesis_json["analysis_timestamp"] = datetime.now().isoformat()
            synthesis_json["rounds_completed"] = 3
            synthesis_json["total_tokens_used"] = self.session_tokens
            synthesis_json["total_cost_estimate"] = round(self.session_cost, 4)
            synthesis_json["model_used"] = self.claude_config.get('model', 'claude-3-5-haiku-20241022')

            return synthesis_json

        except json.JSONDecodeError as e:
            print("ERROR: Failed to parse Round 4 JSON response: {}".format(str(e)))
            print("ERROR: Raw response: {}".format(response))
            return self.create_error_synthesis("JSON parsing failed", response)

    def create_error_synthesis(self, error_msg, raw_response=None):
        """Create error synthesis when normal processing fails."""
        return {
            "analysis_status": "failed",
            "error": error_msg,
            "raw_response": raw_response,
            "rounds_completed": len([r for r in self.round_results.values() if r]),
            "analysis_timestamp": datetime.now().isoformat(),
            "total_tokens_used": self.session_tokens,
            "total_cost_estimate": round(self.session_cost, 4)
        }

    def conduct_full_analysis(self, conn, trade_date):
        """Execute the complete 3-round market analysis."""
        print("INFO: Starting 3-round market analysis for {}".format(trade_date))

        try:
            # Get today's market data
            market_data = self.get_today_market_data(conn, trade_date)
            if not market_data:
                return self.create_error_synthesis("Market data not available")

            # Round 1: Today's snapshot analysis
            snapshot_data = self.filter_snapshot_data(market_data)
            round_1_result = self.execute_round_1_analysis(snapshot_data, trade_date)
            if not round_1_result:
                return self.create_error_synthesis("Round 1 analysis failed")

            # Round 2: Time series analysis
            round_2_result = self.execute_round_2_analysis(market_data, round_1_result, trade_date)
            if not round_2_result:
                print("WARNING: Round 2 failed, continuing with available data")

            # Round 4: Synthesis
            final_synthesis = self.execute_round_4_synthesis(trade_date)

            # Final save of all logs
            self.save_logs_to_file(trade_date)

            print("INFO: Market analysis completed: {} total tokens, ${:.4f} cost".format(
                self.session_tokens, self.session_cost
            ))

            return final_synthesis

        except Exception as e:
            print("ERROR: Fatal error in market analysis: {}".format(str(e)))
            return self.create_error_synthesis("Fatal analysis error: {}".format(str(e)))


def main():
    """Main entry point for standalone execution."""
    # Configure UTF-8 output for Windows
    sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description="AI Market Analyzer - 3-Round Analysis Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python morning_view/ai_market_analyzer.py --date 2025-10-13
  python morning_view/ai_market_analyzer.py --date 2025-10-13 --output results.json
  python morning_view/ai_market_analyzer.py --date 2025-10-13 --db data/datalake_query.db
  python morning_view/ai_market_analyzer.py --date 2025-10-13 --force-refresh  # Skip cache check
        """
    )
    parser.add_argument("--date", required=True, help="Date to analyze (YYYY-MM-DD)")
    parser.add_argument("--db", default="data/datalake_query.db", help="Database path (default: data/datalake_query.db)")
    parser.add_argument("--output", help="Output JSON file path (optional)")
    parser.add_argument("--logs-dir", default="morning_view/logs", help="Directory for detailed logs (default: morning_view/logs)")
    parser.add_argument("--force-refresh", action="store_true", help="Force fresh analysis, skip cache check")
    parser.add_argument("--use-cache", action="store_true", help="Use cached results without prompting (automation mode)")

    args = parser.parse_args()

    # Load configuration
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print("ERROR: Failed to load config.json: {}".format(str(e)))
        sys.exit(1)

    # Validate Claude API configuration
    claude_config = config.get('claude_api', {})
    if not claude_config.get('api_key'):
        print("ERROR: Claude API key not configured in config.json")
        sys.exit(1)

    # Check for cached results (unless --force-refresh)
    cache_file = os.path.join(args.logs_dir, "market_analysis_{}_rounds.json".format(args.date))
    if os.path.exists(cache_file) and not args.force_refresh:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)

            # Extract cached summary
            cached_timestamp = cached_data.get('analysis_timestamp', 'Unknown')
            cached_cost = cached_data.get('total_cost', 0)
            cached_tokens = cached_data.get('total_tokens', 0)

            # Get Round 4 synthesis if available
            round_4_data = cached_data.get('rounds', {}).get('round_4', {})
            cached_synthesis = round_4_data.get('response', 'No synthesis available')

            # Try to parse as JSON for better display
            try:
                synthesis_json = json.loads(cached_synthesis)
                cached_summary = synthesis_json.get('market_environment_summary', 'N/A')
            except:
                cached_summary = cached_synthesis[:100] + "..." if len(cached_synthesis) > 100 else cached_synthesis

            # Display cached analysis info
            print("\n" + "=" * 80)
            print("CACHED ANALYSIS FOUND - {}".format(args.date))
            print("=" * 80)
            print("Timestamp: {}".format(cached_timestamp))
            print("Cost: ${:.4f} | Tokens: {}".format(cached_cost, cached_tokens))
            print("\nSummary Preview:")
            print("  {}".format(cached_summary))
            print("=" * 80)

            # Prompt user (or auto-select if --use-cache)
            if args.use_cache:
                print("\n✓ Auto-using cached results (--use-cache flag)\n")
                choice = "1"
            else:
                print("\nOptions:")
                print("  1. Use cached results (free, instant)")
                print("  2. Run fresh analysis (~$0.0017, 30-60 seconds)")
                choice = input("\nChoice (1/2): ").strip()

            if choice == "1":
                print("\n✓ Using cached results\n")

                # Parse and display full synthesis
                try:
                    synthesis_json = json.loads(cached_synthesis)
                    result = synthesis_json
                except:
                    # If can't parse, create wrapper
                    result = {
                        'analysis_timestamp': cached_timestamp,
                        'total_cost_estimate': cached_cost,
                        'total_tokens_used': cached_tokens,
                        'market_environment_summary': cached_summary,
                        'source': 'cached'
                    }

                # Helper function to format field (handles both string and dict formats)
                def format_field(value):
                    if isinstance(value, dict):
                        return json.dumps(value, indent=4)
                    return str(value)

                # Display cached results
                print("=" * 80)
                print("MARKET ANALYSIS SUMMARY - {} (CACHED)".format(args.date))
                print("=" * 80)
                print("\nMarket Environment:")
                print("  {}".format(format_field(result.get('market_environment_summary', 'N/A'))))
                print("\nMomentum & Trends:")
                print("  {}".format(format_field(result.get('momentum_and_trends', 'N/A'))))
                print("\nKey Nuances:")
                print("  {}".format(format_field(result.get('key_nuances_discovered', 'N/A'))))
                print("\nTrading Implications:")
                print("  {}".format(format_field(result.get('trading_implications', 'N/A'))))
                print("\nConfidence Assessment:")
                print("  {}".format(format_field(result.get('confidence_assessment', 'N/A'))))
                print("\nCost: $0.00 (cached) | Original cost: ${:.4f}".format(cached_cost))
                print("=" * 80)

                # Save to output file if specified
                if args.output:
                    with open(args.output, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2)
                    print("\nCached analysis saved to: {}".format(args.output))

                sys.exit(0)
            else:
                print("\n✓ Running fresh analysis...\n")

        except Exception as e:
            print("WARNING: Failed to load cached results: {}".format(str(e)))
            print("Proceeding with fresh analysis...\n")

    # Initialize analysis engine
    analysis_engine = MarketAnalysisEngine(config, logs_directory=args.logs_dir)

    # Connect to database and run analysis
    try:
        with sqlite3.connect(args.db) as conn:
            result = analysis_engine.conduct_full_analysis(conn, args.date)

            # Print summary to console
            print("\n" + "=" * 80)
            print("MARKET ANALYSIS SUMMARY - {}".format(args.date))
            print("=" * 80)
            print("\nMarket Environment:")
            print("  {}".format(result.get('market_environment_summary', 'N/A')))
            print("\nMomentum & Trends:")
            print("  {}".format(result.get('momentum_and_trends', 'N/A')))
            print("\nKey Nuances:")
            print("  {}".format(result.get('key_nuances_discovered', 'N/A')))
            print("\nTrading Implications:")
            print("  {}".format(result.get('trading_implications', 'N/A')))
            print("\nConfidence Assessment:")
            print("  {}".format(result.get('confidence_assessment', 'N/A')))
            print("\nCost: ${:.4f} | Tokens: {}".format(
                result.get('total_cost_estimate', 0),
                result.get('total_tokens_used', 0)
            ))
            print("=" * 80)

            # Save to output file if specified
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2)
                print("\nFull analysis saved to: {}".format(args.output))

            # Return success/failure based on analysis status
            if result.get('analysis_status') == 'failed':
                sys.exit(1)
            else:
                sys.exit(0)

    except Exception as e:
        print("ERROR: Analysis failed: {}".format(str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
