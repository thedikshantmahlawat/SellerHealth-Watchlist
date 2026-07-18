"""
risk_score.py

Computes a transparent, weighted "Seller Risk Score" (0-100) for every
(seller_id, month) row. This is deliberately NOT a machine-learning model:
no training, no black-box coefficients, nothing that can't be explained in
one sentence per component. That is a design choice, not a limitation --
an ops team can't act on a score they can't audit, and a coaching program
built on an unexplainable score won't survive its first "why did we flag
this seller?" conversation.

METHODOLOGY (this is the part to walk through in an interview)
-----------------------------------------------------------------
1. Four components, each normalized to 0-1 WITHIN ITS OWN MONTH (i.e.
   relative to that month's peer group of sellers, not to some fixed
   historical anchor). Doing it per-month rather than globally means a
   systemic event that hits the whole marketplace at once (e.g. a
   carrier-wide delay) does not automatically make every seller look
   "high risk" -- risk here means "worse than peers right now," which is
   what a coaching team can actually act on.

2. Composite score = weighted sum of the four normalized components,
   scaled to 0-100. Weights are fixed constants (see WEIGHTS below), not
   fitted to data, and are chosen from business reasoning:

     late_shipment_rate    35%  -- the single largest driver of CS tickets
                                   and refund requests; fully within a
                                   seller's operational control (packing
                                   and carrier handoff speed).
     cancellation_rate     30%  -- direct lost revenue + refund/CS cost;
                                   usually a stock-accuracy problem, which
                                   is also seller-side and coachable.
     review_score          25%  -- inverted (low review = high risk).
                                   Weighted third, not first, because it's
                                   a LAGGING, blended signal -- it reflects
                                   product quality and buyer expectations
                                   too, not fulfillment ops alone, so it's
                                   less directly actionable on its own.
     volume_trend          10%  -- a seller whose order volume is dropping
                                   relative to their own recent history can
                                   be an early-warning sign (buyers already
                                   voting with their feet) before it shows
                                   up in the other three metrics. Lowest
                                   weight because volume swings also have
                                   many benign causes (seasonality,
                                   deliberate seller destocking).

   These weights sum to 100% and are the first thing to defend in an
   interview: "why 35/30/25/10 and not equal weights?" The one-line answer
   for each is above -- the ranking follows how directly and immediately
   each metric is both COSTLY to the platform and ACTIONABLE by the
   seller, in that order.

3. Nothing here is fit to the data (no regression, no learned weights),
   so the score cannot overfit and requires no retraining -- it will
   behave identically on day one and on day one thousand. That
   predictability is itself the pitch for "lightweight, explainable
   analytics" over a black-box model in a coaching/policy context.
"""

import os
import sqlite3

import numpy as np
import pandas as pd

WEIGHTS = {
    "late_shipment_rate": 0.35,
    "cancellation_rate": 0.30,
    "review_score_inverted": 0.25,
    "volume_decline": 0.10,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "WEIGHTS must sum to 1.0"

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "seller_health.db")


def _minmax_within_month(df: pd.DataFrame, col: str) -> pd.Series:
    """Min-max normalize `col` to [0, 1] within each month_key group.
    A seller with the worst value THAT MONTH scores 1.0 on this component;
    the best scores 0.0. NaN/degenerate months (all sellers tied) resolve
    to 0.0 so a single missing value can't blow up the composite score."""
    def _scale(s):
        lo, hi = s.min(), s.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            return pd.Series(0.0, index=s.index)
        return (s - lo) / (hi - lo)
    return df.groupby("month_key")[col].transform(_scale)


def compute_volume_decline(df: pd.DataFrame) -> pd.Series:
    """Volume-trend component: how far BELOW a seller's own trailing
    3-month average order volume the current month is, as a fraction.
    Positive = volume dropped vs. this seller's own recent history
    (bad); clipped at 0 so volume GROWTH never reduces the other
    components (this component only ever adds risk, never subtracts it)."""
    df = df.sort_values(["seller_id", "month_key"])
    trailing_avg = (
        df.groupby("seller_id")["total_orders"]
        .transform(lambda s: s.shift(1).rolling(window=3, min_periods=1).mean())
    )
    decline = (trailing_avg - df["total_orders"]) / trailing_avg.replace(0, np.nan)
    return decline.clip(lower=0).fillna(0)


def compute_risk_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Takes the seller_monthly_metrics dataframe and returns it enriched
    with normalized components, per-component weighted contributions, and
    the final 0-100 composite risk_score."""
    df = df.copy()

    df["_late_norm"] = _minmax_within_month(df, "late_shipment_rate")
    df["_cancel_norm"] = _minmax_within_month(df, "cancellation_rate")

    # Invert review score first (5 - score), THEN normalize, so higher
    # normalized value always means "higher risk" consistently across
    # all four components.
    df["_review_inv"] = 5.0 - df["avg_review_score"].fillna(df["avg_review_score"].median())
    df["_review_norm"] = _minmax_within_month(df, "_review_inv")

    df["_volume_decline_raw"] = compute_volume_decline(df)
    df["_volume_norm"] = _minmax_within_month(df, "_volume_decline_raw")

    df["risk_late_component"] = (df["_late_norm"] * WEIGHTS["late_shipment_rate"] * 100).round(2)
    df["risk_cancel_component"] = (df["_cancel_norm"] * WEIGHTS["cancellation_rate"] * 100).round(2)
    df["risk_review_component"] = (df["_review_norm"] * WEIGHTS["review_score_inverted"] * 100).round(2)
    df["risk_volume_component"] = (df["_volume_norm"] * WEIGHTS["volume_decline"] * 100).round(2)

    df["risk_score"] = (
        df["risk_late_component"] + df["risk_cancel_component"]
        + df["risk_review_component"] + df["risk_volume_component"]
    ).clip(0, 100).round(2)

    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    return df


def load_seller_monthly_metrics(conn=None) -> pd.DataFrame:
    own_conn = conn is None
    conn = conn or sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM seller_monthly_metrics", conn)
    if own_conn:
        conn.close()
    return df


if __name__ == "__main__":
    metrics = load_seller_monthly_metrics()
    scored = compute_risk_scores(metrics)
    print(scored[["seller_id", "month_key", "risk_score",
                   "risk_late_component", "risk_cancel_component",
                   "risk_review_component", "risk_volume_component"]].sort_values(
        "risk_score", ascending=False).head(10).to_string(index=False))
