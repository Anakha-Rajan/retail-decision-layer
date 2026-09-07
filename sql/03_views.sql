-- ============================================================================
-- Reporting views. The BI layer reads only from here, never from fact_sales
-- directly - so a schema change breaks one file instead of every dashboard.
-- ============================================================================

DROP VIEW IF EXISTS v_sales_detail;
CREATE VIEW v_sales_detail AS
SELECT  f.transaction_id, f.date_key, d.year, d.month, d.month_name,
        d.fiscal_year, d.fiscal_month, d.season, d.is_weekend,
        s.store_name, c.category, c.price_band, ch.channel, ch.is_physical,
        f.customer_id, f.quantity, f.unit_price, f.discount_pct,
        f.net_amount, f.cogs, f.gross_margin
FROM        fact_sales f
JOIN        dim_date     d  ON d.date_key    = f.date_key
JOIN        dim_store    s  ON s.store_id    = f.store_id
JOIN        dim_category c  ON c.category_id = f.category_id
JOIN        dim_channel  ch ON ch.channel_id = f.channel_id;

DROP VIEW IF EXISTS v_monthly_kpi;
CREATE VIEW v_monthly_kpi AS
SELECT  fiscal_year, year, month, month_name, season,
        COUNT(DISTINCT transaction_id)          AS bills,
        COUNT(DISTINCT customer_id)             AS customers,
        SUM(quantity)                           AS units,
        ROUND(SUM(net_amount), 2)               AS revenue,
        ROUND(SUM(gross_margin), 2)             AS gross_margin,
        ROUND(SUM(gross_margin) * 100.0 / SUM(net_amount), 2) AS gm_pct,
        ROUND(SUM(net_amount) / COUNT(DISTINCT transaction_id), 2) AS avg_bill_value,
        ROUND(AVG(discount_pct) * 100, 2)       AS avg_discount_pct
FROM    v_sales_detail
GROUP BY fiscal_year, year, month, month_name, season;

-- Channel contribution: the number that changes where the owner spends time.
DROP VIEW IF EXISTS v_channel_mix;
CREATE VIEW v_channel_mix AS
SELECT  fiscal_year, channel,
        ROUND(SUM(net_amount), 2) AS revenue,
        ROUND(SUM(net_amount) * 100.0 /
              SUM(SUM(net_amount)) OVER (PARTITION BY fiscal_year), 2) AS pct_of_revenue,
        ROUND(SUM(gross_margin) * 100.0 / SUM(net_amount), 2) AS gm_pct,
        ROUND(AVG(discount_pct) * 100, 2) AS avg_discount_pct,
        COUNT(DISTINCT customer_id) AS customers
FROM    v_sales_detail
GROUP BY fiscal_year, channel;

-- Concentration risk. If the top decile of customers carries too much of the
-- book, the business is one relationship away from a bad year.
DROP VIEW IF EXISTS v_customer_concentration;
CREATE VIEW v_customer_concentration AS
WITH ranked AS (
    SELECT customer_id, SUM(net_amount) AS ltv,
           NTILE(10) OVER (ORDER BY SUM(net_amount) DESC) AS decile
    FROM   v_sales_detail GROUP BY customer_id
)
SELECT decile, COUNT(*) AS customers, ROUND(SUM(ltv), 2) AS revenue,
       ROUND(SUM(ltv) * 100.0 / (SELECT SUM(ltv) FROM ranked), 2) AS pct_of_revenue
FROM   ranked GROUP BY decile ORDER BY decile;
