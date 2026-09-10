"""
Скрипт 02 - World Bank Pink Sheet (мировые цены на сырьё)
===========================================================
Источник: World Bank Commodity Markets (CMO Pink Sheet)
Сайт:     https://www.worldbank.org/en/research/commodity-markets
Файл:     https://thedocs.worldbank.org/en/doc/
          18675f1d1639c7a34d463f59263ba0a2-0050012025/
          related/CMO-Historical-Data-Monthly.xlsx

Как найдено:
  World Bank Pink Sheet - стандартный академический источник мировых цен
  на сельскохозяйственные товары. Файл обновляется ежемесячно,
  последнее обновление - январь 2026 (данные по декабрь 2025).
  Структура листа "Monthly Prices" подтверждена диагностическим
  скриптом 02_diagnose.py:
    строка 4 (index 4) - названия товаров
    строка 5 (index 5) - единицы измерения
    строка 6+ (index 6+) - данные, col 0 = "1960M01", "1960M02", ...

Точные названия и номера нужных колонок (подтверждены):
  col 36 → 'Wheat, US SRW'    → wheat_srw_usd_t
  col 37 → 'Wheat, US HRW'    → wheat_hrw_usd_t
  col 29 → 'Barley'           → barley_usd_t
  col 30 → 'Maize'            → maize_usd_t
  col 27 → 'Rapeseed oil'     → rapeseed_oil_usd_t
  col 28 → 'Sunflower oil'    → sunflower_oil_usd_t
  col 25 → 'Soybean oil'      → soybean_oil_usd_t
  col 22 → 'Palm oil'         → palm_oil_usd_t
  col 58 → 'DAP'              → dap_fertilizer_usd_t  (удобрение)
  col 60 → 'Urea'             → urea_fertilizer_usd_t (удобрение)

Покрытие: 1990–2026, ежемесячно + среднегодовые агрегаты.
"""

import requests
import pandas as pd
import io
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "18675f1d1639c7a34d463f59263ba0a2-0050012025/"
    "related/CMO-Historical-Data-Monthly.xlsx"
)

# Строки в файле (0-индексация, подтверждено диагностикой)
COMMODITY_ROW = 4   # строка с названиями товаров
UNITS_ROW     = 5   # строка с единицами измерения
DATA_START    = 6   # первая строка с данными

START_YEAR = 1990

# Точные маппинги: номер столбца → итоговое имя
# Подтверждены из вывода 02_diagnose.py
COLUMN_MAP = {
    37: "wheat_hrw_usd_t",       # Wheat, US HRW - твёрдая пшеница (ближе к казахстанской)
    36: "wheat_srw_usd_t",       # Wheat, US SRW - мягкая пшеница
    29: "barley_usd_t",          # Barley
    30: "maize_usd_t",           # Maize
    27: "rapeseed_oil_usd_t",    # Rapeseed oil
    28: "sunflower_oil_usd_t",   # Sunflower oil
    25: "soybean_oil_usd_t",     # Soybean oil (индикатор рынка масличных)
    22: "palm_oil_usd_t",        # Palm oil (индикатор мирового рынка масел)
    58: "dap_fertilizer_usd_t",  # DAP - удобрение, важный фактор затрат
    60: "urea_fertilizer_usd_t", # Urea - удобрение
}


def verify_url() -> bool:
    try:
        resp = requests.head(PINK_SHEET_URL, timeout=15, allow_redirects=True)
        if resp.status_code < 400:
            print(f"  ✅ Pink Sheet доступен (HTTP {resp.status_code})")
            return True
        print(f"  ❌ HTTP {resp.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Недоступен: {e}")
        return False


def download_excel() -> pd.DataFrame:
    print(f"  Скачивание файла...")
    resp = requests.get(PINK_SHEET_URL, timeout=60)
    resp.raise_for_status()
    xls = pd.ExcelFile(io.BytesIO(resp.content))
    print(f"  Листы: {xls.sheet_names}")
    raw = pd.read_excel(xls, sheet_name="Monthly Prices", header=None)
    print(f"  Размер листа: {raw.shape}")
    return raw


def validate_columns(raw: pd.DataFrame) -> bool:
    """Проверяет что нужные колонки на своих местах."""
    print("\n  Проверка колонок...")
    all_ok = True
    for col_idx, col_name in COLUMN_MAP.items():
        actual = str(raw.iloc[COMMODITY_ROW, col_idx]).strip()
        unit   = str(raw.iloc[UNITS_ROW,    col_idx]).strip()
        # Проверяем что хотя бы одно ключевое слово совпадает
        key_check = any(
            kw in actual.lower()
            for kw in col_name.split("_")[:2]  # первые два слова имени
        )
        status = "✅" if key_check else "⚠️ "
        print(f"  {status} col {col_idx:2d}: '{actual}' {unit} → {col_name}")
        if not key_check:
            all_ok = False
    return all_ok


def parse_monthly(raw: pd.DataFrame) -> pd.DataFrame:
    """Извлекает месячные данные для всех целевых колонок."""
    data = raw.iloc[DATA_START:].copy().reset_index(drop=True)

    # Столбец 0 - период вида "1960M01"
    period_series = data.iloc[:, 0].astype(str).str.strip()

    records = []
    for idx, row in data.iterrows():
        period = str(row.iloc[0]).strip()

        # Парсим год и месяц из "1960M01"
        if len(period) < 4 or not period[:4].isdigit():
            continue
        year = int(period[:4])
        if year < START_YEAR:
            continue

        month_part = period[4:].replace("M", "").strip()
        month = int(month_part) if month_part.isdigit() else None

        rec = {"period": period, "year": year, "month": month}
        for col_idx, col_name in COLUMN_MAP.items():
            val = row.iloc[col_idx]
            # "…" и пустые значения → NaN
            try:
                rec[col_name] = float(val)
            except (ValueError, TypeError):
                rec[col_name] = None

        records.append(rec)

    df = pd.DataFrame(records)
    df["source"] = "WorldBank_PinkSheet"
    return df


def aggregate_annual(df_monthly: pd.DataFrame) -> pd.DataFrame:
    """Считает среднегодовые цены (среднее по 12 месяцам)."""
    price_cols = [c for c in df_monthly.columns
                  if c not in ["period", "year", "month", "source"]]
    annual = (
        df_monthly.groupby("year")[price_cols]
        .mean()
        .reset_index()
    )
    annual["source"] = "WorldBank_PinkSheet_annual"

    # Количество месяцев с данными (для контроля качества)
    count = df_monthly.groupby("year")["month"].count().reset_index()
    count.columns = ["year", "months_count"]
    annual = annual.merge(count, on="year", how="left")

    return annual


def print_summary(df_monthly: pd.DataFrame, df_annual: pd.DataFrame):
    price_cols = [c for c in df_annual.columns
                  if c not in ["year", "source", "months_count"]]

    print(f"\n  {'='*52}")
    print(f"  Период месячных данных: "
          f"{df_monthly['year'].min()}–{df_monthly['year'].max()}")
    print(f"  Месячных строк: {len(df_monthly)}")
    print(f"  Годовых строк:  {len(df_annual)}")

    print(f"\n  Последние 3 года среднегодовых цен (USD/тонна):")
    last3 = df_annual.tail(3)[["year"] + price_cols]
    # Форматируем красиво
    for _, row in last3.iterrows():
        print(f"\n  {int(row['year'])}:")
        for col in price_cols:
            val = row[col]
            label = col.replace("_usd_t", "").replace("_", " ")
            if pd.notna(val):
                print(f"    {label:<28} {val:>8.1f} $/т")


def main():
    print("=" * 60)
    print("  Скрипт 02 - World Bank Pink Sheet")
    print("  Источник: thedocs.worldbank.org (CMO Monthly Excel)")
    print(f"  Период: {START_YEAR}–2026")
    print("=" * 60)

    if not verify_url():
        print("Завершение.")
        return

    raw = download_excel()

    # Проверяем структуру
    ok = validate_columns(raw)
    if not ok:
        print("\n  ⚠️  Некоторые колонки не прошли проверку.")
        print("  Запустите 02_diagnose.py и сообщите вывод для уточнения маппинга.")

    # Парсим месячные данные
    print("\n  Парсинг месячных данных...")
    df_monthly = parse_monthly(raw)
    print(f"  Получено {len(df_monthly)} месячных записей")

    if df_monthly.empty:
        print("  ❌ Данные не получены.")
        return

    # Сохраняем месячные
    monthly_path = os.path.join(OUTPUT_DIR, "02_prices_monthly.csv")
    df_monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    print(f"  💾 Месячные: {monthly_path}")

    # Агрегируем по годам
    df_annual = aggregate_annual(df_monthly)
    annual_path = os.path.join(OUTPUT_DIR, "02_worldbank_prices.csv")
    df_annual.to_csv(annual_path, index=False, encoding="utf-8-sig")
    print(f"  💾 Годовые:  {annual_path}")

    print_summary(df_monthly, df_annual)


if __name__ == "__main__":
    main()