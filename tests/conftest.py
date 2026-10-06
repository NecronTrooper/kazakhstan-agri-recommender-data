"""
Общие фикстуры для тестов данных и пайплайна.

Тесты не ходят в сеть: они читают готовые output/*.csv и импортируют чистые
функции из скриптов (имена файлов начинаются с цифры - обычный import невозможен,
поэтому загрузка через importlib).

Пороги в тестах выведены из РЕАЛЬНЫХ данных на 2026-10-05 (см. README, раздел
"Районный master-датасет") с запасом - это инварианты "физически возможно",
а не "в точности как сейчас".
"""

import importlib.util
import os

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")


def load_script(filename: str):
    """Импортирует скрипт пайплайна по имени файла (например '12_district_coords.py')."""
    path = os.path.join(ROOT, filename)
    spec = importlib.util.spec_from_file_location("script_" + filename.split(".")[0], path)
    mod = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    os.chdir(ROOT)  # скрипты используют относительные пути (OUTPUT_DIR = "output")
    try:
        spec.loader.exec_module(mod)
    finally:
        os.chdir(cwd)
    return mod


def read_csv(name: str) -> pd.DataFrame:
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        pytest.skip(f"нет файла {name} - запустите соответствующий скрипт пайплайна")
    return pd.read_csv(path)


@pytest.fixture(scope="session")
def districts() -> pd.DataFrame:
    return read_csv("master_dataset_districts.csv")


@pytest.fixture(scope="session")
def coords() -> pd.DataFrame:
    return read_csv("12_district_coords.csv")


@pytest.fixture(scope="session")
def climate() -> pd.DataFrame:
    return read_csv("13_era5_districts_features.csv")


@pytest.fixture(scope="session")
def soil() -> pd.DataFrame:
    return read_csv("14_soilgrids_districts.csv")


@pytest.fixture(scope="session")
def faostat() -> pd.DataFrame:
    return read_csv("01_faostat.csv")


@pytest.fixture(scope="session")
def prices() -> pd.DataFrame:
    return read_csv("02_worldbank_prices.csv")


@pytest.fixture(scope="session")
def soil_grid() -> pd.DataFrame:
    return read_csv("04_soilgrids_wide.csv")


@pytest.fixture(scope="session")
def regional() -> pd.DataFrame:
    return read_csv("05_kaz_stat.csv")


@pytest.fixture(scope="session")
def s12():
    return load_script("12_district_coords.py")


@pytest.fixture(scope="session")
def s13():
    return load_script("13_era5_districts.py")


@pytest.fixture(scope="session")
def s15():
    return load_script("15_merge_districts.py")


@pytest.fixture(scope="session")
def s04():
    return load_script("04_soilgrids.py")


@pytest.fixture(scope="session")
def prices_monthly() -> pd.DataFrame:
    return read_csv("16_producer_prices_monthly.csv")


@pytest.fixture(scope="session")
def prices_annual() -> pd.DataFrame:
    return read_csv("16_producer_prices_annual.csv")


@pytest.fixture(scope="session")
def s16():
    return load_script("16_stat_producer_prices.py")
