"""
Figure generation for the Data Descriptor manuscript.
================================================================
NOT part of the data collection pipeline (01-10) -- a standalone utility
that builds publication figures from the already-collected output/*.csv
files. Palette and mark specs come from the dataviz skill
(references/palette.md, marks-and-anatomy.md) -- categorical colors are
drawn from the validated 8-slot set (CVD-safe on adjacent pairs), not
picked by eye.

Figure 1 -- data source coverage by time span and spatial granularity
           (timeline/Gantt).
Figure 2 -- regional share of national production by year, wheat and
           barley (the main Technical Validation result, built from the
           row-level data in 07_validation_report.csv, not just the
           summary range).
Figure 3 -- export/domestic/world price spread by week
           (09_price_spread.csv).

Output: figures/figure1_coverage.png (+.pdf), figures/figure2_validation.png
(+.pdf), figures/figure3_price_spread.png (+.pdf) -- 300 DPI PNG for
preview, vector PDF for journal typesetting.
"""

import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import MultipleLocator
import pandas as pd

OUTPUT_DIR = "output"
FIG_DIR = "figures"
os.makedirs(FIG_DIR, exist_ok=True)

# -- Palette (references/palette.md, light mode) -----------------------
BLUE    = "#2a78d6"
ORANGE  = "#eb6834"
AQUA    = "#1baf7a"
YELLOW  = "#eda100"
MAGENTA = "#e87ba4"
GREEN   = "#008300"

INK_PRIMARY   = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED     = "#898781"
GRID          = "#e1e0d9"
BASELINE      = "#c3c2b7"
SURFACE       = "#fcfcfb"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"],
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "text.color": INK_PRIMARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def save(fig, name):
    png = os.path.join(FIG_DIR, f"{name}.png")
    pdf = os.path.join(FIG_DIR, f"{name}.pdf")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    print(f"  Saved: {png}")
    print(f"  Saved: {pdf}")


# ══════════════════════════════════════════════════════════════════
# Figure 1 -- data coverage: source x time span x granularity
# ══════════════════════════════════════════════════════════════════

def figure1_coverage():
    # (row label, start, end, category, kind: "bar" | "point" | "bar_min")
    rows = [
        ("World prices\n(World Bank Pink Sheet)",     1990, 2025,    "World (global)",          "bar"),
        ("Production\n(FAOSTAT)",                      1992, 2024,    "Kazakhstan (national)",   "bar"),
        ("Climate\n(ERA5-Land)",                        1991, 2025,    "Grain belt (aggregate)",  "bar"),
        ("Soil\n(SoilGrids v2.0)",                      2026, 2026,    "Grain belt (aggregate)",  "point"),
        ("Production\n(stat.gov.kz, oblast)",           1990, 2025,    "Oblast level",             "bar"),
        ("Production\n(stat.gov.kz, district)",         1990, 2025,    "District level",           "bar"),
        ("Domestic market\n(grainunion.kz, weekly)",    2026.40, 2026.68, "Domestic market (weekly)", "bar_min"),
    ]

    categories = [
        "World (global)", "Kazakhstan (national)", "Grain belt (aggregate)",
        "Oblast level", "District level", "Domestic market (weekly)",
    ]
    cat_color = dict(zip(categories, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN]))

    fig, ax = plt.subplots(figsize=(7.6, 3.9))

    bar_h = 0.55
    MIN_VISUAL_WIDTH = 1.6  # years -- artificial width floor, for visibility of short segments only

    for i, (label, start, end, cat, kind) in enumerate(rows):
        y = len(rows) - 1 - i
        color = cat_color[cat]

        if kind == "point":
            ax.plot(start, y, marker="D", markersize=9, color=color,
                     markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3)
            ax.text(start + 0.8, y, "point-in-time snapshot\n(collected 2026, no time series)",
                     ha="left", va="center", fontsize=7.5, color=INK_SECONDARY)
            continue

        real_width = end - start
        draw_width = max(real_width, MIN_VISUAL_WIDTH) if kind == "bar_min" else real_width
        draw_start = start if kind != "bar_min" else end - MIN_VISUAL_WIDTH

        ax.barh(
            y, draw_width, left=draw_start, height=bar_h,
            color=color, edgecolor=SURFACE, linewidth=2, zorder=3,
        )

        if kind == "bar_min":
            # Short segment is stretched for visibility only -- bar width is
            # NOT proportional to the actual 12 weeks; state that honestly
            # outside the bar (there isn't room to fit the label inside
            # without clipping it, so it goes outside instead).
            ax.text(draw_start - 0.4, y, "not to scale →", ha="right", va="center",
                     fontsize=7, color=INK_MUTED, style="italic")
            ax.text(draw_start + draw_width + 0.4, y,
                     "since 2026-05-25, growing weekly\n(actual: 12 wk at build time)",
                     ha="left", va="center", fontsize=7.5, color=INK_SECONDARY)
        else:
            ax.text(start - 0.3, y, f"{start:.0f}", ha="right", va="center",
                     fontsize=7.5, color=INK_SECONDARY)
            ax.text(end + 0.3, y, f"{end:.0f}", ha="left", va="center",
                     fontsize=7.5, color=INK_SECONDARY)

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in reversed(rows)], fontsize=8.5, color=INK_PRIMARY)
    ax.set_xlim(1988, 2032)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.xaxis.set_major_locator(MultipleLocator(5))
    ax.set_xlabel("Year", fontsize=9)

    ax.grid(axis="x", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(axis="both", length=0)

    handles = [mpatches.Patch(facecolor=cat_color[c], label=c) for c in categories]
    ax.legend(
        handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.22),
        ncol=3, frameon=False, fontsize=8, handlelength=1.2, handleheight=1.2,
        columnspacing=1.2,
    )

    fig.suptitle("Figure 1. Temporal coverage and spatial granularity of data sources",
                  fontsize=10, y=1.04, color=INK_PRIMARY)
    save(fig, "figure1_coverage")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
# Figure 2 -- regional share of national production (validation)
# ══════════════════════════════════════════════════════════════════

def figure2_validation():
    v = pd.read_csv(os.path.join(OUTPUT_DIR, "07_validation_report.csv"))

    fig, ax = plt.subplots(figsize=(6.4, 3.8))

    series = [("Пшеница", "Wheat", BLUE), ("Ячмень", "Barley", ORANGE)]
    for crop_ru, crop_en, color in series:
        sub = v[v.crop == crop_ru].sort_values("year")
        ax.plot(sub.year, sub.production_share * 100, color=color, linewidth=2,
                marker="o", markersize=3.5, markerfacecolor=color,
                markeredgecolor=SURFACE, markeredgewidth=0.8, zorder=3)
        last = sub.iloc[-1]
        ax.text(last.year + 0.5, last.production_share * 100, crop_en,
                fontsize=9, color=INK_PRIMARY, va="center", fontweight="semibold")

    ax.axhline(100, color=INK_MUTED, linewidth=1, linestyle="-", zorder=1)
    ax.text(v.year.min(), 101.5, "national total (FAOSTAT) = 100%",
            fontsize=7.5, color=INK_MUTED, va="bottom")

    ax.set_ylim(0, 110)
    ax.set_xlim(v.year.min() - 1, v.year.max() + 4)
    ax.set_ylabel("Share of national production, %", fontsize=9)
    ax.set_xlabel("Year", fontsize=9)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(axis="both", length=0, labelsize=8)

    fig.suptitle(
        "Figure 2. Cross-validation: Akmola+Kostanay+North Kazakhstan oblasts' share\n"
        "of national production (FAOSTAT), by year",
        fontsize=10, y=1.08, color=INK_PRIMARY,
    )
    save(fig, "figure2_validation")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
# Figure 3 (bonus) -- price spread: export / domestic / world
# ══════════════════════════════════════════════════════════════════

def figure3_price_spread():
    path = os.path.join(OUTPUT_DIR, "09_price_spread.csv")
    if not os.path.exists(path):
        print("  09_price_spread.csv not found -- skipping Figure 3")
        return
    s = pd.read_csv(path)
    s["date_from"] = pd.to_datetime(s["date_from"])
    s = s.sort_values("date_from")

    fig, ax = plt.subplots(figsize=(6.4, 3.6))

    series = [
        ("export_usd_per_t", "Export (DAP)", ORANGE),
        ("domestic_usd_per_t", "Domestic market (EXW)", BLUE),
        ("world_usd_per_t", "World benchmark (World Bank)*", AQUA),
    ]
    for col, label, color in series:
        ax.plot(s.date_from, s[col], color=color, linewidth=2,
                marker="o", markersize=3.5, markerfacecolor=color,
                markeredgecolor=SURFACE, markeredgewidth=0.8,
                label=label, zorder=3)

    ax.set_ylabel("USD / t (Grade-3 wheat)", fontsize=9)
    ax.set_xlabel("Week (start date)", fontsize=9)
    fig.autofmt_xdate(rotation=30, ha="right")

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(axis="both", length=0, labelsize=8)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=3,
              frameon=False, fontsize=7.5, handlelength=1.2)

    ax.text(0.01, -0.40,
            "* World Bank Pink Sheet lags the review date by up to 8 months (latest available month: Dec 2025);\n"
            "  last known value used (as-of), not an exact contemporaneous price.",
            transform=ax.transAxes, fontsize=6.5, color=INK_MUTED, va="top")

    fig.suptitle("Figure 3. Grade-3 wheat price spread: export vs. domestic market vs. world",
                  fontsize=10, y=1.05, color=INK_PRIMARY)
    save(fig, "figure3_price_spread")
    plt.close(fig)


if __name__ == "__main__":
    print("Figure 1 -- data coverage...")
    figure1_coverage()
    print("\nFigure 2 -- validation (regional share)...")
    figure2_validation()
    print("\nFigure 3 -- price spread (bonus)...")
    figure3_price_spread()
    print("\nDone.")
