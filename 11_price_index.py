"""
Скрипт 11 — Индекс цен производителей сельхозпродукции (stat.gov.kz, 1992–2025)
====================================================================================
Источник: Бюро национальной статистики РК (stat.gov.kz)
          Раздел "Статистика цен" → "Цены в сельском, лесном и рыбном хозяйстве" →
          Динамические ряды → "Индекс цен производителей на отдельные виды
          продукции сельского хозяйства".
          Элемент ID 1644 (НЕ /region/<id>/, как в 05_kaz_stat.py — это
          национальная, не региональная таблица):
          https://stat.gov.kz/api/iblock/element/1644/file/ru/

Как найдено (2026-10-01):
  Прямое продолжение проблемы, описанной в 08_grainunion_prices.py: внутренний
  рынок Казахстана там покрыт всего ~12 еженедельными выпусками (с 25.05.2026),
  меньше одного сезона. У stat.gov.kz нашёлся официальный годовой индекс цен
  производителей с 1992 по 2025 год (33 года) — не абсолютная цена, а % к
  предыдущему периоду, но зато с реальной исторической глубиной.

  ВАЖНОЕ ОГРАНИЧЕНИЕ ГРАНУЛЯРНОСТИ (подтверждено разбором файла): по
  растениеводству индекс даёт только ДВЕ товарные группы —
  "культуры зерновые" и "семена масличные" — отдельного индекса по пшенице,
  ячменю, кукурузе или подсолнечнику здесь НЕТ. Это тот же уровень
  детализации, что публикует Акмолинская область в 05_kaz_stat.py
  (stat_gov_kz_real_group), но здесь он национальный, а не региональный.
  Не пытайтесь сопоставлять этот индекс напрямую с рядами пшеницы/ячменя
  Костанайской и СКО областей без явной оговорки о несовпадении уровня
  детализации.

  Животноводческие строки (скот и птица, молоко, яйца, шерсть) в файле есть,
  но в эту таблицу НЕ включены — вне тематики проекта (посевные культуры).

Структура исходного файла (3-й лист, остальные два — заголовок/легенда):
  Строка 3   — годы, столбцами: 1992 … 2025 (34 колонки)
  Строки 5-10  — блок "на конец периода, к декабрю предыдущего года" (Dec/Dec)
  Строки 17-22 — блок "к предыдущему году" (среднегодовой к среднегодовому)
  Обе строки блоков содержат одни и те же 6 категорий в одном порядке:
  Продукция сельского хозяйства, Продукция растениеводства, культуры зерновые,
  семена масличные, картофель, овощи.

Что делает скрипт:
  1. Скачивает xlsx, парсит оба блока индекса (eop и среднегодовой) по
     6 растениеводческим категориям.
  2. Сохраняет "сырые" индексы как есть (output/11_price_index_raw.csv,
     длинный формат) — без искажения первоисточника.
  3. Из среднегодового блока ("к предыдущему году", интерпретируется яснее
     чем Dec/Dec) строит цепной относительный уровень цены с базой = 100 в
     BASE_YEAR (по умолчанию 2015, см. константу ниже — произвольный выбор,
     меняется под нужды анализа) и сохраняет как
     output/11_price_index_chained.csv (широкий формат, по одной колонке на
     категорию).

  Склейка с master_dataset.csv НЕ выполняется автоматически: это
  национальный ряд по товарным ГРУППАМ, а master_dataset — в основном
  региональный и по отдельным культурам, и решение, как их сопоставлять
  (как прокси годовой инфляции для культур без отдельного индекса,
  либо только для строк "группа"), требует явного решения в 06_merge.py,
  а не молчаливого join здесь.
"""

import os
import sys
import io
import requests
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

ELEMENT_ID = 1644
FILE_URL = f"https://stat.gov.kz/api/iblock/element/{ELEMENT_ID}/file/ru/"
SHEET_INDEX = 2  # третий лист (0-индексация) — тот, что с данными по годам

# Строки в файле (0-индексация pandas, header=None), подтверждены разовым
# диагностическим разбором (см. докстринг выше).
YEAR_ROW = 2
BLOCK_EOP_ROWS = list(range(4, 10))     # "на конец периода, к декабрю предыдущего года"
BLOCK_AVG_ROWS = list(range(16, 22))    # "к предыдущему году" (среднегодовой)

# Порядок категорий одинаков в обоих блоках.
CATEGORY_SLUGS = [
    "agriculture_total",       # Продукция сельского хозяйства
    "crop_production_total",   # Продукция растениеводства
    "grain_crops_group",       # культуры зерновые
    "oilseed_crops_group",     # семена масличные
    "potato",                  # картофель
    "vegetables",              # овощи
]

BASE_YEAR = 2015  # произвольная база для цепного уровня — меняйте под задачу


def verify_url() -> bool:
    try:
        resp = requests.head(FILE_URL, timeout=15, allow_redirects=True)
        if resp.status_code < 400:
            print(f"  Файл доступен (HTTP {resp.status_code})")
            return True
        print(f"  HTTP {resp.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Недоступен: {e}")
        return False


def download_sheet() -> pd.DataFrame:
    print("  Скачивание файла...")
    resp = requests.get(FILE_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(resp.content))
    print(f"  Листы: {xls.sheet_names}")
    raw = pd.read_excel(xls, sheet_name=xls.sheet_names[SHEET_INDEX], header=None)
    print(f"  Размер листа данных: {raw.shape}")
    return raw


def validate_structure(raw: pd.DataFrame) -> bool:
    """Проверяет, что строки с категориями совпадают между блоками (пара по паре)."""
    print("\n  Проверка структуры...")
    ok = True
    for eop_row, avg_row, slug in zip(BLOCK_EOP_ROWS, BLOCK_AVG_ROWS, CATEGORY_SLUGS):
        eop_label = str(raw.iloc[eop_row, 0]).strip()
        avg_label = str(raw.iloc[avg_row, 0]).strip()
        status = "OK" if eop_label == avg_label else "MISMATCH"
        print(f"  [{status:8s}] row {eop_row:2d}/{avg_row:2d}: "
              f"'{eop_label}' == '{avg_label}' → {slug}")
        if eop_label != avg_label:
            ok = False
    return ok


def parse_long(raw: pd.DataFrame) -> pd.DataFrame:
    """Извлекает оба блока в длинный формат: year, category, metric, value."""
    years = raw.iloc[YEAR_ROW, 1:35].tolist()
    years = [int(y) for y in years]

    records = []
    for eop_row, avg_row, slug in zip(BLOCK_EOP_ROWS, BLOCK_AVG_ROWS, CATEGORY_SLUGS):
        category_ru = str(raw.iloc[eop_row, 0]).strip()
        eop_vals = raw.iloc[eop_row, 1:35].tolist()
        avg_vals = raw.iloc[avg_row, 1:35].tolist()

        for year, eop_val, avg_val in zip(years, eop_vals, avg_vals):
            def to_float(v):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None  # "…" и пропуски → NaN

            records.append({
                "year": year,
                "category": slug,
                "category_ru": category_ru,
                "index_eop_dec_to_dec_pct": to_float(eop_val),
                "index_avg_yoy_pct": to_float(avg_val),
            })

    df = pd.DataFrame(records)
    df["source"] = "stat_gov_kz_producer_price_index"
    return df


def build_chained_level(df_long: pd.DataFrame, base_year: int = BASE_YEAR) -> pd.DataFrame:
    """
    Строит цепной относительный уровень цены (база=100 в base_year) из
    среднегодового индекса "к предыдущему году". Это НЕ абсолютная цена в
    тенге, а относительный индикатор динамики, сопоставимый только внутри
    одной категории.
    """
    frames = []
    for slug in CATEGORY_SLUGS:
        sub = df_long[df_long["category"] == slug].sort_values("year").copy()
        sub = sub.dropna(subset=["index_avg_yoy_pct"])
        if sub.empty or base_year not in sub["year"].values:
            print(f"  [WARN] {slug}: нет данных за базовый год {base_year}, пропуск цепного уровня")
            continue

        sub = sub.reset_index(drop=True)
        base_idx = sub.index[sub["year"] == base_year][0]

        level = [None] * len(sub)
        level[base_idx] = 100.0
        # Вперёд от базового года
        for i in range(base_idx + 1, len(sub)):
            level[i] = level[i - 1] * sub.loc[i, "index_avg_yoy_pct"] / 100.0
        # Назад от базового года
        for i in range(base_idx - 1, -1, -1):
            level[i] = level[i + 1] / (sub.loc[i + 1, "index_avg_yoy_pct"] / 100.0)

        sub["price_level_base100"] = level
        frames.append(sub[["year", "category", "price_level_base100"]])

    long_level = pd.concat(frames, ignore_index=True)
    wide = long_level.pivot(index="year", columns="category", values="price_level_base100")
    wide = wide.reset_index()
    wide.columns.name = None
    wide["source"] = f"stat_gov_kz_producer_price_index_chained_base{base_year}"
    return wide


def print_summary(df_long: pd.DataFrame, df_chained: pd.DataFrame):
    print(f"\n  {'='*60}")
    print(f"  Период: {df_long['year'].min()}–{df_long['year'].max()}")
    print(f"  Категорий: {df_long['category'].nunique()}")
    print(f"  Строк (длинный формат): {len(df_long)}")

    print(f"\n  Последние 5 лет, среднегодовой индекс 'к предыдущему году' (%):")
    pivot = df_long.pivot(index="year", columns="category", values="index_avg_yoy_pct")
    print(pivot.tail(5).to_string())

    print(f"\n  Цепной уровень (база={BASE_YEAR}=100), последние 5 лет:")
    print(df_chained.tail(5).to_string(index=False))


def main():
    print("=" * 60)
    print("  Скрипт 11 — Индекс цен производителей сельхозпродукции РК")
    print(f"  Источник: stat.gov.kz, элемент {ELEMENT_ID}")
    print("  Период: 1992–2025, годовой")
    print("=" * 60)

    if not verify_url():
        print("Завершение.")
        return

    raw = download_sheet()

    ok = validate_structure(raw)
    if not ok:
        print("\n  Структура файла изменилась — сверьте BLOCK_EOP_ROWS/BLOCK_AVG_ROWS/")
        print("  CATEGORY_SLUGS в начале скрипта с фактическим выводом выше.")

    df_long = parse_long(raw)
    if df_long.empty:
        print("  Данные не получены.")
        return

    raw_path = os.path.join(OUTPUT_DIR, "11_price_index_raw.csv")
    df_long.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"\n  Сырые индексы (длинный формат): {raw_path}")

    df_chained = build_chained_level(df_long)
    chained_path = os.path.join(OUTPUT_DIR, "11_price_index_chained.csv")
    df_chained.to_csv(chained_path, index=False, encoding="utf-8-sig")
    print(f"  Цепной уровень (широкий формат): {chained_path}")

    print_summary(df_long, df_chained)


if __name__ == "__main__":
    main()
