"""
Скрипт 16 - Региональные цены производителей сельхозпродукции (stat.gov.kz)
===========================================================================
Источник: Бюро национальной статистики РК, электронные таблицы раздела "Статистика цен",
выпуск "Индексы цен и цены в сельском хозяйстве в Республике Казахстан" (ежемесячный).
В каждом выпуске лист "5. Средние цены производителей на продукцию сельского хозяйства
по регионам" (тенге за тонну): культура x регион за один месяц.

Как найдено: страница /spreadsheets/ показывает только 10 последних выпусков, но
GET-параметры фильтра (name=<id таблицы>, year=<год>) отдают весь архив. Для этой таблицы
name=19100; доступны выпуски с октября 2022 года (раньше в этой серии нет).

Метод:
  1. Список выпусков по годам (?name=19100&year=Y) -> id элемента, заголовок, дата релиза.
  2. Скачивание /api/iblock/element/<id>/file/ru/ в output/stat_prices_cache/ (кэш).
  3. Поиск листа по заголовку (номер листа между выпусками может меняться), разбор матрицы
     культура x регион. "x" (конфиденциально) и "-" (нет данных) -> NaN.

Выход:
  output/16_producer_prices_monthly.csv - (год, месяц, регион, культура) -> цена, тг/т
  output/16_producer_prices_annual.csv  - годовое среднее и "сезон уборки" (авг-окт) по региону
"""

import html
import io
import os
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
CACHE_DIR = os.path.join(OUTPUT_DIR, "stat_prices_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

BASE = "https://stat.gov.kz"
LIST_URL = BASE + "/ru/industries/economy/prices/spreadsheets/"
FILE_URL = BASE + "/api/iblock/element/{id}/file/ru/"
TABLE_NAME_ID = 19100          # "Индексы цен и цены в сельском хозяйстве в РК"
YEARS = range(2022, 2027)
UA = "Mozilla/5.0"

MONTHS = {"январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6, "июль": 7,
          "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12}

# Сопоставление с названиями культур в master_dataset_districts
CROP_MAP = {
    "Пшеница": "Пшеница",
    "Ячмень": "Ячмень",
    "Кукуруза (маис)": "Кукуруза",
    "Семена подсолнечника": "Подсолнечник",
}
TARGET_REGIONS = {"Акмолинская область", "Костанайская область", "Северо-Казахстанская область"}


def http_get(url: str, retries: int = 3) -> bytes:
    # curl вместо requests: сайт на Windows-окружении стабильнее отвечает на curl с обычным UA
    last = None
    for i in range(retries):
        r = subprocess.run(["curl", "-s", "-m", "90", "-A", UA, "-L", "-f", url], capture_output=True)
        if r.returncode == 0 and r.stdout:
            return r.stdout
        last = r.returncode
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"не удалось скачать {url} (curl код {last})")


def list_releases() -> pd.DataFrame:
    rows = []
    for y in YEARS:
        page = http_get(f"{LIST_URL}?name={TABLE_NAME_ID}&year={y}").decode("utf-8", "ignore")
        for m in re.finditer(r'id="bx_\d+_(\d+)">.*?<a href="[^"]*">\s*(.*?)\s*</a>.*?text-right">(\d\d\.\d\d\.\d{4})',
                             page, flags=re.S):
            title = html.unescape(re.sub(r"\s+", " ", m.group(2)))
            mm = re.search(r"\(\s*([А-Яа-я]+)\s*(\d{4})", title)
            if not mm or mm.group(1).lower() not in MONTHS:
                print(f"  пропуск (не разобран заголовок): {title}")
                continue
            rows.append({"element_id": int(m.group(1)), "title": title, "release_date": m.group(3),
                         "year": int(mm.group(2)), "month": MONTHS[mm.group(1).lower()]})
    df = pd.DataFrame(rows).drop_duplicates("element_id").sort_values(["year", "month"]).reset_index(drop=True)
    return df


def fetch_release(element_id: int) -> bytes:
    # Новые выпуски отдаются как xlsx (zip, "PK"), старые - как xls (OLE2, d0cf11e0)
    for ext in ("xlsx", "xls"):
        path = os.path.join(CACHE_DIR, f"{element_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 10_000:
            with open(path, "rb") as f:
                return f.read()
    data = http_get(FILE_URL.format(id=element_id))
    if data[:2] == b"PK":
        ext = "xlsx"
    elif data[:4] == bytes.fromhex("d0cf11e0"):
        ext = "xls"
    else:
        raise RuntimeError(f"{element_id}: неизвестный формат ответа ({data[:8]!r})")
    with open(os.path.join(CACHE_DIR, f"{element_id}.{ext}"), "wb") as f:
        f.write(data)
    time.sleep(1.0)
    return data


def norm_region(name: str) -> str:
    n = re.sub(r"\s+", " ", str(name)).strip()
    if n.startswith("Республика"):
        return "Республика Казахстан"
    # в разных выпусках: "Северо Казахстанская", "Северо-Казахстанская", "СевероКазахстанская"
    n = re.sub(r"^(Северо|Западно|Восточно|Южно)[\s-]*(Казахстанская)", r"\1-\2", n)
    return n if n.endswith("область") else n + " область"


def norm_crop(label: str) -> str:
    s = re.sub(r"\s+", " ", str(label).replace("\n", " ")).strip()
    s = re.sub(r"\d+\)$", "", s).strip()
    # в части выпусков названия строчными ("семена подсолнечника") - приводим к единому виду
    return s[:1].upper() + s[1:]


def parse_release(raw: bytes, year: int, month: int) -> pd.DataFrame:
    xl = pd.ExcelFile(io.BytesIO(raw))
    sheet = None
    for sh in xl.sheet_names:
        head = xl.parse(sh, header=None, nrows=3)
        text = " ".join(str(v) for v in head.values.ravel() if str(v) != "nan")
        if "Средние цены производителей" in text and "по регионам" in text:
            sheet = sh
            break
    if sheet is None:
        raise RuntimeError("лист со средними ценами производителей по регионам не найден")
    d = xl.parse(sheet, header=None)

    # строка заголовка регионов: содержит "Республика Казахстан"
    hdr = next(i for i in range(len(d)) if d.iloc[i].astype(str).str.contains("Республика Казахстан").any())
    cols = {j: norm_region(d.iat[hdr, j]) for j in range(d.shape[1])
            if str(d.iat[hdr, j]) != "nan" and not re.match(r"\s*[А-Яа-я]+\s+\d{4}", str(d.iat[hdr, j]))}
    # метка единиц измерения проверяется явно - защита от смены формата
    unit_text = " ".join(str(v) for v in d.iloc[:3].values.ravel() if str(v) != "nan")
    if not re.search(r"те[нң]ге за тонну", unit_text):
        raise RuntimeError(f"неожиданные единицы измерения: {unit_text[:100]}")

    recs = []
    for i in range(hdr + 1, len(d)):
        label = d.iat[i, 0]
        if str(label) == "nan":
            continue
        crop = norm_crop(label)
        for j, region in cols.items():
            v = pd.to_numeric(d.iat[i, j], errors="coerce") if isinstance(d.iat[i, j], (int, float, np.number)) \
                else pd.to_numeric(str(d.iat[i, j]).replace("\xa0", "").replace(" ", "").replace(",", "."), errors="coerce")
            if pd.notna(v):
                recs.append({"year": year, "month": month, "region": region, "crop_raw": crop, "price_kzt_t": float(v)})
    return pd.DataFrame(recs)


def build_annual(m: pd.DataFrame) -> pd.DataFrame:
    m = m[m["crop"].notna()].copy()
    g = ["region", "crop", "year"]
    annual = m.groupby(g)["price_kzt_t"].agg(price_mean_kzt_t="mean", n_months="count").reset_index()
    # n_harvest_months: сколько из трёх месяцев сезона уборки (авг-окт) реально есть. Для 2022 года
    # в архиве только октябрь, поэтому такая цена менее надёжна - счётчик позволяет её отфильтровать.
    harvest = (m[m["month"].between(8, 10)].groupby(g)["price_kzt_t"]
               .agg(price_harvest_aug_oct_kzt_t="mean", n_harvest_months="count").reset_index())
    # Послеуборочное окно (ноя-дек): у подсолнечника цены в авг-окт почти не публикуются (октябрь -
    # никогда), а в ноябре-декабре есть; цена известна к следующему севу.
    post = (m[m["month"].between(11, 12)].groupby(g)["price_kzt_t"]
            .agg(price_nov_dec_kzt_t="mean", n_nov_dec_months="count").reset_index())
    return annual.merge(harvest, on=g, how="left").merge(post, on=g, how="left")


def main():
    rel = list_releases()
    print(f"Найдено выпусков: {len(rel)} ({rel.year.min()}-{rel.month.iloc[0]:02d} .. "
          f"{rel.year.max()}-{rel.month.iloc[-1]:02d})")
    gaps = []
    full = pd.period_range(f"{rel.year.iloc[0]}-{rel.month.iloc[0]:02d}", f"{rel.year.iloc[-1]}-{rel.month.iloc[-1]:02d}", freq="M")
    have = set(zip(rel.year, rel.month))
    gaps = [str(p) for p in full if (p.year, p.month) not in have]
    if gaps:
        print(f"  ВНИМАНИЕ: нет выпусков за месяцы: {gaps}")

    frames, failed = [], []
    for _, r in rel.iterrows():
        try:
            raw = fetch_release(r.element_id)
            df = parse_release(raw, r.year, r.month)
            frames.append(df)
            print(f"  {r.year}-{r.month:02d} id={r.element_id}: {len(df)} значений")
        except Exception as e:
            failed.append((r.year, r.month, str(e)[:80]))
            print(f"  {r.year}-{r.month:02d} id={r.element_id}: ОШИБКА {e}")

    monthly = pd.concat(frames, ignore_index=True)
    monthly["crop"] = monthly["crop_raw"].map(CROP_MAP)
    monthly.to_csv(os.path.join(OUTPUT_DIR, "16_producer_prices_monthly.csv"), index=False, encoding="utf-8")

    annual = build_annual(monthly)
    annual.to_csv(os.path.join(OUTPUT_DIR, "16_producer_prices_annual.csv"), index=False, encoding="utf-8")

    print(f"\nmonthly: {monthly.shape}, annual: {annual.shape}; ошибок: {len(failed)}")
    t = annual[annual["region"].isin(TARGET_REGIONS) & (annual["crop"] == "Пшеница")]
    print(t.pivot(index="year", columns="region", values="price_mean_kzt_t").round(0).to_string())


if __name__ == "__main__":
    main()
