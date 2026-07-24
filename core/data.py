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


def _query_storage(query: str) -> pd.DataFrame:
    """Чтение из DuckDB — единственное место, открывающее хранилище на чтение.

    Пока etl.run переписывает файл, тот заперт на запись — доли секунды
    раз в несколько минут. Попав в это окно, не падаем сразу, а пробуем
    ещё несколько раз.

    ConnectionException — другая помеха с тем же лечением: в НАШЕМ процессе
    другой поток сайта прямо сейчас держит соединение на запись (публикует
    в 9:00 или сохраняет черновик плана — core/publish.py), а DuckDB не
    смешивает чтение и запись в одном процессе. Запись мгновенная — ждём.
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
                return con.execute(query).df()
            finally:
                con.close()
        except _LOCK_ERRORS as e:
            last_error = e
            time.sleep(_lock_delay(attempt))
    raise RuntimeError(f"Хранилище {DUCKDB_PATH} занято записью дольше ожидания: {last_error}")


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


def get_display_version() -> str:
    """Что сейчас показывает витрина: версия фактов + отпечаток плана.

    Эту строку страница держит в dcc.Store и раз в 30 сек сверяет со свежей.
    Изменилась — значит, опубликована новая версия данных ИЛИ новый план,
    и коллбэки перерисуются. Оба события меняют цифры на экране, поэтому
    следить только за версией фактов было бы мало.
    """
    return f"{get_published_version()}|{_plan_stamp()}"


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
    """
    version = get_published_version()
    if version == 0:
        # Тот же тип ошибки, что и при отсутствии файла: страницы уже умеют
        # показывать его текст плашкой вместо экрана
        raise FileNotFoundError(
            "В хранилище нет опубликованных данных. Запустите:\n"
            "  python -m etl.run   (первая загрузка публикуется сразу)"
        )
    return _facts_cached(version)


@cache.memoize()
def _facts_cached(version: int) -> pd.DataFrame:
    # version — и ключ кэша, и фильтр: в таблице лежат снимки разных версий
    df = _query_storage(f"SELECT * EXCLUDE (version) FROM facts WHERE version = {version}")
    df["is_total"] = df["is_total"].astype(bool)
    return df


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


def format_value(value: float, indicator: str) -> str:
    """Число в виде, пригодном для показа: масштаб, разряды, единица."""
    meta = get_indicator_meta(indicator)
    scaled = value / meta["divisor"]
    # Неразрывный пробел как разделитель разрядов — так принято в русской типографике
    text = f"{scaled:,.{meta['decimals']}f}".replace(",", " ")
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


def get_kpi(year: int) -> pd.DataFrame:
    """Итоги по стране за год и изменение к предыдущему году.

    Два сорта карточек. Обычные берут итог показателя из данных. Производные
    (в конфиге есть блок `derived`) в данных не лежат — считаются из итогов
    двух других показателей: «Согласно плану %» = освоено / выделено.
    """
    df = load_facts()
    cfg = load_config()

    current = _country_totals(df, year)
    previous = _country_totals(df, year - 1)

    # Опубликованный ручной план. Если он введён, знаменатель производных
    # карточек берётся из него, а не из фактов: «Согласно плану %» начинает
    # считаться от годового плана, введённого админом. Плана нет — всё как
    # раньше, от суммы показателя-знаменателя за загруженные месяцы.
    plan_current = get_published_plan(year)
    plan_previous = get_published_plan(year - 1)

    rows = []
    for indicator in cfg["kpi_order"]:
        meta = cfg["indicators"][indicator]
        derived = meta.get("derived")

        if derived:
            # Подменяется только знаменатель: числитель — это факт,
            # и ручным планом он быть не может
            denom = derived["denominator"]
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
            }
        )
    return pd.DataFrame(rows)


def get_region_choices() -> list[str]:
    """Регионы по алфавиту — для фильтра. Строка итога исключена."""
    df = load_facts()
    return sorted(df.loc[~df.is_total, "region"].unique().tolist())


def get_regions(
    indicator: str,
    year: int,
    limit: int | None = None,
    regions: list[str] | None = None,
) -> pd.DataFrame:
    """Значения по регионам за год, по убыванию. Строка итога исключена.

    regions — показать только перечисленные; None или пустой список = все.
    """
    df = load_facts()
    selected = df[
        (df.indicator == indicator) & (df.report_year == year) & (~df.is_total)
    ]
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


def get_monthly(
    indicator: str, year: int, regions: list[str] | None = None
) -> pd.DataFrame:
    """Показатель по месяцам выбранного года — для вида «динамика в году».

    Здесь всё наоборот по сравнению с остальными функциями: обычно месяцы
    сворачиваются в год, а регионы остаются; тут регионы сворачиваются
    в страну, а месяцы остаются. Правило свёртки — то же, что у показателя:
    средние усредняются, всё остальное складывается (сумма срезов по регионам —
    это срез по стране, так что и для срезов сумма верна).
    """
    df = load_facts()
    selected = df[
        (df.indicator == indicator) & (df.report_year == year) & (~df.is_total)
    ]
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


def get_region_dynamics(
    indicator: str, regions: list[str] | None = None
) -> pd.DataFrame:
    """Показатель по регионам за все годы сразу — для диаграммы «сравнение лет»."""
    df = load_facts()
    selected = df[(df.indicator == indicator) & (~df.is_total)]
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
    indicator: str, year: int, regions: list[str] | None = None
) -> pd.DataFrame:
    """Регионы с колонкой макрорегиона — для иерархических диаграмм."""
    df = get_regions(indicator, year, regions=regions)
    mapping = get_macroregion_map()
    df["macroregion"] = df["region"].map(mapping).fillna("Прочие")
    return df


def get_change(
    indicator: str, year: int, regions: list[str] | None = None
) -> pd.DataFrame:
    """Изменение показателя за выбранный год к предыдущему, по регионам.

    Колонки: region, prev, current, delta. Отсортировано по убыванию delta.

    Сравниваем именно `year` и `year - 1`, а не «два последних года в данных»:
    последний год в источнике почти всегда неполный, и сравнение с ним
    показало бы обвал там, где просто ещё не наступили остальные месяцы.
    """
    empty = pd.DataFrame(columns=["region", "prev", "current", "delta"])
    df = load_facts()
    selected = df[(df.indicator == indicator) & (~df.is_total)]
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


def get_table(year: int, regions: list[str] | None = None) -> pd.DataFrame:
    """Широкая таблица для экрана: регион в строке, показатели в колонках.

    Единственное место, где длинная таблица разворачивается в широкую, —
    и только для показа. В хранилище всё остаётся длинным.
    """
    df = load_facts()
    selected = df[(df.report_year == year) & (~df.is_total)]
    if regions:
        selected = selected[selected.region.isin(regions)]
    wide = selected.pivot_table(
        index="region", columns="indicator", values="value", aggfunc="sum"
    ).reset_index()
    order = ["region"] + [k for k in load_config()["kpi_order"] if k in wide.columns]
    return wide[order]


def get_last_update() -> str:
    """Когда цифры на сайте менялись в последний раз — для подписи.

    С этапа 4 это момент ПУБЛИКАЦИИ, а не разбора: свежая загрузка может
    сутки лежать в ожидании, и писать её время значило бы обещать данные,
    которых на экране ещё нет. У версий, опубликованных до этапа 4,
    момента публикации не записано — берём момент разбора.

    До 9:00 сайт показывает вчерашнюю публикацию — тогда к времени
    добавляется дата, иначе «обновлены в 09:00» читалось бы как сегодня.
    """
    df = _query_storage(
        "SELECT coalesce(published_at, run_at) AS t FROM versions "
        "WHERE status = 'published' ORDER BY version DESC LIMIT 1"
    )
    if df.empty or pd.isna(df.iloc[0]["t"]):
        return "—"
    ts = pd.to_datetime(df.iloc[0]["t"])
    if ts.date() == datetime.now().date():
        return ts.strftime("%H:%M")
    return ts.strftime("%d.%m %H:%M")
