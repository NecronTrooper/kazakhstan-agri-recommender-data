"""Инварианты районного master-датасета (master_dataset_districts.csv)."""

import numpy as np
import pandas as pd

from conftest import read_csv

KEY = ["region", "district_key", "crop", "year"]
CLIMATE_COLS = ["gs_precip_mm", "gs_t2m_c", "mayjul_precip_mm"]


def test_key_is_unique(districts):
    assert not districts.duplicated(KEY).any()


def test_shape_and_coverage(districts):
    assert districts["region"].nunique() == 3
    assert districts.groupby("region")["district_key"].nunique().min() >= 12
    assert districts["year"].min() >= 1990 and districts["year"].max() <= 2026
    assert len(districts) > 5000


def test_no_oblast_total_rows(districts):
    assert not districts["district"].str.contains("итого").any()


def test_yield_is_physically_possible(districts):
    y = districts["yield_kgha"].dropna()
    assert (y > 0).all(), "нулевая/отрицательная урожайность должна быть NaN"
    assert (y <= 8000).all(), "урожайность > 8000 кг/га - ошибка единиц (было 1.6 млн)"


def test_outlier_flag_matches_nan(districts):
    flagged = districts[districts["yield_outlier"] == 1]
    assert flagged["yield_kgha"].isna().all()


def test_area_suspect_is_a_minority(districts):
    # сейчас ~7%; резкий рост означает сломанный парсер единиц в 05
    assert districts["area_suspect"].mean() < 0.12


def test_published_yield_matches_production_over_area(districts):
    """На чистых строках урожайность из источника ~ сбор/площадь (допуск 10%)."""
    x = districts[(districts["area_suspect"] == 0) & (districts["is_group"] == 0)
                  & (districts["yield_derived"] == 0) & (districts["area_ha"] > 50)
                  & districts["yield_kgha"].notna() & districts["production_ton"].notna()]
    ratio = x["yield_kgha"] / (x["production_ton"] * 1000 / x["area_ha"])
    share_ok = ratio.between(0.9, 1.1).mean()
    assert share_ok > 0.80, f"доля согласованных строк {share_ok:.2f}"


def test_wheat_districts_sum_to_oblast_total(districts, regional):
    """Сумма пшеницы по районам (с городами) = областной итог из 05, допуск 2%."""
    obl = regional[regional["crop"] == "Пшеница"].set_index(["region", "year"])["production_ton"]
    s = (districts[districts["crop"] == "Пшеница"]
         .groupby(["region", "year"])["production_ton"].sum())
    m = pd.concat([obl.rename("obl"), s.rename("dist")], axis=1).dropna()
    m = m[m["obl"] > 0]
    ratio = m["dist"] / m["obl"]
    bad = ratio[(ratio < 0.98) | (ratio > 1.02)]
    assert len(bad) <= 2, f"расхождение >2% в {len(bad)} (регион,год): {bad.to_dict()}"


def test_districts_do_not_share_coordinates(districts):
    """Регрессия: геокодер подставил Енбекшильдерскому координаты Биржан сал."""
    c = districts.dropna(subset=["lat", "lon"]).drop_duplicates(["region", "district_key"])
    dup = c[c.duplicated(["region", "lat", "lon"], keep=False)]
    assert dup.empty, dup[["region", "district_key", "lat", "lon"]].to_string()


def test_coordinates_inside_own_region(districts, s12):
    c = districts.dropna(subset=["lat", "lon"]).drop_duplicates(["region", "district_key"])
    for _, r in c.iterrows():
        assert s12.in_region(r["region"], r["lat"], r["lon"]), (r["region"], r["district_key"])


def test_climate_present_except_known_gaps(districts):
    """Климата нет только для 1990 года и для районов без валидных координат."""
    miss = districts[districts[CLIMATE_COLS].isna().any(axis=1)]
    no_coords = miss["lat"].isna()
    first_year = miss["year"] == 1990
    assert (no_coords | first_year).all(), miss.loc[~(no_coords | first_year), KEY].head()


def test_soil_present_except_districts_without_coordinates(districts):
    miss = districts[districts["soil_phh2o_0_30"].isna()]
    assert miss["lat"].isna().all()


def test_lags_use_only_previous_years(districts):
    """lag1 = урожайность того же (район, культура) за год-1, а не соседняя строка."""
    ref = districts.set_index(KEY)["yield_kgha"]
    sample = districts[districts["yield_kgha_lag1"].notna()].sample(300, random_state=0)
    idx = pd.MultiIndex.from_arrays(
        [sample["region"], sample["district_key"], sample["crop"], sample["year"] - 1])
    expected = ref.reindex(idx).values
    assert np.allclose(sample["yield_kgha_lag1"].values, expected, equal_nan=True)


def test_lag_is_nan_when_previous_year_missing(districts):
    have = set(map(tuple, districts[KEY].values))
    row = districts[districts["yield_kgha_lag1"].isna()]
    gap = row[[(r, d, c, y - 1) not in have for r, d, c, y in
               zip(row["region"], row["district_key"], row["crop"], row["year"])]]
    assert gap["yield_kgha_lag1"].isna().all()
    assert len(gap) > 0


def test_group_rows_flagged(districts):
    groups = districts["crop"].str.contains("группа")
    assert (districts.loc[groups, "is_group"] == 1).all()
    assert (districts.loc[~groups, "is_group"] == 0).all()


# ---------- рыночный слой (цены производителей, 2022-2025) ----------

PRICE_COLS = ["price_harvest_kzt_t", "price_postharvest_kzt_t", "price_year_mean_kzt_t",
              "price_harvest_lag1_kzt_t", "price_postharvest_lag1_kzt_t",
              "price_harvest_yoy", "price_postharvest_yoy", "price_ratio_sunflower_wheat"]


def test_no_prices_before_archive_starts(districts):
    """Архив stat.gov.kz начинается с 2022-10: до 2022 года цен быть не должно."""
    early = districts[districts["year"] < 2022]
    assert early[PRICE_COLS[:3]].isna().all().all()


def test_lag1_price_not_available_in_first_price_year(districts):
    assert districts.loc[districts["year"] == 2022, "price_postharvest_lag1_kzt_t"].isna().all()


def test_group_rows_have_no_prices(districts):
    assert districts.loc[districts["is_group"] == 1, "price_harvest_kzt_t"].isna().all()


def test_prices_in_range(districts):
    p = districts["price_postharvest_kzt_t"].dropna()
    assert len(p) > 300
    assert p.between(30_000, 300_000).all()
    ratio = districts["price_ratio_sunflower_wheat"].dropna()
    assert ratio.between(0.8, 4).all()


def test_price_lag1_is_previous_year_value(districts):
    ref = districts.drop_duplicates(["region", "crop", "year"]).set_index(["region", "crop", "year"])
    x = districts[districts["price_postharvest_lag1_kzt_t"].notna()].drop_duplicates(["region", "crop", "year"])
    idx = pd.MultiIndex.from_arrays([x["region"], x["crop"], x["year"] - 1])
    assert np.allclose(x["price_postharvest_lag1_kzt_t"].values,
                       ref["price_postharvest_kzt_t"].reindex(idx).values)


def test_yoy_requires_enough_months(districts):
    y = districts[districts["price_postharvest_yoy"].notna()]
    assert (y["price_postharvest_months"] == 2).all() and (y["price_postharvest_lag1_months"] == 2).all()
    h = districts[districts["price_harvest_yoy"].notna()]
    assert (h["price_harvest_months"] >= 2).all() and (h["price_harvest_lag1_months"] >= 2).all()


def test_2022_2025_subset_matches_master(districts):
    sub = read_csv("master_dataset_districts_2022_2025.csv")
    expected = districts[districts["year"].between(2022, 2025)]
    assert len(sub) == len(expected)
    assert sub["year"].between(2022, 2025).all()
    assert list(sub.columns) == list(districts.columns)
