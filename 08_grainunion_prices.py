"""
Скрипт 08 — Внутренний рынок Казахстана: еженедельные обзоры Зернового союза
================================================================================
Источник: grainunion.kz (ОЮЛ "Зерновой союз Казахстана"), раздел новостей
          /ru/news/32, статьи с заголовком "Еженедельный обзор ценовой
          ситуации на зерновом рынке Казахстана".
          Судя по всему, преемник домена gsc.kz (который на 2026-09-09
          отдаёт 404 на всех путях и, видимо, больше не обслуживается).

Как найдено:
  apk-inform.com даёт по Казахстану только 2 экспортные позиции в USD в
  бесплатном виджете (см. 09_apk_inform_export_prices.py) — внутреннего
  тенгового рынка там нет. На grainunion.kz нашёлся именно внутренний
  рынок: "по данным Комитета аналитики Зернового Союза Казахстана, цены
  на условиях EXW-элеватор (Акмолинская, Костанайская, Северо-Казахстанская
  области), в тыс теңге/т" — то есть ИМЕННО тот внутренний рынок трёх
  целевых зерновых областей, которые уже используются в 05_kaz_stat.py.

  Формат "Еженедельный обзор" структурирован буллет-пунктами вида
  "▪️Пшеница 3 кл (кл-на 23-24%) - 88 - 92 ▶️ (0)", что позволяет
  парсить регулярными выражениями, а не свободный текст через NLP.

Важное ограничение: этот структурированный формат стартовал только
25.05.2026 (проверено постранично по всему архиву новостей /ru/news/32,
который в остальном уходит в 2019 год, но состоит из разрозненных
пресс-релизов/конференций — регулярные еженедельные обзоры с ценами
появились недавно). На 2026-09-09 доступно всего ~12 выпусков (по одному
в неделю). Это НЕ historical backfill на много лет — это старт сбора
"на будущее": скрипт создан так, чтобы его можно было перезапускать
периодически (например, раз в неделю), и с каждым запуском он будет
дозаписывать новые выпуски, накапливая историю со временем.

Как работает:
  1. Постранично обходит /ru/news/32 (страница 1, 2, 3, ...), пока не
     встретит статью, ID которой уже есть в локальном кэше (значит дальше
     все старые — можно остановиться), либо не наберёт MAX_EMPTY_PAGES
     страниц подряд без единого совпадения по заголовку.
  2. Для новых статей с заголовком "Еженедельный обзор ..." скачивает
     текст, парсит блоки "внутренний рынок (EXW-элеватор, тыс.тенге/т)"
     и "экспортные цены (USD/тонна)" через regex по буллет-пунктам.
  3. Сохраняет структурированные записи, накапливая в output/
     08_grainunion_domestic_prices.csv (append, без дублей по article_id).
"""

import os
import re
import sys
import html as html_module
import time
import requests
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"
CACHE_DIR = os.path.join(OUTPUT_DIR, "grainunion_cache")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

BASE = "https://www.grainunion.kz"
LIST_URL_TPL = BASE + "/ru/news/32{page_suffix}"
ARTICLE_URL_TPL = BASE + "/ru/article/{article_id}"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
REQUEST_DELAY_SEC = 2.0     # вежливая задержка между запросами
MAX_PAGES = 10               # запас на будущее — сейчас всё умещается на 2 страницах
MAX_EMPTY_PAGES = 3          # страниц подряд без новых REVIEW-статей -> стоп

OUT_CSV = os.path.join(OUTPUT_DIR, "08_grainunion_domestic_prices.csv")

BASIS_KEYWORDS = ["EXW", "DAP", "FOB", "FCA", "CPT", "CIF", "C&F"]


# ─────────────────────────────────────────
# Список статей
# ─────────────────────────────────────────

def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY_SEC)
    return resp.text


def list_review_articles(known_ids: set) -> list:
    """Постранично собирает (article_id, listed_date, title) для статей-обзоров."""
    found = []
    empty_streak = 0
    for page in range(1, MAX_PAGES + 1):
        suffix = "" if page == 1 else f"/{page}"
        url = LIST_URL_TPL.format(page_suffix=suffix)
        print(f"  Страница {page}: {url}")
        try:
            html = fetch(url)
        except requests.exceptions.RequestException as e:
            print(f"    ⚠ Ошибка загрузки: {e}")
            break

        pattern = re.compile(
            r'href="(/ru/article/(\d+))"[^>]*>.*?<b>([^<]*)</b>\s*<em>([^<]*)</em>', re.S
        )
        page_reviews = []
        for full_href, aid, date, title in pattern.findall(html):
            title_clean = html_module.unescape(title).strip()
            if "еженедельный обзор" in title_clean.lower():
                page_reviews.append((int(aid), date.strip(), title_clean))

        new_on_page = [r for r in page_reviews if r[0] not in known_ids]
        found.extend(new_on_page)
        print(f"    Найдено обзоров на странице: {len(page_reviews)}, новых: {len(new_on_page)}")

        if any(aid in known_ids for aid, _, _ in page_reviews):
            print("    Дошли до уже известной статьи — останавливаемся.")
            break

        if not page_reviews:
            empty_streak += 1
            if empty_streak >= MAX_EMPTY_PAGES:
                print(f"    {MAX_EMPTY_PAGES} страниц подряд без обзоров — останавливаемся.")
                break
        else:
            empty_streak = 0

    return found


# ─────────────────────────────────────────
# Парсинг статьи
# ─────────────────────────────────────────

def html_to_text(raw_html: str) -> str:
    m = re.search(r'class="article"(.*?)class="other-articles"', raw_html, re.S)
    block = m.group(1) if m else raw_html
    text = re.sub(r"<script.*?</script>", " ", block, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = html_module.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def parse_date_range(title: str, article_id: int):
    m = re.search(r"с\s+(\d{2}/\d{2}/\d{2})\s+по\s+(\d{2}/\d{2}/\d{2})", title)
    if not m:
        return None, None
    def to_iso(d):
        dd, mm, yy = d.split("/")
        return f"20{yy}-{mm}-{dd}"
    return to_iso(m.group(1)), to_iso(m.group(2))


def extract_basis(tail: str) -> str:
    for kw in BASIS_KEYWORDS:
        if kw in tail.upper():
            return kw
    return ""


BULLET_RE = re.compile(
    r"▪️\s*([^\n]+?)\s*-\s*(\d+)\s*-\s*(\d+)\s*([^\n(]*)\(([+-]?\d+(?:[.,]\d+)?)\)"
)


def parse_section(text_block: str, orientation: str, currency: str, unit: str) -> list:
    records = []
    for m in BULLET_RE.finditer(text_block):
        label, price_min, price_max, tail, change = m.groups()
        label = label.strip(" -")
        basis = extract_basis(tail) or ("EXW" if orientation == "domestic" else "")
        records.append({
            "crop_label": label,
            "price_min": float(price_min),
            "price_max": float(price_max),
            "change": float(change.replace(",", ".")),
            "orientation": orientation,
            "currency": currency,
            "unit": unit,
            "basis": basis,
        })
    return records


def parse_article(text: str) -> list:
    """Разбивает текст на секцию внутреннего рынка (EXW, тыс.тенге/т) и
    секцию экспортных цен (USD/т), парсит буллеты в каждой."""
    records = []

    dom_match = re.search(
        r"EXW\s*-\s*элеватор.*?:\n(.*?)(?:-{5,}|Курсы валют)",
        text, re.S | re.IGNORECASE,
    )
    if dom_match:
        records += parse_section(dom_match.group(1), "domestic", "KZT", "тыс.тенге/т")

    exp_match = re.search(
        r"Экспортные цены,?\s*USD/тонна:\n(.*?)(?:Мука пшеничная|Пшенично-ячменная|Внутренний рынок:|-{5,})",
        text, re.S | re.IGNORECASE,
    )
    if exp_match:
        records += parse_section(exp_match.group(1), "export", "USD", "USD/т")

    return records


FX_SYMBOL_TO_CODE = {"$": "USD", "₽": "RUB", "€": "EUR", "¥": "CNY"}
FX_RE = re.compile(r"(\d+[.,]\d+)\D{0,12}?(\$|₽|€|¥)")


def parse_fx_rates(text: str) -> dict:
    """Извлекает курсы Нацбанка РК (теңге за единицу валюты) из блока
    'Курсы валют Нацбанка РК:' — эти курсы репортятся в каждом выпуске той
    же датой, что и цены, поэтому дают точный недельный KZT/USD без
    привязки к внешнему источнику валютных курсов."""
    m = re.search(r"Курсы валют.*?:\n(.*?)(?:-{5,}|Экспортные цены|$)", text, re.S | re.IGNORECASE)
    if not m:
        return {}
    block = m.group(1)
    rates = {}
    for value, symbol in FX_RE.findall(block):
        code = FX_SYMBOL_TO_CODE.get(symbol)
        if code and code not in rates:
            rates[code] = float(value.replace(",", "."))
    return rates


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────

FX_CSV = os.path.join(OUTPUT_DIR, "08_grainunion_fx_rates.csv")


def load_existing() -> pd.DataFrame:
    if os.path.exists(OUT_CSV):
        return pd.read_csv(OUT_CSV)
    return pd.DataFrame(columns=[
        "article_id", "date_from", "date_to", "crop_label", "price_min", "price_max",
        "change", "orientation", "currency", "unit", "basis",
    ])


def load_existing_fx() -> pd.DataFrame:
    if os.path.exists(FX_CSV):
        return pd.read_csv(FX_CSV)
    return pd.DataFrame(columns=["article_id", "date_from", "date_to", "USD", "RUB", "EUR", "CNY"])


def main():
    print("=" * 70)
    print("  Скрипт 08 — grainunion.kz: еженедельные обзоры внутреннего рынка")
    print("=" * 70)

    existing = load_existing()
    existing_fx = load_existing_fx()
    known_ids = set(existing["article_id"].unique().tolist()) if not existing.empty else set()
    print(f"\n  Уже собрано выпусков: {len(known_ids)}")

    print("\n  Поиск новых выпусков...")
    new_reviews = list_review_articles(known_ids)
    print(f"\n  Новых выпусков к обработке: {len(new_reviews)}")

    all_new_records = []
    all_new_fx = []
    for article_id, listed_date, title in new_reviews:
        cache_path = os.path.join(CACHE_DIR, f"{article_id}.html")
        if os.path.exists(cache_path):
            raw_html = open(cache_path, encoding="utf-8").read()
        else:
            url = ARTICLE_URL_TPL.format(article_id=article_id)
            print(f"  Скачивание [{article_id}]: {title[:60]}")
            try:
                raw_html = fetch(url)
            except requests.exceptions.RequestException as e:
                print(f"    ⚠ Ошибка: {e}")
                continue
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(raw_html)

        text = html_to_text(raw_html)
        date_from, date_to = parse_date_range(title, article_id)
        records = parse_article(text)
        fx = parse_fx_rates(text)
        print(f"    -> {len(records)} записей, период {date_from}..{date_to}, FX={fx}")

        for r in records:
            r["article_id"] = article_id
            r["date_from"] = date_from
            r["date_to"] = date_to
        all_new_records.extend(records)

        fx_row = {"article_id": article_id, "date_from": date_from, "date_to": date_to}
        fx_row.update(fx)
        all_new_fx.append(fx_row)

    if all_new_records:
        new_df = pd.DataFrame(all_new_records)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["article_id", "crop_label", "orientation", "basis"]
        )
        combined.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        print(f"\n  💾 Сохранено: {OUT_CSV}")
        print(f"  Всего записей: {len(combined)}, выпусков: {combined['article_id'].nunique()}")
    elif not existing.empty:
        print("\n  Новых выпусков нет, файл не менялся.")
        print(f"  Текущий объём: {len(existing)} записей, {existing['article_id'].nunique()} выпусков.")
    else:
        print("\n  ❌ Не удалось собрать ни одной записи.")

    if all_new_fx:
        new_fx_df = pd.DataFrame(all_new_fx)
        combined_fx = pd.concat([existing_fx, new_fx_df], ignore_index=True)
        combined_fx = combined_fx.drop_duplicates(subset=["article_id"])
        combined_fx.to_csv(FX_CSV, index=False, encoding="utf-8-sig")
        print(f"  💾 Курсы валют: {FX_CSV} ({len(combined_fx)} выпусков)")

    print("\n  Для регулярного сбора запускайте этот скрипт периодически")
    print("  (например, раз в неделю) — уже собранные выпуски не скачиваются заново.")


if __name__ == "__main__":
    main()
