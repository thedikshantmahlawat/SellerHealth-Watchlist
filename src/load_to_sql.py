"""
load_to_sql.py

Builds data/processed/seller_health.db from the raw CSVs in data/raw/, then
runs the SQL aggregation layer (sql/seller_monthly_metrics.sql and
sql/seller_level_summary.sql) against it.

Usage:
    python src/load_to_sql.py

This is the ONLY script that touches the raw CSVs directly -- every other
script (risk_score.py, the Streamlit app, the Power BI export builder) reads
from the SQLite database this script produces, never from the CSVs.
Re-run this any time data/raw/ changes (including after swapping in the
real Kaggle dataset).
"""

import os
import sqlite3

import pandas as pd

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "seller_health.db")
SQL_DIR = os.path.join(BASE_DIR, "sql")

CSV_TO_TABLE = {
    "olist_sellers_dataset.csv": "sellers",
    "olist_customers_dataset.csv": "customers",
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_order_payments_dataset.csv": "order_payments",
}


def run_sql_file(conn, path):
    with open(path, "r") as f:
        conn.executescript(f.read())


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)

    print("1/4  creating raw schema ...")
    run_sql_file(conn, os.path.join(SQL_DIR, "schema.sql"))

    print("2/4  loading raw CSVs ...")
    for csv_name, table in CSV_TO_TABLE.items():
        df = pd.read_csv(os.path.join(RAW_DIR, csv_name))
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"     {table:15s} <- {csv_name:35s} ({len(df):,} rows)")

    print("3/4  building seller_monthly_metrics ...")
    run_sql_file(conn, os.path.join(SQL_DIR, "seller_monthly_metrics.sql"))

    print("4/4  building seller_level_summary ...")
    run_sql_file(conn, os.path.join(SQL_DIR, "seller_level_summary.sql"))

    conn.commit()

    for table in ["sellers", "orders", "order_items", "seller_monthly_metrics", "seller_level_summary"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:25s} {n:,} rows")

    conn.close()
    print(f"\nDatabase ready at {DB_PATH}")


if __name__ == "__main__":
    main()
