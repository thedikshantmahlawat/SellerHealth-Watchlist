-- schema.sql
-- Raw tables, matching the Olist dataset's native structure column-for-column.
-- These are loaded directly from data/raw/*.csv by src/load_to_sql.py.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS sellers;
CREATE TABLE sellers (
    seller_id               TEXT PRIMARY KEY,
    seller_zip_code_prefix  INTEGER,
    seller_city             TEXT,
    seller_state            TEXT
);

DROP TABLE IF EXISTS customers;
CREATE TABLE customers (
    customer_id             TEXT PRIMARY KEY,
    customer_unique_id      TEXT,
    customer_zip_code_prefix INTEGER,
    customer_city           TEXT,
    customer_state          TEXT
);

DROP TABLE IF EXISTS orders;
CREATE TABLE orders (
    order_id                        TEXT PRIMARY KEY,
    customer_id                     TEXT REFERENCES customers(customer_id),
    order_status                    TEXT,     -- 'delivered' | 'canceled' (this project's scope)
    order_purchase_timestamp        TEXT,
    order_approved_at               TEXT,
    order_delivered_carrier_date    TEXT,
    order_delivered_customer_date   TEXT,     -- NULL if never delivered (e.g. canceled)
    order_estimated_delivery_date   TEXT      -- the promised delivery date shown to the buyer
);

DROP TABLE IF EXISTS order_items;
CREATE TABLE order_items (
    order_id            TEXT REFERENCES orders(order_id),
    order_item_id        INTEGER,
    product_id           TEXT,
    seller_id            TEXT REFERENCES sellers(seller_id),
    shipping_limit_date  TEXT,
    price                REAL,     -- item price, BRL
    freight_value        REAL,     -- shipping cost, BRL
    PRIMARY KEY (order_id, order_item_id)
);

DROP TABLE IF EXISTS order_reviews;
CREATE TABLE order_reviews (
    review_id                TEXT PRIMARY KEY,
    order_id                 TEXT REFERENCES orders(order_id),
    review_score             INTEGER,   -- 1-5
    review_comment_title     TEXT,
    review_comment_message   TEXT,
    review_creation_date     TEXT,
    review_answer_timestamp  TEXT
);

DROP TABLE IF EXISTS order_payments;
CREATE TABLE order_payments (
    order_id               TEXT REFERENCES orders(order_id),
    payment_sequential      INTEGER,
    payment_type            TEXT,
    payment_installments    INTEGER,
    payment_value           REAL
);

CREATE INDEX IF NOT EXISTS idx_items_seller ON order_items(seller_id);
CREATE INDEX IF NOT EXISTS idx_items_order  ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_reviews_order ON order_reviews(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_order ON order_payments(order_id);
