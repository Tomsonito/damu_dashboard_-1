"""Общее для всех тестов.

Тесты делятся на два сорта, и разница принципиальная:

- **чистые** — считают по конфигу и по коду, хранилище им не нужно
  (заголовки диаграмм, шлюз 9:00, разбор ключей страниц, макетные числа).
  Они обязаны проходить на пустой машине сразу после `git clone`;
- **на данных** — читают `data/analytics.duckdb`. Его в git нет намеренно
  (восстанавливается прогоном ETL), поэтому такие тесты помечены
  `@pytest.mark.needs_storage` и пропускаются, если файла нет.

Так набор не превращается в «у меня всё зелёное, а у тебя ничего
не запускается»: на чужой машине пропущенное видно в отчёте отдельной
строкой, а не выглядит как поломка.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Тесты запускают из корня (`python -m pytest`), но подстрахуемся:
# импорты вида `from core import data` должны работать при любом способе
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STORAGE = ROOT / "data" / "analytics.duckdb"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "needs_storage: тесту нужно data/analytics.duckdb — "
        "без него пропускается",
    )


def pytest_collection_modifyitems(config, items):
    if STORAGE.exists():
        return
    skip = pytest.mark.skip(reason="нет data/analytics.duckdb — "
                                   "запустите `python -m etl.run`")
    for item in items:
        if "needs_storage" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def facts():
    """Таблица фактов целиком — общая на всю сессию тестов.

    Читается один раз: чтение стоит около полусекунды (замерено
    11.08.2026 — 292 мс DuckDB плюс 184 мс на перевод разрезов
    в категории), а тестов, которым она нужна, несколько.
    """
    from core import data
    return data.load_facts()
