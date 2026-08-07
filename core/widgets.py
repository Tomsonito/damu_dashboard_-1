"""Набор виджетов главного экрана: что показывать, чем и какого размера.

Раньше на главной был один график, выбираемый списком. Здесь — несколько
сразу, и их состав настраивает админ прямо на сайте, не трогая код.

Устройство ровно такое же, как у оформления (core/theme.py), и это
намеренно — один механизм, который достаточно понять один раз:

- **умолчания** лежат в `config.yaml`, блок `default_widgets` — что видит
  тот, кто ничего не настраивал. Едут с проектом из git;
- **выбор админа** лежит в таблице `widgets` хранилища. Первая же правка
  переносит туда весь набор целиком (см. `_materialize`), дальше главная
  читает только его. Кнопка «Вернуть набор по умолчанию» удаляет строки —
  и снова начинает действовать `config.yaml`.

Почему набор переносится целиком, а не по одному виджету: иначе «подвинуть
второй виджет вверх» в наборе, которого ещё нет в базе, было бы нечего
двигать. Материализация делает список настоящим — и дальше все правки
работают с ним одинаково.

Порядок держится колонкой `position` (1, 2, 3...), а не порядком строк
в таблице: у строк в базе порядка нет вообще, полагаться на него нельзя.
Перестановка — обмен позициями двух соседей.

Перетаскивания мышью здесь нет намеренно: в Dash его не существует,
а сторонний компонент — чужой код, который однажды отстанет от новой
версии Dash. Кнопки «вверх/вниз» надёжнее и делаются сразу.
"""

from datetime import datetime

import duckdb
import pandas as pd

from core import charts
from core.data import DUCKDB_PATH, _connect_write, _query_storage, load_config

#: Ключи, которые описывают один виджет
FIELDS = ("chart", "indicator", "size")

#: Ключ главного экрана. Разделы пользуются своими ключами из config.yaml
#: (`sections` → `key`), и наборы у них независимые.
MAIN_PAGE = "main"


def defaults_key(page: str) -> str:
    """Откуда брать умолчания: у главной свой список, у разделов общий.

    !! Не единственный источник умолчаний для разделов — см.
    `default_widgets()`: у конкретной пары раздел:вкладка может быть
    свой набор в `section_widgets_by_page`, он проверяется раньше этого.
    Функция осталась ради `page_choices()`-подобных мест, которым нужно
    только «это главная или раздел», без выбора конкретного набора.
    """
    return "default_widgets" if page == MAIN_PAGE else "section_widgets"


def page_key(section: str, tab: str = "") -> str:
    """Ключ набора виджетов: раздел плюс вкладка-разрез.

    У каждой вкладки внутри раздела свой набор — «Динамика по годам»
    и «ОКЭД/Регионы» показывают разное. Ключ склеивается двоеточием:
    `guarantee:regions`. Главная обходится без вкладок и остаётся `main`.
    """
    if not section or section == MAIN_PAGE:
        return MAIN_PAGE
    return f"{section}:{tab}" if tab else section


def split_page(page: str) -> tuple[str, str]:
    """Обратная операция: `guarantee:regions` -> («guarantee», «regions»)."""
    if ":" in page:
        section, tab = page.split(":", 1)
        return section, tab
    return page, ""


def page_choices() -> list[dict]:
    """Страницы для настройщика — только разделы.

    Главной в списке нет с 29.07.2026: сетку виджетов с неё убрали, там
    теперь витрина инструментов по макету. Оставить её в списке значило бы
    дать админу настраивать экран, которого никто не увидит.

    Если сетка на главную вернётся, вернуть сюда строку
    `{"label": "Главная (витрина)", "value": MAIN_PAGE}` — умолчания для неё
    (`default_widgets` в config.yaml) на месте.
    """
    sections = load_config().get("sections") or []
    return [{"label": s["title"], "value": s["key"]} for s in sections]


def first_page() -> str:
    """Что открыть в настройщике по умолчанию — первый раздел из конфига."""
    choices = page_choices()
    return choices[0]["value"] if choices else MAIN_PAGE


def tabs_of(section: str) -> list[dict]:
    """Вкладки-разрезы раздела: свой список, если описан, иначе общий.

    У большинства разделов разрезы одинаковые, поэтому в `config.yaml`
    лежит один общий список `section_tabs`. Но у отдельных разделов их
    больше (у «Гар. выдача» — девять, часть из них в группе ГФ1), и такой
    раздел описывает свои вкладки в `section_tabs_by_section`.

    Ключ раздела может прийти вместе с вкладкой (`guarantee:regions`) —
    отрежем, спрашивают всё равно про раздел целиком.
    """
    key, _ = split_page(section or "")
    cfg = load_config()
    own = (cfg.get("section_tabs_by_section") or {}).get(key)
    return own or (cfg.get("section_tabs") or [])


def tab_choices(section: str = "") -> list[dict]:
    """Вкладки-разрезы для выпадающего списка в настройщике."""
    return [
        {"label": t["title"] + ("" if t.get("data") else " — ждёт данных"),
         "value": t["key"]}
        for t in tabs_of(section)
    ]


def page_title(page: str) -> str:
    for item in page_choices():
        if item["value"] == page:
            return item["label"]
    return page


def program_of(page: str) -> str | None:
    """Раздел (значение колонки `program`), к которому относится страница.

    У главной раздела нет — она смотрит на всё сразу, поэтому None.
    Название раздела берётся из `config.yaml` и должно совпадать с тем,
    что лежит в данных: по нему страница и отбирает свои строки.

    Ключ может прийти вместе с вкладкой (`guarantee:regions`) — вкладка
    на отбор данных не влияет, она выбирает только набор виджетов.
    """
    section, _ = split_page(page or "")
    if not section or section == MAIN_PAGE:
        return None
    for item in load_config().get("sections") or []:
        if item["key"] == section:
            return item["title"]
    return None


# ------------------------------------------------------------ справочники

def sizes() -> dict:
    """Пресеты размеров из config.yaml."""
    return load_config().get("widget_sizes") or {}


def size_meta(size: str) -> dict:
    """Колонки и высота одного пресета. Незнакомый размер — как «средний».

    Подстраховка на случай, если пресет удалили из config.yaml, а виджет
    с ним остался в базе: экран должен нарисоваться, а не упасть.
    """
    preset = sizes().get(size)
    if preset:
        return preset
    return {"label": size, "columns": 6, "height": 420}


def size_choices() -> list[dict]:
    return [{"label": v.get("label", k), "value": k} for k, v in sizes().items()]


def chart_choices() -> list[dict]:
    """Виды диаграмм — прямо из реестра core/charts.py.

    Не свой список: добавите вид декоратором @chart — он появится
    в настройщике сам, править этот файл не нужно.
    """
    return charts.get_choices()


def indicator_choices() -> list[dict]:
    """Показатели для виджета: те, что есть в данных, плюс производные.

    Производные («Согласно плану %») в таблице фактов не лежат — они
    считаются из двух других показателей, поэтому обычный фильтр их
    не показывает. Но виджету-шкале нужен именно такой показатель,
    значит здесь список шире.

    Заведомо пустых показателей в списке всё равно нет: реестр в конфиге
    описывает больше источников, чем подключено, и предлагать их незачем.
    """
    from core import data  # локально: data тянет кэш, а он нужен не всегда

    choices = data.get_indicator_choices()
    known = {item["value"] for item in choices}
    for key, meta in (load_config().get("indicators") or {}).items():
        if meta.get("derived") and key not in known:
            choices.append({"label": meta["title"], "value": key})
    return choices


def describe(widget: dict) -> str:
    """Название виджета для экрана: «Выделено бюджета — Полосы (рейтинг)»."""
    cfg = load_config()
    title = cfg["indicators"].get(widget["indicator"], {}).get("title", widget["indicator"])
    label = next(
        (c["label"] for c in charts.get_choices() if c["value"] == widget["chart"]),
        widget["chart"],
    )
    return f"{title} — {label}"


# ------------------------------------------------------------------ чтение

def _has_table(name: str) -> bool:
    """Есть ли такая таблица в хранилище — до первой правки их нет."""
    try:
        df = _query_storage(
            "SELECT count(*) AS n FROM information_schema.tables "
            f"WHERE table_name = '{name}'"
        )
    except (FileNotFoundError, duckdb.Error):
        return False
    return bool(df.iloc[0]["n"])


def _table_ready() -> bool:
    return _has_table("widgets")


def default_widgets(page: str = MAIN_PAGE) -> list[dict]:
    """Стартовый набор из config.yaml, с проставленными позициями.

    Три уровня, проверяются по порядку:

    1. `section_widgets_by_page[page]` — набор именно для этой пары
       раздел:вкладка (`guarantee:years`). Заведён 04.08.2026 при переносе
       «Описание разделов.md»: там у каждой вкладки своё число диаграмм,
       и один общий набор на все вкладки раздела для этого не годился.
    2. `section_widgets` — общий набор для любого раздела, у которого нет
       записи на уровне 1. На нём остаются все вкладки разделов, которые
       документ ещё не описал.
    3. Список пуст — раздел без умолчаний, `get_widgets` вернёт «нет
       виджетов», а не упадёт.

    Отсутствие ключа на уровне 1 и **пустой список** на уровне 1 — разные
    вещи: отсутствие ключа значит «не описано, взять общее», пустой список
    значит «описано, и в нём осознанно ничего нет» (например, диаграмма
    в документе не названа вовсе — ГФ2 без «Годов»).
    """
    cfg = load_config()
    if page == MAIN_PAGE:
        raw = cfg.get("default_widgets") or []
    else:
        by_page = cfg.get("section_widgets_by_page") or {}
        raw = by_page[page] if page in by_page else (cfg.get("section_widgets") or [])
    return [
        {
            # Номер = позиция, и это не случайность: при материализации
            # (_materialize) умолчания ложатся в базу ровно с такими же
            # номерами. Поэтому кнопки редактора, нажатые на ещё
            # не сохранённом наборе, попадают именно в тот виджет,
            # который админ видел на экране.
            "id": i + 1,
            "position": i + 1,
            "chart": item.get("chart", "bar"),
            "indicator": item.get("indicator", ""),
            "size": item.get("size", "medium"),
        }
        for i, item in enumerate(raw)
    ]


def is_customized(page: str = MAIN_PAGE) -> bool:
    """Набор этой страницы уже настраивали руками (а не взят из config.yaml)?

    !! Отвечает **отметка** в `widget_pages`, а не наличие строк в `widgets`.
    Раньше здесь считались строки, и от этого была ошибка: удаляешь последний
    виджет — строк ноль — хранилище становится неотличимо от «здесь никогда
    ничего не настраивали», и умолчания из `config.yaml` возвращались все
    разом (поймано пользователем 29.07.2026). Хуже того, следующий добавленный
    виджет заново притаскивал за собой весь набор по умолчанию.

    Пустой набор — это законный выбор админа: «на этой странице виджетов нет».
    Выразить его подсчётом строк невозможно в принципе, поэтому и появилась
    отдельная отметка.
    """
    if not _has_table("widget_pages"):
        # Хранилище ещё не доведено до новой схемы (migrate не отработал) —
        # ведём себя как раньше, чтобы страница открылась, а не упала
        return _table_ready() and bool(_query_storage(
            f"SELECT count(*) AS n FROM widgets WHERE page = '{page}'"
        ).iloc[0]["n"])
    df = _query_storage(
        f"SELECT count(*) AS n FROM widget_pages WHERE page = '{page}'"
    )
    return bool(df.iloc[0]["n"])


def get_widgets(page: str = MAIN_PAGE) -> list[dict]:
    """Что показывать на странице: настроенный набор или умолчания.

    Единственная функция, которую спрашивает страница. Откуда взялся
    список — её не касается. Наборы у страниц независимые: настроили
    «Гар. выдачу» — на остальных разделах по-прежнему умолчания.
    """
    if not is_customized(page):
        return default_widgets(page)
    df = _query_storage(
        "SELECT id, position, chart, indicator, size FROM widgets "
        f"WHERE page = '{page}' ORDER BY position, id"
    )
    return df.to_dict("records")


def widgets_table(page: str = MAIN_PAGE) -> pd.DataFrame:
    """То же самое таблицей — удобно для страницы-редактора."""
    return pd.DataFrame(get_widgets(page))


# ------------------------------------------------------------------ запись

def _require_storage() -> None:
    """Набор виджетов живёт в хранилище — без него писать некуда.

    !! Проверка обязательна: duckdb.connect на несуществующий файл СОЗДАЁТ
    его, и первая же правка породила бы хранилище без фактов и версий.
    Та же причина, что и в core/theme.py.
    """
    if not DUCKDB_PATH.exists():
        raise ValueError(
            "Хранилища ещё нет, а набор виджетов хранится в нём. "
            "Сначала запустите: python -m etl.run"
        )


def _validate(chart: str, indicator: str, size: str) -> None:
    """Проверка при записи: в базе не должно лежать того, что не нарисуется."""
    if chart not in {c["value"] for c in charts.get_choices()}:
        raise ValueError(f"Вида диаграммы «{chart}» нет в реестре.")
    if indicator not in (load_config().get("indicators") or {}):
        raise ValueError(f"Показателя «{indicator}» нет в config.yaml.")
    if size not in sizes():
        raise ValueError(f"Размера «{size}» нет в config.yaml, блок widget_sizes.")


def _ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS widgets (
               id         INTEGER   NOT NULL,  -- номер виджета, растёт сам
               page       VARCHAR,             -- 'main' или ключ раздела
               position   INTEGER   NOT NULL,  -- порядок на экране: 1, 2, 3...
               chart      VARCHAR   NOT NULL,  -- ключ вида из реестра charts
               indicator  VARCHAR   NOT NULL,  -- ключ показателя из config.yaml
               size       VARCHAR   NOT NULL,  -- ключ пресета из widget_sizes
               author     VARCHAR   NOT NULL,
               updated_at TIMESTAMP NOT NULL
           )"""
    )
    # Таблица могла остаться от версии без разделов — там колонки `page` нет,
    # а её строки описывали главный экран. Достраиваем и подписываем их.
    con.execute("ALTER TABLE widgets ADD COLUMN IF NOT EXISTS page VARCHAR")
    con.execute("UPDATE widgets SET page = ? WHERE page IS NULL", [MAIN_PAGE])

    # Отметка «эту страницу настраивают вручную». Отдельная таблица, а не
    # колонка в `widgets`: набор может быть ПУСТЫМ (админ убрал все виджеты),
    # и тогда в `widgets` про эту страницу нет ни одной строки, а сказать
    # «набор настроен, и он пуст» всё равно надо.
    con.execute(
        """CREATE TABLE IF NOT EXISTS widget_pages (
               page       VARCHAR   NOT NULL,  -- 'main' или ключ раздела
               author     VARCHAR   NOT NULL,
               updated_at TIMESTAMP NOT NULL
           )"""
    )
    # Хранилище из версии до этой отметки: страницы, у которых строки уже
    # есть, настраивали руками — проставим им отметку задним числом, иначе
    # после обновления их наборы разом заменились бы умолчаниями
    con.execute(
        "INSERT INTO widget_pages (page, author, updated_at) "
        "SELECT page, 'миграция', now() FROM widgets "
        "WHERE page IS NOT NULL AND page NOT IN (SELECT page FROM widget_pages) "
        "GROUP BY page"
    )


def migrate() -> None:
    """Доводит таблицу до текущей схемы. Зовётся при старте сайта (app.py).

    !! Без этого падало чтение: таблица `widgets` могла остаться от версии
    без разделов, где колонки `page` не было, а достраивалась она только
    при записи — то есть страница успевала спросить набор раньше, чем
    кто-нибудь что-нибудь сохранит. Проверено запуском: главная падала
    с «Referenced column "page" not found».

    Повторный вызов ничего не делает: все шаги «если ещё не сделано».
    """
    if not DUCKDB_PATH.exists() or not _table_ready():
        return
    con = _connect_write()
    try:
        _ensure_table(con)
    finally:
        con.close()


def _materialize(con: duckdb.DuckDBPyConnection, author: str, page: str) -> None:
    """Переносит умолчания страницы из config.yaml в базу, если их там нет.

    Зовётся первой строкой каждой правки. После этого «набор по умолчанию»
    и «настроенный набор» — одно и то же по устройству, и правки не надо
    описывать двумя способами.

    Материализуется **только та страница, которую правят**: соседние
    разделы продолжают жить на умолчаниях, и правка одного не превращает
    остальные девятнадцать в копии файла.

    !! Признак «уже материализована» — отметка в `widget_pages`, а не наличие
    строк. По строкам не выходит: у страницы с пустым набором их ноль,
    и добавление виджета к пустому набору заново притащило бы все умолчания.
    """
    now = datetime.now()
    if con.execute("SELECT count(*) FROM widget_pages WHERE page = ?",
                   [page]).fetchone()[0]:
        return
    con.execute(
        "INSERT INTO widget_pages (page, author, updated_at) VALUES (?, ?, ?)",
        [page, author, now],
    )
    # !! Номера — СВОИ У КАЖДОЙ СТРАНИЦЫ, а не сквозные по всей таблице.
    # Иначе ломается обещание из default_widgets(): у ненастроенного набора
    # номера всегда 1..N, и материализация обязана положить строки ровно
    # с такими же. При сквозной нумерации начало сдвигалось (в таблице уже
    # лежат строки другой страницы), номера расходились — и первая же
    # «Убрать» била мимо, молча ничего не удаляя. Поэтому и отбор во всех
    # запросах ниже идёт по паре (id, page), а не по одному id.
    next_id = con.execute(
        "SELECT coalesce(max(id), 0) + 1 FROM widgets WHERE page = ?", [page]
    ).fetchone()[0]
    for offset, item in enumerate(default_widgets(page)):
        con.execute(
            "INSERT INTO widgets (id, page, position, chart, indicator, size, author, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [next_id + offset, page, item["position"], item["chart"],
             item["indicator"], item["size"], author, now],
        )


def _renumber(con: duckdb.DuckDBPyConnection, page: str) -> None:
    """Сжимает позиции страницы в 1, 2, 3... — после удаления в них дыры.

    Дыры сами по себе не мешают (сортировка всё равно верна), но с ровными
    номерами проще и глазами читать, и перестановку считать.
    """
    con.execute(
        "CREATE OR REPLACE TEMP TABLE ordered AS "
        "SELECT id, row_number() OVER (ORDER BY position, id) AS pos "
        "FROM widgets WHERE page = ?", [page]
    )
    # Во временной таблице лежат только строки этой страницы, а UPDATE
    # ограничен той же страницей — номера одинаковые у разных страниц
    # (они теперь свои у каждой) друг на друга не влияют
    con.execute(
        "UPDATE widgets SET position = (SELECT pos FROM ordered WHERE ordered.id = widgets.id) "
        "WHERE page = ?", [page]
    )
    con.execute("DROP TABLE ordered")


def add(chart: str, indicator: str, size: str, author: str,
        page: str = MAIN_PAGE) -> None:
    """Добавляет виджет в конец набора выбранной страницы."""
    _validate(chart, indicator, size)
    _require_storage()
    now = datetime.now()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author, page)
        new_id = con.execute(
            "SELECT coalesce(max(id), 0) + 1 FROM widgets WHERE page = ?", [page]
        ).fetchone()[0]
        position = con.execute(
            "SELECT coalesce(max(position), 0) + 1 FROM widgets WHERE page = ?", [page]
        ).fetchone()[0]
        con.execute(
            "INSERT INTO widgets (id, page, position, chart, indicator, size, author, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [new_id, page, position, chart, indicator, size, author, now],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def update(widget_id: int, field: str, value: str, author: str,
           page: str = MAIN_PAGE) -> None:
    """Меняет одно поле виджета: показатель, вид или размер."""
    if field not in FIELDS:
        raise ValueError(f"Поле «{field}» у виджета не настраивается.")
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author, page)
        row = con.execute(
            "SELECT chart, indicator, size FROM widgets WHERE id = ? AND page = ?",
            [int(widget_id), page],
        ).fetchone()
        if row is None:
            raise ValueError("Виджет уже удалён — обновите страницу.")
        values = dict(zip(FIELDS, row))
        values[field] = value
        _validate(values["chart"], values["indicator"], values["size"])
        con.execute(
            f"UPDATE widgets SET {field} = ?, author = ?, updated_at = ? "
            "WHERE id = ? AND page = ?",
            [value, author, datetime.now(), int(widget_id), page],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def remove(widget_id: int, author: str, page: str = MAIN_PAGE) -> None:
    """Убирает виджет с экрана."""
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author, page)
        con.execute("DELETE FROM widgets WHERE id = ? AND page = ?",
                    [int(widget_id), page])
        _renumber(con, page)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def move(widget_id: int, delta: int, author: str, page: str = MAIN_PAGE) -> None:
    """Двигает виджет вверх (delta = -1) или вниз (delta = +1).

    Меняется местами с соседом, а не «вставляется на позицию»: соседей
    ровно два, и обмен не задевает остальной список. Если соседа нет
    (виджет крайний) — молча ничего не делаем: кнопка на краю списка
    и так не показывается, но нажать её могли из старой страницы.
    """
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author, page)
        _renumber(con, page)
        current = con.execute(
            "SELECT position FROM widgets WHERE id = ? AND page = ?",
            [int(widget_id), page],
        ).fetchone()
        if current is not None:
            target = current[0] + (1 if delta > 0 else -1)
            neighbour = con.execute(
                "SELECT id FROM widgets WHERE position = ? AND page = ?", [target, page]
            ).fetchone()
            if neighbour is not None:
                con.execute(
                    "UPDATE widgets SET position = ? WHERE id = ? AND page = ?",
                    [current[0], neighbour[0], page],
                )
                con.execute(
                    "UPDATE widgets SET position = ? WHERE id = ? AND page = ?",
                    [target, int(widget_id), page],
                )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def reset(page: str = MAIN_PAGE) -> None:
    """Удаляет настроенный набор страницы — она снова берёт его из config.yaml.

    Снимается и сама отметка «настраивают вручную»: именно она отличает
    «вернули умолчания» от «админ убрал все виджеты». Без этого кнопка
    «Вернуть набор по умолчанию» оставляла бы страницу пустой навсегда.
    """
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        con.execute("DELETE FROM widgets WHERE page = ?", [page])
        con.execute("DELETE FROM widget_pages WHERE page = ?", [page])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def last_change(page: str = MAIN_PAGE) -> tuple[str, datetime] | None:
    """Кто и когда правил набор этой страницы — для подписи в редакторе.

    Если набор пуст (админ убрал все виджеты), в `widgets` строк нет —
    тогда отвечает отметка из `widget_pages`. Иначе подпись «кто менял»
    исчезала бы ровно в тот момент, когда изменение самое заметное.
    """
    if not _table_ready():
        return None
    df = _query_storage(
        "SELECT author, updated_at FROM widgets "
        f"WHERE page = '{page}' ORDER BY updated_at DESC LIMIT 1"
    )
    if df.empty and _has_table("widget_pages"):
        df = _query_storage(
            "SELECT author, updated_at FROM widget_pages "
            f"WHERE page = '{page}' ORDER BY updated_at DESC LIMIT 1"
        )
    if df.empty:
        return None
    return str(df.iloc[0]["author"]), df.iloc[0]["updated_at"].to_pydatetime()
