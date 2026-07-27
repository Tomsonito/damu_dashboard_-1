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

def _table_ready() -> bool:
    """Есть ли таблица widgets — до первой правки её нет."""
    try:
        df = _query_storage(
            "SELECT count(*) AS n FROM information_schema.tables "
            "WHERE table_name = 'widgets'"
        )
    except (FileNotFoundError, duckdb.Error):
        return False
    return bool(df.iloc[0]["n"])


def default_widgets() -> list[dict]:
    """Стартовый набор из config.yaml, с проставленными позициями."""
    raw = load_config().get("default_widgets") or []
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


def is_customized() -> bool:
    """Набор уже настраивали руками (а не берётся из config.yaml)?"""
    if not _table_ready():
        return False
    df = _query_storage("SELECT count(*) AS n FROM widgets")
    return bool(df.iloc[0]["n"])


def get_widgets() -> list[dict]:
    """Что показывать на главной: настроенный набор или умолчания.

    Единственная функция, которую спрашивает страница. Откуда взялся
    список — её не касается.
    """
    if not is_customized():
        return default_widgets()
    df = _query_storage(
        "SELECT id, position, chart, indicator, size FROM widgets ORDER BY position, id"
    )
    return df.to_dict("records")


def widgets_table() -> pd.DataFrame:
    """То же самое таблицей — удобно для страницы-редактора."""
    return pd.DataFrame(get_widgets())


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
               position   INTEGER   NOT NULL,  -- порядок на экране: 1, 2, 3...
               chart      VARCHAR   NOT NULL,  -- ключ вида из реестра charts
               indicator  VARCHAR   NOT NULL,  -- ключ показателя из config.yaml
               size       VARCHAR   NOT NULL,  -- ключ пресета из widget_sizes
               author     VARCHAR   NOT NULL,
               updated_at TIMESTAMP NOT NULL
           )"""
    )


def _materialize(con: duckdb.DuckDBPyConnection, author: str) -> None:
    """Переносит умолчания из config.yaml в базу, если набора там ещё нет.

    Зовётся первой строкой каждой правки. После этого «набор по умолчанию»
    и «настроенный набор» — одно и то же по устройству, и правки не надо
    описывать двумя способами.
    """
    if con.execute("SELECT count(*) FROM widgets").fetchone()[0]:
        return
    now = datetime.now()
    for item in default_widgets():
        con.execute(
            "INSERT INTO widgets (id, position, chart, indicator, size, author, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [item["position"], item["position"], item["chart"], item["indicator"],
             item["size"], author, now],
        )


def _renumber(con: duckdb.DuckDBPyConnection) -> None:
    """Сжимает позиции в 1, 2, 3... — после удаления в них появляются дыры.

    Дыры сами по себе не мешают (сортировка всё равно верна), но с ровными
    номерами проще и глазами читать, и перестановку считать.
    """
    con.execute(
        "CREATE OR REPLACE TEMP TABLE ordered AS "
        "SELECT id, row_number() OVER (ORDER BY position, id) AS pos FROM widgets"
    )
    con.execute(
        "UPDATE widgets SET position = (SELECT pos FROM ordered WHERE ordered.id = widgets.id)"
    )
    con.execute("DROP TABLE ordered")


def add(chart: str, indicator: str, size: str, author: str) -> None:
    """Добавляет виджет в конец набора."""
    _validate(chart, indicator, size)
    _require_storage()
    now = datetime.now()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author)
        new_id = con.execute("SELECT coalesce(max(id), 0) + 1 FROM widgets").fetchone()[0]
        position = con.execute("SELECT coalesce(max(position), 0) + 1 FROM widgets").fetchone()[0]
        con.execute(
            "INSERT INTO widgets (id, position, chart, indicator, size, author, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [new_id, position, chart, indicator, size, author, now],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def update(widget_id: int, field: str, value: str, author: str) -> None:
    """Меняет одно поле виджета: показатель, вид или размер."""
    if field not in FIELDS:
        raise ValueError(f"Поле «{field}» у виджета не настраивается.")
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author)
        row = con.execute(
            "SELECT chart, indicator, size FROM widgets WHERE id = ?", [int(widget_id)]
        ).fetchone()
        if row is None:
            raise ValueError("Виджет уже удалён — обновите страницу.")
        values = dict(zip(FIELDS, row))
        values[field] = value
        _validate(values["chart"], values["indicator"], values["size"])
        con.execute(
            f"UPDATE widgets SET {field} = ?, author = ?, updated_at = ? WHERE id = ?",
            [value, author, datetime.now(), int(widget_id)],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def remove(widget_id: int, author: str) -> None:
    """Убирает виджет с экрана."""
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        _materialize(con, author)
        con.execute("DELETE FROM widgets WHERE id = ?", [int(widget_id)])
        _renumber(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def move(widget_id: int, delta: int, author: str) -> None:
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
        _materialize(con, author)
        _renumber(con)
        current = con.execute(
            "SELECT position FROM widgets WHERE id = ?", [int(widget_id)]
        ).fetchone()
        if current is not None:
            target = current[0] + (1 if delta > 0 else -1)
            neighbour = con.execute(
                "SELECT id FROM widgets WHERE position = ?", [target]
            ).fetchone()
            if neighbour is not None:
                con.execute(
                    "UPDATE widgets SET position = ? WHERE id = ?",
                    [current[0], neighbour[0]],
                )
                con.execute(
                    "UPDATE widgets SET position = ? WHERE id = ?",
                    [target, int(widget_id)],
                )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def reset() -> None:
    """Удаляет настроенный набор — главная снова берёт его из config.yaml."""
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("DELETE FROM widgets")
    finally:
        con.close()


def last_change() -> tuple[str, datetime] | None:
    """Кто и когда правил набор — для подписи в редакторе."""
    if not _table_ready():
        return None
    df = _query_storage("SELECT author, updated_at FROM widgets ORDER BY updated_at DESC LIMIT 1")
    if df.empty:
        return None
    return str(df.iloc[0]["author"]), df.iloc[0]["updated_at"].to_pydatetime()
