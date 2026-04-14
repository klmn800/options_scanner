#!/usr/bin/env python3
"""
Direct Database Query Tool for Research
Enhanced tool to run SQL queries against the query database (datalake_query.db) for safe analysis.

DATABASE ARCHITECTURE:
- Query Database (default): datalake_query.db - safe read-only copy for analysis
- Primary Database: datalake.db - actively written by data pipelines (use --db to access)
- Performance Database: data/performance.db - operational metrics (13 tables, written end-of-day)
- Archive Databases: data/sector_archive/*.db - historical sector archives

ENHANCED FEATURES FOR CLAUDE CODE:
- Raw SQL execution: --sql "SELECT * FROM flow_alerts LIMIT 5"
- Schema exploration: --schema flow_alerts
- Multi-query support: --multi "query1; query2; query3"
- JSON output: --json flag for structured data
- Database selection: --db data/datalake.db (primary) or --db archive_2025_07.db (archives)
- Error handling with helpful suggestions

DEPRECATION NOTICE (Oct 20, 2025):
Several convenience methods in this file use deleted database columns (is_interesting,
gap_from_max_pct, etc.) that were removed during the Oct 19, 2025 migration. These
methods are deprecated and will raise errors. Use --sql flag for custom queries instead.

Core functionality (--sql, --schema, --tables, --multi) is unaffected.

ENCOURAGEMENT FOR CLAUDE:
Feel free to add new methods for commonly used query patterns! This is a living
document designed to make database analysis more efficient. Add methods like:
- get_symbol_alerts(symbol, days=7)
- get_high_volume_contracts(min_volume=1000)
- analyze_flow_patterns(date_range)
etc.

The goal is to reduce repetitive Python database scripts and make analysis faster.
"""

import sqlite3
import sys
import json
import argparse
import os
import time
from datetime import datetime, timedelta

class DirectDBQuery:
    def __init__(self, db_path="data/datalake_query.db"):
        self.db_path = db_path

        # If relative path, make it relative to project root
        if not os.path.isabs(self.db_path):
            # Assume we're in tools/ directory, go up to project root
            tools_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(tools_dir)
            self.db_path = os.path.join(project_root, self.db_path)
            self.project_root = project_root
        else:
            # If absolute path, try to infer project root
            self.project_root = os.path.dirname(os.path.dirname(self.db_path))

    def _get_connection_with_sync_check(self):
        """
        Get database connection with sync lock coordination (2025-12-16 Batch Fix)

        Checks for sync lock file to avoid WinError 32 during database sync operations.
        If sync is in progress, waits briefly and retries.
        """
        # Only check lock file if querying the query database
        if 'datalake_query.db' in self.db_path:
            sync_lock_file = os.path.join(self.project_root, 'data', '.datalake_query_sync_in_progress')

            max_retries = 3
            retry_delay = 2.0  # seconds

            for attempt in range(max_retries):
                if not os.path.exists(sync_lock_file):
                    # No sync in progress - safe to open connection
                    return sqlite3.connect(self.db_path)

                # Sync in progress - wait and retry
                if attempt < max_retries - 1:
                    print(f"Database sync in progress, waiting {retry_delay}s (attempt {attempt + 1}/{max_retries})", file=sys.stderr)
                    time.sleep(retry_delay)
                else:
                    # Final attempt - warn but continue (graceful degradation)
                    print(f"Warning: Database sync still in progress after {max_retries} attempts, proceeding anyway", file=sys.stderr)
                    return sqlite3.connect(self.db_path)

        # Not query database or no lock file - connect normally
        return sqlite3.connect(self.db_path)

    def execute_query(self, sql, params=None):
        """Execute SQL query and return results"""
        try:
            conn = self._get_connection_with_sync_check()
            conn.row_factory = sqlite3.Row  # This makes rows act like dictionaries
            cursor = conn.cursor()

            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            results = cursor.fetchall()
            conn.close()

            # Convert to list of dictionaries for easier handling
            return [dict(row) for row in results]

        except Exception as e:
            print("Error executing query: {}".format(e))
            return None

    def get_high_oi_unflagged_contracts(self, limit=20, min_oi=10000):
        """Find high-OI contracts that weren't flagged as interesting"""
        sql = """
        SELECT
            symbol,
            strike,
            option_type,
            expiration_date,
            open_interest,
            is_interesting,
            gap_from_max_pct,
            group_max_oi,
            trade_date
        FROM oi_daily
        WHERE is_interesting = 0
        AND open_interest >= ?
        AND trade_date >= date('now', '-3 days')
        ORDER BY open_interest DESC
        LIMIT ?
        """
        return self.execute_query(sql, (min_oi, limit))

    def get_recent_trading_date(self):
        """Get the most recent trading date in the database"""
        sql = "SELECT MAX(trade_date) as latest_date FROM oi_daily"
        result = self.execute_query(sql)
        return result[0]['latest_date'] if result else None

    def get_contract_group_analysis(self, symbol, expiration_date, option_type):
        """Analyze all contracts in a specific group to understand gap calculations"""
        sql = """
        SELECT
            symbol,
            strike,
            option_type,
            expiration_date,
            open_interest,
            is_interesting,
            gap_from_max_pct,
            group_max_oi,
            MAX(open_interest) OVER (PARTITION BY symbol, expiration_date, option_type) as calculated_max_oi
        FROM oi_daily
        WHERE symbol = ?
        AND expiration_date = ?
        AND option_type = ?
        AND trade_date = (SELECT MAX(trade_date) FROM oi_daily WHERE symbol = ?)
        ORDER BY open_interest DESC
        """
        return self.execute_query(sql, (symbol, expiration_date, option_type, symbol))

    def find_spy_put_groups(self):
        """Find what expiration dates those big SPY puts belong to"""
        sql = """
        SELECT
            strike,
            expiration_date,
            open_interest,
            is_interesting,
            gap_from_max_pct,
            group_max_oi
        FROM oi_daily
        WHERE symbol = 'SPY'
        AND option_type = 'PUT'
        AND strike IN (400, 405, 500, 505)
        AND trade_date = (SELECT MAX(trade_date) FROM oi_daily)
        ORDER BY expiration_date, open_interest DESC
        """
        return self.execute_query(sql)

    def find_spy_put_group_maximum(self):
        """Find the actual maximum OI in SPY 2025-10-17 PUT group"""
        sql = """
        SELECT
            symbol,
            strike,
            expiration_date,
            open_interest,
            is_interesting,
            gap_from_max_pct,
            group_max_oi,
            created_at,
            trade_date
        FROM oi_daily
        WHERE symbol = 'SPY'
        AND option_type = 'PUT'
        AND expiration_date = '2025-10-17'
        AND trade_date = (SELECT MAX(trade_date) FROM oi_daily)
        ORDER BY open_interest DESC
        LIMIT 20
        """
        return self.execute_query(sql)

    def verify_spy_405_data(self):
        """Verify SPY $405 PUT data exists in database"""
        sql = """
        SELECT
            symbol,
            strike,
            option_type,
            expiration_date,
            open_interest,
            is_interesting,
            gap_from_max_pct,
            group_max_oi,
            created_at,
            trade_date,
            contract_hash
        FROM oi_daily
        WHERE symbol = 'SPY'
        AND strike = 405
        AND option_type = 'PUT'
        AND trade_date >= date('now', '-3 days')
        ORDER BY trade_date DESC, created_at DESC
        """
        return self.execute_query(sql)

    def analyze_clean_symbol_groups(self, symbol='NVDA'):
        """Analyze groups in a cleaner symbol to see proper gap calculations"""
        sql = """
        SELECT
            symbol,
            strike,
            option_type,
            expiration_date,
            open_interest,
            is_interesting,
            gap_from_max_pct,
            group_max_oi,
            MAX(open_interest) OVER (PARTITION BY symbol, expiration_date, option_type) as actual_group_max
        FROM oi_daily
        WHERE symbol = ?
        AND trade_date = (SELECT MAX(trade_date) FROM oi_daily)
        AND open_interest > 1000
        ORDER BY expiration_date, option_type, open_interest DESC
        """
        return self.execute_query(sql, (symbol,))

    def get_recent_stats(self):
        """Get basic stats about recent data"""
        sql = """
        SELECT
            COUNT(*) as total_contracts,
            COUNT(CASE WHEN is_interesting = 1 THEN 1 END) as interesting_contracts,
            AVG(open_interest) as avg_oi,
            MAX(open_interest) as max_oi,
            MIN(trade_date) as earliest_date,
            MAX(trade_date) as latest_date
        FROM oi_daily
        WHERE trade_date >= date('now', '-7 days')
        """
        return self.execute_query(sql)

    def get_symbol_coverage_analysis(self):
        """Analyze how many symbols are being processed vs total"""
        sql = """
        SELECT
            symbol,
            COUNT(*) as total_contracts,
            COUNT(CASE WHEN is_interesting = 1 THEN 1 END) as interesting_contracts,
            ROUND(100.0 * COUNT(CASE WHEN is_interesting = 1 THEN 1 END) / COUNT(*), 2) as interesting_pct,
            SUM(open_interest) as total_oi
        FROM oi_daily
        WHERE trade_date >= date('now', '-3 days')
        GROUP BY symbol
        HAVING total_contracts > 10
        ORDER BY total_oi DESC
        LIMIT 20
        """
        return self.execute_query(sql)

    def analyze_symbol_processing_patterns(self):
        """Analyze which symbols are having their gaps calculated vs not"""
        sql = """
        SELECT
            symbol,
            COUNT(*) as total_contracts,
            COUNT(CASE WHEN gap_from_max_pct > 0 THEN 1 END) as processed_contracts,
            COUNT(CASE WHEN gap_from_max_pct = 0 OR gap_from_max_pct IS NULL THEN 1 END) as unprocessed_contracts,
            COUNT(CASE WHEN is_interesting = 1 THEN 1 END) as interesting_contracts,
            MAX(open_interest) as max_oi
        FROM oi_daily
        WHERE trade_date = (SELECT MAX(trade_date) FROM oi_daily)
        GROUP BY symbol
        HAVING total_contracts > 50
        ORDER BY max_oi DESC
        LIMIT 20
        """
        return self.execute_query(sql)

    def check_specific_contracts(self):
        """Check specific contracts mentioned in agent research"""
        contracts_to_check = [
            ('SPY', 405, 'PUT'),
            ('SPY', 505, 'PUT'),
            ('SPY', 400, 'PUT'),
            ('SPY', 500, 'PUT'),
            ('QQQ', 450, 'PUT'),  # Adding some QQQ cases too
            ('IWM', 200, 'PUT'),
        ]

        for symbol, strike, option_type in contracts_to_check:
            sql = """
            SELECT
                symbol, strike, option_type, expiration_date,
                open_interest, is_interesting, gap_from_max_pct, group_max_oi, trade_date
            FROM oi_daily
            WHERE symbol = ? AND strike = ? AND option_type = ?
            AND trade_date >= date('now', '-5 days')
            ORDER BY trade_date DESC, open_interest DESC
            LIMIT 5
            """
            results = self.execute_query(sql, (symbol, strike, option_type))

            if results:
                print("\n=== {} ${} {} ===".format(symbol, strike, option_type))
                for row in results:
                    gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                    interesting = "YES" if row.get('is_interesting') else "NO"
                    print("  Date: {} | OI: {:>6,} | Interesting: {} | Gap: {:>5.1f}% | GroupMax: {:>6,}".format(
                        row.get('trade_date', 'N/A'),
                        row.get('open_interest', 0),
                        interesting,
                        gap_pct,
                        row.get('group_max_oi', 0) or 0
                    ))

    def investigate_edge_cases_near_threshold(self):
        """Look for contracts with gap percentages just below 50%"""
        sql = """
        SELECT
            symbol, strike, option_type, expiration_date,
            open_interest, is_interesting, gap_from_max_pct, group_max_oi, trade_date
        FROM oi_daily
        WHERE gap_from_max_pct BETWEEN 0.45 AND 0.499999
        AND open_interest > 1000
        AND trade_date >= date('now', '-3 days')
        ORDER BY gap_from_max_pct DESC, open_interest DESC
        LIMIT 20
        """
        return self.execute_query(sql)

    def execute_raw_sql(self, sql, output_format='table'):
        """Execute raw SQL and return results in specified format"""
        try:
            conn = self._get_connection_with_sync_check()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Handle multiple statements
            statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
            all_results = []

            for stmt in statements:
                cursor.execute(stmt)
                results = cursor.fetchall()
                all_results.append([dict(row) for row in results])

            conn.close()

            if output_format == 'json':
                return json.dumps(all_results, indent=2, default=str)
            elif output_format == 'table':
                return self._format_table_results(all_results)
            else:
                return all_results

        except Exception as e:
            error_msg = "SQL Error: {}".format(e)
            # Try to provide helpful suggestions
            if "no such table" in str(e).lower():
                tables = self.get_table_names()
                error_msg += "\nAvailable tables: {}".format(", ".join(tables))
            elif "no such column" in str(e).lower():
                # Extract table name from error if possible
                error_msg += "\nTip: Use --schema <table> to see available columns"

            if output_format == 'json':
                return json.dumps({"error": error_msg})
            else:
                return error_msg

    def get_table_names(self):
        """Get list of all table names in database"""
        try:
            conn = self._get_connection_with_sync_check()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            return tables
        except Exception:
            return []

    def get_table_schema(self, table_name):
        """Get schema information for a table"""
        try:
            conn = self._get_connection_with_sync_check()
            cursor = conn.cursor()

            # Get column info
            cursor.execute("PRAGMA table_info({})".format(table_name))
            columns = cursor.fetchall()

            # Get row count
            cursor.execute("SELECT COUNT(*) FROM {}".format(table_name))
            row_count = cursor.fetchone()[0]

            # Get indexes
            cursor.execute("PRAGMA index_list({})".format(table_name))
            indexes = cursor.fetchall()

            conn.close()

            schema_info = {
                'table': table_name,
                'columns': [
                    {
                        'name': col[1],
                        'type': col[2],
                        'not_null': bool(col[3]),
                        'primary_key': bool(col[5])
                    }
                    for col in columns
                ],
                'row_count': row_count,
                'indexes': [idx[1] for idx in indexes]
            }

            return schema_info

        except Exception as e:
            return {"error": "Error getting schema for {}: {}".format(table_name, e)}

    def _format_table_results(self, all_results):
        """Format query results as readable tables"""
        output = []

        for i, results in enumerate(all_results):
            if i > 0:
                output.append("\n" + "="*60 + "\n")

            if not results:
                output.append("No results returned")
                continue

            # Get column names
            columns = list(results[0].keys())

            # Calculate column widths
            col_widths = {}
            for col in columns:
                col_widths[col] = max(
                    len(col),
                    max(len(str(row.get(col, ''))) for row in results[:20])  # Sample first 20 rows
                )
                col_widths[col] = min(col_widths[col], 30)  # Max width 30

            # Header
            header = " | ".join(col.ljust(col_widths[col]) for col in columns)
            output.append(header)
            output.append("-" * len(header))

            # Rows
            for row in results:
                row_str = " | ".join(
                    str(row.get(col, ''))[:col_widths[col]].ljust(col_widths[col])
                    for col in columns
                )
                output.append(row_str)

            output.append("\nRows returned: {}".format(len(results)))

        return "\n".join(output)

    def execute_multi_query(self, queries, output_format='table'):
        """Execute multiple queries and return combined results"""
        all_outputs = []

        for i, query in enumerate(queries):
            query = query.strip()
            if not query:
                continue

            if output_format == 'table':
                all_outputs.append("Query {}: {}".format(i+1, query))
                all_outputs.append("-" * 40)

            result = self.execute_raw_sql(query, output_format)
            all_outputs.append(result)

            if output_format == 'table' and i < len(queries) - 1:
                all_outputs.append("\n" + "="*60 + "\n")

        if output_format == 'json':
            return json.dumps(all_outputs, indent=2, default=str)
        else:
            return "\n".join(all_outputs)

def main():
    parser = argparse.ArgumentParser(
        description='Direct Database Query Tool - Enhanced for Claude Code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Raw SQL query
  python direct_db_query.py --sql "SELECT COUNT(*) FROM flow_alerts"

  # Table schema
  python direct_db_query.py --schema flow_alerts

  # Multiple queries
  python direct_db_query.py --multi "SELECT COUNT(*) FROM flow_alerts; SELECT MAX(trade_date) FROM oi_daily"

  # JSON output
  python direct_db_query.py --sql "SELECT * FROM flow_alerts LIMIT 5" --json

  # Pre-built queries (legacy)
  python direct_db_query.py high_oi_unflagged
        """)

    # New enhanced options
    parser.add_argument('--sql', help='Execute raw SQL query')
    parser.add_argument('--schema', help='Show schema for specified table')
    parser.add_argument('--tables', action='store_true', help='List all tables')
    parser.add_argument('--multi', help='Execute multiple SQL queries (semicolon separated)')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--db', default='data/datalake_query.db',
                       help='Database path (default: data/datalake_query.db). Use data/datalake.db for primary, data/performance.db for operational metrics, or data/sector_archive/*.db for archives')

    # Legacy positional argument for pre-built queries
    parser.add_argument('query_type', nargs='?',
                       help='Pre-built query type (test_connection, high_oi_unflagged, recent_stats, etc.)')
    parser.add_argument('query_arg', nargs='?', help='Optional argument for pre-built queries')

    args = parser.parse_args()

    # Initialize database query object
    db = DirectDBQuery(args.db)
    output_format = 'json' if args.json else 'table'

    # Handle new enhanced features
    if args.sql:
        result = db.execute_raw_sql(args.sql, output_format)
        print(result)
        return

    if args.schema:
        schema = db.get_table_schema(args.schema)
        if args.json:
            print(json.dumps(schema, indent=2))
        else:
            if 'error' in schema:
                print(schema['error'])
            else:
                print("Table: {}".format(schema['table']))
                print("Rows: {:,}".format(schema['row_count']))
                print("\nColumns:")
                for col in schema['columns']:
                    pk = " (PRIMARY KEY)" if col['primary_key'] else ""
                    null = " NOT NULL" if col['not_null'] else ""
                    print("  {} - {}{}{}".format(col['name'], col['type'], null, pk))
                if schema['indexes']:
                    print("\nIndexes: {}".format(", ".join(schema['indexes'])))
        return

    if args.tables:
        tables = db.get_table_names()
        if args.json:
            print(json.dumps({"tables": tables}))
        else:
            print("Tables in database:")
            for table in tables:
                print("  {}".format(table))
        return

    if args.multi:
        queries = [q.strip() for q in args.multi.split(';') if q.strip()]
        result = db.execute_multi_query(queries, output_format)
        print(result)
        return

    # Handle legacy pre-built queries
    if not args.query_type:
        parser.print_help()
        return

    query_type = args.query_type

    if query_type == "test_connection":
        # Test basic connectivity and recent date
        latest_date = db.get_recent_trading_date()
        if latest_date:
            print("Database connection successful!")
            print("Latest trading date: {}".format(latest_date))

            # Get a simple count
            result = db.execute_query("SELECT COUNT(*) as count FROM oi_daily WHERE trade_date = ?", (latest_date,))
            if result:
                print("Contracts on latest date: {:,}".format(result[0]['count']))
        else:
            print("Database connection failed or no data found")

    elif query_type == "high_oi_unflagged":
        # Try different thresholds
        for threshold in [5000, 2500, 1500]:
            print("\n=== High OI contracts (>{:,}) not flagged as interesting ===".format(threshold))
            results = db.get_high_oi_unflagged_contracts(limit=15, min_oi=threshold)

            if results:
                print("Found {} results:".format(len(results)))
                print("-" * 90)
                for row in results:
                    gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                    group_max = row.get('group_max_oi') or 0
                    print("{:<8} ${:<6} {} {} | OI: {:>6,} | Gap: {:>5.1f}% | GroupMax: {:>6,} | {}".format(
                        row['symbol'],
                        row['strike'],
                        row['option_type'][:4],
                        row['expiration_date'],
                        row['open_interest'],
                        gap_pct,
                        group_max,
                        row['trade_date']
                    ))
                break  # Stop at first threshold that gives results
            else:
                print("No results found")

    elif query_type == "recent_stats":
        results = db.get_recent_stats()
        if results:
            stats = results[0]
            print("Recent database statistics:")
            print("=" * 40)
            print("Total contracts: {:,}".format(stats['total_contracts']))
            print("Interesting contracts: {:,}".format(stats['interesting_contracts']))
            print("Interesting percentage: {:.2f}%".format(
                100.0 * stats['interesting_contracts'] / stats['total_contracts'] if stats['total_contracts'] > 0 else 0))
            print("Average OI: {:.0f}".format(stats['avg_oi'] or 0))
            print("Max OI: {:,}".format(stats['max_oi'] or 0))
            print("Date range: {} to {}".format(stats['earliest_date'], stats['latest_date']))

    elif query_type == "check_specific":
        print("Checking specific contracts mentioned in research:")
        db.check_specific_contracts()

    elif query_type == "edge_cases":
        print("Looking for contracts with gap percentages just below 50% threshold:")
        results = db.investigate_edge_cases_near_threshold()
        if results:
            print("Found {} edge cases:".format(len(results)))
            print("-" * 100)
            for row in results:
                gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                interesting = "YES" if row.get('is_interesting') else "NO"
                print("{:<8} ${:<6} {} {} | OI: {:>6,} | Interesting: {} | Gap: {:>5.2f}% | GroupMax: {:>6,}".format(
                    row['symbol'],
                    row['strike'],
                    row['option_type'][:4],
                    row['expiration_date'],
                    row['open_interest'],
                    interesting,
                    gap_pct,
                    row.get('group_max_oi', 0)
                ))
        else:
            print("No edge cases found")

    elif query_type == "symbol_patterns":
        print("Analyzing symbol processing patterns:")
        results = db.analyze_symbol_processing_patterns()
        if results:
            print("Symbol processing analysis (top 20 by max OI):")
            print("-" * 100)
            print("{:<8} | {:>6} | {:>9} | {:>11} | {:>11} | {:>8}".format(
                "Symbol", "Total", "Processed", "Unprocessed", "Interesting", "Max OI"))
            print("-" * 100)
            for row in results:
                processed_pct = 100.0 * row['processed_contracts'] / row['total_contracts'] if row['total_contracts'] > 0 else 0
                print("{:<8} | {:>6} | {:>8} | {:>11} | {:>11} | {:>8,}".format(
                    row['symbol'],
                    row['total_contracts'],
                    "{} ({:.1f}%)".format(row['processed_contracts'], processed_pct),
                    row['unprocessed_contracts'],
                    row['interesting_contracts'],
                    row['max_oi']
                ))
        else:
            print("No results found")

    elif query_type == "symbol_coverage":
        results = db.get_symbol_coverage_analysis()
        print("Symbol coverage analysis (top 20 by total OI):")
        print("=" * 80)
        print("{:<8} | {:>10} | {:>12} | {:>8} | {:>12}".format(
            "Symbol", "Total", "Interesting", "Int %", "Total OI"))
        print("-" * 80)
        for row in results or []:
            print("{:<8} | {:>10} | {:>12} | {:>7.1f}% | {:>12,}".format(
                row['symbol'],
                row['total_contracts'],
                row['interesting_contracts'],
                row['interesting_pct'],
                row['total_oi']
            ))

    elif query_type == "spy_groups":
        print("Analyzing SPY PUT groups for high-OI strikes:")
        results = db.find_spy_put_groups()
        if results:
            current_exp = None
            for row in results:
                if row['expiration_date'] != current_exp:
                    current_exp = row['expiration_date']
                    print("\n=== SPY PUT Expiration: {} ===".format(current_exp))

                interesting = "YES" if row.get('is_interesting') else "NO"
                gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                group_max = row.get('group_max_oi') or 0

                print("  ${:<4} | OI: {:>6,} | Interesting: {:>3} | Gap: {:>5.1f}% | GroupMax: {:>6,}".format(
                    row['strike'],
                    row['open_interest'],
                    interesting,
                    gap_pct,
                    group_max
                ))
        else:
            print("No results found")

    elif query_type == "clean_symbol":
        symbol = sys.argv[2] if len(sys.argv) > 2 else 'NVDA'
        print("Analyzing {} groups to see proper gap calculations:".format(symbol))
        results = db.analyze_clean_symbol_groups(symbol)
        if results:
            current_group = None
            for row in results:
                group_key = "{}_{}_{}".format(row['expiration_date'], row['option_type'], row['actual_group_max'])
                if group_key != current_group:
                    current_group = group_key
                    print("\n=== {} {} {} (Group Max: {:,}) ===".format(
                        row['symbol'], row['option_type'], row['expiration_date'], row['actual_group_max']))

                interesting = "YES" if row.get('is_interesting') else "NO"
                gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                stored_group_max = row.get('group_max_oi') or 0
                calculated_gap = (row['open_interest'] / row['actual_group_max']) * 100 if row['actual_group_max'] > 0 else 0

                print("  ${:<6} | OI: {:>6,} | Int: {:>3} | Gap: {:>5.1f}% | StoredMax: {:>6,} | CalcGap: {:>5.1f}%".format(
                    row['strike'],
                    row['open_interest'],
                    interesting,
                    gap_pct,
                    stored_group_max,
                    calculated_gap
                ))
        else:
            print("No results found")

    elif query_type == "spy_oct17":
        print("Finding actual maximum OI in SPY 2025-10-17 PUT group:")
        results = db.find_spy_put_group_maximum()
        if results:
            print("Top 20 SPY PUTs expiring 2025-10-17:")
            print("-" * 80)
            for i, row in enumerate(results, 1):
                interesting = "YES" if row.get('is_interesting') else "NO"
                gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                group_max = row.get('group_max_oi') or 0

                print("{:>2}. ${:<6} | OI: {:>8,} | Int: {:>3} | Gap: {:>5.1f}% | GroupMax: {:>8,}".format(
                    i,
                    row['strike'],
                    row['open_interest'],
                    interesting,
                    gap_pct,
                    group_max
                ))
        else:
            print("No results found")

    elif query_type == "verify_spy405":
        print("Verifying SPY $405 PUT data exists in database:")
        results = db.verify_spy_405_data()
        if results:
            print("Found {} records for SPY $405 PUT:".format(len(results)))
            print("-" * 100)
            for row in results:
                interesting = "YES" if row.get('is_interesting') else "NO"
                gap_pct = (row.get('gap_from_max_pct') or 0) * 100
                group_max = row.get('group_max_oi') or 0

                print("Date: {} | Exp: {} | OI: {:>8,} | Int: {:>3} | Gap: {:>5.1f}% | GroupMax: {:>8,} | Hash: {}".format(
                    row['trade_date'],
                    row['expiration_date'],
                    row['open_interest'],
                    interesting,
                    gap_pct,
                    group_max,
                    row.get('contract_hash', 'N/A')
                ))
        else:
            print("No SPY $405 PUT data found in database!")

    else:
        print("Unknown query type: {}".format(query_type))

if __name__ == "__main__":
    main()