#!/usr/bin/env python3
"""
Social Content Generator (social_content_generator.py)
------------------------------------------------------
Generates formatted social media posts for high-quality flow alerts.

Features:
- Enriches alerts with market context (regime, sector, etc.)
- Detects multi-leg strategies (strangles, spreads)
- Formats educational narrative for Reddit/Twitter
- Injects disclaimers and branding
- Supports manual context addition

Author: Ben (with assistance from Claude)
Date: 2025-10-06
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Configure UTF-8 output for Windows
sys.stdout.reconfigure(encoding='utf-8')

# Add project paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'tools'))

from tools.timezone_utils import now_eastern, eastern_timestamp_string


class SocialContentGenerator:
    """Generates enriched social media content for flow alerts"""

    def __init__(self, storage):
        """Initialize with database storage

        Args:
            storage: Database storage instance (FlowMonitorStorage or similar)
        """
        self.storage = storage
        logging.info("Social Content Generator initialized")

    def generate_post(self, alert_data, manual_context=None):
        """Generate complete social media post from alert data

        Args:
            alert_data: Alert dictionary from flow_alerts table
            manual_context: Optional manual analysis to include

        Returns:
            dict: {
                'title': Post title/subject,
                'content': Full post body,
                'platform': 'reddit' or 'twitter',
                'tags': List of hashtags/keywords
            }
        """
        # Enrich alert with context
        enriched = self._enrich_alert(alert_data)

        # Check for multi-leg setups
        multi_leg = self._detect_multi_leg(alert_data)

        # Generate title
        title = self._generate_title(enriched, multi_leg)

        # Generate content
        content = self._generate_content(enriched, multi_leg, manual_context)

        # Extract tags
        tags = self._generate_tags(enriched)

        return {
            'title': title,
            'content': content,
            'platform': 'reddit',  # Default platform
            'tags': tags,
            'enriched_data': enriched,
            'multi_leg': multi_leg
        }

    def _enrich_alert(self, alert_data):
        """Enrich alert with market context

        Args:
            alert_data: Alert dictionary

        Returns:
            dict: Enriched alert with additional context
        """
        enriched = alert_data.copy()

        symbol = alert_data.get('symbol')
        trade_date = alert_data.get('trade_date')

        # Get symbol metadata (sector, industry, market cap)
        metadata_query = '''
            SELECT sector, industry, market_cap_category, company_name
            FROM symbol_metadata
            WHERE symbol = ?
        '''
        metadata = self.storage.query_with_params(metadata_query, (symbol,))
        if metadata:
            enriched['sector'] = metadata[0].get('sector', 'Unknown')
            enriched['industry'] = metadata[0].get('industry', 'Unknown')
            enriched['market_cap'] = metadata[0].get('market_cap_category', 'Unknown')
            enriched['company_name'] = metadata[0].get('company_name', symbol)
        else:
            enriched['sector'] = 'Unknown'
            enriched['industry'] = 'Unknown'
            enriched['market_cap'] = 'Unknown'
            enriched['company_name'] = symbol

        # Get market regime data
        market_query = '''
            SELECT regime_classification, market_direction,
                   spy_change_percent, vix_close, vix_change_percent
            FROM market_daily_summary
            WHERE trade_date = ?
        '''
        market = self.storage.query_with_params(market_query, (trade_date,))
        if market:
            enriched['regime'] = market[0].get('regime_classification', 'Unknown')
            enriched['market_direction'] = market[0].get('market_direction', 'Neutral')
            enriched['spy_change'] = market[0].get('spy_change_percent', 0)
            enriched['vix_level'] = market[0].get('vix_close', 0)
        else:
            enriched['regime'] = 'Unknown'
            enriched['market_direction'] = 'Neutral'
            enriched['spy_change'] = 0
            enriched['vix_level'] = 0

        return enriched

    def _detect_multi_leg(self, alert_data):
        """Detect if this alert is part of a multi-leg strategy

        Looks for other alerts on same symbol within 5 minutes

        Args:
            alert_data: Alert dictionary

        Returns:
            dict or None: Multi-leg info if detected
        """
        symbol = alert_data.get('symbol')
        alert_timestamp = alert_data.get('alert_timestamp')
        strike = alert_data.get('strike')
        option_type = alert_data.get('option_type')

        # Query for related alerts within 5 minutes
        query = '''
            SELECT strike, option_type, premium_value, volume, expiration_date
            FROM flow_alerts
            WHERE symbol = ?
                AND alert_timestamp >= datetime(?, '-5 minutes')
                AND alert_timestamp <= datetime(?, '+5 minutes')
                AND (strike != ? OR option_type != ?)
            ORDER BY alert_timestamp
        '''

        related = self.storage.query_with_params(
            query,
            (symbol, alert_timestamp, alert_timestamp, strike, option_type)
        )

        if not related:
            return None

        # Analyze relationship
        all_legs = [alert_data] + list(related)

        # Check for strangle (put + call, different strikes)
        calls = [leg for leg in all_legs if leg.get('option_type') == 'call']
        puts = [leg for leg in all_legs if leg.get('option_type') == 'put']

        if len(calls) >= 1 and len(puts) >= 1:
            total_premium = sum(leg.get('premium_value', 0) for leg in all_legs)
            return {
                'type': 'strangle',
                'legs': len(all_legs),
                'total_premium': total_premium,
                'description': f"${total_premium/1e6:.1f}M strangle ({len(puts)} put{'s' if len(puts) > 1 else ''}, {len(calls)} call{'s' if len(calls) > 1 else ''})"
            }

        # Check for spread (same type, different strikes)
        if len(all_legs) >= 2:
            strikes = sorted([leg.get('strike') for leg in all_legs])
            if len(set([leg.get('option_type') for leg in all_legs])) == 1:
                total_premium = sum(leg.get('premium_value', 0) for leg in all_legs)
                opt_type = all_legs[0].get('option_type')
                return {
                    'type': 'spread',
                    'legs': len(all_legs),
                    'total_premium': total_premium,
                    'description': f"${total_premium/1e6:.1f}M {opt_type} spread (${strikes[0]}-${strikes[-1]})"
                }

        return None

    def _generate_title(self, enriched, multi_leg):
        """Generate post title

        Args:
            enriched: Enriched alert data
            multi_leg: Multi-leg detection results

        Returns:
            str: Post title
        """
        symbol = enriched.get('symbol')

        if multi_leg:
            return f"🎯 Unusual Options Flow: ${symbol} - {multi_leg['description']}"
        else:
            strike = enriched.get('strike')
            option_type = enriched.get('option_type', '').upper()
            premium = enriched.get('premium_value', 0) / 1e6

            return f"🎯 Unusual Options Flow: ${symbol} - ${premium:.1f}M {option_type} Position"

    def _generate_content(self, enriched, multi_leg, manual_context):
        """Generate full post content

        Args:
            enriched: Enriched alert data
            multi_leg: Multi-leg detection results
            manual_context: Optional manual analysis

        Returns:
            str: Formatted post content
        """
        # Extract data
        symbol = enriched.get('symbol')
        company_name = enriched.get('company_name', symbol)
        strike = enriched.get('strike')
        option_type = enriched.get('option_type', '').upper()
        exp_date = enriched.get('expiration_date')
        volume = enriched.get('volume', 0)
        premium = enriched.get('premium_value', 0)
        volume_surprise = enriched.get('volume_surprise_factor', 0)
        alert_timestamp = enriched.get('alert_timestamp')

        # Market context
        sector = enriched.get('sector', 'Unknown')
        market_cap = enriched.get('market_cap', 'Unknown')
        regime = enriched.get('regime', 'Unknown')
        market_direction = enriched.get('market_direction', 'Neutral')

        # Format timestamp
        try:
            dt = datetime.fromisoformat(alert_timestamp.replace(' ', 'T'))
            time_str = dt.strftime('%I:%M %p').lstrip('0')
        except:
            time_str = "Today"

        # Build content sections
        sections = []

        # Header
        sections.append(f"⏰ **Detected:** {time_str} ET (Live Detection)\n")

        # The Flow section
        sections.append("📊 **The Flow:**")

        if multi_leg:
            sections.append(f"• **Strategy:** {multi_leg['description']}")
            sections.append(f"• **Total Premium:** ${premium/1e6:.1f}M")
            sections.append(f"• **Primary Leg:** ${strike} {option_type} | Exp: {exp_date}")
        else:
            sections.append(f"• **Strike/Type:** ${strike} {option_type} | Exp: {exp_date}")
            sections.append(f"• **Volume:** {volume:,} contracts ({volume_surprise:.1f}x normal)")
            sections.append(f"• **Premium:** ${premium/1e6:.1f}M")

        sections.append("")

        # Market Context section
        sections.append("💡 **Market Context:**")
        sections.append(f"• **Company:** {company_name}")
        sections.append(f"• **Sector:** {sector} | **Market Cap:** {market_cap.capitalize()}")
        sections.append(f"• **Market Regime:** {regime.replace('_', ' ').title()}")

        if manual_context:
            sections.append(f"\n**Analysis:**\n{manual_context}")

        sections.append("")

        # Why It Matters section
        sections.append("🎯 **Why It Matters:**")

        # Generate intelligent interpretation
        interpretation = self._generate_interpretation(enriched, multi_leg)
        sections.append(interpretation)

        sections.append("")

        # Disclaimer
        sections.append("⚠️ **Disclaimer:** Educational analysis only. Not financial advice.")
        sections.append("Options involve significant risk. Do your own research.\n")

        # Footer
        sections.append("---")
        sections.append("*Daily flow analysis | Follow for early institutional positioning insights*")

        return '\n'.join(sections)

    def _generate_interpretation(self, enriched, multi_leg):
        """Generate intelligent interpretation of the flow

        Args:
            enriched: Enriched alert data
            multi_leg: Multi-leg detection results

        Returns:
            str: Interpretation text
        """
        interpretations = []

        volume_surprise = enriched.get('volume_surprise_factor', 0)
        premium = enriched.get('premium_value', 0)
        option_type = enriched.get('option_type', '').lower()

        # Multi-leg interpretation
        if multi_leg:
            if multi_leg['type'] == 'strangle':
                interpretations.append(
                    f"Large volatility play suggesting expectation of significant price movement in either direction. "
                    f"With ${multi_leg['total_premium']/1e6:.1f}M in combined premium, this represents substantial "
                    f"institutional positioning ahead of a potential catalyst."
                )
            elif multi_leg['type'] == 'spread':
                interpretations.append(
                    f"Structured {option_type} spread indicating defined-risk directional positioning. "
                    f"The ${multi_leg['total_premium']/1e6:.1f}M commitment suggests institutional hedging or "
                    f"high-conviction directional bias with risk management."
                )
        else:
            # Single-leg interpretation
            if volume_surprise > 50:
                interpretations.append(
                    f"Extremely unusual volume ({volume_surprise:.0f}x normal) suggests aggressive positioning. "
                )
            elif volume_surprise > 10:
                interpretations.append(
                    f"Significant volume spike ({volume_surprise:.0f}x normal) indicates elevated interest. "
                )

            if premium > 10e6:
                interpretations.append(
                    f"The ${premium/1e6:.1f}M premium suggests institutional-scale activity, "
                    f"not retail flow. "
                )

            # Directional interpretation
            if option_type == 'call':
                interpretations.append(
                    "Large call buying could indicate bullish positioning, hedging short equity, or volatility plays."
                )
            else:
                interpretations.append(
                    "Significant put activity could signal downside protection, bearish positioning, or portfolio hedging."
                )

        return ' '.join(interpretations)

    def _generate_tags(self, enriched):
        """Generate relevant tags/hashtags

        Args:
            enriched: Enriched alert data

        Returns:
            list: List of tags
        """
        tags = []

        symbol = enriched.get('symbol')
        sector = enriched.get('sector', '')

        tags.append(symbol)
        tags.append('options')
        tags.append('unusual_activity')

        if sector and sector != 'Unknown':
            tags.append(sector.lower().replace(' ', '_'))

        return tags

    def format_for_x(self, alert_data, max_chars=280):
        """Format flow alert as a single X (Twitter) post (<= max_chars).

        Reuses _enrich_alert() and _detect_multi_leg() from the Reddit pipeline
        but produces plain-text output without markdown, emoji, or disclaimers
        (those live in the account bio).

        Format (single-leg):
            $SYMBOL - unusual call activity

            $32C 5/15/26 | 12,500 contracts (45x avg) | $2.5M premium
            Tech / Large cap / Bull regime

            2:14 PM ET

        Format (multi-leg):
            $SYMBOL - multi-leg activity

            $2.5M strangle (1 put, 1 call) | exp 5/15/26
            Tech / Large cap / Bull regime

            2:14 PM ET

        If the full message exceeds max_chars, the context line is dropped first,
        then the time line. Returns None if even headline + detail won't fit.

        Args:
            alert_data: Alert dict from flow_alerts.
            max_chars: Hard limit. Default 280 (X tweet limit).

        Returns:
            str <= max_chars, or None if it can't fit.
        """
        enriched = self._enrich_alert(alert_data)
        multi_leg = self._detect_multi_leg(alert_data)

        symbol = enriched.get('symbol', '?')
        option_type = (enriched.get('option_type') or '').lower()

        if multi_leg:
            headline = f"${symbol} - multi-leg activity"
            exp_short = self._fmt_exp(enriched.get('expiration_date'))
            detail = multi_leg.get('description', '')
            if exp_short:
                detail = f"{detail} | exp {exp_short}"
        else:
            action = "call" if option_type == 'call' else "put"
            headline = f"${symbol} - unusual {action} activity"

            strike_str = self._fmt_strike(enriched.get('strike'))
            opt_letter = 'C' if option_type == 'call' else 'P'
            exp_short = self._fmt_exp(enriched.get('expiration_date'))
            volume = enriched.get('volume') or 0
            volume_surprise = enriched.get('volume_surprise_factor') or 0
            premium = enriched.get('premium_value') or 0

            vol_str = f"{volume:,} contracts"
            if volume_surprise > 0:
                vol_str += f" ({volume_surprise:.0f}x avg)"

            detail = (
                f"{strike_str}{opt_letter} {exp_short} | "
                f"{vol_str} | "
                f"{self._fmt_premium(premium)} premium"
            )

        context_parts = []
        sector = enriched.get('sector')
        if sector and sector != 'Unknown':
            context_parts.append(sector)
        market_cap = enriched.get('market_cap')
        if market_cap and market_cap != 'Unknown':
            cap_str = market_cap.replace('_', ' ').title()
            if 'cap' not in cap_str.lower():
                cap_str = f"{cap_str} cap"
            context_parts.append(cap_str)
        regime = enriched.get('regime')
        if regime and regime != 'Unknown':
            context_parts.append(f"{regime.replace('_', ' ').title()} regime")
        context_line = " / ".join(context_parts) if context_parts else None

        time_line = self._fmt_alert_time(enriched.get('alert_timestamp'))

        def _build(include_context, include_time):
            lines = [headline, "", detail]
            if include_context and context_line:
                lines.append(context_line)
            if include_time and time_line:
                lines.extend(["", time_line])
            return "\n".join(lines)

        for ctx, tm in [(True, True), (False, True), (True, False), (False, False)]:
            tweet = _build(ctx, tm)
            if len(tweet) <= max_chars:
                return tweet

        return None

    @staticmethod
    def _fmt_premium(value):
        """Format premium as $X.XM, $XXXK, or $XX,XXX."""
        if not value:
            return "$0"
        if value >= 1e6:
            return f"${value/1e6:.1f}M"
        if value >= 1e3:
            return f"${value/1e3:.0f}K"
        return f"${value:,.0f}"

    @staticmethod
    def _fmt_strike(value):
        """Format strike as $X (drop trailing .0)."""
        if value is None:
            return "$?"
        if float(value) == int(value):
            return f"${int(value)}"
        return f"${value:g}"

    @staticmethod
    def _fmt_exp(exp_date):
        """Convert YYYY-MM-DD to M/D/YY (Windows-safe)."""
        if not exp_date:
            return ""
        try:
            dt = datetime.strptime(str(exp_date), '%Y-%m-%d')
            return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"
        except (ValueError, TypeError):
            return str(exp_date)

    @staticmethod
    def _fmt_alert_time(timestamp):
        """Format ISO timestamp as 'H:MM AM/PM ET' (Windows-safe)."""
        if not timestamp:
            return ""
        try:
            dt = datetime.fromisoformat(str(timestamp).replace(' ', 'T'))
            hour = dt.hour % 12 or 12
            ampm = 'AM' if dt.hour < 12 else 'PM'
            return f"{hour}:{dt.minute:02d} {ampm} ET"
        except (ValueError, TypeError):
            return ""


def main():
    """Test/demo function"""
    import argparse
    import json
    import sys
    from pathlib import Path

    # Add project paths
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root / 'strategies' / 'flow_monitor'))

    from fm_config import FMConfig
    from fm_storage import FlowMonitorStorage

    parser = argparse.ArgumentParser(description='Social Content Generator')
    parser.add_argument('--alert-id', type=int, required=True,
                       help='Alert ID from flow_alerts table')
    parser.add_argument('--context',
                       help='Manual context to add')
    parser.add_argument('--output', default='draft.txt',
                       help='Output file for draft')

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        # Initialize
        config = FMConfig()
        storage = FlowMonitorStorage(config)
        generator = SocialContentGenerator(storage)

        # Get alert data
        query = 'SELECT * FROM flow_alerts WHERE id = ?'
        results = storage.query_with_params(query, (args.alert_id,))

        if not results:
            print(f"❌ Alert ID {args.alert_id} not found")
            return 1

        alert_data = dict(results[0])

        # Generate content
        print(f"📝 Generating content for alert {args.alert_id}...")
        post = generator.generate_post(alert_data, args.context)

        # Display
        print("\n" + "="*80)
        print("TITLE:")
        print(post['title'])
        print("\n" + "="*80)
        print("CONTENT:")
        print(post['content'])
        print("="*80)

        # Save to file
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"TITLE:\n{post['title']}\n\n")
            f.write(f"CONTENT:\n{post['content']}\n")

        print(f"\n✅ Draft saved to: {args.output}")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
