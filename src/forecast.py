"""
Monthly revenue forecast: multiplicative seasonal decomposition plus a linear
trend on the deseasonalised series.

Deliberately not a black box. For 24 monthly observations from a business with
a violent and *known* seasonal cycle - Pongal up, Aadi down, Deepavali up -
a heavyweight model has nothing to learn that the calendar does not already
say, and it cannot be explained to the owner.

What matters more than the model is the honesty of the evaluation: every
forecast here is backtested against a seasonal-naive baseline (same month last
year). If the model cannot beat that, it should not be used, and the report
says so out loud.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


def monthly_series(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql(
        """SELECT year, month, ROUND(SUM(net_amount),2) AS revenue
           FROM v_sales_detail GROUP BY year, month ORDER BY year, month""", con)
    df["period"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    return df[["period", "revenue"]]


def seasonal_indices(series: pd.DataFrame, period_len: int = 12) -> pd.Series:
    """Average ratio of actual to a centred 12-month moving average."""
    s = series.set_index("period")["revenue"]
    trend = s.rolling(period_len, center=True, min_periods=period_len // 2).mean()
    ratio = (s / trend).dropna()
    idx = ratio.groupby(ratio.index.month).mean()
    return (idx / idx.mean()).round(4)          # normalise to mean 1.0


def fit_predict(series: pd.DataFrame, horizon: int = 6) -> tuple[pd.DataFrame, pd.Series]:
    idx = seasonal_indices(series)
    s = series.copy()
    s["seasonal"] = s["period"].dt.month.map(idx)
    s["deseasonalised"] = s["revenue"] / s["seasonal"]

    x = np.arange(len(s))
    slope, intercept = np.polyfit(x, s["deseasonalised"].values, 1)

    future_x = np.arange(len(s), len(s) + horizon)
    future_periods = pd.date_range(
        s["period"].iloc[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    future_seasonal = pd.Series(future_periods.month).map(idx).values

    forecast = (intercept + slope * future_x) * future_seasonal

    resid = s["revenue"] - (intercept + slope * x) * s["seasonal"]
    sigma = float(resid.std(ddof=1))

    out = pd.DataFrame({
        "period": future_periods,
        "forecast": np.round(forecast, 2),
        "lower_80": np.round(forecast - 1.28 * sigma, 2),
        "upper_80": np.round(forecast + 1.28 * sigma, 2),
    })
    return out, idx


def backtest(series: pd.DataFrame, holdout: int = 6) -> dict:
    """
    Train on everything except the last `holdout` months, then compare against
    the seasonal-naive baseline. This is the number that decides whether the
    model ships.
    """
    if len(series) <= holdout + 12:
        return {"status": "insufficient history for an honest backtest"}

    train, test = series.iloc[:-holdout], series.iloc[-holdout:]
    pred, _ = fit_predict(train, horizon=holdout)

    actual = test["revenue"].values
    model_mape = float(np.mean(np.abs((actual - pred["forecast"].values) / actual)) * 100)

    lookup = series.set_index("period")["revenue"]
    naive = np.array([
        lookup.get(p - pd.DateOffset(years=1), np.nan) for p in test["period"]])
    mask = ~np.isnan(naive)
    naive_mape = float(np.mean(np.abs((actual[mask] - naive[mask]) / actual[mask])) * 100)

    return {
        "holdout_months": holdout,
        "model_mape_pct": round(model_mape, 2),
        "seasonal_naive_mape_pct": round(naive_mape, 2),
        "improvement_pct_points": round(naive_mape - model_mape, 2),
        "verdict": ("model beats seasonal naive" if model_mape < naive_mape
                    else "seasonal naive is as good or better - prefer it"),
    }


def run(db: str | Path, horizon: int = 6) -> tuple[pd.DataFrame, pd.Series, dict]:
    con = sqlite3.connect(db)
    try:
        s = monthly_series(con)
    finally:
        con.close()
    fc, idx = fit_predict(s, horizon)
    return fc, idx, backtest(s)
