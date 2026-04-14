#!/usr/bin/env python3
"""
Auto-Fix State Manager
======================
Tracks fix attempts and prevents infinite loops in self-healing system.

Safety Features:
- Max 3 fix attempts per unique error
- 5-minute cooldown between attempts
- Circuit breaker after consecutive failures
- Human override support

Author: Ben (with Claude)
Date: 2025-10-16
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


class AutoFixManager:
    """Manages auto-fix state and enforces safety limits"""

    def __init__(self, state_file="data/auto_fix_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(exist_ok=True)
        self.state = self._load_state()

        # Safety limits
        self.MAX_ATTEMPTS = 3
        self.COOLDOWN_MINUTES = 5
        self.CIRCUIT_BREAKER_THRESHOLD = 3  # Consecutive failures

    def _load_state(self):
        """Load state from JSON file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load auto-fix state: {e}")
                return self._default_state()
        return self._default_state()

    def _default_state(self):
        """Return default state structure"""
        return {
            "errors": {},
            "circuit_breaker_active": False,
            "consecutive_failures": 0,
            "last_success": None,
            "disabled": False
        }

    def _save_state(self):
        """Save state to JSON file"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"Error: Could not save auto-fix state: {e}")

    def _hash_error(self, error_message, file_path=None):
        """Create unique hash for error tracking"""
        key = f"{error_message}:{file_path or 'unknown'}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def should_attempt_fix(self, error_message, file_path=None):
        """Determine if auto-fix should be attempted

        Args:
            error_message: The error message text
            file_path: Optional file path where error occurred

        Returns:
            tuple: (should_fix: bool, reason: str)
        """
        # Check if auto-fix is disabled
        if self.state.get("disabled", False):
            return False, "Auto-fix is disabled (human override active)"

        # Check circuit breaker
        if self.state.get("circuit_breaker_active", False):
            return False, f"Circuit breaker active ({self.state['consecutive_failures']} consecutive failures)"

        # Get error history
        error_hash = self._hash_error(error_message, file_path)
        error_state = self.state["errors"].get(error_hash, {
            "attempts": 0,
            "last_attempt": None,
            "fixed": False,
            "error_message": error_message,
            "file_path": file_path
        })

        # Check if already fixed
        if error_state.get("fixed", False):
            return False, "Error already marked as fixed"

        # Check max attempts
        if error_state["attempts"] >= self.MAX_ATTEMPTS:
            return False, f"Max fix attempts reached ({self.MAX_ATTEMPTS})"

        # Check cooldown period
        if error_state["last_attempt"]:
            last_attempt = datetime.fromisoformat(error_state["last_attempt"])
            cooldown_end = last_attempt + timedelta(minutes=self.COOLDOWN_MINUTES)
            if datetime.now() < cooldown_end:
                remaining = (cooldown_end - datetime.now()).seconds // 60
                return False, f"Cooldown active ({remaining} minutes remaining)"

        return True, "OK"

    def record_attempt(self, error_message, file_path=None):
        """Record that a fix attempt is being made

        Args:
            error_message: The error message text
            file_path: Optional file path where error occurred

        Returns:
            str: Error hash for tracking
        """
        error_hash = self._hash_error(error_message, file_path)

        # Get or create error state
        if error_hash not in self.state["errors"]:
            self.state["errors"][error_hash] = {
                "attempts": 0,
                "last_attempt": None,
                "fixed": False,
                "error_message": error_message,
                "file_path": file_path,
                "first_seen": datetime.now().isoformat()
            }

        # Update attempt tracking
        self.state["errors"][error_hash]["attempts"] += 1
        self.state["errors"][error_hash]["last_attempt"] = datetime.now().isoformat()

        self._save_state()
        return error_hash

    def record_success(self, error_hash):
        """Record successful fix

        Args:
            error_hash: The error hash from record_attempt()
        """
        if error_hash in self.state["errors"]:
            self.state["errors"][error_hash]["fixed"] = True
            self.state["errors"][error_hash]["fixed_at"] = datetime.now().isoformat()

        # Reset circuit breaker on success
        self.state["consecutive_failures"] = 0
        self.state["circuit_breaker_active"] = False
        self.state["last_success"] = datetime.now().isoformat()

        self._save_state()

    def record_failure(self, error_hash):
        """Record failed fix attempt

        Args:
            error_hash: The error hash from record_attempt()
        """
        if error_hash in self.state["errors"]:
            self.state["errors"][error_hash]["last_failure"] = datetime.now().isoformat()

        # Increment consecutive failures
        self.state["consecutive_failures"] += 1

        # Activate circuit breaker if threshold reached
        if self.state["consecutive_failures"] >= self.CIRCUIT_BREAKER_THRESHOLD:
            self.state["circuit_breaker_active"] = True
            self.state["circuit_breaker_activated_at"] = datetime.now().isoformat()

        self._save_state()

    def disable_auto_fix(self, reason="Manual override"):
        """Disable auto-fix system (human intervention)

        Args:
            reason: Reason for disabling
        """
        self.state["disabled"] = True
        self.state["disabled_reason"] = reason
        self.state["disabled_at"] = datetime.now().isoformat()
        self._save_state()

    def enable_auto_fix(self):
        """Re-enable auto-fix system"""
        self.state["disabled"] = False
        self.state["enabled_at"] = datetime.now().isoformat()
        self._save_state()

    def reset_circuit_breaker(self):
        """Manually reset circuit breaker"""
        self.state["circuit_breaker_active"] = False
        self.state["consecutive_failures"] = 0
        self.state["circuit_breaker_reset_at"] = datetime.now().isoformat()
        self._save_state()

    def get_status(self):
        """Get current auto-fix system status

        Returns:
            dict: Status information
        """
        total_errors = len(self.state["errors"])
        fixed_errors = sum(1 for e in self.state["errors"].values() if e.get("fixed", False))
        active_errors = total_errors - fixed_errors

        return {
            "enabled": not self.state.get("disabled", False),
            "circuit_breaker_active": self.state.get("circuit_breaker_active", False),
            "consecutive_failures": self.state.get("consecutive_failures", 0),
            "total_errors_tracked": total_errors,
            "fixed_errors": fixed_errors,
            "active_errors": active_errors,
            "last_success": self.state.get("last_success"),
        }

    def clear_old_errors(self, days=7):
        """Clear error history older than specified days

        Args:
            days: Number of days to keep
        """
        cutoff = datetime.now() - timedelta(days=days)

        errors_to_remove = []
        for error_hash, error_state in self.state["errors"].items():
            first_seen = datetime.fromisoformat(error_state.get("first_seen", datetime.now().isoformat()))
            if first_seen < cutoff and error_state.get("fixed", False):
                errors_to_remove.append(error_hash)

        for error_hash in errors_to_remove:
            del self.state["errors"][error_hash]

        self._save_state()
        return len(errors_to_remove)


def main():
    """CLI for testing and managing auto-fix state"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='Auto-Fix State Manager')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--disable', action='store_true', help='Disable auto-fix')
    parser.add_argument('--enable', action='store_true', help='Enable auto-fix')
    parser.add_argument('--reset-breaker', action='store_true', help='Reset circuit breaker')
    parser.add_argument('--clear-old', type=int, metavar='DAYS', help='Clear errors older than N days')
    parser.add_argument('--test', action='store_true', help='Run test scenario')

    args = parser.parse_args()

    manager = AutoFixManager()

    if args.status:
        status = manager.get_status()
        print("\n" + "=" * 70)
        print("AUTO-FIX SYSTEM STATUS")
        print("=" * 70)
        print(f"Enabled: {'✅ YES' if status['enabled'] else '❌ NO'}")
        print(f"Circuit Breaker: {'⚠️  ACTIVE' if status['circuit_breaker_active'] else '✅ Inactive'}")
        print(f"Consecutive Failures: {status['consecutive_failures']}")
        print(f"Total Errors Tracked: {status['total_errors_tracked']}")
        print(f"Fixed Errors: {status['fixed_errors']}")
        print(f"Active Errors: {status['active_errors']}")
        print(f"Last Success: {status['last_success'] or 'Never'}")
        print("=" * 70)

    elif args.disable:
        manager.disable_auto_fix()
        print("✅ Auto-fix disabled")

    elif args.enable:
        manager.enable_auto_fix()
        print("✅ Auto-fix enabled")

    elif args.reset_breaker:
        manager.reset_circuit_breaker()
        print("✅ Circuit breaker reset")

    elif args.clear_old:
        removed = manager.clear_old_errors(days=args.clear_old)
        print(f"✅ Removed {removed} old error(s)")

    elif args.test:
        print("\n" + "=" * 70)
        print("AUTO-FIX MANAGER TEST")
        print("=" * 70)

        # Test 1: Check if fix should be attempted
        error_msg = "Test error: division by zero"
        should_fix, reason = manager.should_attempt_fix(error_msg, "test.py")
        print(f"\nTest 1 - Should attempt fix: {should_fix}")
        print(f"Reason: {reason}")

        # Test 2: Record attempt
        if should_fix:
            error_hash = manager.record_attempt(error_msg, "test.py")
            print(f"\nTest 2 - Recorded attempt: {error_hash}")

        # Test 3: Check again (cooldown should prevent)
        should_fix, reason = manager.should_attempt_fix(error_msg, "test.py")
        print(f"\nTest 3 - Should attempt again: {should_fix}")
        print(f"Reason: {reason}")

        # Test 4: Status
        status = manager.get_status()
        print(f"\nTest 4 - Status:")
        print(f"  Active errors: {status['active_errors']}")

        print("\n✅ Test complete")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
