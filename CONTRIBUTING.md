# Как вносить изменения

1. Создайте issue с описанием задачи или ошибки.
2. Сделайте ветку от `master` (`feature/<кратко>` или `fix/<кратко>`).
3. Перед коммитом локально: `pip install -r requirements.txt -r requirements-dev.txt`, затем `ruff check .` и `pytest`.
4. Откройте Pull Request; слияние возможно только при зелёном CI (GitHub Actions).
5. Исправления данных делаются в скриптах, а не правкой CSV вручную.
