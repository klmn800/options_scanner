-- Max Pain Analysis - Useful Queries
-- Use with: python tools/direct_db_query.py --db data/sector_archive/airlines.db --sql "<query>"

-- ============================================================
-- BASIC EXPLORATION
-- ============================================================

-- View all data, hits first
SELECT * FROM max_pain_analysis;

-- Just the hits
SELECT * FROM max_pain_analysis WHERE hit_max_pain = 1;

-- Just the misses
SELECT * FROM max_pain_analysis WHERE hit_max_pain = 0;

-- ============================================================
-- SUMMARY STATISTICS
-- ============================================================

-- Overall hit rate
SELECT
    COUNT(*) as total_observations,
    SUM(hit_max_pain) as hits,
    ROUND(SUM(hit_max_pain) * 100.0 / COUNT(*), 2) as hit_rate_pct
FROM max_pain_analysis;

-- Hits vs misses comparison
SELECT
    CASE hit_max_pain WHEN 1 THEN 'HIT' ELSE 'MISS' END as outcome,
    COUNT(*) as count,
    ROUND(AVG(ABS(price_change_pct)), 2) as avg_price_move,
    ROUND(AVG(ABS(mon_gap_pct)), 2) as avg_initial_gap,
    ROUND(AVG(ABS(fri_gap_pct)), 2) as avg_final_gap
FROM max_pain_analysis
GROUP BY hit_max_pain;

-- ============================================================
-- BY SYMBOL
-- ============================================================

-- Hit rate by symbol
SELECT
    symbol,
    COUNT(*) as weeks,
    SUM(hit_max_pain) as hits,
    ROUND(SUM(hit_max_pain) * 100.0 / COUNT(*), 2) as hit_rate_pct,
    ROUND(AVG(ABS(price_change_pct)), 2) as avg_price_move
FROM max_pain_analysis
GROUP BY symbol
ORDER BY hit_rate_pct DESC;

-- Most volatile symbol (price moves)
SELECT
    symbol,
    ROUND(AVG(ABS(price_change_pct)), 2) as avg_move,
    ROUND(MAX(ABS(price_change_pct)), 2) as max_move
FROM max_pain_analysis
GROUP BY symbol
ORDER BY avg_move DESC;

-- ============================================================
-- BY WEEK
-- ============================================================

-- Hit rate by week
SELECT
    week_id,
    COUNT(*) as symbols,
    SUM(hit_max_pain) as hits,
    ROUND(SUM(hit_max_pain) * 100.0 / COUNT(*), 2) as hit_rate_pct,
    ROUND(AVG(ABS(price_change_pct)), 2) as avg_price_move
FROM max_pain_analysis
GROUP BY week_id
ORDER BY week_id;

-- ============================================================
-- BY INITIAL DISTANCE
-- ============================================================

-- Hit rate by initial distance from max pain
SELECT
    CASE
        WHEN ABS(mon_gap_pct) < 2 THEN 'Very Close (<2%)'
        WHEN ABS(mon_gap_pct) < 5 THEN 'Close (2-5%)'
        WHEN ABS(mon_gap_pct) < 10 THEN 'Medium (5-10%)'
        ELSE 'Far (>10%)'
    END as distance_category,
    COUNT(*) as total,
    SUM(hit_max_pain) as hits,
    ROUND(SUM(hit_max_pain) * 100.0 / COUNT(*), 2) as hit_rate_pct
FROM max_pain_analysis
GROUP BY distance_category
ORDER BY AVG(ABS(mon_gap_pct));

-- ============================================================
-- MAX PAIN STABILITY
-- ============================================================

-- How often does max pain change during the week?
SELECT
    CASE
        WHEN ABS(max_pain_change_pct) < 1 THEN 'Stable (<1%)'
        WHEN ABS(max_pain_change_pct) < 5 THEN 'Small change (1-5%)'
        WHEN ABS(max_pain_change_pct) < 10 THEN 'Medium change (5-10%)'
        ELSE 'Large change (>10%)'
    END as stability,
    COUNT(*) as count,
    SUM(hit_max_pain) as hits,
    ROUND(SUM(hit_max_pain) * 100.0 / COUNT(*), 2) as hit_rate_pct
FROM max_pain_analysis
GROUP BY stability
ORDER BY AVG(ABS(max_pain_change_pct));

-- Cases where max pain moved significantly
SELECT
    week_id, symbol,
    mon_max_pain, fri_max_pain,
    max_pain_change_pct,
    hit_max_pain
FROM max_pain_analysis
WHERE ABS(max_pain_change_pct) > 5
ORDER BY ABS(max_pain_change_pct) DESC;

-- ============================================================
-- CONVERGENCE ANALYSIS
-- ============================================================

-- True convergence (started >3% away and hit)
SELECT *
FROM max_pain_analysis
WHERE ABS(mon_gap_pct) > 3
  AND hit_max_pain = 1
ORDER BY ABS(mon_gap_pct) DESC;

-- False starts (started close, ended up missing)
SELECT *
FROM max_pain_analysis
WHERE ABS(mon_gap_pct) < 2
  AND hit_max_pain = 0
ORDER BY ABS(fri_gap_pct) DESC;

-- ============================================================
-- DIRECTIONAL ANALYSIS
-- ============================================================

-- Did price move in the right direction?
SELECT
    CASE
        WHEN mon_gap_pct > 0 AND price_change_pct > 0 THEN 'Correct direction (needed to rise)'
        WHEN mon_gap_pct < 0 AND price_change_pct < 0 THEN 'Correct direction (needed to fall)'
        WHEN mon_gap_pct > 0 AND price_change_pct < 0 THEN 'Wrong direction (rose, needed to fall)'
        WHEN mon_gap_pct < 0 AND price_change_pct > 0 THEN 'Wrong direction (fell, needed to rise)'
        ELSE 'No gap or no move'
    END as direction_result,
    COUNT(*) as count,
    SUM(hit_max_pain) as hits
FROM max_pain_analysis
WHERE ABS(mon_gap_pct) > 0.5  -- Exclude trivial gaps
GROUP BY direction_result;

-- ============================================================
-- EXPORT FOR FURTHER ANALYSIS
-- ============================================================

-- Full dataset for Excel/Python
-- (Copy results to CSV)
SELECT
    week_id,
    symbol,
    week_start_date,
    week_end_date,
    mon_price,
    fri_price,
    mon_max_pain,
    fri_max_pain,
    price_change_pct,
    mon_gap_pct,
    fri_gap_pct,
    max_pain_change_pct,
    hit_max_pain,
    mon_oi,
    fri_oi,
    mon_iv,
    fri_iv
FROM max_pain_analysis
ORDER BY hit_max_pain DESC, week_id, symbol;
