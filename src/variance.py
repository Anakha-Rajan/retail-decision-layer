"""
Price / volume / mix variance decomposition.

"Revenue was 8% under plan" is not an insight, it is a symptom. The question
management actually needs answered is *which* 8%:

  - we sold fewer units than planned            -> volume
  - we sold a cheaper blend of what we planned   -> mix
  - we discounted harder than planned            -> price

Those three findings lead to three completely different decisions, and they
routinely point in opposite directions - a business can beat its revenue plan
on volume while quietly destroying margin on mix. This module separates them
and proves the separation reconciles exactly.

    price_i  = Qa_i * (Pa_i - Pb_i)
    volume_i = Pb_i * mb_i * (Qa_total - Qb_total)
    mix_i    = Pb_i * Qa_total * (ma_i - mb_i)

where m is each category's share of total units. Summed over all categories
these three add to (actual revenue - budget revenue) exactly - which is
asserted in the test suite, because a decomposition that does not reconcile
is a decomposition nobody should present.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def load_actuals(con: sqlite3.Connection, fiscal_year: str) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT category,
               SUM(quantity)   AS actual_qty,
               SUM(net_amount) AS actual_revenue
        FROM   v_sales_detail
        WHERE  fiscal_year = ?
        GROUP BY category
        """, con, params=[fiscal_year])


def load_budget(con: sqlite3.Connection, fiscal_year: str) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT category,
               SUM(budget_qty)     AS budget_qty,
               SUM(budget_revenue) AS budget_revenue
        FROM   budget
        WHERE  fiscal_year = ?
        GROUP BY category
        """, con, params=[fiscal_year])


def decompose(actual: pd.DataFrame, budget: pd.DataFrame) -> pd.DataFrame:
    df = budget.merge(actual, on="category", how="outer").fillna(0)

    df["budget_price"] = (df["budget_revenue"] / df["budget_qty"]).fillna(0)
    df["actual_price"] = (df["actual_revenue"] / df["actual_qty"]).fillna(0)

    qa_total = df["actual_qty"].sum()
    qb_total = df["budget_qty"].sum()
    df["budget_mix"] = df["budget_qty"] / qb_total
    df["actual_mix"] = df["actual_qty"] / qa_total

    df["price_variance"] = df["actual_qty"] * (df["actual_price"] - df["budget_price"])
    df["volume_variance"] = df["budget_price"] * df["budget_mix"] * (qa_total - qb_total)
    df["mix_variance"] = df["budget_price"] * qa_total * (df["actual_mix"] - df["budget_mix"])

    df["total_variance"] = df["actual_revenue"] - df["budget_revenue"]
    df["achievement_pct"] = (df["actual_revenue"] / df["budget_revenue"] * 100).round(1)

    cols = ["category", "budget_qty", "actual_qty", "budget_price", "actual_price",
            "budget_revenue", "actual_revenue", "total_variance",
            "price_variance", "volume_variance", "mix_variance", "achievement_pct"]
    return df[cols].round(2).sort_values("total_variance").reset_index(drop=True)


def bridge(decomposed: pd.DataFrame) -> pd.DataFrame:
    """The waterfall: budget -> price -> volume -> mix -> actual."""
    b = decomposed["budget_revenue"].sum()
    p = decomposed["price_variance"].sum()
    v = decomposed["volume_variance"].sum()
    m = decomposed["mix_variance"].sum()
    return pd.DataFrame([
        {"step": "Budget revenue", "value": round(b, 2), "kind": "total"},
        {"step": "Price / discount effect", "value": round(p, 2), "kind": "delta"},
        {"step": "Volume effect", "value": round(v, 2), "kind": "delta"},
        {"step": "Mix effect", "value": round(m, 2), "kind": "delta"},
        {"step": "Actual revenue", "value": round(b + p + v + m, 2), "kind": "total"},
    ])


def reconciliation_error(decomposed: pd.DataFrame) -> float:
    """Should be zero to floating-point tolerance. Report it, do not assume it."""
    parts = decomposed[["price_variance", "volume_variance", "mix_variance"]].sum().sum()
    return float(abs(parts - decomposed["total_variance"].sum()))


def run(db: str | Path, fiscal_year: str = "FY2025-26") -> tuple[pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(db)
    try:
        d = decompose(load_actuals(con, fiscal_year), load_budget(con, fiscal_year))
    finally:
        con.close()
    return d, bridge(d)
