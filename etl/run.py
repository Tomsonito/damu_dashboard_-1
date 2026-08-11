"""Прогон ETL: боевая БД -> хранилище data/analytics.duckdb.

Этот скрипт будет дёргать cron каждые 5 минут (этап 5), поэтому он обязан
быть дешёвым в холостую. Порядок работы:

1. Дешёвая проверка «изменился ли источник»: один запрос к служебной
   статистике PostgreSQL, сами данные не читаются.
2. Отпечаток совпал с прошлым прогоном — выход за секунды.
3. Не совпал — забираем факты, пишем в DuckDB и сверяем контрольные
   суммы с базой. Не сошлось — откат: в хранилище остаётся прошлая
   версия, а не кривая новая.

С этапа 4 свежая загрузка НЕ показывается сайту сразу: она ложится
снимком под новым номером версии со статусом «ждёт публикации», и до
своих 9:00 её можно забраковать (core/publish.py). Сайт показывает
версию со статусом «опубликована». Исключение — самая первая загрузка
в жизни хранилища: ей нечего ждать, она публикуется сразу.

Каждый прогон — и холостой, и полный — пишется в лог data/etl.log
и заодно публикует всё, чей срок уже наступил.

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

from core import cache, db, publish
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


def source_fingerprint() -> str:
    row = db.read_sql(FINGERPRINT_QUERY).iloc[0]
    return f"{int(row.tables)} таблиц / {int(row.live_rows)} строк / {int(row.changes)} изменений"


def last_fingerprint(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute("SELECT fingerprint FROM versions ORDER BY version DESC LIMIT 1").fetchone()
    return row[0] if row else None


def verify(con: duckdb.DuckDBPyConnection, tables: list[str], version: int) -> list[str]:
    """Сверка записанного с источником. Возвращает список расхождений.

    Суммы по каждому показателю считаются в PostgreSQL заново — но другим
    запросом: напрямую по исходным колонкам, без разворота в длинную форму.
    Если разборщик где-то потерял или задвоил строки, суммы разойдутся.
    Сверка тем же запросом, что и загрузка, не поймала бы ничего.

    Сверяется только свежий снимок (`version`): рядом в той же таблице
    лежат снимки прошлых версий, и суммироваться с новым они не должны.
    """
    union = " UNION ALL ".join(f'SELECT * FROM public."{t}"' for t in tables)
    parts = [
        f"SELECT '{code}' AS indicator, sum({column})::double precision AS value FROM all_months"
        for column, (code, _) in load_budget.INDICATORS.items()
    ]
    expected = db.read_sql(f"WITH all_months AS ({union})\n" + "\nUNION ALL\n".join(parts))

    actual = con.execute(
        "SELECT indicator, sum(value) AS value FROM facts WHERE version = ? GROUP BY indicator",
        [version],
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


def publish_pending() -> None:
    """Публикует всё, чей срок наступил. Ошибка публикации прогон не валит:
    данные уже загружены, а публикацию повторит и сайт, и следующий прогон."""
    try:
        result = publish.publish_due()
    except Exception:
        log.exception("публикация дозревшего не прошла")
        return
    if result:
        log.info("опубликовано: %s", result)


def run(force: bool) -> None:
    started = time.perf_counter()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    # Закрыть соединение обязательно, а не «само закроется с процессом»:
    # открытое на запись, оно держит файл запертым — сайт всё это время
    # не может ни читать, ни публиковать
    try:
        _run(con, force, started)
    finally:
        con.close()
    # Шлюз 9:00 — строго ПОСЛЕ закрытия соединения: publish_due открывает
    # своё, а на чужом, только что принявшем большую вставку, ловилась
    # внутренняя ошибка DuckDB (подробности — в докстринге publish_due)
    publish_pending()


def _run(con: duckdb.DuckDBPyConnection, force: bool, started: float) -> None:
    # Схема и миграция старого хранилища — у core/publish.py, он хозяин схемы
    publish.migrate(con)

    fingerprint = source_fingerprint()
    previous = last_fingerprint(con)
    if fingerprint == previous and not force:
        log.info(
            "источник не менялся (%s) — пересчёт пропущен, %.1f сек",
            fingerprint, time.perf_counter() - started,
        )
        return  # но шлюз 9:00 всё равно проверится — в run(), после закрытия

    if force and fingerprint == previous:
        reason = "запуск с --force"
    elif previous is None:
        reason = "первая загрузка"
    else:
        reason = f"отпечаток изменился: было «{previous}», стало «{fingerprint}»"
    log.info("пересчёт: %s", reason)

    tables = load_budget.month_tables()
    df = load_budget.load()

    # Снимок фактов и строка версии — одной транзакцией: если сверка не
    # сошлась или запись оборвалась, откат вернёт прошлое состояние целиком.
    # Момента «снимок уже лежит, а версии ещё нет» не существует.
    con.execute("BEGIN")
    try:
        version = con.execute("SELECT coalesce(max(version), 0) + 1 FROM versions").fetchone()[0]
        df["version"] = version
        con.register("fresh_facts", df)

        # Снимки копятся рядом со старыми, а не затирают их: сайт продолжает
        # показывать опубликованную версию, пока свежая ждёт своих 9:00
        facts_exists = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'facts'"
        ).fetchone()[0]
        if facts_exists:
            con.execute("INSERT INTO facts BY NAME SELECT * FROM fresh_facts")
        else:
            con.execute("CREATE TABLE facts AS SELECT * FROM fresh_facts")

        problems = verify(con, tables, version)
        if problems:
            raise RuntimeError("сверка с БД не сошлась: " + "; ".join(problems))

        # Первой версии в жизни хранилища ждать нечего — до неё сайту
        # было нечего показывать. Остальные ждут своих 9:00.
        bootstrap = con.execute(
            "SELECT count(*) FROM versions WHERE status = ?", [publish.VER_PUBLISHED]
        ).fetchone()[0] == 0
        status = publish.VER_PUBLISHED if bootstrap else publish.VER_PENDING

        duration = time.perf_counter() - started
        now = datetime.now()
        con.execute(
            """INSERT INTO versions
               (version, run_at, fingerprint, facts_rows, duration_sec, status, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [version, now, fingerprint, len(df), round(duration, 1),
             status, now if bootstrap else None],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    log.info(
        "версия %d: %s строк, сверка по %d показателям сошлась, %.1f сек — %s",
        version, f"{len(df):,}".replace(",", " "), len(load_budget.INDICATORS), duration,
        "опубликована сразу (первая)" if bootstrap
        else f"ждёт публикации {publish.describe_publish_time(publish.next_publish_time(now))}",
    )

    # Новая версия — значит записи кэша со старым номером больше никто
    # не спросит. Чистим здесь же: прогон ETL и есть тот момент, когда
    # мусор появляется. Упавшая чистка прогон не роняет — данные уже легли.
    try:
        removed, left_mb = cache.sweep()
        if removed:
            log.info("кэш: убрано %d старых записей, осталось %.0f МБ",
                     removed, left_mb)
    except Exception:
        log.exception("чистка кэша после прогона не удалась")


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
