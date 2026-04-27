#!/usr/bin/env python3
"""
AI Council for Morning Views TUI

Multi-advisor AI analysis system with:
- 4 specialized advisors (General, Detective, Risk, Catalyst)
- User context injection
- Stacked analysis support
- Full synthesis capability

Author: Ben
Date: 2025-10-09
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from morning_view.tui_data import get_data
from morning_view import ai_prompts
from morning_view import ai_providers
from morning_view import advisor_data

# ========== Configuration ==========

CACHE_DAYS = 7
CACHE_DB_PATH = "data/analysis_cache.db"

def load_advisor_config():
    """Load advisor configuration

    Returns:
        dict: Advisor config dictionary
    """
    config_path = Path(__file__).parent / 'advisor_config.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _get_cache_db_path():
    """Get absolute path to cache database

    Returns:
        str: Absolute path to analysis_cache.db
    """
    if not os.path.isabs(CACHE_DB_PATH):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        return os.path.join(project_root, CACHE_DB_PATH)
    return CACHE_DB_PATH

def get_cached_advisor_analysis(symbol: str, advisor_id: int):
    """Check if recent advisor analysis exists in cache

    Args:
        symbol: Stock symbol
        advisor_id: Advisor ID (1-4)

    Returns:
        dict or None: Cached analysis record if found and fresh, else None
    """
    try:
        db_path = _get_cache_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol, advisor_id, advisor_name,
                   analysis_text, model_used, provider,
                   created_at, input_tokens, output_tokens, cost_usd
            FROM advisor_analysis_cache
            WHERE symbol = ? AND advisor_id = ?
        """, (symbol, advisor_id))

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
            'analysis_text': row['analysis_text'],
            'model_used': row['model_used'],
            'provider': row['provider'],
            'created_at': row['created_at'],
            'input_tokens': row['input_tokens'],
            'output_tokens': row['output_tokens'],
            'cost_usd': row['cost_usd'],
            'age_days': age_days,
            'from_cache': True
        }

    except Exception as e:
        print(f"Warning: Cache check failed: {e}")
        return None

def cache_advisor_analysis(symbol: str, advisor_id: int, advisor_name: str,
                          analysis_text: str, model_used: str, provider: str,
                          input_tokens: int, output_tokens: int, cost_usd: float):
    """Store advisor analysis in cache

    Args:
        symbol: Stock symbol
        advisor_id: Advisor ID (1-4)
        advisor_name: Advisor name
        analysis_text: Analysis markdown text
        model_used: Model identifier
        provider: Provider name
        input_tokens: Input token count
        output_tokens: Output token count
        cost_usd: Cost in USD

    Returns:
        bool: True if cached successfully
    """
    try:
        db_path = _get_cache_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        # Delete old analysis for this symbol/advisor
        cursor.execute("""
            DELETE FROM advisor_analysis_cache
            WHERE symbol = ? AND advisor_id = ?
        """, (symbol, advisor_id))

        # Insert new analysis
        cursor.execute("""
            INSERT INTO advisor_analysis_cache
            (symbol, advisor_id, advisor_name, analysis_text, model_used, provider,
             created_at, input_tokens, output_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, advisor_id, advisor_name, analysis_text, model_used, provider,
              now, input_tokens, output_tokens, cost_usd))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"Warning: Cache write failed: {e}")
        return False

# ========== Advisor Class ==========

class Advisor:
    """Individual AI advisor with specialization"""

    def __init__(self, config: dict):
        """Initialize advisor from config

        Args:
            config: Advisor config dict from advisor_config.json
        """
        self.id = config['id']
        self.name = config['name']
        self.provider = config['provider']
        self.model = config['model']
        self.personality = config['personality']
        self.role = config['role']
        self.focus_tables = config['focus_tables']
        self.system_prompt_addition = config['system_prompt_addition']
        self.max_tokens = config['max_tokens']
        self.cost_estimate = config['cost_estimate']

        # Analysis history for this advisor (in-memory, per session)
        self.analysis_history = []

    def build_system_prompt(self, base_prompt: str) -> str:
        """Build complete system prompt with advisor personality

        Args:
            base_prompt: Base system prompt from ai_prompts.py

        Returns:
            str: Complete system prompt
        """
        return f"{base_prompt}\n\n## ADVISOR ROLE\n{self.system_prompt_addition}"

    def build_user_prompt(self, symbol: str, data: dict, user_context: str = "", latest_synthesis: Optional[Dict] = None) -> str:
        """Build user prompt with data and optional user context

        Args:
            symbol: Stock symbol
            data: Dict from advisor_data.gather_advisor_data()
            user_context: Optional user-provided context
            latest_synthesis: Latest consensus synthesis (if available)

        Returns:
            str: Complete user prompt
        """
        # Build base prompt from morning views data
        overview = data['overview']
        oi_dist = data['oi_distribution']
        market_ctx = data['market_context']

        prompt_parts = [f"Analyze {symbol}:\n"]

        # Add symbol overview (if available)
        if overview:
            prompt_parts.append(f"\n## SYMBOL OVERVIEW")
            prompt_parts.append(f"Price: ${overview.get('close_price', 0):.2f}")
            prompt_parts.append(f"Sector: {overview.get('sector', 'Unknown')}")
            prompt_parts.append(f"Confluence Score: {overview.get('confluence_score', 0)}/5")
            prompt_parts.append(f"Direction Bias: {overview.get('direction_bias', 'N/A')}")
            prompt_parts.append(f"Conviction: {overview.get('conviction_level', 'N/A')}")

        # Add market context
        if market_ctx:
            prompt_parts.append(f"\n## MARKET CONTEXT")
            prompt_parts.append(f"Direction: {market_ctx.get('market_direction', 'Unknown')}")
            prompt_parts.append(f"Regime: {market_ctx.get('market_regime', 'Unknown')}")

        # Add OI summary (if available)
        if oi_dist:
            total_oi = oi_dist.get('total_call_oi', 0) + oi_dist.get('total_put_oi', 0)
            prompt_parts.append(f"\n## OI SUMMARY")
            prompt_parts.append(f"Total OI: {total_oi:,}")
            prompt_parts.append(f"Put/Call Ratio: {oi_dist.get('put_call_ratio', 0):.2f}")

        # Add schema context if available
        if data.get('schema_context'):
            prompt_parts.append(f"\n## DATA SCHEMA REFERENCE")
            prompt_parts.append(data['schema_context'])

        # Add advisor-specific additional data
        additional = data.get('additional_data', {})
        if additional:
            prompt_parts.append(f"\n## SPECIALIZED DATA FOR YOUR ANALYSIS")

            # Flow alerts
            if 'flow_alerts' in additional:
                prompt_parts.append(f"\n### Flow Alerts (Last 30 Days):")
                prompt_parts.append(advisor_data.format_flow_alerts(additional['flow_alerts']))

            # High quality alerts
            if 'high_quality_alerts' in additional:
                prompt_parts.append(f"\n### High-Quality Alerts (Sig ≥7.0, Last 14 Days):")
                prompt_parts.append(advisor_data.format_flow_alerts(additional['high_quality_alerts']))

            # Tracked contracts
            if 'tracked_contracts' in additional:
                prompt_parts.append(f"\n### Tracked Contracts:")
                prompt_parts.append(advisor_data.format_tracked_contracts(additional['tracked_contracts']))

            # Option chain summary (available expirations/strikes)
            if 'available_expirations' in additional:
                prompt_parts.append(f"\n### Available Option Expirations:")
                prompt_parts.append(f"  {', '.join(additional['available_expirations'])}")
            if 'option_chain_summary' in additional:
                prompt_parts.append(f"\n### Option Chain Summary:")
                for chain in additional['option_chain_summary']:
                    prompt_parts.append(f"  {chain['expiration_date']}: Strikes {chain['strikes']}")
                prompt_parts.append("\nIMPORTANT: Only recommend strikes/dates that exist in the data above. Never invent expiration dates.")

            # Risk contracts
            if 'risk_contracts' in additional:
                prompt_parts.append(f"\n### Contracts with Risk Metrics:")
                prompt_parts.append(advisor_data.format_risk_contracts(additional['risk_contracts']))

            # News sentiment
            if 'news_sentiment' in additional:
                prompt_parts.append(f"\n### News & Sentiment (Last 14 Days):")
                prompt_parts.append(advisor_data.format_news_sentiment(additional['news_sentiment']))

            # News articles
            if 'news_articles' in additional:
                prompt_parts.append(f"\n### Recent News Articles:")
                prompt_parts.append(advisor_data.format_news_articles(additional['news_articles']))

            # Earnings
            if 'earnings_info' in additional and additional['earnings_info']:
                e = additional['earnings_info']
                prompt_parts.append(f"\n### Earnings:")
                prompt_parts.append(f"  Date: {e['earnings_date']} ({e['earnings_days_ahead']} days ahead)")
                prompt_parts.append(f"  Expected Move: {e['straddle_expected_move_pct']:.1f}%")
                prompt_parts.append(f"  Historical Avg: {e['historical_avg_move_pct']:.1f}%")
                prompt_parts.append(f"  Signal: {e['earnings_play_signal']}")

        # Add user context if provided
        if user_context:
            prompt_parts.append(f"\n## USER FOCUS")
            prompt_parts.append(user_context)

        # Add latest consensus synthesis if available
        if latest_synthesis and latest_synthesis.get('symbol') == symbol:
            prompt_parts.append(f"\n## LATEST CONSENSUS SYNTHESIS")
            prompt_parts.append(f"[Generated {latest_synthesis['timestamp'][:10]} by Chief Strategist]")
            prompt_parts.append(latest_synthesis['text'])
            prompt_parts.append("\nNote: This synthesis represents the consensus view from all advisors. You cannot see other advisors' raw analyses, only this synthesized consensus. Use it as context but maintain your specialized perspective.")

        # Add previous analyses for this advisor if any
        if self.analysis_history:
            # Get last 5 actual trade dates from market_daily_summary
            config_path = Path(__file__).parent / 'config.json'
            import json
            with open(config_path, 'r') as f:
                config = json.load(f)

            db_path = Path(__file__).parent.parent / config['database']['path']
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT trade_date FROM market_daily_summary ORDER BY trade_date DESC LIMIT 5")
            last_5_trade_dates = [row[0] for row in cursor.fetchall()]
            conn.close()

            # Filter analyses to those actual trade dates only
            recent_analyses = [
                a for a in self.analysis_history
                if a['timestamp'][:10] in last_5_trade_dates
            ]

            if recent_analyses:
                # Count how many unique trade dates are represented
                unique_trade_dates = sorted(set(a['timestamp'][:10] for a in recent_analyses))

                history_text = "\n\n".join([
                    f"## PREVIOUS ANALYSIS {i+1} (from {a['timestamp'][:10]})\n{a['text']}"
                    for i, a in enumerate(recent_analyses)
                ])
                prompt_parts.append(f"\n## YOUR PREVIOUS ANALYSES")
                prompt_parts.append(f"[Showing analyses from last {len(unique_trade_dates)} trade date(s): {', '.join(unique_trade_dates)}]")
                prompt_parts.append(history_text)
                prompt_parts.append("\nNote: Build on your previous analyses. Look for new angles or data sources to add value.")

        return "\n".join(prompt_parts)

    def query(self, symbol: str, user_context: str = "", latest_synthesis: Optional[Dict] = None, force_refresh: bool = False) -> Tuple[str, Dict]:
        """Query this advisor for analysis

        Args:
            symbol: Stock symbol
            user_context: Optional user-provided context
            latest_synthesis: Latest consensus synthesis (if available)
            force_refresh: If True, bypass cache and force new analysis

        Returns:
            Tuple of (analysis_text, usage_dict)
        """
        # Load historical analyses from database on first query for this symbol
        if not self.analysis_history:
            self._load_from_db(symbol)

        # Check cache first (unless forced refresh or iterative analysis)
        if not force_refresh and not self.analysis_history:
            cached = get_cached_advisor_analysis(symbol, self.id)
            if cached:
                # Use cached analysis
                analysis_text = cached['analysis_text']
                usage = {
                    'provider': cached['provider'],
                    'model': cached['model_used'],
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'cost_usd': 0.0,
                    'from_cache': True,
                    'age_days': cached['age_days']
                }

                # Store in history
                self.analysis_history.append({
                    'timestamp': cached['created_at'],
                    'text': analysis_text,
                    'symbol': symbol,
                    'user_context': user_context,
                    'usage': usage
                })

                return analysis_text, usage

        # Gather advisor-specific data
        data = advisor_data.gather_advisor_data(self.name, symbol)
        if not data:
            raise Exception(f"No data found for symbol: {symbol}")

        # Build prompts
        system_prompt = self.build_system_prompt(ai_prompts.SYSTEM_PROMPT)
        user_prompt = self.build_user_prompt(symbol, data, user_context, latest_synthesis)

        # Calculate dynamic max_tokens (increases 20% per re-analysis to allow expansion)
        num_previous = len(self.analysis_history)
        dynamic_max_tokens = int(self.max_tokens * (1.2 ** num_previous))

        # Call AI provider
        analysis_text, usage = ai_providers.call_ai(
            provider=self.provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=self.model,
            max_tokens=dynamic_max_tokens
        )

        # Cache result (only if first analysis for this advisor/symbol)
        if not self.analysis_history:
            cache_advisor_analysis(
                symbol=symbol,
                advisor_id=self.id,
                advisor_name=self.name,
                analysis_text=analysis_text,
                model_used=usage['model'],
                provider=usage['provider'],
                input_tokens=usage['input_tokens'],
                output_tokens=usage['output_tokens'],
                cost_usd=usage['cost_usd']
            )

        # Store in history
        from tools.timezone_utils import now_eastern

        analysis_entry = {
            'timestamp': now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            'text': analysis_text,
            'symbol': symbol,
            'user_context': user_context,
            'usage': usage
        }
        self.analysis_history.append(analysis_entry)

        # Save to database for cross-session persistence
        self._save_to_db(symbol, analysis_entry)

        return analysis_text, usage

    def _save_to_db(self, symbol: str, analysis_entry: dict):
        """Save analysis to database for persistence

        Args:
            symbol: Stock symbol
            analysis_entry: Analysis dict with timestamp, text, usage
        """
        import json
        from pathlib import Path

        # Get database path
        cache_db = Path(__file__).parent.parent / 'data' / 'analysis_cache.db'

        # Map advisor ID to column name
        column_map = {
            1: 'general_analyst',
            2: 'detective',
            3: 'risk_analyst',
            4: 'catalyst_hunter'
        }
        column_name = column_map.get(self.id)
        if not column_name:
            return

        # Get today's trade date
        from tools.timezone_utils import now_eastern
        trade_date = now_eastern().strftime('%Y-%m-%d')

        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Check if row exists
        cursor.execute(
            f"SELECT {column_name} FROM symbol_ai_council WHERE symbol = ? AND trade_date = ?",
            (symbol, trade_date)
        )
        row = cursor.fetchone()

        # Prepare analysis data (minimal - just timestamp and text)
        analysis_data = {
            'timestamp': analysis_entry['timestamp'],
            'text': analysis_entry['text']
        }

        # Get cost for this analysis (round to 4 decimals)
        cost = round(analysis_entry.get('usage', {}).get('cost_usd', 0.0), 4)

        if row and row[0]:
            # Row exists - append to existing array and increment cost
            existing = json.loads(row[0])
            existing.append(analysis_data)
            cursor.execute(
                f"UPDATE symbol_ai_council SET {column_name} = ?, total_cost = total_cost + ?, updated_at = ? WHERE symbol = ? AND trade_date = ?",
                (json.dumps(existing), cost, now_eastern().strftime('%Y-%m-%d %H:%M:%S'), symbol, trade_date)
            )
        else:
            # No row or column is NULL - create new or update
            if row:
                # Row exists but column is NULL
                cursor.execute(
                    f"UPDATE symbol_ai_council SET {column_name} = ?, total_cost = total_cost + ?, updated_at = ? WHERE symbol = ? AND trade_date = ?",
                    (json.dumps([analysis_data]), cost, now_eastern().strftime('%Y-%m-%d %H:%M:%S'), symbol, trade_date)
                )
            else:
                # No row - insert new
                now_str = now_eastern().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(
                    "INSERT INTO symbol_ai_council (symbol, trade_date, created_at, updated_at, total_cost, {}) VALUES (?, ?, ?, ?, ?, ?)".format(column_name),
                    (symbol, trade_date, now_str, now_str, cost, json.dumps([analysis_data]))
                )

        conn.commit()
        conn.close()

    def _load_from_db(self, symbol: str):
        """Load historical analyses from database

        Args:
            symbol: Stock symbol
        """
        import json
        from pathlib import Path

        # Get database path
        cache_db = Path(__file__).parent.parent / 'data' / 'analysis_cache.db'

        # Map advisor ID to column name
        column_map = {
            1: 'general_analyst',
            2: 'detective',
            3: 'risk_analyst',
            4: 'catalyst_hunter'
        }
        column_name = column_map.get(self.id)
        if not column_name:
            return

        # Get today's trade date
        from tools.timezone_utils import now_eastern
        trade_date = now_eastern().strftime('%Y-%m-%d')

        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Load analyses for this symbol and advisor from today
        cursor.execute(
            f"SELECT {column_name} FROM symbol_ai_council WHERE symbol = ? AND trade_date = ?",
            (symbol, trade_date)
        )
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            # Parse JSON array and load into analysis_history
            analyses = json.loads(row[0])
            for analysis in analyses:
                self.analysis_history.append({
                    'timestamp': analysis['timestamp'],
                    'text': analysis['text'],
                    'symbol': symbol,
                    'user_context': '',  # Not stored in DB
                    'usage': {'cost_usd': 0.0}  # Not stored in DB
                })

    def clear_history(self):
        """Clear analysis history for this advisor"""
        self.analysis_history = []

    def get_total_cost(self) -> float:
        """Get total cost for this advisor session

        Returns:
            float: Total USD cost
        """
        return sum(a['usage']['cost_usd'] for a in self.analysis_history)

    def get_analysis_count(self) -> int:
        """Get number of analyses performed

        Returns:
            int: Number of analyses
        """
        return len(self.analysis_history)


# ========== Council Manager ==========

class CouncilManager:
    """Manages the AI Council"""

    def __init__(self):
        """Initialize council with advisors from config"""
        config = load_advisor_config()
        self.advisors = [Advisor(adv_config) for adv_config in config['advisors']]
        self.synthesis_models = config['synthesis_models']
        self.guidelines = config['analysis_guidelines']

        # User context (persists across queries)
        self.user_context = ""

        # Latest synthesis result (shared with advisors as consensus view)
        self.latest_synthesis = None

    def get_advisor(self, advisor_id: int) -> Optional[Advisor]:
        """Get advisor by ID

        Args:
            advisor_id: Advisor ID (1-4)

        Returns:
            Advisor instance or None
        """
        for advisor in self.advisors:
            if advisor.id == advisor_id:
                return advisor
        return None

    def set_user_context(self, context: str):
        """Set user context for all future queries

        Args:
            context: User-provided context/focus
        """
        self.user_context = context

    def clear_user_context(self):
        """Clear user context"""
        self.user_context = ""

    def query_advisor(self, advisor_id: int, symbol: str) -> Tuple[str, Dict]:
        """Query specific advisor

        Args:
            advisor_id: Advisor ID (1-4)
            symbol: Stock symbol

        Returns:
            Tuple of (analysis_text, usage_dict)
        """
        advisor = self.get_advisor(advisor_id)
        if not advisor:
            raise Exception(f"Advisor {advisor_id} not found")

        return advisor.query(symbol, self.user_context, self.latest_synthesis)

    def remove_advisor_history(self, advisor_id: int):
        """Clear analysis history for specific advisor

        Args:
            advisor_id: Advisor ID (1-4)
        """
        advisor = self.get_advisor(advisor_id)
        if advisor:
            advisor.clear_history()

    def synthesize(self, symbol: str, model: str = 'sonnet') -> Tuple[str, Dict]:
        """Create comprehensive synthesis from all advisor outputs

        Args:
            symbol: Stock symbol
            model: Synthesis model ('sonnet', 'opus', 'gemini-pro')

        Returns:
            Tuple of (synthesis_text, usage_dict)
        """
        # Load previous synthesis for this symbol if not already loaded
        if not self.latest_synthesis or self.latest_synthesis.get('symbol') != symbol:
            self._load_synthesis_from_db(symbol)

        # Gather all advisor analyses
        advisor_outputs = []
        for advisor in self.advisors:
            if advisor.analysis_history:
                latest = advisor.analysis_history[-1]
                advisor_outputs.append({
                    'advisor': advisor.name,
                    'role': advisor.role,
                    'analysis': latest['text']
                })

        if not advisor_outputs:
            raise Exception("No advisor analyses available for synthesis")

        # Get synthesis model config
        synth_config = self.synthesis_models.get(model)
        if not synth_config:
            raise Exception(f"Unknown synthesis model: {model}")

        # Build synthesis prompt
        system_prompt = self._build_synthesis_system_prompt()
        user_prompt = self._build_synthesis_user_prompt(symbol, advisor_outputs)

        # Call synthesis model
        synthesis_text, usage = ai_providers.call_ai(
            provider=synth_config['provider'],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=synth_config['model'],
            max_tokens=synth_config['max_tokens']
        )

        # Store latest synthesis (will be shared with advisors on next query)
        from tools.timezone_utils import now_eastern

        self.latest_synthesis = {
            'symbol': symbol,
            'text': synthesis_text,
            'timestamp': now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
            'model': model,
            'cost_usd': usage.get('cost_usd', 0.0)
        }

        # Save synthesis to database
        self._save_synthesis_to_db(symbol, self.latest_synthesis)

        return synthesis_text, usage

    def _build_synthesis_system_prompt(self) -> str:
        """Build system prompt for synthesis"""
        return """You are the Chief Strategist synthesizing multiple AI advisor analyses.

Your role:
1. Review all advisor perspectives (General, Detective, Risk, Catalyst)
2. Identify consensus views and key disagreements
3. Weigh evidence quality and advisor specializations
4. Produce actionable trade thesis with specific recommendations

Output Structure:
## Executive Summary
2-3 sentence bottom line

## Consensus View
What advisors agree on

## Key Disagreements
Where advisors differ and why

## Trade Thesis
Specific recommendation with strikes, dates, position size

## Risk Assessment
What could go wrong

## Final Verdict
Clear buy/pass decision with confidence level

Remember: Only recommend BUYING calls or puts (no spreads, no selling). Position size <$300. Target 25% gain. Swing trading timeframe (2-4 weeks)."""

    def _build_synthesis_user_prompt(self, symbol: str, advisor_outputs: List[Dict]) -> str:
        """Build user prompt for synthesis

        Args:
            symbol: Stock symbol
            advisor_outputs: List of advisor analysis dicts

        Returns:
            str: Synthesis prompt
        """
        prompt_parts = [f"Synthesize the following analyses for {symbol}:\n"]

        for output in advisor_outputs:
            prompt_parts.append(f"\n{'='*60}")
            prompt_parts.append(f"## {output['advisor']} ({output['role']})")
            prompt_parts.append(f"{'='*60}\n")
            prompt_parts.append(output['analysis'])

        if self.user_context:
            prompt_parts.append(f"\n\n{'='*60}")
            prompt_parts.append(f"USER FOCUS: {self.user_context}")
            prompt_parts.append(f"{'='*60}")

        return "\n".join(prompt_parts)

    def _save_synthesis_to_db(self, symbol: str, synthesis: dict):
        """Save synthesis to database

        Args:
            symbol: Stock symbol
            synthesis: Synthesis dict with timestamp, text, model
        """
        import json
        from pathlib import Path
        from tools.timezone_utils import now_eastern

        # Get database path
        cache_db = Path(__file__).parent.parent / 'data' / 'analysis_cache.db'
        trade_date = now_eastern().strftime('%Y-%m-%d')

        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Check if row exists
        cursor.execute(
            "SELECT synthesis FROM symbol_ai_council WHERE symbol = ? AND trade_date = ?",
            (symbol, trade_date)
        )
        row = cursor.fetchone()

        # Prepare synthesis data
        synthesis_data = {
            'timestamp': synthesis['timestamp'],
            'text': synthesis['text'],
            'model': synthesis['model']
        }

        # Get cost for this synthesis (round to 4 decimals)
        cost = round(synthesis.get('cost_usd', 0.0), 4)

        if row and row[0]:
            # Row exists - append to existing array and increment cost
            existing = json.loads(row[0])
            existing.append(synthesis_data)
            cursor.execute(
                "UPDATE symbol_ai_council SET synthesis = ?, total_cost = total_cost + ?, updated_at = ? WHERE symbol = ? AND trade_date = ?",
                (json.dumps(existing), cost, now_eastern().strftime('%Y-%m-%d %H:%M:%S'), symbol, trade_date)
            )
        else:
            # No row or column is NULL
            if row:
                # Row exists but synthesis column is NULL
                cursor.execute(
                    "UPDATE symbol_ai_council SET synthesis = ?, total_cost = total_cost + ?, updated_at = ? WHERE symbol = ? AND trade_date = ?",
                    (json.dumps([synthesis_data]), cost, now_eastern().strftime('%Y-%m-%d %H:%M:%S'), symbol, trade_date)
                )
            else:
                # No row - insert new
                now_str = now_eastern().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(
                    "INSERT INTO symbol_ai_council (symbol, trade_date, created_at, updated_at, total_cost, synthesis) VALUES (?, ?, ?, ?, ?, ?)",
                    (symbol, trade_date, now_str, now_str, cost, json.dumps([synthesis_data]))
                )

        conn.commit()
        conn.close()

    def _load_synthesis_from_db(self, symbol: str):
        """Load previous synthesis from database

        Args:
            symbol: Stock symbol
        """
        import json
        from pathlib import Path
        from tools.timezone_utils import now_eastern

        # Get database path
        cache_db = Path(__file__).parent.parent / 'data' / 'analysis_cache.db'
        trade_date = now_eastern().strftime('%Y-%m-%d')

        conn = sqlite3.connect(str(cache_db))
        cursor = conn.cursor()

        # Load synthesis for this symbol from today
        cursor.execute(
            "SELECT synthesis FROM symbol_ai_council WHERE symbol = ? AND trade_date = ?",
            (symbol, trade_date)
        )
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            # Parse JSON array and load the latest synthesis
            syntheses = json.loads(row[0])
            if syntheses:
                latest = syntheses[-1]  # Get most recent
                self.latest_synthesis = {
                    'symbol': symbol,
                    'text': latest['text'],
                    'timestamp': latest['timestamp'],
                    'model': latest.get('model', 'unknown')
                }

    def get_total_cost(self) -> float:
        """Get total cost across all advisors

        Returns:
            float: Total USD cost
        """
        return sum(advisor.get_total_cost() for advisor in self.advisors)

    def get_session_summary(self) -> Dict:
        """Get summary of council session

        Returns:
            dict: Session summary with costs per advisor
        """
        return {
            'total_cost': self.get_total_cost(),
            'user_context': self.user_context,
            'advisors': [
                {
                    'id': advisor.id,
                    'name': advisor.name,
                    'analyses': advisor.get_analysis_count(),
                    'cost': advisor.get_total_cost()
                }
                for advisor in self.advisors
            ]
        }


# ========== CLI Testing ==========

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test AI Council')
    parser.add_argument('symbol', help='Stock symbol')
    parser.add_argument('--advisor', type=int, choices=[1, 2, 3, 4],
                       help='Query specific advisor (1-4)')
    parser.add_argument('--synthesize', action='store_true',
                       help='Create synthesis from all advisors')
    parser.add_argument('--context', help='User context/focus')

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"AI Council Test: {args.symbol}")
    print(f"{'='*70}\n")

    try:
        council = CouncilManager()

        if args.context:
            council.set_user_context(args.context)
            print(f"User Context: {args.context}\n")

        if args.advisor:
            # Query single advisor
            advisor = council.get_advisor(args.advisor)
            print(f"Querying: {advisor.name} ({advisor.role})")
            print(f"{'='*70}\n")

            analysis, usage = council.query_advisor(args.advisor, args.symbol)

            print(analysis)
            print(f"\n{'='*70}")
            print(f"Cost: ${usage['cost_usd']:.4f}")
            print(f"{'='*70}\n")

        elif args.synthesize:
            # Query all advisors first
            print("Querying all advisors...\n")
            for advisor in council.advisors:
                print(f"- {advisor.name}...", end=' ')
                analysis, usage = council.query_advisor(advisor.id, args.symbol)
                print(f"${usage['cost_usd']:.4f}")

            print(f"\nCreating synthesis...")
            synthesis, usage = council.synthesize(args.symbol)

            print(f"\n{'='*70}")
            print("SYNTHESIS")
            print(f"{'='*70}\n")
            print(synthesis)

            print(f"\n{'='*70}")
            summary = council.get_session_summary()
            print(f"Total Session Cost: ${summary['total_cost']:.4f}")
            print(f"{'='*70}\n")

        else:
            print("Specify --advisor N or --synthesize")

    except Exception as e:
        print(f"ERROR: {e}\n")
        sys.exit(1)
