"""
modules/watchlist.py — Module 2: Seller Watchlist

The "who needs attention right now" view: sellers ranked by risk score,
with a trend sparkline so a reviewer can see at a glance whether a
seller's risk is climbing, falling, or has been consistently bad. This is
also where the anomaly flag (sudden deterioration, from
src/anomaly_detection.py) surfaces -- it's called out separately from
"just has a high score," since those need different follow-up.
"""

import pandas as pd
import streamlit as st

SPARKLINE_MONTHS = 6


def render(fact: pd.DataFrame, dim_seller: pd.DataFrame):
    st.title("Seller Watchlist")
    st.caption("Sellers ranked by risk score, with recent trend and anomaly flags")

    months = sorted(fact["month_key"].unique())
    latest_month = months[-1]

    # ---- Filters --------------------------------------------------------
    f1, f2, f3, f4 = st.columns([1.2, 1.4, 1, 1])
    with f1:
        selected_month = st.selectbox("Month", months, index=len(months) - 1)
    with f2:
        states = sorted(fact["seller_state"].dropna().unique())
        selected_states = st.multiselect("State", states, default=[])
    with f3:
        min_risk = st.slider("Min risk score", 0, 100, 0, step=5)
    with f4:
        only_anomalies = st.checkbox("Anomalies only", value=False)

    month_df = fact[fact["month_key"] == selected_month].copy()
    if selected_states:
        month_df = month_df[month_df["seller_state"].isin(selected_states)]
    month_df = month_df[month_df["risk_score"] >= min_risk]
    if only_anomalies:
        month_df = month_df[month_df["anomaly_flag"] == 1]
    month_df = month_df.sort_values("risk_score", ascending=False)

    st.caption(f"{len(month_df)} sellers match these filters, out of {fact[fact['month_key'] == selected_month]['seller_id'].nunique()} active in {selected_month}.")

    # ---- Build sparkline trend per seller (trailing N months up to selected_month) ----
    history = fact[fact["month_key"] <= selected_month].sort_values("month_key")
    trend_by_seller = (
        history.groupby("seller_id")["risk_score"]
        .apply(lambda s: list(s.tail(SPARKLINE_MONTHS)))
        .to_dict()
    )
    month_df["risk_trend"] = month_df["seller_id"].map(trend_by_seller)

    display_df = month_df[[
        "seller_id", "seller_state", "risk_score", "risk_trend",
        "late_shipment_rate", "cancellation_rate", "avg_review_score",
        "revenue", "anomaly_flag", "total_orders",
    ]].copy()
    display_df["seller_id"] = display_df["seller_id"].str[:10] + "…"
    display_df["late_shipment_rate"] *= 100
    display_df["cancellation_rate"] *= 100
    display_df["anomaly_flag"] = display_df["anomaly_flag"].map({1: "⚠️ sudden drop", 0: ""})

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "seller_id": st.column_config.TextColumn("Seller ID"),
            "seller_state": st.column_config.TextColumn("State"),
            "risk_score": st.column_config.ProgressColumn(
                "Risk score", min_value=0, max_value=100, format="%.1f"
            ),
            "risk_trend": st.column_config.LineChartColumn(
                f"Last {SPARKLINE_MONTHS} months", y_min=0, y_max=100
            ),
            "late_shipment_rate": st.column_config.NumberColumn("Late %", format="%.1f%%"),
            "cancellation_rate": st.column_config.NumberColumn("Cancel %", format="%.1f%%"),
            "avg_review_score": st.column_config.NumberColumn("Avg review", format="%.2f ⭐"),
            "revenue": st.column_config.NumberColumn("Revenue (R$)", format="%.0f"),
            "anomaly_flag": st.column_config.TextColumn("Anomaly"),
            "total_orders": st.column_config.NumberColumn("Orders"),
        },
    )

    st.download_button(
        "Download this view as CSV",
        month_df.drop(columns=["risk_trend"]).to_csv(index=False).encode("utf-8"),
        file_name=f"seller_watchlist_{selected_month}.csv",
        mime="text/csv",
    )

    st.caption(
        "Risk score = weighted blend of late-shipment rate, cancellation rate, review score, "
        "and order-volume trend (see README for the full formula). ⚠️ marks a seller whose "
        "risk score just jumped well above their own recent pattern, not just a high score."
    )
