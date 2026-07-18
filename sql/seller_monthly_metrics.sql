-- seller_monthly_metrics.sql
--
-- GRAIN: one row per (seller_id, month). This is the fact-table grain used
-- everywhere downstream (risk scoring, anomaly detection, Power BI export).
--
-- Month = the order's PURCHASE month (not delivery month). This matters:
-- a late shipment or a cancellation is a failure that happened against an
-- order the seller took on in a given month, so performance is attributed
-- to when the seller accepted the order, not to whenever it was resolved.
--
-- DENOMINATOR RULES (this is the part worth defending in an interview):
--   - late_shipment_rate  = late_orders / delivered_orders
--       Denominator is DELIVERED orders only. A cancelled order was never
--       "on time" or "late" -- it's a different failure mode, tracked
--       separately as cancellation_rate. Mixing the two into one rate
--       would hide which problem a seller actually has (fulfillment speed
--       vs. inventory/stock accuracy), which is the opposite of what a
--       coaching program needs.
--   - cancellation_rate   = cancelled_orders / total_orders
--       Denominator is ALL orders placed, because every cancellation is a
--       cost regardless of what would have happened at delivery.
--   - late definition      = order_delivered_customer_date >
--                             order_estimated_delivery_date
--       i.e. arrived after the promise date shown to the buyer at checkout.
--
-- "Returns" are not tracked as a separate status in this dataset (Olist
-- only exposes order-level status, not post-delivery returns), so
-- cancellation_rate is used throughout this project as an explicit PROXY
-- for return/refund-driving behavior. This proxy choice is documented
-- again in powerbi_export/data_dictionary.md and reports/business_case_summary.md
-- so it is never presented as if it were literal return data.

DROP TABLE IF EXISTS seller_monthly_metrics;
CREATE TABLE seller_monthly_metrics AS
WITH order_seller AS (
    -- One row per (order, seller). In this dataset each order has exactly
    -- one seller (see data dictionary "Known simplifications"), so this is
    -- also one row per order -- but written as a join so the query still
    -- works unmodified if the real multi-seller-per-order Olist data is
    -- swapped in later.
    SELECT DISTINCT oi.order_id, oi.seller_id
    FROM order_items oi
),
order_facts AS (
    SELECT
        os.seller_id,
        o.order_id,
        strftime('%Y-%m', o.order_purchase_timestamp) AS month_key,
        o.order_status,
        CASE WHEN o.order_status = 'delivered' THEN 1 ELSE 0 END AS is_delivered,
        CASE WHEN o.order_status = 'canceled'  THEN 1 ELSE 0 END AS is_cancelled,
        CASE
            WHEN o.order_status = 'delivered'
                 AND o.order_delivered_customer_date > o.order_estimated_delivery_date
            THEN 1 ELSE 0
        END AS is_late
    FROM orders o
    JOIN order_seller os ON os.order_id = o.order_id
),
revenue_facts AS (
    SELECT
        oi.seller_id,
        strftime('%Y-%m', o.order_purchase_timestamp) AS month_key,
        SUM(oi.price + oi.freight_value) AS revenue
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    GROUP BY oi.seller_id, strftime('%Y-%m', o.order_purchase_timestamp)
),
review_facts AS (
    SELECT
        os.seller_id,
        strftime('%Y-%m', o.order_purchase_timestamp) AS month_key,
        AVG(r.review_score) AS avg_review_score,
        COUNT(r.review_id)  AS review_count
    FROM order_reviews r
    JOIN orders o ON o.order_id = r.order_id
    JOIN order_seller os ON os.order_id = o.order_id
    GROUP BY os.seller_id, strftime('%Y-%m', o.order_purchase_timestamp)
),
monthly_marketplace_revenue AS (
    -- Total marketplace revenue per month, used to express each seller's
    -- revenue_share -- i.e. "revenue contribution" relative to that month's
    -- whole marketplace, not an absolute number that's meaningless on its own.
    SELECT month_key, SUM(revenue) AS marketplace_revenue
    FROM revenue_facts
    GROUP BY month_key
)
SELECT
    f.seller_id,
    f.month_key,
    COUNT(f.order_id)                                   AS total_orders,
    SUM(f.is_delivered)                                 AS delivered_orders,
    SUM(f.is_late)                                       AS late_orders,
    ROUND(1.0 * SUM(f.is_late) / NULLIF(SUM(f.is_delivered), 0), 4)      AS late_shipment_rate,
    SUM(f.is_cancelled)                                  AS cancelled_orders,
    ROUND(1.0 * SUM(f.is_cancelled) / NULLIF(COUNT(f.order_id), 0), 4)   AS cancellation_rate,
    ROUND(rv.avg_review_score, 3)                        AS avg_review_score,
    COALESCE(rv.review_count, 0)                         AS review_count,
    ROUND(COALESCE(rf.revenue, 0), 2)                    AS revenue,
    ROUND(COALESCE(rf.revenue, 0) / NULLIF(mmr.marketplace_revenue, 0), 4) AS revenue_share_of_marketplace
FROM order_facts f
LEFT JOIN revenue_facts rf
       ON rf.seller_id = f.seller_id AND rf.month_key = f.month_key
LEFT JOIN review_facts rv
       ON rv.seller_id = f.seller_id AND rv.month_key = f.month_key
LEFT JOIN monthly_marketplace_revenue mmr
       ON mmr.month_key = f.month_key
GROUP BY f.seller_id, f.month_key
ORDER BY f.seller_id, f.month_key;

CREATE INDEX IF NOT EXISTS idx_smm_seller ON seller_monthly_metrics(seller_id);
CREATE INDEX IF NOT EXISTS idx_smm_month  ON seller_monthly_metrics(month_key);
