"""
    python -m src.cli --rebuild
    python -m src.cli --fiscal-year FY2025-26 --horizon 6
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from . import forecast as fc_mod
from . import rfm as rfm_mod
from . import variance as var_mod
from .build_warehouse import build
from .export_powerbi import export
from .report import forecast_chart, segment_chart, waterfall

DB = Path("outputs/retail.db")


def main() -> None:
    p = argparse.ArgumentParser(description="SME retail decision layer")
    p.add_argument("--rebuild", action="store_true", help="rebuild the warehouse from CSV")
    p.add_argument("--fiscal-year", default="FY2025-26")
    p.add_argument("--horizon", type=int, default=6)
    p.add_argument("--outdir", default="outputs")
    p.add_argument("--no-charts", action="store_true")
    args = p.parse_args()

    out = Path(args.outdir); out.mkdir(parents=True, exist_ok=True)
    if args.rebuild or not DB.exists():
        build()

    # ---- variance --------------------------------------------------------
    dec, bridge = var_mod.run(DB, args.fiscal_year)
    err = var_mod.reconciliation_error(dec)
    dec.to_csv(out / "variance_by_category.csv", index=False)
    bridge.to_csv(out / "variance_bridge.csv", index=False)

    print(f"\n=== {args.fiscal_year} vs budget ===")
    for _, r in bridge.iterrows():
        print(f"  {r['step']:<26} {r['value']/1e7:>9.2f} cr")
    print(f"  (decomposition reconciles to within INR {err:.2f})")

    worst = dec.iloc[0]
    print(f"\n  Largest single miss: {worst['category']} at "
          f"{worst['achievement_pct']}% of plan "
          f"(volume {worst['volume_variance']/1e5:+.1f}L, "
          f"mix {worst['mix_variance']/1e5:+.1f}L, "
          f"price {worst['price_variance']/1e5:+.1f}L)")

    # ---- customers -------------------------------------------------------
    rfm, seg = rfm_mod.run(DB)
    rfm.to_csv(out / "rfm_customers.csv", index=False)
    seg.to_csv(out / "rfm_segments.csv", index=False)
    print("\n=== Customer segments ===")
    for _, r in seg.iterrows():
        print(f"  {r['segment']:<44} {r['pct_of_customers']:>5.1f}% of customers  "
              f"{r['pct_of_revenue']:>5.1f}% of revenue")

    # ---- forecast --------------------------------------------------------
    fc, idx, bt = fc_mod.run(DB, args.horizon)
    fc.to_csv(out / "forecast.csv", index=False)
    print("\n=== Forecast ===")
    print(f"  backtest: model MAPE {bt.get('model_mape_pct')}% vs "
          f"seasonal naive {bt.get('seasonal_naive_mape_pct')}% -> {bt.get('verdict')}")
    for _, r in fc.iterrows():
        print(f"  {r['period']:%b %Y}  {r['forecast']/1e7:>6.2f} cr  "
              f"[{r['lower_80']/1e7:.2f} - {r['upper_80']/1e7:.2f}]")

    exported = export(DB)
    print(f"\n  Power BI extracts: {len(exported)} files -> outputs/powerbi/")

    if not args.no_charts:
        con = sqlite3.connect(DB)
        hist = fc_mod.monthly_series(con); con.close()
        waterfall(bridge, out / "variance_waterfall.png")
        forecast_chart(hist, fc, out / "forecast.png")
        segment_chart(seg, out / "segments.png")

    (out / "summary.json").write_text(json.dumps({
        "fiscal_year": args.fiscal_year,
        "reconciliation_error_inr": round(err, 4),
        "bridge": bridge.to_dict("records"),
        "backtest": bt,
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten to {out.resolve()}")


if __name__ == "__main__":
    main()
