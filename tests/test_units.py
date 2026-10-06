"""Юнит-тесты чистых функций пайплайна (без сети и без файлов данных)."""

import numpy as np
import pandas as pd
import pytest


# ---------- 12_district_coords ----------

@pytest.mark.parametrize("raw,key", [
    ("район им. Г.Мусрепова", "Г.Мусрепова"),
    ("г.а Косшы", "Косшы"),
    ("г.а.Косшы", "Косшы"),
    ("г.а. Кокшетау", "Кокшетау"),
    ("Рудный г.а.", "Рудный"),
    ("г.Костанай", "Костанай"),
    ("Айыртауский район", "Айыртауский"),
    ("район Шал акына", "Шал акына"),
    ("Аккольский", "Аккольский"),
])
def test_district_key(s12, raw, key):
    assert s12.district_key(raw) == key


@pytest.mark.parametrize("raw,expected", [
    ("г.а. Кокшетау", True), ("Рудный г.а.", True), ("г.Костанай", True),
    ("Аккольский", False), ("район Шал акына", False),
])
def test_is_city(s12, raw, expected):
    assert s12.is_city(raw) is expected


def test_in_region_rejects_wrong_oblast(s12):
    assert s12.in_region("Костанайская область", 53.2, 63.6)
    assert not s12.in_region("Костанайская область", 53.2, 71.4)  # это Акмолинская область


# ---------- 13_era5_districts ----------

def _raw_month(year, month, tp=0.001, pev=-0.002, t2m=283.15):
    return {"time": pd.Timestamp(year, month, 1), "t2m": t2m, "tp": tp, "pev": pev,
            "swvl1": 0.3, "swvl2": 0.3, "ssrd": 1.0e7, "region": "R", "district_key": "D"}


def test_convert_units_daily_rate_to_monthly_sum(s13):
    df = pd.DataFrame([_raw_month(2020, 2), _raw_month(2021, 2)])
    out = s13.convert_units(df)
    # 0.001 м/сут * 1000 * число дней: февраль 2020 = 29 дней, 2021 = 28
    assert out["precip_mm"].tolist() == pytest.approx([29.0, 28.0])
    assert out["pot_evap_mm"].tolist() == pytest.approx([58.0, 56.0])  # испарение берётся по модулю
    assert out["t2m_c"].tolist() == pytest.approx([10.0, 10.0])


def _monthly(years, precip=10.0):
    rows = []
    for y in years:
        for m in range(1, 13):
            rows.append({"region": "R", "district_key": "D", "year": y, "month": m,
                         "days": 30, "t2m_c": 10.0, "precip_mm": precip, "pot_evap_mm": 50.0,
                         "soil_water_l1": 0.3, "soil_water_l2": 0.3, "solar_mjm2": 100.0})
    return pd.DataFrame(rows)


def test_build_features_growing_season_sums(s13):
    f = s13.build_features(_monthly([2019, 2020]))
    row = f[f["year"] == 2020].iloc[0]
    assert row["gs_precip_mm"] == pytest.approx(60.0)       # апр-сен = 6 месяцев
    assert row["mayjul_precip_mm"] == pytest.approx(30.0)   # май-июль = 3 месяца
    assert row["gs_pot_evap_mm"] == pytest.approx(300.0)
    assert row["aridity_index"] == pytest.approx(60.0 / 300.0)


def test_cold_season_requires_previous_autumn(s13):
    f = s13.build_features(_monthly([2019, 2020])).set_index("year")
    assert np.isnan(f.loc[2019, "coldseason_precip_mm"])    # нет окт-дек 2018
    assert f.loc[2020, "coldseason_precip_mm"] == pytest.approx(60.0)  # окт-дек 2019 + янв-мар 2020


# ---------- 15_merge_districts ----------

def _series(years, yields):
    n = len(years)
    return pd.DataFrame({
        "region": ["R"] * n, "district_key": ["D"] * n, "crop": ["Пшеница"] * n,
        "year": years, "yield_kgha": yields, "area_ha": [1000.0] * n,
        "wheat_hrw_usd_t": [100.0 + y for y in years],
    })


def test_lags_are_calendar_based_not_positional(s15):
    out = s15.add_lags(_series([2000, 2001, 2003], [10.0, 20.0, 40.0])).set_index("year")
    assert out.loc[2001, "yield_kgha_lag1"] == 10.0
    assert np.isnan(out.loc[2003, "yield_kgha_lag1"])    # 2002 пропущен - не берём 2001
    assert out.loc[2003, "yield_kgha_lag2"] == 20.0
    assert out.loc[2003, "wheat_price_lag3"] == 100.0 + 2000


def test_lags_do_not_leak_current_year(s15):
    a = s15.add_lags(_series([2000, 2001, 2002], [10.0, 20.0, 30.0])).set_index("year")
    b = s15.add_lags(_series([2000, 2001, 2002], [10.0, 20.0, 9999.0])).set_index("year")
    lag_cols = [c for c in a.columns if "lag" in c or "roll" in c]
    pd.testing.assert_series_equal(a.loc[2002, lag_cols], b.loc[2002, lag_cols], check_names=False)


def test_rolling_mean_uses_only_past(s15):
    out = s15.add_lags(_series([2000, 2001, 2002, 2003], [10.0, 20.0, 30.0, 40.0])).set_index("year")
    assert out.loc[2003, "yield_kgha_roll3"] == pytest.approx(20.0)  # (10+20+30)/3, без 40


# ---------- 04_soilgrids ----------

def test_soilgrids_parser_applies_d_factor(s04):
    """Регрессия: поле называется d_factor, а не conversion_factor."""
    resp = {"properties": {"layers": [{
        "name": "phh2o",
        "unit_measure": {"d_factor": 10, "mapped_units": "pH*10"},
        "depths": [{"label": "0-5cm", "values": {"mean": 68}}],
    }]}}
    recs = s04.parse_soilgrids_response(resp, 52.0, 71.0)
    assert len(recs) == 1
    assert recs[0]["value"] == pytest.approx(6.8)
    assert recs[0]["value_raw"] == 68


def test_winter_is_december_before_sowing_not_after_harvest(s13):
    """Регрессия: winter_t2m_c брал декабрь того же года (после уборки) - признак из будущего."""
    df = _monthly([2019, 2020])
    df.loc[(df.year == 2019) & (df.month == 12), "t2m_c"] = -20.0   # декабрь ПЕРЕД сезоном 2020
    df.loc[(df.year == 2020) & df.month.isin([1, 2]), "t2m_c"] = -10.0
    df.loc[(df.year == 2020) & (df.month == 12), "t2m_c"] = +5.0    # декабрь ПОСЛЕ сезона 2020 - не учитывается
    f = s13.build_features(df).set_index("year")
    assert f.loc[2020, "winter_t2m_c"] == pytest.approx((-20.0 - 10.0 - 10.0) / 3)
    assert np.isnan(f.loc[2019, "winter_t2m_c"])                    # нет декабря 2018
