#!/usr/bin/env python3
"""
Oracle Database Access Layer (oracle_data_access.py)
---------------------------------------------------
Safe, read-only database access for Oracle CLI.
Provides secure query execution with comprehensive validation.

Features:
- Read-only query enforcement
- Query timeout and result limits
- Comprehensive query logging
- Schema introspection
- Parameter binding for safety

Author: Ben (with assistance from Claude)
Date: 2025-07-10
"""

import sqlite3
import logging
import time
import re
from pathlib import Path
from contextlib import contextmanager
from tools.timezone_utils import now_eastern, eastern_isoformat

class DatabaseConnection:
    """Secure database connection manager for Oracle CLI"""
    
    def __init__(self, config, debug_mode=False):
        """Initialize database connection manager
        
        Args:
            config: OracleConfig instance with database settings
            debug_mode: Whether to show detailed SQL execution logs
        """
        self.config = config
        self.debug_mode = debug_mode
        self.db_path = config.get_database_path()
        self.max_timeout = config.max_query_timeout
        self.max_result_rows = config.max_result_rows
        
        # Set up database-specific logging
        self._setup_database_logging()
        
        # Validate database exists and is accessible
        self._validate_database_file()
        
        # Cache schema information
        self._schema_cache = None
        
        logging.info("Database connection manager initialized")
        logging.info("Database path: {}".format(self.db_path))
        logging.info("Query timeout: {} seconds".format(self.max_timeout))
        logging.info("Result limit: {} rows".format(self.max_result_rows))
    
    def _setup_database_logging(self):
        """Set up database-specific logging to separate file"""
        db_logger = logging.getLogger('oracle.database')
        
        # Check if handler already exists
        if db_logger.handlers:
            return
        
        db_log_file = self.config.get_database_log_file()
        
        # Create file handler for database operations
        db_handler = logging.FileHandler(db_log_file, mode='a', encoding='utf-8')
        db_handler.setLevel(logging.DEBUG)
        
        # Detailed formatter for database operations
        db_formatter = logging.Formatter(
            '%(asctime)s - DATABASE - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        db_handler.setFormatter(db_formatter)
        
        db_logger.addHandler(db_handler)
        db_logger.setLevel(logging.DEBUG)
        db_logger.propagate = True  # Also log to main logger
    
    def _validate_database_file(self):
        """Validate that database file exists and is accessible"""
        db_file = Path(self.db_path)
        
        if not db_file.exists():
            raise FileNotFoundError("Database file not found: {}".format(self.db_path))
        
        if not db_file.is_file():
            raise ValueError("Database path is not a file: {}".format(self.db_path))
        
        # Test basic connectivity
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                cursor.fetchone()
            logging.info("Database connectivity test passed")
        except sqlite3.Error as e:
            raise RuntimeError("Database connectivity test failed: {}".format(e))
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper resource management"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.max_timeout,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row  # Enable column access by name
            
            # Set read-only mode and other safety settings
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA temp_store = MEMORY")
            
            yield conn
            
        except sqlite3.Error as e:
            logging.error("Database connection error: {}".format(e))
            raise
        finally:
            if conn:
                conn.close()
    
    def _is_safe_pragma(self, query):
        """Check if PRAGMA statement is safe to execute"""
        query_lower = query.lower().strip()
        allowed_pragmas = [
            'pragma query_only',
            'pragma table_info',
            'pragma table_list'
        ]
        return any(query_lower.startswith(pragma) for pragma in allowed_pragmas)
        
    def validate_query_safety(self, sql):
        """Validate that SQL query is safe (read-only)
        
        Args:
            sql: SQL query string to validate
            
        Returns:
            bool: True if query is safe, False otherwise
            
        Raises:
            ValueError: If query contains dangerous operations
        """
        if not sql or not isinstance(sql, str):
            raise ValueError("SQL query must be a non-empty string")
        
        # Normalize query for checking
        sql_upper = sql.upper().strip()
        
        # Remove comments and extra whitespace
        sql_clean = re.sub(r'--.*?\n', ' ', sql_upper)
        sql_clean = re.sub(r'/\*.*?\*/', ' ', sql_clean, flags=re.DOTALL)
        sql_clean = re.sub(r'\s+', ' ', sql_clean).strip()
        
        # Dangerous keywords that should never appear as standalone words
        dangerous_patterns = [
            r'\bINSERT\b', r'\bUPDATE\b', r'\bDELETE\b', r'\bDROP\b', 
            r'\bCREATE\b', r'\bALTER\b', r'\bTRUNCATE\b', r'\bREPLACE\b', 
            r'\bMERGE\b', r'\bUPSERT\b'
        ]

        # Check for dangerous keywords as whole words only
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_clean):
                raise ValueError("Query contains forbidden operation: {}".format(pattern))
        
        # Additional dangerous patterns
        dangerous_patterns = [
            r'\bINTO\b',  # Usually part of INSERT INTO
            r'\bSET\b',   # Usually part of UPDATE SET
            r'\bVALUES\b', # Part of INSERT VALUES
            r'ATTACH\b', r'DETACH\b',  # Database attachment
            r'VACUUM\b', r'REINDEX\b'  # Maintenance operations
        ]      
      
        # Check for dangerous patterns
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_clean):
                raise ValueError("Query contains forbidden pattern: {}".format(pattern))
        
        # Handle PRAGMA statements separately
        if sql_clean.startswith('PRAGMA'):
            if not self._is_safe_pragma(sql):
                raise ValueError("Query contains forbidden PRAGMA command")
        else:
            # Must start with SELECT or WITH (CTE)
            if not any(sql_clean.startswith(start) for start in ['SELECT', 'WITH']):
                raise ValueError("Query must start with SELECT, WITH, or safe PRAGMA statement")
        
        logging.getLogger('oracle.database').debug("Query safety validation passed")
        return True
    
    def execute_query(self, sql, params=None):
        """Execute a safe SELECT query with parameter binding and self-correction
        
        Args:
            sql: SQL query string (SELECT only)
            params: Optional parameters for query binding
            
        Returns:
            dict: Query results with metadata
            
        Raises:
            ValueError: If query is unsafe
            sqlite3.Error: If query execution fails after all correction attempts
        """
        start_time = time.time()
        db_logger = logging.getLogger('oracle.database')
        
        # Enhanced semantic column correction system
        SEMANTIC_COLUMN_GROUPS = {
            'price_terms': {
                'aliases': ['price', 'cost', 'premium', 'value'],
                'targets': ['last_price', 'close_price', 'underlying_price', 'premium_value', 'bid', 'ask'],
                'preferred': 'close_price'  # Default when multiple matches exist
            },
            'date_terms': {
                'aliases': ['date', 'time', 'datetime'],
                'targets': ['trade_date', 'expiration_date', 'created_at', 'updated_at', 'scan_timestamp'],
                'preferred': 'trade_date'
            },
            'volume_terms': {
                'aliases': ['vol', 'volume'],
                'targets': ['volume', 'total_volume', 'call_volume', 'put_volume'],
                'preferred': 'volume'
            },
            'symbol_terms': {
                'aliases': ['ticker', 'stock', 'underlying'],
                'targets': ['symbol'],
                'preferred': 'symbol'
            }
        }
        
        # Legacy mappings for backwards compatibility
        LEGACY_CORRECTIONS = {
            'date': 'trade_date',
            'price_date': 'trade_date', 
            'price': 'close_price',
            'cost': 'close_price'
        }
        
        # Prepare parameters
        if params is None:
            params = []
        elif isinstance(params, dict):
            param_str = "Named params: {}".format(params)
        else:
            param_str = "Positional params: {}".format(params)
        
        # Try query execution with correction attempts (max 3 attempts)
        max_attempts = 3
        corrections_made = []
        
        for attempt in range(max_attempts):
            corrected_sql = sql
            
            # Apply corrections for this attempt
            if attempt == 0:
                # First attempt: Try original query (no corrections)
                corrected_sql = sql
            elif attempt == 1:
                # Second attempt: Apply schema-aware corrections based on error
                last_error = getattr(self, '_last_error', '')
                corrected_sql, schema_corrections = self._apply_schema_aware_corrections(sql, last_error)
                corrections_made.extend(schema_corrections)
            elif attempt == 2:
                # Third attempt: Apply fallback semantic corrections
                corrected_sql, semantic_corrections = self._apply_semantic_corrections(
                    sql, SEMANTIC_COLUMN_GROUPS)
                corrections_made.extend(semantic_corrections)
            elif attempt == 2:
                # Third attempt: Apply learned corrections from database
                corrected_sql, learned_corrections = self._apply_learned_corrections(sql)
                corrections_made.extend(learned_corrections)
            
            # Log corrections if any were made (debug mode only)
            if corrections_made and attempt > 0 and self.debug_mode:
                db_logger.info("SELF_CORRECTION (attempt {}): Applied corrections: {}".format(
                    attempt + 1, ', '.join(corrections_made)))
                db_logger.debug("SELF_CORRECTION: Original query: {}".format(sql[:200]))
                db_logger.debug("SELF_CORRECTION: Corrected query: {}".format(corrected_sql[:200]))
            
            # Validate query safety on corrected SQL
            try:
                self.validate_query_safety(corrected_sql)
            except ValueError as e:
                db_logger.error("SELF_CORRECTION: Safety validation failed on attempt {}: {}".format(
                    attempt + 1, str(e)))
                continue
            
            # Log query execution start (debug mode only)
            if self.debug_mode:
                db_logger.info("Executing query (attempt {}): {}".format(
                    attempt + 1, corrected_sql[:200] + ('...' if len(corrected_sql) > 200 else '')))
                if params:
                    db_logger.debug(param_str)
            
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Execute query with timeout handling
                    cursor.execute(corrected_sql, params or [])
                    
                    # Fetch results with row limit
                    rows = cursor.fetchmany(self.max_result_rows + 1)
                    
                    # Check if we hit the row limit
                    hit_limit = len(rows) > self.max_result_rows
                    if hit_limit:
                        rows = rows[:self.max_result_rows]
                        db_logger.warning("Query result truncated to {} rows".format(self.max_result_rows))
                    
                    # Convert rows to list of dictionaries
                    columns = [description[0] for description in cursor.description] if cursor.description else []
                    results = []

                    for row in rows:
                        try:
                            if hasattr(row, 'keys'):
                                row_dict = dict(row)
                            else:
                                row_dict = {columns[i]: row[i] for i in range(len(columns))}
                            results.append(row_dict)
                        except Exception as e:
                            db_logger.warning("Row conversion issue: {} - using manual conversion".format(e))
                            row_dict = {}
                            for i, col_name in enumerate(columns):
                                try:
                                    row_dict[col_name] = row[i] if i < len(row) else None
                                except (IndexError, TypeError):
                                    row_dict[col_name] = None
                            results.append(row_dict)
                    
                    execution_time = time.time() - start_time
                    
                    # SUCCESS! Store successful corrections for future learning
                    if corrections_made and attempt > 0:
                        self._store_successful_corrections(corrections_made, corrected_sql)
                        if self.debug_mode:
                            db_logger.info("SELF_CORRECTION: Success on attempt {} with corrections: {}".format(
                                attempt + 1, ', '.join(corrections_made)))
                    
                    # Log execution success (debug mode only)
                    if self.debug_mode:
                        db_logger.info("Query completed: {} rows, {:.3f} seconds{}".format(
                            len(results), execution_time, 
                            " (with corrections)" if corrections_made else ""))
                    
                    # Return comprehensive result object
                    return {
                        'success': True,
                        'data': results,
                        'columns': columns,
                        'row_count': len(results),
                        'execution_time': execution_time,
                        'hit_limit': hit_limit,
                        'timestamp': eastern_isoformat(),
                        'corrections_applied': corrections_made,
                        'correction_attempt': attempt + 1,
                        'self_corrected': len(corrections_made) > 0 and attempt > 0
                    }
                    
            except sqlite3.Error as e:
                error_msg = str(e).lower()
                db_logger.warning("Query attempt {} failed: {}".format(attempt + 1, str(e)))
                # Store error for context in next attempt
                self._last_error = str(e)

                # Don't retry if this is the last attempt or if it's a non-correctable error
                if attempt == max_attempts - 1 or self._is_non_correctable_error(error_msg):
                    execution_time = time.time() - start_time
                    final_error = "Query execution failed after {} attempts: {}".format(
                        max_attempts, str(e))
                    db_logger.error("{} (after {:.3f} seconds)".format(final_error, execution_time))
                    
                    return {
                        'success': False,
                        'error': final_error,
                        'original_error': str(e),
                        'error_type': type(e).__name__,
                        'execution_time': execution_time,
                        'timestamp': eastern_isoformat(),
                        'corrections_attempted': corrections_made,
                        'max_attempts_reached': True
                    }
                
                # Continue to next attempt for correctable errors
                continue
                
            except Exception as e:
                execution_time = time.time() - start_time
                error_msg = "Unexpected error during query execution: {}".format(e)
                db_logger.error("{} (after {:.3f} seconds)".format(error_msg, execution_time))
                
                return {
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'execution_time': execution_time,
                    'timestamp': eastern_isoformat(),
                    'corrections_attempted': corrections_made
                }
        
        # If we get here, all attempts failed
        execution_time = time.time() - start_time
        final_error = "Query failed after {} correction attempts".format(max_attempts)
        db_logger.error("{} (after {:.3f} seconds)".format(final_error, execution_time))
        
        return {
            'success': False,
            'error': final_error,
            'error_type': 'MaxAttemptsExceeded',
            'execution_time': execution_time,
            'timestamp': eastern_isoformat(),
            'corrections_attempted': corrections_made,
            'max_attempts_reached': True
        }
    
    def format_results(self, query_result):
        """Format query results for Claude consumption
        
        Args:
            query_result: Result from execute_query()
            
        Returns:
            str: Formatted string suitable for Claude
        """
        if not query_result['success']:
            return "Query failed: {}".format(query_result['error'])
        
        data = query_result['data']
        columns = query_result['columns']
        row_count = query_result['row_count']
        
        if row_count == 0:
            return "Query returned no results."
        
        # For small result sets, format as readable table
        if row_count <= 10 and len(columns) <= 8:
            formatted = "Query Results ({} rows):\n".format(row_count)
            formatted += "-" * 50 + "\n"
            
            for i, row in enumerate(data):
                formatted += "Row {}:\n".format(i + 1)
                for col in columns:
                    value = row[col]
                    if value is None:
                        value = 'NULL'
                    formatted += "  {}: {}\n".format(col, value)
                formatted += "\n"
        
        # For larger result sets, provide summary
        else:
            formatted = "Query Results Summary:\n"
            formatted += "  Rows returned: {}\n".format(row_count)
            formatted += "  Columns: {}\n".format(', '.join(columns))
            
            if query_result['hit_limit']:
                formatted += "  Note: Results truncated to {} rows\n".format(self.max_result_rows)
            
            # Show first few rows as sample
            formatted += "\nSample data (first 3 rows):\n"
            for i, row in enumerate(data[:3]):
                formatted += "Row {}: {}\n".format(i + 1, dict(row))
        
        formatted += "\nExecution time: {:.3f} seconds".format(query_result['execution_time'])
        return formatted
    
    def _apply_legacy_corrections(self, sql):
        """Apply table-aware column corrections using schema intelligence"""
        # Only apply corrections on FIRST attempt (not preemptively)
        return sql, []  # Return original SQL unchanged

    def _apply_schema_aware_corrections(self, sql, error_message):
        """Apply intelligent table-aware corrections based on schema and error context"""
        corrections_made = []
        corrected_sql = sql
        
        # Extract table name from SQL
        table_name = self._extract_table_name(sql)
        if not table_name:
            return corrected_sql, corrections_made
        
        # Get schema for this specific table
        try:
            schema = self.get_database_schema()
            if not schema or 'tables' not in schema or table_name not in schema['tables']:
                return corrected_sql, corrections_made
            
            available_columns = [col['name'].lower() for col in schema['tables'][table_name]['columns']]
            
        except Exception as e:
            db_logger = logging.getLogger('oracle.database')
            db_logger.warning("Schema lookup failed for table {}: {}".format(table_name, str(e)))
            return corrected_sql, corrections_made
        
        # Table-specific correction mappings based on actual schema
        TABLE_CORRECTIONS = {
            'historical_prices': {
                'price': 'close_price',
                'cost': 'close_price', 
                'date': 'trade_date'
            },
            'option_contracts': {
                'price': 'last_price',          # ← KEY FIX!
                'cost': 'last_price',
                'premium': 'premium_value',
                'date': 'trade_date'
            },
            'flow_alerts': {
                'price': 'premium_value',
                'date': 'alert_timestamp'
            },
            'options_symbol_summary': {
                'price': 'close_price',  # This table likely doesn't have price data
                'date': 'trade_date'
            }
        }
        
        # Get corrections for this table
        table_corrections = TABLE_CORRECTIONS.get(table_name, {})
        
        # Apply corrections only for columns that actually exist
        for wrong_col, correct_col in table_corrections.items():
            if correct_col.lower() in available_columns:
                pattern = r'\b' + re.escape(wrong_col) + r'\b'
                if re.search(pattern, corrected_sql, re.IGNORECASE):
                    def replace_preserving_case(match):
                        original = match.group()
                        if original.isupper():
                            return correct_col.upper()
                        elif original.istitle():
                            return correct_col.title()
                        else:
                            return correct_col.lower()
                    
                    old_sql = corrected_sql
                    corrected_sql = re.sub(pattern, replace_preserving_case, corrected_sql, flags=re.IGNORECASE)
                    
                    if old_sql != corrected_sql:
                        corrections_made.append("'{}' -> '{}' (table: {})".format(
                            wrong_col, correct_col, table_name))
        
        return corrected_sql, corrections_made

    def _extract_table_name(self, sql):
        """Extract the main table name from SQL query"""
        import re
        
        # Look for FROM clause
        from_match = re.search(r'\bFROM\s+(\w+)', sql, re.IGNORECASE)
        if from_match:
            return from_match.group(1).lower()
        
        # Look for UPDATE clause  
        update_match = re.search(r'\bUPDATE\s+(\w+)', sql, re.IGNORECASE)
        if update_match:
            return update_match.group(1).lower()
        
        return None

    def _apply_semantic_corrections(self, sql, semantic_groups):
        """Apply semantic column corrections based on meaning rather than exact match"""
        corrected_sql = sql
        corrections_made = []
        
        for group_name, group_config in semantic_groups.items():
            aliases = group_config['aliases']
            targets = group_config['targets']
            preferred = group_config['preferred']
            
            for alias in aliases:
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, corrected_sql, re.IGNORECASE):
                    # Check if any target columns exist (would need schema access)
                    # For now, use preferred default
                    def replace_preserving_case(match):
                        original = match.group()
                        if original.isupper():
                            return preferred.upper()
                        elif original.istitle():
                            return preferred.title()
                        else:
                            return preferred.lower()
                    
                    old_sql = corrected_sql
                    corrected_sql = re.sub(pattern, replace_preserving_case, corrected_sql, flags=re.IGNORECASE)
                    
                    if old_sql != corrected_sql:
                        corrections_made.append("'{}' -> '{}' (semantic)".format(alias, preferred))
        
        return corrected_sql, corrections_made

    def _apply_learned_corrections(self, sql):
        """Apply corrections learned from previous successful fixes"""
        corrections_made = []
        corrected_sql = sql
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get learned corrections ordered by success count
                cursor.execute("""
                    SELECT original_column, corrected_column, success_count
                    FROM query_corrections 
                    ORDER BY success_count DESC, confidence_score DESC
                """)
                
                learned_corrections = cursor.fetchall()
                
                for original, corrected, success_count in learned_corrections:
                    pattern = r'\b' + re.escape(original) + r'\b'
                    if re.search(pattern, corrected_sql, re.IGNORECASE):
                        def replace_preserving_case(match):
                            orig = match.group()
                            if orig.isupper():
                                return corrected.upper()
                            elif orig.istitle():
                                return corrected.title()
                            else:
                                return corrected.lower()
                        
                        old_sql = corrected_sql
                        corrected_sql = re.sub(pattern, replace_preserving_case, corrected_sql, flags=re.IGNORECASE)
                        
                        if old_sql != corrected_sql:
                            corrections_made.append("'{}' -> '{}' (learned, {} successes)".format(
                                original, corrected, success_count))
                            break  # Apply one learned correction at a time
                
        except Exception as e:
            # If learning system fails, continue without learned corrections
            pass
        
        return corrected_sql, corrections_made

    def _store_successful_corrections(self, corrections, final_sql):
        """Store successful corrections in database for future learning"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                for correction in corrections:
                    # Parse correction string like "'price' -> 'close_price'"
                    if " -> " in correction:
                        parts = correction.split(" -> ")
                        original = parts[0].strip("'\"")
                        corrected = parts[1].split(" ")[0].strip("'\"")  # Remove any trailing info
                        
                        # Check if this correction already exists
                        cursor.execute("""
                            SELECT id, success_count FROM query_corrections 
                            WHERE original_column = ? AND corrected_column = ?
                        """, (original, corrected))
                        
                        existing = cursor.fetchone()
                        current_time = eastern_isoformat()
                        
                        if existing:
                            # Update existing correction
                            cursor.execute("""
                                UPDATE query_corrections 
                                SET success_count = success_count + 1,
                                    last_used = ?,
                                    confidence_score = MIN(confidence_score + 0.1, 1.0)
                                WHERE id = ?
                            """, (current_time, existing[0]))
                            
                            # Also store table context for better learning
                            table_name = self._extract_table_name(final_sql)
                            if table_name:
                                cursor.execute("""
                                    UPDATE query_corrections 
                                    SET table_context = ?
                                    WHERE original_column = ? AND corrected_column = ?
                                """, (table_name, original, corrected))
                        else:
                            # Insert new correction with table context
                            table_name = self._extract_table_name(final_sql)
                            cursor.execute("""
                                INSERT INTO query_corrections 
                                (original_column, corrected_column, table_context, first_seen, last_used)
                                VALUES (?, ?, ?, ?, ?)
                            """, (original, corrected, table_name, current_time, current_time))
                
                conn.commit()
                
        except Exception as e:
            # Learning system failure shouldn't break the main query
            db_logger = logging.getLogger('oracle.database')
            db_logger.warning("Failed to store correction learning: {}".format(str(e)))

    def _is_non_correctable_error(self, error_msg):
        """Determine if an error can't be fixed by column corrections"""
        non_correctable_patterns = [
            'permission denied',
            'database is locked',
            'disk i/o error',
            'out of memory',
            'syntax error near',  # Complex syntax errors
            'cannot start a transaction'
        ]
        
        return any(pattern in error_msg for pattern in non_correctable_patterns)

    def get_database_schema(self):
        """Get database schema information
        
        Returns:
            dict: Schema information including tables and columns
        """
        if self._schema_cache:
            return self._schema_cache
        
        logging.info("Retrieving database schema information")
        
        schema_info = {
            'tables': {},
            'total_tables': 0,
            'generated_at': eastern_isoformat()
        }
        
        try:
            # Get all tables
            tables_result = self.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            
            if not tables_result['success']:
                return {'error': 'Failed to retrieve table list'}
            
            table_names = [row['name'] for row in tables_result['data']]
            schema_info['total_tables'] = len(table_names)
            
            # Get column information for each table
            for table_name in table_names:
                columns_result = self.execute_query(
                    "PRAGMA table_info({})".format(table_name)
                )
                
                if columns_result['success']:
                    columns = []
                    for col_row in columns_result['data']:
                        columns.append({
                            'name': col_row['name'],
                            'type': col_row['type'],
                            'nullable': not col_row['notnull'],
                            'primary_key': bool(col_row['pk'])
                        })
                    
                    schema_info['tables'][table_name] = {
                        'columns': columns,
                        'column_count': len(columns)
                    }
                else:
                    schema_info['tables'][table_name] = {
                        'error': 'Could not retrieve column information'
                    }
            
            # Cache the schema
            self._schema_cache = schema_info
            logging.info("Schema information cached for {} tables".format(len(table_names)))
            
            return schema_info
            
        except Exception as e:
            error_msg = "Failed to retrieve database schema: {}".format(e)
            logging.error(error_msg)
            return {'error': error_msg}
    
    def check_database_health(self):
        """Perform comprehensive database health checks
        
        Returns:
            dict: Health check results
        """
        logging.info("Performing database health check")
        
        health_status = {
            'overall_status': 'unknown',
            'checks': {},
            'timestamp': eastern_isoformat()
        }
        
        checks = []
        
        # Check 1: Basic connectivity
        try:
            with self.get_connection() as conn:
                conn.execute("SELECT 1")
            checks.append(('connectivity', True, 'Database connection successful'))
        except Exception as e:
            checks.append(('connectivity', False, 'Connection failed: {}'.format(e)))
        
        # Check 2: Schema integrity
        try:
            schema = self.get_database_schema()
            if 'error' in schema:
                checks.append(('schema', False, schema['error']))
            else:
                checks.append(('schema', True, '{} tables found'.format(schema['total_tables'])))
        except Exception as e:
            checks.append(('schema', False, 'Schema check failed: {}'.format(e)))
        
        # Check 3: Key tables exist
        expected_tables = ['option_contracts', 'flow_alerts', 'symbol_baselines', 'symbol_metadata']
        missing_tables = []
        
        try:
            for table in expected_tables:
                result = self.execute_query("SELECT COUNT(*) as count FROM {}".format(table))
                if result['success']:
                    count = result['data'][0]['count']
                    checks.append((table, True, '{} rows'.format(count)))
                else:
                    missing_tables.append(table)
                    checks.append((table, False, 'Table not accessible'))
        except Exception as e:
            checks.append(('tables', False, 'Table check failed: {}'.format(e)))
        
        # Check 4: Query performance test
        try:
            start = time.time()
            result = self.execute_query("SELECT COUNT(*) FROM sqlite_master")
            duration = time.time() - start
            
            if result['success'] and duration < 5.0:
                checks.append(('performance', True, 'Query completed in {:.3f}s'.format(duration)))
            else:
                checks.append(('performance', False, 'Query too slow: {:.3f}s'.format(duration)))
        except Exception as e:
            checks.append(('performance', False, 'Performance test failed: {}'.format(e)))
        
        # Compile results
        health_status['checks'] = {check[0]: {'passed': check[1], 'message': check[2]} for check in checks}
        
        # Determine overall status
        failed_checks = [check for check in checks if not check[1]]
        if not failed_checks:
            health_status['overall_status'] = 'healthy'
        elif len(failed_checks) <= 1:
            health_status['overall_status'] = 'warning'
        else:
            health_status['overall_status'] = 'critical'
        
        logging.info("Database health check completed: {}".format(health_status['overall_status']))
        
        return health_status


# Quick validation if run directly
if __name__ == "__main__":
    print("Oracle Database Access Test")
    print("=" * 50)
    
    try:
        # Import and create config
        from oracle_config import OracleConfig
        config = OracleConfig()
        
        # Create database connection
        db = DatabaseConnection(config)
        print("✅ Database connection manager created")
        
        # Test basic query
        result = db.execute_query("SELECT COUNT(*) as total_tables FROM sqlite_master WHERE type='table'")
        if result['success']:
            table_count = result['data'][0]['total_tables']
            print("✅ Basic query successful: {} tables found".format(table_count))
        else:
            print("❌ Basic query failed: {}".format(result['error']))
        
        # Test query validation
        try:
            db.validate_query_safety("SELECT * FROM option_contracts LIMIT 5")
            print("✅ Query validation passed for safe query")
        except Exception as e:
            print("❌ Query validation failed: {}".format(e))
        
        try:
            db.validate_query_safety("DELETE FROM option_contracts")
            print("❌ Query validation should have failed for DELETE")
        except ValueError:
            print("✅ Query validation correctly rejected DELETE")
        
        # Test health check
        health = db.check_database_health()
        print("✅ Health check completed: {}".format(health['overall_status']))
        
    except Exception as e:
        print("❌ Database test failed: {}".format(e))
        import traceback
        traceback.print_exc()

    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - no special cleanup needed for our use case"""
        pass
