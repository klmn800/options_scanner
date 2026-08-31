# The Print — Social Posting Quick Start

> **Account:** [@ThePrintFlow](https://x.com/ThePrintFlow) on X
> **Status:** Live as of 2026-04-27 (auto-posting via Flow Monitor)
> **Brainstorm / Phase 2-3 vision:** `docs/_local/social_poster/BRAINSTORM.md`

## What it does

Flow Monitor auto-posts qualifying `flow_alerts` rows to X (@ThePrintFlow) immediately on save. Each post is a single tweet with the alert's symbol, contract, volume context, and market regime.

## Eligibility filter (current MVP)

An alert posts iff ALL of:
- `social_posted` is 0 / NULL (dedup)
- `roll_detected` is 0 / NULL (no rolls)
- `open_interest > 0` (no divide-by-zero)
- `volume / open_interest >= min_voi_ratio` (default 1.0; closure-resistant)
- daily post cap not reached (default 30/day, counts `social_posted=1` rows for today)

## Tweet format (Option A — single tweet, terse)

Single-leg:
```
$PLTR - unusual call activity

$32C 5/15/26 | 12,500 contracts (45x avg) | $2.5M premium
Tech / Large cap / Bull regime

2:14 PM ET
```

Multi-leg (auto-detected via 5-min same-symbol window in `_detect_multi_leg()`):
```
$NVDA - multi-leg activity

$132.8M call spread ($170-$185) | exp 5/15/26
Tech / Mega cap / Bull regime

10:28 AM ET
```

Hard cap: 280 chars. If full message exceeds, the context line drops first, then the time line. Returns None (skip post) if even headline + detail won't fit.

## Configuration

`config.json` `social_posting`:
```json
{
  "enabled": true,
  "dry_run": false,
  "selection_criteria": {
    "min_voi_ratio": 1.0,
    "exclude_rolls": true,
    "max_posts_per_day": 30
  }
}
```

- `enabled` — master kill switch. False = nothing happens, FM skips the entire path.
- `dry_run` — true = log formatted tweet but don't post or write to DB. Use for testing in production without spamming X.
- `min_voi_ratio` — `volume / open_interest` threshold. Higher = fewer posts but stronger "fresh institutional" signal.
- `max_posts_per_day` — safety cap.

## CLI utilities

```bash
# Post one specific alert manually
python tools/twitter_post_alert.py --alert-id 12345

# Preview the most recent eligible alert (no post)
python tools/twitter_post_alert.py --latest --dry-run

# Post the most recent eligible alert
python tools/twitter_post_alert.py --latest

# X API auth smoke test (posts a "disregard" tweet)
python tools/twitter_test_post.py

# Re-run notifier on a specific alert with safe override
python strategies/flow_monitor/fm_social_notifier.py --alert-id 12345 --force-dry-run
```

## How posting flows through code

1. FM cycle saves a new alert to `flow_alerts` (`fm_alerts.py`)
2. If `social_posting.enabled = true`, `_check_social_posting()` calls `fm_social_notifier.FMSocialNotifier.check_alert(alert_id)`
3. Notifier loads alert, runs eligibility filter, checks daily cap
4. If eligible: `social_content_generator.format_for_x(alert)` builds the tweet text
5. tweepy.Client posts via X API v2 (cost: $0.01/post on pay-per-use)
6. On success: `flow_alerts.social_posted = 1`, `social_post_id = <tweet_id>` written back to primary `data/datalake.db`

## Credentials

OAuth 1.0a User Context, stored in `credentials.json` `twitter_api`:
- `api_key`, `api_key_secret` (Consumer Key + Secret in X portal)
- `access_token`, `access_token_secret` (regenerate AFTER setting App permissions to Read+Write)
- `bearer_token` (saved but not used for posting — write needs OAuth 1.0a User Context)

App type in X Developer Portal: **Web App, Automated App or Bot** (Confidential client).

## Cost

X API pay-per-use, **$0.01 per tweet posted**. Daily cap of 30/day = max ~$9/month. No fixed monthly fee. 2 million read cap doesn't apply (we're posting, not scraping).

The previous Free tier was discontinued February 2026. Legacy Basic ($200/mo) and Pro ($5,000/mo) tiers are closed to new signups.

## Compliance

@ThePrintFlow displays X's "Automated" account label, linked to a separate human-owned account per X's automation policy. Disclaimer ("informational only, not investment advice") lives in the X bio, not in tweets.

## What's NOT here yet

- Threshold tuning based on production data — wait for ~2 weeks of posts, then query `flow_alerts.social_posted=1` and tune `min_voi_ratio` and daily cap.
- Multi-leg strike trailing-zero polish (e.g., `$170.0` → `$170` in `_detect_multi_leg()` description).
- Engagement / track-record stats page (Phase 2 of brainstorm).
- Tiered access / paid tier (Phase 2-3 of brainstorm).

## Files

| File | Purpose |
|------|---------|
| `tools/social_content_generator.py` | `format_for_x()` method + helpers (`_fmt_premium`, `_fmt_strike`, `_fmt_exp`, `_fmt_alert_time`). Reuses `_enrich_alert()` and `_detect_multi_leg()` from the older Reddit pipeline. |
| `tools/twitter_post_alert.py` | Manual single-alert posting CLI. |
| `tools/twitter_test_post.py` | Auth smoke test. |
| `strategies/flow_monitor/fm_social_notifier.py` | FM hook. `check_alert()` is called per saved alert. |
| `config.json` `social_posting` | Toggles + selection criteria. |
| `credentials.json` `twitter_api` | OAuth credentials. |

## Old code still on disk (not in active path)

- `tools/social_poster.py` — original Reddit + Twitter draft-review poster (Oct 2025). Never activated. Not imported by anything live.
- `docs/reference/social-posting.md` — original design doc, marked DEPRECATED.

These can be deleted in a future cleanup sweep.
