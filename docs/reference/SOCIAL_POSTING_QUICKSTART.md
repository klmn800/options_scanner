# Social Posting Quick Start Guide

## What Was Built

A complete automated social media posting system for sharing high-quality flow alerts on Reddit/Twitter.

### ✅ Components Created

1. **Database Infrastructure**
   - `social_posts` table for tracking drafts and published posts
   - New columns in `flow_alerts` (social_posted, social_post_id)
   - Migration script: `data/migrations/create_social_posts_table.py`

2. **Core Modules**
   - `tools/social_content_generator.py` - Generates enriched educational posts
   - `tools/social_poster.py` - Posts to Reddit/Twitter with draft management
   - `strategies/flow_monitor/fm_social_notifier.py` - Integration with Flow Monitor

3. **Configuration**
   - Added `social_posting`, `reddit_api`, `twitter_api` sections to config.json
   - Everything disabled by default (safe to deploy)

4. **Documentation**
   - `docs/social-posting.md` - Complete system documentation
   - This quick start guide

5. **Integration**
   - Flow Monitor automatically queues high-quality alerts
   - 30-minute delay for manual context addition
   - Draft-first workflow (nothing posts automatically yet)

## Current Status: DISABLED (Safe)

```json
{
  "social_posting": {
    "enabled": false,  // ✅ Disabled
    "auto_post": false  // ✅ Draft-only mode
  }
}
```

**Nothing will post automatically.** The system is ready but inactive.

## How to Activate (When Ready)

### Step 1: Get Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "create app"
3. Fill in:
   - name: OptionsFlowBot
   - type: script
   - redirect: http://localhost:8080
4. Save `client_id` and `client_secret`

### Step 2: Update config.json

```json
{
  "reddit_api": {
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "username": "YOUR_REDDIT_USERNAME",
    "password": "YOUR_REDDIT_PASSWORD",
    "user_agent": "OptionsFlowBot/1.0"
  }
}
```

### Step 3: Test with Draft Mode

```bash
# Enable social posting but keep auto_post = false
# Edit config.json:
"social_posting": {
  "enabled": true,
  "auto_post": false  // Still draft-only
}

# Test with existing alert
python tools/social_content_generator.py --alert-id 7650 --output test.txt

# Generate draft (doesn't post)
python tools/social_poster.py --alert-id 7650
```

### Step 4: Choose Posting Strategy

**Option A: Manual Review (Recommended Initially)**
```json
{
  "social_posting": {
    "enabled": true,
    "auto_post": false  // You approve each draft manually
  }
}
```

**Option B: Full Automation**
```json
{
  "social_posting": {
    "enabled": true,
    "auto_post": true,  // Posts automatically after 30-min delay
    "platforms": {
      "reddit": {
        "enabled": true,
        "subreddits": ["u_YourUsername"]  // Start with profile posts
      }
    }
  }
}
```

## Testing Today's KDP Alert

The system successfully detected and formatted today's KDP strangle:

```
🎯 Unusual Options Flow: $KDP - $19.9M strangle (1 put, 1 call)

⏰ Detected: 12:11 PM ET (Live Detection)

📊 The Flow:
• Strategy: $19.9M strangle (1 put, 1 call)
• Total Premium: $11.6M
• Primary Leg: $25.0 PUT | Exp: 2025-11-21

💡 Market Context:
• Company: Keurig Dr Pepper Inc.
• Sector: Consumer Defensive | Market Cap: Large_cap
• Market Regime: Low Vol

🎯 Why It Matters:
Large volatility play suggesting expectation of significant price movement
in either direction. With $19.9M in combined premium, this represents
substantial institutional positioning ahead of a potential catalyst.
```

**Features Demonstrated:**
- ✅ Multi-leg detection (found both put and call)
- ✅ Market context enrichment (sector, regime)
- ✅ Educational interpretation
- ✅ Proper disclaimers

## Command Reference

### Generate Draft Content

```bash
# Basic draft
python tools/social_content_generator.py --alert-id <ID>

# With manual context
python tools/social_content_generator.py --alert-id <ID> --context "Your analysis here"

# Save to file
python tools/social_content_generator.py --alert-id <ID> --output draft.txt
```

### Post to Social Media

```bash
# Create draft (if auto_post = false)
python tools/social_poster.py --alert-id <ID>

# Create draft with context
python tools/social_poster.py --alert-id <ID> --context "Your analysis"

# Publish existing draft
python tools/social_poster.py --draft-id <DRAFT_ID>
```

### Queue Management

```bash
# Check if alert qualifies
python strategies/flow_monitor/fm_social_notifier.py --check-alert <ID>

# Process delayed queue manually
python strategies/flow_monitor/fm_social_notifier.py --process-queue
```

### Database Queries

```bash
# View all drafts
python tools/direct_db_query.py --sql "SELECT * FROM social_posts ORDER BY created_at DESC LIMIT 10"

# Check which alerts were posted
python tools/direct_db_query.py --sql "SELECT id, symbol, significance_score, social_posted FROM flow_alerts WHERE social_posted = TRUE"
```

## Recommended First Steps

1. **Test Content Generation**: Use today's KDP alert (7650) to verify formatting
2. **Get Reddit API Credentials**: Set up app at reddit.com/prefs/apps
3. **Start with Profile Posts**: Use `"subreddits": ["u_YourUsername"]` initially
4. **Build Post History**: Post 5-10 drafts to your profile over 1-2 weeks
5. **Request Subreddit Access**: Message r/options mods with examples
6. **Enable Automation**: Switch to auto_post after confidence builds

## Quality Thresholds

Current settings (can be adjusted):

```json
"selection_criteria": {
  "min_significance_score": 7.0,      // Only exceptional alerts (v2 scoring, was 9.0)
  "min_premium_value": 5000000,       // $5M+ premium
  "max_posts_per_day": 3,             // Quality over quantity
  "exclude_earnings_day": true        // Avoid earnings noise
}
```

**Expected volume**: 1-2 posts per day (score > 9.0 is rare)

## Safety Features

1. **Rate Limiting**: Max 3 posts/day prevents spam
2. **Deduplication**: Won't post same alert twice
3. **Age Check**: Won't post alerts > 60 minutes old
4. **Draft Mode**: Review before posting when auto_post = false
5. **Error Handling**: Failed posts logged, won't crash Flow Monitor

## Next Steps

- [ ] Get Reddit API credentials
- [ ] Test content generation with recent alerts
- [ ] Review generated drafts for tone/accuracy
- [ ] Start with manual posting to profile
- [ ] Build 1-2 weeks of post history
- [ ] Request r/options subreddit access
- [ ] Enable auto_post after confidence builds

## Support

- Full docs: `docs/social-posting.md`
- Flow Monitor integration: `strategies/flow_monitor/fm_social_notifier.py`
- Content customization: `tools/social_content_generator.py`
- Posting logic: `tools/social_poster.py`

---

**Built:** 2025-10-06
**Status:** Complete, tested, disabled by default
**Ready to activate:** When you get Reddit API credentials
