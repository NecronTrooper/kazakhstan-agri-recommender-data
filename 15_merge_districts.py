"""
Скрипт 15 - Районный master-датасет (урожайность + климат района + почва района + рынок)
=======================================================================================
Объединяет:
  05_kaz_stat_districts.csv      - площадь/валовой сбор/урожайность по районам (1990-2025)
  13_era5_districts_features.csv - климат ERA5-Land по району и году   (скрипт 13)
  14_soilgrids_districts.csv     - почва SoilGrids по району            (скрипт 14)
  master_dataset.csv             - мировые цены и индексы цен по годам (скрипт 06)

Гранулярность строки: (область, район, культура, год).
Выход: output/master_dataset_districts.csv

Лаги и скользящие средние считаются ВНУТРИ (район, культура) строго по прошлым
годам - в признаки текущего года данные текущего года не попадают.
"""

import importlib.util
import os
import sys

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
OUT_PATH = os.path.join(OUTPUT_DIR, "master_dataset_districts.csv")
OUT_PATH_PRICES = os.path.join(OUTPUT_DIR, "master_dataset_districts_2022_2025.csv")
PRICE_FIRST_YEAR, PRICE_LAST_YEAR = 2022, 2025   # цены производителей есть с 2022-10; урожай - по 2025

_spec = importlib.util.spec_from_file_location("coords12", "12_district_coords.py")
c12 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c12)

CROP_EN = {
    "Пшеница": "Wheat", "Ячмень": "Barley", "Кукуруза": "Maize", "Подсолнечник": "Sunflower seed",
    "Зерновые и бобовые (группа)": "Grains and legumes (group)", "Масличные (группа)": "Oilseeds (group)",
}
# Столбцы master_dataset.csv, зависящие только от года (одинаковы для всех областей/культур)
YEAR_LEVEL_COLS = [
    "wheat_hrw_usd_t", "wheat_srw_usd_t", "barley_usd_t", "maize_usd_t",
    "rapeseed_oil_usd_t", "sunflower_oil_usd_t", "soybean_oil_usd_t", "palm_oil_usd_t",
    "dap_fertilizer_usd_t", "urea_fertilizer_usd_t",
    "price_idx_agriculture_total_yoy_pct", "price_idx_crop_production_total_yoy_pct",
    "price_idx_grain_crops_group_yoy_pct", "price_idx_oilseed_crops_group_yoy_pct",
    "price_idx_agriculture_total_level", "price_idx_crop_production_total_level",
    "price_idx_grain_crops_group_level", "price_idx_oilseed_crops_group_level",
]


def add_lags(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["region", "district_key", "crop", "year"]).reset_index(drop=True)
    g = ["region", "district_key", "crop"]

    def shifted(col, k):
        # shift по календарному году, а не по позиции строки: пропущенный год -> NaN
        s = df.set_index(g + ["year"])[col]
        idx = pd.MultiIndex.from_arrays([df[x] for x in g] + [df["year"] - k])
        return s.reindex(idx).values

    for k in (1, 2, 3):
        df[f"yield_kgha_lag{k}"] = shifted("yield_kgha", k)
    prev = np.column_stack([shifted("yield_kgha", k) for k in range(1, 6)])
    df["yield_kgha_roll3"] = np.nanmean(prev[:, :3], axis=1)
    df["yield_kgha_roll5"] = np.nanmean(prev, axis=1)
    df["area_ha_lag1"] = shifted("area_ha", 1)
    # Район относительно своей области в предыдущем году - устойчивое "качество района"
    reg_mean = df.groupby(["region", "crop", "year"])["yield_kgha"].transform("mean")
    df["_regm"] = reg_mean
    s = df.drop_duplicates(["region", "crop", "year"]).set_index(["region", "crop", "year"])["_regm"]
    idx = pd.MultiIndex.from_arrays([df["region"], df["crop"], df["year"] - 1])
    df["region_crop_yield_lag1"] = s.reindex(idx).values
    df["yield_rel_region_lag1"] = df["yield_kgha_lag1"] / df["region_crop_yield_lag1"]
    df = df.drop(columns="_regm")

    # wheat_price_lagk = мировая цена пшеницы k лет назад
    price = df.drop_duplicates("year").set_index("year")["wheat_hrw_usd_t"]
    for k in (1, 2, 3):
        df[f"wheat_price_lag{k}"] = (df["year"] - k).map(price).values
    return df


def add_prices(d: pd.DataFrame) -> pd.DataFrame:
    """Региональные цены производителей (скрипт 16) по ключу (область, культура, год).

    Цены есть только с 2022-10, поэтому до 2022 года столбцы пустые. Групповые строки
    («Зерновые и бобовые», «Масличные») цены не получают - у них нет одной культуры.
    Цена сезона уборки (авг-окт) года Y известна только ПОСЛЕ посева года Y; для задач
    прогноза на момент посева используется price_harvest_lag1_kzt_t (прошлый сезон).
    """
    path = os.path.join(OUTPUT_DIR, "16_producer_prices_annual.csv")
    if not os.path.exists(path):
        print("  ВНИМАНИЕ: нет 16_producer_prices_annual.csv - рыночный слой не добавлен")
        return d
    a = pd.read_csv(path)
    key = ["region", "crop", "year"]
    cur = a.rename(columns={
        "price_harvest_aug_oct_kzt_t": "price_harvest_kzt_t",
        "n_harvest_months": "price_harvest_months",
        "price_mean_kzt_t": "price_year_mean_kzt_t",
        "n_months": "price_year_months",
        "price_nov_dec_kzt_t": "price_postharvest_kzt_t",
        "n_nov_dec_months": "price_postharvest_months",
    })[key + ["price_harvest_kzt_t", "price_harvest_months", "price_postharvest_kzt_t",
              "price_postharvest_months", "price_year_mean_kzt_t", "price_year_months"]]
    d = d.merge(cur, on=key, how="left")

    # Прошлый сезон (год-1): цена, известная на момент посева текущего года
    prev = cur.assign(year=cur["year"] + 1).rename(columns={
        "price_harvest_kzt_t": "price_harvest_lag1_kzt_t", "price_harvest_months": "price_harvest_lag1_months",
        "price_postharvest_kzt_t": "price_postharvest_lag1_kzt_t",
        "price_postharvest_months": "price_postharvest_lag1_months",
    })[key + ["price_harvest_lag1_kzt_t", "price_harvest_lag1_months",
              "price_postharvest_lag1_kzt_t", "price_postharvest_lag1_months"]]
    d = d.merge(prev, on=key, how="left")

    # Изменение к прошлому сезону: цена уборки - только если в обоих сезонах >= 2 месяцев из 3;
    # послеуборочная - если есть оба месяца (ноя и дек) в обоих годах
    ok = (d["price_harvest_months"] >= 2) & (d["price_harvest_lag1_months"] >= 2)
    d["price_harvest_yoy"] = np.where(ok, d["price_harvest_kzt_t"] / d["price_harvest_lag1_kzt_t"] - 1, np.nan)
    ok2 = (d["price_postharvest_months"] == 2) & (d["price_postharvest_lag1_months"] == 2)
    d["price_postharvest_yoy"] = np.where(
        ok2, d["price_postharvest_kzt_t"] / d["price_postharvest_lag1_kzt_t"] - 1, np.nan)

    # Соотношение цен подсолнечник/пшеница (послеуборочное окно) в регионе и году - сигнал для выбора культуры
    ref = cur.pivot_table(index=["region", "year"], columns="crop", values="price_postharvest_kzt_t")
    if {"Подсолнечник", "Пшеница"} <= set(ref.columns):
        ratio = (ref["Подсолнечник"] / ref["Пшеница"]).rename("price_ratio_sunflower_wheat").reset_index()
        d = d.merge(ratio, on=["region", "year"], how="left")
    return d


def main():
    d = pd.read_csv(os.path.join(OUTPUT_DIR, "05_kaz_stat_districts.csv"))
    d = d[~d["district"].str.contains("итого")].copy()
    d["district_key"] = d["district"].map(c12.district_key)
    n0 = len(d)
    d = d.drop_duplicates(["region", "district_key", "crop", "year"])  # Косшы под двумя написаниями
    print(f"Строк районных данных: {n0} -> {len(d)} (убраны дубли написаний)")

    d["crop_en"] = d["crop"].map(CROP_EN)
    d["is_group"] = d["source"].eq("stat_gov_kz_real_group").astype(int)
    d["is_city"] = d["district"].map(c12.is_city).astype(int)

    calc = d["production_ton"] * 1000 / d["area_ha"]
    fill = d["yield_kgha"].isna() & calc.replace([np.inf, -np.inf], np.nan).notna()
    d["yield_derived"] = fill.astype(int)
    d.loc[fill, "yield_kgha"] = calc[fill].round(1)
    print(f"Урожайность восстановлена из сбор/площадь: {int(fill.sum())} строк")

    # Флаг подозрительной площади: в источнике единицы измерения иногда меняются внутри ряда
    # (тыс. га -> га), детектор в 05 ловит не все случаи. Признак: площадь в >20 раз
    # отличается от медианы того же (район, культура), либо урожайность из источника
    # расходится с сбор/площадь более чем в 3 раза (или менее чем в 0.1).
    med = d.groupby(["region", "district_key", "crop"])["area_ha"].transform("median")
    ratio_med = d["area_ha"] / med
    ratio_pub = d["yield_kgha"] * d["area_ha"] / (d["production_ton"] * 1000)
    d["area_suspect"] = ((ratio_med < 1 / 20) | (ratio_med > 20) | (ratio_pub > 3) | (ratio_pub < 0.1)).astype(int)
    # Восстановленную из площади урожайность убираем там, где площадь подозрительна
    drop_der = (d["yield_derived"] == 1) & (d["area_suspect"] == 1)
    d.loc[drop_der, "yield_kgha"] = np.nan
    print(f"Подозрительная площадь (area_suspect): {int(d['area_suspect'].sum())} строк; "
          f"восстановленная урожайность отброшена: {int(drop_der.sum())}")

    # Санитарная очистка цели: отрицательные/нулевые значения, физически невозможные
    # (>8000 кг/га для зерновых/масличных на богаре) и восстановленные по микроскопической площади
    bad = (d["yield_kgha"] <= 0) | (d["yield_kgha"] > 8000) | ((d["yield_derived"] == 1) & (d["area_ha"] < 50))
    d["yield_outlier"] = bad.astype(int)
    d.loc[bad, "yield_kgha"] = np.nan
    print(f"Урожайность обнулена как некорректная (<=0, >8000 или из площади <50 га): {int(bad.sum())} строк")

    coords = pd.read_csv(os.path.join(OUTPUT_DIR, "12_district_coords.csv")).drop_duplicates(["region", "district_key"])
    d = d.merge(coords[["region", "district_key", "lat", "lon"]], on=["region", "district_key"], how="left")

    clim = pd.read_csv(os.path.join(OUTPUT_DIR, "13_era5_districts_features.csv"))
    d = d.merge(clim, on=["region", "district_key", "year"], how="left")

    soil_path = os.path.join(OUTPUT_DIR, "14_soilgrids_districts.csv")
    if os.path.exists(soil_path):
        soil = pd.read_csv(soil_path).drop(columns=["lat", "lon"])
        d = d.merge(soil, on=["region", "district_key"], how="left")
    else:
        print("  ВНИМАНИЕ: нет 14_soilgrids_districts.csv - почва не добавлена")

    master = pd.read_csv(os.path.join(OUTPUT_DIR, "master_dataset.csv"))
    yearly = master.groupby("year")[YEAR_LEVEL_COLS].first().reset_index()
    d = d.merge(yearly, on="year", how="left")

    d = add_lags(d)
    d = add_prices(d)
    d.to_csv(OUT_PATH, index=False, encoding="utf-8")

    sub = d[d["year"].between(PRICE_FIRST_YEAR, PRICE_LAST_YEAR)]
    sub.to_csv(OUT_PATH_PRICES, index=False, encoding="utf-8")
    print(f"Подмножество с рыночным слоем {PRICE_FIRST_YEAR}-{PRICE_LAST_YEAR}: {len(sub)} строк -> {OUT_PATH_PRICES}")

    print(f"\nИтог: {d.shape[0]} строк x {d.shape[1]} столбцов -> {OUT_PATH}")
    print(f"Районов: {d.groupby(['region','district_key']).ngroups}")
    print(f"Без климата (нет ERA5): {int(d['gs_precip_mm'].isna().sum())} строк "
          f"(1990 - до начала ERA5-кэша, плюс районы вне покрытия)")
    if "soil_phh2o_0_30" in d:
        print(f"Без почвы: {int(d['soil_phh2o_0_30'].isna().sum())} строк")
    ok = d[(d.is_group == 0) & d.yield_kgha.notna()]
    print(f"Пригодно для моделирования (отдельная культура, есть yield): {len(ok)} строк")


if __name__ == "__main__":
    main()
