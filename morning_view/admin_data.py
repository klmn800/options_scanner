#!/usr/bin/env python3
"""
Admin Data Layer - Write operations for Morning Views TUI

Provides database write functions for:
- Trading journal (append notes to earnings events)
- Earnings event lookups
- Symbol metadata and archive management
- Future: Portfolio tracking, file operations

Database: datalake.db (production database with WAL mode enabled)
"""

import sqlite3
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Database paths
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'data' / 'datalake.db'
SECTOR_ARCHIVE_DIR = PROJECT_ROOT / 'data' / 'sector_archive'


def lookup_earnings_event(symbol: str, earnings_date: str) -> Optional[Dict]:
    """
    Find earnings event by symbol and date.

    Args:
        symbol: Stock ticker symbol (e.g., "NVDA")
        earnings_date: ISO date string (YYYY-MM-DD)

    Returns:
        Dict with event details if found:
            - event_id, symbol, earnings_date, earnings_time
            - actual_eps, estimate_eps
            - notes, tags, note_type, sentiment
        None if not found

    Raises:
        sqlite3.Error: If database query fails
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT event_id, symbol, earnings_date, earnings_time,
                   actual_eps, estimated_eps, notes, tags, note_type, sentiment
            FROM earnings_events
            WHERE symbol = ? AND earnings_date = ?
        """, (symbol.upper(), earnings_date))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    except sqlite3.Error as e:
        logger.error(f"Database error in lookup_earnings_event: {e}")
        raise


def append_journal_note(symbol: str, earnings_date: str, note_data: Dict) -> Tuple[bool, str]:
    """
    Append note to existing earnings event or create new event stub.

    Args:
        symbol: Stock ticker symbol
        earnings_date: ISO date string (YYYY-MM-DD)
        note_data: Dict with:
            - 'notes': str (note text)
            - 'tags': str (comma-separated tags)
            - 'note_type': str (Trade|Observation|Pattern|Lesson)
            - 'sentiment': str (Bullish|Bearish|Neutral)

    Returns:
        Tuple of (success: bool, message: str)
        - (True, "Note appended...") on success
        - (False, "Database error...") on failure

    Notes:
        - Appends to existing notes with timestamp separator
        - Merges tags (comma-separated, no duplicates)
        - Creates new event if not found
        - Preserves form data on failure (caller responsibility)
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Check if event exists
        existing = lookup_earnings_event(symbol, earnings_date)

        if existing:
            # Append to existing notes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            separator = f"\n\n--- {timestamp} ---\n"

            existing_notes = existing['notes'] or ""
            updated_notes = existing_notes + separator + note_data['notes']

            # Merge tags (comma-separated, no duplicates)
            existing_tags = set((existing['tags'] or "").split(",")) if existing['tags'] else set()
            new_tags = set(note_data['tags'].split(",")) if note_data['tags'] else set()
            # Remove empty strings
            existing_tags.discard("")
            new_tags.discard("")
            merged_tags = ",".join(sorted(existing_tags | new_tags))

            cursor.execute("""
                UPDATE earnings_events
                SET notes = ?, tags = ?, note_type = ?, sentiment = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
            """, (updated_notes, merged_tags, note_data['note_type'],
                  note_data['sentiment'], existing['event_id']))

            message = f"Note appended to {symbol} {earnings_date}"

        else:
            # Create new event stub
            cursor.execute("""
                INSERT INTO earnings_events
                (symbol, earnings_date, notes, tags, note_type, sentiment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (symbol.upper(), earnings_date, note_data['notes'], note_data['tags'],
                  note_data['note_type'], note_data['sentiment']))

            message = f"New event created for {symbol} {earnings_date}"

        conn.commit()
        conn.close()
        logger.info(f"Journal note saved: {message}")
        return True, message

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            return False, "Database busy. Pipeline may be running. Try again."
        else:
            return False, f"Database error: {str(e)}"

    except sqlite3.Error as e:
        logger.error(f"Database error in append_journal_note: {e}")
        return False, f"Database error: {str(e)}"

    except Exception as e:
        logger.error(f"Unexpected error in append_journal_note: {e}")
        return False, f"Unexpected error: {str(e)}"


# ============================================================================
# Symbol Metadata & Archive Management Functions
# ============================================================================

def get_symbol_metadata(symbol: str) -> Optional[Dict]:
    """
    Get symbol's archive assignment and company info.

    Args:
        symbol: Stock ticker symbol (e.g., "NVDA")

    Returns:
        Dict with:
            - symbol: str
            - company_name: str
            - sector: str
            - industry: str
            - archive_db: str
        None if symbol not found

    Raises:
        sqlite3.Error: If database query fails
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT symbol, company_name, sector, industry, archive_db
            FROM symbol_metadata
            WHERE symbol = ?
        """, (symbol.upper(),))

        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None

    except sqlite3.Error as e:
        logger.error(f"Database error in get_symbol_metadata: {e}")
        raise


def update_symbol_archive(symbol: str, new_archive: str) -> Tuple[bool, str]:
    """
    Update symbol's archive_db field in production database.

    Args:
        symbol: Stock ticker symbol
        new_archive: New archive database name (e.g., "crypto")

    Returns:
        (True, "Success message") or (False, "Error message")
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()

        # Verify symbol exists
        cursor.execute("SELECT symbol FROM symbol_metadata WHERE symbol = ?", (symbol.upper(),))
        if not cursor.fetchone():
            conn.close()
            return False, f"Symbol '{symbol}' not found in symbol_metadata"

        # Update archive_db
        cursor.execute("""
            UPDATE symbol_metadata
            SET archive_db = ?
            WHERE symbol = ?
        """, (new_archive, symbol.upper()))

        conn.commit()
        rows_updated = cursor.rowcount
        conn.close()

        if rows_updated > 0:
            logger.info(f"Updated {symbol} archive_db to '{new_archive}'")
            return True, f"Archive updated: {symbol} → {new_archive}"
        else:
            return False, f"No changes made (symbol not found or archive unchanged)"

    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            return False, "Database busy. Pipeline may be running. Try again."
        else:
            return False, f"Database error: {str(e)}"

    except sqlite3.Error as e:
        logger.error(f"Database error in update_symbol_archive: {e}")
        return False, f"Database error: {str(e)}"

    except Exception as e:
        logger.error(f"Unexpected error in update_symbol_archive: {e}")
        return False, f"Unexpected error: {str(e)}"


def get_available_archives() -> List[str]:
    """
    List all sector archives from filesystem AND database.

    Returns:
        Sorted list of archive names (e.g., ["airlines", "crypto", "technology"])

    Implementation:
        - Scans data/sector_archive/*.db files
        - Queries DISTINCT archive_db from symbol_metadata
        - Returns union, sorted
    """
    archives = set()

    # Get archives from filesystem
    if SECTOR_ARCHIVE_DIR.exists():
        for file_path in SECTOR_ARCHIVE_DIR.glob("*.db"):
            # Exclude backup files and special databases
            if not file_path.name.startswith('.') and not file_path.name.endswith('-wal') and not file_path.name.endswith('-shm'):
                archive_name = file_path.stem  # filename without .db extension
                archives.add(archive_name)

    # Get archives from database
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT archive_db FROM symbol_metadata WHERE archive_db IS NOT NULL")
        for row in cursor.fetchall():
            archives.add(row[0])
        conn.close()
    except sqlite3.Error as e:
        logger.warning(f"Could not query database for archives: {e}")

    return sorted(list(archives))


def get_archive_stats() -> List[Dict]:
    """
    Get statistics for all sector archives.

    Returns:
        List of dicts with:
            - archive_name: str
            - symbol_count: int (from symbol_metadata)
            - file_size_bytes: int (from filesystem)
            - file_size_human: str (e.g., "1.5 GB")
            - last_modified: str (ISO format)
    """
    stats = []

    # Get all archives
    archives = get_available_archives()

    for archive_name in archives:
        archive_path = SECTOR_ARCHIVE_DIR / f"{archive_name}.db"

        # Get symbol count from database
        symbol_count = 0
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM symbol_metadata WHERE archive_db = ?",
                (archive_name,)
            )
            symbol_count = cursor.fetchone()[0]
            conn.close()
        except sqlite3.Error as e:
            logger.warning(f"Could not get symbol count for {archive_name}: {e}")

        # Get file stats
        file_size_bytes = 0
        file_size_human = "N/A"
        last_modified = "N/A"

        if archive_path.exists():
            try:
                file_size_bytes = archive_path.stat().st_size
                file_size_human = _format_file_size(file_size_bytes)
                last_modified = datetime.fromtimestamp(archive_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError as e:
                logger.warning(f"Could not get file stats for {archive_name}: {e}")

        stats.append({
            'archive_name': archive_name,
            'symbol_count': symbol_count,
            'file_size_bytes': file_size_bytes,
            'file_size_human': file_size_human,
            'last_modified': last_modified
        })

    return stats


def estimate_migration_rows(symbol: str, from_archive: str) -> Dict[str, int]:
    """
    Estimate row counts for symbol migration.

    Args:
        symbol: Stock ticker
        from_archive: Source archive name

    Returns:
        Dict mapping table_name → row_count
        Example: {"flow_options_scans": 45000, "option_contracts": 1200, ...}
    """
    source_path = SECTOR_ARCHIVE_DIR / f"{from_archive}.db"

    if not source_path.exists():
        logger.error(f"Source archive not found: {source_path}")
        return {}

    row_counts = {}

    # Tables to check
    tables = [
        'flow_options_scans',
        'option_contracts',
        'flow_alerts',
        'flow_symbol_summary',
        'option_symbol_summary',
        'historical_prices',
        'earnings_events',
        'earnings_upcoming',
        'news_articles',
        'news_symbol_sentiment',
        'alert_contract_tracking',
        'symbol_metadata'
    ]

    try:
        conn = sqlite3.connect(str(source_path))
        cursor = conn.cursor()

        for table_name in tables:
            try:
                # Check if table has 'symbol' column
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [row[1] for row in cursor.fetchall()]

                if 'symbol' in columns:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE symbol = ?", (symbol.upper(),))
                    count = cursor.fetchone()[0]
                    if count > 0:
                        row_counts[table_name] = count
            except sqlite3.Error:
                # Table might not exist in this archive
                pass

        conn.close()

    except sqlite3.Error as e:
        logger.error(f"Error estimating migration rows: {e}")

    return row_counts


def _format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string (e.g., "1.5 GB", "234.5 MB", "15.2 KB")
    """
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    elif size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    elif size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    else:
        return f"{size_bytes} B"
