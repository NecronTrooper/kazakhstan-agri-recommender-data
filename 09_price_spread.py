"""
Скрипт 09 — Спред: внутренняя цена (Казахстан) vs мировая цена (World Bank)
==============================================================================
Отвечает на вопрос диссертации про "нарық динамикасы" (рыночную динамику):
сейчас выгоднее фермеру продавать зерно внутри страны или экспортировать?

Считает две вещи по каждому еженедельному выпуску 08_grainunion_prices.py:

  1. world_spread — внутренняя цена (EXW-элеватор, тыс.тенге/т, из
     grainunion.kz) минус мировая цена (World Bank Pink Sheet, USD/т,
     wheat_hrw — US Hard Red Winter, ближайший публичный бенчмарк к
     казахстанской твёрдой продовольственной пшенице). Внутренняя цена
     переводится в USD по курсу Нацбанка РК за ТУ ЖЕ неделю (курс берётся
     из того же выпуска обзора, где указана цена — не из внешнего FX-
     источника, это даёт точное сопоставление на дату).

  2. export_spread — внутри самого Казахстана: цена экспорта (DAP
     ст.Сарыагаш, USD/т, из того же обзора) минус внутренняя цена EXW-
     элеватор (USD/т). Это более прямое, "яблоки к яблокам" сравнение
     (одна страна, один сорт, одна неделя) — показывает премию/дисконт
     экспорта над внутренним рынком без привязки к общемировому
     бенчмарку.

ВАЖНОЕ МЕТОДОЛОГИЧЕСКОЕ ОГРАНИЧЕНИЕ: на 2026-09-09 доступно всего
12 недель данных (с 25.05.2026) — этого недостаточно для отдельной
ARIMA/Prophet-модели ряда спреда (нужно 1-2+ полных сезонных цикла).
Спред здесь считается как ОПИСАТЕЛЬНЫЙ/диагностический сигнал текущего
состояния рынка и как потенциальный корректирующий признак поверх
модели, обученной на длинной истории (World Bank Pink Sheet, 1990-2025),
а не как самостоятельный прогнозный ряд. См. README, раздел
"Внутренний рынок Казахстана".
"""

import os
import re
import sys
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
OUT_CSV = os.path.join(OUTPUT_DIR, "09_price_spread.csv")

# Бенчмарк для сопоставления с мировой ценой: усредняем по всем подклассам
# 3-го класса пшеницы (наиболее ходовой продовольственный класс).
WHEAT3_LABEL_RE = re.compile(r"пшеница\s*3\s*кл", re.IGNORECASE)


def load_domestic_wheat3() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "08_grainunion_domestic_prices.csv")
    df = pd.read_csv(path)
    dom = df[(df.orientation == "domestic") & (df.crop_label.str.match(WHEAT3_LABEL_RE))]
    dom = dom.groupby(["article_id", "date_from", "date_to"]).agg(
        domestic_kzt_per_t_min=("price_min", "mean"),
        domestic_kzt_per_t_max=("price_max", "mean"),
    ).reset_index()
    dom["domestic_kzt_per_t"] = (dom.domestic_kzt_per_t_min + dom.domestic_kzt_per_t_max) / 2 * 1000
    return dom[["article_id", "date_from", "date_to", "domestic_kzt_per_t"]]


def load_export_wheat3() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "08_grainunion_domestic_prices.csv")
    df = pd.read_csv(path)
    exp = df[(df.orientation == "export") & (df.crop_label.str.match(WHEAT3_LABEL_RE))
             & (df.basis == "DAP")]
    exp = exp.groupby(["article_id"]).agg(
        export_usd_per_t_min=("price_min", "mean"),
        export_usd_per_t_max=("price_max", "mean"),
    ).reset_index()
    exp["export_usd_per_t"] = (exp.export_usd_per_t_min + exp.export_usd_per_t_max) / 2
    return exp[["article_id", "export_usd_per_t"]]


def load_fx() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "08_grainunion_fx_rates.csv")
    return pd.read_csv(path)[["article_id", "USD"]].rename(columns={"USD": "usd_kzt_rate"})


def load_world_wheat_monthly() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "02_worldbank_prices.csv")
    df = pd.read_csv(path)
    if "year" not in df.columns:
        raise ValueError("Ожидался годовой файл — используйте 02_prices_monthly.csv, если он есть")
    return df


def load_world_wheat_for_dates(dates: pd.Series) -> pd.DataFrame:
    """
    Подбирает мировую цену на пшеницу (World Bank) для каждой недельной
    даты через as-of merge (последнее известное значение НА ИЛИ ДО этой
    даты) — обычный точный месячный match здесь не сработает, так как
    Pink Sheet имеет лаг публикации (см. докстринг 02_worldbank_prices.py:
    "обновление ~январь N -> данные по декабрь N-1"), а недельные даты
    grainunion.kz относятся к 2026 году, для которого на момент сборки
    этого пайплайна (2026-09-09) в Pink Sheet ещё нет ни одного месяца.
    Каждой недельной точке присваивается последняя известная мировая цена
    и явно помечается, на сколько месяцев она "устарела" относительно
    даты обзора — не выдаём NaN молча и не притворяемся, что это точное
    совпадение месяца.
    """
    monthly_path = os.path.join(OUTPUT_DIR, "02_prices_monthly.csv")
    wb = pd.read_csv(monthly_path)
    wb["wb_date"] = pd.to_datetime(wb["year"].astype(str) + "-" + wb["month"].astype(int).astype(str).str.zfill(2) + "-01")
    wb = wb.sort_values("wb_date")[["wb_date", "wheat_hrw_usd_t"]].dropna()

    dates_df = pd.DataFrame({"date_from": dates.sort_values().values}).drop_duplicates()
    merged = pd.merge_asof(dates_df, wb, left_on="date_from", right_on="wb_date", direction="backward")
    merged["months_stale"] = (
        (merged["date_from"].dt.year - merged["wb_date"].dt.year) * 12
        + (merged["date_from"].dt.month - merged["wb_date"].dt.month)
    )
    lookup_price = merged.set_index("date_from")["wheat_hrw_usd_t"]
    lookup_stale = merged.set_index("date_from")["months_stale"]
    return pd.DataFrame({
        "world_usd_per_t": dates.map(lookup_price).values,
        "world_price_months_stale": dates.map(lookup_stale).values,
    })


def main():
    print("=" * 70)
    print("  Скрипт 09 — Спред: внутренняя цена (KZ) vs мировая цена")
    print("=" * 70)

    dom_path = os.path.join(OUTPUT_DIR, "08_grainunion_domestic_prices.csv")
    if not os.path.exists(dom_path):
        print(f"  ❌ {dom_path} не найден — сначала запустите 08_grainunion_prices.py")
        return

    dom = load_domestic_wheat3()
    exp = load_export_wheat3()
    fx = load_fx()

    merged = dom.merge(exp, on="article_id", how="left").merge(fx, on="article_id", how="left")
    merged["date_from"] = pd.to_datetime(merged["date_from"])
    merged["date_to"] = pd.to_datetime(merged["date_to"])

    merged["domestic_usd_per_t"] = merged["domestic_kzt_per_t"] / merged["usd_kzt_rate"]
    merged["export_spread_usd_per_t"] = merged["export_usd_per_t"] - merged["domestic_usd_per_t"]
    merged["export_spread_pct"] = merged["export_spread_usd_per_t"] / merged["domestic_usd_per_t"] * 100

    print(f"\n  Подбор мировой цены (World Bank Pink Sheet, wheat_hrw)...")
    world = load_world_wheat_for_dates(merged["date_from"])
    merged["world_usd_per_t"] = world["world_usd_per_t"].values
    merged["world_price_months_stale"] = world["world_price_months_stale"].values
    merged["world_spread_usd_per_t"] = merged["domestic_usd_per_t"] - merged["world_usd_per_t"]
    merged["world_spread_pct"] = merged["world_spread_usd_per_t"] / merged["world_usd_per_t"] * 100
    max_stale = merged["world_price_months_stale"].max()
    if max_stale and max_stale > 0:
        print(f"  ⚠️  Мировая цена устарела до {int(max_stale)} мес. относительно даты обзора")
        print(f"      (Pink Sheet ещё не опубликовал более свежие месяцы) — используется")
        print(f"      последнее известное значение, помечено в колонке world_price_months_stale.")

    merged = merged.sort_values("date_from")
    out_cols = [
        "article_id", "date_from", "date_to", "usd_kzt_rate",
        "domestic_kzt_per_t", "domestic_usd_per_t",
        "export_usd_per_t", "export_spread_usd_per_t", "export_spread_pct",
        "world_usd_per_t", "world_price_months_stale", "world_spread_usd_per_t", "world_spread_pct",
    ]
    merged[out_cols].to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n  💾 Сохранено: {OUT_CSV} ({len(merged)} недель)")
    print(f"\n  Пшеница 3 класс (усреднено по подклассам), последние недели:")
    print(merged[["date_from", "domestic_usd_per_t", "export_usd_per_t",
                   "export_spread_usd_per_t", "world_usd_per_t", "world_spread_usd_per_t"]]
          .tail(6).to_string(index=False))

    avg_export_spread = merged["export_spread_pct"].mean()
    avg_world_spread = merged["world_spread_pct"].mean()
    print(f"\n  Средний спред экспорт-внутренний рынок: {avg_export_spread:+.1f}%")
    print(f"  Средний спред внутренний-мировой рынок:  {avg_world_spread:+.1f}%")
    if avg_export_spread > 0:
        print("  -> в среднем за период экспорт выгоднее продажи на внутренний элеватор.")
    else:
        print("  -> в среднем за период продажа на внутренний элеватор выгоднее экспорта.")

    print(f"\n  ⚠️  Напоминание: {len(merged)} недель — недостаточно для отдельной")
    print(f"  time-series модели самого спреда (нужно 1-2+ сезонных цикла).")
    print(f"  Используйте как описательный сигнал/корректирующий признак, не как")
    print(f"  самостоятельный прогнозный ряд. Перезапускайте 08 и 09 по мере")
    print(f"  накопления истории.")


if __name__ == "__main__":
    main()
