"""Словарь данных должен описывать каждый столбец районного master-датасета."""


def test_every_column_is_described(districts):
    s17 = __import__("conftest").load_script("17_data_dictionary.py")
    missing = [c for c in districts.columns if c not in s17.DESCRIPTIONS]
    stale = [c for c in s17.DESCRIPTIONS if c not in districts.columns]
    assert not missing, f"нет описания: {missing}"
    assert not stale, f"описание без столбца: {stale}"


def test_descriptions_are_not_empty(districts):
    s17 = __import__("conftest").load_script("17_data_dictionary.py")
    for col, (unit, text, group, src) in s17.DESCRIPTIONS.items():
        assert unit.strip() and len(text.strip()) > 3, col
