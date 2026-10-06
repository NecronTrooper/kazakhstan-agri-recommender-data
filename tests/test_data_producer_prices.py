"""Региональные цены производителей stat.gov.kz (скрипт 16)."""

import re

import pandas as pd
import pytest

TARGET = ["Акмолинская область", "Костанайская область", "Северо-Казахстанская область"]


def test_spot_check_against_source_sheet(prices_monthly):
    """Значения из листа 5 выпуска за сентябрь 2026 (проверены глазами по исходному файлу).
    Фиксируют правильную привязку столбцов к регионам: СКО = 80223, а 81207 - это Павлодарская."""
    s = prices_monthly[(prices_monthly["year"] == 2026) & (prices_monthly["month"] == 9)
                       & (prices_monthly["crop_raw"] == "Пшеница")].set_index("region")["price_kzt_t"]
    assert s["Республика Казахстан"] == 84925
    assert s["Акмолинская область"] == 91262
    assert s["Костанайская область"] == 77879
    assert s["Северо-Казахстанская область"] == 80223
    assert s["Павлодарская область"] == 81207


def test_monthly_key_is_unique(prices_monthly):
    assert not prices_monthly.duplicated(["year", "month", "region", "crop_raw"]).any()


def test_no_missing_months(prices_monthly):
    ym = prices_monthly.drop_duplicates(["year", "month"])
    periods = pd.PeriodIndex.from_fields(year=ym["year"], month=ym["month"], freq="M").sort_values()
    full = pd.period_range(periods.min(), periods.max(), freq="M")
    assert list(periods) == list(full), f"нет выпусков: {sorted(set(full) - set(periods))}"
    assert len(full) >= 48


def test_wheat_present_every_month_for_target_regions(prices_monthly):
    w = prices_monthly[(prices_monthly["crop"] == "Пшеница") & prices_monthly["region"].isin(TARGET)]
    per_month = w.groupby(["year", "month"])["region"].nunique()
    assert (per_month == 3).all()


@pytest.mark.parametrize("crop,lo,hi", [("Пшеница", 40_000, 160_000),
                                         ("Ячмень", 30_000, 150_000),
                                         ("Подсолнечник", 80_000, 300_000)])
def test_prices_in_tenge_per_tonne_range(prices_monthly, crop, lo, hi):
    """Регрессия на единицы: тенге за тонну, а не за кг/центнер и не в тыс. тенге."""
    p = prices_monthly[(prices_monthly["crop"] == crop) & prices_monthly["region"].isin(TARGET)]["price_kzt_t"]
    assert len(p) > 20
    assert p.between(lo, hi).all(), p[~p.between(lo, hi)].tolist()


def test_annual_months_consistent(prices_annual, prices_monthly):
    assert (prices_annual["n_months"].between(1, 12)).all()
    m = prices_monthly[prices_monthly["crop"].notna()].groupby(["region", "crop", "year"])["month"].nunique()
    a = prices_annual.set_index(["region", "crop", "year"])["n_months"]
    assert (m.reindex(a.index) == a).all()


def test_harvest_price_only_from_aug_oct(prices_annual, prices_monthly):
    row = prices_annual[(prices_annual["region"] == "Костанайская область") & (prices_annual["crop"] == "Пшеница")
                        & (prices_annual["year"] == 2024)].iloc[0]
    m = prices_monthly[(prices_monthly["region"] == "Костанайская область") & (prices_monthly["crop"] == "Пшеница")
                       & (prices_monthly["year"] == 2024) & prices_monthly["month"].between(8, 10)]
    assert row["price_harvest_aug_oct_kzt_t"] == pytest.approx(m["price_kzt_t"].mean())


# ---------- юнит-тесты разбора ----------

@pytest.mark.parametrize("raw,expected", [
    ("Северо Казахстанская", "Северо-Казахстанская область"),
    ("Западно Казахстанская", "Западно-Казахстанская область"),
    ("Акмолинская", "Акмолинская область"),
    ("Республика Казахстан", "Республика Казахстан"),
    ("Костанайская область", "Костанайская область"),
])
def test_norm_region(s16, raw, expected):
    assert s16.norm_region(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Ячмень1)", "Ячмень"),
    ("семена подсолнечника", "Семена подсолнечника"),
    ("Кукуруза (маис)", "Кукуруза (маис)"),
    ("Пшеница,\nкроме пшеницы твердой", "Пшеница, кроме пшеницы твердой"),
])
def test_norm_crop(s16, raw, expected):
    assert s16.norm_crop(raw) == expected


def test_crop_map_covers_target_crops(s16):
    assert set(s16.CROP_MAP.values()) == {"Пшеница", "Ячмень", "Кукуруза", "Подсолнечник"}


def test_region_labels_are_normalised(prices_monthly):
    """Регрессия: в выпуске за июль 2026 заголовок был 'СевероКазахстанская' (слитно)."""
    regions = set(prices_monthly["region"])
    assert len(regions) <= 21, sorted(regions)
    assert not [r for r in regions if re.match(r"^(Северо|Западно|Восточно|Южно)(?!-)", r)], sorted(regions)


def test_s16_region_variants(s16):
    for raw in ("СевероКазахстанская", "Северо Казахстанская", "Северо-Казахстанская"):
        assert s16.norm_region(raw) == "Северо-Казахстанская область"
