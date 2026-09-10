"""
Скрипт 10 — Районный снимок "урожай × текущая цена"
=======================================================
⚠️ ЭТО ИЛЛЮСТРАТИВНЫЙ ДЕМО-АРТЕФАКТ, НЕ КОМПОНЕНТ МЕТОДОЛОГИИ. ⚠️
Решение от 2026-09-10 (см. README, раздел "Методологическая позиция:
районные данные (05) vs цена (08/09)"): для диссертации/статьи 05 и
08/09 остаются ДВУМЯ НЕЗАВИСИМЫМИ слоями до накопления у 08/09 истории
хотя бы за один полный с/х цикл (сентябрь 2026 — август 2027). Этот
скрипт существует только чтобы продемонстрировать, что recommender-слой
технически принимает оба входа (например, для научрука) — его выход
(`output/10_district_price_snapshot.csv`) НЕЛЬЗЯ цитировать как факт о
конкретном годе и НЕЛЬЗЯ использовать как источник для обучения/валидации
модели.

Отвечает на вопрос recommender-слоя: "сколько стоит прямо сейчас то, что
вырастил этот район" — соединяет РАЙОННУЮ урожайность/сбор (05, годовая,
1990–2025) с ТЕКУЩЕЙ ценой/спредом (08/09, недельная, с 25.05.2026).

ПОЧЕМУ ЭТО НЕ ОБЫЧНЫЙ JOIN ПО (регион, год):
  1. У 08/09 нет разбивки по области вообще — в обзорах grainunion.kz
     указана ОДНА цена EXW-элеватор сразу на "Акмолинская, Костанайская,
     Северо-Казахстанская области" (проверено 2026-09-10 по исходному
     тексту обзоров). Область как ключ join просто нечем сопоставлять на
     стороне цены.
  2. У 05 и 08/09 НЕТ ни одного общего года: районные данные — 1990–2025,
     ценовые — только недели 2026 года. Прямой join по year даст пустой
     результат.

ЧТО ДЕЛАЕТ СКРИПТ ВМЕСТО ЭТОГО (согласовано с пользователем 2026-09-10):
  Берёт ПОСЛЕДНИЙ доступный год районных данных (сейчас 2025, факт сбора)
  и ПОСЛЕДНЮЮ доступную неделю цены (сейчас конец августа/начало сентября
  2026) и соединяет их как "если бы урожай последнего сезона продавался
  по сегодняшней цене" — это НЕ исторический факт (урожай 2025 года
  физически продавался по ценам 2025/начала 2026, а не по ценам конца
  лета 2026), а разведочный, здесь-и-сейчас снимок для поддержки решения
  "продавать на элеватор или искать экспортный канал". Это date-mismatch
  сделан осознанно и прозрачно — если для диссертации важна историческая
  точность, использовать этот снимок как факт про 2025 год НЕЛЬЗЯ; его
  роль — actionable "текущая экономика" на момент прогона.

  Покрытие по культурам: цена (08) есть только для Пшеницы и Ячменя —
  для Кукурузы/Подсолнечника/групп культур снимок всё равно строится
  (сохраняется урожай), но price-колонки остаются NaN, а не пропускается
  вся строка.

ВАЖНО ДЛЯ ПОВТОРНЫХ ЗАПУСКОВ: "последний год" и "последняя неделя" —
плавающие точки отсчёта, которые сдвигаются с каждым новым прогоном 05 и
08. Этот скрипт НЕ кэширует историю снимков — каждый запуск полностью
перезаписывает output/10_district_price_snapshot.csv текущим срезом.
Если нужна история снимков по неделям — сохранять этот файл с меткой
даты запуска, скрипт сам этого не делает.
"""

import os
import re
import sys
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
OUT_CSV = os.path.join(OUTPUT_DIR, "10_district_price_snapshot.csv")

# район-урожайность crop -> regex подстроки для сопоставления с
# ценовыми crop_label в 08_grainunion_domestic_prices.csv
CROP_PRICE_PATTERNS = {
    "Пшеница": re.compile(r"пшениц", re.IGNORECASE),
    "Ячмень": re.compile(r"ячмен", re.IGNORECASE),
}


def load_latest_year_districts() -> pd.DataFrame:
    """
    Возвращает только настоящие районы, БЕЗ строки "Область (итого)" —
    она дублирует уже существующий областной уровень (05_kaz_stat.csv +
    09_price_spread.csv) и, будучи суммой всех районов, доминирует в любом
    ранжировании "топ районов по объёму", маскируя реальную районную
    картину, которая и есть смысл этого файла.
    """
    path = os.path.join(OUTPUT_DIR, "05_kaz_stat_districts.csv")
    df = pd.read_csv(path)
    latest_year = df["year"].max()
    snap = df[(df["year"] == latest_year) & (df["district"] != "Область (итого)")].copy()
    print(f"  Районные данные: последний доступный год = {latest_year} ({len(snap)} строк, без 'Область (итого)')")
    return snap, int(latest_year)


def load_latest_week_prices():
    path = os.path.join(OUTPUT_DIR, "08_grainunion_domestic_prices.csv")
    fx_path = os.path.join(OUTPUT_DIR, "08_grainunion_fx_rates.csv")
    prices = pd.read_csv(path)
    fx = pd.read_csv(fx_path)

    latest_article = prices["article_id"].max()
    latest = prices[prices["article_id"] == latest_article].copy()
    date_from = latest["date_from"].iloc[0]
    date_to = latest["date_to"].iloc[0]
    usd_kzt = fx.loc[fx["article_id"] == latest_article, "USD"].iloc[0]
    print(f"  Ценовые данные: последняя неделя = {date_from}..{date_to} (курс {usd_kzt:.2f} KZT/USD)")

    rows = []
    for crop, pattern in CROP_PRICE_PATTERNS.items():
        dom = latest[(latest.orientation == "domestic") & (latest.crop_label.str.contains(pattern))]
        exp = latest[(latest.orientation == "export") & (latest.crop_label.str.contains(pattern))
                      & (latest.basis.isin(["DAP", "FOB"]))]
        if dom.empty:
            continue
        dom_kzt_per_t = (dom.price_min.mean() + dom.price_max.mean()) / 2 * 1000
        dom_usd_per_t = dom_kzt_per_t / usd_kzt
        exp_usd_per_t = ((exp.price_min.mean() + exp.price_max.mean()) / 2) if not exp.empty else None
        rows.append({
            "crop": crop,
            "price_week_date_from": date_from,
            "price_week_date_to": date_to,
            "usd_kzt_rate": usd_kzt,
            "domestic_usd_per_t": dom_usd_per_t,
            "export_usd_per_t": exp_usd_per_t,
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 70)
    print("  Скрипт 10 — Районный снимок: урожай (последний год) x цена (последняя неделя)")
    print("=" * 70)

    districts, latest_year = load_latest_year_districts()
    prices = load_latest_week_prices()

    if prices.empty:
        print("  ❌ Нет ценовых данных — запустите 08_grainunion_prices.py")
        return

    snapshot = districts.merge(prices, on="crop", how="left")

    snapshot["notional_revenue_domestic_usd"] = snapshot["production_ton"] * snapshot["domestic_usd_per_t"]
    snapshot["notional_revenue_export_usd"] = snapshot["production_ton"] * snapshot["export_usd_per_t"]
    snapshot["export_uplift_usd"] = (
        snapshot["notional_revenue_export_usd"] - snapshot["notional_revenue_domestic_usd"]
    )

    snapshot = snapshot.sort_values(["region", "district", "crop"]).reset_index(drop=True)
    snapshot.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    n_with_price = snapshot["domestic_usd_per_t"].notna().sum()
    print(f"\n  💾 Сохранено: {OUT_CSV}")
    print(f"  Строк: {len(snapshot)} (год урожая={latest_year}), из них с ценой: {n_with_price}")
    print(f"  Культуры без цены в 08 (площадь/урожай сохранены, price-колонки = NaN):")
    no_price_crops = sorted(snapshot.loc[snapshot.domestic_usd_per_t.isna(), "crop"].unique())
    print(f"    {no_price_crops}")

    top = snapshot.dropna(subset=["export_uplift_usd"]).nlargest(5, "export_uplift_usd")
    if not top.empty:
        print(f"\n  Топ-5 районов по потенциальному выигрышу от экспорта (USD, на текущий урожай):")
        print(top[["region", "district", "crop", "production_ton", "export_uplift_usd"]].to_string(index=False))

    print(f"\n  ⚠️  НАПОМИНАНИЕ: год урожая ({latest_year}) и неделя цены")
    print(f"  ({prices.price_week_date_from.iloc[0]}) — РАЗНЫЕ периоды, это намеренный")
    print(f"  'здесь и сейчас' снимок, а не исторический факт про {latest_year} год.")
    print(f"  При каждом новом прогоне 05/08 обе точки отсчёта сдвигаются — файл")
    print(f"  перезаписывается заново, история снимков не хранится.")


if __name__ == "__main__":
    main()
