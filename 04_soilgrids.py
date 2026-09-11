"""
Скрипт 04 - SoilGrids почвенные данные (ISRIC)
================================================
Источник: SoilGrids v2.0 - ISRIC World Soil Information
Сайт:     https://soilgrids.org
API:      https://rest.isric.org/soilgrids/v2.0/docs
Лицензия: CC BY 4.0

Как найдено:
  SoilGrids - глобальная база данных свойств почв с разрешением 250м,
  созданная ISRIC с применением методов машинного обучения. Обнаружена
  как стандартный источник почвенных данных в статьях по прогнозированию
  урожайности (Feature engineering remains critical - Section V обзора).
  API активен и документирован: rest.isric.org/soilgrids/v2.0/docs.
  Лимит - 5 запросов в минуту (fair use policy ISRIC).

Покрытие:
  Сетка точек по зерновому поясу Казахстана (Акмолинская, Костанайская,
  Северо-Казахстанская области). Данные статичны (обновляются раз в ~3 года).

Свойства почв:
  phh2o  - pH (H₂O)
  soc    - органический углерод (dg/kg)
  bdod   - объёмная плотность (cg/cm³)
  clay   - содержание глины (g/kg)
  sand   - содержание песка (g/kg)
  silt   - содержание ила (g/kg)
  cec    - ёмкость катионного обмена (mmol(c)/kg)
  nitrogen - общий азот (cg/kg)
"""

import requests
import pandas as pd
import time
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

API_BASE = "https://rest.isric.org/soilgrids/v2.0/properties/query"

SOIL_PROPERTIES = [
    "phh2o", "soc", "bdod", "clay",
    "sand", "silt", "cec", "nitrogen",
]

# Глубины почвенного профиля (стандарт GlobalSoilMap)
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm"]

# Сетка точек по зерновому поясу Казахстана
# Шаг 2° (~200 км) - достаточно для регионального анализа
SAMPLE_POINTS = []
for lat in [50.0, 51.5, 53.0, 54.5]:
    for lon in [62.0, 65.0, 68.0, 71.0, 74.0]:
        SAMPLE_POINTS.append({"lat": lat, "lon": lon})


def fetch_soilgrids_point(lat: float, lon: float) -> dict:
    """Запрос свойств почвы в одной точке."""
    params = {
        "lon": lon,
        "lat": lat,
        "property": SOIL_PROPERTIES,
        "depth": DEPTHS,
        "value": ["mean"],
    }

    resp = requests.get(API_BASE, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_soilgrids_response(data: dict, lat: float, lon: float) -> list:
    """Парсит JSON-ответ SoilGrids в список записей."""
    records = []
    try:
        layers = data["properties"]["layers"]
        for layer in layers:
            prop_name = layer["name"]
            unit_factor = layer.get("unit_measure", {}).get("mapped_units", "")
            # ВНИМАНИЕ: поле в реальном ответе API называется "d_factor", а не
            # "conversion_factor" — из-за этого делитель всегда молча
            # откатывался на дефолт 1, и, например, pH (mapped_units="pH*10")
            # сохранялся как есть (72 вместо 7.2). Обнаружено 2026-09-09
            # прямым запросом к rest.isric.org/soilgrids/v2.0/properties/query.
            conv_factor = layer.get("unit_measure", {}).get("d_factor", 1)

            for depth_info in layer.get("depths", []):
                depth_label = depth_info["label"]
                mean_val = depth_info["values"].get("mean")
                if mean_val is not None:
                    records.append({
                        "lat":       lat,
                        "lon":       lon,
                        "property":  prop_name,
                        "depth":     depth_label,
                        "value_raw": mean_val,
                        "value":     mean_val / conv_factor if conv_factor else mean_val,
                        "unit":      unit_factor,
                        "source":    "SoilGrids_v2",
                    })
    except (KeyError, TypeError) as e:
        print(f"     Ошибка парсинга [{lat},{lon}]: {e}")
    return records


def verify_api() -> bool:
    """Проверка доступности SoilGrids API."""
    test_params = {
        "lon": 71.4,
        "lat": 51.1,
        "property": ["phh2o"],
        "depth": ["0-5cm"],
        "value": ["mean"],
    }
    try:
        resp = requests.get(API_BASE, params=test_params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        layers = data.get("properties", {}).get("layers", [])
        val = layers[0]["depths"][0]["values"].get("mean") if layers else None
        print(f"  SoilGrids API доступен. pH (0-5cm, Астана): {val}")
        return True
    except Exception as e:
        print(f"  SoilGrids API недоступен: {e}")
        return False


def collect_soilgrids(points: list) -> pd.DataFrame:
    """Собирает данные по всем точкам с соблюдением rate limit."""
    all_records = []
    total = len(points)

    for i, point in enumerate(points):
        lat, lon = point["lat"], point["lon"]
        print(f"  Точка {i+1}/{total}: [{lat}, {lon}]")
        try:
            data = fetch_soilgrids_point(lat, lon)
            records = parse_soilgrids_response(data, lat, lon)
            all_records.extend(records)
            print(f"    → {len(records)} значений")
        except requests.exceptions.HTTPError as e:
            print(f"     HTTP {e.response.status_code}: пропуск")
        except Exception as e:
            print(f"     Ошибка: {e}")

        # Rate limit: 5 запросов / минута
        if i < total - 1:
            time.sleep(13)

    return pd.DataFrame(all_records)


def pivot_soilgrids(df: pd.DataFrame) -> pd.DataFrame:
    """Преобразует длинный формат в широкий (одна строка = одна точка × глубина)."""
    if df.empty:
        return df
    pivot = df.pivot_table(
        index=["lat", "lon", "depth"],
        columns="property",
        values="value",
        aggfunc="mean",
    ).reset_index()
    pivot["source"] = "SoilGrids_v2"
    return pivot


def main():
    print("=" * 55)
    print("  Скрипт 04 - SoilGrids почвенные данные")
    print("  Источник: rest.isric.org/soilgrids/v2.0")
    print(f"  Точек: {len(SAMPLE_POINTS)}")
    print("=" * 55)

    if not verify_api():
        print("  Завершение: API недоступен.")
        return

    print(f"\n  Сбор данных по {len(SAMPLE_POINTS)} точкам...")
    print("  (rate limit: 5 запросов/мин - займёт ~5 минут)")

    df_long = collect_soilgrids(SAMPLE_POINTS)

    if df_long.empty:
        print("  Данные не получены.")
        return

    # Сохраняем длинный формат
    long_path = os.path.join(OUTPUT_DIR, "04_soilgrids_long.csv")
    df_long.to_csv(long_path, index=False, encoding="utf-8-sig")

    # Сохраняем широкий формат (удобен для ML)
    df_wide = pivot_soilgrids(df_long)
    wide_path = os.path.join(OUTPUT_DIR, "04_soilgrids_wide.csv")
    df_wide.to_csv(wide_path, index=False, encoding="utf-8-sig")

    print(f"\n  Длинный формат: {long_path} ({len(df_long)} строк)")
    print(f"  Широкий формат: {wide_path} ({len(df_wide)} строк)")
    print(f"  Свойства: {df_long['property'].unique().tolist()}")
    print(f"  Глубины: {df_long['depth'].unique().tolist()}")
    print(f"  Точек с данными: {df_long[['lat','lon']].drop_duplicates().shape[0]}")


if __name__ == "__main__":
    main()
