"""
RFM segmentation with a retail-appropriate twist.

Standard RFM quintiles a customer base and stops. For a seasonal apparel
retailer that is misleading: a customer who buys once a year at Deepavali is
not 'lapsed' in March, they are on schedule. So recency is measured against
each customer's own observed inter-purchase interval where one exists, and the
segment names describe an action, not a label.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


def _score(s: pd.Series, ascending: bool = True, bins: int = 5) -> pd.Series:
    """Quintile score 1-5, robust to ties that break plain qcut."""
    ranked = s.rank(method="first", ascending=ascending)
    return pd.qcut(ranked, bins, labels=range(1, bins + 1)).astype(int)


def build(con: sqlite3.Connection, as_of: str | None = None) -> pd.DataFrame:
    tx = pd.read_sql(
        "SELECT customer_id, date_key, transaction_id, net_amount FROM v_sales_detail",
        con, parse_dates=["date_key"])

    asof = pd.Timestamp(as_of) if as_of else tx["date_key"].max()

    g = tx.groupby("customer_id").agg(
        last_purchase=("date_key", "max"),
        first_purchase=("date_key", "min"),
        frequency=("transaction_id", "nunique"),
        monetary=("net_amount", "sum"),
    ).reset_index()

    g["recency_days"] = (asof - g["last_purchase"]).dt.days
    g["tenure_days"] = (asof - g["first_purchase"]).dt.days

    # Each customer's own rhythm. Undefined for one-time buyers.
    g["avg_gap_days"] = np.where(
        g["frequency"] > 1,
        g["tenure_days"] / (g["frequency"] - 1).replace(0, np.nan),
        np.nan)

    # Overdue relative to personal rhythm; falls back to the cohort median gap.
    fallback = float(g["avg_gap_days"].median(skipna=True))
    g["expected_gap"] = g["avg_gap_days"].fillna(fallback)
    g["overdue_ratio"] = (g["recency_days"] / g["expected_gap"]).round(2)

    g["R"] = _score(g["recency_days"], ascending=False)
    g["F"] = _score(g["frequency"], ascending=True)
    g["M"] = _score(g["monetary"], ascending=True)
    g["rfm_score"] = g["R"] + g["F"] + g["M"]
    g["avg_order_value"] = (g["monetary"] / g["frequency"]).round(2)

    g["segment"] = g.apply(_segment, axis=1)
    return g.sort_values("monetary", ascending=False).reset_index(drop=True)


def _segment(r: pd.Series) -> str:
    if r["R"] >= 4 and r["F"] >= 4 and r["M"] >= 4:
        return "Champions - protect"
    if r["M"] >= 4 and r["overdue_ratio"] >= 2.0:
        return "High value, overdue - call them"
    if r["R"] >= 4 and r["F"] <= 2:
        return "New - convert to second purchase"
    if r["F"] >= 4 and r["R"] <= 2:
        return "Loyal but slipping - reactivate"
    if r["R"] <= 2 and r["M"] <= 2:
        return "Dormant low value - do not spend"
    if r["M"] >= 4:
        return "Big spender, low frequency - upsell events"
    return "Steady middle - hold"


def summary(rfm: pd.DataFrame) -> pd.DataFrame:
    s = rfm.groupby("segment").agg(
        customers=("customer_id", "count"),
        revenue=("monetary", "sum"),
        avg_order_value=("avg_order_value", "mean"),
        avg_orders=("frequency", "mean"),
        median_days_since=("recency_days", "median"),
    ).reset_index()
    s["pct_of_customers"] = (s["customers"] / s["customers"].sum() * 100).round(1)
    s["pct_of_revenue"] = (s["revenue"] / s["revenue"].sum() * 100).round(1)
    s["revenue_per_customer"] = (s["revenue"] / s["customers"]).round(0)
    return s.sort_values("revenue", ascending=False).round(2).reset_index(drop=True)


def run(db: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(db)
    try:
        rfm = build(con)
    finally:
        con.close()
    return rfm, summary(rfm)
