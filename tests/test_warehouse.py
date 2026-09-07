import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import forecast as fc_mod
from src import rfm as rfm_mod
from src import variance as var_mod
from src.build_warehouse import build

DB = ROOT / "outputs" / "retail.db"


@pytest.fixture(scope="module")
def db():
    if not DB.exists():
        build()
    return DB


@pytest.fixture(scope="module")
def con(db):
    c = sqlite3.connect(db)
    yield c
    c.close()


# --- warehouse integrity ---------------------------------------------------

def test_no_orphan_foreign_keys(con):
    for fk, dim, pk in [("date_key", "dim_date", "date_key"),
                        ("store_id", "dim_store", "store_id"),
                        ("category_id", "dim_category", "category_id"),
                        ("channel_id", "dim_channel", "channel_id"),
                        ("customer_id", "dim_customer", "customer_id")]:
        n = con.execute(
            f"SELECT COUNT(*) FROM fact_sales f "
            f"LEFT JOIN {dim} d ON d.{pk} = f.{fk} WHERE d.{pk} IS NULL").fetchone()[0]
        assert n == 0, f"{n} orphan rows on {fk}"


def test_fact_grain_is_unique(con):
    total, distinct = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT transaction_id) FROM fact_sales").fetchone()
    assert total == distinct


def test_view_revenue_matches_fact(con):
    a = con.execute("SELECT ROUND(SUM(net_amount),2) FROM fact_sales").fetchone()[0]
    b = con.execute("SELECT ROUND(SUM(revenue),2) FROM v_monthly_kpi").fetchone()[0]
    assert a == pytest.approx(b, abs=1.0)


def test_channel_mix_sums_to_100_per_year(con):
    df = pd.read_sql("SELECT fiscal_year, SUM(pct_of_revenue) s FROM v_channel_mix "
                     "GROUP BY fiscal_year", con)
    assert (df["s"] - 100).abs().max() < 0.1


def test_fiscal_year_boundary_is_april(con):
    r = con.execute("SELECT fiscal_year FROM dim_date WHERE date_key='2025-03-31'").fetchone()[0]
    s = con.execute("SELECT fiscal_year FROM dim_date WHERE date_key='2025-04-01'").fetchone()[0]
    assert r == "FY2024-25" and s == "FY2025-26"


# --- variance --------------------------------------------------------------

def test_variance_decomposition_reconciles(db):
    """The load-bearing assertion of the whole module."""
    dec, _ = var_mod.run(db, "FY2025-26")
    assert var_mod.reconciliation_error(dec) < 1.0  # INR, i.e. rounding only


def test_bridge_ends_at_actual_revenue(db):
    dec, bridge = var_mod.run(db, "FY2025-26")
    assert bridge.iloc[-1]["value"] == pytest.approx(dec["actual_revenue"].sum(), abs=1.0)


def test_price_variance_responds_to_price_only():
    import pandas as pd
    budget = pd.DataFrame({"category": ["A"], "budget_qty": [100],
                           "budget_revenue": [1000.0]})
    actual = pd.DataFrame({"category": ["A"], "actual_qty": [100],
                           "actual_revenue": [1200.0]})
    d = var_mod.decompose(actual, budget)
    assert d["price_variance"].sum() == pytest.approx(200.0)
    assert d["volume_variance"].sum() == pytest.approx(0.0)
    assert d["mix_variance"].sum() == pytest.approx(0.0)


# --- customers & forecast --------------------------------------------------

def test_rfm_segments_partition_the_base(db):
    rfm, seg = rfm_mod.run(db)
    assert seg["customers"].sum() == len(rfm)
    assert rfm["customer_id"].is_unique


def test_rfm_scores_in_range(db):
    rfm, _ = rfm_mod.run(db)
    for c in ("R", "F", "M"):
        assert rfm[c].between(1, 5).all()


def test_seasonal_indices_average_to_one(con):
    idx = fc_mod.seasonal_indices(fc_mod.monthly_series(con))
    assert idx.mean() == pytest.approx(1.0, abs=0.01)


def test_aadi_is_the_trough(con):
    """Domain sanity check: July and August must be the weakest months."""
    idx = fc_mod.seasonal_indices(fc_mod.monthly_series(con))
    assert idx.idxmin() in (7, 8)
    assert idx.loc[10] > 1.2  # Deepavali


def test_forecast_intervals_are_ordered(db):
    fc, _, _ = fc_mod.run(db, horizon=6)
    assert (fc["lower_80"] < fc["forecast"]).all()
    assert (fc["forecast"] < fc["upper_80"]).all()


def test_backtest_reports_a_baseline(db):
    _, _, bt = fc_mod.run(db)
    assert "seasonal_naive_mape_pct" in bt
    assert bt["model_mape_pct"] > 0
