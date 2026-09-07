"""
Generate the bundled sample dataset: 24 months of transactions for a
two-store Tamil Nadu apparel retailer, plus an annual budget.

The data is synthetic. The *structure* is not: category mix, channel mix,
the Aadi trough, the Diwali and Pongal peaks, the exhibition-stall channel
that carries a third of turnover in five months of the year - all modelled on
anonymised patterns from real SME retail engagements.

Replace data/*.csv with your own export and nothing downstream changes.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 11
random.seed(SEED)
rng = np.random.default_rng(SEED)

ROOT = Path(__file__).resolve().parents[1]
START = date(2024, 4, 1)
DAYS = 730

STORES = {"ST01": "Cross Cut Road", "ST02": "RS Puram"}

# category -> (base daily units per store, mean price, price sd, margin)
CATEGORIES = {
    "Silk Saree":    (3.2, 12800, 3400, 0.24),
    "Fancy Saree":   (7.5,  3150,  900, 0.34),
    "Cotton Saree":  (9.0,  1450,  380, 0.31),
    "Readymade":     (6.4,  2250,  700, 0.38),
    "Kids Wear":     (4.1,   980,  280, 0.41),
    "Accessories":   (5.8,   420,  160, 0.46),
}

CHANNELS = {"Walk-in": 0.55, "Exhibition Stall": 0.20,
            "WhatsApp Order": 0.17, "Online": 0.08}

# Multiplicative month factors. Aadi (mid Jul-mid Aug) is inauspicious for
# purchases in Tamil Nadu and reliably collapses apparel demand.
MONTH_FACTOR = {1: 1.42,  # Pongal
                2: 0.94, 3: 0.98,
                4: 1.18,  # Chithirai / Akshaya Tritiya, wedding season
                5: 1.12, 6: 0.92,
                7: 0.61, 8: 0.66,   # Aadi
                9: 1.05,
                10: 1.55, 11: 1.34,  # Deepavali build-up and month
                12: 1.08}

DOW_FACTOR = {0: 0.82, 1: 0.80, 2: 0.85, 3: 0.90, 4: 1.05, 5: 1.45, 6: 1.38}


def main() -> None:
    rows, cust_pool = [], [f"C{n:05d}" for n in range(1, 2600)]
    tid = 0

    for d in range(DAYS):
        day = START + timedelta(days=d)
        m, dow = day.month, day.weekday()
        trend = 1 + 0.00028 * d                      # slow underlying growth
        noise = float(rng.normal(1.0, 0.14))

        for store in STORES:
            store_scale = 1.0 if store == "ST01" else 0.68
            for cat, (base, price_mu, price_sd, margin) in CATEGORIES.items():
                lam = base * MONTH_FACTOR[m] * DOW_FACTOR[dow] * trend * noise * store_scale
                # Exhibition months push silk and fancy harder
                if m in (4, 5, 10, 11) and cat in ("Silk Saree", "Fancy Saree"):
                    lam *= 1.25
                n = int(rng.poisson(max(lam, 0.01)))

                for _ in range(n):
                    tid += 1
                    channel = random.choices(list(CHANNELS), weights=list(CHANNELS.values()))[0]
                    qty = 1 if random.random() < 0.86 else random.randint(2, 3)
                    unit = float(max(rng.normal(price_mu, price_sd), price_mu * 0.45))
                    disc = 0.0
                    if m in (10, 11) and random.random() < 0.35:
                        disc = round(random.uniform(0.04, 0.14), 3)
                    if channel == "Exhibition Stall" and random.random() < 0.5:
                        disc = max(disc, round(random.uniform(0.05, 0.18), 3))

                    net = round(unit * qty * (1 - disc), 2)
                    rows.append({
                        "transaction_id": f"T{tid:07d}",
                        "transaction_date": day.isoformat(),
                        "store_id": store,
                        "customer_id": random.choice(cust_pool),
                        "category": cat,
                        "channel": channel,
                        "quantity": qty,
                        "unit_price": round(unit, 2),
                        "discount_pct": disc,
                        "net_amount": net,
                        "cogs": round(net * (1 - margin), 2),
                    })

    tx = pd.DataFrame(rows)
    (ROOT / "data").mkdir(exist_ok=True)
    tx.to_csv(ROOT / "data" / "transactions.csv", index=False)

    # ---- Budget: what the owner planned for FY2025-26 ---------------------
    # Deliberately built by uprating FY2024-25 actuals by a flat 12% and
    # holding last year's category mix. That is exactly how SME budgets are
    # really made, and it is exactly why mix variance is worth measuring.
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"])
    prior = tx[tx["transaction_date"] < "2025-04-01"]
    plan = (prior.groupby([prior["transaction_date"].dt.month.rename("month"), "category"])
            .agg(qty=("quantity", "sum"), revenue=("net_amount", "sum"))
            .reset_index())
    plan["budget_qty"] = (plan["qty"] * 1.12).round(0).astype(int)
    plan["budget_price"] = (plan["revenue"] / plan["qty"]).round(2)
    plan["budget_revenue"] = (plan["budget_qty"] * plan["budget_price"]).round(2)
    plan["fiscal_year"] = "FY2025-26"
    plan[["fiscal_year", "month", "category", "budget_qty",
          "budget_price", "budget_revenue"]].to_csv(ROOT / "data" / "budget.csv", index=False)

    pd.DataFrame([{"store_id": k, "store_name": v, "city": "Coimbatore"}
                  for k, v in STORES.items()]).to_csv(ROOT / "data" / "stores.csv", index=False)

    print(f"{len(tx):,} transactions, {tx['net_amount'].sum()/1e7:.2f} cr revenue")
    print(f"{tx['transaction_date'].min().date()} to {tx['transaction_date'].max().date()}")
    print(f"budget rows: {len(plan)}")


if __name__ == "__main__":
    main()
