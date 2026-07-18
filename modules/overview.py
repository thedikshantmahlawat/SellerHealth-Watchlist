"""
modules/overview.py — Module 1: Marketplace Overview

Aggregate, marketplace-wide health trends across ALL sellers: KPIs for
the latest month, monthly trend lines, the overall risk score
distribution, and a regional (state) breakdown. This is the "how healthy
is the marketplace as a whole, and is it improving or declining" view --
Module 2 (Watchlist) is where individual at-risk sellers get named.
"""

import pandas as pd
import streamlit as st

RISK_WATCHLIST_THRESHOLD = 70


def render(fact: pd.DataFrame, dim_seller: pd.DataFrame):
    st.title("Marketplace Overview")
    st.caption("Aggregate seller-health trends across the whole marketplace")

    months = sorted(fact["month_key"].unique())
    latest_month = months[-1]
    latest = fact[fact["month_key"] == latest_month]
    prev = fact[fact["month_key"] == months[-2]] if len(months) > 1 else latest

    # ---- KPI row -----------------------------------------------------
    def _delta(cur, prev_val):
        return None if prev_val == 0 else cur - prev_val

    active_sellers = latest["seller_id"].nunique()
    avg_risk = latest["risk_score"].mean()
    pct_watchlist = (latest["risk_score"] >= RISK_WATCHLIST_THRESHOLD).mean() * 100
    total_revenue = latest["revenue"].sum()
    avg_late = latest["late_shipment_rate"].mean() * 100
    avg_cancel = latest["cancellation_rate"].mean() * 100

    prev_avg_risk = prev["risk_score"].mean()
    prev_late = prev["late_shipment_rate"].mean() * 100
    prev_cancel = prev["cancellation_rate"].mean() * 100

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Active sellers", f"{active_sellers:,}")
    c2.metric("Avg risk score", f"{avg_risk:.1f}", delta=f"{avg_risk - prev_avg_risk:+.1f}", delta_color="inverse")
    c3.metric("% on watchlist", f"{pct_watchlist:.1f}%")
    c4.metric("Revenue (R$)", f"{total_revenue:,.0f}")
    c5.metric("Avg late rate", f"{avg_late:.1f}%", delta=f"{avg_late - prev_late:+.1f}pp", delta_color="inverse")
    c6.metric("Avg cancel rate", f"{avg_cancel:.1f}%", delta=f"{avg_cancel - prev_cancel:+.1f}pp", delta_color="inverse")

    st.caption(f"Latest month: {latest_month}  ·  deltas vs. {months[-2] if len(months) > 1 else 'n/a'}")
    st.divider()

    # ---- Trend lines ---------------------------------------------------
    st.subheader("Marketplace trends over time")
    monthly = (
        fact.groupby("month_key")
        .agg(
            avg_risk_score=("risk_score", "mean"),
            avg_late_shipment_rate=("late_shipment_rate", "mean"),
            avg_cancellation_rate=("cancellation_rate", "mean"),
            avg_review_score=("avg_review_score", "mean"),
            total_revenue=("revenue", "sum"),
            active_sellers=("seller_id", "nunique"),
        )
        .reset_index()
        .sort_values("month_key")
    )

    tab1, tab2, tab3 = st.tabs(["Risk score", "Late shipments & cancellations", "Review score & revenue"])
    with tab1:
        st.line_chart(monthly, x="month_key", y="avg_risk_score", height=320)
        st.caption("Marketplace-wide average Seller Risk Score (0-100) by month.")
    with tab2:
        rates = monthly[["month_key", "avg_late_shipment_rate", "avg_cancellation_rate"]].copy()
        rates["avg_late_shipment_rate"] *= 100
        rates["avg_cancellation_rate"] *= 100
        st.line_chart(rates, x="month_key", y=["avg_late_shipment_rate", "avg_cancellation_rate"], height=320)
        st.caption("Average late-shipment rate and cancellation rate (%) by month.")
    with tab3:
        colA, colB = st.columns(2)
        with colA:
            st.line_chart(monthly, x="month_key", y="avg_review_score", height=280)
            st.caption("Average review score (1-5) by month.")
        with colB:
            st.bar_chart(monthly, x="month_key", y="total_revenue", height=280)
            st.caption("Total marketplace revenue (R$) by month.")

    st.divider()

    # ---- Distribution + regional breakdown ------------------------------
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Risk score distribution (latest month)")
        bins = pd.cut(latest["risk_score"], bins=[0, 20, 40, 60, 80, 100], include_lowest=True)
        dist = bins.value_counts().sort_index()
        dist.index = [str(i) for i in dist.index]
        st.bar_chart(dist, height=280)
        st.caption("Number of sellers by risk score band, this month.")

    with col_right:
        st.subheader("Average risk score by state (latest month)")
        by_state = (
            latest.groupby("seller_state")["risk_score"]
            .mean()
            .sort_values(ascending=False)
            .head(10)
        )
        st.bar_chart(by_state, height=280)
        st.caption("Top 10 states by average seller risk score, this month.")
