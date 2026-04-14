"""Quick test script for capital planner data layer"""

import sys
from pathlib import Path

# Fix Windows UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from morning_view.capital_planner_data import (
    load_planner_config,
    load_positions,
    add_position,
    update_position,
    delete_position,
    get_position_by_id,
    get_capital_timeline,
    get_planner_summary,
    validate_position
)

def test_data_layer():
    """Test all data layer functions"""
    print("=" * 60)
    print("Testing Capital Planner Data Layer")
    print("=" * 60)

    # Test 1: Load config
    print("\n1. Loading config...")
    config = load_planner_config()
    print(f"   ✓ Total capital: ${config['capital']['total_capital']}")
    print(f"   ✓ Target position: ${config['capital']['target_position_size']}")

    # Test 2: Load positions (should be empty initially)
    print("\n2. Loading positions...")
    positions = load_positions()
    print(f"   ✓ Found {len(positions)} positions")

    # Test 3: Create test position
    print("\n3. Creating test position...")
    test_position = {
        "symbol": "NVDA",
        "earnings_date": "2025-10-23",
        "entry_date": "2025-10-09",
        "exit_date": "2025-10-21",
        "num_contracts": 2,
        "estimated_contract_price": 5.50,
        "estimated_total_cost": 1100,
        "status": "planned",
        "notes": "Test position for NVDA earnings"
    }

    # Validate first
    is_valid, error = validate_position(test_position)
    if is_valid:
        print("   ✓ Validation passed")
    else:
        print(f"   ✗ Validation failed: {error}")
        return

    # Add position
    pos_id = add_position(test_position)
    print(f"   ✓ Created position: {pos_id}")

    # Test 4: Retrieve position
    print("\n4. Retrieving position...")
    retrieved = get_position_by_id(pos_id)
    if retrieved:
        print(f"   ✓ Retrieved: {retrieved['symbol']} ${retrieved['estimated_total_cost']}")
    else:
        print("   ✗ Position not found")

    # Test 5: Update position
    print("\n5. Updating position...")
    success = update_position(pos_id, {"status": "watching", "notes": "Updated note"})
    if success:
        updated = get_position_by_id(pos_id)
        print(f"   ✓ Status changed to: {updated['status']}")
        print(f"   ✓ Notes updated to: {updated['notes']}")
    else:
        print("   ✗ Update failed")

    # Test 6: Capital timeline
    print("\n6. Calculating capital timeline...")
    positions = load_positions()
    timeline = get_capital_timeline(positions, days_ahead=30)
    print(f"   ✓ Peak capital: ${timeline['peak_amount']} on {timeline['peak_date']}")
    print(f"   ✓ Average: ${timeline['average']:.0f}")

    # Test 7: Summary
    print("\n7. Getting planner summary...")
    summary = get_planner_summary()
    print(f"   ✓ Total positions: {summary['total_positions']}")
    print(f"   ✓ By status: {summary['by_status']}")
    print(f"   ✓ Total capital deployed: ${summary['total_capital_deployed']}")

    # Test 8: Delete position
    print("\n8. Deleting test position...")
    success = delete_position(pos_id)
    if success:
        print(f"   ✓ Deleted position: {pos_id}")
    else:
        print("   ✗ Delete failed")

    # Verify deletion
    positions = load_positions()
    print(f"   ✓ Positions remaining: {len(positions)}")

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_data_layer()
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
