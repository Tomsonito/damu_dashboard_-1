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
import contextlib
import logging
import math
import os
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from core import cache, db, monitoring, publish
from etl import load_budget

DB_PATH = Path("data/analytics.duckdb")
LOG_PATH = Path("data/etl.log")
LOCK_PATH = Path("data/etl.lock")

#: Через сколько замок считается брошенным. Прогон, переживший это время,
#: почти наверняка не идёт, а был убит вместе с процессом (перезагрузка,
#: kill -9, падение контейнера) — иначе замок сняла бы сама программа.
#: Полчаса взяты с запасом: полный прогон сейчас укладывается в секунды,
#: и даже вырасти он в сто раз, до получаса ему далеко.
LOCK_STALE_AFTER = 30 * 60

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


@contextlib.contextmanager
def single_run():
    """Пускает внутрь один прогон за раз; второй молча уходит.

    Зачем. Cron запускает `etl.run` каждые пять минут и НЕ спрашивает,
    закончился ли прошлый (найдено внешним аудитом 18.08.2026). Пока
    прогон укладывается в секунды, это безобидно; стоит источнику
    вырасти — и два прогона пойдут внахлёст, оба потянут факты из боевой
    БД и подерутся за файл хранилища.

    `!!` Замок сделан ЗДЕСЬ, а не флагом `flock` в crontab, и это
    осознанно. `flock` пришлось бы не забыть дописать в задание — то есть
    защита держалась бы на памяти администратора и работала бы только
    у запуска из cron, но не у запуска руками. Здесь она есть при любом
    способе запуска. Заодно код остаётся переносимым: `flock` — команда
    Linux, а разработка идёт под Windows.

    `!!` Второй прогон уходит БЕЗ ошибки, но со строкой в журнале.
    Наложение — это не поломка (первый прогон делает ровно ту же работу),
    и падать из-за него значит слать cron письма об ошибке пять раз
    в час. Но и молчать нельзя: если наложения пошли подряд, это первый
    признак, что прогон перестал укладываться в свои пять минут.

    Брошенный замок (процесс убили, замок остался) снимается по возрасту,
    см. `LOCK_STALE_AFTER`. Иначе одно падение остановило бы ETL навсегда,
    а заметили бы это по остывшим данным через сутки.
    """
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_PATH.exists():
        age = time.time() - LOCK_PATH.stat().st_mtime
        if age < LOCK_STALE_AFTER:
            log.info("прогон уже идёт (замок %s, возраст %.0f сек) — пропускаем",
                     LOCK_PATH, age)
            yield False
            return
        log.warning("замок %s брошен (возраст %.0f сек > %d) — снимаем и работаем",
                    LOCK_PATH, age, LOCK_STALE_AFTER)
        LOCK_PATH.unlink(missing_ok=True)

    # !! Создаём с O_EXCL: проверка выше и создание — не одно действие,
    # и между ними может вклиниться сосед. O_EXCL делает создание
    # неделимым, поэтому гонку выигрывает ровно один.
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        log.info("прогон уже идёт (замок занят соседом) — пропускаем")
        yield False
        return

    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"pid={os.getpid()} started={datetime.now():%Y-%m-%d %H:%M:%S}\n")
        yield True
    finally:
        LOCK_PATH.unlink(missing_ok=True)


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
    if monitoring.init_etl():
        log.info("Sentry подключён — ошибки прогона дублируются в кабинет")
    try:
        # Замок снаружи run(): наложившийся прогон не должен делать вообще
        # ничего — ни ходить в боевую БД за отпечатком, ни дёргать шлюз
        with single_run() as got_lock:
            if not got_lock:
                return
            run(force=args.force)
    except Exception:
        # В лог — с полным следом: cron ошибок не показывает, файл — единственный свидетель.
        #
        # !! Если Sentry подключён (monitoring.init_etl), ЭТО ЖЕ исключение
        # уйдёт и туда — но не потому, что оно «необработанное». Мы его как
        # раз обрабатываем сами (except + SystemExit), и глобальный перехват
        # sentry_sdk такое не увидит. Работает это через LoggingIntegration:
        # у неё по умолчанию event_level=ERROR, и log.exception() — это
        # ERROR-запись со стектрейсом, её она превращает в событие сама.
        # Проверено вживую (без сети, с подменённым transport): 11.08.2026.
        #
        # Значит explicit sentry_sdk.capture_exception() здесь не нужен,
        # НО если строку заменят на log.error(..., exc_info=False) или
        # понизят уровень логгера ниже ERROR — отправка в Sentry молча
        # прекратится, а в data/etl.log ошибка как была, так и останется.
        log.exception("прогон упал")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
