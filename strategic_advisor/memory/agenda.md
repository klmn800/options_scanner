# Investigation Agenda

Prioritized threads to pull on. Updated each session.

---

## Priority A — Next Session

### A1. Score-Performance Relationship: Real or Confounded?
The inverse correlation between significance_score and max_prof_7d_pct is the most important finding from Session 001. Before proposing scoring changes, I need to determine if this is:
- A genuine scoring flaw (score doesn't predict outcomes, period)
- A market regime effect (April 2026 was bullish, making lower-scored v2 alerts look better)
- A DTE confound (lower-scored alerts might cluster at shorter DTEs, which naturally have higher % gains)
- A selection bias (v2 captured cheaper options with higher percentage swing potential)

**Method:** Run the analysis controlling for DTE and time period. Within the same DTE band, does score still show an inverse relationship? Within the same month, does the pattern hold?

**Also:** Read the evaluator code in detail — understand exactly what max_prof_7d_pct measures and how it's calculated.

### A2. expected_move_pct Data Quality
Map out: What function calculates this? Why is it producing values >100% for dozens of symbols? What depends on it? Is the signal system actually isolated from this bad data, or does it leak through anywhere?

---

## Priority B — Following Sessions

### B1. The Feedback Loop Gap
The system generates alerts but doesn't learn from actual trading outcomes. This is the biggest architectural gap. Explore what a minimal trade journal / outcome tracker would look like. Read the existing user_watchlist infrastructure and the Morning View TUI state to understand what already exists.

### B2. Evaluation Coverage Gap
Why are 40% of older alerts missing profitability data? Is this expected (expired options) or a pipeline bug? Quantify how much of the historical dataset is lost and whether it matters for analysis.

### B3. Earnings Signal Ramp-Up Tracking
As Q1 2026 earnings season progresses, track how the 6Q-weighted signals perform. Design a monitoring approach — what should I query each session to build a picture over time?

### B4. v3 Alert Scoring Design Review
The v3 design doc is thoughtful but may not address the core finding. After A1 confirms/refutes the score-performance issue, review v3 with fresh eyes and propose adjustments.

### B5. Unused Data & Feature Audit
What tables are populated but never queried by any pipeline? What features exist in code but aren't wired into the orchestrator? Is complexity being accumulated without commensurate value?

---

## Priority C — Longer Term

### C1. System Architecture Assessment
The system has grown organically over 7+ months. Map the data flow end-to-end and identify structural risks or simplification opportunities.

### C2. Trading Style Alignment Audit
Does the system's design actually serve Ben's trading style? He's a swing trader buying options on <$60 stocks with <$300 positions and a 25% profit target. How much of the system's analysis directly helps that?

### C3. Self-Assessment Framework
After 5-10 sessions, build a way to evaluate my own recommendations' quality. Am I getting deeper or repeating myself? Are my proposals practical or theoretical?

---

*Last updated: Session 001, 2026-04-17*
