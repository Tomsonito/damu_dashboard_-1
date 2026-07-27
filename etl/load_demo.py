"""Разборщик демо-выгрузки: Excel из data/raw/ -> таблица `demo_facts`.

Обычный маленький разборщик, каких в проекте уже два (`parse_msp.py` для
Excel, `load_budget.py` для базы). Архитектура «узкая талия» ровно это
и предполагает: новый источник = новый разборщик, приводящий свои данные
к общей форме таблицы фактов. Страницы и диаграммы при этом не трогаются.

Отличие от собратьев одно, и оно намеренное: пишет **не в `facts`**,
а в отдельную таблицу `demo_facts` той же формы. Причин две.

1. `facts` ведёт `etl/run.py`: каждый прогон кладёт туда новый снимок
   версии. Демо-строки в этом снимке отсутствовали бы, и первый же прогон
   их «потерял» бы — точнее, они просто не попали бы в свежую версию.
2. Смешать выдуманные числа с настоящими в одной таблице — плохая идея
   сама по себе. В отдельной таблице их видно, и удаляются они одной
   строкой SQL.

Сайт подмешивает демо-строки к настоящим только когда в `config.yaml`
стоит `demo_data: true` (см. `load_facts()` в `core/data.py`).

Запуск из корня проекта:

    python -m etl.load_demo
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from core.data import _connect_write

DEFAULT_PATH = Path("data/raw/demo_показатели.xlsx")

#: Колонки таблицы фактов — в этот вид приводим что угодно.
#: Порядок важен: `demo_facts` создаётся по этому же списку.
FACT_COLUMNS = [
    "indicator", "report_year", "date", "period", "region",
    "instrument", "program", "is_total", "value", "source_file", "loaded_at",
]


def parse(path: Path) -> pd.DataFrame:
    """Excel -> длинная таблица фактов.

    Русские заголовки файла (его открывают глазами) переводятся в
    английские имена колонок хранилища. Раздел уезжает в `program` —
    туда же, куда лягут настоящие программы, когда появятся.
    """
    raw = pd.read_excel(path, sheet_name="Данные")

    missing = {"Раздел", "Код показателя", "Область", "Год", "Месяц", "Значение"} - set(raw.columns)
    if missing:
        raise ValueError(f"В файле нет колонок: {', '.join(sorted(missing))}")

    df = pd.DataFrame({
        "indicator": raw["Код показателя"],
        "report_year": raw["Год"].astype(int),
        # Дата — первое число месяца, строкой: в `facts` она тоже строка
        "date": pd.to_datetime(
            dict(year=raw["Год"], month=raw["Месяц"], day=1)
        ).dt.strftime("%Y-%m-%d"),
        "period": "month",
        "region": raw["Область"],
        "instrument": "",
        "program": raw["Раздел"],
        # Строк-итогов в демо-данных нет: итог по стране считается сложением
        "is_total": False,
        "value": raw["Значение"].astype(float),
        "source_file": f"демо: {path.name}",
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    })
    return df[FACT_COLUMNS]


def load(path: Path = DEFAULT_PATH) -> int:
    """Разбирает файл и полностью заменяет содержимое `demo_facts`.

    Именно заменяет, а не дописывает: демо-данные — не история, а один
    слепок для макета. Повторный запуск не должен их удваивать.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла {path}. Сначала создайте его:\n"
            "  python -m etl.make_samples --excel"
        )

    df = parse(path)
    con = _connect_write()
    try:
        con.execute("BEGIN")
        con.register("fresh_demo", df)
        con.execute("DROP TABLE IF EXISTS demo_facts")
        con.execute("CREATE TABLE demo_facts AS SELECT * FROM fresh_demo")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()

    print(f"в demo_facts загружено строк: {len(df):,}".replace(",", " "))
    print("показать их на сайте: config.yaml -> demo_data: true")
    return len(df)


def main() -> None:
    load()


if __name__ == "__main__":
    main()
