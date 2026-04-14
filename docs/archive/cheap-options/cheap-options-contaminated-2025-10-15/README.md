# Cheap Options Research - CONTAMINATED (Deprecated 2025-10-15)

## Why These Files Are Deprecated

These files represent research that was contaminated by **data snooping** and **overfitting**:

### Fatal Flaws

1. **No Train/Test Split**
   - Analyzed entire Aug 18 - Oct 15 dataset at once
   - Optimized parameters on full data
   - "Verified" on subsets of same data
   - Result: Overfit to noise

2. **Parameter Optimization Without Hypothesis**
   - Swept parameters to find what "worked"
   - No market structure reasoning
   - Found correlations, not causation
   - Example: "Vega 0.015-0.035" has no theoretical basis

3. **Evidence of Overfitting**
   - Analysis A claimed 40% win rate
   - Analysis B verification found 27.74% win rate
   - 12-point drop indicates fitting noise
   - Results not trustworthy

## What We Learned (Possibly Real)

Some patterns may be legitimate and worth exploring with proper methodology:

- ✓ ETF dominance (85% opportunities from sector/index ETFs)
- ✓ Winners are fast (1-3 days to target)
- ✓ Winners are strong (70-80% returns)
- ✓ Calls-only pattern emerged
- ✓ Deep OTM (delta <0.15) still achieved wins

**However:** These findings are contaminated and need independent validation.

## Files Included

### Analysis A (Original - Claude)
- `cheap-options-research-NOTES.md` (805 lines)
- `cheap-options-research-EVIDENCE.md` (735 lines)
- `cheap-options-scalping-research-FINDINGS.md` (20 pages)

### Analysis B (Verification - Second Analyst)
- `cheap-options-research-NOTES - B.md` (471 lines)
- `cheap-options-research-EVIDENCE - B.md` (461 lines)

### Analysis Scripts
- `tradeable_moments_analysis.py`
- `parameter_analysis.py`
- `combined_filter_test.py`
- `full_sample_test.py`
- `verify_original.py`
- `multivariate_analysis.py`
- `phase4_time_validation.py`
- `practical_constraints.py`

## DO NOT USE These Results

❌ Do not implement strategies based on these findings
❌ Do not use parameter ranges identified here
❌ Do not trust win rate or EV claims
❌ October data has been contaminated (cannot use as holdout)

## Next Steps

Use the clean research plan: `docs/cheap-options-CLEAN-RESEARCH-PLAN.md`

**Requirements for valid research:**
1. Lock holdout data BEFORE any analysis
2. Form hypothesis based on market structure
3. Test hypothesis ONCE on holdout
4. Accept failure if it doesn't generalize

**Recommended approach:**
- Wait for Nov-Dec data as fresh holdout
- Use Aug-Oct as training period
- Follow proper scientific methodology
- Don't peek at holdout until final test

---

**Date Deprecated:** 2025-10-15
**Reason:** Data snooping, overfitting, lack of proper validation methodology
**Replacement:** Clean research plan (proper train/test methodology)
