"""
run_analysis_pipeline.py

Orchestrates the Python analysis layer end to end:
    seller_monthly_metrics (SQL output)
        -> risk_score.compute_risk_scores()
        -> anomaly_detection.compute_anomaly_flags()
        -> writes `seller_month_scored` table back into the SQLite DB
        -> writes data/processed/seller_month_scored.csv as a convenience copy

This is the single script to re-run any time the risk-score weights or
anomaly threshold change (edit the constants at the top of risk_score.py /
anomaly_detection.py, then re-run this file). Everything downstream --
the Streamlit app, the Power BI export builder, the business case
generator -- reads from `seller_month_scored`, never recomputes it itself.

Usage:
    python src/run_analysis_pipeline.py
"""

import os
import sqlite3

from anomaly_detection import compute_anomaly_flags
from risk_score import compute_risk_scores, load_seller_monthly_metrics

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "seller_health.db")
CSV_OUT = os.path.join(BASE_DIR, "data", "processed", "seller_month_scored.csv")


def main():
    conn = sqlite3.connect(DB_PATH)

    print("1/3  loading seller_monthly_metrics ...")
    metrics = load_seller_monthly_metrics(conn)
    print(f"     {len(metrics):,} seller-month rows")

    print("2/3  computing risk scores + anomaly flags ...")
    scored = compute_risk_scores(metrics)
    scored = compute_anomaly_flags(scored)

    print("3/3  writing seller_month_scored (SQLite + CSV) ...")
    scored.to_sql("seller_month_scored", conn, if_exists="replace", index=False)
    scored.to_csv(CSV_OUT, index=False)

    n_anomalies = int(scored["anomaly_flag"].sum())
    print(f"\nDone. {len(scored):,} rows scored, {n_anomalies} flagged as sudden deterioration.")
    print(f"  risk_score range: {scored['risk_score'].min():.1f} - {scored['risk_score'].max():.1f}")
    print(f"  SQLite table 'seller_month_scored' written to {DB_PATH}")
    print(f"  CSV copy written to {CSV_OUT}")

    conn.close()


if __name__ == "__main__":
    main()
