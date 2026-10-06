"""
Скрипт 13 - Климат ERA5-Land на уровне районов
===============================================
Берёт уже скачанные скриптом 03 годовые NetCDF (output/era5_cache/*.nc).
В них сохранена вся сетка 0.1 градуса по зерновому поясу (усреднение по bbox
делается уже после чтения), поэтому повторная загрузка из CDS не нужна.

Для каждого района (координаты - из 12_district_coords.csv) берётся среднее по
окну +-WINDOW градусов вокруг центроида (~5x5 ячеек ERA5-Land, ~40x40 км) -
устойчивее одного пикселя, но не размывает район до климата всего пояса.

Выход:
  output/13_era5_districts_monthly.csv  - (район, год, месяц) x переменные
  output/13_era5_districts_features.csv - (район, год) x агрономические признаки

Единицы: tp, pev, ssrd в monthly_averaged_reanalysis - среднесуточная скорость,
поэтому умножаются на число дней месяца (см. комментарий в 03_era5_climate.py).
"""

import calendar
import glob
import io
import os
import sys

import numpy as np
import pandas as pd
import xarray as xr

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
CACHE_DIR = os.path.join(OUTPUT_DIR, "era5_cache")
WINDOW = 0.2          # градусов в каждую сторону от центроида
PET_SUSPECT_FACTOR = 1.8  # испарение района > 1.8 x медианы по всем районам за год -> недостоверно
MAX_EDGE_GAP = 0.15   # если центроид дальше этого от границы bbox - предупреждение

VAR_RENAME = {"t2m": "t2m_kelvin", "tp": "precip_m", "pev": "pot_evap_m",
              "swvl1": "soil_water_l1", "swvl2": "soil_water_l2", "ssrd": "solar_rad_jm2"}


def read_year(path: str) -> xr.Dataset:
    # Через BytesIO: netCDF4 на Windows не открывает пути с кириллицей
    with open(path, "rb") as f:
        raw = f.read()
    return xr.open_dataset(io.BytesIO(raw), engine="scipy").load()


def monthly_for_districts(ds: xr.Dataset, coords: pd.DataFrame) -> pd.DataFrame:
    lat_min, lat_max = float(ds.latitude.min()), float(ds.latitude.max())
    lon_min, lon_max = float(ds.longitude.min()), float(ds.longitude.max())
    frames = []
    for _, c in coords.iterrows():
        if not (lat_min - MAX_EDGE_GAP <= c.lat <= lat_max + MAX_EDGE_GAP
                and lon_min - MAX_EDGE_GAP <= c.lon <= lon_max + MAX_EDGE_GAP):
            print(f"  ВНЕ ПОКРЫТИЯ ERA5: {c.region} / {c.district_key} ({c.lat}, {c.lon})")
            continue
        sub = ds.sel(latitude=slice(c.lat + WINDOW, c.lat - WINDOW),
                     longitude=slice(c.lon - WINDOW, c.lon + WINDOW))
        if sub.latitude.size == 0 or sub.longitude.size == 0:
            sub = ds.sel(latitude=c.lat, longitude=c.lon, method="nearest")
            df = sub.to_dataframe().reset_index()
        else:
            df = sub.mean(dim=["latitude", "longitude"]).to_dataframe().reset_index()
        df["region"], df["district_key"] = c.region, c.district_key
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def convert_units(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={k: v for k, v in VAR_RENAME.items() if k in df.columns})
    t = pd.to_datetime(df["time"])
    df["year"], df["month"] = t.dt.year, t.dt.month
    dim = np.array([calendar.monthrange(y, m)[1] for y, m in zip(df.year, df.month)])
    df["t2m_c"] = df["t2m_kelvin"] - 273.15
    df["precip_mm"] = df["precip_m"] * 1000 * dim
    df["pot_evap_mm"] = df["pot_evap_m"].abs() * 1000 * dim
    df["solar_mjm2"] = df["solar_rad_jm2"] * dim / 1e6
    df["days"] = dim
    keep = ["region", "district_key", "year", "month", "days", "t2m_c", "precip_mm",
            "pot_evap_mm", "soil_water_l1", "soil_water_l2", "solar_mjm2"]
    return df[keep]


def build_features(m: pd.DataFrame) -> pd.DataFrame:
    """Агрономические признаки (район, год). Год = год уборки урожая."""
    g = ["region", "district_key"]
    m = m.sort_values(g + ["year", "month"]).copy()
    # Влага холодного периода (окт прошлого года - мар текущего) - запас влаги в почве к посеву
    m["season_year"] = np.where(m.month >= 10, m.year + 1, m.year)

    def agg(mask, col, how, name):
        s = m[mask].groupby(g + ["year"])[col].agg(how).rename(name)
        return s

    parts = [
        agg(m.month.between(4, 9), "t2m_c", "mean", "gs_t2m_c"),
        agg(m.month.between(4, 9), "precip_mm", "sum", "gs_precip_mm"),
        agg(m.month.between(4, 9), "pot_evap_mm", "sum", "gs_pot_evap_mm"),
        agg(m.month.between(4, 9), "solar_mjm2", "sum", "gs_solar_mjm2"),
        agg(m.month.between(5, 7), "precip_mm", "sum", "mayjul_precip_mm"),
        agg(m.month.between(5, 7), "t2m_c", "mean", "mayjul_t2m_c"),
        agg(m.month.between(6, 8), "t2m_c", "mean", "junaug_t2m_c"),
        agg(m.month.between(6, 8), "pot_evap_mm", "sum", "junaug_pot_evap_mm"),
        agg(m.month == 5, "soil_water_l1", "mean", "may_soil_water_l1"),
        agg(m.month == 5, "soil_water_l2", "mean", "may_soil_water_l2"),
        agg(m.month == 6, "soil_water_l1", "mean", "jun_soil_water_l1"),
        agg(m.month == 7, "soil_water_l1", "mean", "jul_soil_water_l1"),
        agg(m.month == 7, "soil_water_l2", "mean", "jul_soil_water_l2"),
        agg(m.month == 6, "precip_mm", "sum", "jun_precip_mm"),
        agg(m.month == 7, "precip_mm", "sum", "jul_precip_mm"),
    ]
    # Градусо-дни выше 5 C (по месячным средним - грубая аппроксимация)
    gdd = m[m.month.between(4, 9)].assign(gdd=lambda x: np.clip(x.t2m_c - 5, 0, None) * x.days)
    parts.append(gdd.groupby(g + ["year"])["gdd"].sum().rename("gs_gdd5"))

    f = pd.concat(parts, axis=1).reset_index()

    # Холодный период: окт (год-1) .. мар (год) -> привязан к году уборки
    cold = m[(m.month >= 10) | (m.month <= 3)].groupby(g + ["season_year"])["precip_mm"].agg(["sum", "count"])
    cold = cold[cold["count"] == 6]["sum"].rename("coldseason_precip_mm").reset_index()
    cold = cold.rename(columns={"season_year": "year"})

    # Зима перед посевом года Y: декабрь Y-1 + январь и февраль Y (по season_year). Раньше считалось
    # по календарному году и захватывало декабрь Y, то есть ПОСЛЕ уборки - признак из будущего.
    winter = m[m.month.isin([12, 1, 2])].groupby(g + ["season_year"])["t2m_c"].agg(["mean", "count"])
    winter = winter[winter["count"] == 3]["mean"].rename("winter_t2m_c").reset_index()
    winter = winter.rename(columns={"season_year": "year"})
    f = f.merge(cold, on=g + ["year"], how="left").merge(winter, on=g + ["year"], how="left")

    f["aridity_index"] = f["gs_precip_mm"] / f["gs_pot_evap_mm"]            # P/PET, меньше = суше
    f["mayjul_aridity"] = f["mayjul_precip_mm"] / m[m.month.between(5, 7)].groupby(g + ["year"])["pot_evap_mm"].sum().reindex(
        pd.MultiIndex.from_frame(f[g + ["year"]])).values
    f["water_balance_mm"] = f["gs_precip_mm"] - f["gs_pot_evap_mm"]

    # Потенциальное испарение ERA5-Land над озёрами/мокрыми ячейками в 2-4 раза выше, чем над
    # сушей (20-40 против ~9 мм/сут в июне). Район, чьё окно целиком попало в озёрную зону
    # (М.Жумабаева: ~3250 мм за сезон при норме ~1300), получает завышенное испарение, и
    # производные признаки становятся недостоверными - лучше NaN, чем ложная "засушливость".
    med = f.groupby("year")["gs_pot_evap_mm"].transform("median")
    f["pet_suspect"] = (f["gs_pot_evap_mm"] > PET_SUSPECT_FACTOR * med).astype(int)
    pet_cols = ["gs_pot_evap_mm", "junaug_pot_evap_mm", "aridity_index", "mayjul_aridity", "water_balance_mm"]
    f.loc[f["pet_suspect"] == 1, pet_cols] = np.nan
    return f


def main():
    coords = pd.read_csv(os.path.join(OUTPUT_DIR, "12_district_coords.csv"))
    # район может встречаться под разными написаниями (Косшы) - координаты на ключ
    coords_u = coords.drop_duplicates(["region", "district_key"])
    paths = sorted(glob.glob(os.path.join(CACHE_DIR, "era5_*.nc")))
    print(f"Районов: {len(coords_u)}, файлов ERA5: {len(paths)}")

    frames = []
    for p in paths:
        ds = read_year(p)
        frames.append(convert_units(monthly_for_districts(ds, coords_u)))
        ds.close()
        print(f"  {os.path.basename(p)} ok")
    monthly = pd.concat(frames, ignore_index=True)
    monthly.round(4).to_csv(os.path.join(OUTPUT_DIR, "13_era5_districts_monthly.csv"), index=False, encoding="utf-8")

    feats = build_features(monthly)
    feats = feats.round(4)
    feats.to_csv(os.path.join(OUTPUT_DIR, "13_era5_districts_features.csv"), index=False, encoding="utf-8")
    print(f"monthly: {monthly.shape}, features: {feats.shape}")
    print(feats.groupby("region")[["gs_precip_mm", "gs_t2m_c", "aridity_index"]].mean().round(2))


if __name__ == "__main__":
    main()
