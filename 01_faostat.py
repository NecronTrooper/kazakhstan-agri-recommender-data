"""
Скрипт 01 — FAOSTAT (Bulk Download)
=====================================
Источник: FAO FAOSTAT — Agricultural Production Statistics
Сайт:     https://www.fao.org/faostat/en/#data/QCL
Bulk URL: https://bulks-faostat.fao.org/production/
 
Почему bulk вместо API:
  REST API (fenixservices.fao.org) периодически даёт 521 Server Error.
  Bulk-сервер (bulks-faostat.fao.org) — отдельная стабильная инфраструктура,
  используется официальным R-пакетом FAOSTAT и OWID (Our World in Data).
 
  FAOSTAT выпустил данные за 2024 год в декабре 2025:
  https://www.fao.org/statistics/highlights-archive/
    highlights-detail/agricultural-production-statistics-2010-2024/en
 
Покрытие:
  Казахстан (Area Code: 63), 1992–2024
  QCL: площадь сева, урожайность, валовой сбор
  PP1: цены производителей (USD/тонна)
"""
 
import requests
import pandas as pd
import zipfile
import io
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)
 
BULK_BASE = "https://bulks-faostat.fao.org/production"
BULK_URLS = {
    "QCL": f"{BULK_BASE}/Production_Crops_Livestock_E_All_Data_(Normalized).zip",
    "PP1": f"{BULK_BASE}/Prices_E_All_Data_(Normalized).zip",
}
 
# ВНИМАНИЕ: в первой версии скрипта здесь стоял код 63, который в
# реальном FAOSTAT bulk-файле соответствует Эстонии, а не Казахстану —
# проверено 2026-09-09 прямым чтением Production_Crops_Livestock_E_All_
# Data_(Normalized).csv (df[df["Area"].str.contains("Kazakh")] -> Area
# Code 108). Из-за этого весь 01_faostat.csv молча содержал данные
# Эстонии под меткой "Kazakhstan" (result["country"] = "Kazakhstan"
# ниже — жёстко прописанная строка, сама по себе ничего не проверяла).
KAZ_AREA_CODE = 108
 
CROP_CODES = {
    15:  "Wheat",
    44:  "Barley",
    56:  "Maize (corn)",
    267: "Sunflower seed",
    270: "Rapeseed",
}
 
ELEMENT_CODES_QCL = {
    5312: "Area harvested (ha)",
    5419: "Yield (kg/ha)",
    5510: "Production (t)",
}
 
ELEMENT_PP1 = 5532
START_YEAR = 1992
 
 
def download_and_extract(dataset_code: str) -> pd.DataFrame:
    url = BULK_URLS[dataset_code]
    print(f"  Скачивание {dataset_code}: {url}")
    print(f"  (файл ~50–150 МБ, может занять 1–3 минуты...)")
 
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()
 
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    chunks = []
    for chunk in resp.iter_content(chunk_size=1024 * 256):
        chunks.append(chunk)
        downloaded += len(chunk)
        if total:
            pct = downloaded / total * 100
            print(f"\r  Загрузка: {downloaded/1e6:.1f}/{total/1e6:.1f} МБ ({pct:.0f}%)", end="")
    print()
 
    content = b"".join(chunks)
    print(f"  Распаковка ZIP...")
 
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        csv_name = next(
            (n for n in zf.namelist() if "Normalized" in n and n.endswith(".csv")),
            zf.namelist()[0]
        )
        print(f"  Читаем: {csv_name}")
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, encoding="latin1", low_memory=False)
 
    print(f"  Загружено строк (весь мир): {len(df):,}")
    return df
 
 
def filter_kazakhstan(df: pd.DataFrame, dataset_code: str) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
 
    area_col = next((c for c in df.columns if "Area Code" in c and "M49" not in c), "Area Code")
    df = df[df[area_col] == KAZ_AREA_CODE].copy()

    if "Area" in df.columns and not df.empty:
        actual_names = df["Area"].unique().tolist()
        if not any("kazakh" in str(n).lower() for n in actual_names):
            raise ValueError(
                f"KAZ_AREA_CODE={KAZ_AREA_CODE} не соответствует Казахстану в этом "
                f"bulk-файле — по факту это {actual_names}. FAOSTAT переиспользует "
                f"Area Code между разными датасетами не всегда стабильно, поэтому "
                f"код здесь явно проверяется, а не берётся на веру."
            )

    print(f"  После фильтра Казахстан: {len(df)} строк")
 
    item_col = next((c for c in df.columns if c.startswith("Item Code") and "CPC" not in c), "Item Code")
    df = df[df[item_col].isin(CROP_CODES.keys())].copy()
    df["crop_name"] = df[item_col].map(CROP_CODES)
 
    elem_col = next((c for c in df.columns if c.startswith("Element Code")), "Element Code")
 
    if dataset_code == "QCL":
        df = df[df[elem_col].isin(ELEMENT_CODES_QCL.keys())].copy()
        df["indicator"] = df[elem_col].map(ELEMENT_CODES_QCL)
    elif dataset_code == "PP1":
        df = df[df[elem_col] == ELEMENT_PP1].copy()
        df["indicator"] = "Producer Price (USD/t)"
 
    year_col = "Year" if "Year" in df.columns else [c for c in df.columns if c.startswith("Year")][0]
    df = df[df[year_col] >= START_YEAR].copy()
    df = df.rename(columns={year_col: "year"})
 
    value_col = "Value"
    unit_col  = "Unit" if "Unit" in df.columns else None
    flag_col  = "Flag" if "Flag" in df.columns else None
 
    out_cols = {"year": "year", "crop_name": "crop", "indicator": "indicator", value_col: "value"}
    if unit_col: out_cols[unit_col] = "unit"
    if flag_col: out_cols[flag_col] = "flag"
 
    result = df[list(out_cols.keys())].rename(columns=out_cols).copy()
    result["country"] = "Kazakhstan"
    result["source"]  = f"FAOSTAT_{dataset_code}"
    result["year"]    = result["year"].astype(int)
    result["value"]   = pd.to_numeric(result["value"], errors="coerce")
    result = result.dropna(subset=["value"])
    return result
 
 
def verify_bulk_server() -> bool:
    url = BULK_URLS["QCL"]
    try:
        resp = requests.head(url, timeout=15, allow_redirects=True)
        if resp.status_code < 400:
            size_mb = int(resp.headers.get("content-length", 0)) / 1e6
            print(f"  Bulk-сервер доступен (HTTP {resp.status_code}, ~{size_mb:.0f} МБ)")
            return True
        print(f"  HTTP {resp.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Bulk-сервер недоступен: {e}")
        return False
 
 
def main():
    print("=" * 60)
    print("  Скрипт 01 — FAOSTAT (Bulk Download)")
    print("  Источник: bulks-faostat.fao.org/production/")
    print(f"  Данные: 1992–2024 (QCL + PP1), Казахстан")
    print("=" * 60)
 
    print("\n  Проверка bulk-сервера...")
    if not verify_bulk_server():
        print("\n  Bulk-сервер недоступен. Скачайте вручную:")
        print(f"    {BULK_URLS['QCL']}")
        print("  Положите CSV в input/QCL_Normalized.csv и повторите запуск.")
        return
 
    frames = []
 
    print("\n  [1/2] QCL — урожайность, площади, сбор")
    try:
        raw_qcl = download_and_extract("QCL")
        qcl = filter_kazakhstan(raw_qcl, "QCL")
        frames.append(qcl)
        print(f"  QCL: {len(qcl)} записей")
        print(f"     Культуры: {qcl['crop'].unique().tolist()}")
        print(f"     Период:   {qcl['year'].min()}–{qcl['year'].max()}")
    except Exception as e:
        print(f"  Ошибка QCL: {e}")
 
    print("\n  [2/2] PP1 — цены производителей")
    try:
        raw_pp1 = download_and_extract("PP1")
        pp1 = filter_kazakhstan(raw_pp1, "PP1")
        frames.append(pp1)
        print(f"  PP1: {len(pp1)} записей")
    except Exception as e:
        print(f"  Ошибка PP1: {e}")
 
    if not frames:
        print("\n  Данные не получены.")
        return
 
    result = pd.concat(frames, ignore_index=True)
    out_path = os.path.join(OUTPUT_DIR, "01_faostat.csv")
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
 
    print(f"\n  {'='*50}")
    print(f"  Сохранено: {out_path}")
    print(f"  Итого строк:  {len(result)}")
    print(f"  Период:       {result['year'].min()}–{result['year'].max()}")
    print(f"\n  Сводка:")
    print(result.groupby(["source", "indicator"])["value"].count().to_string())
 
 
if __name__ == "__main__":
    main()
 