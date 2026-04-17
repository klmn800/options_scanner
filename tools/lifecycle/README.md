# Symbol Lifecycle Management

CLI tool and package for managing the KLMN symbol universe: onboarding, offboarding, health monitoring, and audit trail.

**PRD:** `tasks/0013-prd-symbol-lifecycle-management.md`

## Quick Reference

```bash
python tools/symbol_lifecycle.py --add ACME       # Onboard new symbol
python tools/symbol_lifecycle.py --offboard ACME  # Move to purgatory
python tools/symbol_lifecycle.py --restore ACME   # Restore from purgatory
python tools/symbol_lifecycle.py --list           # Universe dashboard
python tools/symbol_lifecycle.py --review         # Review pending suspects
```

## Onboarding (`--add`)

Interactive flow that walks through:

1. **Tradier API fetch** — quotes, fundamentals, expirations, earnings calendars
2. **Symbol card** — name, sector, industry, market cap, volume, price, earnings dates
3. **Pre-flight checks** — optionable, liquidity, universe membership, sector, earnings data
4. **Tier selection** — FM_UNIVERSE (full intraday scan) or DAILY_ONLY (OP/EI only)
5. **Archive routing** — numbered picker of all `data/sector_archive/*.db` files with sector-based suggestion. Can create new archives on the fly.
6. **Backfill steps** (7 total):
   - Insert/update `symbol_metadata`
   - Backfill `historical_prices` (~1 year from Tradier)
   - Backfill `earnings_events` (Tradier corporate calendars)
   - Compute `earnings_moves`
   - Populate `earnings_upcoming`
   - Generate FM baseline (fm_universe only)
   - Log lifecycle audit event

Steps that fail skip gracefully — the system self-heals on the next daily cycle.

## Offboarding (`--offboard`)

Moves a symbol to purgatory: updates `symbol_metadata.universe_tier`, removes from `earnings_upcoming`, logs audit event. Production data archives naturally on the next Friday cycle.

## Restore (`--restore`)

Moves a symbol out of purgatory back to fm_universe or daily_only.

## Dashboard (`--list`)

Shows tier counts, protected groups, ETF count, pending suspects, recent 30-day lifecycle activity, and purgatory residents.

## Suspect Review (`--review`)

Interactive review of symbols flagged by the Phase 6.2 health check (missing from `option_contracts` for 5+ consecutive trading days). Actions: offboard, dismiss, skip.

## Health Check (Phase 6.2)

Runs automatically in the orchestrator after performance data collection. Detects symbols missing from `option_contracts`:
- **Warning** at 3-4 consecutive missing days (logged in end-of-day report)
- **Suspect** at 5+ days (logged to `symbol_lifecycle_events`, surfaced in report)
- **90% safety gate** — skips the check if fewer than 90% of active symbols have data on the most recent day (likely API outage, not symbol-level issue)

## Database

**Tables affected:**
- `symbol_metadata` — columns: `universe_tier`, `protected_reason`, `is_etf`, `tier_changed_date`, `notes`
- `symbol_lifecycle_events` — full audit trail of all lifecycle actions

**Source of truth:** `symbol_metadata.universe_tier` in `datalake.db`. `get_specialty_list()` in `core/symbols_klmn800.py` queries this with a Python list fallback.

## Package Structure

```
tools/symbol_lifecycle.py    # CLI entry point
tools/lifecycle/
  __init__.py
  onboarding.py              # --add flow
  offboarding.py             # --offboard, --restore, --list, --review
  routing.py                 # Archive DB suggestion from sector/industry
  preflight.py               # Pre-flight checks
  audit.py                   # symbol_lifecycle_events table + logging
  health_check.py            # Phase 6.2 health check
  ui.py                      # Interactive prompts, symbol card, archive picker
```
