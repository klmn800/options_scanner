# News Collector Enhancement Roadmap

**Document Created:** 2025-10-13
**Status:** Future Enhancement (Deferred)
**Current Module Status:** Functional but Basic

---

## Current State

The `strategies/news_collector/` module is **operational** with core functionality complete:

✅ **Working Features:**
- Three-tier priority system (Watchlist → KLMN_PREFERRED+Airlines → KLMN_800)
- Multi-key API rotation (5 Alpha Vantage keys, 125 calls/day)
- Staleness-based symbol rotation
- Database storage to `news_articles` (5,293 rows) and `news_symbol_sentiment` (13,920 rows)
- Decimal formatting, timezone consistency, duplicate prevention
- Comprehensive argparse options (dry-run, tier-specific, symbol-specific)
- Automatic news pruning (>30 days)

❌ **Known Issues:**
- `v_morning_watchlist` view missing from query database (Tier 1 collection fails)
- Not integrated into scheduling (last collection: Oct 5)
- Basic Alpha Vantage sentiment scores only (no enrichment)

---

## Enhancement Vision

Transform from basic collector to **intelligent news curation system** that provides actionable trading insights, not just raw sentiment scores.

---

## Phase 1: Enriched News Content (Foundation)

**Goal:** Store and expose full article details for downstream analysis.

**Enhancements:**
1. **Full article metadata storage:**
   - Add: `banner_image`, `category_within_source`, human-readable timestamps
   - Store complete article JSON for future AI analysis

2. **Topic/theme extraction:**
   - Parse Alpha Vantage topics (Earnings, IPO, M&A, Legal, Technology)
   - Create `news_topics` table for better querying
   - Enable topic-based filtering ("show me all M&A news this week")

3. **Symbol mention context:**
   - Track WHY symbol was mentioned (headline vs footnote)
   - Store mention count (1 symbol article vs 10 symbol article = different relevance)
   - Differentiate primary subject vs passing mention

**Database Changes:**
- Extend `news_articles` columns for richer metadata
- Add `news_topics` table: `(article_url, topic, topic_score)`
- Add `mention_context` field to `news_symbol_sentiment`

---

## Phase 2: Smarter Sentiment/Relevance (Intelligence Layer)

**Goal:** Move beyond Alpha Vantage's black-box scores to contextualized intelligence.

**Enhancements:**

### 2.1 Multi-Factor Relevance Scoring
```python
# Current: Single relevance_score (0.0-1.0)
# Enhanced: Composite relevance with factors:
- Position in article (headline = high, footnote = low)
- Mention frequency (1x vs 5x mentions = stronger relevance)
- Article recency (decay function: today = 1.0, 7 days = 0.5)
- Source quality score (WSJ/Bloomberg = high, unknown blog = low)
```

### 2.2 Contextualized Sentiment
```python
# Current: Generic -1 to +1 sentiment
# Enhanced: Trading-specific sentiment classification:
- Earnings context (bullish expectations vs actual results)
- Options catalysts (IV expansion triggers, unusual activity)
- Sector sympathy triggers (peer earnings, supply chain impacts)
- Macro overlays (Fed news, sector rotation themes)
```

### 2.3 Oracle Integration for News Analysis
- Use Claude API to analyze article summaries for top watchlist symbols
- Generate actionable insights: "Bullish catalyst - partnership with major tech firm"
- Classify news types: Earnings, M&A, Product Launch, Legal Issues, Analyst Upgrade/Downgrade
- Extract trading implications: "Potential IV expansion ahead of product event"
- Estimate impact magnitude: Minor/Moderate/Major catalyst

**Implementation:**
- Create `news_oracle_analysis` table for AI-generated insights
- Run Oracle analysis on top 20 news articles daily (watchlist symbols only)
- Store: `article_url`, `symbol`, `catalyst_type`, `impact_magnitude`, `trading_implications`, `analysis_timestamp`

---

## Phase 3: Morning View Integration (Consumer Experience)

**Goal:** Transform Morning View from showing raw scores to rich news context.

**Enhancements:**

### 3.1 News Cards with Actionable Details
```
Current:  NVDA - Sentiment: +0.45
Enhanced:
┌─ 📰 NVDA - BULLISH CATALYST (Rel: 0.82, Sent: +0.45) ───┐
│ "Nvidia announces AI chip breakthrough"                  │
│ Reuters • 2 hours ago • M&A/Technology                   │
│                                                           │
│ 🎯 Impact: Potential earnings beat catalyst              │
│ 💡 Action: Watch for unusual call flow today             │
│ 🔗 Related: AMD ↓, INTC ↓ (sector sympathy)             │
└───────────────────────────────────────────────────────────┘
```

### 3.2 News-Driven Watchlist Ranking
- Factor news momentum into Morning View scores
- Highlight symbols with breaking news (<6 hours old) with 🔴 indicator
- Show "news freshness" score (fresh = <6h, stale = >3 days)
- Rank by combination of: OI momentum + Flow signals + News catalysts

### 3.3 Sector News Aggregation
- "Airlines sector: 3 bearish articles today (fuel costs rising)"
- Helps identify sympathy plays and rotation trends
- Show cross-sector impacts ("Tech selloff affecting semiconductor suppliers")

**UI Changes:**
- Add news detail modal/panel to Morning View TUI
- Show top 3 articles per symbol (most recent + highest relevance)
- Add keyboard shortcut to open full articles in browser
- Display news staleness indicator in watchlist table

---

## Phase 4: Multi-Source Intelligence (Future Expansion)

**Goal:** Aggregate multiple news sources for comprehensive coverage.

**Potential Sources:**
1. **Financial Modeling Prep:** Earnings transcripts, insider trades
2. **Reddit/Twitter Sentiment:** Retail trader positioning signals
3. **SEC Filings:** 8-K (material events), 13-F (institutional moves)
4. **Earnings Call Transcripts:** Tone analysis, guidance extraction, Q&A sentiment
5. **Benzinga/Seeking Alpha:** Real-time breaking news feeds

**Architecture:**
- Abstract `NewsSource` base class
- Source-specific collectors inherit from base
- Unified storage in `news_articles` with `source_type` field
- Cross-source deduplication (same story from multiple sources)
- Source quality scoring (weighted credibility)

---

## Recommended Implementation Order

### Quick Win: Fix & Schedule (1-2 hours)
1. Fix `v_morning_watchlist` view issue in query database
2. Integrate into `main.py` scheduling (run daily at 6:30 AM)
3. Verify Morning View gets fresh data
**Value:** Makes existing functionality reliable

### Phase 1 Foundation (4-6 hours)
1. Enhance storage to capture full article metadata
2. Add Oracle analysis for top 20 watchlist news articles
3. Create enriched view for Morning View with actionable insights
4. Build "breaking news" indicator (<6 hours old)
**Value:** Immediate improvement to Morning View user experience

### Phase 2 Intelligence (8-12 hours)
1. Design multi-factor relevance scoring algorithm
2. Build Oracle integration for sentiment contextualization
3. Create `news_oracle_analysis` table
4. Implement trading-specific sentiment classification
**Value:** Transforms raw data into trading signals

### Phase 3 UI Enhancements (6-8 hours)
1. Rebuild Morning View news cards with rich detail
2. Add news detail modal to TUI
3. Implement sector news aggregation
4. Add news-driven ranking to watchlist
**Value:** Full user experience upgrade

### Phase 4 Multi-Source (12-16 hours per source)
1. Design source abstraction layer
2. Add one source at a time (FMP → Reddit → SEC → Transcripts)
3. Build cross-source deduplication
4. Implement source quality scoring
**Value:** Comprehensive news intelligence system

---

## Technical Considerations

### Alpha Vantage Sentiment Calibration
- **Current understanding:** Limited - scale appears to be -1 to +1 but calibration unclear
- **Action needed:** Analyze historical sentiment scores vs actual price moves to understand predictive power
- **Enhancement:** Build custom calibration layer that adjusts AV scores based on historical performance

### API Quota Management
- Current: 125 calls/day across 5 keys (sufficient for baseline)
- Phase 2: Oracle analysis adds ~20 Claude API calls/day (minimal cost: ~$0.50/day)
- Phase 4: Additional sources may require new API subscriptions

### Database Growth
- Current: 5,293 articles (2+ years of data)
- With enrichment: ~200 articles/day → 6,000/month → 72,000/year
- With pruning (30 days): Stable at ~6,000 articles
- Oracle analysis: ~600 rows/month (20 articles/day, 30-day retention)

### Performance Impact
- Oracle analysis: ~30 seconds for 20 articles (non-blocking, can run async)
- Morning View load time: +200ms for enriched news queries (acceptable)
- Database size impact: Minimal (<100MB total with all enhancements)

---

## Success Metrics

**Phase 1 Success:**
- Morning View displays article titles and summaries (not just scores)
- Breaking news indicator highlights time-sensitive opportunities
- Oracle insights appear within 10 minutes of news collection

**Phase 2 Success:**
- Multi-factor relevance score correlates better with actual symbol moves than Alpha Vantage score alone
- Oracle-classified catalyst types enable strategy-specific filters ("show me only M&A catalysts")
- Trading implications text provides actionable next steps

**Phase 3 Success:**
- Morning View users spend less time switching to external news sources
- News-driven ranking surfaces high-conviction plays earlier
- Sector aggregation identifies sympathy plays automatically

**Phase 4 Success:**
- Cross-source deduplication prevents duplicate stories
- Source diversity increases coverage (fewer "no recent news" symbols)
- Source quality weighting improves signal-to-noise ratio

---

## Open Questions

1. **Relevance scoring weights:** What's the optimal weighting for position vs frequency vs recency?
2. **Oracle cost management:** Should we limit Oracle analysis to only high-priority symbols?
3. **News latency:** How quickly do we need news updates? (Current: daily, Real-time: requires streaming API)
4. **Source prioritization:** Which additional sources provide highest ROI for Phase 4?
5. **Historical backfill:** Should we backfill Oracle analysis for existing 5,293 articles?
6. **User customization:** Should traders be able to customize news relevance factors?

---

## Related Documentation

- **PRD:** `tasks/0002-prd-news-collection-infrastructure.md` - Original design document
- **Task List:** `tasks/tasks-0002-prd-news-collection-infrastructure.md` - Implementation checklist
- **Module Code:** `strategies/news_collector/` - Current implementation
- **Database Schema:** `data/datalake_schema_2025-10-01.md` - Tables: `news_articles`, `news_symbol_sentiment`

---

## Next Steps When Ready

1. **Review and approve** specific phase to implement
2. **Create detailed PRD** for chosen phase (if needed)
3. **Generate task list** using AI Dev Tasks workflow
4. **Implement incrementally** with testing at each milestone

**Estimated Total Effort:** 30-40 hours for all phases (can be done incrementally over weeks/months)
