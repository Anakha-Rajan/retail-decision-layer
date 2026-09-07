-- ============================================================================
-- Dimensions
-- ----------------------------------------------------------------------------
-- A star schema is not ceremony here. The owner's real question is "which
-- channel is dying in which month for which category" - three dimensions and
-- a measure. Answering that off a flat transaction table means a scan and a
-- string join every single time. Answering it off conformed dimensions means
-- the question is one GROUP BY.
-- ============================================================================

DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date (
    date_key        TEXT PRIMARY KEY,      -- ISO date
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT    NOT NULL,
    quarter         INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,
    is_weekend      INTEGER NOT NULL,
    fiscal_year     TEXT    NOT NULL,      -- Indian FY: April to March
    fiscal_month    INTEGER NOT NULL,      -- 1 = April
    season          TEXT    NOT NULL       -- retail-meaningful, not calendar
);

DROP TABLE IF EXISTS dim_store;
CREATE TABLE dim_store (
    store_id    TEXT PRIMARY KEY,
    store_name  TEXT NOT NULL,
    city        TEXT NOT NULL
);

DROP TABLE IF EXISTS dim_category;
CREATE TABLE dim_category (
    category_id   INTEGER PRIMARY KEY,
    category      TEXT NOT NULL UNIQUE,
    price_band    TEXT NOT NULL           -- derived from observed unit price
);

DROP TABLE IF EXISTS dim_channel;
CREATE TABLE dim_channel (
    channel_id  INTEGER PRIMARY KEY,
    channel     TEXT NOT NULL UNIQUE,
    is_physical INTEGER NOT NULL
);

DROP TABLE IF EXISTS dim_customer;
CREATE TABLE dim_customer (
    customer_id      TEXT PRIMARY KEY,
    first_purchase   TEXT,
    last_purchase    TEXT,
    lifetime_orders  INTEGER,
    lifetime_value   REAL
);
