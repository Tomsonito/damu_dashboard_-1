"""Прогон ETL: боевая БД -> хранилище data/analytics.duckdb.

Этот скрипт будет дёргать cron каждые 5 минут (этап 5), поэтому он обязан
быть дешёвым в холостую. Порядок работы:

1. Дешёвая проверка «изменился ли источник»: один запрос к служебной
   статистике PostgreSQL, сами данные не читаются.
2. Отпечаток совпал с прошлым прогоном — выход за секунды.
3. Не совпал — забираем факты, пишем в DuckDB и сверяем контрольные
   суммы с базой. Не сошлось — откат: в хранилище остаётся прошлая
   версия, а не кривая новая.

Каждый прогон — и холостой, и полный — пишется в лог data/etl.log.

Запуск из корня проекта:   python -m etl.run
Пересчёт без проверки:     python -m etl.run --force
"""

import argparse
import logging
import math
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from core import db
from etl import load_budget

DB_PATH = Path("data/analytics.duckdb")
LOG_PATH = Path("data/etl.log")

log = logging.getLogger("etl")

# Отпечаток источника. Колонок updated_at в базе нет, поэтому берём
# накопительные счётчики PostgreSQL: сколько строк вставлено, изменено
# и удалено за всю жизнь таблиц. Любая правка данных сдвигает счётчик.
# Сброс статистики сервера собьёт отпечаток — тогда пересчитаем лишний
# раз. Ошибка идёт в безвредную сторону: пропустить изменения нельзя.
FINGERPRINT_QUERY = f"""
SELECT count(*)                                            AS tables,
       coalesce(sum(n_live_tup), 0)                        AS live_rows,
       coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) AS changes
FROM pg_stat_user_tables
WHERE relname LIKE '{load_budget.TABLE_PREFIX}%'
"""


def setup_logging() -> None:
    """Лог в файл и в консоль одновременно.

    Файл — для cron: когда прогоны пойдут по расписанию, консоль никто
    не увидит. Консоль — для ручного запуска, чтобы не открывать файл.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS versions (
               version      INTEGER   NOT NULL,  -- порядковый номер загрузки
               run_at       TIMESTAMP NOT NULL,
               fingerprint  VARCHAR   NOT NULL,  -- отпечаток источника на момент загрузки
               facts_rows   BIGINT    NOT NULL,
               duration_sec DOUBLE    NOT NULL
           )"""
    )


def source_fingerprint() -> str:
    row = db.read_sql(FINGERPRINT_QUERY).iloc[0]
    return f"{int(row.tables)} таблиц / {int(row.live_rows)} строк / {int(row.changes)} изменений"


def last_fingerprint(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute("SELECT fingerprint FROM versions ORDER BY version DESC LIMIT 1").fetchone()
    return row[0] if row else None


def verify(con: duckdb.DuckDBPyConnection, tables: list[str]) -> list[str]:
    """Сверка записанного с источником. Возвращает список расхождений.

    Суммы по каждому показателю считаются в PostgreSQL заново — но другим
    запросом: напрямую по исходным колонкам, без разворота в длинную форму.
    Если разборщик где-то потерял или задвоил строки, суммы разойдутся.
    Сверка тем же запросом, что и загрузка, не поймала бы ничего.
    """
    union = " UNION ALL ".join(f'SELECT * FROM public."{t}"' for t in tables)
    parts = [
        f"SELECT '{code}' AS indicator, sum({column})::double precision AS value FROM all_months"
        for column, (code, _) in load_budget.INDICATORS.items()
    ]
    expected = db.read_sql(f"WITH all_months AS ({union})\n" + "\nUNION ALL\n".join(parts))

    actual = con.execute(
        "SELECT indicator, sum(value) AS value FROM facts GROUP BY indicator"
    ).df()

    # База — слева: ловим показатели, которые потерялись или съехали.
    # Лишние показатели в хранилище (другие источники) сверке не мешают.
    merged = expected.merge(actual, on="indicator", how="left", suffixes=("_source", "_duck"))
    problems = []
    for row in merged.itertuples():
        ok = (
            not pd.isna(row.value_duck)
            and math.isclose(row.value_source, row.value_duck, rel_tol=1e-9, abs_tol=1e-6)
        )
        if not ok:
            problems.append(f"{row.indicator}: в БД {row.value_source}, в DuckDB {row.value_duck}")
    return problems


def run(force: bool) -> None:
    started = time.perf_counter()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    ensure_schema(con)

    fingerprint = source_fingerprint()
    previous = last_fingerprint(con)
    if fingerprint == previous and not force:
        log.info(
            "источник не менялся (%s) — пересчёт пропущен, %.1f сек",
            fingerprint, time.perf_counter() - started,
        )
        return

    if force and fingerprint == previous:
        reason = "запуск с --force"
    elif previous is None:
        reason = "первая загрузка"
    else:
        reason = f"отпечаток изменился: было «{previous}», стало «{fingerprint}»"
    log.info("пересчёт: %s", reason)

    tables = load_budget.month_tables()
    df = load_budget.load()

    # Факты и строка версии — одной транзакцией: если сверка не сошлась
    # или запись оборвалась, откат вернёт прошлое состояние целиком.
    # Момента «данные уже затёрты, а версии ещё нет» не существует.
    con.execute("BEGIN")
    try:
        con.register("fresh_facts", df)
        con.execute("CREATE OR REPLACE TABLE facts AS SELECT * FROM fresh_facts")

        problems = verify(con, tables)
        if problems:
            raise RuntimeError("сверка с БД не сошлась: " + "; ".join(problems))

        version = con.execute("SELECT coalesce(max(version), 0) + 1 FROM versions").fetchone()[0]
        duration = time.perf_counter() - started
        con.execute(
            "INSERT INTO versions VALUES (?, ?, ?, ?, ?)",
            [version, datetime.now(), fingerprint, len(df), round(duration, 1)],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    log.info(
        "версия %d: %s строк, сверка по %d показателям сошлась, %.1f сек",
        version, f"{len(df):,}".replace(",", " "), len(load_budget.INDICATORS), duration,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Прогон ETL: PostgreSQL -> DuckDB")
    parser.add_argument(
        "--force", action="store_true",
        help="пересчитать, даже если источник не менялся",
    )
    args = parser.parse_args()

    setup_logging()
    try:
        run(force=args.force)
    except Exception:
        # В лог — с полным следом: cron ошибок не показывает, файл — единственный свидетель
        log.exception("прогон упал")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
