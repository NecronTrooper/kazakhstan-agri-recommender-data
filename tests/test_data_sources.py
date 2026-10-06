"""Инварианты исходных слоёв: FAOSTAT, World Bank, ERA5 (по районам), SoilGrids."""

import glob
import os

import numpy as np

from conftest import OUT


# ---------- FAOSTAT (01) ----------

def test_faostat_is_kazakhstan_not_estonia(faostat):
    """Регрессия: код страны 63 - Эстония, а не Казахстан."""
    assert faostat["country"].str.contains("Kazakhstan").all()


def test_faostat_wheat_area_realistic(faostat):
    w = faostat[(faostat["crop"] == "Wheat") & faostat["indicator"].str.startswith("Area")]
    assert len(w) > 20
    # реальная площадь пшеницы в КЗ - ~10-13 млн га (у Эстонии было ~130 тыс.)
    assert w["value"].between(5e6, 20e6).all()


# ---------- World Bank (02) ----------

def test_prices_years_contiguous_and_unique(prices):
    years = prices["year"].tolist()
    assert len(years) == len(set(years))
    assert years == list(range(min(years), max(years) + 1))


def test_prices_in_plausible_range(prices):
    assert prices["wheat_hrw_usd_t"].between(50, 600).all()
    assert prices["urea_fertilizer_usd_t"].dropna().between(50, 1500).all()


# ---------- ERA5 (03 / 13) ----------

def test_era5_cache_covers_all_years():
    files = glob.glob(os.path.join(OUT, "era5_cache", "era5_*.nc"))
    years = sorted(int(os.path.basename(f)[5:9]) for f in files)
    if not years:
        import pytest
        pytest.skip("нет кэша ERA5")
    assert years == list(range(years[0], years[-1] + 1)), "пропущены годы в кэше ERA5"
    assert all(os.path.getsize(f) > 10_000 for f in files)


def test_district_climate_ranges(climate):
    assert climate["gs_precip_mm"].between(40, 500).all()
    assert climate["gs_t2m_c"].between(8, 22).all()
    assert climate["junaug_t2m_c"].between(12, 30).all()
    assert climate["winter_t2m_c"].dropna().between(-30, 0).all()
    # ERA5-Land PET завышен относительно FAO, но у суши район-сезон лежит в 500-2000 мм
    assert climate["gs_pot_evap_mm"].dropna().between(500, 2000).all()


def test_precip_is_not_per_day_rate(climate):
    """Регрессия: без умножения на число дней осадки были ~13 мм/год."""
    assert climate.groupby("year")["gs_precip_mm"].mean().min() > 100


def test_known_drought_years_are_drier(climate):
    by_year = climate.groupby("year")["gs_precip_mm"].mean()
    assert by_year[2010] < by_year.median()
    assert by_year[2021] < by_year.median()


def test_no_constant_climate_columns(climate):
    num = climate.drop(columns=["year"]).select_dtypes("number")
    assert (num.std() > 0).all()


def test_districts_have_distinct_climate(climate):
    p = climate.pivot_table(index="year", columns=["region", "district_key"], values="gs_precip_mm")
    assert p.T.duplicated().sum() == 0, "два района с идентичным рядом осадков"


def test_pet_anomaly_is_masked_not_kept(climate):
    """Озёрные ячейки ERA5-Land дают PET в 2-4 раза выше нормы: такие районы должны быть NaN."""
    pet_cols = ["gs_pot_evap_mm", "junaug_pot_evap_mm", "aridity_index", "mayjul_aridity", "water_balance_mm"]
    flagged = climate[climate["pet_suspect"] == 1]
    assert flagged[pet_cols].isna().all().all()
    assert len(flagged) < 0.05 * len(climate)


def test_climate_features_complete_except_known_gaps(climate):
    pet_cols = ["gs_pot_evap_mm", "junaug_pot_evap_mm", "aridity_index", "mayjul_aridity", "water_balance_mm"]
    # coldseason_precip_mm и winter_t2m_c требуют декабря предыдущего года -> пусты в первый год (1991)
    prev_year = ["coldseason_precip_mm", "winter_t2m_c"]
    ok = climate[climate["pet_suspect"] == 0]
    assert ok.drop(columns=prev_year).notna().all().all()
    other = climate.drop(columns=pet_cols + prev_year)
    assert other.notna().all().all()
    assert climate.loc[climate["year"] > climate["year"].min(), "winter_t2m_c"].notna().all()


# ---------- SoilGrids (04 / 14) ----------

def test_soil_grid_units_applied(soil_grid):
    """Регрессия: не применялся d_factor - pH был 65-80, гранулометрия ~1000."""
    assert soil_grid["phh2o"].between(4, 9).all()
    tex = soil_grid["clay"] + soil_grid["sand"] + soil_grid["silt"]
    assert tex.between(95, 105).all()


def test_district_soil_ranges(soil):
    for depth in ("0_30", "30_60"):
        assert soil[f"soil_phh2o_{depth}"].between(4, 9).all()
        assert (soil[f"soil_soc_{depth}"] > 0).all()
        tex = soil[f"soil_clay_{depth}"] + soil[f"soil_sand_{depth}"] + soil[f"soil_silt_{depth}"]
        assert tex.between(90, 110).all()


def test_soil_differs_between_districts(soil):
    assert soil["soil_clay_0_30"].nunique() > 20
    assert not np.isclose(soil["soil_soc_0_30"].std(), 0)


def test_every_district_with_coordinates_has_soil(coords, soil):
    have = set(zip(soil["region"], soil["district_key"]))
    need = set(zip(coords["region"], coords["district_key"]))
    assert need <= have, need - have
