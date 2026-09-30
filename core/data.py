"""Единственная дверь к данным.

Страницы никогда не читают файлы напрямую — только вызывают функции отсюда.
Благодаря этому смена источника (Excel → БД) не потребует правок в pages/.
"""

import random
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from core.cache import cache

DUCKDB_PATH = Path("data/analytics.duckdb")
CONFIG_PATH = Path("config.yaml")

# Повторы при занятом хранилище. DuckDB — «один писатель ИЛИ много читателей»:
# пока один процесс пишет (публикация в 9:00, правка плана, прогон ETL),
# другие процессы получают IOException уже на открытии файла. На этапе 5
# под Gunicorn воркеров будет несколько, поэтому это не редкость.
#
# !! Это НЕ порча данных, а честный отказ: стресс-тест (24.07.2026, 9 процессов
# молотили один файл 15 сек) подтвердил — конкуренция даёт IOException, но
# транзакции ACID держат целостность, инвариант «одна опубликованная версия»
# не ломается. Лечится ожиданием: запись мгновенная. Задержки растут
# экспоненциально и с разбросом (jitter) — чтобы конкурирующие писатели
# расходились по времени, а не били в файл синхронно каждые 0.2 сек и
# не мешали друг другу до бесконечности. Суммарное окно ожидания ~4 сек.
_RETRY_ATTEMPTS = 8
_RETRY_BASE = 0.1
_RETRY_CAP = 1.0
_LOCK_ERRORS = (duckdb.IOException, duckdb.ConnectionException)


def _lock_delay(attempt: int) -> float:
    """Пауза перед попыткой №attempt (с нуля): экспонента с потолком и jitter."""
    base = min(_RETRY_BASE * 2 ** attempt, _RETRY_CAP)
    return random.uniform(0.5 * base, base)


def load_config() -> dict:
    """Реестр показателей и настройки из config.yaml.

    Кэшируется по времени правки файла: за одну отрисовку конфиг нужен
    десятки раз, и до кэша каждое обращение перечитывало диск — на это
    уходила большая часть времени отклика. Правка файла меняет mtime,
    а значит и ключ кэша — свежий конфиг подхватится сам.
    """
    return _config_cached(CONFIG_PATH.stat().st_mtime)


@cache.memoize()
def _config_cached(mtime: float) -> dict:
    # mtime не используется в теле — он часть ключа кэша
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _query_storage(query: str, params: list | tuple | None = None) -> pd.DataFrame:
    """Чтение из DuckDB — единственное место, открывающее хранилище на чтение.

    Пока etl.run переписывает файл, тот заперт на запись — доли секунды
    раз в несколько минут. Попав в это окно, не падаем сразу, а пробуем
    ещё несколько раз.

    ConnectionException — другая помеха с тем же лечением: в НАШЕМ процессе
    другой поток сайта прямо сейчас держит соединение на запись (публикует
    в 9:00 или сохраняет черновик плана — core/publish.py), а DuckDB не
    смешивает чтение и запись в одном процессе. Запись мгновенная — ждём.

    `params` — значения для мест `?` в запросе (добавлено 19.08.2026 после
    внешнего аудита). **Всё, что пришло из браузера, обязано ехать сюда
    параметром, а не склейкой в текст запроса.** До этого номер страницы
    подставлялся через f-строку прямо в `WHERE page = '...'`
    (`core/widgets.py`), а приходит он из адреса — то есть текст запроса
    отчасти писал посетитель. Чтение открыто `read_only=True`, поэтому
    испортить базу было нельзя, но подменить условие и вычитать то, что
    видит процесс, — можно.
    """
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(
            f"Нет хранилища {DUCKDB_PATH}. Сначала запустите:\n"
            "  python -m etl.run   (БД -> DuckDB)"
        )
    last_error: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
            try:
                return con.execute(query, params or []).df()
            finally:
                con.close()
        except _LOCK_ERRORS as e:
            last_error = e
            time.sleep(_lock_delay(attempt))
    raise RuntimeError(f"Хранилище {DUCKDB_PATH} занято записью дольше ожидания: {last_error}")


def _connect_write() -> duckdb.DuckDBPyConnection:
    """Соединение на запись — с теми же повторами, что и чтение выше.

    Живёт здесь, а не у того, кто пишет: писателей в проекте уже трое
    (публикация в 9:00, черновики плана, настройки оформления), и правило
    «дверь к хранилищу одна» должно держаться и для записи. core/publish.py
    и core/theme.py берут эту функцию отсюда.

    Файл может быть заперт прогоном etl.run — доли секунды раз в несколько
    минут; под Gunicorn к этому добавятся соседние воркеры.
    """
    last_error: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return duckdb.connect(str(DUCKDB_PATH))
        # IOException — файл заперт другим процессом (etl.run или другой
        # воркер Gunicorn пишет). ConnectionException — в ЭТОМ процессе прямо
        # сейчас открыто читающее соединение (другой поток сайта): DuckDB не
        # смешивает чтение и запись в одном процессе. И то и другое лечится
        # ожиданием — общий backoff с jitter, _lock_delay выше.
        except _LOCK_ERRORS as e:
            last_error = e
            time.sleep(_lock_delay(attempt))
    raise RuntimeError(f"Хранилище {DUCKDB_PATH} занято записью дольше ожидания: {last_error}")


def poll_health() -> dict:
    """ОДНО открытие DuckDB: версия, план, время публикации.

    Замещает три отдельных открытия (get_published_version + _plan_stamp +
    _last_publish_time), каждое из которых стоит 24–34 мс: при закрытии
    последнего соединения DuckDB выгружает базу, и следующее открытие
    грузит её заново. Здесь всё в одном соединении — ~25 мс вместо ~81.

    Возвращает словарь:
      version       — номер опубликованной версии (int)
      plan_n        — строк опубликованного плана (int)
      plan_t        — max(published_at) или None
      pub_date      — день публикации (int) или None
      pub_month     — месяц (int) или None
      pub_time      — строка "HH:MM" или None
    """
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        # Номер опубликованной версии
        row = con.execute(
            "SELECT coalesce(max(version), 0) AS v FROM versions WHERE status = 'published'"
        ).fetchone()
        version = int(row[0])

        # Отпечаток плана
        plan_row = con.execute(
            "SELECT count(*) AS n, max(published_at) AS t FROM plan WHERE status = 'published'"
        ).fetchone()
        plan_n = int(plan_row[0])
        plan_t = plan_row[1]

        # Время последней публикации
        ts_row = con.execute(
            "SELECT coalesce(published_at, run_at) AS t FROM versions "
            "WHERE status = 'published' ORDER BY version DESC LIMIT 1"
        ).fetchone()
        pub_date = pub_month = None
        pub_time = None
        if ts_row and ts_row[0] is not None and not pd.isna(ts_row[0]):
            ts = pd.to_datetime(ts_row[0])
            pub_date = ts.day
            pub_month = ts.month
            pub_time = ts.strftime("%H:%M")

        return {
            "version": version,
            "plan_n": plan_n,
            "plan_t": plan_t,
            "pub_date": pub_date,
            "pub_month": pub_month,
            "pub_time": pub_time,
        }
    finally:
        con.close()


def get_published_version() -> int:
    """Номер ОПУБЛИКОВАННОЙ версии данных — одна строка из `versions`, дёшево.

    С этапа 4 сайт показывает не последнюю загрузку, а последнюю
    опубликованную: свежие загрузки ждут своих 9:00 со статусом pending
    (шлюз — в core/publish.py). Номер входит в ключ кэша фактов.
    Намеренно НЕ кэшируется — это и есть проба свежести.
    """
    df = _query_storage(
        "SELECT coalesce(max(version), 0) AS v FROM versions WHERE status = 'published'"
    )
    return int(df.iloc[0]["v"])


def _plan_stamp() -> str:
    """Отпечаток опубликованного плана — вторая половина display-версии.

    Публикация плана не меняет номер версии фактов, но экран перерисовать
    должна. Считаем по `published_at`, а не по `updated_at`: правка могла
    быть сделана давно, а на витрину она влияет с момента публикации.
    """
    try:
        df = _query_storage(
            "SELECT count(*) AS n, max(published_at) AS t "
            "FROM plan WHERE status = 'published'"
        )
    except duckdb.Error:
        return "0"  # хранилище старой схемы, таблицы plan ещё нет
    return f"{int(df.iloc[0]['n'])}@{df.iloc[0]['t']}"


def _display_version(health: dict) -> str:
    """Составляет display-версию из уже готовых данных poll_health()."""
    plan_stamp = f"{health['plan_n']}@{health['plan_t']}" if health["plan_t"] else "0"
    return f"{health['version']}|{plan_stamp}"


def get_display_version() -> str:
    """Что сейчас показывает витрина: версия фактов + отпечаток плана.

    Эту строку страница держит в dcc.Store и раз в 30 сек сверяет со свежей.
    Изменилась — значит, опубликована новая версия данных ИЛИ новый план,
    и коллбэки перерисуются. Оба события меняют цифры на экране, поэтому
    следить только за версией фактов было бы мало.

    Использует poll_health() — одно открытие DuckDB вместо двух отдельных.
    """
    return _display_version(poll_health())


def _display_version_from_health(health: dict) -> str:
    """Alias — для совместимости с коллбэком, который получает health-словарь."""
    return _display_version(health)


def load_facts() -> pd.DataFrame:
    """Читает снимок опубликованной версии фактов из хранилища DuckDB.

    **Это единственная точка, знающая формат источника.** До этапа 3 здесь
    читались CSV-файлы — временная затычка. Теперь источник — таблица `facts`
    в data/analytics.duckdb, которую ведёт `python -m etl.run`; с этапа 4
    в ней лежат снимки нескольких версий, и наружу отдаётся только
    опубликованный, без служебной колонки `version` — форма данных для
    страниц не изменилась ни на колонку.

    Кэшируется по номеру опубликованной версии: пока публикации не было,
    повторные вызовы получают копию из памяти, а не ходят на диск.
    Опубликовалась новая — ключ кэша сменился, факты перечитались.
    Поэтому свежесть не страдает: кэш не «протухает», а привязан к данным.

    Поверх этого — память на время ОДНОГО запроса, см. `_request_memo`.
    """
    memo = _request_memo()
    if memo is not None and "facts" in memo:
        return memo["facts"]

    version = get_published_version()
    if version == 0:
        # Тот же тип ошибки, что и при отсутствии файла: страницы уже умеют
        # показывать его текст плашкой вместо экрана
        raise FileNotFoundError(
            "В хранилище нет опубликованных данных. Запустите:\n"
            "  python -m etl.run   (первая загрузка публикуется сразу)"
        )
    df = _facts_cached(version, _demo_stamp(), FACTS_SHAPE)
    if memo is not None:
        memo["facts"] = df
    return df


#: !! Поднимите это число, если поменяли ФОРМУ таблицы в `_facts_cached`:
#: колонки, типы, состав строк. Ключ кэша складывается из версии данных
#: и отпечатка демо — про код он не знает ничего, поэтому после правки
#: разбора кэш продолжает отдавать таблицу старой формы. Так и случилось
#: 07.08.2026: колонки перевели в категории, замер показал прежние 177 МБ,
#: и минуту было непонятно, почему правка «не работает».
FACTS_SHAPE = 3


def _request_memo() -> dict | None:
    """Память на время одного HTTP-запроса. Вне запроса — `None`.

    Зачем она поверх файлового кэша. Один вызов `load_facts()` стоит около
    60 мс: два пробных запроса к DuckDB (номер версии и отпечаток демо)
    плюс распаковка снимка из файлового кэша — 26 МБ через pickle. Само по
    себе немного, но за отрисовку раздела СЭЭ функцию зовут **33 раза**
    (двенадцать диаграмм и четыре карточки, каждая по своим показателям),
    и это складывалось в 2 секунды из 2,7 (замерено 07.08.2026).

    Почему именно запрос, а не процесс. Кэш нарочно сделан файловым, чтобы
    воркеры Gunicorn делили его и не держали по своей копии фактов
    (см. `core/cache.py`). Память на весь процесс вернула бы ту самую
    копию на каждого воркера. А запрос — самый большой отрезок времени,
    внутри которого данные заведомо не меняются: он живёт миллисекунды,
    новая версия за это время появиться не может. Свежесть не страдает
    вообще: следующий запрос снова спросит версию.

    Вне веб-запроса (консоль, ETL, тесты) возвращается `None`, и всё
    работает ровно как раньше.
    """
    try:
        from flask import g, has_request_context
    except ImportError:                         # flask не установлен
        return None
    if not has_request_context():
        return None
    store = getattr(g, "_damu_request_memo", None)
    if store is None:
        store = {}
        g._damu_request_memo = store
    return store


def _demo_stamp() -> str:
    """Отпечаток демо-данных — вторая половина ключа кэша фактов.

    Пусто, когда демо выключены в `config.yaml` (`demo_data: false`)
    или таблицы `demo_facts` нет вовсе. Переключили флаг — сменился
    ключ, и факты перечитались: макет включается и выключается
    без перезапуска сайта.
    """
    if not load_config().get("demo_data"):
        return ""
    try:
        df = _query_storage("SELECT count(*) AS n, max(loaded_at) AS t FROM demo_facts")
    except duckdb.Error:
        return ""  # демо-таблицы ещё нет — работаем на настоящих данных
    return f"{int(df.iloc[0]['n'])}@{df.iloc[0]['t']}"


#: Колонки-разрезы: значений в них десятки, а строк сотни тысяч.
#:
#: !! `date` в список НЕ входит намеренно. У показателей с `agg: last`
#: свёртка ищет последнюю дату через `idxmax`, а на неупорядоченной
#: категории сравнение падает. Выигрыш от неё всё равно маленький —
#: значений там втрое больше, чем в любом настоящем разрезе.
CATEGORICAL = (
    "indicator", "period", "region", "industry", "bank", "subject_type",
    "loan_purpose", "instrument", "program", "source_program",
    "source_file", "loaded_at",
)


#: Разные источники называют один регион по-разному: кратко, аббревиатурой
#: или через название регионального филиала. На витрину должна выходить одна
#: география, иначе один регион распадается на несколько пунктов фильтра и
#: несколько полос диаграммы. Оригиналы в data/raw не меняем — каноническое
#: имя присваивается только снимку, который читает сайт.
#:
#: Абай, Жетісу и Ұлытау оставлены в казахском написании по решению
#: пользователя 02.09.2026.
REGION_ALIASES = {
    "РФ по области Абай": "Абай",
    "РФ по Акмолинской области": "Акмолинская",
    "РФ по Актюбинской области": "Актюбинская",
    "РФ по Алматинской области": "Алматинская",
    "РФ по Атырауской области": "Атырауская",
    "ВКО": "Восточно-Казахстанская",
    "РФ по Восточно-Казахстанской области": "Восточно-Казахстанская",
    "РФ по Жамбылской области": "Жамбылская",
    "Жетысу": "Жетісу",
    "РФ по области Жетiсу": "Жетісу",
    "ЗКО": "Западно-Казахстанская",
    "РФ по Западно-Казахстанской области": "Западно-Казахстанская",
    "РФ по Карагандинской области": "Карагандинская",
    "РФ по Костанайской области": "Костанайская",
    "РФ по Кызылординской области": "Кызылординская",
    "РФ по Мангистауской области": "Мангистауская",
    "РФ по Павлодарской области": "Павлодарская",
    "СКО": "Северо-Казахстанская",
    "РФ по Северо-Казахстанской области": "Северо-Казахстанская",
    "РФ по Туркестанской области": "Туркестанская",
    "Улытау": "Ұлытау",
    "РФ по области Ұлытау": "Ұлытау",
    "г.Алматы": "г. Алматы",
    "РФ по г. Алматы": "г. Алматы",
    "г.Астана": "г. Астана",
    "РФ по г. Астана": "г. Астана",
    "г.Шымкент": "г. Шымкент",
    "РФ по г. Шымкент": "г. Шымкент",
}

# Это не географические значения. Строки остаются в фактах: они нужны для
# общего итога и других разрезов, но выбирать их как область нельзя.
NON_GEOGRAPHIC_REGIONS = {"Неизвестно", "Департамент гарантирования"}


def _canonical_regions(series: pd.Series) -> pd.Series:
    """Приводит названия регионов разных источников к одному справочнику."""
    return series.replace(REGION_ALIASES)


@cache.memoize()
def _facts_cached(version: int, demo: str, shape: int = 1) -> pd.DataFrame:
    # `shape` в теле не нужен — он часть ключа кэша, см. FACTS_SHAPE
    # version — и ключ кэша, и фильтр: в таблице лежат снимки разных версий
    df = _query_storage("SELECT * EXCLUDE (version) FROM facts WHERE version = ?",
                        [version])
    df["is_total"] = df["is_total"].astype(bool)

    if demo:
        # !! Демо-строки лежат в своей таблице и подмешиваются только здесь.
        # Спутаться с настоящими они не могут: у них свои коды показателей
        # (demo_*), поэтому в одну сумму эти строки никогда не попадают —
        # все расчёты в проекте идут по конкретному показателю.
        extra = _query_storage("SELECT * FROM demo_facts")
        extra["is_total"] = extra["is_total"].astype(bool)
        df = pd.concat([df, extra], ignore_index=True)

    if "region" in df.columns:
        df["region"] = _canonical_regions(df["region"])

    # Разрезы — категориями, а не строками. Повод не в аккуратности,
    # а в весе: когда 07.08.2026 к фактам добавились ОКЭД, БВУ,
    # субъектность и цели займа, строк стало 157 тысяч вместо 28,
    # таблица распухла до 197 МБ, а чтение из кэша — с 61 мс до 369.
    # Категория хранит не саму строку в каждой ячейке, а номер в словаре
    # значений: банков 108, отраслей 39, разделов 5. Замерено: 197 -> 5 МБ,
    # результаты группировок совпали до копейки.
    for column in CATEGORICAL:
        if column in df.columns:
            df[column] = df[column].astype("category")
    return df


def get_programs() -> list[str]:
    """Программы (они же разделы), по которым в данных есть строки.

    Колонка `program` в настоящих данных пока пуста — заполнена она только
    у демо-строк макета. Пустые значения отбрасываем: раздел «ничего»
    в меню не нужен.
    """
    df = load_facts()
    found = df.loc[df["program"].astype(str) != "", "program"].unique().tolist()
    return sorted(found)


def _only_program(df: pd.DataFrame, program: str | None) -> pd.DataFrame:
    """Оставляет строки одного раздела (колонка `program`).

    `None` — не фильтровать: так ведут себя главная страница и «Разбор»,
    они смотрят на всё сразу. Страница раздела передаёт своё название,
    и дальше все расчёты идут только по его строкам.

    Отдельная функция, а не одна строка внутри каждого места, потому что
    мест этих полтора десятка, и правило отбора должно быть одно.
    """
    if not program:
        return df
    return df[df["program"] == program]


def _aggregate(df: pd.DataFrame, indicator: str, by: list[str]) -> pd.DataFrame:
    """Сворачивает несколько строк в одну по правилу `agg` из конфига.

    Нужно, потому что источники разной частоты: выгрузка МСП даёт одну строку
    на год, а таблицы из БД — двенадцать, по месяцам. Складывать их одинаково
    нельзя: потоки (выделено, освоено) суммируются, срезы на дату (сколько МСП
    существует) берутся по последней дате, а средний срок — усредняется.
    """
    how = get_indicator_meta(indicator).get("agg", "sum")

    if how == "last":
        latest = df.loc[df.groupby(by)["date"].idxmax()]
        return latest[by + ["value"]].reset_index(drop=True)
    if how == "mean":
        return df.groupby(by, as_index=False)["value"].mean()
    return df.groupby(by, as_index=False)["value"].sum()


def get_indicator_meta(indicator: str) -> dict:
    return load_config()["indicators"][indicator]


def get_indicator_choices() -> list[dict]:
    """Список показателей для выпадающего фильтра.

    Показываем только те, по которым **реально есть данные**. Реестр в конфиге
    может описывать больше, чем сейчас загружено: источники подключают и
    отключают, и предлагать пользователю заведомо пустой показатель незачем.
    """
    cfg = load_config()
    present = set(load_facts()["indicator"].unique())
    return [
        {"label": meta["title"], "value": key}
        for key, meta in cfg["indicators"].items()
        if key in present
    ]


def get_years() -> list[int]:
    """Годы, за которые есть данные, свежий первым."""
    return sorted(load_facts()["report_year"].unique().tolist(), reverse=True)


def indicator_years(indicator: str, program: str | None = None) -> list[int]:
    """Годы, за которые есть данные У ЭТОГО показателя, свежий первым.

    Не то же самое, что `get_years()`: тот отвечает «какие годы вообще есть
    в хранилище», а источники приходят разной длины. Гарантии и кредиты
    доходят до 2026-го, разрез СЭЭ по областям обрывается на 2024-м —
    и общий список годов про это ничего не знает.
    """
    df = _only_program(load_facts(), program)
    df = df[(df.indicator == indicator) & df.value.notna()]
    return sorted(df["report_year"].unique().tolist(), reverse=True)


def resolve_year(indicator: str, year: int, program: str | None = None) -> int | None:
    """Год, который реально можно показать: выбранный или ближайший с данными.

    Зачем это нужно. Год выбирается один на весь сайт, а показатели кончаются
    в разные годы. До 07.08.2026 несовпадение давало пустой экран: человек
    открывал раздел и видел пустые оси, не понимая, сломано это или данных
    правда нет.

    Правило: выбранный год, если он есть; иначе **ближайший предыдущий**
    с данными (2026 → 2025 → 2024 …). Если выбранный старше всех имеющихся,
    берём самый старый — показать хоть что-то honestнее, чем пустая ось.

    Возвращает `None`, только когда данных нет вовсе: показатель в реестре
    описан, а строк по нему в хранилище не появилось. Тогда диаграмма
    честно скажет «нет данных» — подставлять нечего.

    !! Подставленный год ОБЯЗАН быть виден на экране. Тихо показать 2024-й
    там, где человек выбрал 2026-й, — худший вид ошибки: цифры выглядят
    свежими и никак не помечены. Пометку рисует `charts.build`.
    """
    years = indicator_years(indicator, program)
    if not years:
        return None
    year = int(year)
    if year in years:
        return year
    earlier = [y for y in years if y < year]
    return int(earlier[0] if earlier else years[-1])


def format_value(value: float, indicator: str, with_unit: bool = True) -> str:
    """Число в виде, пригодном для показа: масштаб, разряды, единица.

    `with_unit=False` — только число, без «млрд ₸». Нужно там, где единица
    названа рядом один раз: подписи столбцов внутри диаграммы (17.08.2026,
    просьба пользователя — пять раз «млрд ₸» на пяти столбцах занимали
    больше места, чем сами числа, и подпись вставала вертикально).

    !! Отдельной функции «только число» заводить нельзя: масштаб, разряды
    и запятая обязаны считаться одинаково для карточки и для подписи.
    Разойдись они — на одном экране появились бы два разных написания
    одного числа, и никакой ошибки при этом не случилось бы.
    """
    meta = get_indicator_meta(indicator)
    scaled = value / meta["divisor"]
    # Неразрывный пробел как разделитель разрядов — так принято в русской типографике
    # Запятая отделяет дробную часть: Питон по умолчанию делает наоборот
    # («1,307.9»). Порядок замен важен — сначала разряды на пробел, потом
    # точку на запятую, иначе запятая-разделитель успела бы стать дробной.
    text = (f"{scaled:,.{meta['decimals']}f}"
            .replace(",", " ").replace(".", ","))
    if not with_unit:
        return text
    return f"{text} {meta['display_unit']}".strip()


def _country_totals(df: pd.DataFrame, year: int) -> dict[str, float]:
    """Итог по стране за год для каждого показателя.

    Два случая. Если в источнике есть готовая строка-итог («Республика
    Казахстан» в выгрузках статистики) — берём её: официальная цифра важнее
    нашей суммы, и если они разойдутся, показать надо источник.

    Если строки-итога нет — а в данных из БД её и не бывает — складываем
    регионы сами, по правилу `agg` того же показателя.
    """
    totals: dict[str, float] = {}
    for indicator, group in df[df.report_year == year].groupby("indicator"):
        official = group[group.is_total]
        if not official.empty:
            totals[indicator] = float(
                _aggregate(official, indicator, ["indicator"])["value"].iloc[0]
            )
            continue

        per_region = _aggregate(group[~group.is_total], indicator, ["region"])
        if per_region.empty:
            continue
        how = get_indicator_meta(indicator).get("agg", "sum")
        # Средние по регионам усредняем, всё остальное складываем
        totals[indicator] = float(
            per_region["value"].mean() if how == "mean" else per_region["value"].sum()
        )
    return totals


def get_country_total(
    indicator: str, year: int, regions: list[str] | None = None,
    program: str | None = None,
) -> float | None:
    """Одна цифра: итог показателя по стране за год.

    Нужна виджетам «общий показатель» — тем, что показывают не разрез
    по областям, а одно число: сколько всего МСП, сколько освоено.
    Регионы в них сворачиваются в страну по правилу `agg` показателя.

    Если в фильтре выбраны отдельные области, готовая строка-итог
    не годится (она про всю страну) — тогда складываем только выбранные.
    """
    df = load_facts()
    selected = _only_program(
        df[(df.indicator == indicator) & (df.report_year == year)], program
    )
    if selected.empty:
        return None

    official = selected[selected.is_total]
    if not regions and not official.empty:
        return float(_aggregate(official, indicator, ["indicator"])["value"].iloc[0])

    per_region = selected[~selected.is_total]
    if regions:
        per_region = per_region[per_region.region.isin(regions)]
    if per_region.empty:
        return None
    per_region = _aggregate(per_region, indicator, ["region"])
    how = get_indicator_meta(indicator).get("agg", "sum")
    return float(
        per_region["value"].mean() if how == "mean" else per_region["value"].sum()
    )


def get_country_years(
    indicator: str, regions: list[str] | None = None, program: str | None = None,
) -> pd.DataFrame:
    """Показатель по годам, страна целиком. Колонки: report_year, value.

    Отличие от `get_region_dynamics`: там строка на каждую область,
    здесь — на каждый год. Для виджета «как менялось в целом».

    !! Считается ОДНИМ проходом по годам, а не вызовом `get_country_total`
    в цикле. Так было до 07.08.2026, и это оказалось самым дорогим местом
    на сайте: двадцать лет × (перечитать таблицу фактов + отфильтровать) —
    2,2 секунды на одну диаграмму (замерено). На странице раздела таких
    диаграмм четыре, и они одни давали 9 секунд из 10.

    Логика повторяет `get_country_total` слово в слово, только фильтр по
    году снят, а группировка идёт по паре (год, регион). Держать их
    согласованными обязательно: разойдутся — «Годы» перестанут сходиться
    с карточкой за тот же год.
    """
    df = load_facts()
    selected = _only_program(df[df.indicator == indicator], program)
    if selected.empty:
        return pd.DataFrame(columns=["report_year", "value"])

    # Официальная строка-итог годится, только когда смотрим всю страну:
    # при выбранных областях она про другое (см. `get_country_total`)
    official = selected[selected.is_total]
    if not regions and not official.empty:
        out = _aggregate(official, indicator, ["report_year"])
    else:
        per_region = selected[~selected.is_total]
        if regions:
            per_region = per_region[per_region.region.isin(regions)]
        if per_region.empty:
            return pd.DataFrame(columns=["report_year", "value"])
        per_region = _aggregate(per_region, indicator, ["report_year", "region"])
        how = get_indicator_meta(indicator).get("agg", "sum")
        grouped = per_region.groupby("report_year", as_index=False)["value"]
        out = grouped.mean() if how == "mean" else grouped.sum()

    out = out[["report_year", "value"]].copy()
    out["report_year"] = out["report_year"].astype(int)
    return out.sort_values("report_year").reset_index(drop=True)


def get_derived_percent(
    indicator: str, year: int, regions: list[str] | None = None,
    program: str | None = None,
) -> tuple[float | None, str]:
    """Производный процент («Согласно плану») и подпись, от чего он считан.

    Тот же расчёт, что у карточки на главной: числитель — факт,
    знаменатель — план. Если админ опубликовал годовой план, знаменатель
    берётся из него.

    !! С одной оговоркой: **при выбранных областях план не применяется.**
    План вводится один на страну, к трём выбранным областям он отношения
    не имеет, и делить их факт на общий план значило бы показать
    бессмыслицу. В таком случае считаем от фактов и говорим об этом
    подписью — чтобы цифра не выглядела не тем, чем она является.
    """
    spec = get_indicator_meta(indicator).get("derived")
    if not spec:
        return None, ""

    numerator = get_country_total(spec["numerator"], year, regions, program)
    denominator = get_country_total(spec["denominator"], year, regions, program)
    source = "от факта за загруженные месяцы"

    if not regions:
        plan = get_published_plan(year).get(spec["denominator"])
        if plan:
            denominator, source = float(plan), "от годового плана"

    if numerator is None or not denominator:
        return None, source
    return numerator / denominator * 100, source


def get_published_plan(year: int) -> dict[str, float]:
    """Опубликованный ручной план на год: показатель -> значение.

    Черновики сюда не попадают — витрина видит план только после его
    публикации в 9:00 (core/publish.py). Значения лежат в единицах
    показателя из config.yaml, как и факты. Сумма по программам — на
    вырост: пока разреза по программам нет, строка на показатель одна.
    """
    try:
        df = _query_storage(
            "SELECT indicator, sum(value) AS value FROM plan "
            f"WHERE status = 'published' AND period_year = {int(year)} "
            "GROUP BY indicator"
        )
    except duckdb.Error:
        return {}  # хранилище старой схемы, таблицы plan ещё нет
    return dict(zip(df["indicator"], df["value"]))


def _derived_value(totals: dict[str, float], spec: dict) -> float | None:
    """Производный показатель: доля числителя от знаменателя, в процентах.

    Считается из готовых итогов по стране, а не по строкам данных: сначала
    сворачиваем факт и план каждый по своему правилу, потом делим итоги.
    """
    numerator = totals.get(spec["numerator"])
    denominator = totals.get(spec["denominator"])
    if numerator is None or not denominator:
        return None
    return numerator / denominator * 100


def kpi_indicators(present: set[str]) -> list[str]:
    """Какие карточки показать, если состав задан не списком, а данными.

    Нужно страницам разделов: `kpi_order` в конфиге описывает витрину
    главного экрана, а у раздела свои показатели, и перечислять их
    двадцать раз в YAML — путь к рассинхрону. Берём всё, что есть
    в данных раздела, в порядке объявления в реестре, плюс производные,
    у которых на месте и числитель, и знаменатель.
    """
    cfg = load_config()
    order = []
    for key, meta in cfg["indicators"].items():
        derived = meta.get("derived")
        difference = meta.get("difference")
        if derived:
            parts = {derived["numerator"], derived["denominator"]}
            if parts <= present:
                order.append(key)
        elif difference:
            if set(difference) <= present:
                order.append(key)
        elif key in present:
            order.append(key)
    return order


def get_kpi(year: int, program: str | None = None) -> pd.DataFrame:
    """Итоги по стране за год и изменение к предыдущему году.

    Два сорта карточек. Обычные берут итог показателя из данных. Производные
    (в конфиге есть блок `derived`) в данных не лежат — считаются из итогов
    двух других показателей: «Согласно плану %» = освоено / выделено.

    Без раздела состав карточек берётся из `kpi_order` — это витрина
    главного экрана, её собирали руками. Для раздела список строится
    по его данным (см. `kpi_indicators`).
    """
    df = _only_program(load_facts(), program)
    cfg = load_config()
    order = (
        kpi_indicators(set(df["indicator"].unique())) if program else cfg["kpi_order"]
    )

    # Итоги считаются по годам, а год у каждого показателя теперь может быть
    # свой: где-то данные кончились в 2024-м, где-то доходят до 2026-го
    # (см. `resolve_year`). Считаем по требованию и запоминаем — иначе один
    # и тот же год пересчитывался бы для каждой карточки заново
    _totals_by_year: dict[int, dict[str, float]] = {}

    def totals(y: int) -> dict[str, float]:
        if y not in _totals_by_year:
            _totals_by_year[y] = _country_totals(df, y)
        return _totals_by_year[y]

    def for_indicator(key: str) -> tuple[dict, dict, int]:
        """Итоги за год этого показателя: сам год, он же минус один."""
        effective = resolve_year(key, year, program) or int(year)
        return totals(effective), totals(effective - 1), effective

    # Опубликованный ручной план. Если он введён, знаменатель производных
    # карточек берётся из него, а не из фактов: «Согласно плану %» начинает
    # считаться от годового плана, введённого админом. Плана нет — всё как
    # раньше, от суммы показателя-знаменателя за загруженные месяцы.
    #
    # План спрашивается за ТОТ ЖЕ год, за который посчитан факт: если факт
    # подставлен за 2024-й, делить его на план 2026-го было бы бессмыслицей
    _plan_by_year: dict[int, dict[str, float]] = {}

    def plan(y: int) -> dict[str, float]:
        if y not in _plan_by_year:
            _plan_by_year[y] = get_published_plan(y)
        return _plan_by_year[y]

    rows = []
    for indicator in order:
        meta = cfg["indicators"][indicator]
        derived = meta.get("derived")
        difference = meta.get("difference")

        if difference:
            # Второй вид производного показателя: разность, а не доля.
            # Так считается «Остаток» = план − факт. В данных его нет,
            # и это правильно: производное надо считать из частей, иначе
            # однажды разойдётся с ними
            left, right = difference
            # Год берём по левой части: производное считается из своих
            # слагаемых, и подставлять им разные годы нельзя — разность
            # плана 2026-го и факта 2024-го не значила бы ничего
            current, previous, effective = for_indicator(left)
            if left not in current or right not in current:
                continue
            value = current[left] - current[right]
            before = (
                previous[left] - previous[right]
                if left in previous and right in previous else None
            )
            change = (value / before - 1) * 100 if before else None
            change_kind = "pct"
        elif derived:
            # Подменяется только знаменатель: числитель — это факт,
            # и ручным планом он быть не может
            denom = derived["denominator"]
            current, previous, effective = for_indicator(derived["numerator"])
            plan_current, plan_previous = plan(effective), plan(effective - 1)
            cur_totals = {**current, **(
                {denom: plan_current[denom]} if denom in plan_current else {}
            )}
            prev_totals = {**previous, **(
                {denom: plan_previous[denom]} if denom in plan_previous else {}
            )}
            value = _derived_value(cur_totals, derived)
            if value is None:
                continue
            before = _derived_value(prev_totals, derived)
            # Проценты сравнивают вычитанием: рост с 78 % до 80 % — это
            # +2 процентных пункта, а не «+2.6 %». Отсюда отдельный вид
            # изменения, карточка подпишет его «п.п.»
            change = None if before is None else value - before
            change_kind = "pp"
        else:
            current, previous, effective = for_indicator(indicator)
            if indicator not in current:
                continue
            value = current[indicator]
            before = previous.get(indicator)
            change = (value / before - 1) * 100 if before else None
            change_kind = "pct"

        rows.append(
            {
                "indicator": indicator,
                "short": meta["short"],
                "title": meta["title"],
                "value": value,
                "text": format_value(value, indicator),
                "change_pct": change,
                "change_kind": change_kind,
                # За какой год карточка на самом деле посчитана. Совпадает
                # с выбранным, пока у показателя есть данные за него;
                # разошлось — карточка обязана это показать (см. kpi_card)
                "year": effective,
            }
        )
    # !! Колонки перечислены явно, и это не украшательство. Без них пустой
    # список давал DataFrame ВООБЩЕ БЕЗ колонок, и первое же обращение
    # `kpi["indicator"]` на стороне страницы падало с `KeyError`. Поймано
    # 07.08.2026 на разделе, где ни у одного показателя не оказалось данных:
    # страница обязана показать «показателей нет», а не уронить коллбэк
    return pd.DataFrame(rows, columns=[
        "indicator", "short", "title", "value", "text",
        "change_pct", "change_kind", "year",
    ])


def get_region_choices() -> list[str]:
    """Канонические регионы по алфавиту — для географического фильтра."""
    df = load_facts()
    regions = df.loc[
        (~df.is_total)
        & df["region"].notna()
        & ~df["region"].isin(NON_GEOGRAPHIC_REGIONS),
        "region",
    ]
    return sorted(regions.unique().tolist())



#: Чем разборщик помечает строку, у которой такого разреза нет.
#:
#: !! Пустую ячейку заменяют словом, а не оставляют пустой, потому что
#: `groupby` в pandas молча выбрасывает группы с `NaN` в ключе — и часть
#: строк исчезла бы из сумм без единой ошибки. Но показывать «Неизвестно»
#: очередной отраслью тоже нельзя: это не значение, а признак того, что
#: у источника такого разреза нет вовсе.
NO_VALUE = "Неизвестно"


def get_breakdown(
    indicator: str,
    year: int,
    column: str,
    limit: int | None = None,
    regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Значения показателя в разрезе любой колонки-разреза, по убыванию.

    Одна функция на все разрезы: отрасли (ОКЭД), банки (БВУ), субъектность,
    цели займа. Отличается от `get_regions` только тем, что колонка приходит
    параметром — правило отбора и свёртки то же самое.

    Разрез, которого у источника нет, отдаёт пустую таблицу (у таких строк
    в колонке стоит `NO_VALUE`), и диаграмма честно пишет «нет данных»
    вместо одной полосы «Неизвестно» во весь экран.
    """
    df = load_facts()
    empty = pd.DataFrame(columns=[column, "value"])
    if column not in df.columns:
        return empty

    selected = _only_program(
        df[(df.indicator == indicator) & (df.report_year == year) & (~df.is_total)],
        program,
    )
    if regions:
        selected = selected[selected.region.isin(regions)]
    selected = selected[selected[column].notna() & (selected[column] != NO_VALUE)]
    if selected.empty:
        return empty

    selected = _aggregate(selected, indicator, [column])
    selected = selected.sort_values("value", ascending=False)
    if limit:
        selected = selected.head(limit)
    return selected


def get_industries(
    indicator: str,
    year: int,
    limit: int | None = None,
    regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Разрез по отраслям — частный случай `get_breakdown`."""
    return get_breakdown(indicator, year, "industry", limit, regions, program)


def has_breakdown(column: str, program: str | None = None) -> bool:
    """Есть ли у раздела хоть одна строка с этим разрезом.

    Нужна странице раздела: пока разреза нет, на его месте стоит макетная
    карточка «как это будет выглядеть»; появился — карточку убираем, чтобы
    выдуманные числа не стояли рядом с настоящими.
    """
    df = load_facts()
    if column not in df.columns:
        return False
    rows = _only_program(df, program)
    return bool((rows[column].notna() & (rows[column] != NO_VALUE)).any())


def get_regions(
    indicator: str,
    year: int,
    limit: int | None = None,
    regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Значения по регионам за год, по убыванию. Строка итога исключена.

    regions — показать только перечисленные; None или пустой список = все.
    """
    df = load_facts()
    selected = _only_program(
        df[(df.indicator == indicator) & (df.report_year == year) & (~df.is_total)],
        program,
    )
    if regions:
        selected = selected[selected.region.isin(regions)]
    if selected.empty:
        return pd.DataFrame(columns=["region", "value"])

    selected = _aggregate(selected, indicator, ["region"])
    selected = selected.sort_values("value", ascending=False)
    if limit:
        selected = selected.head(limit)
    return selected.reset_index(drop=True)


MONTH_NAMES = ["янв", "фев", "мар", "апр", "май", "июн",
               "июл", "авг", "сен", "окт", "ноя", "дек"]

# Тестовая сезонность для СЭЭ 2. Сумма коэффициентов ровно 1, поэтому
# придуманная разбивка всегда сходится с настоящим годовым итогом и годовой
# график не противоречит раскрытому. В хранилище эти строки НЕ записываются:
# реальная выгрузка СЭЭ пока содержит только декабрь.
TEST_MONTH_WEIGHTS = (0.055, 0.060, 0.070, 0.075, 0.080, 0.085,
                      0.090, 0.095, 0.100, 0.090, 0.100, 0.100)


def get_monthly(
    indicator: str, year: int, regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Показатель по месяцам выбранного года — для вида «динамика в году».

    Здесь всё наоборот по сравнению с остальными функциями: обычно месяцы
    сворачиваются в год, а регионы остаются; тут регионы сворачиваются
    в страну, а месяцы остаются. Правило свёртки — то же, что у показателя:
    средние усредняются, всё остальное складывается (сумма срезов по регионам —
    это срез по стране, так что и для срезов сумма верна).
    """
    df = load_facts()
    selected = _only_program(
        df[(df.indicator == indicator) & (df.report_year == year) & (~df.is_total)],
        program,
    )
    if regions:
        selected = selected[selected.region.isin(regions)]
    if selected.empty:
        return pd.DataFrame(columns=["month", "month_name", "value"])

    how = get_indicator_meta(indicator).get("agg", "sum")
    per_month = selected.groupby("date", as_index=False)["value"].agg(
        "mean" if how == "mean" else "sum"
    )
    per_month["month"] = pd.to_datetime(per_month["date"]).dt.month
    per_month["month_name"] = per_month["month"].map(lambda m: MONTH_NAMES[m - 1])
    return (
        per_month.sort_values("month")[["month", "month_name", "value"]]
        .reset_index(drop=True)
    )


def get_test_monthly(
    indicator: str, year: int, regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Прозрачная тестовая разбивка годового итога на 12 месяцев.

    Используется только в отдельном макетном разделе СЭЭ 2, чтобы проверить
    сценарий раскрытия года. Это не подмена источника: функция вызывается
    только по явному флагу виджета, а сумма равна годовому итогу.
    """
    total = get_country_total(indicator, year, regions=regions, program=program)
    if total is None:
        return pd.DataFrame(columns=["month", "month_name", "value"])
    return pd.DataFrame({
        "month": range(1, 13),
        "month_name": MONTH_NAMES,
        "value": [float(total) * weight for weight in TEST_MONTH_WEIGHTS],
    })


def get_region_dynamics(
    indicator: str, regions: list[str] | None = None, program: str | None = None,
) -> pd.DataFrame:
    """Показатель по регионам за все годы сразу — для диаграммы «сравнение лет»."""
    df = load_facts()
    selected = _only_program(df[(df.indicator == indicator) & (~df.is_total)], program)
    if regions:
        selected = selected[selected.region.isin(regions)]
    if selected.empty:
        return pd.DataFrame(columns=["region", "report_year", "value"])

    out = _aggregate(selected, indicator, ["region", "report_year"])
    return out.sort_values(["report_year", "value"]).reset_index(drop=True)


def get_macroregion_map() -> dict[str, str]:
    """Область → макрорегион. Разворачивает списки из config.yaml в плоский словарь."""
    groups = load_config().get("macroregions", {})
    return {region: group for group, members in groups.items() for region in members}


def get_regions_grouped(
    indicator: str, year: int, regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Регионы с колонкой макрорегиона — для иерархических диаграмм."""
    df = get_regions(indicator, year, regions=regions, program=program)
    mapping = get_macroregion_map()
    df["macroregion"] = df["region"].map(mapping).fillna("Прочие")
    return df


def get_change(
    indicator: str, year: int, regions: list[str] | None = None,
    program: str | None = None,
) -> pd.DataFrame:
    """Изменение показателя за выбранный год к предыдущему, по регионам.

    Колонки: region, prev, current, delta. Отсортировано по убыванию delta.

    Сравниваем именно `year` и `year - 1`, а не «два последних года в данных»:
    последний год в источнике почти всегда неполный, и сравнение с ним
    показало бы обвал там, где просто ещё не наступили остальные месяцы.
    """
    empty = pd.DataFrame(columns=["region", "prev", "current", "delta"])
    df = load_facts()
    selected = _only_program(df[(df.indicator == indicator) & (~df.is_total)], program)
    if regions:
        selected = selected[selected.region.isin(regions)]
    if selected.empty:
        return empty

    # Сначала сворачиваем месяцы в год, иначе на регион придётся 12 строк
    per_year = _aggregate(selected, indicator, ["region", "report_year"])
    prev = per_year[per_year.report_year == year - 1].set_index("region")["value"]
    current = per_year[per_year.report_year == year].set_index("region")["value"]
    if prev.empty or current.empty:
        return empty

    out = pd.DataFrame({"prev": prev, "current": current}).dropna().reset_index()
    out["delta"] = out["current"] - out["prev"]
    return out.sort_values("delta", ascending=False).reset_index(drop=True)


def get_table(year: int, regions: list[str] | None = None,
              program: str | None = None) -> pd.DataFrame:
    """Широкая таблица для экрана: регион в строке, показатели в колонках.

    Единственное место, где длинная таблица разворачивается в широкую, —
    и только для показа. В хранилище всё остаётся длинным.
    """
    df = load_facts()
    selected = _only_program(df[(df.report_year == year) & (~df.is_total)], program)
    if regions:
        selected = selected[selected.region.isin(regions)]
    wide = selected.pivot_table(
        index="region", columns="indicator", values="value", aggfunc="sum"
    ).reset_index()
    # Колонки: на главной — витринный список `kpi_order`, у раздела — всё,
    # что в нём есть, в порядке реестра. Тот же принцип, что у карточек
    if program:
        columns = [k for k in load_config()["indicators"] if k in wide.columns]
    else:
        columns = [k for k in load_config()["kpi_order"] if k in wide.columns]
    return wide[["region"] + columns]


#: Месяцы в родительном падеже — «28 июля», а не «28 июль».
#: Своя таблица, а не locale: имя русской локали в Windows и в Linux
#: пишется по-разному, и на сервере подпись молча стала бы английской.
MONTHS_OF = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _last_update_from_health(health: dict) -> tuple[str, str]:
    """Составляет дату и время публикации из готовых данных poll_health()."""
    if health["pub_date"] is None:
        return "—", ""
    return f"{health['pub_date']} {MONTHS_OF[health['pub_month'] - 1]}", health["pub_time"]


def get_last_update_parts() -> tuple[str, str]:
    """Момент последней публикации двумя строками: «28 июля» и «09:58».

    Разделено потому, что в шапке дата и время стоят друг под другом
    и по-разному: дата крупная, время мелкое и приглушённое. Собирать
    из одной строки обратно значило бы разбирать её же по пробелу.

    Дата показывается всегда, даже сегодняшняя: две строки не создают
    той путаницы, из-за которой get_last_update() её прячет.

    Использует poll_health() — одно открытие DuckDB вместо двух отдельных.
    """
    return _last_update_from_health(poll_health())


def _last_publish_time():
    """Отметка времени последней публикации или None. Общая для двух подписей."""
    df = _query_storage(
        "SELECT coalesce(published_at, run_at) AS t FROM versions "
        "WHERE status = 'published' ORDER BY version DESC LIMIT 1"
    )
    if df.empty or pd.isna(df.iloc[0]["t"]):
        return None
    return pd.to_datetime(df.iloc[0]["t"])


def get_last_update() -> str:
    """Когда цифры на сайте менялись в последний раз — для подписи.

    С этапа 4 это момент ПУБЛИКАЦИИ, а не разбора: свежая загрузка может
    сутки лежать в ожидании, и писать её время значило бы обещать данные,
    которых на экране ещё нет. У версий, опубликованных до этапа 4,
    момента публикации не записано — берём момент разбора.

    До 9:00 сайт показывает вчерашнюю публикацию — тогда к времени
    добавляется дата, иначе «обновлены в 09:00» читалось бы как сегодня.
    """
    ts = _last_publish_time()
    if ts is None:
        return "—"
    if ts.date() == datetime.now().date():
        return ts.strftime("%H:%M")
    return ts.strftime("%d.%m %H:%M")
