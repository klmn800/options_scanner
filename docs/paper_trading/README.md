# Paper Trading Platform

> **Status:** State A **LIVE** 2026-05-18. State B (Engine-Managed Exits) **LIVE** 2026-05-19.
> **Source of truth for design:** [DESIGN.md](DESIGN.md). **Build plans:** [PHASE_1_PLAN.md](PHASE_1_PLAN.md), [PHASE_B_PLAN.md](PHASE_B_PLAN.md).
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
| **B** | Engine-managed exits. Positions carry `close_conditions_json` (TP / SL / max hold / DTE / underlying targets); standalone engine fires closes. | **LIVE** |
| **C** | First auto-open consumer: FM alerts. Every alert opens a paper trade tagged by scorer version. | Future |
| **D** | Multi-consumer platform. FM alerts + earnings STRONG BUY straddles + TA journal running concurrently. | Future |
| **E** | A/B experiment harness. Formal framework for named strategy comparisons against shared triggers. | Future |

---

## Quick start

```bash
# Confirm sandbox auth works
python tools/paper_trade.py --balance

# Open a SPY weekly ATM call, 1 contract, market order, tagged "manual-test"
# (UNMONITORED — close it yourself, the engine ignores it)
python tools/paper_trade.py --open --instrument option --symbol SPY \
    --option-symbol SPY260522C00740000 --side buy_to_open --qty 1 \
    --type market --tag manual_test

# Same trade but MONITORED — engine auto-closes per these conditions
python tools/paper_trade.py --open --instrument option --symbol SPY \
    --option-symbol SPY260522C00740000 --side buy_to_open --qty 1 \
    --type market --tag manual_test \
    --tp 25 --sl -30 --max-hold 5 --expire-before-dte 1

# After Tradier reports the fill, record it locally
python tools/paper_poll.py

# Check open positions (shows conditions column)
python tools/paper_trade.py --positions

# Retrofit conditions onto an existing position (or update existing ones)
python tools/paper_trade.py --update-conditions --position-id 7 --tp 30 --sl -25
python tools/paper_trade.py --update-conditions --position-id 7 --clear  # back to unmonitored

# Manually close a position (overrides any conditions)
python tools/paper_trade.py --close --position-id 1 --reason manual
python tools/paper_poll.py            # records the closing fill

# Realized P&L by tag
python tools/paper_trade.py --pnl --tag manual_test

# Daily balance snapshot (run end-of-day)
python tools/paper_poll.py --snapshot

# Phase B close engine (Task Scheduler runs this every 2 min during market hours)
python tools/paper_close_engine.py --dry-run --verbose   # safe testing
python tools/paper_close_engine.py                       # live submission
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
│     _ensure_schema()             4 tables, 6 indexes, idempotent     │
│     get_connection()             sqlite3 conn → data/paper.db        │
│     parse/build_close_conditions Phase B JSON helpers                │
│     set/pop_pending_conditions   bridge between open and fill        │
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

Eight mutually exclusive subcommands. Run one per invocation.

| Subcommand | Required flags | Notes |
|---|---|---|
| `--balance` | (none) | Tradier sandbox balance summary |
| `--positions` / `--status` | (none) | List paper positions. `--tag T` filters; `--include-closed` shows closed too. Conditions column shows `TP+25/SL-30/5d/...` or `unmonitored` |
| `--pnl` | (none) | Realized P&L by tag. `--tag T` filters; `--since YYYY-MM-DD` filters by close date |
| `--open` | `--instrument {stock\|option} --symbol --side --qty --type` | Add condition flags to monitor; omit to leave unmonitored. See below |
| `--close` | `--position-id N` | Optional `--reason {manual\|take_profit\|stop_loss\|max_hold\|signal_event}`. Immediately flips status `open → closing`. Poller flips to `closed` on fill |
| `--update-conditions` | `--position-id N` | Pass condition flags to overwrite, or `--clear` to wipe back to unmonitored. Without flags, just prints current conditions |
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
| `--tp` | float | Phase B. take_profit_pct — close when pnl% ≥ N |
| `--sl` | float (negative) | Phase B. stop_loss_pct — close when pnl% ≤ N |
| `--max-hold` | int | Phase B. max_hold_days — close after N calendar days |
| `--expire-before-dte` | int | Phase B. Option-only. Close when DTE ≤ N (avoid auto-exercise) |
| `--target-above` | float | Phase B. Close when underlying price ≥ N |
| `--target-below` | float | Phase B. Close when underlying price ≤ N |

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

## Phase B — Close Conditions Vocabulary

`paper_positions.close_conditions_json` stores the per-position "thesis" the engine evaluates each cycle.

**⚠️ NULL by default.** A manual `--open` without any `--tp`/`--sl`/`--max-hold`/etc. flags creates an
**unmonitored** position. The engine skips unmonitored rows entirely. This is intentional — the platform
will not auto-close a position you didn't ask it to. To opt in, pass condition flags at open time, or use
`--update-conditions` later.

| Field | CLI flag | Meaning | Trip rule |
|---|---|---|---|
| `take_profit_pct` | `--tp N` | Float, positive | Close when `current_pnl_pct >= N` |
| `stop_loss_pct` | `--sl N` | Float, negative | Close when `current_pnl_pct <= N` |
| `max_hold_days` | `--max-hold N` | Int | Close when held ≥ N calendar days |
| `expire_before_dte` | `--expire-before-dte N` | Int, option-only | Close option when DTE ≤ N |
| `underlying_target_above` | `--target-above N` | Float | Close when underlying price ≥ N |
| `underlying_target_below` | `--target-below N` | Float | Close when underlying price ≤ N |

Any field may be null/absent → that condition is inactive. The engine fires a close on the **first**
condition that trips (any-of, not all-of). Stop-loss is evaluated before take-profit so a position tripping
both simultaneously gets the safer close reason.

The `paper_trading.default_close_conditions` block in `config.json` exists for **programmatic reference**
(future auto-consumers will read it as a template). CLI `--open` does **not** auto-apply it.

Update a position's conditions:
```bash
python tools/paper_trade.py --update-conditions --position-id 7 --tp 30 --sl -25
python tools/paper_trade.py --update-conditions --position-id 7 --clear   # back to unmonitored
python tools/paper_trade.py --update-conditions --position-id 7           # prints current, no change
```

---

## Phase B — Close Engine

`tools/paper_close_engine.py` is a standalone reconciliation script. Each invocation:

1. Acquires a psutil-based instance lock — refuses to run a second copy.
2. Checks Tradier's `markets/clock` endpoint. If market is closed and `--ignore-market-hours` not passed,
   skips evaluation entirely (no quote fetch).
3. Reads all `paper_positions WHERE status='open' AND close_conditions_json IS NOT NULL`.
4. Batch-fetches Tradier quotes for every relevant underlying + option symbol in one call.
5. Evaluates each position's conditions. Logs every trip with the reason and trigger detail.
6. For tripped positions: submits a closing order, flips status to `'closing'`, records `close_reason` +
   `closing_submitted_at`. `paper_poll.py` flips `'closing' → 'closed'` when the fill is recorded.

### Engine CLI flags

| Flag | Effect |
|---|---|
| `--dry-run` | Evaluate + log trips, do NOT submit close orders. Essential for testing. |
| `--ignore-market-hours` | Run evaluation even when market is closed (testing only) |
| `--position-id N` | Evaluate only one paper_positions.id (testing) |
| `--verbose` | Log every position's evaluation, not just trips |

### Scheduling

Task Scheduler runs `scheduled_tasks/start_paper_engine.bat` every 2 minutes during market hours (M-F
9:30 AM – 4:00 PM ET). Engine self-skips when Tradier reports market closed, so off-hours runs are
no-ops. **On first deployment**, edit the `.bat` to include `--dry-run` for one trading day to validate
condition evaluation against real market data before letting it submit closes.

### Status state machine

```
                ┌─────────┐    cmd_close OR engine trip
                │  open   │ ──────────────────────────┐
                └─────────┘                           │
                                                      ▼
                                              ┌─────────────┐
                                              │   closing   │
                                              └─────────────┘
                                                      │
                                              paper_poll.py records fill
                                                      │
                                                      ▼
                                              ┌─────────────┐
                                              │   closed    │
                                              └─────────────┘
```

The `'closing'` intermediate state prevents the engine from re-submitting close orders for a position whose
previous close is still pending fill. This is the idempotency mechanism.

### Stuck-in-closing recovery

If Tradier rejects a close order (sandbox glitch, contract just expired, etc.) the engine leaves the
position in `'open'` state (not `'closing'`) and increments the error counter. If a `'closing'` row exists
but no fill ever comes (Tradier order cancelled out-of-band), use direct SQL to roll status back to
`'open'` and let the engine retry. A future `--unstick` CLI command may automate this.

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

## Data model — four tables in `data/paper.db`

> **Phase B moved paper tables out of `data/datalake.db`** to eliminate FM write-lock contention.
> Migration was one-shot via `tools/paper_migrate_to_paper_db.py`. Querying via `direct_db_query.py`
> requires `--db data/paper.db`.

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
| `status` | `open` / `closing` / `closed`. See close engine section for the state machine. |
| `close_reason` | `manual` / `take_profit_pct` / `stop_loss_pct` / `max_hold_days` / `expire_before_dte` / `underlying_target_above` / `underlying_target_below` / `signal_event` |
| `close_conditions_json` | Phase B per-position thesis. **NULL = unmonitored.** See Close Conditions Vocabulary section. |
| `closing_submitted_at` | Phase B. Timestamp when close order was submitted (status flipped to `closing`). |

### `paper_pending_conditions` — Phase B bridge table

Keyed by `tradier_order_id`. Holds close-conditions stashed by `paper_trade.py --open` between order
submission and fill recording. `paper_poll.py` pops the row when the fill is processed and copies the
JSON onto the new `paper_positions` row. If an order is rejected/cancelled the pending row sits
harmlessly until a future cleanup.

| Column | Notes |
|---|---|
| `tradier_order_id` | PK |
| `close_conditions_json` | The JSON blob to apply to the resulting position |
| `created_at` | Insertion timestamp |

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
- **Paper tables live in `data/paper.db`** (Phase B), not `datalake.db` and not `datalake_query.db`. Use
  `--db data/paper.db` when querying via `direct_db_query.py`. Quick sync is not wired to paper.db (and
  doesn't need to be — the engine writes directly).
- **Phase B engine evaluates conditions stateless.** Trailing stops, signal-coupled exits, and IV-collapse
  exits are deferred to later phases. Only the 6 conditions in the vocabulary table are honored today.

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
config.json                                    tradier_sandbox + paper_trading blocks
core/tradier_paper.py                          TradierPaperBroker + sanitize_tag
tools/paper_trading.py                         schema + persistence helpers (shared)
tools/paper_trade.py                           human-facing CLI (--open/--close/--update-conditions/...)
tools/paper_poll.py                            fill recorder + balance snapshot
tools/paper_close_engine.py                    Phase B condition evaluator + close submitter
tools/paper_migrate_to_paper_db.py             one-shot Phase B migration (datalake.db → paper.db)
tools/decimal_formatter.py                     skip_formatting set extended for paper text columns
scheduled_tasks/start_paper_engine.bat         Task Scheduler entrypoint for the engine
docs/paper_trading/DESIGN.md                   design + end states + decisions (source of truth)
docs/paper_trading/PHASE_1_PLAN.md             build plan for State A
docs/paper_trading/PHASE_B_PLAN.md             build plan for State B
docs/paper_trading/README.md                   this file
data/paper.db                                  the paper_* tables (Phase B onward)
```

## Cross-references

- Tradier sandbox API base: <https://sandbox.tradier.com/v1>
- Tradier docs: <https://docs.tradier.com/docs/endpoints>
- Place-order endpoint: <https://docs.tradier.com/reference/brokerage-api-trading-place-order>
- Sibling pattern (real-trade ingest): [`tools/trade_ingest.py`](../../tools/trade_ingest.py) — `paper_executions` mirrors its position-key convention via shared `_make_position_key()`.
- Decimal policy: `CLAUDE.md` → Database Standards → Decimal Policy.
