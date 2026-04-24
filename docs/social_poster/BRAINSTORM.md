# Social Poster / Flow Alert Publishing — Brainstorm

> **Created:** 2026-04-22 (Ben + Claude brainstorm session)
> **Status:** Idea phase. Weekend project candidate.
> **Related code:** `tools/social_poster.py`, `tools/social_content_generator.py`, `strategies/flow_monitor/fm_social_notifier.py` (existing but never activated)

---

## The Idea

Monetize the options scanner by publishing unusual options flow alerts as content — the same model as The Fly (theflyonthewall.com), Unusual Whales, Benzinga's options feed. These services surface publicly observable market data (options volume, open interest, strike/expiration) and package it as news. Brokerages like Robinhood license The Fly's feed and display it as "news" articles.

Our system already does the hard part: scanning 388 symbols every 15 minutes, detecting unusual volume, scoring significance, tracking outcomes. The gap is just the publishing layer.

## Why This Could Work

- **Speed advantage:** Ben has repeatedly acted on alerts before The Fly publishes theirs for the same activity. Our detection-to-alert latency is minutes, not hours.
- **Track record already exists:** ~3,000+ alerts in `flow_alerts` with timestamped outcome data (profit/loss at 1d, 3d, 7d, 14d, 30d windows). Most new services have to say "trust me" — we can show verified historical performance by score tier.
- **Content generation code exists:** `social_content_generator.py` already enriches alerts with market context (regime, sector, metadata), detects multi-leg strategies, and formats educational narratives. Needs retargeting from Reddit/Twitter to the chosen channel.
- **Zero marginal cost:** The scanner runs anyway. Publishing alerts costs nothing beyond the one-time integration work.

## What We're NOT Selling

The raw alert signal has roughly a 48-52% win rate. That's not an edge for blind trading. What we're selling is **awareness** — "this happened, here's the context." Financial journalism, not investment advice. What people do with the information is their decision.

The real edge (knowing which alerts are worth following based on score tiers, volume surprise thresholds, market regime context) stays with Ben. The published feed is the tea leaves; the reading is proprietary.

## Business Model Progression

### Phase 1: Free Content, Build Audience (MVP)
- Pick one low-friction channel (Twitter/X, Substack, Discord, Telegram)
- Auto-publish top 3-5 alerts per day with enriched context
- Zero ongoing cost, zero commitment to subscribers
- Goal: see if anyone cares. 3 months minimum to evaluate traction
- Track record page with aggregate stats builds passively

### Phase 2: Tiered Access (if Phase 1 shows traction)
- Free tier: delayed alerts (30-60 min), daily digest
- Paid tier: real-time alerts, full context, score breakdowns
- Subscription model ($20-50/month range, see competitors)

### Phase 3: Syndication / API (aspirational)
- License the alert feed to platforms, brokerages, data aggregators
- This is where The Fly makes real money
- Requires established track record and volume

## Legal / ToS Considerations

**What's clearly fine:**
- Publishing that unusual options volume occurred is factual market data observation. The Fly, Benzinga, Unusual Whales all do this.
- Not giving buy/sell recommendations — surfacing activity with context.
- Derived analytics (significance scores, surprise factors) are our intellectual property, not raw data redistribution.

**Needs verification:**
- **Tradier API ToS:** Does our agreement allow redistribution of derived data for commercial purposes? Raw quote redistribution usually requires an exchange data license, but derived analytics are generally free. Need to read the specific terms or email Tradier support.
- **SEC/FINRA registration:** Publishing factual observations vs. "investment advice." The Fly operates as a media company, not a registered investment advisor. Line can get blurry depending on framing. "Talk to a lawyer for an hour" territory — not a blocker, just a checkbox.

## Competitive Landscape

| Service | Model | Pricing | Notes |
|---------|-------|---------|-------|
| The Fly | News wire + syndication | $50-100/mo retail, licensing to brokers | Gold standard. Robinhood, Schwab, Bloomberg all license their feed |
| Unusual Whales | SaaS dashboard + alerts | $40-70/mo | Started as a Twitter bot, grew into full platform |
| Benzinga Pro | News + options flow | $99-177/mo | Broader financial news, options flow is one vertical |
| Cheddar Flow | Options flow alerts | $100/mo | Pure options flow, no news |

## Distribution Channel Options

| Channel | Friction | Reach | Monetization | Notes |
|---------|----------|-------|--------------|-------|
| Twitter/X | Low | High | Indirect (audience building) | Best for Phase 1 awareness. Unusual Whales started here. |
| Substack | Low | Medium | Built-in subscriptions | Free+paid tier natural fit. Email delivery. |
| Discord | Low | Medium | Subscription roles | Community aspect. Common in trading space. |
| Telegram | Low | Low-Med | Subscription channels | Fast alerts, no algorithm. Popular in crypto/trading. |
| Own website | High | Low initially | Ads, subscriptions, API | Most control but most work. Phase 2-3. |

## Existing Code Assessment

### Reusable
- `social_content_generator.py` — alert enrichment logic (market context, multi-leg detection, narrative generation). Core is solid, needs output format changes.
- `fm_social_notifier.py` — FM integration hook (called after each alert save). Eligibility checking, delay queue concept.
- Alert data pipeline — `flow_alerts` table, significance scoring, outcome tracking all exist.

### Needs Rework
- `social_poster.py` — Reddit/Twitter API integration. Platform-specific code needs replacing with whatever channel we choose. The draft/review/publish workflow pattern is reusable.
- Content format — current output is Reddit-style markdown. Needs adapting to chosen channel.
- Selection criteria — current thresholds (9.0 score, $5M premium) are too aggressive. Most alerts wouldn't qualify. Need more inclusive filtering for a content product.

### Missing
- Publishing endpoint for chosen channel
- Track record / stats page
- Rate limiting appropriate for public content (vs. social media posting)
- Disclaimer/legal boilerplate

## Technical Implementation (Weekend Scope)

If we go with Twitter/X as Phase 1:
1. Create X account for the service
2. Set up X API access (developer account, API keys)
3. Adapt `social_content_generator.py` output to tweet format (280 char headline + thread for detail)
4. Wire into FM alert pipeline via existing `fm_social_notifier.py` hook
5. Set `social_posting.enabled = true` in config with appropriate thresholds
6. Let it run for a week, review output quality

## Open Questions

- [ ] Which channel to start with? (Twitter/X seems highest leverage for Phase 1)
- [ ] What selection threshold? Current 9.0 score / $5M premium is too restrictive. Maybe 5.0 score / $500K premium for broader content?
- [ ] How much context per alert? One-liner headline vs. detailed thread?
- [ ] Branding — what name? Separate from personal identity?
- [ ] Tradier ToS — read and confirm derived data redistribution is allowed
- [ ] Do we need a disclaimer page / terms of service for the published content?

## Next Steps

1. Ben to think about channel preference and branding
2. Read Tradier API ToS re: commercial redistribution of derived data
3. Weekend build session to wire up MVP
