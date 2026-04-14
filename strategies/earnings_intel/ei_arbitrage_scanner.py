#!/usr/bin/env python3
"""
Earnings Play: Arbitrage Scanner (ep_arbitrage_scanner.py)
-----------------------------------------------------------
Morning arbitrage opportunity scanner for sector sympathy plays.

Finds peers with cheap IV relative to primary symbol's earnings:
- Today's earnings events (earnings_date = current date)
- Industry peers with historical correlation to primary
- IV discount opportunities (peer IV < primary IV buildup)
- Quality scoring based on correlation strength and IV discount

Part of: Earnings Intelligence System (PRD 0003)
Author: Ben (with Claude)
Date: 2025-10-10
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, date

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from decimal_formatter import clean_database_row
from log_utils import beautiful_log

class ArbitrageScanner:
    """Scan for IV arbitrage opportunities in sector sympathy plays"""

    def __init__(self, db_path=None):
        """Initialize scanner

        Args:
            db_path: Path to database (default: data/datalake.db)
        """
        if not db_path:
            db_path = os.path.join(project_root, 'data', 'datalake.db')

        self.db_path = db_path

        # Statistics tracking
        self.stats = {
            'scan_date': None,
            'earnings_today': 0,
            'opportunities_found': 0,
            'high_quality': 0,
            'medium_quality': 0,
            'low_quality': 0,
            'persisted': 0,
            'errors': 0
        }

        logging.debug("Arbitrage scanner initialized")

    def scan_morning_opportunities(self, scan_date=None):
        """Scan for morning arbitrage opportunities

        Args:
            scan_date: Date to scan for (default: today)

        Returns:
            dict: Scan statistics
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Step 1: Determine scan date
                if not scan_date:
                    scan_date = date.today().strftime('%Y-%m-%d')

                self.stats['scan_date'] = scan_date
                logging.debug("Scanning for arbitrage opportunities on: {}".format(scan_date))

                # Step 2: Get today's earnings events
                todays_earnings = self._get_todays_earnings(cursor, scan_date)

                if not todays_earnings:
                    logging.debug("No earnings events today")
                    return self.stats

                self.stats['earnings_today'] = len(todays_earnings)
                beautiful_log("Found {} earnings events today".format(len(todays_earnings)), 'info')

                # Step 3: For each earnings event, scan for peer opportunities
                opportunities = []
                for event in todays_earnings:
                    peer_opportunities = self._scan_event_peers(cursor, event, scan_date)
                    opportunities.extend(peer_opportunities)

                self.stats['opportunities_found'] = len(opportunities)

                # Step 4: Rank and score opportunities
                ranked_opportunities = self._rank_opportunities(opportunities)

                # Step 5: Persist to database
                persisted_count = self._persist_opportunities(cursor, ranked_opportunities)
                self.stats['persisted'] = persisted_count
                beautiful_log("Persisted {} opportunities to earnings_sector_effects".format(persisted_count), 'success')

                # Step 6: Display results
                self._display_opportunities(ranked_opportunities)

                return self.stats

        except Exception as e:
            logging.error("Arbitrage scan failed: {}".format(e))
            import traceback
            traceback.print_exc()
            self.stats['errors'] += 1
            return self.stats

    def _get_todays_earnings(self, cursor, scan_date):
        """Get earnings events for today

        Args:
            cursor: Database cursor
            scan_date: Date to scan for

        Returns:
            list: Today's earnings events
        """
        query = """
        SELECT ee.event_id, ee.symbol, ee.earnings_date, ee.earnings_time
        FROM earnings_events ee
        WHERE ee.earnings_date = ?
        ORDER BY ee.symbol
        """

        cursor.execute(query, (scan_date,))
        return cursor.fetchall()

    def _scan_event_peers(self, cursor, event, scan_date):
        """Scan peers for arbitrage opportunities

        Args:
            cursor: Database cursor
            event: Event record
            scan_date: Scan date

        Returns:
            list: Peer opportunities
        """
        event_id = event['event_id']
        primary_symbol = event['symbol']
        earnings_time = event['earnings_time']

        # Get primary symbol's current IV (for buildup comparison)
        primary_iv = self._get_current_iv(cursor, primary_symbol)
        if not primary_iv:
            logging.debug("No IV data for primary symbol: {}".format(primary_symbol))
            return []

        # Get industry peers and industry name (for DB persistence)
        peer_symbols = self._get_peer_symbols(cursor, primary_symbol)
        if not peer_symbols:
            logging.debug("No peers found for {}".format(primary_symbol))
            return []

        industry = self._get_symbol_industry(cursor, primary_symbol)

        # Get historical correlation from past earnings_sector_effects
        correlations = self._get_historical_correlations(cursor, primary_symbol, peer_symbols)

        opportunities = []

        for peer_symbol in peer_symbols:
            # Get peer's current IV
            peer_iv = self._get_current_iv(cursor, peer_symbol)
            if not peer_iv:
                continue

            # Calculate IV discount (primary IV - peer IV)
            iv_discount = primary_iv - peer_iv

            # Only consider opportunities where peer IV is cheaper
            if iv_discount <= 0:
                continue

            # Get correlation data
            correlation_data = correlations.get(peer_symbol, {})
            correlation_strength = correlation_data.get('correlation_strength', 0)
            sample_size = correlation_data.get('sample_size', 0)

            # Calculate opportunity score
            opportunity_score = self._calculate_opportunity_score(
                iv_discount, correlation_strength, sample_size
            )

            # Determine quality
            quality = self._determine_quality(opportunity_score)

            # Build opportunity record
            opportunity = {
                'primary_symbol': primary_symbol,
                'primary_event_id': event_id,
                'peer_symbol': peer_symbol,
                'industry': industry,
                'earnings_time': earnings_time,
                'primary_iv': primary_iv,
                'peer_iv': peer_iv,
                'iv_discount': iv_discount,
                'correlation_strength': correlation_strength,
                'sample_size': sample_size,
                'opportunity_score': opportunity_score,
                'quality': quality,
                'scan_date': scan_date
            }

            opportunities.append(opportunity)

        return opportunities

    def _get_current_iv(self, cursor, symbol):
        """Get current IV for a symbol

        Args:
            cursor: Database cursor
            symbol: Symbol

        Returns:
            float: IV value or None
        """
        query = """
        SELECT iv_30dte
        FROM option_symbol_summary
        WHERE symbol = ? AND trade_date = (
            SELECT MAX(trade_date) FROM option_symbol_summary WHERE symbol = ?
        )
        """

        cursor.execute(query, (symbol, symbol))
        row = cursor.fetchone()

        return row['iv_30dte'] if row and row['iv_30dte'] else None

    def _get_peer_symbols(self, cursor, primary_symbol, limit=10):
        """Get peer symbols for primary symbol

        Args:
            cursor: Database cursor
            primary_symbol: Primary symbol
            limit: Max peers to return

        Returns:
            list: Peer symbols
        """
        # Get industry of primary symbol
        query = """
        SELECT industry FROM industry_peer_mappings
        WHERE symbol = ? AND is_active = TRUE
        """

        cursor.execute(query, (primary_symbol,))
        row = cursor.fetchone()

        if not row:
            return []

        industry = row['industry']

        # Get peers in same industry (excluding primary)
        peer_query = """
        SELECT symbol FROM industry_peer_mappings
        WHERE industry = ?
          AND symbol != ?
          AND is_active = TRUE
        ORDER BY is_industry_leader DESC, symbol
        LIMIT ?
        """

        cursor.execute(peer_query, (industry, primary_symbol, limit))
        return [row['symbol'] for row in cursor.fetchall()]

    def _get_symbol_industry(self, cursor, symbol):
        """Get industry classification for a symbol

        Args:
            cursor: Database cursor
            symbol: Symbol to look up

        Returns:
            str: Industry name or None
        """
        cursor.execute("""
            SELECT industry FROM industry_peer_mappings
            WHERE symbol = ? AND is_active = TRUE
        """, (symbol,))
        row = cursor.fetchone()
        return row['industry'] if row else None

    def _get_historical_correlations(self, cursor, primary_symbol, peer_symbols):
        """Get historical correlation data from past earnings

        Args:
            cursor: Database cursor
            primary_symbol: Primary symbol
            peer_symbols: List of peer symbols

        Returns:
            dict: {peer_symbol: {correlation_strength, sample_size}}
        """
        if not peer_symbols:
            return {}

        # Get average correlation from earnings_sector_effects
        placeholders = ','.join(['?'] * len(peer_symbols))
        query = """
        SELECT peer_symbol,
               AVG(ABS(peer_move_pct / NULLIF(primary_move_pct, 0))) as avg_correlation,
               COUNT(*) as sample_size
        FROM earnings_sector_effects
        WHERE primary_symbol = ?
          AND peer_symbol IN ({})
          AND primary_move_pct IS NOT NULL
          AND peer_move_pct IS NOT NULL
          AND primary_move_pct != 0
        GROUP BY peer_symbol
        """.format(placeholders)

        params = [primary_symbol] + peer_symbols
        cursor.execute(query, params)

        correlations = {}
        for row in cursor.fetchall():
            peer = row['peer_symbol']
            correlations[peer] = {
                'correlation_strength': row['avg_correlation'] if row['avg_correlation'] else 0,
                'sample_size': row['sample_size'] if row['sample_size'] else 0
            }

        return correlations

    def _calculate_opportunity_score(self, iv_discount, correlation_strength, sample_size):
        """Calculate opportunity score

        Formula from PRD: IV_discount * 0.5 + correlation_strength * 50

        Args:
            iv_discount: IV discount (primary - peer)
            correlation_strength: Historical correlation
            sample_size: Number of historical data points

        Returns:
            float: Opportunity score
        """
        # Apply sample size penalty if too few data points
        sample_penalty = 1.0
        if sample_size < 3:
            sample_penalty = 0.5  # 50% penalty for low sample size
        elif sample_size < 5:
            sample_penalty = 0.75  # 25% penalty for moderate sample size

        # Calculate base score
        base_score = (iv_discount * 0.5) + (correlation_strength * 50)

        # Apply penalty
        final_score = base_score * sample_penalty

        return final_score

    def _determine_quality(self, opportunity_score):
        """Determine quality rating from score

        Args:
            opportunity_score: Calculated score

        Returns:
            str: Quality rating (High, Medium, Low)
        """
        if opportunity_score > 40:
            return 'High'
        elif opportunity_score > 20:
            return 'Medium'
        else:
            return 'Low'

    def _rank_opportunities(self, opportunities):
        """Rank and sort opportunities by score

        Args:
            opportunities: List of opportunity dicts

        Returns:
            list: Sorted opportunities
        """
        # Sort by score descending
        sorted_opps = sorted(opportunities, key=lambda x: x['opportunity_score'], reverse=True)

        # Count quality levels
        for opp in sorted_opps:
            quality = opp['quality']
            if quality == 'High':
                self.stats['high_quality'] += 1
            elif quality == 'Medium':
                self.stats['medium_quality'] += 1
            else:
                self.stats['low_quality'] += 1

        return sorted_opps

    def _persist_opportunities(self, cursor, opportunities):
        """Persist ranked opportunities to earnings_sector_effects table

        Args:
            cursor: Database cursor (within existing connection context)
            opportunities: List of ranked opportunity dicts

        Returns:
            int: Number of rows inserted
        """
        if not opportunities:
            return 0

        scan_date = opportunities[0]['scan_date']

        # Delete pre-existing pre-earnings rows for this date (idempotent re-runs)
        # Only delete rows where primary_move_pct IS NULL (pre-earnings scan records)
        try:
            cursor.execute("""
                DELETE FROM earnings_sector_effects
                WHERE DATE(calculated_at) = ?
                AND primary_move_pct IS NULL
            """, (scan_date,))
            deleted = cursor.rowcount
            if deleted > 0:
                logging.info("Cleared {} pre-existing scan results for re-run".format(deleted))
        except Exception as e:
            logging.warning("Could not clear old scan results: {}".format(e))

        inserted = 0
        for opp in opportunities:
            row = {
                'primary_event_id': opp['primary_event_id'],
                'primary_symbol': opp['primary_symbol'],
                'peer_symbol': opp['peer_symbol'],
                'industry': opp.get('industry'),
                'primary_iv_buildup_pct': opp['primary_iv'],
                'peer_iv_buildup_pct': opp['peer_iv'],
                'iv_arbitrage_delta': opp['iv_discount'],
                'correlation_strength': opp['correlation_strength'],
                'sample_size': opp['sample_size'],
                'arbitrage_quality': opp['quality'].upper(),
                'calculated_at': opp['scan_date'],
                'primary_move_pct': None,
                'peer_move_pct': None,
                'expected_peer_move_pct': None,
                'actual_vs_expected_diff': None,
            }

            # Apply decimal formatting for numeric precision
            cleaned = clean_database_row(row)
            # Restore integer fields that clean_database_row converts to float
            cleaned['primary_event_id'] = opp['primary_event_id']
            cleaned['sample_size'] = opp['sample_size']

            try:
                cursor.execute("""
                    INSERT INTO earnings_sector_effects
                    (primary_event_id, primary_symbol, peer_symbol, industry,
                     primary_iv_buildup_pct, peer_iv_buildup_pct, iv_arbitrage_delta,
                     correlation_strength, sample_size,
                     arbitrage_quality, calculated_at,
                     primary_move_pct, peer_move_pct, expected_peer_move_pct,
                     actual_vs_expected_diff)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cleaned['primary_event_id'],
                    cleaned['primary_symbol'],
                    cleaned['peer_symbol'],
                    cleaned['industry'],
                    cleaned['primary_iv_buildup_pct'],
                    cleaned['peer_iv_buildup_pct'],
                    cleaned['iv_arbitrage_delta'],
                    cleaned['correlation_strength'],
                    cleaned['sample_size'],
                    cleaned['arbitrage_quality'],
                    cleaned['calculated_at'],
                    cleaned['primary_move_pct'],
                    cleaned['peer_move_pct'],
                    cleaned['expected_peer_move_pct'],
                    cleaned['actual_vs_expected_diff'],
                ))
                inserted += 1
            except Exception as e:
                logging.warning("Failed to persist opportunity {} -> {}: {}".format(
                    opp['primary_symbol'], opp['peer_symbol'], e))
                self.stats['errors'] += 1

        return inserted

    def _display_opportunities(self, opportunities):
        """Display opportunities summary

        Args:
            opportunities: Ranked opportunities
        """
        if not opportunities:
            logging.info("No arbitrage opportunities found")
            return

        logging.info("Arbitrage opportunities - {}".format(self.stats['scan_date']))

        # Group by quality
        for quality_level in ['High', 'Medium', 'Low']:
            quality_opps = [o for o in opportunities if o['quality'] == quality_level]

            if not quality_opps:
                continue

            logging.info("{} QUALITY ({} opportunities):".format(quality_level.upper(), len(quality_opps)))

            for opp in quality_opps[:10]:  # Show top 10 per quality level
                logging.info("  {} -> {} | Score: {:.1f} | IV Discount: {:.2f}% | Correlation: {:.2f} (n={})".format(
                    opp['primary_symbol'],
                    opp['peer_symbol'],
                    opp['opportunity_score'],
                    opp['iv_discount'] * 100,
                    opp['correlation_strength'],
                    opp['sample_size']
                ))



def setup_logging(debug=False):
    """Set up logging configuration with UTF-8 encoding"""
    level = logging.DEBUG if debug else logging.INFO

    # Create logs directory
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, 'ei_arbitrage_scanner.log')

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )


def main():
    """Main function with CLI interface"""
    import argparse

    parser = argparse.ArgumentParser(description='Earnings Play: Arbitrage Scanner')
    parser.add_argument('--scan-date', type=str,
                       help='Date to scan for (YYYY-MM-DD, default: today)')
    parser.add_argument('--no-interaction', action='store_true',
                       help='Run without user prompts')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')

    args = parser.parse_args()

    # Reconfigure stdout for UTF-8 encoding (Windows)
    sys.stdout.reconfigure(encoding='utf-8')

    print("Earnings Play: Arbitrage Scanner")
    print("Scanning for IV arbitrage opportunities")

    if not args.no_interaction:
        input("\nPress Enter to begin...")

    setup_logging(args.debug)

    try:
        # Initialize scanner
        scanner = ArbitrageScanner()

        # Run scan
        results = scanner.scan_morning_opportunities(args.scan_date)

        # Show results
        if results['errors'] > 0:
            print("✅ Scan completed with {} errors".format(results['errors']))
            print("   Opportunities: {}".format(results['opportunities_found']))
            return 1
        else:
            print("✅ Scan completed successfully!")
            print("   Scan date: {}".format(results['scan_date']))
            print("   Earnings today: {}".format(results['earnings_today']))
            print("   Opportunities: {}".format(results['opportunities_found']))
            print("   High quality: {}".format(results['high_quality']))
            print("   Medium quality: {}".format(results['medium_quality']))
            return 0

    except KeyboardInterrupt:
        print("\n⚠️ Scan cancelled by user")
        return 130
    except Exception as e:
        print("\n❌ Scan failed: {}".format(e))
        logging.error("Scan error: {}".format(e))
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if not args.no_interaction:
            input("\nPress Enter to exit...")


if __name__ == "__main__":
    sys.exit(main())
