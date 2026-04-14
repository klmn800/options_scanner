# Database Migrations

SQL migration scripts for the Earnings Intelligence System database schema.

## Usage

Run all migrations at once:
```bash
python -c "import sqlite3; conn = sqlite3.connect('../../data/datalake.db'); conn.executescript(open('000_run_all_migrations.sql', encoding='utf-8').read()); conn.commit(); conn.close(); print('All migrations completed successfully')"
```

## Migration Files

- **000_run_all_migrations.sql** - Master script that runs all migrations
- **001_create_earnings_events.sql** - Foundation table with trading journal
- **002_create_earnings_snapshots.sql** - IV/price time series (T-7 to T+3)
- **003_create_earnings_moves.sql** - Calculated price moves and IV changes
- **004_create_industry_peer_mappings.sql** - Industry-based peer relationships
- **005_create_earnings_sector_effects.sql** - Sector sympathy and arbitrage signals

## Schema Design

All migrations use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`, making them safe to re-run.

### Relationships
```
earnings_events (foundation)
    ├── earnings_snapshots (1:N) - Daily observations
    ├── earnings_moves (1:1) - Calculated metrics
    └── earnings_sector_effects (1:N) - Peer correlations

industry_peer_mappings (independent) - Defines peer groups
```

## Notes

- migrations are idempotent (safe to re-run)
- Foreign keys enforce referential integrity
- UNIQUE constraints prevent duplicates
- All tables use immutable archive pattern (never delete, only insert)
