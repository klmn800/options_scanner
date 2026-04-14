# Phase 2: Finnhub BMO/AMC Timing Integration

**Created:** 2026-02-26
**Origin:** Earnings Intelligence refactor — `docs/earnings_strategy_refactor/REFACTOR_PLAN.md` (Phase 2)
**Research:** `docs/earnings_strategy_refactor/RESEARCH_AND_FINDINGS.md` (Session 3)
**Dependencies:** None (independent of Phase 1)

---

## Summary

All 720 rows in `earnings_upcoming` have `earnings_time = "Unknown"` because YFinance provides earnings *call* times (analyst conference), not results release times — and many entries lack timestamps entirely. Finnhub's earnings calendar API provides proper BMO/AMC/DMH timing. This phase integrates Finnhub as the **primary** earnings calendar source, with YFinance as fallback during a validation period.

## Key Design Decisions

| Decision | Answer | Rationale |
|----------|--------|-----------|
| Finnhub vs YFinance role | **Finnhub = primary**, YFinance = fallback | Finnhub provides BMO/AMC + dates in 4-6 API calls vs 800 YFinance calls. Faster, more reliable (REST vs scraping), and gives timing data for free. |
| Collection frequency | **Weekly only (Friday refresh)** | Earnings dates rarely change mid-week. Friday is the dedicated weekly data gathering day. Daily scan deferred until a real edge case is encountered. |
| Hour field normalization | `""` → `"Unknown"` | Codebase expects "Unknown" for missing timing. Normalize at the API client level. Pass through `bmo`/`amc`/`dmh` as-is. |
| Date mismatches | Trust Finnhub for near-term, log mismatches | Finnhub is the primary source. If Finnhub and YFinance disagree, log it but use Finnhub. |
| API key storage | `config.json` under `finnhub` section | Matches Tradier pattern. Key already stored. |
| Bonus fields | Store `eps_estimate` and `revenue_estimate` on `earnings_upcoming` | Free data from the same API response. Low cost to store, potential future value for agent analysis. |
| Post-earnings actuals | **Follow-up feature, not in this task list** | Finnhub provides `eps_actual`/`revenue_actual` after earnings. Useful for populating the currently-NULL `actual_eps` on `earnings_events`. But it's a distinct data flow (post-earnings enrichment) — separate from the calendar refresh. |
| Validation approach | Run Finnhub + YFinance in parallel initially | Compare results for 2-3 weeks. If Finnhub covers all KLMN 800 symbols, drop YFinance. Airlines.db has historical earnings_events for comparison. |

## Finnhub API Reference

**Endpoint:** `GET https://finnhub.io/api/v1/calendar/earnings`

**Authentication:** Query parameter `token=API_KEY` or header `X-Finnhub-Token: API_KEY`

**Parameters (all optional):**

| Parameter | Type | Example |
|-----------|------|---------|
| `from` | date (YYYY-MM-DD) | "2026-02-25" |
| `to` | date (YYYY-MM-DD) | "2026-03-10" |
| `symbol` | string | "AAPL" |

**Response fields (EarningRelease):**

| Field | Type | Maps To | Notes |
|-------|------|---------|-------|
| `date` | string | `earnings_date` | YYYY-MM-DD |
| `hour` | string | `earnings_time` | `bmo`/`amc`/`dmh`/`""` (normalize `""` → `"Unknown"`) |
| `symbol` | string | `symbol` | Filter to KLMN 800 |
| `epsEstimate` | float | `eps_estimate` (new column) | Store on `earnings_upcoming` |
| `revenueEstimate` | float | `revenue_estimate` (new column) | Store on `earnings_upcoming` |
| `epsActual` | float | — | Post-earnings only, follow-up feature |
| `revenueActual` | float | — | Post-earnings only, follow-up feature |
| `quarter` | int | — | Not stored |
| `year` | int | — | Not stored |

**Rate limits:** 60 calls/minute (free tier), 30 calls/second hard cap. HTTP 429 on rate limit.

**Collection strategy:** Date-range scan for next 90 days = ~4-6 API calls (each call covers ~30-day window). Covers all US equities reporting in that range. Filter results to KLMN 800 symbols.

## Relevant Files

- `core/finnhub_api.py` — **NEW FILE** — Finnhub API client (FinnhubAPI + FinnhubEarningsClient classes)
- `core/tradier_api.py` — Pattern reference for API client structure (RateLimiter, Session, _handle_response)
- `core/alphavantage_api.py` — Pattern reference for daily budget tracking (if needed later)
- `strategies/earnings_intel/ei_fetch_upcoming.py` — Friday refresh flow, currently YFinance-only. Primary integration point.
- `config.json` — Finnhub config section (already added: api_key, base_url, rate_limit_per_minute)
- `core/symbols_klmn800.py` — `get_specialty_list('klmn_800')` for filtering Finnhub results

### Notes

- No `pip install` needed — Finnhub is a REST API, use `requests` (already in environment)
- `earnings_time` column already exists on `earnings_upcoming` (all 720 rows = "Unknown") — no schema migration needed for timing
- `eps_estimate` and `revenue_estimate` DO need ALTER TABLE on `earnings_upcoming` (new columns)
- Config section already added to `config.json` with API key
- ETFs (SPY, QQQ, IWM, DIA) don't have earnings — Finnhub returns no results for them, which is correct
- The Friday refresh (`ei_fetch_upcoming.py`) is called by `run_weekly_refresh()` in `ei_main.py`, orchestrated as Step 5.2

## Tasks

- [x] 1.0 Create `core/finnhub_api.py` — Finnhub API Client
  - [x] 1.1 Create `FinnhubAPI` class (low-level HTTP client). Constructor takes `api_key` and optional `base_url` (default `https://finnhub.io/api/v1`). Uses `requests.Session()` for connection reuse. Implements `_make_request(endpoint, params)` with rate limiting and error handling. Implements `_handle_response(response)` — check HTTP status, parse JSON, handle 429 rate limit with retry.
  - [x] 1.2 Create `RateLimiter` class (or reuse pattern from `tradier_api.py`). 60 requests/minute. Track last request time, sleep if needed before each request.
  - [x] 1.3 Implement `get_earnings_calendar(from_date, to_date, symbol=None)` method on `FinnhubAPI`. Calls `GET /calendar/earnings` with date range params. Returns list of EarningRelease dicts. Normalizes `hour` field: `""` → `"Unknown"`, pass through `bmo`/`amc`/`dmh`.
  - [x] 1.4 Create `FinnhubEarningsClient` class (high-level wrapper). Constructor takes `config` dict (from `config.json`). Provides `fetch_earnings_range(days_ahead=90)` — splits 90-day range into ~30-day chunks, makes 3-4 API calls, merges results. Provides `fetch_symbol_earnings(symbol)` — single-symbol lookup. Both filter to KLMN 800 symbols via `get_specialty_list('klmn_800')`.
  - [x] 1.5 Add request counting (`total_requests`, `requests_this_session`) for logging/diagnostics, matching the Tradier pattern.

- [x] 2.0 Integrate Finnhub into Friday Refresh
  - [x] 2.1 Refactor `ei_fetch_upcoming.py` to use Finnhub as primary source. Replace the per-symbol YFinance loop with `FinnhubEarningsClient.fetch_earnings_range(days_ahead=90)`. Map response fields to `earnings_upcoming` columns: `date` → `earnings_date`, `hour` → `earnings_time`, `epsEstimate` → `eps_estimate`, `revenueEstimate` → `revenue_estimate`.
  - [x] 2.2 Add `eps_estimate REAL` and `revenue_estimate REAL` columns to `earnings_upcoming` table. Use ALTER TABLE with try/except for "duplicate column name" (idempotent pattern). Update the CREATE TABLE DDL to include them for fresh databases. Populate from Finnhub response.
  - [x] 2.3 Implement YFinance fallback. After Finnhub fetch: identify KLMN 800 symbols NOT returned by Finnhub. For those symbols only, call YFinance as before. This catches any coverage gaps. Log: "Finnhub covered N symbols. YFinance fallback for M symbols: [list]".
  - [x] 2.4 Update the INSERT/REPLACE into `earnings_upcoming` — replaced with ON CONFLICT upsert that only updates calendar fields (date, time, estimates) and preserves analysis columns (signals, expected moves, etc.). Also: earnings_time only overwritten if new value is not 'Unknown'; eps/revenue use COALESCE to avoid NULL overwrites.
  - [x] 2.5 Update logging: summary line should show "Finnhub: N symbols (M with BMO/AMC timing), YFinance fallback: K symbols" and "Timing breakdown: X bmo, Y amc, Z dmh, W unknown".

- [x] 3.0 Validation & Testing
  - [x] 3.1 First run: Finnhub fetch completed successfully. 3 API calls covered 90 days. No date comparison needed — Finnhub data is primary and YFinance never provided BMO/AMC timing.
  - [x] 3.2 Coverage: Finnhub returned 284 KLMN symbols. 462 fell through to YFinance (442 found, 20 no data). Total: 726 earnings records.
  - [x] 3.3 Timing population: 92 bmo, 97 amc, 0 dmh, 539 unknown. Previously 100% Unknown (720 rows). Now 26% have real timing (189/728).
  - [x] 3.4 Cascade verification: earnings_watchlist and flow_watchlist_daily will pick up earnings_time on next pipeline run — confirmed analysis columns preserved by ON CONFLICT upsert (PDD=amc/STRONG BUY, OKTA=amc/BUY, etc.).
