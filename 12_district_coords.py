"""
Скрипт 12 - Координаты районов (геокодирование через OSM Nominatim)
====================================================================
Нужен для районного климата (13) и почвы (14): в 05_kaz_stat_districts.csv
есть только названия районов, координат нет.

Метод: Nominatim отдаёт центроид административной границы района. Для каждого
результата проверяется, что точка попала в bbox своей области (защита от
омонимов: "Есильский" есть и в Акмолинской, и в Северо-Казахстанской областях).
Результаты кэшируются в output/district_coords_cache.json - повторный запуск
не ходит в сеть.

Выход: output/12_district_coords.csv  (region, district, district_key, lat, lon)
"""

import json
import os
import re
import sys
import time

import pandas as pd
import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
CACHE_PATH = os.path.join(OUTPUT_DIR, "district_coords_cache.json")
OUT_PATH = os.path.join(OUTPUT_DIR, "12_district_coords.csv")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "kz-agri-research/1.0 (academic dataset; kumarov.akezhan@gmail.com)"}

# Грубые bbox областей (lat_min, lat_max, lon_min, lon_max) - только для sanity-check
REGION_BBOX = {
    "Акмолинская область":          (49.0, 53.8, 65.0, 75.5),
    "Костанайская область":         (49.0, 54.8, 59.5, 68.5),
    "Северо-Казахстанская область": (52.8, 55.7, 65.5, 73.5),
}


def district_key(raw: str) -> str:
    """Нормализует название района (убирает 'район', 'г.а.' и пр., склеивает дубли)."""
    s = raw.strip()
    s = re.sub(r"\bрайон\b", "", s, flags=re.I).strip()
    s = re.sub(r"\bг\.\s*а\.?", "", s, flags=re.I)
    s = re.sub(r"^г\.\s*", "", s)
    s = re.sub(r"^им\.\s*", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s


def is_city(raw: str) -> bool:
    return bool(re.search(r"(^г\.|г\.а\.?|\(итого\)|^город)", raw, flags=re.I)) or raw.endswith("г.а.")


# Ручные уточнения запросов там, где сокращённое название в stat.gov.kz не геокодируется
QUERY_OVERRIDES = {
    "Г.Мусрепова": "район Габита Мусрепова, Северо-Казахстанская область, Казахстан",
}


def build_query(region: str, raw: str, key: str) -> str:
    if "(итого)" in raw:
        return ""
    if key in QUERY_OVERRIDES:
        return QUERY_OVERRIDES[key]
    if is_city(raw):
        return f"{key}, {region}, Казахстан"
    return f"{key} район, {region}, Казахстан"


def geocode(query: str):
    r = requests.get(
        NOMINATIM,
        params={"q": query, "format": "json", "limit": 1, "accept-language": "ru"},
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    js = r.json()
    if not js:
        return None
    return float(js[0]["lat"]), float(js[0]["lon"]), js[0].get("display_name", "")


def in_region(region: str, lat: float, lon: float) -> bool:
    a, b, c, d = REGION_BBOX[region]
    return a <= lat <= b and c <= lon <= d


def main():
    d = pd.read_csv(os.path.join(OUTPUT_DIR, "05_kaz_stat_districts.csv"))
    pairs = d[["region", "district"]].drop_duplicates().sort_values(["region", "district"])

    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    rows = []
    for _, r in pairs.iterrows():
        region, raw = r["region"], r["district"]
        key = district_key(raw)
        q = build_query(region, raw, key)
        if not q:
            continue
        ck = f"{region}|{key}"
        if ck not in cache:
            try:
                res = geocode(q)
            except Exception as e:
                print(f"  ОШИБКА {q}: {e}")
                res = None
            cache[ck] = res
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
            time.sleep(1.1)  # политика Nominatim: <= 1 запрос/сек
        res = cache[ck]
        if not res:
            print(f"  НЕ НАЙДЕНО: {q}")
            continue
        lat, lon, name = res
        if not in_region(region, lat, lon):
            print(f"  ВНЕ ОБЛАСТИ: {q} -> {lat:.2f},{lon:.2f} ({name})")
            continue
        rows.append({"region": region, "district": raw, "district_key": key,
                     "lat": round(lat, 4), "lon": round(lon, 4)})

    out = pd.DataFrame(rows)
    # Геокодер при неудаче может вернуть соседний объект: два РАЗНЫХ района с идентичными
    # координатами - признак такой подмены (обнаружено: "Енбекшильдерский" -> "Биржан сал").
    # Такие районы исключаются: чужой климат/почва хуже, чем честный NaN.
    key = out.drop_duplicates(["region", "district_key"])
    dup = key[key.duplicated(["region", "lat", "lon"], keep=False)]
    if len(dup):
        # оставляем тот, чьё название совпадает с display_name в кэше
        drop_keys = []
        for (_, _, _), grp in dup.groupby(["region", "lat", "lon"]):
            for _, r in grp.iterrows():
                res = cache.get(f"{r.region}|{r.district_key}")
                if not res or r.district_key.split()[0].lower() not in res[2].lower():
                    drop_keys.append((r.region, r.district_key))
        for reg, k in drop_keys:
            print(f"  ИСКЛЮЧЁН (координаты совпали с другим районом): {reg} / {k}")
        out = out[~out.set_index(["region", "district_key"]).index.isin(drop_keys)]
    out.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"Сохранено {len(out)} записей -> {OUT_PATH}")
    print(f"Уникальных (регион, район): {out[['region','district_key']].drop_duplicates().shape[0]}")


if __name__ == "__main__":
    main()
