# Proposal 004: Add Tradability Highlight to Flow Alerts

**Effort:** ~30 minutes
**Files:** `strategies/flow_monitor/fm_alerts.py` — `_format_alert_line()` method

---

## What

Add a `[ACTIONABLE]` tag to flow alerts matching Ben's trading profile: underlying ≤$175, option ≤$3, call, DTE 7-60. These are the alerts worth investigating first. Everything else is watchlist intelligence.

April 2026 data: ~5-6 of ~16 daily alerts match this profile. The problem isn't that the system misses them — it's that they're visually indistinguishable from the ~10 alerts Ben scrolls past.

## Why

Ben reports ~20% signal-to-noise (3-4 of ~16 daily alerts worth following). Profile-matching alerts ARE the ones he follows. Visually flagging them saves mental filtering time.

This is a bridge until v3 scoring (May/June) adds flow concentration and actionability bonuses. No schema changes needed — all criteria are already available in the alert dict.

## How

In `_format_alert_line()`, after the symbol name and cap tag, add `[ACTIONABLE]` if:
- `underlying_price <= 175`
- `last_price <= 3.0`
- `option_type == 'call'`
- `dte >= 7 and dte <= 60`

Example output:
```
DOW [ACTIONABLE] [MID] $37.5 CALL(28d) | Vol: 20,268 (4.5x) | OI: 4,461 | V/OI: 4.5 | ...
MSTR [MEG] $157.5 CALL(7d) | Vol: 8,740 (3.2x) | OI: 36,456 | V/OI: 0.2 | ...
```

The tag goes before the cap tag so it's the first thing Ben sees when scanning. Alerts without the tag are still shown — they're intelligence, just not personal trading candidates.

Note: MSTR doesn't get tagged despite $155 underlying (under $175) because its option prices are $7-16 (over $3). The option price filter is the main discriminator.

## Config

Make the thresholds configurable in `config.json` under `flow_monitor.tradability_filter`:
```json
"tradability_filter": {
    "max_underlying_price": 175,
    "max_option_price": 3.0,
    "option_type": "call",
    "min_dte": 7,
    "max_dte": 60
}
```

This lets Ben tune as his portfolio grows.

## Evidence

Analysis details: `strategic_advisor/memory/observations/009_strategy_config_analysis.md`
Ben's trade profile: `strategic_advisor/memory/observations/008_intent_classification_data.md` (section: "Ben's Trade Profile")

## CLI Command

```
cd /d E:\options_scanner
claude -p "Add a tradability highlight to flow alerts. In fm_alerts.py _format_alert_line(), add an [ACTIONABLE] tag after the symbol name for alerts where underlying_price <= 175, last_price <= 3.0, option_type == 'call', and dte between 7 and 60. Put it before the [CAP] tag. Make thresholds configurable via config.json under flow_monitor.tradability_filter with keys: max_underlying_price (175), max_option_price (3.0), option_type ('call'), min_dte (7), max_dte (60). All values already exist in the alert dict. This is a display-only change — no DB schema changes."
```
