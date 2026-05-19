# Plan: Paper Trading Platform — State A (Manual PoC)

> **Status: COMPLETE 2026-05-19.** All 8 acceptance criteria pass. Option order 30219623 filled @ $3.14 at open, equity order 30266026 filled @ $732.54, both closed manually (option @ $1.90, equity @ $732.25), realized P&L -$126.90 visible via `--pnl --tag manual_test`, balance snapshot written for 2026-05-19 (total_equity $99,872.30). One observation: parallel close-order invocations hit a transient `database is locked` SQLite write contention — sequential close calls work cleanly. Likely worth a small `_retry_on_lock()` wrapper if Phase B fires multiple closes per cycle, but not blocking.
> **Companion docs:** [`README.md`](README.md) (operational ref), [`DESIGN.md`](DESIGN.md) (source of truth)

## Context

The scanner produces many trading signals (FM alert scoring v2, earnings underpricing tiers, OP delta scores, intraday signal upgrades) but ground-truth feedback today is limited to a next-day OI heuristic and Ben's manual Robinhood trades. We want a paper-trading platform that wraps Tradier's sandbox brokerage API so future consumers (FM auto-paper, agent journal, A/B harness) can plug in via stable primitives — but Phase 1 is just proving the foundation works.

**What "State A" means:** A human (or an agent via CLI) can buy and sell paper equities and options against Tradier's sandbox, fills are recorded, open positions tracked, and realized P&L queryable. No automation. No consumers. Just the platform.

Full design context: `docs/paper_trading/DESIGN.md`. This plan turns Section 6 of that doc into concrete code-level steps.

---

## Architecture decisions (grounded in exploration)

1. **Reuse `core/tradier_api.py:TradierAPI` for HTTP, auth, rate limiting.** It already supports sandbox mode and has a `trading_limiter`. New paper code instantiates it with `sandbox=True` and reuses `_make_request()` for order endpoints. No fork, no duplicate request layer.
2. **`TradierPaperBroker` is the new class** in `core/tradier_paper.py`. Wraps a sandbox-mode `TradierAPI`, holds the paper account_id, asserts sandbox on construction, and exposes order/account/position methods. Quote methods delegate to the underlying API. **Safety guarantee: `TradierPaperBroker` refuses to instantiate against a live-API token — it's the only thing that places orders, and it can only place sandbox orders.**
3. **Write to `data/datalake.db`** following `trade_ingest.py` precedent. Don't add to quick sync in Phase 1 — the CLI reads/writes in the same process, so sync is unnecessary for the PoC. Revisit when Claude Code needs to query paper data.
4. **Schema via `_ensure_schema()`** in a new `tools/paper_trading.py` helper module (importable by both `paper_trade.py` and `paper_poll.py`). Idempotent `CREATE TABLE IF NOT EXISTS`. Same pattern as `tools/trade_ingest.py:46-92`.
5. **Reuse `_make_position_key()` from `tools/trade_ingest.py:186-199`** for `paper_executions.position_key` so paper and real positions share the same key format. Cross-DB future queries just work.
6. **Credentials in `config.json` `tradier_sandbox` block**, parallel to existing `tradier` block. Visual separation prevents accidental live-API calls.

---

## Files to create

### `core/tradier_paper.py` (new)

`TradierPaperBroker` class. Wraps a sandbox `TradierAPI`. Public methods:

- `__init__(config)` — loads `config['tradier_sandbox']`, instantiates `TradierAPI(token, sandbox=True)`, asserts `self.api.sandbox is True`, stores `self.account_id`.
- `place_equity_order(symbol, side, qty, type_, duration='day', price=None, preview=False, tag=None, source_event_id=None) -> dict` — POST `/accounts/{id}/orders` with `class=equity`. Returns Tradier response (includes `order.id` and `order.status`).
- `place_option_order(underlying, option_symbol, side, qty, type_, duration='day', price=None, preview=False, tag=None, source_event_id=None) -> dict` — POST same endpoint with `class=option`.
- `get_order(order_id) -> dict` — GET `/accounts/{id}/orders/{order_id}`.
- `get_orders(status_filter=None) -> list` — GET `/accounts/{id}/orders`. Useful for batch-polling.
- `cancel_order(order_id) -> dict` — DELETE `/accounts/{id}/orders/{order_id}`.
- `get_positions() -> list` — GET `/accounts/{id}/positions`. Tradier-authoritative view.
- `get_balances() -> dict` — GET `/accounts/{id}/balances`.
- `get_quote(symbol) -> dict` — delegate to `self.api.get_quotes([symbol])`.
- `get_option_quote(option_symbol) -> dict` — delegate to `self.api.get_quotes([option_symbol])` (Tradier accepts OCC symbols here).

All methods route through `self.api._make_request(method, endpoint, self.api.trading_limiter, ...)` to inherit error handling, retries, and rate limits.

### `tools/paper_trading.py` (new — shared helpers)

Reusable schema + persistence helpers, imported by `paper_trade.py` and `paper_poll.py`.

- `_ensure_schema(conn)` — creates `paper_executions`, `paper_positions`, `paper_account_snapshots`, plus indexes. Idempotent.
- `get_connection()` — `sqlite3.connect(DATALAKE_DB_PATH, timeout=10)`, sets `row_factory = sqlite3.Row`. Mirrors `trade_executions.py:52-55`.
- `record_execution(conn, execution_dict)` — calls `clean_database_row()`, restores date fields, INSERTs into `paper_executions`. Computes `position_key` via `_make_position_key()` (import from `trade_ingest`).
- `open_or_update_position(conn, execution)` — after a BUY fill, INSERT into `paper_positions` (or UPDATE if averaging in). After a SELL/CLOSE fill, UPDATE the matching open position to CLOSED with `realized_pnl`.
- `snapshot_balance(conn, balances_dict)` — INSERT (or REPLACE) into `paper_account_snapshots` for today's date.

### `tools/paper_trade.py` (new — primary CLI)

Argparse with mutually-exclusive subcommands (mirrors `tools/symbol_lifecycle.py:79-118`):

- `--open` — submits an order. Required: `--instrument {stock|option}`, `--symbol`, `--side`, `--qty`, `--type`. Conditional: `--option-symbol` (required if instrument=option), `--price` (required if type in {limit, stop, stop_limit}). Optional: `--tag` (default `manual`), `--preview` (validate, don't submit), `--source-event-id`.
- `--close` — submits a closing order for a specific position. Required: `--position-id`. Optional: `--reason` (default `manual`).
- `--cancel` — cancels an open Tradier order. Required: `--order-id`.
- `--status` / `--positions` — prints all OPEN paper positions (optionally filtered by `--tag`).
- `--balance` — prints current Tradier paper balance.
- `--pnl` — prints realized P&L. Optional `--tag`, `--since`.

Loads config via `json.load(open(PROJECT_ROOT / 'config.json'))`, instantiates `TradierPaperBroker(config)`, gets DB connection, runs `_ensure_schema()`, dispatches to subcommand.

### `tools/paper_poll.py` (new — order polling + balance snapshot)

Standalone script. Run by hand in Phase 1; hooked into FM cycle in Phase B.

Modes:
- (default) Polls all open Tradier orders that have no corresponding fill in `paper_executions` yet. For each:
  - `broker.get_order(order_id)` — check status.
  - If `filled` or `partially_filled` (and qty > 0), call `record_execution()` and `open_or_update_position()`.
  - If `rejected` / `canceled` / `expired`, log to console (don't persist).
- `--snapshot` — calls `broker.get_balances()`, writes one row to `paper_account_snapshots`.

Idempotency: a Tradier order_id appearing in `paper_executions` is already recorded; skip.

---

## Files to modify

### `config.json` — add `tradier_sandbox` block

```json
"tradier_sandbox": {
  "api_key": "<paper-trading-token>",
  "account_id": "<paper-account-id>"
}
```

Ben pastes values from his sandbox account at <https://web.tradier.com/user/api>.

### `tools/decimal_formatter.py` — extend `skip_formatting` set

Lines ~123-160 of `format_database_values()`. Add these text columns so they're not nullified by `clean_database_row()`:
- `tag`, `source_event_id`, `tradier_order_id`, `close_conditions_json`, `close_reason`, `status`, `option_symbol`, `raw_response_json`

(Most existing columns — `action`, `symbol`, `instrument_type`, `notes`, `position_key`, `broker` — are already in the skip list.)

---

## Schema (verbatim, to drop into `_ensure_schema()`)

### `paper_executions`

```sql
CREATE TABLE IF NOT EXISTS paper_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_timestamp DATETIME,
    action TEXT NOT NULL,           -- buy/sell (stock) or buy_to_open/sell_to_open/buy_to_close/sell_to_close (option)
    instrument_type TEXT NOT NULL,  -- 'stock' or 'option'
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    fill_price REAL NOT NULL,       -- per-share ($1.80 for an option, not $180.00)
    total_cost REAL,                -- qty * fill_price * multiplier (100 for option, 1 for stock)
    option_type TEXT,               -- 'call' / 'put' / NULL
    strike REAL,
    expiration_date DATE,
    option_symbol TEXT,             -- OCC format (AAPL251017C00247500) / NULL for stock
    position_key TEXT NOT NULL,     -- generated via _make_position_key()
    tag TEXT NOT NULL DEFAULT 'manual',
    source_event_id TEXT,           -- optional idempotency key for auto-consumers
    tradier_order_id TEXT,
    broker TEXT NOT NULL DEFAULT 'tradier_sandbox',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tag, source_event_id)    -- prevents double-open from same trigger (NULL+NULL allowed for manual)
);
CREATE INDEX IF NOT EXISTS idx_paper_executions_symbol ON paper_executions(symbol);
CREATE INDEX IF NOT EXISTS idx_paper_executions_position_key ON paper_executions(position_key);
CREATE INDEX IF NOT EXISTS idx_paper_executions_tag ON paper_executions(tag);
CREATE INDEX IF NOT EXISTS idx_paper_executions_tradier_order_id ON paper_executions(tradier_order_id);
```

### `paper_positions`

```sql
CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_key TEXT NOT NULL,
    tag TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    option_symbol TEXT,
    option_type TEXT,
    strike REAL,
    expiration_date DATE,
    quantity REAL NOT NULL,
    cost_basis_per_unit REAL,
    total_cost REAL,
    opened_at DATETIME,
    opening_execution_id INTEGER REFERENCES paper_executions(id),
    closed_at DATETIME,
    closing_execution_id INTEGER REFERENCES paper_executions(id),
    exit_price_per_unit REAL,
    realized_pnl REAL,
    close_reason TEXT,              -- take_profit/stop_loss/max_hold/manual/signal_event
    close_conditions_json TEXT,     -- JSON: {"take_profit_pct": 25, "stop_loss_pct": -30, "max_hold_days": 5}
    status TEXT NOT NULL DEFAULT 'open',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_paper_positions_status_symbol ON paper_positions(status, symbol);
CREATE INDEX IF NOT EXISTS idx_paper_positions_tag_status ON paper_positions(tag, status);
```

### `paper_account_snapshots`

```sql
CREATE TABLE IF NOT EXISTS paper_account_snapshots (
    snapshot_date DATE PRIMARY KEY,
    total_equity REAL,
    cash REAL,
    long_market_value REAL,
    short_market_value REAL,
    open_pl REAL,
    close_pl REAL,
    buying_power REAL,
    option_buying_power REAL,
    raw_response_json TEXT,
    snapshotted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Implementation sequence

Each step ends with a checkpoint where the system is in a working, testable state.

**Step 1 — Credentials skeleton.** Add `tradier_sandbox` block to `config.json` with empty values. Ben pastes real values.

**Step 2 — Schema + shared helpers.** Create `tools/paper_trading.py` with `_ensure_schema()`, `get_connection()`, and stubs for `record_execution()` / `open_or_update_position()` / `snapshot_balance()`. Verify tables exist via `sqlite3` CLI.

**Step 3 — TradierPaperBroker, read-only first.** Create `core/tradier_paper.py` with `__init__`, `get_balances`, `get_positions`, `get_orders`, `get_quote`. **Checkpoint:** smoke test from a one-liner `python -c "..."` that prints sandbox balance. Confirms auth works.

**Step 4 — TradierPaperBroker order methods.** Add `place_equity_order`, `place_option_order`, `get_order`, `cancel_order`. No CLI yet — exercised via the next step.

**Step 5 — CLI shell, read-only subcommands.** Create `tools/paper_trade.py` with argparse skeleton + `--balance` and `--positions` (queries Tradier directly, no DB write yet). **Checkpoint:** `python tools/paper_trade.py --balance` prints sandbox balance.

**Step 6 — `--open` subcommand.** Submits a Tradier order, prints order ID. Does NOT yet poll for fill (next step). **Checkpoint:** order submission returns 200 and Tradier WebUI shows the pending order.

**Step 7 — `paper_poll.py`.** Polling loop + fill recording + position open. **Checkpoint:** after step 6's order fills (or after a market order fills immediately), `python tools/paper_poll.py` writes a row to `paper_executions` and `paper_positions`.

**Step 8 — `--close` + `--cancel` + `--pnl` + `--snapshot`.** Closing orders update `paper_positions` (status=CLOSED, realized_pnl computed). `--pnl` queries `paper_positions` grouped by tag. `--snapshot` writes daily balance row. **Checkpoint:** all 8 acceptance criteria below pass.

**Step 9 — `decimal_formatter.py` skip list.** Add the 8 new text columns. Confirm `clean_database_row()` no longer nullifies them by manually invoking on a sample dict.

**Step 10 — README in `core/` and a one-paragraph note in `CLAUDE.md` Common Commands section.** Per CLAUDE.md "Documentation on Delivery" rule.

---

## Critical files to read before editing

- `core/tradier_api.py` — entire file. Especially the `TradierAPI._make_request` signature and how the trading limiter is wired.
- `tools/trade_ingest.py:46-92` — schema pattern.
- `tools/trade_ingest.py:186-199` — `_make_position_key()` (will be imported by paper code).
- `tools/trade_positions.py:48-117` — second schema example, position-tracking conventions.
- `tools/symbol_lifecycle.py:79-118` — CLI argparse pattern to mirror.
- `tools/decimal_formatter.py:107-346` — `format_database_values()` and the skip_formatting set.
- `tools/log_utils.py` — `beautiful_log()` signature so output style matches the rest of the codebase.

---

## Verification (end-to-end)

After all steps land, these eight checks define Phase 1 "done." Smoke-test contract: SPY weekly ATM call (cheap, liquid, fills fast).

1. `python tools/paper_trade.py --balance` prints non-zero cash and equity from the sandbox account.
2. `python tools/paper_trade.py --open --instrument option --symbol SPY --option-symbol SPY<...>C00<strike> --side buy_to_open --qty 1 --type market --tag manual_test` submits an order; CLI prints the Tradier order ID. Tradier WebUI confirms the order.
3. `python tools/paper_poll.py` polls, sees the fill, writes a row to `paper_executions` (verify via `sqlite3 data/datalake.db "SELECT * FROM paper_executions"`) and creates one in `paper_positions`.
4. `python tools/paper_trade.py --open --instrument stock --symbol SPY --side buy --qty 10 --type market --tag manual_test` works end-to-end (equity path). Same poll, same verification.
5. `python tools/paper_trade.py --positions` shows both open positions with current quantity and cost basis.
6. `python tools/paper_trade.py --close --position-id N` submits a closing order; next `paper_poll.py` records the closing fill, updates `paper_positions` to CLOSED with non-NULL `realized_pnl` and `close_reason='manual'`.
7. `python tools/paper_trade.py --pnl --tag manual_test` returns realized P&L for the closed positions.
8. `python tools/paper_poll.py --snapshot` writes a row to `paper_account_snapshots` for today's date.

Once all eight pass, Phase 1 ships and we update `docs/paper_trading/DESIGN.md` to mark State A complete and target State B (engine-managed exits).

---

## Risks / open items

- **Sandbox market order fills against delayed quotes.** Documented in DESIGN.md §5.4. Not a blocker for State A; surfaces in any absolute-P&L comparison later.
- **Multileg orders unverified in sandbox.** Phase 1 only needs single-leg. Phase D (earnings straddle auto-paper) will surface any issues.
- **Tradier may auto-exercise ITM options.** Phase 1 smoke test uses near-the-money short-dated; if test contract goes ITM at expiry, behavior may surprise us. Use a contract expiring after our test window or close manually before expiry.
- **No orchestrator integration yet.** Polling is manual in Phase 1. Phase B hooks into FM cycle (~15min cadence).
- **No `datalake_query.db` sync yet.** Reading paper data from Claude Code analysis will require direct `datalake.db` access until we add to quick sync rules. Document in the new `core/README.md` so future-us doesn't get confused.
