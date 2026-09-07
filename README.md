# Retail Decision Layer

**A SQL warehouse, a variance decomposition and a backtested forecast for an SME retailer whose data currently lives in Tally and a WhatsApp group.**

Worked example: **two-store apparel retailer, Coimbatore, 55,697 transactions, ₹18.9 cr over 24 months.**

---

## The problem this solves

Small retailers are not short of data. They are short of a layer between the data and the decision.

The owner can tell you last month's turnover to the rupee. What they cannot tell you is whether the shortfall against plan came from selling fewer pieces, from selling a cheaper blend of pieces, or from discounting harder than intended — even though those three answers lead to three completely different decisions, and they routinely point in opposite directions.

This is the missing layer. Star schema, tested SQL models, an FP&A-grade variance bridge, RFM built around a seasonal buying rhythm, and a forecast that has to earn its place against a naive baseline before anyone is allowed to use it.

---

## What it produces

### 1. The variance bridge — where the plan actually broke

```
=== FY2025-26 vs budget ===
  Budget revenue                 10.06 cr
  Price / discount effect        +0.04 cr
  Volume effect                  -0.16 cr
  Mix effect                     -0.03 cr
  Actual revenue                  9.91 cr
  (decomposition reconciles to within INR 0.02)

  Largest single miss: Silk Saree at 96.8% of plan
    (volume -6.8L, mix -8.6L, price +1.3L)
```

Headline: revenue landed 1.5% under plan. Useless on its own.

The decomposition is the finding. **Silk sarees missed by more on mix than on volume** — footfall held up, but customers traded down out of the highest-ticket category into fancy sarees, which beat its own plan by ₹6.3L on mix. The business did not lose customers. It lost basket value, in one specific category, and it partly masked that by discounting less than planned.

The three effects are separated as:

```
price_i  = Qa_i × (Pa_i − Pb_i)
volume_i = Pb_i × mb_i × (Qa_total − Qb_total)
mix_i    = Pb_i × Qa_total × (ma_i − mb_i)
```

They sum to the total variance exactly. `test_variance_decomposition_reconciles` asserts the residual is under one rupee, because a decomposition that does not reconcile is one nobody should be shown.

### 2. Customer segments named as actions, not labels

```
Steady middle - hold                          28.5% of customers   23.3% of revenue
Big spender, low frequency - upsell events    16.5% of customers   22.2% of revenue
Champions - protect                           11.5% of customers   15.9% of revenue
Loyal but slipping - reactivate               10.5% of customers   11.8% of revenue
New - convert to second purchase              13.8% of customers   10.9% of revenue
Dormant low value - do not spend              14.6% of customers    9.4% of revenue
High value, overdue - call them                4.6% of customers    6.4% of revenue
```

The last row is the one worth money: **119 customers, 4.6% of the base, ₹1.01 lakh of lifetime value each, and overdue against their own buying rhythm.** That is a callable list, not a segment.

Standard RFM would have filed most of them as lapsed. That is wrong for seasonal retail — a customer who buys once a year at Deepavali is not lapsed in March, they are on schedule. So recency is scored against each customer's own observed inter-purchase interval, not a fixed window.

### 3. A forecast that had to beat a baseline

```
backtest: model MAPE 5.62% vs seasonal naive 7.34% -> model beats seasonal naive

  Apr 2026    1.10 cr  [1.06 - 1.14]
  Jul 2026    0.50 cr  [0.46 - 0.54]
  Sep 2026    0.85 cr  [0.81 - 0.89]
```

Multiplicative seasonal decomposition plus a linear trend on the deseasonalised series. Not a neural network, and deliberately so: with 24 monthly observations from a business whose seasonality is *already known* — Pongal up, Aadi down, Deepavali carrying the year — a heavy model has nothing to learn that the calendar does not say, and it cannot be explained to the person who has to act on it.

Every run reports the backtest against seasonal-naive. If the model loses, `verdict` says so in plain words and tells you to use the baseline instead. There is a test asserting the July–August trough is the seasonal minimum, because a model that misses Aadi is broken regardless of its error metric.

### 4. Findings that fall out of the SQL

The views surface things the owner has never had a number for:

- **Exhibition stalls carry 19.2% of revenue at a 6.1% average discount, against 0.77% for walk-in** — an eightfold difference in discount intensity in a channel taken on faith.
- **The top customer decile drives 17.6% of revenue; the top three deciles drive 43.6%** — concentration worth knowing before losing one of them.
- **Aadi (₹1.76 cr) runs at roughly a third of Deepavali (₹4.57 cr)** — which makes it a scheduled staffing and inventory decision, not an annual surprise.

---

## Why a star schema for 56,000 rows

Because the schema is not for the row count, it is for the questions.

The owner's real question is *"which channel is falling, in which month, for which category."* Off a flat transaction table that is a full scan and three string joins every single time, re-typed slightly differently by whoever asks. Off conformed dimensions it is one `GROUP BY`, and every dashboard reads the same definition of "revenue".

The BI layer reads only from views (`v_sales_detail`, `v_monthly_kpi`, `v_channel_mix`, `v_customer_concentration`), never from `fact_sales`. Change a definition in one SQL file instead of in fourteen DAX measures scattered across three reports.

`src/export_powerbi.py` materialises a pre-aggregated monthly grain so Power BI imports a few thousand rows instead of 56,000 and aggregates client-side.

---

## The Spark branch, and why it is not the default

`spark/build_warehouse_spark.py` expresses the identical build against PySpark — window functions for surrogate keys, broadcast joins on the dimensions, `date_key` partitioning for cheap month-range scans.

It exists so that moving this to Databricks against a chain rather than a single store is a platform change and not a rewrite. It is **not** the default, because bringing Spark to a 56,000-row problem would be the wrong engineering decision, and shipping it as the default would be resume-driven development rather than analysis.

---

## Run it

```bash
pip install -r requirements.txt

python scripts/make_sample_data.py     # regenerate the sample dataset
python -m src.cli --rebuild            # build warehouse, run everything
pytest tests/ -q                       # 14 tests

# optional Spark branch
pip install pyspark
spark-submit spark/build_warehouse_spark.py --data data --out outputs/spark
```

Outputs: `variance_by_category.csv`, `variance_bridge.csv`, `rfm_customers.csv`, `rfm_segments.csv`, `forecast.csv`, `summary.json`, `powerbi/*.csv`, plus `variance_waterfall.png`, `forecast.png`, `segments.png`.

---

## What the tests actually protect

Not coverage for its own sake. The 14 tests target the things that break silently and get shipped:

- no orphan foreign keys, unique fact grain, views reconciling to the fact table
- fiscal year rolls at 1 April, not 1 January
- the variance decomposition reconciles to under one rupee
- a pure price change produces zero volume and zero mix variance
- seasonal indices average to 1.0, and the Aadi trough is where it should be
- forecast intervals are correctly ordered and a baseline is always reported

---

## Honest limitations

- **The data is synthetic.** The structure is not — the category mix, the Aadi collapse, the exhibition-stall channel and the way SME budgets get made (last year's actuals uprated by a flat percentage, last year's mix held) are all modelled on anonymised patterns from real engagements. `scripts/make_sample_data.py` shows every assumption explicitly. Point the loader at a real export and nothing downstream changes.
- **COGS is a category-level margin assumption, not line-level cost.** Gross margin figures are therefore directional. Real cost data would change the category rankings and possibly the conclusions.
- **The budget is deliberately naive**, because real SME budgets are. That is what makes mix variance worth measuring — a plan built by holding last year's mix will always miss on mix.
- **24 months is two seasonal cycles.** Enough to estimate seasonal indices; not enough to separate a genuine trend from one unusual year. The confidence intervals reflect residual spread only, not parameter uncertainty, so they are narrower than the truth.
- **RFM describes the past.** It identifies customers who look overdue. It does not establish that contacting them causes them to buy — that needs a holdout test, which this repository does not run.

---

*Built by [Anakha Rajan](https://www.linkedin.com/in/) — mechanical engineer turned data analyst. I build this layer for retail clients; this is the version I can show you.*
