"""Отложенная публикация: правки ждут ближайших 9:00, до этого их можно отменить.

Правило одно на всё: то, что появилось в момент T, публикуется в ближайшие
9:00 СТРОГО ПОСЛЕ T. Правка в 16:00 вторника выходит в среду утром; правка
в 8:00 — в те же 9:00, через час. Повторная правка сдвигает срок заново.

Под правилом живут две разные вещи:

- **план** — строки таблицы `plan` со статусом draft. В 9:00 черновик
  становится published и с этого момента виден витрине. Отмена черновика —
  просто удаление строки, published-строк она не трогает.
- **версии данных из БД** — каждый прогон etl.run со свежими данными кладёт
  снимок фактов под новым номером версии со статусом pending. Сайт показывает
  версию со статусом published; в 9:00 публикуется самая свежая из pending.
  Админ может забраковать pending-версию — тогда опубликуется предыдущая
  незабракованная, а сайт до тех пор продолжает показывать старую.

Решения, принятые 23.07.2026 (подробный разбор — в ROADMAP, этап 4):
- публикуем каждый день, включая выходные — календаря в коде нет;
- время — по часам сервера, часовых поясов в коде нет; требование
  «часы сервера стоят на казахстанском времени» уйдёт в памятку этапа 5;
- сервер лежал в 9:00 — публикуем при первом же запуске после подъёма:
  publish_due() смотрит не «сейчас ровно 9:00?», а «наступил ли срок»;
- вето снимает админ вручную, и оно касается только самой забракованной
  версии (@@ к этому вопросу решили вернуться — возможно, переделаем);
- уведомление о версии на рассмотрении — плашка на сайте, только админу.

Кто дёргает publish_due(): опрос свежести на страницах (раз в 30 сек)
и каждый прогон etl.run — даже холостой. Отдельного планировщика нет
намеренно: оба вызова и так происходят регулярно, а холостая проверка
стоит два маленьких чтения.

Разделение труда с core/data.py: data.py — чтение для витрины,
этот модуль — запись и жизненный цикл (черновики, вето, 9:00).
Страницы по-прежнему не открывают хранилище сами.
"""

import time
from datetime import datetime, timedelta

import duckdb
import pandas as pd

from core.data import DUCKDB_PATH, _query_storage

PUBLISH_HOUR = 9

# Статусы — английские коды, как и весь код; русские подписи для экрана
# лежат в STATUS_LABELS, чтобы интерфейс не изобретал их сам.
PLAN_DRAFT = "draft"
PLAN_PUBLISHED = "published"

VER_PENDING = "pending"        # разобрана, ждёт своих 9:00
VER_PUBLISHED = "published"    # её показывает сайт; такая всегда одна
VER_REJECTED = "rejected"      # забракована админом, публикации не подлежит
VER_SUPERSEDED = "superseded"  # устарела: позже неё опубликована другая

STATUS_LABELS = {
    VER_PENDING: "ждёт публикации",
    VER_PUBLISHED: "опубликована",
    VER_REJECTED: "забракована",
    VER_SUPERSEDED: "заменена",
}

# Сколько снимков фактов держать позади опубликованного — про запас
# на откат («вернуть отметку на предыдущую версию»). Более старые
# снимки заменённых версий вычищаются при публикации; сами строки
# в `versions` остаются все — это журнал.
KEEP_SNAPSHOTS = 3


# ---------------------------------------------------------------- время

def next_publish_time(after: datetime) -> datetime:
    """Ближайшие 9:00 строго после момента `after` — когда правка выйдет."""
    nine = after.replace(hour=PUBLISH_HOUR, minute=0, second=0, microsecond=0)
    return nine + timedelta(days=1) if after >= nine else nine


def last_deadline(now: datetime) -> datetime:
    """Последний рубеж 9:00, который уже наступил к моменту `now`.

    Зеркало next_publish_time: правка со штампом T дозрела до публикации
    ровно тогда, когда T < last_deadline(now). Сравнение со штампом одним
    неравенством — вот зачем эта функция, оно уходит прямо в SQL.
    """
    nine = now.replace(hour=PUBLISH_HOUR, minute=0, second=0, microsecond=0)
    return nine if now >= nine else nine - timedelta(days=1)


def describe_publish_time(moment: datetime, now: datetime | None = None) -> str:
    """«сегодня в 09:00» / «завтра в 09:00» / дата — для подписей на экране."""
    now = now or datetime.now()
    day = (moment.date() - now.date()).days
    when = {0: "сегодня", 1: "завтра"}.get(day, moment.strftime("%d.%m"))
    return f"{when} в {moment.strftime('%H:%M')}"


# ------------------------------------------------------------- хранилище

def _connect_write() -> duckdb.DuckDBPyConnection:
    """Соединение на запись, с повторами.

    Файл может быть заперт прогоном etl.run — это доли секунды раз
    в несколько минут. Логика та же, что у чтения в core/data.py.
    """
    last_error: Exception | None = None
    for _ in range(5):
        try:
            return duckdb.connect(str(DUCKDB_PATH))
        # IOException — файл заперт другим процессом (etl.run пишет).
        # ConnectionException — в ЭТОМ процессе прямо сейчас открыто
        # читающее соединение (другой поток сайта): DuckDB не смешивает
        # чтение и запись в одном процессе. И то и другое лечится ожиданием.
        except (duckdb.IOException, duckdb.ConnectionException) as e:
            last_error = e
            time.sleep(0.2)
    raise RuntimeError(f"Хранилище {DUCKDB_PATH} занято записью: {last_error}")


def ensure_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Создаёт таблицы публикации, если их нет. Безопасно звать сколько угодно.

    Схема `versions` описана здесь, а не в etl/run.py, чтобы у неё был
    один хозяин: и ETL, и сайт зовут этот код.
    """
    con.execute(
        """CREATE TABLE IF NOT EXISTS versions (
               version      INTEGER   NOT NULL,  -- порядковый номер загрузки
               run_at       TIMESTAMP NOT NULL,
               fingerprint  VARCHAR   NOT NULL,  -- отпечаток источника на момент загрузки
               facts_rows   BIGINT    NOT NULL,
               duration_sec DOUBLE    NOT NULL,
               status       VARCHAR,             -- pending/published/rejected/superseded
               published_at TIMESTAMP
           )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS plan (
               indicator    VARCHAR   NOT NULL,  -- ключ показателя из config.yaml
               program      VARCHAR,             -- разрез по программам; пока пусто, в данных его нет
               period_year  INTEGER   NOT NULL,
               value        DOUBLE    NOT NULL,  -- в единицах показателя из config.yaml (unit)
               author       VARCHAR   NOT NULL,
               updated_at   TIMESTAMP NOT NULL,  -- когда автор сохранил; от этого штампа считается срок
               status       VARCHAR   NOT NULL,  -- draft | published
               published_at TIMESTAMP
           )"""
    )


def migrate(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """Доводит хранилище, созданное до этапа 4, до новой схемы.

    Старый файл: в `versions` нет статусов, в `facts` нет номера версии,
    таблицы `plan` нет вовсе. Правила переноса: последняя версия — та,
    что уже показывалась на сайте, она и объявляется опубликованной;
    все строки фактов принадлежат ей (старые снимки не хранились).

    Зовут при старте сайта (app.py) и в начале каждого прогона etl.run.
    Повторный вызов ничего не меняет — все шаги «если ещё не сделано».
    """
    own = con is None
    if own:
        if not DUCKDB_PATH.exists():
            return  # хранилища ещё нет — его создаст первый прогон ETL
        con = _connect_write()
    try:
        ensure_schema(con)
        con.execute("ALTER TABLE versions ADD COLUMN IF NOT EXISTS status VARCHAR")
        con.execute("ALTER TABLE versions ADD COLUMN IF NOT EXISTS published_at TIMESTAMP")
        has_facts = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'facts'"
        ).fetchone()[0]
        if has_facts:
            con.execute("ALTER TABLE facts ADD COLUMN IF NOT EXISTS version INTEGER")
            con.execute(
                "UPDATE facts SET version = (SELECT max(version) FROM versions) "
                "WHERE version IS NULL"
            )
        con.execute(
            "UPDATE versions SET status = ? WHERE status IS NULL "
            "AND version < (SELECT max(version) FROM versions)",
            [VER_SUPERSEDED],
        )
        con.execute(
            "UPDATE versions SET status = ? WHERE status IS NULL", [VER_PUBLISHED]
        )
    finally:
        if own:
            con.close()


def _plan_table_ready() -> bool:
    """Есть ли таблица plan — старый файл до миграции её не имеет."""
    df = _query_storage(
        "SELECT count(*) AS n FROM information_schema.tables WHERE table_name = 'plan'"
    )
    return bool(df.iloc[0]["n"])


# ------------------------------------------------------------- черновики

def save_draft(indicator: str, period_year: int, value: float, author: str) -> datetime:
    """Сохраняет черновик плана; возвращает момент, когда он опубликуется.

    Повторная правка того же показателя и года заменяет прежний черновик —
    строки не копятся, а срок публикации отсчитывается от новой правки.
    Опубликованную строку черновик не трогает: она живёт рядом, пока
    в 9:00 её не заменит этот черновик.
    """
    now = datetime.now()
    con = _connect_write()
    try:
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM plan WHERE status = ? AND indicator = ? AND period_year = ? "
            "AND coalesce(program, '') = ''",
            [PLAN_DRAFT, indicator, period_year],
        )
        con.execute(
            "INSERT INTO plan (indicator, program, period_year, value, author, "
            "updated_at, status, published_at) VALUES (?, NULL, ?, ?, ?, ?, ?, NULL)",
            [indicator, period_year, value, author, now, PLAN_DRAFT],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return next_publish_time(now)


def delete_draft(indicator: str, period_year: int) -> None:
    """Отмена черновика — удаление строки. Опубликованного не касается."""
    con = _connect_write()
    try:
        con.execute(
            "DELETE FROM plan WHERE status = ? AND indicator = ? AND period_year = ? "
            "AND coalesce(program, '') = ''",
            [PLAN_DRAFT, indicator, period_year],
        )
    finally:
        con.close()


def get_plan_rows(status: str) -> pd.DataFrame:
    """Строки плана заданного статуса — для страницы ввода."""
    if not _plan_table_ready():
        return pd.DataFrame(
            columns=["indicator", "program", "period_year", "value",
                     "author", "updated_at", "published_at"]
        )
    return _query_storage(
        "SELECT indicator, program, period_year, value, author, updated_at, published_at "
        f"FROM plan WHERE status = '{status}' ORDER BY period_year DESC, indicator"
    )


# ----------------------------------------------------------------- вето

def list_versions(limit: int = 15) -> pd.DataFrame:
    """Последние версии данных с их статусами — для раздела на странице ввода."""
    return _query_storage(
        "SELECT version, run_at, facts_rows, status, published_at "
        f"FROM versions ORDER BY version DESC LIMIT {int(limit)}"
    )


def reject_version(version: int) -> None:
    """Вето: pending-версия помечается забракованной и в 9:00 не выйдет."""
    con = _connect_write()
    try:
        con.execute(
            "UPDATE versions SET status = ? WHERE version = ? AND status = ?",
            [VER_REJECTED, int(version), VER_PENDING],
        )
    finally:
        con.close()


def restore_version(version: int) -> None:
    """Снятие вето — версия снова pending.

    Если её срок уже прошёл, ближайший вызов publish_due() опубликует её
    в течение полминуты: снятие вето — это, по сути, немедленная публикация.
    Так решено 23.07.2026 (@@ возможно, переделаем — см. ROADMAP).
    """
    con = _connect_write()
    try:
        con.execute(
            "UPDATE versions SET status = ? WHERE version = ? AND status = ?",
            [VER_PENDING, int(version), VER_REJECTED],
        )
    finally:
        con.close()


# ------------------------------------------------------------ публикация

def pending_summary() -> dict:
    """Что сейчас ждёт публикации — для плашки админа.

    Возвращает словарь: `version` и `version_run_at` — самая свежая
    pending-версия новее опубликованной (или None), `drafts` — сколько
    черновиков плана.
    """
    row = _query_storage(
        "SELECT version, run_at FROM versions "
        "WHERE status = 'pending' AND version > "
        "  (SELECT coalesce(max(version), 0) FROM versions WHERE status = 'published') "
        "ORDER BY version DESC LIMIT 1"
    )
    drafts = 0
    if _plan_table_ready():
        drafts = int(
            _query_storage("SELECT count(*) AS n FROM plan WHERE status = 'draft'")
            .iloc[0]["n"]
        )
    if row.empty:
        return {"version": None, "version_run_at": None, "drafts": drafts}
    return {
        "version": int(row.iloc[0]["version"]),
        "version_run_at": pd.to_datetime(row.iloc[0]["run_at"]).to_pydatetime(),
        "drafts": drafts,
    }


def _anything_due(cutoff: datetime) -> bool:
    """Дешёвая проверка на чтении: есть ли хоть что-то с наступившим сроком.

    Зовётся каждые 30 секунд из каждого открытого браузера, поэтому
    открывать соединение на запись «на всякий случай» нельзя — только
    когда точно есть работа.
    """
    due_version = _query_storage(
        "SELECT 1 FROM versions WHERE status = 'pending' "
        f"AND run_at < '{cutoff}' AND version > "
        "  (SELECT coalesce(max(version), 0) FROM versions WHERE status = 'published') "
        "LIMIT 1"
    )
    if not due_version.empty:
        return True
    if not _plan_table_ready():
        return False
    due_plan = _query_storage(
        f"SELECT 1 FROM plan WHERE status = 'draft' AND updated_at < '{cutoff}' LIMIT 1"
    )
    return not due_plan.empty


def publish_due(now: datetime | None = None) -> str | None:
    """Публикует всё, чей срок наступил. Возвращает описание для лога или None.

    Не «срабатывает в 9:00», а спрашивает «что уже дозрело?» — поэтому
    неважно, лежал ли сервер в 9:00: первый же вызов после подъёма
    опубликует пропущенное. Пока ничего не дозрело, вызов стоит
    два маленьких чтения.

    Параметр `now` нужен только для проверок: подставив «завтра 9:01»,
    публикацию можно прогнать не дожидаясь настоящего утра.

    Соединение всегда открывается своё, свежее. Вариант «работать на чужом
    соединении etl.run» был и ловил внутреннюю ошибку DuckDB 1.5.4
    (Attempted to access index 0 within vector of size 0) сразу после
    большой вставки на том же соединении; со своим соединением тот же
    запрос стабилен. Поэтому etl.run сначала закрывает своё — потом зовёт.
    """
    now = now or datetime.now()
    cutoff = last_deadline(now)
    if not DUCKDB_PATH.exists() or not _anything_due(cutoff):
        return None
    con = _connect_write()
    published: list[str] = []
    try:
        con.execute("BEGIN")

        # --- версии данных: публикуется самая свежая дозревшая из pending
        current = con.execute(
            "SELECT coalesce(max(version), 0) FROM versions WHERE status = 'published'"
        ).fetchone()[0]
        candidate = con.execute(
            "SELECT max(version) FROM versions "
            "WHERE status = 'pending' AND version > ? AND run_at < ?",
            [current, cutoff],
        ).fetchone()[0]
        if candidate is not None:
            con.execute(
                "UPDATE versions SET status = ? WHERE status = ?",
                [VER_SUPERSEDED, VER_PUBLISHED],
            )
            con.execute(
                "UPDATE versions SET status = ?, published_at = ? WHERE version = ?",
                [VER_PUBLISHED, now, candidate],
            )
            # Более старые pending опубликованы уже не будут — их обогнали
            con.execute(
                "UPDATE versions SET status = ? WHERE status = ? AND version < ?",
                [VER_SUPERSEDED, VER_PENDING, candidate],
            )
            # Снимки фактов заменённых версий чистим, оставив немного на откат.
            # Журнал в `versions` не трогаем — он помнит всё.
            con.execute(
                "DELETE FROM facts WHERE version IN "
                "  (SELECT version FROM versions WHERE status = ? AND version < ?)",
                [VER_SUPERSEDED, candidate - KEEP_SNAPSHOTS],
            )
            published.append(f"версия данных {candidate}")

        # --- план: дозревшие черновики замещают опубликованные строки
        due = con.execute(
            "SELECT count(*) FROM plan WHERE status = ? AND updated_at < ?",
            [PLAN_DRAFT, cutoff],
        ).fetchone()[0]
        if due:
            con.execute(
                "DELETE FROM plan WHERE status = ? AND EXISTS ("
                "  SELECT 1 FROM plan d WHERE d.status = ? AND d.updated_at < ?"
                "    AND d.indicator = plan.indicator"
                "    AND d.period_year = plan.period_year"
                "    AND coalesce(d.program, '') = coalesce(plan.program, ''))",
                [PLAN_PUBLISHED, PLAN_DRAFT, cutoff],
            )
            con.execute(
                "UPDATE plan SET status = ?, published_at = ? "
                "WHERE status = ? AND updated_at < ?",
                [PLAN_PUBLISHED, now, PLAN_DRAFT, cutoff],
            )
            published.append(f"план: строк — {due}")

        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return ", ".join(published) if published else None
