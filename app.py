"""
app.py — SellerHealth Watchlist

Entry point for the Streamlit dashboard. Run locally with:
    streamlit run app.py

Loads data ONCE (cached) from the pre-built SQLite database, then hands
off to one of three modules based on sidebar navigation:
    modules/overview.py   -- Module 1: Marketplace overview
    modules/watchlist.py  -- Module 2: Seller Watchlist (ranked + sparklines)
    modules/drilldown.py  -- Module 3: Individual seller drill-down

This file deliberately contains no business logic of its own -- the risk
score, anomaly flags, and every metric are computed upstream by
src/run_analysis_pipeline.py and simply read here. If data/processed/seller_health.db
is missing (e.g. a fresh clone before the pipeline has been run), this
file regenerates it automatically so the deployed app never shows a
blank/broken page.
"""

import os
import subprocess
import sys

import pandas as pd
import sqlite3
import streamlit as st

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "seller_health.db")
SRC_DIR = os.path.join(BASE_DIR, "src")

st.set_page_config(
    page_title="SellerHealth Watchlist",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _ensure_pipeline_has_run():
    """Self-healing bootstrap: if the scored table doesn't exist yet
    (e.g. a fresh clone, or Streamlit Cloud's ephemeral filesystem lost
    it), regenerate it from the raw CSVs. Committed data/raw/*.csv and
    data/processed/seller_health.db mean this normally never fires."""
    needs_build = not os.path.exists(DB_PATH)
    if not needs_build:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("SELECT 1 FROM seller_month_scored LIMIT 1")
            conn.close()
        except sqlite3.OperationalError:
            needs_build = True
    if needs_build:
        with st.spinner("First run: building the database from raw data..."):
            subprocess.run([sys.executable, os.path.join(SRC_DIR, "load_to_sql.py")], check=True, cwd=SRC_DIR)
            subprocess.run([sys.executable, os.path.join(SRC_DIR, "run_analysis_pipeline.py")], check=True, cwd=SRC_DIR)


def load_custom_css():
    st.markdown(
        """
        <style>
        .block-container {padding-top: 2rem;}
        [data-testid="stMetricValue"] {font-size: 1.6rem;}
        .risk-badge {
            display: inline-block; padding: 2px 10px; border-radius: 10px;
            font-size: 0.8rem; font-weight: 600;
        }
        .risk-high {background-color: #FEE2E2; color: #B91C1C;}
        .risk-watch {background-color: #FEF3C7; color: #B45309;}
        .risk-healthy {background-color: #DCFCE7; color: #15803D;}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)
    fact = pd.read_sql("SELECT * FROM seller_month_scored", conn)
    dim_seller = pd.read_sql("SELECT * FROM seller_level_summary", conn)
    conn.close()
    fact["month_date"] = pd.to_datetime(fact["month_key"] + "-01")
    fact = fact.merge(dim_seller[["seller_id", "seller_state", "seller_city"]], on="seller_id", how="left")
    return fact, dim_seller


_ensure_pipeline_has_run()
load_custom_css()
fact, dim_seller = load_data()

with st.sidebar:
    st.markdown("## 📊 SellerHealth Watchlist")
    st.caption("Seller performance monitoring & risk scoring")
    page = st.radio(
        "Go to",
        ["Marketplace Overview", "Seller Watchlist", "Seller Drill-Down"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(
        f"Data: {fact['month_key'].min()} to {fact['month_key'].max()}  \n"
        f"{fact['seller_id'].nunique():,} sellers  ·  {int(fact['total_orders'].sum()):,} orders"
    )
    st.caption("Built on synthetic data matching the Olist schema — see README.")

if page == "Marketplace Overview":
    from modules import overview
    overview.render(fact, dim_seller)
elif page == "Seller Watchlist":
    from modules import watchlist
    watchlist.render(fact, dim_seller)
else:
    from modules import drilldown
    drilldown.render(fact, dim_seller)
