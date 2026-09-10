"""
Скрипт 05 — Данные Казахстана: реальные региональные ряды stat.gov.kz (1990–2025)
====================================================================================
Источник: Бюро национальной статистики РК (stat.gov.kz)
          Раздел "Статистика регионов" → [область] → Динамические ряды →
          Статистика сельского, лесного, охотничьего и рыбного хозяйства.
          https://stat.gov.kz/ru/region/<slug>/dynamic-tables/1485/

Как найдено (2026-09-09):
  У stat.gov.kz нет публичного REST API для растениеводства (раздел
  "Электронные таблицы" в разделе бизнес-статистики отдаёт только последние
  1-2 релиза, без исторического архива). Но у каждой области отдельно есть
  страница "Динамические ряды" с прямыми ссылками на xlsx-файлы (стабильный
  URL вида /api/iblock/element/region/<ID>/file/ru/), где ID — числовой
  идентификатор конкретной таблицы. Эти файлы содержат реальные официальные
  ряды с 1990/1991 по 2025 год.

  Детализация ОТЛИЧАЕТСЯ между областями (это не ограничение скрипта, а то,
  что реально публикует каждый областной комитет статистики):
    - Костанайская и Северо-Казахстанская области — один xlsx-файл на
      область с 6 листами (площадь/сбор/урожайность × область/районы).
      Листы "(регионы)"/"(районы)" разбиты БЛОКАМИ ПО ОТДЕЛЬНЫМ КУЛЬТУРАМ
      (Пшеница, Ячмень, Кукуруза, Подсолнечник), внутри блока — годы по
      столбцам, районы по строкам; первая строка данных в блоке — итог
      по области.
    - Акмолинская область публикует растениеводство только на уровне
      КРУПНЫХ ГРУПП культур (зерновые и бобовые; масличные), отдельных
      файлов по пшенице/ячменю/кукурузе на её странице нет.
    - Рапс (Rapeseed) НИ ОДНА из трёх областей не публикует отдельно —
      единственный источник по рапсу в этом проекте остаётся национальный
      FAOSTAT (см. 01_faostat.py). Это реальное ограничение источника,
      а не недосмотр.

  Единицы измерения тоже отличаются между файлами (например, у Костаная
  валовой сбор и площадь — в ТЫСЯЧАХ тонн/га, у СКО и Акмолинской — в
  штучных центнерах/гектарах), поэтому единицу измерения скрипт определяет
  динамически по подписи в самом файле (см. detect_unit), а не жёстко
  зашивает коэффициент.

Итог: это РЕАЛЬНЫЕ официальные данные Бюро нацстатистики РК, а не
синтетика. Из-за разной детализации между областями в датасете будет:
  - Костанайская, Северо-Казахстанская область: Пшеница, Ячмень, Кукуруза,
    Подсолнечник (отдельные культуры).
  - Акмолинская область: "Зерновые и бобовые (группа)", "Масличные
    (группа)" — это агрегаты по нескольким культурам, НЕ сопоставимые
    напрямую со строками отдельных культур у двух других областей.
    В колонке source они помечены как "stat_gov_kz_real_group", чтобы
    не перепутать с данными по отдельным культурам.

Если сайт недоступен (нет интернета / stat.gov.kz лёг) — скрипт
откатывается на синтетические данные (см. generate_synthetic_kaz),
это явно помечается в колонке source как "*_FALLBACK_SYNTHETIC".
"""

import os
import re
import sys
import requests
import pandas as pd
import numpy as np

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
INPUT_DIR = "input"
CACHE_DIR = os.path.join(OUTPUT_DIR, "stat_gov_kz_cache")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

FILE_URL = "https://stat.gov.kz/api/iblock/element/region/{}/file/ru/"

# Костанайская и Северо-Казахстанская область публикуют один комбинированный
# xlsx с 6 листами: "Посевная площадь (обл|регионы|районы)",
# "Валовой сбор (обл|регионы|районы)", "Урожайность (обл|регионы|районы)".
COMBINED_REGIONS = {
    "Костанайская область": 505415,
    "Северо-Казахстанская область": 503900,
}

# Акмолинская область: раздельные файлы по показателю x группе культур.
AKMOLA_REGION = "Акмолинская область"
AKMOLA_FILES = {
    ("Зерновые и бобовые (группа)", "area"):    40088,
    ("Зерновые и бобовые (группа)", "harvest"): 40092,
    ("Зерновые и бобовые (группа)", "yield"):   40103,
    ("Масличные (группа)", "area"):    40090,
    ("Масличные (группа)", "harvest"): 40097,
    ("Масличные (группа)", "yield"):   40104,
}

CROPS_WANTED = ["Пшеница", "Ячмень", "Кукуруза", "Подсолнечник"]

METRIC_COL = {"area": "area_ha", "harvest": "production_ton", "yield": "yield_kgha"}

# (regex по ОСНОВЕ слова, множитель к базовой единице, что получаем на выходе)
# Единицы на stat.gov.kz пишутся с разными падежными окончаниями и
# сокращениями ("центнеров" / "в центнерах", "тыс. гектар" / "тыс.га"), а
# substring-match по конкретной словоформе такое пропускает молча (без
# ошибки — просто "не нашли метку", тихий откат к factor=1.0). Поэтому
# матчим по неизменяемой ОСНОВЕ слова через regex, а не по точной фразе.
# Порядок важен: более специфичные варианты (с "тыс." или "с одного
# гектара") должны проверяться раньше общих ("гектар", "центнер").
UNIT_FACTORS = [
    (re.compile(r"тыс\.?\s*тонн"), 1000.0),
    (re.compile(r"тыс\.?\s*(?:га\b|гектар)"), 1000.0),
    (re.compile(r"центнер\S*\s+с\s+(?:одного\s+)?(?:1\s+)?(?:гектар|га\b)"), 100.0),  # ц/га -> кг/га
    (re.compile(r"центнер"), 0.1),                                       # ц -> тонн (любой падеж)
    (re.compile(r"гектар|(?:^|\W)га(?:\W|$)"), 1.0),
]


# ─────────────────────────────────────────
# Загрузка (с кэшем на диске)
# ─────────────────────────────────────────

def download_file(element_id: int) -> str:
    """Скачивает xlsx по ID элемента, кэширует локально."""
    path = os.path.join(CACHE_DIR, f"{element_id}.xlsx")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    url = FILE_URL.format(element_id)
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


# ─────────────────────────────────────────
# Парсинг
# ─────────────────────────────────────────

def is_subblock_boundary(label: str, total_label: str) -> bool:
    """
    Обнаруживает начало НОВОГО подблока внутри списка районов — например,
    "из них:\\nпшеницы" или повтор метки "Всего по области"/"по области"
    (см. подробный комментарий в fetch_akmola). Такой подблок повторяет
    список районов для более узкого среза (конкретная культура), и если
    его не отсечь, числа задваивают сумму по районам.

    Важно НЕ путать это с обычным районом, у которого просто нет данных
    за год (например, "-" на все годы для малой городской администрации,
    вроде "г.а Косшы" в отдельные годы) — такие строки пропускаются, а
    не считаются границей блока.
    """
    low = label.strip().lower()
    if low == total_label.strip().lower():
        return True
    if low.startswith("из них") or low.startswith("в т.ч") or low.startswith("в том числе"):
        return True
    return False


def is_num(v) -> bool:
    """isinstance(nan, float) is True in Python, so isinstance alone treats blank
    cells as numeric — always pair it with pd.notna() when checking for real data."""
    return isinstance(v, (int, float)) and pd.notna(v)


def detect_unit_factor(raw: pd.DataFrame) -> float:
    """Определяет множитель единицы измерения по подписи в первых строках листа."""
    text_cells = []
    for i in range(min(8, len(raw))):
        for j in range(raw.shape[1]):
            v = raw.iat[i, j]
            if isinstance(v, str):
                text_cells.append(v.lower())
    blob = " | ".join(text_cells)
    for pattern, factor in UNIT_FACTORS:
        if pattern.search(blob):
            return factor
    return 1.0


def detect_unit_factors_by_column(raw: pd.DataFrame) -> dict:
    """
    Некоторые листы содержат БОЛЬШЕ ОДНОЙ подписи единицы измерения в одной
    и той же строке (обнаружено на файле Акмолинской области "валовой
    сбор зерновых": в строке 2 стоит и "тыс. тонн" в столбце 13, и
    "центнеров" в столбце 35 — методика отчётности сменилась где-то в
    середине ряда, и подпись показывает единицу только для СВОЕГО участка
    столбцов, а не для всего листа). detect_unit_factor() в этом случае
    находит первую попавшуюся подпись и молча применяет её ко всем
    столбцам, что даёт ошибку на 3-4 порядка для части лет.

    Возвращает {col_idx: factor} — для каждого столбца берётся ближайшая
    подпись единицы С ТЕМ ЖЕ ИЛИ БОЛЬШИМ индексом столбца (эмпирически
    подпись стоит в последнем столбце своего участка). Если подпись на
    листе всего одна — все столбцы получают один и тот же множитель
    (эквивалентно detect_unit_factor).
    """
    hints = []
    for i in range(min(8, len(raw))):
        for j in range(1, raw.shape[1]):
            v = raw.iat[i, j]
            if not isinstance(v, str):
                continue
            low = v.lower()
            for pattern, factor in UNIT_FACTORS:
                if pattern.search(low):
                    hints.append((j, factor))
                    break

    factors = {}
    if not hints:
        return factors
    hints.sort()
    prev_col = 0
    for col_idx, factor in hints:
        for c in range(prev_col + 1, col_idx + 1):
            factors[c] = factor
        prev_col = col_idx
    for c in range(prev_col + 1, raw.shape[1]):
        factors[c] = hints[-1][1]
    return factors


def parse_crop_block_sheet(raw: pd.DataFrame, region_label: str, metric: str,
                            include_districts: bool = False) -> pd.DataFrame:
    """
    Парсит лист вида 'Урожайность (регионы)' / 'Валовой сбор (районы)' /
    'Посевная площадь (районы)': несколько блоков по отдельным культурам,
    внутри блока — годы по столбцам, район/область по строкам.

    По умолчанию (include_districts=False) возвращает только строку-итог
    по области (первая строка данных сразу после строки с годами внутри
    блока) — так работал скрипт исторически, это то, что попадает в
    05_kaz_stat.csv и master_dataset.csv.

    Если include_districts=True — дополнительно возвращает ВСЕ
    последующие строки блока (районы) до его конца, с районом в колонке
    "district". Используется отдельным output'ом
    (05_kaz_stat_districts.csv), НЕ подмешивается в master_dataset, чтобы
    не трогать уже провалидированный пайплайн 06/07.
    """
    col_factors = detect_unit_factors_by_column(raw)
    fallback_factor = detect_unit_factor(raw)

    title_rows = [
        i for i in range(len(raw))
        if isinstance(raw.iat[i, 0], str) and raw.iat[i, 0].strip()
        and pd.isna(raw.iat[i, 1])
    ]

    records = []
    for idx, tr in enumerate(title_rows):
        crop_raw = raw.iat[tr, 0].strip()
        crop = next((c for c in CROPS_WANTED if crop_raw.lower().startswith(c.lower())), None)
        if crop is None:
            continue
        block_end = title_rows[idx + 1] if idx + 1 < len(title_rows) else len(raw)

        year_row = None
        for r in range(tr, block_end):
            vals = raw.iloc[r].tolist()
            years_found = [v for v in vals if isinstance(v, (int, float)) and 1985 < v < 2030]
            if len(years_found) >= 5:
                year_row = r
                break
        if year_row is None:
            continue

        total_row = None
        for r in range(year_row + 1, block_end):
            if isinstance(raw.iat[r, 0], str) and raw.iat[r, 0].strip():
                has_numeric = any(
                    is_num(raw.iat[r, c]) for c in range(1, raw.shape[1])
                )
                if has_numeric:
                    total_row = r
                    break
        if total_row is None:
            continue

        # Строки-кандидаты: только итог по области, либо итог + все районы
        # до конца блока.
        total_label = raw.iat[total_row, 0].strip()
        data_rows = [total_row]
        if include_districts:
            # Отсекаем на повторе метки области/"из них:" (см. is_subblock_
            # boundary) — но НЕ на обычной строке района без данных за год
            # (например, "-" на всё для мелкой городской администрации).
            for r in range(total_row + 1, block_end):
                label = raw.iat[r, 0]
                if not (isinstance(label, str) and label.strip()):
                    continue
                if label.strip().startswith('"') or label.strip().startswith("'"):
                    continue  # сноска — не район и не подзаголовок, просто пропускаем
                if is_subblock_boundary(label, total_label):
                    break
                if any(is_num(raw.iat[r, c]) for c in range(1, raw.shape[1])):
                    data_rows.append(r)

        for row_idx, data_row in enumerate(data_rows):
            district_label = raw.iat[data_row, 0].strip() if row_idx > 0 else "Область (итого)"
            for col in range(1, raw.shape[1]):
                year_val = raw.iat[year_row, col]
                if not (isinstance(year_val, (int, float)) and 1985 < year_val < 2030):
                    continue
                val = raw.iat[data_row, col]
                if not isinstance(val, (int, float)) or pd.isna(val):
                    continue
                factor = col_factors.get(col, fallback_factor)
                rec = {
                    "year": int(year_val), "region": region_label,
                    "crop": crop, "metric": metric, "value": float(val) * factor,
                }
                if include_districts:
                    rec["district"] = district_label
                records.append(rec)

    return pd.DataFrame(records)


def fetch_combined_region(region_label: str, element_id: int, include_districts: bool = False) -> pd.DataFrame:
    """Скачивает и парсит комбинированный файл (Костанай / СКО)."""
    path = download_file(element_id)
    sheet_by_metric = {
        "area": None, "harvest": None, "yield": None,
    }
    xls = pd.ExcelFile(path)
    for sheet in xls.sheet_names:
        low = sheet.lower()
        if "регион" not in low and "район" not in low:
            continue
        if "посевн" in low:
            sheet_by_metric["area"] = sheet
        elif "сбор" in low:
            sheet_by_metric["harvest"] = sheet
        elif "урожайн" in low:
            sheet_by_metric["yield"] = sheet

    frames = []
    for metric, sheet in sheet_by_metric.items():
        if sheet is None:
            print(f"    ⚠ {region_label}: не найден лист для metric={metric}")
            continue
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        frames.append(parse_crop_block_sheet(raw, region_label, metric, include_districts=include_districts))

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


SUBCROP_NAME_PATTERNS = [
    (re.compile(r"пшениц", re.IGNORECASE), "Пшеница"),
    (re.compile(r"ячмен", re.IGNORECASE), "Ячмень"),
    (re.compile(r"кукуруз", re.IGNORECASE), "Кукуруза"),
    (re.compile(r"подсолнечник", re.IGNORECASE), "Подсолнечник"),
]


def extract_subcrop_name(label: str):
    """'из них:\\nпшеницы' -> 'Пшеница', 'из них: семена подсолнечника*' -> 'Подсолнечник'."""
    for pattern, name in SUBCROP_NAME_PATTERNS:
        if pattern.search(label):
            return name
    return None


def fetch_akmola(include_districts: bool = False) -> pd.DataFrame:
    """
    Скачивает и парсит раздельные файлы Акмолинской области.

    Помимо основной группы культур ("Зерновые и бобовые (группа)" /
    "Масличные (группа)"), некоторые файлы содержат встроенный подблок
    "из них: <культура>" — ПОВТОРНУЮ районную разбивку уже для конкретной
    культуры внутри группы (обнаружено 2026-09-09: пшеница есть во всех
    3 файлах зерновых — площадь/сбор/урожайность; подсолнечник — в сборе
    и урожайности масличных, но не в площади — реальное ограничение
    источника, не пропуск скрипта).

    Раньше такой подблок только МЕШАЛ (задваивал сумму по районам, если
    его не отсечь) — теперь он же самый парсится как ОТДЕЛЬНАЯ культура
    (crop="Пшеница"/"Подсолнечник", не "(группа)"), закрывая часть
    "слепой зоны" Акмолинской по конкретным культурам. Признак культуры
    возвращается в результате через колонку "_is_group_total" (True для
    самой группы, False для распознанных подкультур) — вызывающий код
    (main/build_district_level) использует её, чтобы проставить разный
    source (stat_gov_kz_real_group / stat_gov_kz_real).
    """
    records = []
    for (crop_group, metric), element_id in AKMOLA_FILES.items():
        path = download_file(element_id)
        xls = pd.ExcelFile(path)
        raw = pd.read_excel(path, sheet_name=xls.sheet_names[0], header=None)
        col_factors = detect_unit_factors_by_column(raw)
        fallback_factor = detect_unit_factor(raw)

        year_row = None
        for r in range(len(raw)):
            vals = raw.iloc[r].tolist()
            years_found = [v for v in vals if isinstance(v, (int, float)) and 1985 < v < 2030]
            if len(years_found) >= 5:
                year_row = r
                break
        if year_row is None:
            print(f"    ⚠ Акмолинская/{crop_group}/{metric}: строка с годами не найдена")
            continue

        segment_crop = crop_group
        is_group_total = True
        segment_start = year_row + 1

        while True:
            total_row = None
            for r in range(segment_start, len(raw)):
                if isinstance(raw.iat[r, 0], str) and raw.iat[r, 0].strip():
                    if any(is_num(raw.iat[r, c]) for c in range(1, raw.shape[1])):
                        total_row = r
                        break
            if total_row is None:
                if segment_crop == crop_group:
                    print(f"    ⚠ Акмолинская/{crop_group}/{metric}: итоговая строка по области не найдена")
                break

            # См. подробный комментарий про is_subblock_boundary в
            # parse_crop_block_sheet — то же правило: граница блока это
            # НЕ "нет числа в строке" (у мелких городских администраций
            # иногда весь год "-", это обычный пустой район), а повтор
            # метки области или явное "из них:"/"в т.ч.".
            # Границу следующего сегмента ("из них: ...") ищем ВСЕГДА (нужна
            # для перехода к следующей культуре), а вот districts в
            # data_rows добавляем, только если include_districts=True —
            # иначе (в режиме "только область") каждый район эмитился бы
            # отдельной записью года, задваивая и затраивая сумму по
            # области (реальный баг первой версии этого рефакторинга).
            total_label = raw.iat[total_row, 0].strip()
            data_rows = [total_row]
            boundary_row = None
            for r in range(total_row + 1, len(raw)):
                label = raw.iat[r, 0]
                if not (isinstance(label, str) and label.strip()):
                    continue
                if label.strip().startswith('"') or label.strip().startswith("'"):
                    continue
                if is_subblock_boundary(label, total_label):
                    boundary_row = r
                    break
                if include_districts and any(is_num(raw.iat[r, c]) for c in range(1, raw.shape[1])):
                    data_rows.append(r)

            for row_idx, data_row in enumerate(data_rows):
                district_label = raw.iat[data_row, 0].strip() if row_idx > 0 else "Область (итого)"
                for col in range(1, raw.shape[1]):
                    year_val = raw.iat[year_row, col]
                    if not (isinstance(year_val, (int, float)) and 1985 < year_val < 2030):
                        continue
                    val = raw.iat[data_row, col]
                    if not isinstance(val, (int, float)) or pd.isna(val):
                        continue
                    factor = col_factors.get(col, fallback_factor)
                    rec = {
                        "year": int(year_val), "region": AKMOLA_REGION,
                        "crop": segment_crop, "metric": metric, "value": float(val) * factor,
                        "_is_group_total": is_group_total,
                    }
                    if include_districts:
                        rec["district"] = district_label
                    records.append(rec)

            if boundary_row is None:
                break
            subcrop = extract_subcrop_name(raw.iat[boundary_row, 0])
            if subcrop is None:
                break  # неопознанный подблок — не гадаем, просто останавливаемся здесь
            segment_crop = subcrop
            is_group_total = False
            segment_start = boundary_row + 1

    return pd.DataFrame(records)


def detect_and_drop_unit_breaks(long_df: pd.DataFrame, ratio_threshold: float = 50.0) -> pd.DataFrame:
    """
    В некоторых файлах stat.gov.kz единица измерения незаметно меняется
    посреди временного ряда (например, тысячи гектаров -> гектары, тысячи
    центнеров -> центнеры) без пометки по годам — подпись листа отражает
    только одну (обычно актуальную) единицу. Обнаружено эмпирически на
    Акмолинской области: "Всего по области" для зерновых прыгает с ~4700
    (1998) до ~2 728 207 (1999), хотя область явно не увеличила посевную
    площадь в 580 раз за один год.

    Если между соседними годами найден устойчивый скачок в ratio_threshold+
    раз, который НЕ откатывается обратно в течение следующих лет (то есть
    это не единичный выброс/ошибка ввода, а переход на новый порядок
    величины) — считаем все годы ДО скачка данными в неизвестной единице
    измерения и отбрасываем их, вместо того чтобы тихо оставить заведомо
    неверный масштаб в датасете.

    Порог отсечки определяется ТОЛЬКО по строке "Область (итого)" (или по
    единственной серии, если колонки district нет вовсе) — у отдельных
    районов абсолютные значения маленькие, и обычная волатильность
    (например, второстепенная культура на паре сотен га в одном районе)
    легко даёт мнимый "скачок в 50+ раз", который на самом деле не имеет
    отношения к смене единицы измерения. Смена единицы в источнике — это
    свойство СТОЛБЦА (года) в файле и затрагивает все строки листа
    одинаково, поэтому год отсечки, найденный по надёжной агрегированной
    серии, применяется ко всем районам той же (region, crop, metric).
    """
    has_district = "district" in long_df.columns
    base_group_keys = ["region", "crop", "metric"]

    # 1) Определяем год отсечки по агрегированной серии (область/итого).
    base_df = long_df[long_df["district"] == "Область (итого)"] if has_district else long_df
    break_years = {}
    dropped_info = []
    for key, grp in base_df.groupby(base_group_keys, sort=False):
        grp = grp.sort_values("year").reset_index(drop=True)
        vals = grp["value"].tolist()
        years = grp["year"].tolist()

        for i in range(1, len(vals)):
            prev, cur = vals[i - 1], vals[i]
            if not prev:
                continue
            ratio = cur / prev
            if ratio > ratio_threshold or (0 < ratio < 1 / ratio_threshold):
                tail = [v for v in vals[i:i + 3] if v]
                if len(tail) >= 2 and all(0.2 < (t / cur) < 5 for t in tail):
                    break_years[key] = years[i]
                    dropped_info.append((*key, years[i - 1], years[i]))
                    break

    # 2) Применяем найденный год отсечки ко ВСЕМ строкам группы (включая районы).
    if break_years:
        def keep_row(row):
            key = (row["region"], row["crop"], row["metric"])
            cutoff = break_years.get(key)
            return cutoff is None or row["year"] >= cutoff
        long_df = long_df[long_df.apply(keep_row, axis=1)]

    if dropped_info:
        print("  ⚠️  Обнаружен устойчивый скачок масштаба (похоже на смену единицы")
        print("      измерения в самом источнике) — годы до скачка отброшены как")
        print("      ненадёжные вместо того, чтобы оставить неверный порядок величины:")
        for region, crop, metric, y_before, y_after in dropped_info:
            print(f"        {region} / {crop} / {metric}: данные до {y_before} отброшены (скачок к {y_after})")

    return long_df.reset_index(drop=True)


def long_to_wide(long_df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    """year, region, crop, metric, value -> year, region, crop, area_ha, yield_kgha, production_ton."""
    if long_df.empty:
        return long_df
    long_df = long_df.copy()
    long_df["metric_col"] = long_df["metric"].map(METRIC_COL)
    index_cols = ["year", "region", "crop"] + (["district"] if "district" in long_df.columns else [])
    wide = long_df.pivot_table(
        index=index_cols, columns="metric_col", values="value", aggfunc="mean"
    ).reset_index()
    wide.columns.name = None
    for col in METRIC_COL.values():
        if col not in wide.columns:
            wide[col] = np.nan
    wide["source"] = source_label
    return wide


# ─────────────────────────────────────────
# Синтетический fallback (если сайт недоступен)
# ─────────────────────────────────────────

REGIONAL_BASELINES = {
    "Акмолинская область": {
        "Пшеница": {"area_ha": 3_800_000, "yield_kgha": 1050},
        "Ячмень":  {"area_ha":   400_000, "yield_kgha": 1100},
        "Подсолнечник": {"area_ha": 50_000, "yield_kgha": 900},
        "Кукуруза": {"area_ha": 20_000, "yield_kgha": 2800},
    },
    "Костанайская область": {
        "Пшеница": {"area_ha": 4_200_000, "yield_kgha": 1080},
        "Ячмень":  {"area_ha":   350_000, "yield_kgha": 1150},
        "Подсолнечник": {"area_ha": 30_000, "yield_kgha": 920},
        "Кукуруза": {"area_ha": 10_000, "yield_kgha": 2700},
    },
    "Северо-Казахстанская область": {
        "Пшеница": {"area_ha": 3_100_000, "yield_kgha": 1120},
        "Ячмень":  {"area_ha":   280_000, "yield_kgha": 1180},
        "Подсолнечник": {"area_ha": 15_000, "yield_kgha": 880},
        "Кукуруза": {"area_ha": 5_000, "yield_kgha": 2500},
    },
}

YIELD_MODIFIERS = {2010: 0.72, 2012: 0.68, 2018: 1.12, 2020: 0.88, 2022: 1.15, 2024: 1.08}


def generate_synthetic_kaz(start_year: int = 2000, end_year: int = 2025) -> pd.DataFrame:
    """Синтетические данные — используются ТОЛЬКО если stat.gov.kz недоступен."""
    np.random.seed(42)
    records = []
    for year in range(start_year, end_year + 1):
        modifier = YIELD_MODIFIERS.get(year, 1.0)
        trend = (year - 2000) * 5
        for region, crops in REGIONAL_BASELINES.items():
            for crop, base in crops.items():
                area = base["area_ha"] * (1 + np.random.normal(0, 0.04))
                yield_kgha = (base["yield_kgha"] + trend) * modifier * (1 + np.random.normal(0, 0.06))
                yield_kgha = max(300, yield_kgha)
                production = area * yield_kgha / 1000
                records.append({
                    "year": year, "region": region, "crop": crop,
                    "area_ha": round(area, 0), "yield_kgha": round(yield_kgha, 1),
                    "production_ton": round(production, 0),
                    "source": "synthetic_KAZ_stat_FALLBACK_SYNTHETIC",
                })
    return pd.DataFrame(records)


def try_load_manual_file() -> pd.DataFrame:
    """Если пользователь вручную положил файл в input/ — используем его вместо сети."""
    for name in ("stat_gov_kz_crops.xlsx", "stat_gov_kz_crops.csv"):
        path = os.path.join(INPUT_DIR, name)
        if os.path.exists(path):
            print(f"  ✅ Найден ручной файл: {path} (имеет приоритет над автозагрузкой)")
            df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path, encoding="utf-8-sig")
            df["source"] = "stat_gov_kz_manual_upload"
            return df
    return pd.DataFrame()


def process_akmola(include_districts: bool = False) -> pd.DataFrame:
    """
    Единая точка сборки Акмолинской области: скачивает/парсит fetch_akmola(),
    разделяет результат на группы культур (crop="... (группа)") и
    распознанные подкультуры внутри "из них:" (crop="Пшеница"/
    "Подсолнечник") — у них разный, независимый год отсечки для
    detect_and_drop_unit_breaks и разный source (real_group vs real).
    """
    long_akmola = fetch_akmola(include_districts=include_districts)
    if long_akmola.empty:
        return long_akmola

    is_group = long_akmola["_is_group_total"]
    group_part = long_akmola[is_group].drop(columns=["_is_group_total"])
    crop_part = long_akmola[~is_group].drop(columns=["_is_group_total"])

    wide_parts = []
    if not group_part.empty:
        wide_parts.append(long_to_wide(detect_and_drop_unit_breaks(group_part), "stat_gov_kz_real_group"))
    if not crop_part.empty:
        wide_parts.append(long_to_wide(detect_and_drop_unit_breaks(crop_part), "stat_gov_kz_real"))
        found_crops = sorted(crop_part["crop"].unique())
        print(f"    ℹ️  Найдена районная разбивка по отдельным культурам внутри группы: {found_crops}")

    if not wide_parts:
        return pd.DataFrame()
    return pd.concat(wide_parts, ignore_index=True)


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Скрипт 05 — Данные stat.gov.kz (реальные региональные ряды)")
    print("  Источник: stat.gov.kz/ru/region/<область>/dynamic-tables/1485/")
    print("=" * 70)

    df_manual = try_load_manual_file()
    if not df_manual.empty:
        out_path = os.path.join(OUTPUT_DIR, "05_kaz_stat.csv")
        df_manual.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"  💾 Сохранено (ручная загрузка): {out_path} ({len(df_manual)} строк)")
        return

    all_frames = []
    try:
        for region, element_id in COMBINED_REGIONS.items():
            print(f"\n  [{region}] скачивание и парсинг...")
            long_df = detect_and_drop_unit_breaks(fetch_combined_region(region, element_id))
            wide = long_to_wide(long_df, "stat_gov_kz_real")
            if not wide.empty:
                all_frames.append(wide)
                print(f"    ✅ {len(wide)} строк, культуры: {sorted(wide['crop'].unique())}")
            else:
                print(f"    ❌ Не удалось распарсить данные")

        print(f"\n  [{AKMOLA_REGION}] скачивание и парсинг (группы + встроенные культуры)...")
        wide_akmola = process_akmola()
        if not wide_akmola.empty:
            all_frames.append(wide_akmola)
            print(f"    ✅ {len(wide_akmola)} строк, культуры/группы: {sorted(wide_akmola['crop'].unique())}")
        else:
            print(f"    ❌ Не удалось распарсить данные")

    except requests.exceptions.RequestException as e:
        print(f"\n  ❌ Сеть/сайт недоступны: {e}")
        all_frames = []

    if all_frames:
        result = pd.concat(all_frames, ignore_index=True)
        result = result.sort_values(["region", "crop", "year"]).reset_index(drop=True)
        out_path = os.path.join(OUTPUT_DIR, "05_kaz_stat.csv")
        result.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"\n  {'='*50}")
        print(f"  💾 Сохранено (реальные данные): {out_path}")
        print(f"  Строк: {len(result)}, период: {result['year'].min()}–{result['year'].max()}")
        print(f"  Регионы: {result['region'].unique().tolist()}")
    else:
        print("\n  ⚠️  Реальные данные недоступны — переход на синтетический fallback.")
        df_synth = generate_synthetic_kaz(2000, 2025)
        out_path = os.path.join(OUTPUT_DIR, "05_kaz_stat.csv")
        df_synth.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"  💾 Синтетические данные (FALLBACK): {out_path} ({len(df_synth)} строк)")
        print(f"  ⚠️  Это НЕ реальная статистика — замените, когда сайт снова станет доступен.")
        return

    build_district_level()


def build_district_level():
    """
    Отдельный, дополнительный выход — районная разбивка (не только итог
    по области). Сохраняется в 05_kaz_stat_districts.csv и НЕ подмешивается
    в 05_kaz_stat.csv/master_dataset.csv, чтобы не трогать уже
    провалидированный пайплайн 06/07: климат/почва в мастер-датасете
    остаются на уровне области (см. README, раздел про районный уровень).

    Акмолинская область здесь тоже участвует (районы есть в её файлах),
    хотя на уровне области у неё только группы культур, не отдельные
    культуры — то же ограничение, что и в 05_kaz_stat.csv.
    """
    print(f"\n{'='*70}")
    print("  Районная разбивка (дополнительный выход, не в master_dataset)")
    print(f"{'='*70}")

    frames = []
    for region, element_id in COMBINED_REGIONS.items():
        print(f"\n  [{region}] районы...")
        long_df = detect_and_drop_unit_breaks(
            fetch_combined_region(region, element_id, include_districts=True)
        )
        wide = long_to_wide(long_df, "stat_gov_kz_real")
        if not wide.empty:
            frames.append(wide)
            n_districts = wide["district"].nunique()
            print(f"    ✅ {len(wide)} строк, районов: {n_districts}")

    print(f"\n  [{AKMOLA_REGION}] районы (группы + встроенные культуры)...")
    wide_akmola = process_akmola(include_districts=True)
    if not wide_akmola.empty:
        frames.append(wide_akmola)
        print(f"    ✅ {len(wide_akmola)} строк, районов: {wide_akmola['district'].nunique()}, "
              f"культуры/группы: {sorted(wide_akmola['crop'].unique())}")

    if not frames:
        print("\n  ❌ Районные данные не собраны.")
        return

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(["region", "district", "crop", "year"]).reset_index(drop=True)
    out_path = os.path.join(OUTPUT_DIR, "05_kaz_stat_districts.csv")
    result.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 Сохранено: {out_path}")
    print(f"  Строк: {len(result)}, районов всего: {result['district'].nunique()}")
    print(f"  Из них 'Область (итого)' — сводная строка, дублирует 05_kaz_stat.csv,")
    print(f"  оставлена для удобства сравнения район vs область в одном файле.")

    validate_district_sums(result)


def validate_district_sums(result: pd.DataFrame, tolerance: float = 0.02):
    """
    Кросс-проверка: сумма production_ton по районам должна совпадать с
    строкой 'Область (итого)' для того же (region, crop, year) — это
    официальная статистика, районы формально составляют область без
    остатка, так что расхождение сигнализирует об ошибке парсинга, а не
    просто о шумных данных (в отличие от 07_validate_regions_vs_national.py,
    где заведомо ожидается неполное покрытие — здесь ожидается точное).
    """
    mismatches = []
    checked = 0
    for (region, crop, year), grp in result.groupby(["region", "crop", "year"]):
        oblast_row = grp[grp.district == "Область (итого)"]
        district_rows = grp[grp.district != "Область (итого)"]
        if oblast_row.empty or district_rows.empty:
            continue
        oblast_val = oblast_row["production_ton"].iloc[0]
        districts_sum = district_rows["production_ton"].sum(min_count=1)
        if pd.isna(oblast_val) or pd.isna(districts_sum) or oblast_val == 0:
            continue
        checked += 1
        rel_diff = abs(districts_sum - oblast_val) / abs(oblast_val)
        if rel_diff > tolerance:
            mismatches.append((region, crop, year, oblast_val, districts_sum, rel_diff))

    print(f"\n  Кросс-проверка сумма(районы) == область: {checked} групп (year×crop×region) проверено")
    if mismatches:
        print(f"  ⚠️  Расхождение >2% в {len(mismatches)} группах (первые 10):")
        for region, crop, year, oblast_val, districts_sum, rel_diff in mismatches[:10]:
            print(f"    {region}/{crop}/{year}: область={oblast_val:.0f}, сумма районов={districts_sum:.0f} ({rel_diff:.1%})")
    else:
        print(f"  ✅ Все проверенные группы совпадают с допуском {tolerance:.0%} — районные данные согласованы с областными.")


if __name__ == "__main__":
    main()
