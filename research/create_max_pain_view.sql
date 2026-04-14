-- Max Pain Analysis View
-- Dynamically handles Thursday or Friday expirations

CREATE VIEW IF NOT EXISTS max_pain_analysis AS
WITH weekly_pairs AS (
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
    week_id,
    symbol,
    week_start_date,
    week_end_date,
    mon_price,
    fri_price,
    mon_max_pain,
    fri_max_pain,
    ROUND((fri_price - mon_price) / mon_price * 100, 2) as price_change_pct,
    ROUND((mon_max_pain - mon_price) / mon_price * 100, 2) as mon_gap_pct,
    ROUND((fri_max_pain - fri_price) / fri_price * 100, 2) as fri_gap_pct,
    ROUND((fri_max_pain - mon_max_pain) / mon_max_pain * 100, 2) as max_pain_change_pct,
    CASE WHEN ABS(fri_price - fri_max_pain) / fri_price * 100 <= 1.0 THEN 1 ELSE 0 END as hit_max_pain_1pct,
    CASE WHEN ABS(fri_price - fri_max_pain) / fri_price * 100 <= 2.0 THEN 1 ELSE 0 END as hit_max_pain_2pct,
    CASE WHEN ABS(fri_price - fri_max_pain) / fri_price * 100 <= 3.0 THEN 1 ELSE 0 END as hit_max_pain_3pct,
    mon_oi,
    fri_oi,
    mon_iv,
    fri_iv
FROM weekly_pairs
ORDER BY hit_max_pain_1pct DESC, week_id, symbol;
