"""
Скрипт 03 — ERA5 климатические данные (Copernicus CDS)
========================================================
Источник: ECMWF ERA5-Land Monthly Means
Сайт:     https://cds.climate.copernicus.eu
Пакет:    pip install cdsapi xarray netcdf4

Стратегия загрузки:
  Данные скачиваются ПО ОДНОМУ ГОДУ за запрос (~1-2 МБ каждый).
  Это решает проблему разрыва соединения при загрузке большого файла.
  Уже скачанные годы пропускаются — можно прерывать и продолжать.

Покрытие:
  Зерновой пояс Казахстана (N55 S49 W60 E78)
  Период: 1991–2025, месячные агрегаты
"""

import os
import sys
import time
import pandas as pd
import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR  = "output"
CACHE_DIR   = os.path.join(OUTPUT_DIR, "era5_cache")  # папка для годовых NC файлов
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR,  exist_ok=True)

BBOX = {"north": 55.0, "south": 49.0, "west": 60.0, "east": 78.0}

VARIABLES = [
    "2m_temperature",
    "total_precipitation",
    "potential_evaporation",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "surface_solar_radiation_downwards",
]

DATASET    = "reanalysis-era5-land-monthly-means"
START_YEAR = 1991
END_YEAR   = 2025

# Переименование переменных ERA5 → понятные имена
VAR_RENAME = {
    "t2m":   "t2m_kelvin",
    "tp":    "precip_m",
    "pev":   "pot_evap_m",
    "swvl1": "soil_water_l1",
    "swvl2": "soil_water_l2",
    "ssrd":  "solar_rad_jm2",
}


# ─────────────────────────────────────────
# Загрузка по одному году
# ─────────────────────────────────────────

def download_year(client, year: int, nc_path: str) -> bool:
    """Скачивает один год ERA5 данных (~1-2 МБ)."""
    request = {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable":     VARIABLES,
        "year":         [str(year)],
        "month":        [f"{m:02d}" for m in range(1, 13)],
        "time":         ["00:00"],
        "area":         [BBOX["north"], BBOX["west"], BBOX["south"], BBOX["east"]],
        "data_format":  "netcdf_legacy",   # отдаёт чистый NC без ZIP-упаковки
        "download_format": "unarchived",   # дополнительная гарантия без архива
    }
    try:
        client.retrieve(DATASET, request, nc_path)
        return True
    except Exception as e:
        print(f"    Ошибка {year}: {e}")
        # Удаляем битый файл если он создался
        if os.path.exists(nc_path) and os.path.getsize(nc_path) < 1000:
            os.remove(nc_path)
        return False


def extract_nc_from_zip(zip_path: str) -> str:
    """
    CDS отдаёт ZIP-архив вместо прямого NC файла.
    Читает NC прямо из памяти — без извлечения на диск,
    что полностью обходит проблемы с путями на Windows.
    Перезаписывает ZIP файл содержимым NC и возвращает тот же путь.
    """
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zf:
        nc_names = [n for n in zf.namelist() if n.endswith(".nc")]
        if not nc_names:
            nc_names = zf.namelist()
        nc_name = nc_names[0]
        nc_bytes = zf.read(nc_name)  # читаем в память, не на диск

    # Перезаписываем ZIP содержимым NC прямо по тому же пути
    with open(zip_path, "wb") as f:
        f.write(nc_bytes)

    return zip_path


def is_zip(path: str) -> bool:
    """Проверяет является ли файл ZIP-архивом по сигнатуре."""
    with open(path, "rb") as f:
        return f.read(4) == b'PK\x03\x04'


def nc_to_df(nc_path: str, year: int) -> pd.DataFrame:
    """Читает NetCDF файл и возвращает DataFrame с месячными данными.
    Читает через BytesIO чтобы обойти проблему кириллицы/пробелов в пути на Windows."""
    import xarray as xr
    import io

    # Читаем файл в память как байты
    with open(nc_path, "rb") as f:
        raw = f.read()

    # Если это ZIP — распаковываем в памяти, не трогая диск
    if raw[:4] == b"PK":
        import zipfile
        print(f" (ZIP→NC)", end="")
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            nc_names = [n for n in zf.namelist() if n.endswith(".nc")]
            nc_name = nc_names[0] if nc_names else zf.namelist()[0]
            raw = zf.read(nc_name)
        # Сохраняем распакованный NC обратно (чтобы при повторном запуске не распаковывать)
        with open(nc_path, "wb") as f:
            f.write(raw)

    # Открываем xarray из памяти — путь к файлу не используется совсем
    ds = xr.open_dataset(io.BytesIO(raw), engine="scipy")
    # Пространственное среднее по региону
    df = ds.mean(dim=["latitude", "longitude"]).to_dataframe().reset_index()
    ds.close()

    # Переименовываем
    df = df.rename(columns={k: v for k, v in VAR_RENAME.items() if k in df.columns})

    # Извлекаем год и месяц (нужны ДО конвертации накопительных переменных —
    # см. ниже, коэффициент зависит от числа дней в конкретном месяце)
    time_col = next((c for c in df.columns if "time" in c.lower() or "valid" in c.lower()), None)
    if time_col:
        df["year"]  = pd.to_datetime(df[time_col]).dt.year
        df["month"] = pd.to_datetime(df[time_col]).dt.month
    else:
        df["year"]  = year
        df["month"] = range(1, len(df) + 1)

    # Конвертируем единицы.
    # ВАЖНО: для product_type="monthly_averaged_reanalysis" (см. запрос в
    # download_year выше) CDS отдаёт "накопительные" переменные —
    # total_precipitation, potential_evaporation, surface_solar_radiation_
    # downwards — не как сумму за месяц, а как СРЕДНЕСУТОЧНУЮ скорость за
    # месяц (m/day). Это задокументированная особенность ERA5/ERA5-Land:
    # https://confluence.ecmwf.int/pages/viewpage.action?pageId=197702790
    # ("tp [mm] = tp [m/day] * 1000 * N, где N — число дней в месяце").
    # Без умножения на N осадки получались ~в 30 раз меньше нормы
    # (обнаружено 2026-09-09: реальная норма для зернового пояса КЗ —
    # 300-400 мм/год, без этой поправки сумма выходила ~13 мм/год).
    import calendar
    days_in_month = df.apply(lambda r: calendar.monthrange(int(r["year"]), int(r["month"]))[1], axis=1)

    if "t2m_kelvin" in df.columns:
        df["t2m_celsius"] = (df["t2m_kelvin"] - 273.15).round(2)
    if "precip_m" in df.columns:
        df["precip_mm"] = (df["precip_m"] * 1000 * days_in_month).round(2)
    if "pot_evap_m" in df.columns:
        df["pot_evap_mm"] = (df["pot_evap_m"].abs() * 1000 * days_in_month).round(2)
    if "solar_rad_jm2" in df.columns:
        df["solar_rad_mjm2"] = (df["solar_rad_jm2"] * days_in_month / 1_000_000).round(3)

    df["source"] = "ERA5_real"
    return df


def collect_all_years() -> pd.DataFrame:
    """Скачивает все годы последовательно, пропускает уже скачанные."""
    try:
        import cdsapi
    except ImportError:
        print("  Установите: pip install cdsapi")
        return pd.DataFrame()

    client = cdsapi.Client()
    all_frames = []
    years = list(range(START_YEAR, END_YEAR + 1))
    total = len(years)

    print(f"\n  Загрузка {total} лет по одному году за раз...")
    print(f"  Уже скачанные годы будут пропущены автоматически.\n")

    failed_years = []

    for i, year in enumerate(years):
        nc_path = os.path.join(CACHE_DIR, f"era5_{year}.nc")

        # Пропускаем если файл уже есть и не пустой
        if os.path.exists(nc_path) and os.path.getsize(nc_path) > 10_000:
            print(f"  [{i+1:2d}/{total}] {year} — уже скачан ", end="")
            try:
                df_year = nc_to_df(nc_path, year)
                all_frames.append(df_year)
                print(f" ({len(df_year)} строк)")
            except Exception as e:
                print(f"  ошибка чтения: {e}, перескачиваем...")
                os.remove(nc_path)
                failed_years.append(year)
            continue

        print(f"  [{i+1:2d}/{total}] {year} — скачиваем...", end="", flush=True)
        success = download_year(client, year, nc_path)

        if success and os.path.exists(nc_path):
            try:
                df_year = nc_to_df(nc_path, year)
                all_frames.append(df_year)
                size_kb = os.path.getsize(nc_path) / 1024
                print(f" {size_kb:.0f} КБ, {len(df_year)} строк")
            except Exception as e:
                print(f"  ошибка чтения NC: {e}")
                failed_years.append(year)
        else:
            print(f" пропущен")
            failed_years.append(year)

        # Небольшая пауза между запросами
        if i < total - 1:
            time.sleep(2)

    if failed_years:
        print(f"\n   Не удалось скачать годы: {failed_years}")
        print(f"  Повторно запустите скрипт — они будут скачаны автоматически.")

    if all_frames:
        return pd.concat(all_frames, ignore_index=True)
    return pd.DataFrame()


# ─────────────────────────────────────────
# Синтетические данные (фолбэк)
# ─────────────────────────────────────────

def generate_synthetic(csv_path: str) -> pd.DataFrame:
    """Синтетические климатические данные по нормам зернового пояса Казахстана."""
    print("  Генерация синтетических данных...")
    np.random.seed(42)

    monthly_norms = {
        "t2m_c": [-15.2,-13.8,-5.4, 6.8,16.1,21.3,23.5,22.1,14.8, 4.6,-5.1,-12.3],
        "prec":  [  19,  16,  19,  25,  31,  36,  47,  34,  25,  21,  21,   22],
        "pet":   [   4,   7,  26,  62, 112, 143, 157, 131,  70,  29,   7,    3],
    }

    records = []
    for year in range(START_YEAR, END_YEAR + 1):
        warming = (year - 1991) * 0.03
        for month in range(1, 13):
            m = month - 1
            records.append({
                "year":         year,
                "month":        month,
                "t2m_celsius":  round(monthly_norms["t2m_c"][m] + warming + np.random.normal(0, 1.8), 2),
                "precip_mm":    round(max(0, monthly_norms["prec"][m] + np.random.normal(0, 8)), 1),
                "pot_evap_mm":  round(max(0, monthly_norms["pet"][m]  + np.random.normal(0, 12)), 1),
                "soil_water_l1": round(np.random.uniform(0.14, 0.34), 3),
                "soil_water_l2": round(np.random.uniform(0.18, 0.38), 3),
                "source":       "ERA5_synthetic",
            })

    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  Синтетика: {csv_path} ({len(df)} строк)")
    return df


# ─────────────────────────────────────────
# Агрегация по вегетационному сезону
# ─────────────────────────────────────────

def aggregate_growing_season(df: pd.DataFrame, out_path: str):
    """Апрель–Сентябрь: средние значения за вегетационный сезон."""
    gs = df[df["month"].between(4, 9)]
    num_cols = [c for c in gs.select_dtypes("number").columns
                if c not in ["year", "month"]]
    annual = gs.groupby("year")[num_cols].mean().reset_index()
    annual.columns = ["year"] + [f"gs_{c}" for c in num_cols]
    annual["source"] = df["source"].iloc[0] + "_gs"
    annual.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  Вегетационный сезон: {out_path} ({len(annual)} лет)")
    return annual


# ─────────────────────────────────────────
# Проверка конфигурации
# ─────────────────────────────────────────

def check_config() -> bool:
    if os.environ.get("CDSAPI_KEY") and os.environ.get("CDSAPI_URL"):
        print("  Конфигурация: переменные окружения")
        return True
    rc = os.path.join(os.path.expanduser("~"), ".cdsapirc")
    setup_hint = "см. README.md, раздел \"Настройка ERA5 (Скрипт 03)\""
    if not os.path.exists(rc):
        print(f"  Файл не найден: {rc}")
        print(f"     {setup_hint}")
        return False
    with open(rc, encoding="utf-8") as f:
        content = f.read()
    if "cds.climate.copernicus.eu/api" not in content or "key:" not in content:
        print(f"  Неверный формат .cdsapirc — {setup_hint}")
        return False
    for line in content.splitlines():
        if line.strip().startswith("key:"):
            token = line.split(":", 1)[1].strip()
            if token in ("", "<PERSONAL-ACCESS-TOKEN>", "ВАШ-ТОКЕН-ЗДЕСЬ"):
                print(f"  Токен не заполнен — {setup_hint}")
                return False
    print(f"  ~/.cdsapirc настроен корректно")
    return True


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────

def clear_bad_cache():
    """Удаляет файлы кэша которые остались повреждёнными (ZIP или слишком маленькие)."""
    cleared = 0
    if not os.path.exists(CACHE_DIR):
        return
    for fname in os.listdir(CACHE_DIR):
        fpath = os.path.join(CACHE_DIR, fname)
        if not fname.endswith(".nc"):
            continue
        size = os.path.getsize(fpath)
        if size < 10_000:
            os.remove(fpath)
            cleared += 1
            continue
        # Проверяем сигнатуру — NC должен начинаться с HDF5 или CDF
        with open(fpath, "rb") as f:
            sig = f.read(4)
        if sig[:2] == b"PK":   # это ZIP — повреждён
            os.remove(fpath)
            cleared += 1
    if cleared:
        print(f"   Удалено {cleared} повреждённых файлов кэша")


def main():
    print("=" * 60)
    print("  Скрипт 03 — ERA5 климатические данные")
    print("  Источник: cds.climate.copernicus.eu")
    print(f"  Период: {START_YEAR}–{END_YEAR} (по 1 году за запрос)")
    print("=" * 60)

    monthly_csv = os.path.join(OUTPUT_DIR, "03_era5_monthly.csv")
    gs_csv      = os.path.join(OUTPUT_DIR, "03_era5_climate.csv")
    synth_csv   = os.path.join(OUTPUT_DIR, "03_era5_synthetic.csv")
    synth_gs    = os.path.join(OUTPUT_DIR, "03_era5_synthetic_gs.csv")

    config_ok = check_config()

    if config_ok:
        print(f"\n  Режим: реальные данные ERA5")
        clear_bad_cache()
        print(f"  Кэш NC файлов: {CACHE_DIR}")
        print(f"  Совет: можно прерывать Ctrl+C — прогресс сохраняется!")
        try:
            df = collect_all_years()
            if not df.empty:
                df.to_csv(monthly_csv, index=False, encoding="utf-8-sig")
                print(f"\n  Месячные данные: {monthly_csv} ({len(df)} строк)")
                gs = aggregate_growing_season(df, gs_csv)
                print(f"\n  Готово! Период: {df['year'].min()}–{df['year'].max()}")
            else:
                print("  Данные не получены, переключение на синтетику...")
                df_s = generate_synthetic(synth_csv)
                aggregate_growing_season(df_s, synth_gs)
        except KeyboardInterrupt:
            print("\n\n   Прервано пользователем.")
            print(f"  Уже скачанные годы сохранены в: {CACHE_DIR}")
            print(f"  Повторно запустите скрипт — продолжит с места остановки.")
        except Exception as e:
            print(f"  Ошибка: {e}")
            print("  Переключение на синтетические данные...")
            df_s = generate_synthetic(synth_csv)
            aggregate_growing_season(df_s, synth_gs)
    else:
        print(f"\n  Режим: синтетические данные")
        df_s = generate_synthetic(synth_csv)
        aggregate_growing_season(df_s, synth_gs)


if __name__ == "__main__":
    main()