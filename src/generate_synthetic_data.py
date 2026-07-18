"""
generate_synthetic_data.py

Generates a dataset that mirrors the EXACT schema of the real Olist Brazilian
E-Commerce public dataset (Kaggle: "olist_orders_dataset.csv",
"olist_order_items_dataset.csv", "olist_order_reviews_dataset.csv",
"olist_order_payments_dataset.csv", "olist_customers_dataset.csv",
"olist_sellers_dataset.csv") — same filenames, same columns, same dtypes,
same order_status values.

WHY SYNTHETIC DATA
-------------------
This project was built in a sandboxed environment with no internet access,
so the real Kaggle CSVs could not be downloaded here. Because every column
name and value convention below matches the real dataset, you can swap this
out at any time:

    1. Download the real dataset from Kaggle ("olist_public_dataset" /
       "Brazilian E-Commerce Public Dataset by Olist").
    2. Drop the CSVs into data/raw/, overwriting these files (same names).
    3. Re-run sql/build_database.py — nothing else needs to change.

No script downstream of data/raw/ hardcodes a year, a seller count, or a
row count; every aggregation is computed from whatever is actually in the
tables, which is what makes this swap possible.

WHY ARCHETYPES, NOT PURE RANDOMNESS
-------------------------------------
A uniformly random dataset would make the risk score and the anomaly
detector meaningless to demo (everything would look equally "fine"). So
each synthetic seller is assigned one of four behavior patterns:

    - healthy         (70%): normal performers, small month-to-month noise
    - chronic_risk    (15%): consistently poor performers (high late/cancel,
                              low reviews) from the day they join
    - deteriorating   (10%): perform normally, then have a genuine mid-window
                              breakdown (e.g. a logistics failure) — this is
                              the pattern the rolling z-score is built to catch
    - volatile_small   (5%): low order volume -> noisy rates, a realistic
                              edge case for any seller-level scoring system

The ground-truth archetype/pivot-month labels are saved separately to
data/synthetic_ground_truth.csv (NOT part of the real Olist schema) purely
so the methodology can be validated end to end: "seller X was injected as
deteriorating at month 9 -> does the pipeline actually flag month 9-10?"
That file has no equivalent when using the real dataset and is not read by
any other script — it's a validation aid, not a project input.

Seeded (SEED=42) -> fully reproducible from run to run.
"""

import os
import random
import uuid
from datetime import timedelta

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
GROUND_TRUTH_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "synthetic_ground_truth.csv")
os.makedirs(OUT_DIR, exist_ok=True)

N_SELLERS = 220
START_MONTH = pd.Timestamp("2017-01-01")
N_MONTHS = 18  # 2017-01 through 2018-06 -- mirrors the real Olist dataset's ~2016-2018 window
MONTHS = pd.date_range(START_MONTH, periods=N_MONTHS, freq="MS")

# Brazilian seller-state mix weighted roughly like the real marketplace (heavily SP-centric)
STATE_WEIGHTS = {
    "SP": 0.42, "RJ": 0.13, "MG": 0.12, "RS": 0.06, "PR": 0.06,
    "SC": 0.04, "BA": 0.04, "DF": 0.03, "GO": 0.02, "ES": 0.02,
    "PE": 0.02, "CE": 0.015, "PA": 0.01, "MT": 0.01, "AM": 0.005,
}
STATES = list(STATE_WEIGHTS.keys())
STATE_P = np.array(list(STATE_WEIGHTS.values()))
STATE_P = STATE_P / STATE_P.sum()

STATE_CITY = {
    "SP": ["sao paulo", "campinas", "santos"], "RJ": ["rio de janeiro", "niteroi"],
    "MG": ["belo horizonte", "uberlandia"], "RS": ["porto alegre", "caxias do sul"],
    "PR": ["curitiba", "londrina"], "SC": ["florianopolis", "joinville"],
    "BA": ["salvador", "feira de santana"], "DF": ["brasilia"], "GO": ["goiania"],
    "ES": ["vitoria"], "PE": ["recife"], "CE": ["fortaleza"], "PA": ["belem"],
    "MT": ["cuiaba"], "AM": ["manaus"],
}

ARCHETYPE_MIX = (
    ["healthy"] * int(N_SELLERS * 0.70)
    + ["chronic_risk"] * int(N_SELLERS * 0.15)
    + ["deteriorating"] * int(N_SELLERS * 0.10)
    + ["volatile_small"] * int(N_SELLERS * 0.05)
)
while len(ARCHETYPE_MIX) < N_SELLERS:
    ARCHETYPE_MIX.append("healthy")
random.shuffle(ARCHETYPE_MIX)

# (late_rate range, cancel_rate range, mean review score, orders/month lambda range)
ARCH_PARAMS = {
    "healthy":             dict(late_p=(0.05, 0.12), cancel_p=(0.01, 0.03), review_mu=4.5, lam=(4, 9)),
    "chronic_risk":        dict(late_p=(0.20, 0.35), cancel_p=(0.06, 0.14), review_mu=3.1, lam=(3, 7)),
    "deteriorating_pre":   dict(late_p=(0.05, 0.12), cancel_p=(0.01, 0.03), review_mu=4.5, lam=(4, 9)),
    "deteriorating_post":  dict(late_p=(0.22, 0.38), cancel_p=(0.07, 0.15), review_mu=2.9, lam=(3, 7)),
    "volatile_small":      dict(late_p=(0.05, 0.30), cancel_p=(0.00, 0.10), review_mu=3.8, lam=(0.5, 2.5)),
}


def new_id():
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# 1. Sellers (+ ground-truth archetype assignment)
# ---------------------------------------------------------------------------
seller_rows, ground_truth_rows = [], []
for i in range(N_SELLERS):
    state = np.random.choice(STATES, p=STATE_P)
    city = random.choice(STATE_CITY[state])
    archetype = ARCHETYPE_MIX[i]
    join_idx = 0 if random.random() < 0.75 else random.randint(1, N_MONTHS - 6)

    pivot_idx = None
    if archetype == "deteriorating":
        lo, hi = max(join_idx + 4, 3), N_MONTHS - 3
        pivot_idx = random.randint(lo, hi) if hi > lo else N_MONTHS - 3

    seller_id = new_id()
    seller_rows.append({
        "seller_id": seller_id,
        "seller_zip_code_prefix": random.randint(1000, 99999),
        "seller_city": city,
        "seller_state": state,
    })
    ground_truth_rows.append({
        "seller_id": seller_id, "archetype": archetype, "join_month": MONTHS[join_idx].strftime("%Y-%m"),
        "pivot_month": MONTHS[pivot_idx].strftime("%Y-%m") if pivot_idx is not None else "",
    })
    seller_rows[-1]["_archetype"] = archetype
    seller_rows[-1]["_join_idx"] = join_idx
    seller_rows[-1]["_pivot_idx"] = pivot_idx

sellers_df = pd.DataFrame(seller_rows)
pd.DataFrame(ground_truth_rows).to_csv(GROUND_TRUTH_PATH, index=False)

# ---------------------------------------------------------------------------
# 2. Orders, items, reviews, payments, customers
# ---------------------------------------------------------------------------
orders, items, reviews, payments, customers = [], [], [], [], []

for _, s in sellers_df.iterrows():
    archetype = s["_archetype"]
    for m_idx, month in enumerate(MONTHS):
        if m_idx < s["_join_idx"]:
            continue
        if archetype == "deteriorating":
            key = "deteriorating_pre" if (s["_pivot_idx"] is None or m_idx < s["_pivot_idx"]) else "deteriorating_post"
        else:
            key = archetype
        p = ARCH_PARAMS[key]

        growth = 0.75 + 0.5 * (m_idx / max(N_MONTHS - 1, 1))  # mild platform-wide growth over time
        lam = np.random.uniform(*p["lam"]) * growth
        n_orders = np.random.poisson(max(lam, 0.1))
        late_p = np.random.uniform(*p["late_p"])
        cancel_p = np.random.uniform(*p["cancel_p"])

        for _ in range(n_orders):
            order_id, customer_id = new_id(), new_id()
            purchase_ts = month + timedelta(days=random.randint(1, 27), hours=random.randint(0, 23))
            est_delivery = purchase_ts + timedelta(days=random.randint(10, 25))
            is_cancelled = random.random() < cancel_p

            if is_cancelled:
                status, approved_at, carrier_date, customer_date = "canceled", purchase_ts + timedelta(hours=random.randint(1, 48)), None, None
            else:
                status = "delivered"
                approved_at = purchase_ts + timedelta(hours=random.randint(1, 36))
                carrier_date = approved_at + timedelta(days=random.randint(1, 4))
                if random.random() < late_p:
                    customer_date = est_delivery + timedelta(days=random.randint(1, 15))
                else:
                    customer_date = est_delivery - timedelta(days=random.randint(0, 6))
                    if customer_date < carrier_date:
                        customer_date = carrier_date + timedelta(days=1)

            orders.append({
                "order_id": order_id, "customer_id": customer_id, "order_status": status,
                "order_purchase_timestamp": purchase_ts, "order_approved_at": approved_at,
                "order_delivered_carrier_date": carrier_date, "order_delivered_customer_date": customer_date,
                "order_estimated_delivery_date": est_delivery,
            })
            cust_state = random.choice(STATES)
            customers.append({
                "customer_id": customer_id, "customer_unique_id": new_id(),
                "customer_zip_code_prefix": random.randint(1000, 99999),
                "customer_city": random.choice(STATE_CITY[cust_state]), "customer_state": cust_state,
            })
            price = round(np.random.uniform(25, 420), 2)
            freight = round(price * np.random.uniform(0.05, 0.16), 2)
            items.append({
                "order_id": order_id, "order_item_id": 1, "product_id": new_id(), "seller_id": s["seller_id"],
                "shipping_limit_date": purchase_ts + timedelta(days=3), "price": price, "freight_value": freight,
            })
            payments.append({
                "order_id": order_id, "payment_sequential": 1,
                "payment_type": np.random.choice(["credit_card", "boleto", "voucher", "debit_card"], p=[0.74, 0.19, 0.04, 0.03]),
                "payment_installments": int(np.random.choice([1, 2, 3, 4, 6, 10], p=[0.45, 0.2, 0.15, 0.1, 0.06, 0.04])),
                "payment_value": price + freight,
            })
            if status != "canceled" or random.random() < 0.3:
                base_score = p["review_mu"]
                if status == "canceled":
                    base_score = min(base_score, 2.2)
                elif customer_date is not None and customer_date > est_delivery:
                    base_score -= 1.1
                score = int(np.clip(round(np.random.normal(base_score, 0.9)), 1, 5))
                anchor = customer_date or purchase_ts
                reviews.append({
                    "review_id": new_id(), "order_id": order_id, "review_score": score,
                    "review_comment_title": None, "review_comment_message": None,
                    "review_creation_date": anchor + timedelta(days=1),
                    "review_answer_timestamp": anchor + timedelta(days=3),
                })

sellers_df.drop(columns=["_archetype", "_join_idx", "_pivot_idx"]).to_csv(
    os.path.join(OUT_DIR, "olist_sellers_dataset.csv"), index=False)
pd.DataFrame(orders).to_csv(os.path.join(OUT_DIR, "olist_orders_dataset.csv"), index=False)
pd.DataFrame(items).to_csv(os.path.join(OUT_DIR, "olist_order_items_dataset.csv"), index=False)
pd.DataFrame(reviews).to_csv(os.path.join(OUT_DIR, "olist_order_reviews_dataset.csv"), index=False)
pd.DataFrame(payments).to_csv(os.path.join(OUT_DIR, "olist_order_payments_dataset.csv"), index=False)
pd.DataFrame(customers).drop_duplicates("customer_id").to_csv(os.path.join(OUT_DIR, "olist_customers_dataset.csv"), index=False)

print(f"sellers={len(sellers_df)}  orders={len(orders)}  items={len(items)}  reviews={len(reviews)}  payments={len(payments)}")
print(f"date range: {MONTHS[0].strftime('%Y-%m')} to {MONTHS[-1].strftime('%Y-%m')}")
