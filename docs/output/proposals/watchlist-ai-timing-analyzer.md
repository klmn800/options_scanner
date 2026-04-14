# Watchlist AI Timing Analyzer - Vision Document

**Date:** October 22, 2025
**Status:** Proposed
**Scope:** AI-powered entry timing optimization for My Watchlist screen

---

## Problem Statement

**Current Workflow Gap:**
- Discovery AI helps filter 40+ triggered symbols → Top 5 to investigate
- Symbol Detail provides deep-dive analysis on individual symbols
- **Missing piece:** "Of my 10 watchlist symbols, which have optimal entry timing TODAY?"

**The Challenge:**
You've already screened symbols (added to watchlist), you've researched them (Symbol Detail analyses), but you still need to decide: "Which 2-3 should I enter today vs keep watching vs remove?"

This requires synthesizing:
- Prior AI analyses (context from days ago)
- Fresh data (what changed since last analysis)
- Market conditions (current regime)
- Timing signals (setup maturity, urgency, thesis confirmation)

---

## Vision: Meta-Analysis Portfolio Manager

**Watchlist AI = Synthesis Engine**

Unlike Discovery AI (screening) or Symbol Detail (research), Watchlist AI **synthesizes all existing analyses** to answer:

> "Given everything we know from prior research, what should I do with these symbols TODAY?"

---

## Key Differentiators

### Scope & Cost Tradeoff

| Screen | Symbols | Model | Cost | Question |
|--------|---------|-------|------|----------|
| Discovery | 40-50 | Haiku | $0.01 | "Which deserve research?" |
| **Watchlist** | **10** | **Sonnet** | **$0.04** | **"Which to enter TODAY?"** |
| Symbol Detail | 1 | Sonnet | $0.03 | "Tell me everything" |

**Cost Justification:** Watchlist analysis operates on pre-screened symbols where you're making actual entry decisions with real money. Worth spending 4x Discovery budget for better reasoning.

### Core Focus: Entry Timing Optimization

**Watchlist AI specifically answers:**
1. **Entry Ready Today**: Thesis confirmed, setup mature, timing optimal
2. **Still Developing**: Setup building, wait for confirmation
3. **Consider Removing**: Thesis broken, stale, no longer relevant

This is **materially different** from:
- Discovery: "Should I care about this symbol?"
- Symbol Detail: "What's the complete picture on this symbol?"

---

## Architecture: Multi-Source Data Synthesis

### Input Sources (Hierarchical Context)

**1. Cached AI Analyses (Last 5 Trading Days)**
```sql
SELECT symbol, analysis_text, created_at, model_used
FROM symbol_ai_analysis
WHERE symbol IN (...watchlist...)
AND created_at > DATE('now', '-5 days')
ORDER BY created_at DESC
```

Per symbol, pull:
- Symbol Detail analyses (deep-dive context)
- Discovery analysis (original trigger reason)
- Flow Pattern analyses (if implemented)

**2. Watchlist Metadata**
```sql
SELECT symbol, added_date, added_reason, relevance_score
FROM user_watchlist
WHERE symbol IN (...)
```

Context: When/why symbol was added (timeframe awareness)

**3. Fresh Metrics (Delta Analysis)**
- New alerts since last analysis
- Price movement since last analysis
- Days since last alert (staleness)
- Earnings proximity changes

**4. Market Context**
```sql
SELECT market_direction, market_regime
FROM market_daily_summary
WHERE trade_date = (SELECT MAX(trade_date) FROM market_daily_summary)
```

Current regime for alignment assessment

---

## AI Prompt Structure

### System Prompt
```
You are a portfolio timing advisor. You've previously analyzed these symbols in detail.
Now synthesize all prior analyses with fresh data to determine optimal entry timing TODAY.

Focus on:
1. Thesis confirmation (prior analysis predictions vs current data)
2. Setup maturity (building vs ready vs missed)
3. Timing urgency (windows opening/closing)
4. Thesis invalidation (what would break the setup)
```

### User Prompt (Per Watchlist Symbol)
```
SYMBOL: MGM
ADDED: 2 days ago (Reason: Discovery - Strong bullish flow)

PRIOR ANALYSES:
- [2 days ago, Symbol Detail]: "OI buildup at $45 calls, bullish flow,
  awaiting price confirmation. Entry if breaks $44.50 resistance."
- [2 days ago, Discovery]: "12 flow alerts in 5d, bullish bias,
  confluence score 4.2"

FRESH DATA (Since last analysis):
- New alerts: 2 (both bullish calls at $45-46 strikes)
- Price action: Broke $44.50 → now $45.20 (+1.5% since analysis)
- Days since last alert: 0 (fresh today)
- Active alerts: 14 (was 12)

MARKET CONTEXT:
- Regime: Bull
- Direction: Neutral→Bullish shift today

ANALYSIS:
Compare thesis from 2 days ago vs current state. Has setup matured?
Thesis confirming or invalidating? Entry window status?
```

---

## Output Format

### Categorized Recommendations

```
🤖 WATCHLIST TIMING ANALYSIS
Analyzed: 10 symbols | Market: Bullish | Time: 2:30 PM

═══════════════════════════════════════════════
ENTRY READY TODAY (Act Now)
═══════════════════════════════════════════════

1. MGM - THESIS CONFIRMED
   Prior Analysis (2d ago): "OI buildup, awaiting price breakout"
   Today's Update: Price broke $44.50 resistance → $45.20, 2 fresh alerts

   Entry Signal: ✅ Setup matured, confirmation received
   Suggested Trade: Nov 15 $46 calls (riding momentum)
   Risk: Quick 1.5% move may have front-run some upside

2. USB - TIME-SENSITIVE WINDOW
   Prior Analysis (12h ago): "Earnings play, IV cheap vs historical"
   Today's Update: Earnings tomorrow AM, fresh flow this morning

   Entry Signal: ⏰ Narrow window (earnings <24h)
   Suggested Trade: Straddle if entering, or skip (tight timing)
   Risk: Overnight hold into earnings = binary outcome

───────────────────────────────────────────────
STILL DEVELOPING (Keep Watching)
───────────────────────────────────────────────

3. BWA - SETUP BUILDING, NOT READY
   Discovery Analysis (3d ago): "Bullish flow, earnings in 10d"
   Today's Update: No fresh flow in 3 days, price consolidating

   Status: 📊 Setup intact but dormant
   Wait For: Fresh flow or price breakout above $48
   Remove If: No activity by Friday or bearish flow appears

4. ADT - EARLY STAGE
   Added yesterday (Discovery), no Symbol Detail analysis yet
   Today's Update: 1 new alert, mild positive price action

   Status: 🌱 Just added, needs more observation
   Action: Run Symbol Detail analysis if activity continues

───────────────────────────────────────────────
CONSIDER REMOVING (Thesis Broken or Stale)
───────────────────────────────────────────────

5. TSCO - THESIS INVALIDATED
   Prior Analysis (5d ago): "Accumulating call flow, bullish setup"
   Today's Update: 0 alerts in 5 days, -2.3% price decline

   Red Flags: ❌ Flow dried up, bearish price action
   Recommendation: Remove from watchlist (thesis broken)

6. HST - STALE / NO CONVICTION
   Added 8 days ago, last alert 12 days ago
   Today's Update: No activity, neutral price action

   Red Flags: ⚠️ Alerts preceded addition (late to party)
   Recommendation: Remove to free up watchlist space
```

### Status Indicators (In Watchlist Table)

Add visual column to My Watchlist table:

| Symbol | AI Status | Last Analysis |
|--------|-----------|---------------|
| MGM    | 🟢 Ready   | 2d ago       |
| USB    | 🟡 Urgent  | 12h ago      |
| BWA    | 🔵 Watch   | 3d ago       |
| TSCO   | 🔴 Remove  | 5d ago       |
| ADT    | ⚪ New     | Never        |

---

## Implementation Plan

### Phase 1: Core Engine (Week 1)

**Files to Create:**
- `morning_view/ai_watchlist_analyzer.py` - Core analysis engine

**Key Functions:**
```python
def analyze_watchlist_timing(watchlist_symbols: List[str],
                             force_refresh: bool = False) -> Dict:
    """Meta-analysis for entry timing

    Returns:
        {
            'entry_ready': [...],      # Act today
            'developing': [...],       # Keep watching
            'consider_removing': [...] # Thesis broken/stale
        }
    """

def gather_symbol_context(symbol: str) -> Dict:
    """Pull all cached analyses + fresh metrics for symbol"""

def build_synthesis_prompt(symbol_contexts: List[Dict],
                           market_context: Dict) -> str:
    """Build Sonnet prompt with multi-source context"""
```

**Integration Points:**
- `morning_view/screens/my_watchlist.py` - Add `A` key binding
- `data/analysis_cache.db` - Cache table `watchlist_timing_analysis`

### Phase 2: UI Enhancement (Week 1-2)

**Watchlist Table Updates:**
- Add "AI Status" column (🟢🟡🔵🔴⚪ indicators)
- Add "Last Analysis" column (time since cached analysis)

**Status Bar Updates:**
- Show cache age: `AI Timing: 2h ago | 3 ready, 4 watch, 2 remove`

**Analysis Result Screen:**
- Use categorized sections (Entry Ready / Developing / Remove)
- Color-coded priorities
- Clear action items per symbol

### Phase 3: Advanced Features (Week 2-3)

**Auto-Cleanup Suggestions:**
- After analysis, prompt: "Remove these 2 stale symbols from watchlist? (Y/N)"

**Notification Integration:**
- If symbol moves from "Developing" → "Entry Ready", notify user

**Historical Tracking:**
- Track timing recommendation accuracy
- "You entered MGM 2 days after 'Entry Ready' signal - outcome: +45%"

---

## Cost Analysis

### Per-Analysis Cost Breakdown

**Watchlist AI (Sonnet):**
- 10 symbols × ~300 tokens context each = 3,000 input tokens
- Prior analyses summary = ~2,000 input tokens
- Market context = ~500 input tokens
- **Total Input**: ~5,500 tokens = $0.0165
- **Output**: ~1,500 tokens = $0.0225
- **Total per analysis**: ~$0.04

**Daily Usage Pattern:**
- Morning check: $0.04
- Mid-day check: $0.00 (cached)
- End-of-day check: $0.00 (cached)
- Force refresh (if needed): $0.04

**Monthly cost**: ~$0.80-1.60 (assuming 1-2 fresh analyses per day)

### Cost Comparison to Manual Research

**Without Watchlist AI:**
- 10 symbols on watchlist
- Manually check each for fresh activity = 20-30 min/day
- Miss timing signals (don't notice thesis confirmation)
- **Cost**: ~10 hours/month of manual work

**With Watchlist AI:**
- Press `A` once per day
- Get synthesis of all prior research + fresh data
- Clear action priorities
- **Cost**: $1.60/month, 2 minutes/day

**ROI**: Save ~10 hours/month for $1.60 = $0.16/hour

---

## Success Metrics

### Quantitative
1. **Timing accuracy**: % of "Entry Ready" signals that lead to profitable entries
2. **Cleanup effectiveness**: % of "Remove" recommendations that were correct (thesis actually broke)
3. **Cache hit rate**: % of analyses served from cache vs fresh API calls
4. **User adoption**: Times per day Watchlist AI is triggered

### Qualitative
1. **Decision confidence**: Does user feel more confident in entry timing?
2. **Missed opportunities**: Reduction in "I should have entered that 2 days ago" regrets
3. **Watchlist hygiene**: Is watchlist staying lean (10-15 symbols) vs bloating (30+)?

---

## Future Enhancements

### Multi-Timeframe Analysis
- Morning: "What's ready for today's session?"
- Weekly: "What setups are building for next week?"

### Risk-Adjusted Recommendations
- Factor in portfolio exposure, position sizing, correlation

### Integration with Order Flow
- "Fresh $500K call sweep on MGM 5 min ago - thesis accelerating"

### Backtesting Framework
- Track all "Entry Ready" signals vs actual outcomes
- Refine prompt based on what actually works

---

## Open Questions

1. **Staleness threshold**: How old is "too old" for prior analyses? (Current: 5 days)
2. **Cache invalidation**: Force refresh if symbol has >3 new alerts since cached analysis?
3. **Notification system**: Push alerts when status changes (Developing → Entry Ready)?
4. **Integration with Symbol Detail**: One-click from Watchlist AI → deep-dive Symbol Detail?

---

## Conclusion

Watchlist AI Timing Analyzer transforms the watchlist from a **passive list** into an **active decision engine**.

By synthesizing all prior AI research with fresh data, it answers the critical question:

> "I've done my research. What should I DO today?"

This bridges the gap between research (Symbol Detail) and execution, providing the **timing intelligence** needed to act on opportunities at the optimal moment.

**Core Value Proposition:**
- Saves 10+ hours/month of manual watchlist review
- Reduces missed timing opportunities
- Provides objective entry/exit signals
- Maintains watchlist hygiene (removes stale symbols)
- **Costs ~$1.60/month for portfolio-level AI guidance**

---

**Next Steps:**
1. Review and approve proposal
2. Implement Phase 1 (core engine)
3. Test with real watchlist data
4. Iterate based on actual trading decisions
