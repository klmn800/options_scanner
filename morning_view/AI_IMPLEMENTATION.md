# AI Council Implementation Tracker

**Purpose:** Track remaining tasks and future enhancements for the AI Council multi-advisor analysis system.

**Created:** 2025-10-10
**Last Updated:** 2025-10-10

---

## 🎯 Completed Features

### ✅ Multi-Provider Infrastructure (2025-10-10)
- Unified interface for Anthropic, OpenAI, xAI, Google
- Config-driven model management (single source of truth)
- Automatic cost tracking and token counting
- Error handling with diagnostic messages

### ✅ Four Specialized Advisors (2025-10-10)
1. **General Analyst** (Haiku) - Morning views core data, basic OI metrics
2. **Advanced Detective** (Sonnet) - Deep dive with flow alerts, tracked contracts, option chain
3. **Risk Analyst** (GPT-4o-mini) - Position sizing, timing, Greeks, earnings risk
4. **Catalyst Hunter** (Grok-2) - News sentiment, articles, earnings, sector dynamics

### ✅ Synthesis System (2025-10-10)
- Chief Strategist combines all advisor outputs
- Three synthesis models available: Sonnet, Opus, Gemini Pro
- Produces trade thesis, risk assessment, final verdict

### ✅ Analysis Persistence (2025-10-10)
- 7-day cache in advisor_analysis_cache table
- Analyses load automatically on screen mount
- "Clear" button (C key) to delete cache and force fresh analysis

---

## 🚧 High Priority Tasks

### 1. xAI Live Search Integration
**Status:** 🔴 Not Started
**Priority:** HIGH
**Goal:** Enable real-time Twitter/X and web search for Catalyst Hunter

**Requirements:**
- Research xAI function calling / tool use API format
- Modify `XAIProvider.call()` to support `tools` parameter
- Add search results parsing
- Handle search costs: +$0.025 per search
- Make search automatic (not opt-in)

**Benefits:**
- Real-time Twitter/X sentiment analysis
- Breaking news detection
- Sector narrative tracking
- Market catalyst discovery

**Estimated Effort:** 2-3 hours
**Documentation:** https://docs.x.ai/docs/overview (check for tool calling)

---

### 2. Prompt Engineering Refinement
**Status:** 🟡 In Progress
**Priority:** HIGH
**Goal:** Eliminate markdown, reduce verbosity, improve insight density

**Current Issues:**
- Markdown still appearing (##, **) despite prompts
- Risk Analyst hedging language ("trades don't materialize as expected")
- Responses occasionally truncated at token limits

**Experiments to Try:**
- Add explicit negative examples: "DON'T write: ## Executive Summary"
- System prompt: "CRITICAL: Use zero markdown. Write in plain paragraphs."
- Test if model choice matters (e.g., all use Haiku for consistency?)
- A/B test different prompt phrasing

**Success Metrics:**
- 0 markdown formatting in 10 consecutive analyses
- No obvious/hedging statements
- 90%+ of analyses use <90% of token limit (not truncated)

**Estimated Effort:** Ongoing iteration

---

### 3. Data Source Review & Refinement
**Status:** 🔴 Not Started
**Priority:** MEDIUM-HIGH
**Goal:** Map complete data access requirements per advisor, implement optimal data sourcing

**Weekend Project Scope:**
- Document current data access per advisor (DONE in code, formalize in doc)
- Identify gaps in available data
- Research/implement new data sources:
  - Twitter sentiment (xAI Live Search covers this)
  - Reddit mentions (r/wallstreetbets, r/stocks, r/options)
  - Analyst ratings / price targets
  - Sector rotation signals
  - Insider trading activity
  - Short interest changes

**Advisor Data Source Matrix:**

| Data Source | General | Detective | Risk | Catalyst |
|------------|---------|-----------|------|----------|
| OI Summary | ✅ | ✅ | ✅ | ❌ |
| OI Timing | ✅ | ✅ | ❌ | ❌ |
| Flow Alerts | ❌ | ✅ | ✅ | ❌ |
| Option Contracts | ❌ | ✅ | ✅ | ❌ |
| News Sentiment | ❌ | ❌ | ❌ | ✅ |
| News Articles | ❌ | ❌ | ❌ | ✅ |
| Earnings | ❌ | ❌ | ✅ | ✅ |
| Symbol Metadata | ❌ | ❌ | ❌ | ✅ |
| Market Regime | ✅ | ✅ | ✅ | ✅ |
| Historical Prices | ❌ | ✅ | ❌ | ❌ |

**Estimated Effort:** 4-6 hours planning + implementation varies by source

---

### 4. Synthesis Database Access
**Status:** 🔴 Not Started
**Priority:** MEDIUM
**Goal:** Give Chief Strategist direct database access for omniscient analysis

**Context:**
- Synthesis currently only sees text from 4 advisors
- High context limit (2-3k tokens) designed for comprehensive data ingestion
- Could provide complete picture by querying database directly

**Architectural Questions:**
- Give Synthesis access to ALL tables via specialized data gathering function?
- Or limit to specific high-value data (option chain, flow alerts, news)?
- How to structure prompts for effective database-aware analysis?
- Cost implications of longer prompts (more input tokens)

**Potential Approach:**
```python
def gather_synthesis_data(symbol: str) -> Dict:
    # Gather comprehensive symbol data
    # - Complete option chain
    # - All flow alerts (last 30 days)
    # - All tracked contracts
    # - Full news history
    # - Earnings + historical performance
    # - Technical levels
    return complete_data_dict
```

**Estimated Effort:** 3-4 hours
**Risk:** May increase synthesis cost significantly

---

## 🔮 Future Enhancements (Low Priority)

### 5. Model Selection Flexibility
**Status:** 🔴 Not Started
**Goal:** Allow user to choose model per advisor

**Ideas:**
- TUI setting: Map each advisor to different model
- Test: All advisors use Haiku vs mixed models
- Cost vs quality tradeoffs

### 6. Custom Advisor Creation
**Status:** 🔴 Not Started
**Goal:** User-definable advisors with custom prompts and data access

**Features:**
- Add/remove advisors via TUI
- Configure: name, model, personality, focus tables, system prompt
- Save custom advisor configs

### 7. Analysis Export
**Status:** 🔴 Not Started
**Goal:** Export analyses to PDF, Markdown, or email

**Use Cases:**
- Share with trading group
- Archive high-conviction analyses
- Track analysis accuracy over time

### 8. Advisor Performance Tracking
**Status:** 🔴 Not Started
**Goal:** Track which advisor recommendations actually work

**Metrics:**
- Recommendation accuracy (if trade executed, did it hit 25% target?)
- Average cost per advisor
- User satisfaction ratings
- Frequency of use per advisor

---

## 📋 Known Issues & Limitations

### Current Limitations:
1. **Markdown Persists** - Despite prompts, LLMs default to markdown (ongoing iteration)
2. **Hallucination Risk** - Added option chain data to Detective, but LLMs can still invent data
3. **No Real-Time Data** - Catalyst Hunter relies on stale news database (xAI search will fix)
4. **Token Limits** - Compressed responses may lose nuance (dynamic +20% on re-analysis helps)
5. **Cost Accumulation** - Multiple analyses can get expensive ($0.05-0.10 per full session)

### Architectural Constraints:
- Textual TUI doesn't support rich formatting (markdown won't render anyway)
- Database locking during collection windows (Morning Views uses query DB)
- Cache expiration is simple (7 days), not sophisticated (based on data freshness)

---

## 💡 Research & Experimentation

### Questions to Explore:
1. **Do smaller models follow instructions better?** (Haiku vs Sonnet for brevity)
2. **Can we force plain text with output schemas?** (Structured output APIs)
3. **What's the optimal token limit per advisor role?** (currently 270-330)
4. **How does synthesis quality change with database access?**
5. **What's the cost/benefit of Live Search per query?** ($0.025 vs insight value)

### A/B Test Ideas:
- Same symbol, 4 different models, compare outputs
- Same advisor, different prompts, measure markdown usage
- Synthesis with vs without direct DB access
- Analysis quality: cached vs fresh

---

## 📚 Resources & Documentation

### Relevant Docs:
- `JOURNAL.md` - Daily changelog and session notes
- `advisor_config.json` - Advisor definitions and prompts
- `ai_council.py` - Core council logic and caching
- `advisor_data.py` - Data gathering per advisor type
- `ai_providers.py` - Multi-provider interface

### External References:
- xAI API Docs: https://docs.x.ai/docs/overview
- Anthropic API: https://docs.anthropic.com/
- OpenAI API: https://platform.openai.com/docs/
- Google Gemini: https://ai.google.dev/gemini-api/docs

### Research Papers:
- Few-shot prompting for structured outputs
- Chain-of-thought reasoning in financial analysis
- Tool use / function calling best practices

---

## ✅ Acceptance Criteria for "Complete"

The AI Council system will be considered **production-ready** when:

1. ✅ All 4 advisors provide analyses without errors
2. ✅ Analysis persistence works (7-day cache)
3. 🔴 Markdown formatting eliminated (0 instances in 20 analyses)
4. 🔴 xAI Live Search integrated and working
5. 🔴 Data sources fully documented and optimized per advisor
6. 🔴 Synthesis produces actionable trade recommendations (strike/date/size)
7. 🔴 Cost tracking accurate and visible to user
8. 🔴 User can configure advisors (at minimum: enable/disable per advisor)

**Current Status:** 2 / 8 criteria met

---

**Next Session Goals:**
1. Research xAI Live Search API
2. Implement tool calling for Catalyst Hunter
3. Test Live Search with real symbol
4. Iterate on prompts based on Live Search outputs

---

**Maintainer Notes:**
- Update this doc after each implementation session
- Move completed items from "High Priority" to "Completed Features"
- Add new discovered tasks to appropriate priority section
- Track cost/quality tradeoffs for future optimization
