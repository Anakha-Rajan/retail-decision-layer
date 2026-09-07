-- ============================================================================
-- Fact table + indexes
-- Grain: one row per transaction line.
-- ============================================================================

DROP TABLE IF EXISTS fact_sales;
CREATE TABLE fact_sales (
    transaction_id TEXT PRIMARY KEY,
    date_key       TEXT    NOT NULL REFERENCES dim_date(date_key),
    store_id       TEXT    NOT NULL REFERENCES dim_store(store_id),
    category_id    INTEGER NOT NULL REFERENCES dim_category(category_id),
    channel_id     INTEGER NOT NULL REFERENCES dim_channel(channel_id),
    customer_id    TEXT    NOT NULL REFERENCES dim_customer(customer_id),
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit_price     REAL    NOT NULL CHECK (unit_price > 0),
    discount_pct   REAL    NOT NULL CHECK (discount_pct >= 0 AND discount_pct < 1),
    net_amount     REAL    NOT NULL CHECK (net_amount > 0),
    cogs           REAL    NOT NULL,
    gross_margin   REAL    NOT NULL
);

CREATE INDEX idx_fact_date     ON fact_sales(date_key);
CREATE INDEX idx_fact_cat      ON fact_sales(category_id);
CREATE INDEX idx_fact_channel  ON fact_sales(channel_id);
CREATE INDEX idx_fact_customer ON fact_sales(customer_id);

DROP TABLE IF EXISTS budget;
CREATE TABLE budget (
    fiscal_year    TEXT    NOT NULL,
    month          INTEGER NOT NULL,
    category       TEXT    NOT NULL,
    budget_qty     INTEGER NOT NULL,
    budget_price   REAL    NOT NULL,
    budget_revenue REAL    NOT NULL,
    PRIMARY KEY (fiscal_year, month, category)
);
