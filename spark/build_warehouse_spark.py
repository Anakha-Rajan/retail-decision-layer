"""
PySpark implementation of the same warehouse build - optional branch.

Why it exists: the SQLite path is correct for one retailer with 56,000 rows.
It stops being correct at a few hundred million rows, or when the same model
has to run on Databricks against a chain rather than a single store. This file
shows the identical logic expressed against Spark so the migration is a
platform change, not a rewrite.

Deliberately NOT the default. Bringing Spark to a 56k-row problem would be
the wrong engineering decision, and shipping it as the default would be
resume-driven development rather than analysis.

    pip install pyspark
    spark-submit spark/build_warehouse_spark.py --data data --out outputs/delta
"""
from __future__ import annotations

import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


def month_name_col(c):
    return F.date_format(F.to_date(F.concat_ws("-", F.lit("2000"),
                                               F.lpad(c.cast("string"), 2, "0"),
                                               F.lit("01"))), "MMMM")


def build(data_dir: str, out_dir: str, fmt: str = "parquet") -> None:
    spark = (SparkSession.builder
             .appName("retail-decision-layer")
             .config("spark.sql.shuffle.partitions", "8")
             .getOrCreate())

    tx = (spark.read.option("header", True).option("inferSchema", True)
          .csv(f"{data_dir}/transactions.csv")
          .withColumn("transaction_date", F.to_date("transaction_date")))

    # ---- dim_date --------------------------------------------------------
    dim_date = (tx.select(F.col("transaction_date").alias("d")).distinct()
                .withColumn("date_key", F.date_format("d", "yyyy-MM-dd"))
                .withColumn("year", F.year("d"))
                .withColumn("month", F.month("d"))
                .withColumn("month_name", month_name_col(F.month("d")))
                .withColumn("quarter", F.quarter("d"))
                .withColumn("day_of_week", F.dayofweek("d") - 1)
                .withColumn("is_weekend", (F.dayofweek("d").isin(1, 7)).cast("int"))
                # Indian fiscal year: April to March
                .withColumn("fy_start", F.when(F.month("d") >= 4, F.year("d"))
                                         .otherwise(F.year("d") - 1))
                .withColumn("fiscal_year",
                            F.concat(F.lit("FY"), F.col("fy_start"), F.lit("-"),
                                     F.substring((F.col("fy_start") + 1).cast("string"), 3, 2)))
                .withColumn("fiscal_month", ((F.month("d") - 4) % 12) + 1)
                .drop("d", "fy_start"))

    # ---- dim_category with data-derived price band -----------------------
    dim_category = (tx.groupBy("category")
                    .agg(F.expr("percentile_approx(unit_price, 0.5)").alias("median_price"))
                    .withColumn("price_band",
                                F.when(F.col("median_price") >= 6000, "Premium")
                                 .when(F.col("median_price") >= 1500, "Mid")
                                 .otherwise("Value"))
                    .withColumn("category_id",
                                F.row_number().over(Window.orderBy("category"))))

    dim_channel = (tx.select("channel").distinct()
                   .withColumn("channel_id", F.row_number().over(Window.orderBy("channel")))
                   .withColumn("is_physical",
                               F.col("channel").isin("Walk-in", "Exhibition Stall").cast("int")))

    dim_customer = (tx.groupBy("customer_id")
                    .agg(F.min("transaction_date").alias("first_purchase"),
                         F.max("transaction_date").alias("last_purchase"),
                         F.countDistinct("transaction_id").alias("lifetime_orders"),
                         F.round(F.sum("net_amount"), 2).alias("lifetime_value")))

    # ---- fact ------------------------------------------------------------
    fact = (tx.join(F.broadcast(dim_category.select("category", "category_id")), "category")
              .join(F.broadcast(dim_channel.select("channel", "channel_id")), "channel")
              .withColumn("date_key", F.date_format("transaction_date", "yyyy-MM-dd"))
              .withColumn("gross_margin", F.round(F.col("net_amount") - F.col("cogs"), 2))
              .select("transaction_id", "date_key", "store_id", "category_id",
                      "channel_id", "customer_id", "quantity", "unit_price",
                      "discount_pct", "net_amount", "cogs", "gross_margin"))

    for name, df, part in [("dim_date", dim_date, None),
                           ("dim_category", dim_category, None),
                           ("dim_channel", dim_channel, None),
                           ("dim_customer", dim_customer, None),
                           ("fact_sales", fact, "date_key")]:
        w = df.write.mode("overwrite").format(fmt)
        if part:
            # Partitioning on date_key is what makes the month-range scans in
            # the reporting layer cheap once this is bigger than memory.
            w = w.partitionBy(part)
        w.save(f"{out_dir}/{name}")

    print(f"fact rows: {fact.count():,}")
    spark.stop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="outputs/spark")
    ap.add_argument("--format", default="parquet", choices=["parquet", "delta"])
    build(*vars(ap.parse_args()).values())
