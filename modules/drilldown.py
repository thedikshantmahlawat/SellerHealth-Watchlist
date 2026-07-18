"""
modules/drilldown.py — Module 3: Individual Seller Drill-Down

Everything about ONE seller: their full metric history, month-by-month
risk score breakdown by component (so it's visible WHY a seller scored
what they scored, not just the final number), and their anomaly-flag
timeline. This is the view a coach/analyst would open right before an
actual conversation with that seller.
"""

import pandas as pd
import streamlit as st


def render(fact: pd.DataFrame, dim_seller: pd.DataFrame):
    st.title("Seller Drill-Down")

    seller_lookup = dim_seller.set_index("seller_id")
    all_ids = sorted(fact["seller_id"].unique())
    label_map = {
        sid: f"{sid[:10]}…  ({seller_lookup.loc[sid, 'seller_state']})"
        if sid in seller_lookup.index else sid
        for sid in all_ids
    }

    default_idx = 0
    latest_month = fact["month_key"].max()
    top_risk_this_month = fact[fact["month_key"] == latest_month].sort_values("risk_score", ascending=False)
    if len(top_risk_this_month):
        default_idx = all_ids.index(top_risk_this_month.iloc[0]["seller_id"])

    selected_id = st.selectbox(
        "Select a seller", all_ids, index=default_idx, format_func=lambda sid: label_map.get(sid, sid)
    )

    seller_hist = fact[fact["seller_id"] == selected_id].sort_values("month_key")
    seller_info = seller_lookup.loc[selected_id] if selected_id in seller_lookup.index else None
    latest_row = seller_hist.iloc[-1]

    st.caption(
        f"Seller `{selected_id}`"
        + (f"  ·  {seller_info['seller_city'].title()}, {seller_info['seller_state']}" if seller_info is not None else "")
        + f"  ·  active {seller_hist['month_key'].min()} to {seller_hist['month_key'].max()}"
    )

    # ---- Current snapshot -------------------------------------------
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Current risk score", f"{latest_row['risk_score']:.1f}")
    c2.metric("Late shipment rate", f"{latest_row['late_shipment_rate'] * 100:.1f}%")
    c3.metric("Cancellation rate", f"{latest_row['cancellation_rate'] * 100:.1f}%")
    c4.metric("Avg review score", f"{latest_row['avg_review_score']:.2f}" if pd.notna(latest_row["avg_review_score"]) else "n/a")
    c5.metric("Orders this month", f"{int(latest_row['total_orders'])}")

    if latest_row["anomaly_flag"] == 1:
        st.warning(
            f"⚠️ Sudden deterioration flagged for {latest_row['month_key']}: this seller's risk score "
            f"jumped well above their own recent pattern (z-score {latest_row['risk_score_zscore']:.2f}).",
            icon="⚠️",
        )

    st.divider()

    # ---- Trends over time -----------------------------------------------
    st.subheader("Metric history")
    t1, t2 = st.tabs(["Risk score & anomaly flags", "Underlying metrics"])
    with t1:
        st.line_chart(seller_hist, x="month_key", y="risk_score", height=300)
        flagged_months = seller_hist[seller_hist["anomaly_flag"] == 1]["month_key"].tolist()
        if flagged_months:
            st.caption(f"⚠️ Flagged for sudden deterioration in: {', '.join(flagged_months)}")
        else:
            st.caption("No sudden-deterioration months flagged for this seller.")
    with t2:
        rates = seller_hist[["month_key", "late_shipment_rate", "cancellation_rate"]].copy()
        rates["late_shipment_rate"] *= 100
        rates["cancellation_rate"] *= 100
        colA, colB = st.columns(2)
        with colA:
            st.line_chart(rates, x="month_key", y=["late_shipment_rate", "cancellation_rate"], height=280)
            st.caption("Late shipment rate & cancellation rate (%) by month.")
        with colB:
            st.line_chart(seller_hist, x="month_key", y="avg_review_score", height=280)
            st.caption("Average review score (1-5) by month.")

    st.divider()

    # ---- Risk score breakdown --------------------------------------------
    st.subheader("Risk score breakdown (most recent month)")
    components = pd.DataFrame({
        "component": ["Late shipments (35%)", "Cancellations (30%)", "Review score (25%)", "Volume decline (10%)"],
        "points": [
            latest_row["risk_late_component"], latest_row["risk_cancel_component"],
            latest_row["risk_review_component"], latest_row["risk_volume_component"],
        ],
    }).set_index("component")
    st.bar_chart(components, height=280)
    st.caption(
        f"Total risk score = sum of the four components above = {latest_row['risk_score']:.1f} / 100. "
        "Each component is scored relative to this month's other sellers — see README for the full methodology."
    )
