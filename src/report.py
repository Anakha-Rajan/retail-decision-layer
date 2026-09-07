"""Charts. Waterfall is the one that matters."""
from __future__ import annotations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PINK, PALE, INK, GREEN = "#ED267F", "#EFE5ED", "#1A1A1A", "#2E7D32"


def waterfall(bridge: pd.DataFrame, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    cum, xs, heights, bottoms, colors = 0.0, [], [], [], []

    for _, r in bridge.iterrows():
        v = r["value"] / 1e7
        if r["kind"] == "total":
            xs.append(r["step"]); heights.append(v); bottoms.append(0); colors.append(INK)
            cum = v
        else:
            xs.append(r["step"]); heights.append(v); bottoms.append(cum)
            colors.append(GREEN if v >= 0 else PINK)
            cum += v

    ax.bar(xs, heights, bottom=bottoms, color=colors, width=0.6)
    for i, (h, b) in enumerate(zip(heights, bottoms)):
        ax.text(i, b + h + (0.04 if h >= 0 else -0.12), f"{h:+.2f}" if bottoms[i] else f"{h:.2f}",
                ha="center", fontsize=9, color=INK)
    ax.set_ylabel("INR crore")
    ax.set_title("Budget to actual: which part of the gap is which",
                 loc="left", fontsize=11, weight="bold", color=INK)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=18, ha="right", fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=PALE); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
    return out


def forecast_chart(history: pd.DataFrame, fc: pd.DataFrame, out: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.plot(history["period"], history["revenue"] / 1e7, color=INK, lw=1.6, label="Actual")
    ax.plot(fc["period"], fc["forecast"] / 1e7, color=PINK, lw=2, ls="--", label="Forecast")
    ax.fill_between(fc["period"], fc["lower_80"] / 1e7, fc["upper_80"] / 1e7,
                    color=PINK, alpha=0.15, label="80% interval")
    ax.set_ylabel("Monthly revenue (INR crore)")
    ax.set_title("Aadi collapses, Deepavali carries the year",
                 loc="left", fontsize=11, weight="bold", color=INK)
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color=PALE); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
    return out


def segment_chart(summary: pd.DataFrame, out: Path) -> Path:
    d = summary.sort_values("pct_of_revenue")
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(d) + 1.8))
    ax.barh(d["segment"], d["pct_of_revenue"], color=PINK, label="% of revenue")
    ax.barh(d["segment"], d["pct_of_customers"], color=PALE, height=0.42,
            edgecolor=PINK, label="% of customers")
    ax.set_xlabel("Percent")
    ax.set_title("Revenue share vs customer share by segment",
                 loc="left", fontsize=11, weight="bold", color=INK)
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color=PALE); ax.set_axisbelow(True)
    fig.tight_layout(); fig.savefig(out, dpi=200, bbox_inches="tight"); plt.close(fig)
    return out
