-- Max Pain Analysis View with Baselines
-- Includes Monday/Friday specific baselines for volume and OI
-- Shows deviation from baseline (signed %) to see direction

DROP VIEW IF EXISTS max_pain_analysis;

CREATE VIEW max_pain_analysis AS
WITH
-- Calculate symbol-specific Monday baselines for volume (same period as option_symbol_summary)
monday_volume_baseline AS (
    SELECT
        symbol,
        AVG(volume) as baseline_mon_vol
    FROM historical_prices
    WHERE strftime('%w', trade_date) = '1'
    AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    AND trade_date >= (SELECT MIN(trade_date) FROM option_symbol_summary WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL'))
    AND trade_date <= (SELECT MAX(trade_date) FROM option_symbol_summary WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL'))
    GROUP BY symbol
),
-- Calculate symbol-specific Friday baselines for volume (same period as option_symbol_summary)
friday_volume_baseline AS (
    SELECT
        symbol,
        AVG(volume) as baseline_fri_vol
    FROM historical_prices
    WHERE strftime('%w', trade_date) = '5'
    AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    AND trade_date >= (SELECT MIN(trade_date) FROM option_symbol_summary WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL'))
    AND trade_date <= (SELECT MAX(trade_date) FROM option_symbol_summary WHERE symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL'))
    GROUP BY symbol
),
-- Calculate symbol-specific Monday baselines for OI
monday_oi_baseline AS (
    SELECT
        symbol,
        AVG(total_open_interest) as baseline_mon_oi
    FROM option_symbol_summary
    WHERE strftime('%w', trade_date) = '1'
    AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    GROUP BY symbol
),
-- Calculate symbol-specific Friday baselines for OI
friday_oi_baseline AS (
    SELECT
        symbol,
        AVG(total_open_interest) as baseline_fri_oi
    FROM option_symbol_summary
    WHERE strftime('%w', trade_date) = '5'
    AND symbol IN ('AAL', 'ALK', 'DAL', 'JBLU', 'LUV', 'UAL')
    GROUP BY symbol
),
-- Get Monday/Friday pairs for max pain weeks
weekly_pairs AS (
    SELECT
        strftime('%Y-%W', mon.trade_date) as week_id,
        mon.symbol,
        mon.trade_date as week_start_date,
        exp.trade_date as week_end_date,
        mon.close_price as mon_price,
        exp.close_price as fri_price,
        mon.max_pain_by_friday as mon_max_pain,
        exp.max_pain_by_friday as fri_max_pain,
        mon.total_open_interest as mon_oi,
        exp.total_open_interest as fri_oi,
        mon.iv_front_month as mon_iv,
        exp.iv_front_month as fri_iv
    FROM option_symbol_summary mon
    JOIN option_symbol_summary exp
        ON mon.symbol = exp.symbol
        AND strftime('%Y-%W', mon.trade_date) = strftime('%Y-%W', exp.trade_date)
        AND strftime('%w', mon.trade_date) = '1'  -- Monday
        AND strftime('%w', exp.trade_date) IN ('4', '5')  -- Thursday OR Friday
    WHERE mon.max_pain_by_friday IS NOT NULL
      AND exp.max_pain_by_friday IS NOT NULL
      -- Prefer Friday if both Thu and Fri exist in same week
      AND exp.trade_date = (
          SELECT MAX(trade_date)
          FROM option_symbol_summary
          WHERE symbol = mon.symbol
            AND strftime('%Y-%W', trade_date) = strftime('%Y-%W', mon.trade_date)
            AND strftime('%w', trade_date) IN ('4', '5')
            AND max_pain_by_friday IS NOT NULL
      )
)
SELECT
    wp.week_id,
    wp.symbol as symbol,
    wp.week_start_date,
    wp.week_end_date,

    -- Prices and max pain
    wp.mon_price,
    wp.fri_price,
    wp.mon_max_pain,
    wp.fri_max_pain,
    ROUND((wp.fri_price - wp.mon_price) / wp.mon_price * 100, 2) as price_change_pct,
    ROUND((wp.mon_max_pain - wp.mon_price) / wp.mon_price * 100, 2) as mon_gap_pct,
    ROUND((wp.fri_max_pain - wp.fri_price) / wp.fri_price * 100, 2) as fri_gap_pct,
    ROUND((wp.fri_max_pain - wp.mon_max_pain) / wp.mon_max_pain * 100, 2) as max_pain_change_pct,

    -- Hit flags
    CASE WHEN ABS(wp.fri_price - wp.fri_max_pain) / wp.fri_price * 100 <= 1.0 THEN 1 ELSE 0 END as hit_max_pain_1pct,
    CASE WHEN ABS(wp.fri_price - wp.fri_max_pain) / wp.fri_price * 100 <= 2.0 THEN 1 ELSE 0 END as hit_max_pain_2pct,
    CASE WHEN ABS(wp.fri_price - wp.fri_max_pain) / wp.fri_price * 100 <= 3.0 THEN 1 ELSE 0 END as hit_max_pain_3pct,

    -- OI
    wp.mon_oi,
    wp.fri_oi,
    wp.mon_iv,
    wp.fri_iv,

    -- Volume baselines
    ROUND(mvb.baseline_mon_vol, 0) as baseline_mon_vol,
    ROUND(fvb.baseline_fri_vol, 0) as baseline_fri_vol,

    -- Actual volumes for this week
    ROUND(mon_hp.volume, 0) as mon_vol,
    ROUND(fri_hp.volume, 0) as fri_vol,

    -- Volume deviation from baseline (signed %)
    ROUND((mon_hp.volume - mvb.baseline_mon_vol) / mvb.baseline_mon_vol * 100, 2) as mon_vol_dev_pct,
    ROUND((fri_hp.volume - fvb.baseline_fri_vol) / fvb.baseline_fri_vol * 100, 2) as fri_vol_dev_pct,

    -- OI baselines
    ROUND(moib.baseline_mon_oi, 0) as baseline_mon_oi,
    ROUND(foib.baseline_fri_oi, 0) as baseline_fri_oi,

    -- OI deviation from baseline (signed %)
    ROUND((wp.mon_oi - moib.baseline_mon_oi) / moib.baseline_mon_oi * 100, 2) as mon_oi_dev_pct,
    ROUND((wp.fri_oi - foib.baseline_fri_oi) / foib.baseline_fri_oi * 100, 2) as fri_oi_dev_pct

FROM weekly_pairs wp
-- Join volume data
LEFT JOIN historical_prices mon_hp
    ON wp.symbol = mon_hp.symbol AND wp.week_start_date = mon_hp.trade_date
LEFT JOIN historical_prices fri_hp
    ON wp.symbol = fri_hp.symbol AND wp.week_end_date = fri_hp.trade_date
-- Join baselines
LEFT JOIN monday_volume_baseline mvb ON wp.symbol = mvb.symbol
LEFT JOIN friday_volume_baseline fvb ON wp.symbol = fvb.symbol
LEFT JOIN monday_oi_baseline moib ON wp.symbol = moib.symbol
LEFT JOIN friday_oi_baseline foib ON wp.symbol = foib.symbol

ORDER BY hit_max_pain_1pct DESC, week_id, symbol;
