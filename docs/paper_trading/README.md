# Paper Trading Platform

> **Status:** Phase 1 (State A — Manual PoC) **LIVE** as of 2026-05-18.
> **Source of truth for design:** [DESIGN.md](DESIGN.md). **Build plan:** [PHASE_1_PLAN.md](PHASE_1_PLAN.md).
> **This file** is the operational reference — read here when you need to *use* the system.

## What this is

A platform layer that places and tracks paper (simulated) trades against Tradier's sandbox brokerage API.
Same endpoints as live Tradier, separate URL (`sandbox.tradier.com`), a real fill engine with a $100K paper account.

Consumers — manual CLI today, FM auto-paper / earnings auto-paper / agent journals tomorrow — plug in via the
broker class and DB helpers. The platform handles auth, order submission, fill polling, position tracking,
and P&L attribution.

## Why

Scanner signals (FM alerts, earnings tiers, OP delta scores) need automated ground-truth feedback. Today the
only loop is a next-day OI heuristic plus Ben's manual Robinhood trades. Paper trading gives every signal a
real P&L track, segregated by `tag`, comparable across versions and variants.

## End states

| State | What "done" looks like | Status |
|---|---|---|
| **A** | Manual paper trading via CLI. Buy/sell equities and options, polled fills, tagged P&L, daily balance snapshot. | **LIVE** |
| **B** | Engine-managed exits. Positions carry `close_conditions` (take profit / stop loss / max hold); engine fires closes. | Next |
| **C** | First auto-open consumer: FM alerts. Every alert opens a paper trade tagged by scorer version. | Future |
| **D** | Multi-consumer platform. FM alerts + earnings STRONG BUY straddles + TA journal running concurrently. | Future |
| **E** | A/B experiment harness. Formal framework for named strategy comparisons against shared triggers. | Future |

---

## Quick start

```bash
# Confirm sandbox auth works
python tools/paper_trade.py --balance

# Open a SPY weekly ATM call, 1 contract, market order, tagged "manual-test"
python tools/paper_trade.py --open --instrument option --symbol SPY \
    --option-symbol SPY260522C00740000 --side buy_to_open --qty 1 \
    --type market --tag manual_test

# After Tradier reports the fill, record it locally
python tools/paper_poll.py

# Check open positions
python tools/paper_trade.py --positions

# Close a position by paper_positions.id
python tools/paper_trade.py --close --position-id 1 --reason manual
python tools/paper_poll.py            # records the closing fill

# Realized P&L by tag
python tools/paper_trade.py --pnl --tag manual_test

# Daily balance snapshot (run end-of-day)
python tools/paper_poll.py --snapshot
```

**Important caveats:**
- Sandbox quotes are **15-minute delayed**. Market-order fills price against delayed quotes.
- After-hours orders sit `pending` until next market open. Tradier will fill them at the opening tick.
- Tradier rejects underscores in order tags. CLI auto-sanitizes (`manual_test` → `manual-test`) and prints
  a notice; filter args get the same treatment, so muscle memory still works.

---

## Architecture — four layers

```
┌──────────────────────────────────────────────────────────────────────┐
│ LAYER 4 — CLI (humans / agents)                                      │
│   tools/paper_trade.py       open/close/cancel/positions/balance/pnl │
│   tools/paper_poll.py        records fills, takes balance snapshots  │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│ LAYER 3 — Persistence helpers (importable by any consumer)           │
│   tools/paper_trading.py                                             │
│     _ensure_schema()             3 tables, 6 indexes, idempotent     │
│     get_connection()             sqlite3 conn → data/datalake.db     │
│     record_execution()           INSERT into paper_executions        │
│     open_or_update_position()    INSERT/UPDATE paper_positions       │
│     snapshot_balance()           INSERT today's row into snapshots   │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│ LAYER 2 — Broker (the network boundary, sandbox-only)                │
│   core/tradier_paper.py                                              │
│     TradierPaperBroker           constructor refuses non-sandbox     │
│       place_equity_order(...)    POST /accounts/{id}/orders          │
│       place_option_order(...)    POST /accounts/{id}/orders          │
│       get_order / get_orders     GET                                 │
│       cancel_order(id)           DELETE                              │
│       get_balances / get_positions / get_quote                       │
│     sanitize_tag(s)              Tradier tag-char fixer              │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│ LAYER 1 — HTTP/auth/rate-limit (pre-existing)                        │
│   core/tradier_api.py                                                │
│     TradierAPI(token, sandbox=True)                                  │
│       _make_request()            session + 60 req/min limiter        │
└──────────────────────────────────────────────────────────────────────┘
```

### Safety guarantees

1. `TradierPaperBroker.__init__` reads `config['tradier_sandbox']` (not `config['tradier']`). Missing/empty → raises before any HTTP call.
2. Constructor asserts `self.api.sandbox is True` AND `self.api.base_url == "https://sandbox.tradier.com/v1"`.
3. This is the **only** class in the codebase that places orders. There is no fallback path that could route a paper order to live.

---

## CLI reference — `tools/paper_trade.py`

Seven mutually exclusive subcommands. Run one per invocation.

| Subcommand | Required flags | Notes |
|---|---|---|
| `--balance` | (none) | Tradier sandbox balance summary |
| `--positions` / `--status` | (none) | List paper positions. `--tag T` filters; `--include-closed` shows closed too |
| `--pnl` | (none) | Realized P&L by tag. `--tag T` filters; `--since YYYY-MM-DD` filters by close date |
| `--open` | `--instrument {stock\|option} --symbol --side --qty --type` | See below |
| `--close` | `--position-id N` | Optional `--reason {manual\|take_profit\|stop_loss\|max_hold\|signal_event}` |
| `--cancel` | `--order-id N` | Cancels an open Tradier order by Tradier ID |

### `--open` full args

| Flag | Values / format | Notes |
|---|---|---|
| `--instrument` | `stock` or `option` | Required |
| `--symbol` | `SPY` | Underlying ticker |
| `--option-symbol` | `SPY260522C00740000` (OCC) | Required when `--instrument=option` |
| `--side` | `buy` / `sell` (stock) | |
| | `buy_to_open` / `sell_to_open` (open option) | |
| | `buy_to_close` / `sell_to_close` (close option) | |
| `--qty` | integer | Shares or contracts |
| `--type` | `market` / `limit` / `stop` / `stop_limit` | |
| `--price` | float | Required for `limit` / `stop_limit` |
| `--duration` | `day` (default) / `gtc` / `pre` / `post` | |
| `--tag` | free text | Default `manual`. Auto-sanitized to Tradier-safe chars. |
| `--preview` | flag | Validate via Tradier, do not submit |
| `--source-event-id` | string | Idempotency key for auto-consumers; manual use leaves NULL |

### CLI examples

```bash
# Equity, market order
python tools/paper_trade.py --open --instrument stock --symbol SPY \
    --side buy --qty 10 --type market --tag manual_test

# Option, limit order, GTC
python tools/paper_trade.py --open --instrument option --symbol AAPL \
    --option-symbol AAPL260619C00200000 --side buy_to_open --qty 1 \
    --type limit --price 5.20 --duration gtc --tag manual_test

# Preview only — Tradier validates, returns cost/commission, doesn't submit
python tools/paper_trade.py --open --instrument option --symbol SPY \
    --option-symbol SPY260619C00500000 --side buy_to_open --qty 1 \
    --type market --preview

# Close by position ID
python tools/paper_trade.py --close --position-id 3 --reason take_profit

# Tag-filtered P&L since a date
python tools/paper_trade.py --pnl --tag fm_alert_v2 --since 2026-05-01
```

---

## CLI reference — `tools/paper_poll.py`

| Invocation | Purpose |
|---|---|
| `python tools/paper_poll.py` | Poll all Tradier orders, record any new fills |
| `python tools/paper_poll.py --order-id N` | Poll one specific Tradier order (useful for diagnostics) |
| `python tools/paper_poll.py --snapshot` | Record today's balance row into `paper_account_snapshots` |
| `python tools/paper_poll.py --verbose` | Print HTTP debug + per-order skip reasons |

The poller is **idempotent**. It tracks cumulative recorded quantity per `tradier_order_id` and records only
the delta. Running it twice in a row never double-records a fill. Partial fills that complete later are
captured as incremental rows.

---

## Data model — three tables in `data/datalake.db`

### `paper_executions` — immutable fill log
One row per fill. Multiple rows per Tradier order if it fills partially.

| Column | Notes |
|---|---|
| `id` | PK |
| `execution_timestamp` | Tradier-reported fill time |
| `action` | `buy` / `sell` (stock) or `buy_to_open` / `sell_to_close` / etc. (option) |
| `instrument_type` | `stock` or `option` |
| `symbol` | Underlying |
| `quantity` | Shares or contracts |
| `fill_price` | **Per-share** ($1.80 not $180.00 for a contract) |
| `total_cost` | `qty * fill_price * multiplier` (100 for option, 1 for stock) |
| `option_type` / `strike` / `expiration_date` / `option_symbol` | NULL for stock |
| `position_key` | `SPY\|740.0\|2026-05-22\|CALL` or just `SPY` for stock. Same convention as `trade_executions`. |
| `tag` | Attribution. Tradier-sanitized form. |
| `source_event_id` | Auto-consumer idempotency key. UNIQUE with `tag`. NULL for manual. |
| `tradier_order_id` | Groups partial fills under one Tradier order |
| `broker` | `tradier_sandbox` |

### `paper_positions` — current + closed positions

| Column | Notes |
|---|---|
| `id` | PK |
| `position_key`, `tag` | Same convention as executions |
| `instrument_type`, `symbol`, `option_symbol`, `option_type`, `strike`, `expiration_date` | Position identity |
| `quantity` | Decrements on partial close; hits 0 on full close |
| `cost_basis_per_unit` | Avg fill price; recalculated when averaging in |
| `total_cost` | `quantity * cost_basis * multiplier` |
| `realized_pnl` | **Accumulates** across partial closes; populated on first close (not NULL means trades happened) |
| `status` | `open` / `closed`. Only flips to `closed` when `quantity` hits 0. |
| `close_reason` | `manual` / `take_profit` / `stop_loss` / `max_hold` / `signal_event` |
| `close_conditions_json` | Phase B: `{"take_profit_pct":25,"stop_loss_pct":-30,"max_hold_days":5}` |

### `paper_account_snapshots` — daily balance time-series

| Column | Notes |
|---|---|
| `snapshot_date` | PK, one row per day |
| `total_equity`, `cash`, `long_market_value`, `short_market_value`, `open_pl`, `close_pl`, `buying_power`, `option_buying_power` | From Tradier `/balances` |
| `raw_response_json` | Full Tradier response stashed for forensics |

---

## End-to-end flow

### Open flow
```
You: paper_trade.py --open --instrument option --symbol SPY ...
      │
CLI: sanitize tag → broker.place_option_order(...)
      │
Broker: POST sandbox.tradier.com/v1/accounts/{id}/orders
      │
Tradier: returns {"order": {"id": 30219623, "status": "ok"}}
      │
CLI prints order id. NO DB row yet — order is pending, not filled.
```

### Poll flow
```
You: paper_poll.py
      │
Broker: GET /accounts/{id}/orders
      │
For each order Tradier returns:
   status='pending' / 'open'  → skip (not filled yet)
   status='filled' / 'partially_filled'
        → already_recorded = SUM(paper_executions.quantity for this tradier_order_id)
        → delta = exec_quantity - already_recorded
        → if delta > 0:
              record_execution(delta)         # INSERT into paper_executions
              open_or_update_position(...)    # opens new row, averages in,
                                              # or closes/decrements existing
   status='rejected' / 'canceled' / 'expired' → log to console, no DB write
```

### Close flow
```
You: paper_trade.py --close --position-id 7 --reason manual
      │
CLI reads paper_positions[7], picks close side
     (sell_to_close for option long, sell for stock long)
      │
Broker: POST orders endpoint with closing order
      │
Next paper_poll.py records the closing fill:
   close_qty < open_qty → decrement quantity, accumulate realized_pnl, status stays 'open'
   close_qty == open_qty → set status='closed', final realized_pnl, closed_at
```

---

## Config

`config.json` → `tradier_sandbox` block:
```json
"tradier_sandbox": {
  "api_key": "<paper-trading token from https://web.tradier.com/user/api>",
  "account_id": "<paper account number — format VA########, NOT the username>"
}
```

**Account ID is the VA-prefixed account number, not your Tradier username.** Tradier rejects the username on
account-specific endpoints with a 401.

---

## Known gotchas

- **`account_id` is the `VA########` paper account number, not your username.** The username works for login;
  the API endpoints want the account number.
- **Order tags reject underscores.** CLI sanitizes automatically (replaces invalid chars with `-`), prints a
  notice. Filter args (`--tag` on `--positions` / `--pnl`) get the same treatment.
- **Sandbox quotes are 15-minute delayed.** Absolute paper P&L will diverge from real-time fills. Relative
  comparisons (A/B, signal validation) are unaffected — both sides see the same delay.
- **After-hours market orders queue.** Tradier accepts them with `status=pending` and fills at the next
  market open against opening-tick quotes.
- **Auto-exercise risk on near-expiry ITM options.** Tradier sandbox may auto-exercise expiring ITM contracts.
  Close manually before expiry or pick longer-dated contracts for tests.
- **Quick sync is NOT wired up yet.** Phase 1 reads `paper_*` tables directly from `data/datalake.db`. Claude
  Code's default query DB (`datalake_query.db`) doesn't have these rows until the sync rules are extended.
  Use `--db data/datalake.db` when querying via `direct_db_query.py`.

---

## Future-phase hooks already in the schema

Built now so Phase B/C/D don't need migrations:

- `paper_positions.close_conditions_json` — Phase B reads this per row to evaluate auto-close.
- `paper_executions.source_event_id` — Phase C/D auto-consumers pass `flow_alerts.id` (or similar) here;
  the `UNIQUE(tag, source_event_id)` constraint prevents double-opens on engine crash recovery.
- `paper_executions.tag` — already the experiment axis. Phase E A/B harness reads this for grouping.

---

## Files

```
config.json                       tradier_sandbox block: api_key + account_id
core/tradier_paper.py             TradierPaperBroker + sanitize_tag
tools/paper_trading.py            schema + persistence helpers (shared)
tools/paper_trade.py              human-facing CLI
tools/paper_poll.py               fill recorder + balance snapshot
tools/decimal_formatter.py        skip_formatting set extended for paper text columns
docs/paper_trading/DESIGN.md      design + end states + decisions (source of truth)
docs/paper_trading/PHASE_1_PLAN.md  build plan for State A
docs/paper_trading/README.md      this file
```

## Cross-references

- Tradier sandbox API base: <https://sandbox.tradier.com/v1>
- Tradier docs: <https://docs.tradier.com/docs/endpoints>
- Place-order endpoint: <https://docs.tradier.com/reference/brokerage-api-trading-place-order>
- Sibling pattern (real-trade ingest): [`tools/trade_ingest.py`](../../tools/trade_ingest.py) — `paper_executions` mirrors its position-key convention via shared `_make_position_key()`.
- Decimal policy: `CLAUDE.md` → Database Standards → Decimal Policy.
