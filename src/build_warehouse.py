"""Build the SQLite star schema from raw CSV exports."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "outputs" / "retail.db"

SEASONS = {1: "Pongal", 2: "Post-Pongal", 3: "Lean", 4: "Wedding",
           5: "Wedding", 6: "Lean", 7: "Aadi", 8: "Aadi",
           9: "Pre-festive", 10: "Deepavali", 11: "Deepavali", 12: "Year-end"}
MONTH_NAMES = {i: n for i, n in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}


def _fiscal(dt: pd.Series) -> pd.Series:
    """Indian fiscal year: April to March."""
    y = dt.dt.year.where(dt.dt.month >= 4, dt.dt.year - 1)
    return "FY" + y.astype(str) + "-" + (y + 1).astype(str).str[-2:]


def build(data_dir: Path | None = None, db_path: Path | None = None) -> Path:
    data_dir = Path(data_dir or ROOT / "data")
    db_path = Path(db_path or DB)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    tx = pd.read_csv(data_dir / "transactions.csv", parse_dates=["transaction_date"])
    stores = pd.read_csv(data_dir / "stores.csv")
    budget = pd.read_csv(data_dir / "budget.csv")

    con = sqlite3.connect(db_path)
    for f in ("01_dimensions.sql", "02_fact.sql"):
        con.executescript((ROOT / "sql" / f).read_text(encoding="utf-8"))

    # ---- dim_date --------------------------------------------------------
    dates = pd.DataFrame({"d": pd.date_range(tx["transaction_date"].min(),
                                             tx["transaction_date"].max(), freq="D")})
    dim_date = pd.DataFrame({
        "date_key": dates["d"].dt.strftime("%Y-%m-%d"),
        "year": dates["d"].dt.year,
        "month": dates["d"].dt.month,
        "month_name": dates["d"].dt.month.map(MONTH_NAMES),
        "quarter": dates["d"].dt.quarter,
        "day_of_week": dates["d"].dt.weekday,
        "is_weekend": (dates["d"].dt.weekday >= 5).astype(int),
        "fiscal_year": _fiscal(dates["d"]),
        "fiscal_month": ((dates["d"].dt.month - 4) % 12) + 1,
        "season": dates["d"].dt.month.map(SEASONS),
    })
    dim_date.to_sql("dim_date", con, if_exists="append", index=False)
    stores.to_sql("dim_store", con, if_exists="append", index=False)

    # ---- dim_category: price band derived from observed data, not typed in
    cat_price = tx.groupby("category")["unit_price"].median()
    dim_cat = pd.DataFrame({"category": sorted(tx["category"].unique())})
    dim_cat["category_id"] = range(1, len(dim_cat) + 1)
    dim_cat["price_band"] = dim_cat["category"].map(
        lambda c: "Premium" if cat_price[c] >= 6000
        else ("Mid" if cat_price[c] >= 1500 else "Value"))
    dim_cat[["category_id", "category", "price_band"]].to_sql(
        "dim_category", con, if_exists="append", index=False)

    dim_ch = pd.DataFrame({"channel": sorted(tx["channel"].unique())})
    dim_ch["channel_id"] = range(1, len(dim_ch) + 1)
    dim_ch["is_physical"] = dim_ch["channel"].isin(["Walk-in", "Exhibition Stall"]).astype(int)
    dim_ch[["channel_id", "channel", "is_physical"]].to_sql(
        "dim_channel", con, if_exists="append", index=False)

    cust = tx.groupby("customer_id").agg(
        first_purchase=("transaction_date", "min"),
        last_purchase=("transaction_date", "max"),
        lifetime_orders=("transaction_id", "nunique"),
        lifetime_value=("net_amount", "sum")).reset_index()
    cust["first_purchase"] = cust["first_purchase"].dt.strftime("%Y-%m-%d")
    cust["last_purchase"] = cust["last_purchase"].dt.strftime("%Y-%m-%d")
    cust.to_sql("dim_customer", con, if_exists="append", index=False)

    # ---- fact ------------------------------------------------------------
    fact = tx.merge(dim_cat[["category", "category_id"]], on="category") \
             .merge(dim_ch[["channel", "channel_id"]], on="channel")
    fact["date_key"] = fact["transaction_date"].dt.strftime("%Y-%m-%d")
    fact["gross_margin"] = (fact["net_amount"] - fact["cogs"]).round(2)
    fact[["transaction_id", "date_key", "store_id", "category_id", "channel_id",
          "customer_id", "quantity", "unit_price", "discount_pct", "net_amount",
          "cogs", "gross_margin"]].to_sql("fact_sales", con, if_exists="append",
                                          index=False)

    budget.to_sql("budget", con, if_exists="append", index=False)
    con.executescript((ROOT / "sql" / "03_views.sql").read_text(encoding="utf-8"))
    con.commit()

    n = con.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    rev = con.execute("SELECT SUM(net_amount) FROM fact_sales").fetchone()[0]
    con.close()
    print(f"Warehouse built: {n:,} fact rows, INR {rev/1e7:.2f} cr -> {db_path}")
    return db_path


if __name__ == "__main__":
    build()
