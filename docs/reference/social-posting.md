# Social Media Posting System

Automated Reddit/Twitter posting for high-quality flow alerts to build credibility and audience before monetization.

## Overview

The social posting system automatically detects exceptional flow alerts and creates social media posts showcasing early institutional positioning detection. Posts are generated within 60 minutes of alert detection, establishing credibility as an early detector.

### Key Features

- **Early Detection Branding**: Posts include real-time timestamps showing detection before major outlets
- **Multi-leg Intelligence**: Automatically detects strangles, spreads, and ratio plays
- **Educational Content**: Enriched with market context, sector data, and regime analysis
- **Quality Control**: Only posts alerts with significance_score >= 7.0 and premium > $5M (v2 scoring, was 9.0)
- **Draft Review**: 30-minute delay window for manual context addition
- **Rate Limiting**: Max 3 posts/day to maintain quality and avoid spam perception

## Architecture

### Components

1. **social_content_generator.py** - Generates enriched educational content
   - Enriches alerts with symbol metadata (sector, market cap)
   - Adds market regime context (Bull/Bear, VIX, SPY)
   - Detects multi-leg strategies (strangles, spreads)
   - Formats educational narrative with disclaimers

2. **social_poster.py** - Posts to Reddit/Twitter
   - Reddit integration via PRAW
   - Twitter integration via tweepy
   - Draft generation and manual review workflow
   - Post deduplication and rate limiting
   - Engagement tracking

3. **fm_social_notifier.py** - Integration hook
   - Monitors new flow_alerts for eligibility
   - Manages 30-minute delay queue
   - Coordinates with Flow Monitor

4. **social_posts** database table - Tracks all posts
   - Draft status tracking
   - Post URLs and engagement scores
   - Error logging for failed posts

## Configuration

### Setup Steps

#### 1. Reddit API Setup

1. Go to https://www.reddit.com/prefs/apps
2. Click "create app" or "create another app"
3. Fill in:
   - **name**: OptionsFlowBot (or your choice)
   - **app type**: script
   - **redirect uri**: http://localhost:8080
4. Save and note the `client_id` (under app name) and `client_secret`

#### 2. Twitter API Setup (Optional)

1. Go to https://developer.twitter.com/en/portal/dashboard
2. Create a new app
3. Generate API keys and access tokens
4. Note: Twitter API is now restricted; may require approval

#### 3. Update config.json

```json
{
  "social_posting": {
    "enabled": false,  // Set to true when ready
    "auto_post": false,  // false = draft only, true = auto-post
    "platforms": {
      "reddit": {
        "enabled": true,
        "subreddits": ["options"],  // or ["u_YourUsername"] for profile posts
        "post_as": "text"
      },
      "twitter": {
        "enabled": false,
        "thread_mode": true
      }
    },
    "selection_criteria": {
      "min_significance_score": 7.0,
      "min_premium_value": 5000000,
      "max_posts_per_day": 3,
      "exclude_earnings_day": true
    },
    "timing": {
      "delay_minutes": 30,  // Time for manual context addition
      "max_age_minutes": 60  // Don't post stale alerts
    }
  },
  "reddit_api": {
    "client_id": "YOUR_CLIENT_ID_HERE",
    "client_secret": "YOUR_CLIENT_SECRET_HERE",
    "username": "YOUR_REDDIT_USERNAME",
    "password": "YOUR_REDDIT_PASSWORD",
    "user_agent": "OptionsFlowBot/1.0"
  },
  "twitter_api": {
    "api_key": "",
    "api_secret": "",
    "access_token": "",
    "access_token_secret": ""
  }
}
```

## Usage

### Automatic Mode (Integrated with Flow Monitor)

When `social_posting.enabled = true`, the system automatically:

1. Flow Monitor detects high-quality alert (score > 9.0, premium > $5M)
2. Alert is saved to `flow_alerts` table
3. `fm_social_notifier` checks eligibility and queues alert
4. **30-minute delay** for manual context addition
5. Alert is processed:
   - If `auto_post = false`: Draft is created in `social_posts` table
   - If `auto_post = true`: Post is published to Reddit/Twitter

### Manual Draft Review

#### View Alert and Generate Draft

```bash
# Generate draft for specific alert
python tools/social_poster.py --alert-id 7650

# Add manual context
python tools/social_poster.py --alert-id 7650 --context "Unusual pre-earnings positioning. Company reports earnings in 5 days."
```

#### Preview Draft Content

```bash
# Preview content without posting
python tools/social_content_generator.py --alert-id 7650 --output draft.txt
```

#### Publish Draft

```bash
# Publish previously created draft
python tools/social_poster.py --draft-id 123

# Or enable auto-posting in config.json
```

### Process Queue Manually

```bash
# Process all eligible alerts past their delay window
python strategies/flow_monitor/fm_social_notifier.py --process-queue

# Check specific alert
python strategies/flow_monitor/fm_social_notifier.py --check-alert 7650
```

## Post Format

### Example Post

**Title:**
```
🎯 Unusual Options Flow: $KDP - $20M volatility play
```

**Body:**
```
⏰ **Detected:** 12:11 PM ET (Live Detection)

📊 **The Flow:**
• **Strategy:** $20M strangle (1 put, 1 call)
• **Total Premium:** $20M
• **Primary Leg:** $25 PUT | Exp: 2025-11-21

💡 **Market Context:**
• **Company:** Keurig Dr Pepper
• **Sector:** Consumer Staples | **Market Cap:** Large
• **Market Regime:** Low Vol

**Analysis:**
Unusual pre-earnings positioning. Company reports earnings in 5 days.

🎯 **Why It Matters:**
Large volatility play suggesting expectation of significant price movement in
either direction. With $20M in combined premium, this represents substantial
institutional positioning ahead of a potential catalyst.

⚠️ **Disclaimer:** Educational analysis only. Not financial advice.
Options involve significant risk. Do your own research.

---
*Daily flow analysis | Follow for early institutional positioning insights*
```

## Database Schema

### social_posts Table

```sql
CREATE TABLE social_posts (
    id INTEGER PRIMARY KEY,
    alert_id INTEGER NOT NULL,           -- FK to flow_alerts.id
    platform TEXT NOT NULL,               -- 'reddit' or 'twitter'
    post_id TEXT,                         -- Platform's post ID
    post_url TEXT,                        -- Full post URL
    post_title TEXT,                      -- Post title
    post_content TEXT,                    -- Full content
    draft_generated_at TEXT,              -- When draft was created
    posted_at TEXT,                       -- When actually posted
    engagement_score INTEGER DEFAULT 0,   -- Upvotes/likes
    status TEXT NOT NULL DEFAULT 'draft', -- 'draft', 'posted', 'failed'
    error_message TEXT,                   -- Error details if failed
    manual_context TEXT,                  -- User-added context
    created_at TEXT NOT NULL,
    updated_at TEXT
);
```

### flow_alerts Updates

```sql
-- New columns added to flow_alerts
ALTER TABLE flow_alerts ADD COLUMN social_posted BOOLEAN DEFAULT FALSE;
ALTER TABLE flow_alerts ADD COLUMN social_post_id INTEGER;
```

## Workflow Examples

### Example 1: Full Automatic Posting

**Config:**
```json
{
  "social_posting": {
    "enabled": true,
    "auto_post": true
  }
}
```

**Flow:**
1. KDP alert detected at 12:11 PM (score: 9.6, premium: $20M)
2. Alert saved to flow_alerts (ID: 7650)
3. fm_social_notifier queues alert for posting
4. **30-minute delay** (until 12:41 PM)
5. At 12:41 PM, social_poster generates content
6. Post published to Reddit automatically
7. Post URL and engagement tracked in social_posts

### Example 2: Draft Review Workflow

**Config:**
```json
{
  "social_posting": {
    "enabled": true,
    "auto_post": false
  }
}
```

**Flow:**
1. Alert detected and queued (same as above)
2. After 30 minutes, draft is created but NOT posted
3. Notification: "Draft created for alert 7650"
4. You review: `python tools/social_content_generator.py --alert-id 7650`
5. Add context: `python tools/social_poster.py --alert-id 7650 --context "..."`
6. Publish: `python tools/social_poster.py --draft-id 123`

### Example 3: Manual Post Anytime

**Config:**
```json
{
  "social_posting": {
    "enabled": false
  }
}
```

**Flow:**
1. Alerts are processed normally, no social posting
2. You manually review flow_alerts table
3. Find interesting alert from earlier today
4. Generate and post manually:
   ```bash
   python tools/social_poster.py --alert-id 7650 --context "Custom analysis here"
   ```

## Best Practices

### Content Strategy

1. **Timing**: Post within 60 minutes of detection for credibility
2. **Quality Over Quantity**: Only post score > 9.0, premium > $5M
3. **Educational Angle**: Focus on "what we detected" not "what will happen"
4. **Context Matters**: Add manual context when you have insights
5. **Multi-leg Stories**: Strangles and spreads tell better stories

### Reddit Strategy

1. **Start with Profile Posts**: Use `"subreddits": ["u_YourUsername"]`
2. **Build History**: Post consistently for 2-4 weeks
3. **Request Mod Approval**: Message r/options mods with example posts
4. **Follow Subreddit Rules**: Each subreddit has specific posting guidelines
5. **Engage**: Respond to comments, build reputation

### Rate Limiting

1. **Max 3 posts/day**: Quality threshold prevents spam
2. **Only top alerts**: significance_score >= 7.0 is rare (~1-2/day) (v2 scoring)
3. **Avoid earnings noise**: exclude_earnings_day = true
4. **Monitor engagement**: Track upvotes/downvotes, adjust strategy

### Legal/Ethical

1. **Clear Disclaimers**: Every post includes "not financial advice"
2. **Educational Focus**: Explain what was detected, not predictions
3. **No Recommendations**: Never say "buy" or "sell"
4. **Transparency**: Show methodology, data sources

## Monitoring & Analytics

### Track Engagement

```sql
-- Get post performance
SELECT
    p.post_url,
    p.posted_at,
    p.engagement_score,
    a.symbol,
    a.significance_score,
    a.premium_value
FROM social_posts p
JOIN flow_alerts a ON p.alert_id = a.id
WHERE p.status = 'posted'
ORDER BY p.posted_at DESC;
```

### Success Metrics

- **Engagement rate**: Upvotes per post
- **Click-through**: If using external links
- **Follower growth**: Track over time
- **Post timing correlation**: Best times to post

## Troubleshooting

### Reddit API Errors

**Error: "invalid_grant"**
- Check username/password in config.json
- Verify client_id and client_secret

**Error: "429 Too Many Requests"**
- Reddit rate limit hit (1 post per 10 minutes)
- Reduce max_posts_per_day

**Error: "Forbidden"**
- Account too new or low karma
- Try posting to your profile first

### Draft Generation Errors

**Error: "Alert not found"**
- Check alert_id exists in flow_alerts table
- Verify database path

**Error: "Content generation failed"**
- Check that symbol exists in symbol_metadata
- Verify market_daily_summary has data for trade_date

### Integration Issues

**Social posting not triggering**
- Verify `social_posting.enabled = true` in config.json
- Check alert meets criteria (score > 9.0, premium > $5M)
- Review fm_alerts.py logs for social_queued count

## Future Enhancements

### Phase 2 Features

- [ ] Twitter thread generation (multi-tweet format)
- [ ] Image generation (charts, heatmaps)
- [ ] Engagement analytics dashboard
- [ ] A/B testing for post formats
- [ ] Automated follow-up posts (outcomes after 1 day, 1 week)

### Advanced Features

- [ ] Multi-platform coordination (cross-post same alert)
- [ ] Subscriber notification system
- [ ] Premium tier content differentiation
- [ ] API endpoint for Chrome extension integration

## Support

For issues or questions:
1. Check logs in Flow Monitor output
2. Review database entries in social_posts table
3. Test components individually with command-line tools
4. Verify API credentials and rate limits

---

**Last Updated:** 2025-10-06
**Version:** 1.0
