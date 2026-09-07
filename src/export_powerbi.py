"""
Flat exports for Power BI / Excel.

The warehouse is the source of truth; the BI tool should never re-implement
business logic. Everything Power BI needs is materialised here from the views,
so a definition changes in one SQL file rather than in fourteen DAX measures
scattered across three reports.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

VIEWS = ["v_monthly_kpi", "v_channel_mix", "v_customer_concentration"]


def export(db: str | Path, outdir: str | Path = "outputs/powerbi") -> list[Path]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    con = sqlite3.connect(db)
    try:
        for v in VIEWS:
            df = pd.read_sql(f"SELECT * FROM {v}", con)
            p = outdir / f"{v}.csv"
            df.to_csv(p, index=False)
            written.append(p)

        # A pre-aggregated grain small enough to load into Power BI directly,
        # instead of importing 56k rows and aggregating client-side.
        detail = pd.read_sql(
            """SELECT fiscal_year, year, month, month_name, season, store_name,
                      category, price_band, channel,
                      COUNT(DISTINCT transaction_id) AS bills,
                      SUM(quantity) AS units,
                      ROUND(SUM(net_amount),2) AS revenue,
                      ROUND(SUM(gross_margin),2) AS gross_margin
               FROM v_sales_detail
               GROUP BY fiscal_year, year, month, month_name, season, store_name,
                        category, price_band, channel""", con)
        p = outdir / "fact_monthly_grain.csv"
        detail.to_csv(p, index=False)
        written.append(p)
    finally:
        con.close()
    return written
