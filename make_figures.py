"""
Генерация фигур для дескрипторной статьи (Data Descriptor).
================================================================
НЕ часть пайплайна сбора данных (01-10) — отдельная утилита, строит
публикационные фигуры из уже собранных output/*.csv. Палитра и спеки
марок взяты из навыка dataviz (references/palette.md,
marks-and-anatomy.md) — категориальные цвета из провалидированного
8-слотового набора (CVD-safe по соседним парам), не подобраны на глаз.

Figure 1 — покрытие данных по времени и гранулярности (timeline/Gantt).
Figure 2 — доля регионов от национального производства по годам,
           пшеница и ячмень (главный результат Technical Validation,
           реальные данные из 07_validation_report.csv, не агрегат).
Figure 3 — спред цен экспорт/внутренний рынок/мир по неделям
           (09_price_spread.csv).

Выход: figures/figure1_coverage.png (+.pdf), figures/figure2_validation.png
(+.pdf), figures/figure3_price_spread.png (+.pdf) — 300 DPI PNG для
предпросмотра, векторный PDF для вёрстки журнала.
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

# ── Палитра (references/palette.md, light mode) ──────────────────────
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
    print(f"  Сохранено: {png}")
    print(f"  Сохранено: {pdf}")


# ══════════════════════════════════════════════════════════════════
# Figure 1 — покрытие данных: источник x период x гранулярность
# ══════════════════════════════════════════════════════════════════

def figure1_coverage():
    # (метка строки, старт, конец, категория, тип: "bar" | "point")
    rows = [
        ("Мировые цены\n(World Bank Pink Sheet)",       1990, 2025,    "Мир (глобально)",           "bar"),
        ("Производство\n(FAOSTAT)",                      1992, 2024,    "Казахстан (национально)",   "bar"),
        ("Климат\n(ERA5-Land)",                          1991, 2025,    "Зерновой пояс (агрегат)",   "bar"),
        ("Почва\n(SoilGrids v2.0)",                      2026, 2026,    "Зерновой пояс (агрегат)",   "point"),
        ("Производство\n(stat.gov.kz, область)",         1990, 2025,    "По областям",               "bar"),
        ("Производство\n(stat.gov.kz, район)",           1990, 2025,    "По районам",                "bar"),
        ("Внутренний рынок\n(grainunion.kz, понедельно)", 2026.40, 2026.68, "Внутр. рынок (понедельно)", "bar_min"),
    ]

    categories = [
        "Мир (глобально)", "Казахстан (национально)", "Зерновой пояс (агрегат)",
        "По областям", "По районам", "Внутр. рынок (понедельно)",
    ]
    cat_color = dict(zip(categories, [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN]))

    fig, ax = plt.subplots(figsize=(7.6, 3.9))

    bar_h = 0.55
    MIN_VISUAL_WIDTH = 1.6  # года — искусственный пол ширины только для видимости коротких сегментов

    for i, (label, start, end, cat, kind) in enumerate(rows):
        y = len(rows) - 1 - i
        color = cat_color[cat]

        if kind == "point":
            ax.plot(start, y, marker="D", markersize=9, color=color,
                     markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3)
            ax.text(start + 0.8, y, "точечный снимок\n(собрано 2026, без временного ряда)",
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
            # короткий сегмент растянут только для видимости — ширина полосы НЕ
            # пропорциональна реальным 12 неделям; честно это проговариваем
            # снаружи (внутри полосы места на подпись всё равно не хватает —
            # текст, который не помещается, не обрезаем, а выносим наружу).
            ax.text(draw_start - 0.4, y, "не в масштабе →", ha="right", va="center",
                     fontsize=7, color=INK_MUTED, style="italic")
            ax.text(draw_start + draw_width + 0.4, y,
                     "с 25.05.2026, растёт понедельно\n(факт: 12 нед. на момент сборки)",
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
    ax.set_xlabel("Год", fontsize=9)

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

    fig.suptitle("Figure 1. Временной охват и пространственная гранулярность источников данных",
                  fontsize=10, y=1.04, color=INK_PRIMARY)
    save(fig, "figure1_coverage")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
# Figure 2 — доля региона от национального производства (валидация)
# ══════════════════════════════════════════════════════════════════

def figure2_validation():
    v = pd.read_csv(os.path.join(OUTPUT_DIR, "07_validation_report.csv"))

    fig, ax = plt.subplots(figsize=(6.4, 3.8))

    series = [("Пшеница", BLUE), ("Ячмень", ORANGE)]
    for crop, color in series:
        sub = v[v.crop == crop].sort_values("year")
        ax.plot(sub.year, sub.production_share * 100, color=color, linewidth=2,
                marker="o", markersize=3.5, markerfacecolor=color,
                markeredgecolor=SURFACE, markeredgewidth=0.8, zorder=3)
        last = sub.iloc[-1]
        ax.text(last.year + 0.5, last.production_share * 100, crop,
                fontsize=9, color=INK_PRIMARY, va="center", fontweight="semibold")

    ax.axhline(100, color=INK_MUTED, linewidth=1, linestyle="-", zorder=1)
    ax.text(v.year.min(), 101.5, "национальный итог (FAOSTAT) = 100%",
            fontsize=7.5, color=INK_MUTED, va="bottom")

    ax.set_ylim(0, 110)
    ax.set_xlim(v.year.min() - 1, v.year.max() + 4)
    ax.set_ylabel("Доля от национального производства, %", fontsize=9)
    ax.set_xlabel("Год", fontsize=9)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(BASELINE)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(axis="both", length=0, labelsize=8)

    fig.suptitle(
        "Figure 2. Кросс-валидация: доля Акмолинской+Костанайской+СКО областей\n"
        "от национального производства (FAOSTAT), по годам",
        fontsize=10, y=1.08, color=INK_PRIMARY,
    )
    save(fig, "figure2_validation")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
# Figure 3 (бонус) — спред цен: экспорт / внутренний рынок / мир
# ══════════════════════════════════════════════════════════════════

def figure3_price_spread():
    path = os.path.join(OUTPUT_DIR, "09_price_spread.csv")
    if not os.path.exists(path):
        print("  09_price_spread.csv не найден — Figure 3 пропущена")
        return
    s = pd.read_csv(path)
    s["date_from"] = pd.to_datetime(s["date_from"])
    s = s.sort_values("date_from")

    fig, ax = plt.subplots(figsize=(6.4, 3.6))

    series = [
        ("export_usd_per_t", "Экспорт (DAP)", ORANGE),
        ("domestic_usd_per_t", "Внутренний рынок (EXW)", BLUE),
        ("world_usd_per_t", "Мировой бенчмарк (World Bank)*", AQUA),
    ]
    for col, label, color in series:
        ax.plot(s.date_from, s[col], color=color, linewidth=2,
                marker="o", markersize=3.5, markerfacecolor=color,
                markeredgecolor=SURFACE, markeredgewidth=0.8,
                label=label, zorder=3)

    ax.set_ylabel("USD / т (пшеница 3 класс)", fontsize=9)
    ax.set_xlabel("Неделя (дата начала)", fontsize=9)
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
            "* World Bank Pink Sheet отстаёт от даты обзора до 8 месяцев (последний доступный месяц — декабрь 2025);\n"
            "  используется последнее известное значение (as-of), не апрель-2026-точная цена.",
            transform=ax.transAxes, fontsize=6.5, color=INK_MUTED, va="top")

    fig.suptitle("Figure 3. Спред цен на пшеницу 3 класса: экспорт vs внутренний рынок vs мир",
                  fontsize=10, y=1.05, color=INK_PRIMARY)
    save(fig, "figure3_price_spread")
    plt.close(fig)


if __name__ == "__main__":
    print("Figure 1 — покрытие данных...")
    figure1_coverage()
    print("\nFigure 2 — валидация (доля региона)...")
    figure2_validation()
    print("\nFigure 3 — спред цен (бонус)...")
    figure3_price_spread()
    print("\nГотово.")
