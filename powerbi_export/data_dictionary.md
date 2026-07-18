# Data Dictionary — SellerHealth Watchlist Power BI Export

Four CSVs, built by `src/build_powerbi_export.py` from the SQL + Python
layers. Star-schema shape: one fact table, three dimension tables.

```
dim_seller ── (seller_id) ──> fact_seller_month <── (month_date) ── dim_month
     │
     └── (seller_state = region_state) ──> dim_region
```

---

## fact_seller_month.csv
**Grain: one row per seller, per calendar month.** Every numeric metric
below is *for that seller, in that month only* — not a running total.

| Column | Meaning |
|---|---|
| `seller_id` | Unique seller identifier (relationship key to `dim_seller`). |
| `month_key` | Month as text, `YYYY-MM` (e.g. `2017-03`). Human-readable label. |
| `month_date` | Month as a real date (first of month). **Relationship key to `dim_month`** — use this one for joins/time intelligence, not `month_key`. |
| `total_orders` | Orders placed with this seller this month (any status). |
| `delivered_orders` | Of those, how many were actually delivered. |
| `late_orders` | Delivered orders that arrived *after* the promised delivery date. |
| `late_shipment_rate` | `late_orders / delivered_orders`. **Denominator is delivered orders only** — a cancelled order was never "on time" or "late," it's a different failure mode (see `cancellation_rate`). |
| `cancelled_orders` | Orders cancelled before delivery. |
| `cancellation_rate` | `cancelled_orders / total_orders`. Used throughout this project as a **proxy for returns/refunds** — the source dataset only tracks order-level status, not a separate post-delivery "return" event, so cancellations are the closest available signal for refund-driving behavior. This is a modeling choice, not a literal return count. |
| `avg_review_score` | Mean of 1–5 review scores for this seller's orders this month. |
| `review_count` | Number of reviews behind that average (low counts = less reliable average). |
| `revenue` | Sum of item price + freight for this seller this month, in **BRL (R$)** — the dataset's native currency. |
| `revenue_share_of_marketplace` | This seller's revenue ÷ total marketplace revenue that same month. "Revenue contribution," expressed relative to that month's whole marketplace rather than as a raw number that's hard to interpret alone. |
| `risk_late_component` | Points (of 100) this seller's risk score gets from late shipments this month. Weight: 35%. |
| `risk_cancel_component` | Points from cancellations. Weight: 30%. |
| `risk_review_component` | Points from (low) review score. Weight: 25%. |
| `risk_volume_component` | Points from an order-volume drop vs. this seller's own recent trend. Weight: 10%. |
| `risk_score` | **Sum of the four components above, 0–100.** Higher = worse. See "Risk Score Methodology" below. |
| `risk_score_zscore` | How many standard deviations this month's risk score is above this seller's own recent trend. Blank/empty when a seller has under 2 months of prior history (not enough data yet, not a zero). |
| `anomaly_flag` | 1 if `risk_score_zscore > 2.0` — a *sudden* deterioration, not just "currently bad." See methodology below. |
| `is_watchlist` | 1 if `risk_score >= 70` this month. The threshold used by the Streamlit Watchlist module and the README's example DAX measures — change it in one place (`RISK_WATCHLIST_THRESHOLD` in `build_powerbi_export.py`) if you want a different cutoff. |

## dim_seller.csv
**Grain: one row per seller** (lifetime attributes, not month-by-month).

| Column | Meaning |
|---|---|
| `seller_id` | Relationship key to `fact_seller_month`. |
| `seller_city`, `seller_state`, `seller_zip_code_prefix` | Seller's registered location. |
| `first_active_month`, `last_active_month` | First/last month this seller has any order, in this dataset's window. |
| `lifetime_orders`, `lifetime_revenue` | Totals across the seller's full history in the data. |
| `lifetime_late_shipment_rate`, `lifetime_cancellation_rate`, `lifetime_avg_review_score` | Same definitions as the monthly fact columns, computed over the seller's entire history instead of one month. |
| `latest_month_risk_score` | This seller's `risk_score` in the most recent month present in the data. |
| `current_watchlist_flag` | 1 if that latest-month score is ≥ 70 — "is this seller on the watchlist *right now*," as of the last pipeline run. |
| `region_state` | Same value as `seller_state`; kept as an explicit relationship key to `dim_region`. |

## dim_region.csv
**Grain: one row per Brazilian state** (13 states present in this dataset).

| Column | Meaning |
|---|---|
| `region_state` | Two-letter state code (e.g. `SP`, `RJ`). Relationship key to `dim_seller.region_state`. |
| `region_name` | Macro-region the state belongs to (Southeast, South, Northeast, North, Central-West) — Brazil's standard regional grouping, for roll-up reporting above the state level. |

## dim_month.csv
**Grain: one row per calendar month** in the fact table's range — a
continuous calendar with no gaps, which Power BI's time-intelligence
functions (e.g. `DATEADD`) require.

| Column | Meaning |
|---|---|
| `month_date` | First-of-month date. Relationship key to `fact_seller_month.month_date`. **Mark this table as a Date Table on this column** (Power BI: Table tools → Mark as Date Table) before using any DAX time-intelligence function. |
| `month_key`, `month_name`, `quarter`, `year` | Display-friendly labels for slicers and axis labels. |

---

## Risk Score Methodology (plain-language version)

Every seller-month gets a score from **0 (healthy) to 100 (highest risk)**,
built from four ingredients, each scored relative to that same month's
other sellers (so one bad month for the whole marketplace — e.g. a
carrier-wide delay — doesn't automatically flag everyone):

| Signal | Weight | Why this weight |
|---|---|---|
| Late shipments | 35% | Biggest driver of CS tickets and refunds; fully within the seller's control. |
| Cancellations | 30% | Direct lost revenue + refund cost; usually a stock-accuracy issue — also seller-side and coachable. |
| Review score | 25% | A real signal, but a *lagging* one that blends in product quality too, not fulfillment alone — so weighted third. |
| Order volume drop | 10% | An early-warning sign (buyers already leaving) that can show up before the other three metrics do; lowest weight because volume swings also have harmless causes like seasonality. |

The four weighted pieces are just added together — **no machine learning,
no fitted coefficients, nothing that isn't a one-line explanation.** That
is intentional: a coaching program needs a score an ops manager can
audit and defend, not one that requires trusting a model.

**Anomaly flag** is a separate signal from the risk score: it asks "did
this seller just get suddenly worse," by comparing this month's score to
that seller's own recent average. It's designed to catch a seller who was
fine for a year and just broke down — which a simple "is the score above
70" rule would miss until it's already chronic.

Full formula, code, and the reasoning behind every threshold: `src/risk_score.py` and `src/anomaly_detection.py` in the project repo.
