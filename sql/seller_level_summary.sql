-- seller_level_summary.sql
--
-- GRAIN: one row per seller_id (lifetime, across the full window in
-- seller_monthly_metrics). This is the source for the Power BI dim_seller
-- table -- static/slowly-changing attributes about a seller, as opposed to
-- the month-by-month fact grain in seller_monthly_metrics.
--
-- Depends on seller_monthly_metrics already being built (run
-- seller_monthly_metrics.sql first).

DROP TABLE IF EXISTS seller_level_summary;
CREATE TABLE seller_level_summary AS
SELECT
    s.seller_id,
    s.seller_city,
    s.seller_state,
    s.seller_zip_code_prefix,
    MIN(m.month_key)                                          AS first_active_month,
    MAX(m.month_key)                                           AS last_active_month,
    SUM(m.total_orders)                                        AS lifetime_orders,
    ROUND(SUM(m.revenue), 2)                                   AS lifetime_revenue,
    ROUND(1.0 * SUM(m.late_orders) / NULLIF(SUM(m.delivered_orders), 0), 4)     AS lifetime_late_shipment_rate,
    ROUND(1.0 * SUM(m.cancelled_orders) / NULLIF(SUM(m.total_orders), 0), 4)    AS lifetime_cancellation_rate,
    ROUND(SUM(m.avg_review_score * m.review_count) / NULLIF(SUM(m.review_count), 0), 3) AS lifetime_avg_review_score
FROM sellers s
JOIN seller_monthly_metrics m ON m.seller_id = s.seller_id
GROUP BY s.seller_id, s.seller_city, s.seller_state, s.seller_zip_code_prefix;
