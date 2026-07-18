"""
generate_business_case.py

Auto-generates reports/business_case_summary.md from whatever is
currently in `seller_month_scored` -- every number in the report is
computed here, none are typed in by hand, so re-running this script after
a data refresh (or after swapping in the real Kaggle dataset) regenerates
the report with current figures.

WHY A TRAILING 3-MONTH WINDOW, NOT JUST "THE LATEST MONTH"
-----------------------------------------------------------------
An earlier version of this script used only the single most recent month.
On this dataset that produced a coaching pool of just 1 seller at the
risk >= 70 threshold -- technically correct, but too thin a sample to
build a business case on, and it doesn't reflect how an ops team would
actually run this (nobody enrolls a sudden coaching program off one
month's snapshot). Pooling the trailing 3 months gives a larger, steadier
sample for both the "bottom 5%" ranking and the cancellation/late-shipment
totals it's compared against, while still being a "recent, current state"
view rather than the seller's entire lifetime history.

IMPORTANT HONESTY NOTE ON THE DOLLAR FIGURE
-----------------------------------------------------------------
This project runs on synthetic data (see src/generate_synthetic_data.py),
so the "prevented cost" figure below is an ILLUSTRATIVE SCENARIO
CALCULATION, not a validated real-world estimate. It rests on one clearly
labeled, easily-changed assumption: COST_PER_CANCELLATION_BRL. Swap that
one constant for a real internal CS/refund-handling cost figure and every
downstream number recalculates. Presenting a fabricated-but-precise
dollar figure as if it were audited fact would be a bad look in an
interview if probed -- the defensible story is "here is the calculation
and here is the one assumption it rests on," not "here is a verified
number."

Currency: figures are in BRL (R$), the Olist dataset's native currency,
not converted to USD -- see README "Assumptions & Limitations."
"""

import os
import sqlite3
from datetime import date

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "seller_health.db")
OUT_PATH = os.path.join(BASE_DIR, "reports", "business_case_summary.md")

WINDOW_MONTHS = 3
BOTTOM_PCT = 0.05     # "bottom 5% of sellers" = the 5% with the WORST (highest) risk scores -- the headline stat
COACHING_PCT = 0.10   # coaching pool = bottom 10% -- a deliberately wider net than the headline 5%, to catch
                      # adjacent at-risk sellers before they become the next month's bottom 5%. Percentile-based
                      # (not a fixed absolute score) because risk_score's usable range shifts once you average
                      # it over several months -- a fixed cutoff like "70" can end up above every seller's
                      # smoothed average and silently produce an empty coaching pool.
COST_PER_CANCELLATION_BRL = 45.0  # ILLUSTRATIVE placeholder (CS handling + refund processing + re-ship overhead).
                                   # Replace with an actual internal figure if you have one.


def plural(n, singular="seller", pluralized="sellers"):
    return singular if n == 1 else pluralized


def main():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM seller_month_scored", conn)
    conn.close()

    all_months = sorted(df["month_key"].unique())
    window = all_months[-WINDOW_MONTHS:]
    window_label = f"{window[0]} to {window[-1]}"
    win_df = df[df["month_key"].isin(window)].copy()

    # Per-seller trailing-window average risk score -> the ranking basis for both
    # the "bottom 5%" headline stat and the coaching recommendation, so the whole
    # report is built on ONE consistently-defined cohort rather than two.
    seller_avg_risk = win_df.groupby("seller_id")["risk_score"].mean()
    n_sellers = seller_avg_risk.shape[0]
    n_bottom = max(1, round(n_sellers * BOTTOM_PCT))
    bottom_threshold = seller_avg_risk.sort_values(ascending=False).iloc[n_bottom - 1]
    bottom_sellers = set(seller_avg_risk.sort_values(ascending=False).head(n_bottom).index)

    total_cancellations = win_df["cancelled_orders"].sum()
    total_late = win_df["late_orders"].sum()
    bottom_window = win_df[win_df["seller_id"].isin(bottom_sellers)]
    bottom_cancellations = bottom_window["cancelled_orders"].sum()
    bottom_late = bottom_window["late_orders"].sum()
    pct_of_cancellations = (bottom_cancellations / total_cancellations * 100) if total_cancellations else 0
    pct_of_late = (bottom_late / total_late * 100) if total_late else 0

    n_coaching = max(1, round(n_sellers * COACHING_PCT))
    coaching_threshold = seller_avg_risk.sort_values(ascending=False).iloc[n_coaching - 1]
    coaching_sellers = set(seller_avg_risk.sort_values(ascending=False).head(n_coaching).index)
    coaching_window = win_df[win_df["seller_id"].isin(coaching_sellers)]

    # Pooled (sum of cancellations / sum of orders) rather than a per-seller median: with many
    # sellers placing only a handful of orders a month, the median of individual seller rates is
    # pulled toward 0% by sampling noise (a seller with 4 orders and no cancellation that month
    # isn't necessarily "perfect," there just wasn't enough volume to see one). The pooled rate is
    # the platform's actual blended cancellation rate and isn't distorted by that effect.
    marketplace_pooled_cancel_rate = win_df["cancelled_orders"].sum() / win_df["total_orders"].sum()
    projected_if_median = (coaching_window["total_orders"] * marketplace_pooled_cancel_rate).sum()
    prevented_cancellations = max(0, coaching_window["cancelled_orders"].sum() - projected_if_median)
    prevented_cost_window_brl = prevented_cancellations * COST_PER_CANCELLATION_BRL
    prevented_cost_annualized_brl = prevented_cost_window_brl * (12 / WINDOW_MONTHS)

    anomaly_count = int(win_df[win_df["seller_id"].isin(coaching_sellers) | win_df["seller_id"].isin(bottom_sellers)]["anomaly_flag"].sum())
    anomaly_count_all = int(win_df["anomaly_flag"].sum())

    report = f"""# SellerHealth Watchlist — Business Case Summary

*Auto-generated by `src/generate_business_case.py` from `seller_month_scored`,
using the trailing {WINDOW_MONTHS}-month window **{window_label}**.
Regenerate any time the data refreshes — every number below is computed,
not hand-typed. Currency: BRL (R$), the dataset's native currency.*

## Headline

Over the last {WINDOW_MONTHS} months, the **bottom {BOTTOM_PCT:.0%} of
sellers by average risk score** ({n_bottom} of {n_sellers} active
{plural(n_bottom)}, avg. risk score ≥ {bottom_threshold:.1f}) account for
**{pct_of_cancellations:.1f}% of all cancellations** and
**{pct_of_late:.1f}% of all late shipments** in that window — a
concentration of platform cost sitting on a small share of the seller
base.

## Recommendation

Enroll the **{n_coaching} {plural(n_coaching)}** in the bottom
{COACHING_PCT:.0%} by trailing {WINDOW_MONTHS}-month average risk score
(avg. risk score ≥ {coaching_threshold:.1f}) in a targeted coaching /
performance-improvement track (fulfillment SLA review + stock-accuracy
check), rather than a blanket policy across all sellers. This is a
deliberately wider net than the bottom {BOTTOM_PCT:.0%} above, to reach
adjacent at-risk sellers before they become next month's worst
performers. {anomaly_count_all} seller-months in this window were also
flagged for *sudden* deterioration (not just chronic underperformance) —
those are the highest-priority outreach candidates, since they represent
a recent break from an otherwise normal track record.

## Estimated Impact (illustrative scenario)

If those {n_coaching} {plural(n_coaching)}' cancellation rates improved to
the blended marketplace cancellation rate for this window ({marketplace_pooled_cancel_rate:.1%}),
this would prevent an estimated **{prevented_cancellations:.0f}
cancellations over {WINDOW_MONTHS} months** — worth approximately
**R$ {prevented_cost_window_brl:,.0f}** in avoided refund + CS handling
cost over that window, or roughly **R$ {prevented_cost_annualized_brl:,.0f}
annualized** if the pattern held steady, using a placeholder cost of
R$ {COST_PER_CANCELLATION_BRL:.0f} per cancellation
(`COST_PER_CANCELLATION_BRL` in `src/generate_business_case.py` — replace
with an actual internal figure for a real number; this is a scenario
calculation on synthetic demo data, not an audited estimate).

## Supporting Detail

| Metric | Value |
|---|---|
| Window | {window_label} ({WINDOW_MONTHS} months) |
| Active sellers in window | {n_sellers} |
| Bottom {BOTTOM_PCT:.0%} avg. risk score threshold | {bottom_threshold:.1f} |
| Sellers in bottom {BOTTOM_PCT:.0%} | {n_bottom} |
| Cancellations attributable to bottom {BOTTOM_PCT:.0%} | {bottom_cancellations:.0f} of {total_cancellations:.0f} ({pct_of_cancellations:.1f}%) |
| Late shipments attributable to bottom {BOTTOM_PCT:.0%} | {bottom_late:.0f} of {total_late:.0f} ({pct_of_late:.1f}%) |
| Sellers recommended for coaching (bottom {COACHING_PCT:.0%}, avg. risk score ≥ {coaching_threshold:.1f}) | {n_coaching} |
| Seller-months flagged for sudden deterioration in window | {anomaly_count_all} |

## Methodology, in one line

Risk score = weighted sum of late-shipment rate (35%), cancellation rate
(30%), inverted review score (25%), and order-volume decline (10%), each
scored relative to that month's peers. No machine learning — every
component is auditable. Full methodology: `powerbi_export/data_dictionary.md`
and `src/risk_score.py`.

---
*Generated {date.today().isoformat()}.*
"""

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write(report)
    print(f"Wrote {OUT_PATH}")
    print(f"  window: {window_label}")
    print(f"  bottom {BOTTOM_PCT:.0%}: {n_bottom} sellers, {pct_of_cancellations:.1f}% of cancellations, {pct_of_late:.1f}% of late shipments")
    print(f"  coaching pool (bottom {COACHING_PCT:.0%}, avg risk>={coaching_threshold:.1f}): {n_coaching} sellers, ~R${prevented_cost_window_brl:,.0f} illustrative prevented cost/window")


if __name__ == "__main__":
    main()
