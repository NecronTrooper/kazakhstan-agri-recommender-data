"""
Скрипт 06 — Объединение всех датасетов в master_dataset.csv
=============================================================
Этот скрипт объединяет выходные файлы скриптов 01–05 в единый
датасет, готовый к обучению ML-моделей рекомендательной системы.

Структура итогового датасета:
  year, region, crop, area_ha, yield_kgha, production_ton,
  wheat_price_usd_t, maize_price_usd_t, ...,  (мировые цены)
  t2m_celsius, total_precip_mm, ...,           (климат)
  ph, soc, clay, sand, ...,                    (почва)
  yield_lag1, yield_lag2, price_lag1, ...      (лаговые переменные)
  yield_roll3, price_roll3                     (скользящие средние)
"""

import pandas as pd
import numpy as np
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
MASTER_PATH = os.path.join(OUTPUT_DIR, "master_dataset.csv")


CROP_MAP_RU_EN = {
    "Пшеница":                    "Wheat",
    "Пшеница яровая":             "Wheat",       # старое название синтетического fallback
    "Ячмень":                     "Barley",
    "Подсолнечник":               "Sunflower seed",
    "Рапс":                       "Rapeseed",
    "Кукуруза":                   "Maize",
    "Зерновые и бобовые (группа)": "Grains and legumes (group)",
    "Масличные (группа)":         "Oilseeds (group)",
}


def load_production() -> pd.DataFrame:
    """
    Загружает производственные данные с региональной разбивкой.
    05_kaz_stat.csv — единственный ожидаемый файл от 05_kaz_stat.py:
    либо реальные данные stat.gov.kz (source начинается с "stat_gov_kz"),
    либо синтетический fallback (source кончается на "FALLBACK_SYNTHETIC"),
    либо ручная выгрузка (source == "stat_gov_kz_manual_upload").
    Если файла нет вообще — откатываемся на национальные данные FAOSTAT
    (без региональной разбивки; лаговые/скользящие признаки по региону
    в этом случае не считаются, см. merge_all).
    """
    kaz_path = os.path.join(OUTPUT_DIR, "05_kaz_stat.csv")
    fao_path = os.path.join(OUTPUT_DIR, "01_faostat.csv")

    if os.path.exists(kaz_path):
        df = pd.read_csv(kaz_path)
        df = df[df["crop"].isin(CROP_MAP_RU_EN.keys())].copy()
        df["crop_en"] = df["crop"].map(CROP_MAP_RU_EN)
        sources = df["source"].unique().tolist()
        print(f"  Производство (05_kaz_stat.csv): {len(df)} строк, source={sources}")
        if any(str(s).endswith("FALLBACK_SYNTHETIC") for s in sources):
            print("   ВНИМАНИЕ: часть/все данные — синтетический fallback, не реальная статистика!")
        return df
    elif os.path.exists(fao_path):
        df = pd.read_csv(fao_path)
        print(f"  Производство (FAOSTAT, национальный уровень, БЕЗ регионов): {len(df)} строк")
        return df
    else:
        print("   Файлы производства не найдены — запустите 01_faostat.py и/или 05_kaz_stat.py")
        return pd.DataFrame()


def load_prices() -> pd.DataFrame:
    """Загружает мировые цены (World Bank Pink Sheet)."""
    path = os.path.join(OUTPUT_DIR, "02_worldbank_prices.csv")
    if not os.path.exists(path):
        print("   Файл цен не найден — запустите 02_worldbank_prices.py")
        return pd.DataFrame()

    df = pd.read_csv(path)
    price_cols = [c for c in df.columns if c.endswith("_usd_t")]
    df = df[["year"] + price_cols].dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    # Агрегируем по году (среднегодовые)
    df = df.groupby("year")[price_cols].mean().reset_index()
    print(f"  Цены (Pink Sheet): {len(df)} лет, {len(price_cols)} товаров")
    return df


def load_climate() -> pd.DataFrame:
    """Загружает климатические данные ERA5."""
    for fname in ["03_era5_climate.csv", "03_era5_synthetic.csv"]:
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path):
            df = pd.read_csv(path)
            # Агрегируем: вегетационный сезон апрель–сентябрь
            if "month" in df.columns:
                growing = df[df["month"].between(4, 9)]
                num_cols = growing.select_dtypes(include="number").columns.tolist()
                num_cols = [c for c in num_cols if c not in ["year", "month"]]
                annual = growing.groupby("year")[num_cols].mean().reset_index()
                annual.columns = [
                    f"gs_{c}" if c not in ["year"] else c
                    for c in annual.columns
                ]
            else:
                annual = df.groupby("year").mean(numeric_only=True).reset_index()
            print(f"  Климат ({fname}): {len(annual)} лет")
            return annual
    print("   Файл климата не найден — запустите 03_era5_climate.py")
    return pd.DataFrame()


def load_soil() -> pd.DataFrame:
    """Загружает почвенные данные SoilGrids."""
    path = os.path.join(OUTPUT_DIR, "04_soilgrids_wide.csv")
    if not os.path.exists(path):
        print("   Почвенные данные не найдены — запустите 04_soilgrids.py")
        return pd.DataFrame()

    df = pd.read_csv(path)
    # Берём среднее по всем точкам для слоя 0-5cm как региональную характеристику
    top_layer = df[df["depth"] == "0-5cm"] if "depth" in df.columns else df
    soil_cols = [c for c in top_layer.columns
                 if c not in ["lat", "lon", "depth", "source"]]
    soil_mean = top_layer[soil_cols].mean()
    print(f"  Почва (SoilGrids): {len(soil_cols)} свойств")
    return soil_mean


def series_group_keys(df: pd.DataFrame) -> list:
    """
    Ключи для группировки временных рядов: region+crop_en в норме, но при
    откате на национальный FAOSTAT (без разбивки по регионам) колонки
    "region"/"crop_en" могут отсутствовать — тогда группируем по тому, что
    есть ("crop" в FAOSTAT), а если и этого нет, лаги/скользящие средние
    просто не считаются (пустой список ключей обрабатывается вызывающим
    кодом).
    """
    for candidate in (["region", "crop_en"], ["crop_en"], ["crop"]):
        if all(c in df.columns for c in candidate):
            return candidate
    return []


def add_lag_features(df: pd.DataFrame, target_col: str, lags=(1, 2, 3)) -> pd.DataFrame:
    """Добавляет лаговые переменные для временного ряда."""
    keys = series_group_keys(df)
    if not keys:
        return df
    df = df.sort_values(keys + ["year"])
    grp = df.groupby(keys)
    for lag in lags:
        df[f"{target_col}_lag{lag}"] = grp[target_col].shift(lag)
    return df


def add_rolling_features(df: pd.DataFrame, target_col: str, windows=(3, 5)) -> pd.DataFrame:
    """Добавляет скользящие средние."""
    keys = series_group_keys(df)
    if not keys:
        return df
    df = df.sort_values(keys + ["year"])
    grp = df.groupby(keys)
    for w in windows:
        df[f"{target_col}_roll{w}"] = (
            grp[target_col].shift(1).rolling(w).mean().reset_index(0, drop=True)
        )
    return df


def merge_all() -> pd.DataFrame:
    """Объединяет все источники."""
    print("\n  Загрузка датасетов...")
    prod   = load_production()
    prices = load_prices()
    clim   = load_climate()
    soil   = load_soil()

    if prod.empty:
        print("  Нет производственных данных. Прерывание.")
        return pd.DataFrame()

    master = prod.copy()

    # Join цен по году
    if not prices.empty:
        master = master.merge(prices, on="year", how="left")
        print(f"  После join цен: {len(master)} строк")

    # Join климата по году
    if not clim.empty:
        master = master.merge(clim, on="year", how="left")
        print(f"  После join климата: {len(master)} строк")

    # Добавляем почву как константные признаки (статичны)
    if isinstance(soil, pd.Series) and not soil.empty:
        for prop, val in soil.items():
            master[f"soil_{prop}"] = val
        print(f"  Добавлены почвенные признаки: {len(soil)}")

    # Лаговые переменные для урожайности
    if "yield_kgha" in master.columns and "crop_en" in master.columns:
        master = add_lag_features(master, "yield_kgha", lags=(1, 2, 3))
        master = add_rolling_features(master, "yield_kgha", windows=(3, 5))

    # Лаговые переменные для цены пшеницы
    keys = series_group_keys(master)
    if "wheat_hrw_usd_t" in master.columns and keys:
        master = master.sort_values(keys + ["year"])
        for lag in (1, 2, 3):
            master[f"wheat_price_lag{lag}"] = (
                master.groupby(keys)["wheat_hrw_usd_t"].shift(lag)
            )

    if keys:
        master = master.sort_values(keys + ["year"]).reset_index(drop=True)
    else:
        master = master.sort_values(["year"]).reset_index(drop=True)
    return master


def main():
    print("=" * 55)
    print("  Скрипт 06 — Объединение датасетов")
    print("=" * 55)

    master = merge_all()

    if master.empty:
        print("  Итоговый датасет пуст.")
        return

    master.to_csv(MASTER_PATH, index=False, encoding="utf-8-sig")

    print(f"\n  {'='*45}")
    print(f"  Итоговый датасет: {MASTER_PATH}")
    print(f"  Строк:    {len(master)}")
    print(f"  Столбцов: {len(master.columns)}")
    print(f"  Период:   {master['year'].min()}–{master['year'].max()}")
    if "region" in master.columns:
        print(f"  Регионы:  {master['region'].nunique()}")
    if "crop" in master.columns:
        print(f"  Культуры: {master['crop'].nunique()}")

    missing = master.isnull().sum()
    missing = missing[missing > 0]
    if not missing.empty:
        print(f"\n  Пропуски (первые лаговые строки — норма):")
        for col, cnt in missing.items():
            print(f"    {col}: {cnt}")

    print(f"\n  Столбцы датасета:")
    for c in master.columns:
        print(f"    {c}")


if __name__ == "__main__":
    main()
