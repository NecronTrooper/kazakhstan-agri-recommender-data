"""
Скрипт 14 - Почва SoilGrids на уровне районов
==============================================
Запрашивает SoilGrids v2.0 в точке центроида каждого района
(координаты - 12_district_coords.csv), используя fetch/parse из 04_soilgrids.py.
Ответы кэшируются в output/soilgrids_districts_cache.json: повторный запуск
дозапрашивает только недостающие районы (rate limit ISRIC - 5 запросов/мин).

Выход: output/14_soilgrids_districts.csv - одна строка на район; для каждого
свойства - значение пахотного слоя 0-30 см (взвешено по толщине слоёв 5/10/15 см)
и слоя 30-60 см.
"""

import importlib.util
import json
import os
import sys
import time

import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
CACHE_PATH = os.path.join(OUTPUT_DIR, "soilgrids_districts_cache.json")
OUT_PATH = os.path.join(OUTPUT_DIR, "14_soilgrids_districts.csv")

# Переиспользуем fetch/parse из 04 (имя файла начинается с цифры - обычный import невозможен)
_spec = importlib.util.spec_from_file_location("soilgrids04", "04_soilgrids.py")
sg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sg)

# Центроиды городов/озёр маскируются в SoilGrids - в этом случае ищем ближайшую точку с данными
PROBE_OFFSETS = [(0, 0), (0.1, 0), (-0.1, 0), (0, 0.1), (0, -0.1),
                 (0.2, 0.2), (-0.2, 0.2), (0.2, -0.2), (-0.2, -0.2)]

TOPSOIL_WEIGHTS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}


def main():
    coords = pd.read_csv(os.path.join(OUTPUT_DIR, "12_district_coords.csv"))
    coords = coords.drop_duplicates(["region", "district_key"]).reset_index(drop=True)

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    todo = [r for _, r in coords.iterrows() if f"{r.region}|{r.district_key}" not in cache]
    print(f"Районов: {len(coords)}, уже в кэше: {len(coords) - len(todo)}, к запросу: {len(todo)}")

    for i, r in enumerate(todo):
        key = f"{r.region}|{r.district_key}"
        print(f"  [{i+1}/{len(todo)}] {key} ({r.lat}, {r.lon})", flush=True)
        recs = []
        for dlat, dlon in PROBE_OFFSETS:
            try:
                data = sg.fetch_soilgrids_point(round(r.lat + dlat, 4), round(r.lon + dlon, 4))
                recs = sg.parse_soilgrids_response(data, round(r.lat + dlat, 4), round(r.lon + dlon, 4))
            except Exception as e:
                print(f"    ОШИБКА: {e}")
                recs = []
            if recs:
                if (dlat, dlon) != (0, 0):
                    print(f"    центроид без данных (город/вода), взята точка со сдвигом {dlat:+.2f},{dlon:+.2f}")
                break
            time.sleep(13)
        if recs:
            cache[key] = recs
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        else:
            print("    пустой ответ (точка вне суши/маски почв?)")
        if i < len(todo) - 1:
            time.sleep(13)

    rows = []
    for _, r in coords.iterrows():
        recs = cache.get(f"{r.region}|{r.district_key}")
        if not recs:
            continue
        df = pd.DataFrame(recs)
        row = {"region": r.region, "district_key": r.district_key, "lat": r.lat, "lon": r.lon}
        for prop, g in df.groupby("property"):
            top = g[g.depth.isin(TOPSOIL_WEIGHTS)]
            if len(top):
                w = top.depth.map(TOPSOIL_WEIGHTS)
                row[f"soil_{prop}_0_30"] = round((top.value * w).sum() / w.sum(), 3)
            deep = g[g.depth == "30-60cm"]
            if len(deep):
                row[f"soil_{prop}_30_60"] = round(float(deep.value.iloc[0]), 3)
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"Сохранено {len(out)} районов -> {OUT_PATH}")
    missing = len(coords) - len(out)
    if missing:
        print(f"  Без почвенных данных: {missing} (повторите запуск)")


if __name__ == "__main__":
    main()
