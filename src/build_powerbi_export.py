"""
build_powerbi_export.py

Builds the /powerbi_export folder: a star-schema-shaped set of CSVs meant
to be loaded into Power BI Desktop (Get Data -> Text/CSV, or Get Data ->
Folder for all four at once). See powerbi_export/data_dictionary.md for
the full column-by-column reference and README.md's "Power BI Setup Guide"
for load steps, relationships, and ready-to-paste DAX measures.

Outputs:
    fact_seller_month.csv   grain: seller_id x month -- every metric,
                            every risk-score component, and the anomaly
                            flag, one row per seller per month.
    dim_seller.csv          one row per seller_id -- static/lifetime
                            attributes (state, city, lifetime totals).
    dim_region.csv          one row per Brazilian state -- maps state
                            code to a macro-region name for roll-up
                            reporting (relates to dim_seller, not
                            directly to the fact table -- see the Power
                            BI Setup Guide for why).
    dim_month.csv           one row per calendar month in the fact table's
                            range, with a proper Date column so Power BI
                            time-intelligence (DATEADD etc.) works.

Usage:
    python src/build_powerbi_export.py
"""

import os
import sqlite3

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "seller_health.db")
OUT_DIR = os.path.join(BASE_DIR, "powerbi_export")

RISK_WATCHLIST_THRESHOLD = 70  # matches the threshold used in README DAX examples & the Streamlit watchlist module

# Brazilian state -> macro-region (public, static geography -- IBGE's five
# official macro-regions). Any state not listed defaults to "Other".
STATE_TO_REGION = {
    "SP": "Southeast", "RJ": "Southeast", "MG": "Southeast", "ES": "Southeast",
    "PR": "South", "SC": "South", "RS": "South",
    "BA": "Northeast", "PE": "Northeast", "CE": "Northeast", "MA": "Northeast",
    "PB": "Northeast", "RN": "Northeast", "AL": "Northeast", "SE": "Northeast", "PI": "Northeast",
    "AM": "North", "PA": "North", "AC": "North", "RO": "North", "RR": "North", "AP": "North", "TO": "North",
    "MT": "Central-West", "MS": "Central-West", "GO": "Central-West", "DF": "Central-West",
}


def build_fact_seller_month(conn) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM seller_month_scored", conn)
    df["month_date"] = pd.to_datetime(df["month_key"] + "-01")
    df["is_watchlist"] = (df["risk_score"] >= RISK_WATCHLIST_THRESHOLD).astype(int)
    cols = [
        "seller_id", "month_key", "month_date",
        "total_orders", "delivered_orders", "late_orders", "late_shipment_rate",
        "cancelled_orders", "cancellation_rate",
        "avg_review_score", "review_count",
        "revenue", "revenue_share_of_marketplace",
        "risk_late_component", "risk_cancel_component", "risk_review_component", "risk_volume_component",
        "risk_score", "risk_score_zscore", "anomaly_flag", "is_watchlist",
    ]
    return df[cols].sort_values(["seller_id", "month_key"])


def build_dim_seller(conn, fact: pd.DataFrame) -> pd.DataFrame:
    summary = pd.read_sql("SELECT * FROM seller_level_summary", conn)
    latest_month = fact["month_key"].max()
    latest_flag = (
        fact[fact["month_key"] == latest_month][["seller_id", "risk_score", "is_watchlist"]]
        .rename(columns={"risk_score": "latest_month_risk_score", "is_watchlist": "current_watchlist_flag"})
    )
    dim = summary.merge(latest_flag, on="seller_id", how="left")
    dim["current_watchlist_flag"] = dim["current_watchlist_flag"].fillna(0).astype(int)
    dim["region_state"] = dim["seller_state"]
    return dim


def build_dim_region(dim_seller: pd.DataFrame) -> pd.DataFrame:
    states = sorted(dim_seller["seller_state"].unique())
    rows = [{"region_state": s, "region_name": STATE_TO_REGION.get(s, "Other")} for s in states]
    return pd.DataFrame(rows)


def build_dim_month(fact: pd.DataFrame) -> pd.DataFrame:
    all_months = pd.date_range(fact["month_date"].min(), fact["month_date"].max(), freq="MS")
    dim = pd.DataFrame({"month_date": all_months})
    dim["month_key"] = dim["month_date"].dt.strftime("%Y-%m")
    dim["month_name"] = dim["month_date"].dt.strftime("%b %Y")
    dim["quarter"] = "Q" + dim["month_date"].dt.quarter.astype(str) + " " + dim["month_date"].dt.year.astype(str)
    dim["year"] = dim["month_date"].dt.year
    return dim


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    fact = build_fact_seller_month(conn)
    dim_seller = build_dim_seller(conn, fact)
    dim_region = build_dim_region(dim_seller)
    dim_month = build_dim_month(fact)

    fact.to_csv(os.path.join(OUT_DIR, "fact_seller_month.csv"), index=False)
    dim_seller.to_csv(os.path.join(OUT_DIR, "dim_seller.csv"), index=False)
    dim_region.to_csv(os.path.join(OUT_DIR, "dim_region.csv"), index=False)
    dim_month.to_csv(os.path.join(OUT_DIR, "dim_month.csv"), index=False)

    print(f"fact_seller_month.csv  {len(fact):,} rows")
    print(f"dim_seller.csv         {len(dim_seller):,} rows")
    print(f"dim_region.csv         {len(dim_region):,} rows")
    print(f"dim_month.csv          {len(dim_month):,} rows")
    conn.close()


if __name__ == "__main__":
    main()
