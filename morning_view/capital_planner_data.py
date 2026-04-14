"""
Capital Planner Data Access Layer

Manages JSON-based storage for capital planning positions.
No database writes - all data stored in planner_config.json and planner_data.json.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional

# Setup logging
logger = logging.getLogger(__name__)

# Paths to JSON files
PLANNER_DIR = Path(__file__).parent
CONFIG_FILE = PLANNER_DIR / "planner_config.json"
DATA_FILE = PLANNER_DIR / "planner_data.json"

# Default config if file missing/corrupted
DEFAULT_CONFIG = {
    "capital": {
        "total_capital": 3000,
        "target_position_size": 300,
        "warning_threshold_pct": 80
    },
    "defaults": {
        "default_entry_days_before": 14,
        "default_exit_days_before": 2
    },
    "archival": {
        "auto_archive_closed": False,
        "archive_after_days": 7
    }
}

# Default data structure
DEFAULT_DATA = {
    "version": "1.0",
    "last_updated": datetime.now().isoformat(),
    "positions": [],
    "archived_positions": []
}


# ========== Config Management ==========

def load_planner_config() -> dict:
    """Load planner configuration from JSON file.

    Returns:
        dict: Configuration with capital, defaults, archival settings
    """
    try:
        if not CONFIG_FILE.exists():
            logger.warning(f"Config file not found, creating with defaults: {CONFIG_FILE}")
            save_planner_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()

        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Validate structure (has required keys)
        required_keys = ["capital", "defaults", "archival"]
        if not all(key in config for key in required_keys):
            logger.warning("Config missing required keys, using defaults")
            return DEFAULT_CONFIG.copy()

        return config

    except json.JSONDecodeError as e:
        logger.error(f"Config file corrupted: {e}. Using defaults.")
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        logger.error(f"Error loading config: {e}. Using defaults.")
        return DEFAULT_CONFIG.copy()


def save_planner_config(config: dict) -> None:
    """Save planner configuration to JSON file.

    Args:
        config: Configuration dictionary
    """
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("Config saved successfully")
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise


# ========== Position Data Management ==========

def load_positions() -> list[dict]:
    """Load all positions from JSON file.

    Returns:
        list[dict]: List of position dictionaries
    """
    try:
        if not DATA_FILE.exists():
            logger.warning(f"Data file not found, creating empty: {DATA_FILE}")
            save_positions([])
            return []

        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate structure
        if not isinstance(data, dict) or "positions" not in data:
            logger.warning("Data file has invalid structure, returning empty")
            return []

        return data.get("positions", [])

    except json.JSONDecodeError as e:
        logger.error(f"Data file corrupted: {e}. Creating fresh file.")
        # Create fresh file
        _save_data_file(DEFAULT_DATA)
        return []
    except Exception as e:
        logger.error(f"Error loading positions: {e}")
        return []


def save_positions(positions: list[dict]) -> None:
    """Save positions to JSON file.

    Args:
        positions: List of position dictionaries
    """
    try:
        # Load existing data to preserve archived positions
        existing_data = _load_data_file()

        # Update positions and timestamp
        existing_data["positions"] = positions
        existing_data["last_updated"] = datetime.now().isoformat()

        _save_data_file(existing_data)
        logger.info(f"Saved {len(positions)} positions")

    except Exception as e:
        logger.error(f"Error saving positions: {e}")
        raise


def _load_data_file() -> dict:
    """Internal: Load entire data file structure.

    Returns:
        dict: Full data structure with positions and archived_positions
    """
    try:
        if not DATA_FILE.exists():
            return DEFAULT_DATA.copy()

        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Ensure all required keys exist
        if "positions" not in data:
            data["positions"] = []
        if "archived_positions" not in data:
            data["archived_positions"] = []
        if "version" not in data:
            data["version"] = "1.0"

        return data

    except Exception as e:
        logger.error(f"Error loading data file: {e}")
        return DEFAULT_DATA.copy()


def _save_data_file(data: dict) -> None:
    """Internal: Save entire data file structure.

    Args:
        data: Full data dictionary
    """
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving data file: {e}")
        raise


# ========== CRUD Operations ==========

def add_position(position: dict) -> str:
    """Add a new position to the planner.

    Args:
        position: Position dictionary (without ID)

    Returns:
        str: Generated position ID

    Raises:
        ValueError: If position validation fails
    """
    # Validate position
    is_valid, error_msg = validate_position(position)
    if not is_valid:
        raise ValueError(f"Invalid position: {error_msg}")

    # Generate ID
    position_id = _generate_position_id(
        position["symbol"],
        position["earnings_date"],
        position.get("entry_date", "")
    )

    # Add metadata
    position["id"] = position_id
    position["created_at"] = datetime.now().isoformat()
    position["updated_at"] = datetime.now().isoformat()

    # Load existing positions
    positions = load_positions()
    positions.append(position)

    # Save
    save_positions(positions)
    logger.info(f"Added position: {position_id}")

    return position_id


def update_position(position_id: str, updates: dict) -> bool:
    """Update an existing position.

    Args:
        position_id: Position ID to update
        updates: Dictionary of fields to update

    Returns:
        bool: True if updated, False if position not found
    """
    positions = load_positions()

    # Find position
    for pos in positions:
        if pos.get("id") == position_id:
            # Apply updates (but protect immutable fields)
            immutable_fields = ["id", "symbol", "earnings_date", "created_at"]
            for key, value in updates.items():
                if key not in immutable_fields:
                    pos[key] = value

            # Update timestamp
            pos["updated_at"] = datetime.now().isoformat()

            # Save
            save_positions(positions)
            logger.info(f"Updated position: {position_id}")
            return True

    logger.warning(f"Position not found for update: {position_id}")
    return False


def delete_position(position_id: str) -> bool:
    """Delete a position from the planner.

    Args:
        position_id: Position ID to delete

    Returns:
        bool: True if deleted, False if position not found
    """
    positions = load_positions()
    initial_count = len(positions)

    # Filter out the position
    positions = [p for p in positions if p.get("id") != position_id]

    if len(positions) < initial_count:
        save_positions(positions)
        logger.info(f"Deleted position: {position_id}")
        return True

    logger.warning(f"Position not found for deletion: {position_id}")
    return False


def get_position_by_id(position_id: str) -> Optional[dict]:
    """Get a position by ID.

    Args:
        position_id: Position ID

    Returns:
        dict or None: Position dictionary if found, None otherwise
    """
    positions = load_positions()

    for pos in positions:
        if pos.get("id") == position_id:
            return pos

    return None


# ========== Archival ==========

def archive_closed_positions(days_threshold: int = 7) -> int:
    """Archive closed positions older than threshold.

    Args:
        days_threshold: Archive positions closed more than N days ago

    Returns:
        int: Number of positions archived
    """
    positions = load_positions()
    data = _load_data_file()

    cutoff_date = (datetime.now() - timedelta(days=days_threshold)).date()

    # Separate positions into active and to-archive
    active_positions = []
    to_archive = []

    for pos in positions:
        if pos.get("status") == "closed":
            # Check updated_at timestamp
            try:
                updated_dt = datetime.fromisoformat(pos.get("updated_at", ""))
                if updated_dt.date() < cutoff_date:
                    to_archive.append(pos)
                else:
                    active_positions.append(pos)
            except (ValueError, TypeError):
                # If can't parse date, keep in active
                active_positions.append(pos)
        else:
            active_positions.append(pos)

    if to_archive:
        # Add to archived_positions
        if "archived_positions" not in data:
            data["archived_positions"] = []
        data["archived_positions"].extend(to_archive)

        # Update active positions
        data["positions"] = active_positions
        data["last_updated"] = datetime.now().isoformat()

        _save_data_file(data)
        logger.info(f"Archived {len(to_archive)} closed positions")

    return len(to_archive)


# ========== Capital Timeline Calculation ==========

def get_capital_timeline(positions: list[dict], days_ahead: int = 90) -> dict:
    """Calculate daily capital utilization for next N days.

    Args:
        positions: List of positions
        days_ahead: Number of days to calculate

    Returns:
        dict: {
            "daily": {"2025-10-12": 1100, ...},
            "weekly": {"2025-W41": 1100, ...},
            "peak_date": "2025-10-15",
            "peak_amount": 2600,
            "average": 1200
        }
    """
    # Filter to non-closed positions
    active_positions = [p for p in positions if p.get("status") != "closed"]

    # Calculate date range
    start_date = date.today()
    end_date = start_date + timedelta(days=days_ahead)

    # Daily capital locked
    daily_capital = {}
    current = start_date

    while current <= end_date:
        date_str = current.isoformat()
        total_locked = 0

        for pos in active_positions:
            try:
                entry = date.fromisoformat(pos["entry_date"])
                exit_date = date.fromisoformat(pos["exit_date"])

                # Position is active if current is between entry and exit
                if entry <= current <= exit_date:
                    cost = pos.get("estimated_total_cost", 0)
                    total_locked += cost
            except (ValueError, KeyError, TypeError):
                # Skip positions with invalid dates
                continue

        daily_capital[date_str] = total_locked
        current += timedelta(days=1)

    # Weekly aggregation (take max per week)
    weekly_capital = {}
    for date_str, amount in daily_capital.items():
        dt = date.fromisoformat(date_str)
        week_key = dt.strftime("%Y-W%W")

        if week_key not in weekly_capital or amount > weekly_capital[week_key]:
            weekly_capital[week_key] = amount

    # Peak and average
    if daily_capital:
        peak_date = max(daily_capital, key=daily_capital.get)
        peak_amount = daily_capital[peak_date]
        average = sum(daily_capital.values()) / len(daily_capital)
    else:
        peak_date = None
        peak_amount = 0
        average = 0

    return {
        "daily": daily_capital,
        "weekly": weekly_capital,
        "peak_date": peak_date,
        "peak_amount": peak_amount,
        "average": average
    }


# ========== Validation ==========

def validate_position(position: dict) -> tuple[bool, str]:
    """Validate a position dictionary.

    Args:
        position: Position dictionary to validate

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    # Required fields
    required_fields = [
        "symbol", "earnings_date", "entry_date", "exit_date",
        "num_contracts", "estimated_contract_price", "estimated_total_cost", "status"
    ]

    for field in required_fields:
        if field not in position:
            return False, f"Missing required field: {field}"

    # Validate types
    try:
        # Dates
        entry = date.fromisoformat(position["entry_date"])
        exit_date = date.fromisoformat(position["exit_date"])
        earnings = date.fromisoformat(position["earnings_date"])

        # Exit must be after entry
        if exit_date <= entry:
            return False, "Exit date must be after entry date"

        # Numeric values
        contracts = int(position["num_contracts"])
        if contracts <= 0:
            return False, "Number of contracts must be positive"

        price = float(position["estimated_contract_price"])
        if price <= 0:
            return False, "Contract price must be positive"

        cost = float(position["estimated_total_cost"])
        if cost <= 0:
            return False, "Total cost must be positive"

        # Symbol
        symbol = str(position["symbol"]).strip().upper()
        if not symbol or not symbol.isalnum():
            return False, "Invalid symbol format"

        # Notes length
        notes = position.get("notes", "")
        if len(notes) > 500:
            return False, "Notes exceed 500 character limit"

    except (ValueError, TypeError) as e:
        return False, f"Validation error: {str(e)}"

    return True, ""


# ========== Helper Functions ==========

def _generate_position_id(symbol: str, earnings_date: str, entry_date: str = "") -> str:
    """Generate unique position ID.

    Format: {symbol}_{earnings_date}_{sequence}

    Args:
        symbol: Stock symbol
        earnings_date: Earnings date (YYYY-MM-DD)
        entry_date: Entry date (for uniqueness)

    Returns:
        str: Generated position ID
    """
    # Clean symbol
    symbol = symbol.strip().upper()

    # Remove hyphens from dates
    earnings_clean = earnings_date.replace("-", "")

    # Check for existing IDs with same symbol+earnings
    positions = load_positions()
    existing_ids = [
        p["id"] for p in positions
        if p["id"].startswith(f"{symbol}_{earnings_clean}")
    ]

    # Determine sequence number
    if not existing_ids:
        sequence = 1
    else:
        # Extract sequence numbers
        sequences = []
        for pid in existing_ids:
            parts = pid.split("_")
            if len(parts) >= 3:
                try:
                    seq = int(parts[-1])
                    sequences.append(seq)
                except ValueError:
                    pass

        sequence = max(sequences) + 1 if sequences else 1

    return f"{symbol}_{earnings_clean}_{sequence:03d}"


# ========== Summary Functions ==========

def get_planner_summary() -> dict:
    """Get summary statistics for capital planner.

    Returns:
        dict: {
            "total_positions": 10,
            "by_status": {"planned": 5, "watching": 3, "entered": 2},
            "total_capital_deployed": 3000,
            "positions_next_week": 3
        }
    """
    positions = load_positions()

    # Count by status
    status_counts = {}
    for pos in positions:
        status = pos.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    # Total capital (non-closed positions)
    active_positions = [p for p in positions if p.get("status") != "closed"]
    total_capital = sum(p.get("estimated_total_cost", 0) for p in active_positions)

    # Positions in next 7 days
    today = date.today()
    next_week = today + timedelta(days=7)

    positions_next_week = 0
    for pos in active_positions:
        try:
            entry = date.fromisoformat(pos["entry_date"])
            if today <= entry <= next_week:
                positions_next_week += 1
        except (ValueError, KeyError, TypeError):
            continue

    return {
        "total_positions": len(positions),
        "by_status": status_counts,
        "total_capital_deployed": total_capital,
        "positions_next_week": positions_next_week
    }
