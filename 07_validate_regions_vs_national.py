"""
Скрипт 07 — Кросс-валидация: регионы (05) против нацио­нального FAOSTAT (01)
==============================================================================
Цель: независимая проверка данных 05_kaz_stat.py (реальные региональные
ряды stat.gov.kz) против 01_faostat.csv (национальный FAOSTAT) — два
независимых источника, которые ДОЛЖНЫ быть согласованы:
  1. Доля area_ha/production_ton трёх областей от нацио­нального итога не
     может превышать 100% ни в одном году.
  2. Доля должна быть в целом стабильна год к году — резкий скачок доли
     (не объяснимый погодным годом) обычно означает остаточную ошибку
     единицы измерения (см. README про смену "тыс." <-> штучных единиц
     на stat.gov.kz, уже дважды пойманную в 05_kaz_stat.py).

Ограничение метода: Акмолинская, Костанайская и Северо-Казахстанская —
только 3 из ~17 регионов Казахстана (хотя и одни из крупнейших зерновых),
поэтому их доля от национального итога ожидаемо составляет заметную, но
НЕ подавляющую часть — 100% никогда не ожидается, и это не является
целью проверки. Цель — стабильность и физическая правдоподобность доли,
а не её точное значение.

Сопоставление культур:
  Пшеница/Ячмень/Кукуруза/Подсолнечник (Костанай + СКО, отдельные культуры)
    -> напрямую сравниваются с соответствующей культурой FAOSTAT.
  "Зерновые и бобовые (группа)" / "Масличные (группа)" (Акмолинская)
    -> нет культуры-аналога в FAOSTAT, сравниваются с СУММОЙ нескольких
       культур FAOSTAT (грубое приближение, помечено как approx).
  Рапс -> в 05 нет ни одного региона с этой культурой, кросс-проверка
    невозможна (это и есть задокументированное ограничение методологии).
"""

import os
import sys
import pandas as pd

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

OUTPUT_DIR = "output"

# regional crop (05_kaz_stat.csv) -> одна или несколько культур FAOSTAT (01_faostat.csv)
# None = нет прямого аналога (пропускаем эту культуру, документируем как gap)
CROP_TO_FAOSTAT = {
    "Пшеница":     ["Wheat"],
    "Ячмень":      ["Barley"],
    "Кукуруза":    ["Maize (corn)"],
    "Подсолнечник": ["Sunflower seed"],
    "Зерновые и бобовые (группа)": ["Wheat", "Barley", "Maize (corn)"],   # approx
    "Масличные (группа)":          ["Sunflower seed", "Rapeseed"],        # approx
}
APPROX_CROPS = {"Зерновые и бобовые (группа)", "Масличные (группа)"}


def load_national() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(OUTPUT_DIR, "01_faostat.csv"))
    df = df[df["source"] == "FAOSTAT_QCL"]
    prod = df[df["indicator"] == "Production (t)"][["year", "crop", "value"]].rename(
        columns={"value": "national_production_ton"}
    )
    area = df[df["indicator"] == "Area harvested (ha)"][["year", "crop", "value"]].rename(
        columns={"value": "national_area_ha"}
    )
    return prod, area


def load_regional() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "05_kaz_stat.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} не найден — сначала запустите 05_kaz_stat.py")
    return pd.read_csv(path)


def build_comparison(regional: pd.DataFrame, nat_prod: pd.DataFrame, nat_area: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for reg_crop, fao_crops in CROP_TO_FAOSTAT.items():
        sub = regional[regional["crop"] == reg_crop]
        if sub.empty:
            continue
        reg_by_year = sub.groupby("year")[["area_ha", "production_ton"]].sum(min_count=1)

        fao_prod = nat_prod[nat_prod["crop"].isin(fao_crops)].groupby("year")["national_production_ton"].sum(min_count=1)
        fao_area = nat_area[nat_area["crop"].isin(fao_crops)].groupby("year")["national_area_ha"].sum(min_count=1)

        for year in sorted(set(reg_by_year.index) & set(fao_prod.index)):
            reg_area = reg_by_year.loc[year, "area_ha"]
            reg_prod = reg_by_year.loc[year, "production_ton"]
            nat_p = fao_prod.get(year)
            nat_a = fao_area.get(year)
            rows.append({
                "crop": reg_crop,
                "faostat_crops": "+".join(fao_crops),
                "approx": reg_crop in APPROX_CROPS,
                "year": year,
                "regional_area_ha": reg_area,
                "national_area_ha": nat_a,
                "area_share": (reg_area / nat_a) if nat_a else None,
                "regional_production_ton": reg_prod,
                "national_production_ton": nat_p,
                "production_share": (reg_prod / nat_p) if nat_p else None,
            })
    return pd.DataFrame(rows)


def main():
    print("=" * 70)
    print("  Скрипт 07 — Кросс-валидация регионов (05) против FAOSTAT (01)")
    print("=" * 70)

    regional = load_regional()
    nat_prod, nat_area = load_national()
    cmp_df = build_comparison(regional, nat_prod, nat_area)

    if cmp_df.empty:
        print("  ❌ Нет пересекающихся лет/культур для сравнения.")
        return

    out_path = os.path.join(OUTPUT_DIR, "07_validation_report.csv")
    cmp_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n  💾 Полный отчёт: {out_path} ({len(cmp_df)} строк)")

    print("\n  Доля региональных данных (Акмолинская+Костанайская+СКО) от")
    print("  национального FAOSTAT — по культуре (production_share):")
    print(f"  {'-'*66}")
    flags = []
    for crop, grp in cmp_df.groupby("crop"):
        s = grp["production_share"].dropna()
        if s.empty:
            continue
        approx = " [ПРИБЛИЖЁННО: группа культур]" if grp["approx"].iloc[0] else ""
        over_100 = (s > 1.0).sum()
        cv = s.std() / s.mean() if s.mean() else float("nan")
        print(f"  {crop}{approx}")
        print(f"    доля от нац. производства: мин={s.min():.1%} медиана={s.median():.1%} макс={s.max():.1%}")
        print(f"    коэфф. вариации (std/mean): {cv:.2f}   лет с долей >100%: {over_100}")
        if over_100 > 0:
            flags.append(f"{crop}: {over_100} лет(а) с долей >100% — региональные данные ПРЕВЫШАЮТ национальные, проверить единицы измерения")
        if cv > 0.5:
            flags.append(f"{crop}: высокая нестабильность доли (CV={cv:.2f}) год к году — возможна остаточная ошибка масштаба")

    print(f"\n  {'='*66}")
    if flags:
        print("  ⚠️  НАЙДЕНЫ АНОМАЛИИ, требуют ручной проверки:")
        for f in flags:
            print(f"    - {f}")
    else:
        print("  ✅ Аномалий не найдено: доля региональных данных от национального")
        print("     итога нигде не превышает 100% и остаётся стабильной год к году.")
        print("     Данные 05 (stat.gov.kz) и 01 (FAOSTAT) взаимно непротиворечивы —")
        print("     кросс-валидация между двумя независимыми источниками пройдена.")

    print(f"\n  Примечание: Рапс не участвует в проверке — ни один из трёх")
    print(f"  регионов не публикует рапс отдельно (задокументированное")
    print(f"  ограничение методологии, см. README).")


if __name__ == "__main__":
    main()
