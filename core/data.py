"""Единственная дверь к данным.

Страницы никогда не читают файлы напрямую — только вызывают функции отсюда.
Благодаря этому смена источника (Excel → БД) не потребует правок в pages/.
"""

import time
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from core.cache import cache

DUCKDB_PATH = Path("data/analytics.duckdb")
CONFIG_PATH = Path("config.yaml")


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
    """Чтение из DuckDB — единственное место, открывающее хранилище.

    Пока etl.run переписывает файл, тот заперт на запись — доли секунды
    раз в несколько минут. Попав в это окно, не падаем сразу, а пробуем
    ещё несколько раз.
    """
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(
            f"Нет хранилища {DUCKDB_PATH}. Сначала запустите:\n"
            "  python -m etl.run   (БД -> DuckDB)"
        )
    last_error: Exception | None = None
    for _ in range(5):
        try:
            con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
            try:
                return con.execute(query).df()
            finally:
                con.close()
        except duckdb.IOException as e:
            last_error = e
            time.sleep(0.2)
    raise RuntimeError(f"Хранилище {DUCKDB_PATH} занято записью дольше секунды: {last_error}")


def get_data_version() -> int:
    """Номер последней загрузки ETL — одна строка из `versions`, дёшево.

    На этом номере держится «живость» сайта: он входит в ключ кэша фактов,
    а открытая страница раз в 30 сек сверяет его со своим и перерисовывается,
    когда номер вырос. Намеренно НЕ кэшируется — это и есть проба свежести.
    """
    df = _query_storage("SELECT coalesce(max(version), 0) AS v FROM versions")
    return int(df.iloc[0]["v"])


def load_facts() -> pd.DataFrame:
    """Читает таблицу фактов из хранилища DuckDB.

    **Это единственная точка, знающая формат источника.** До этапа 3 здесь
    читались CSV-файлы — временная затычка. Теперь источник — таблица `facts`
    в data/analytics.duckdb, которую ведёт `python -m etl.run`. Форма таблицы
    не изменилась ни на колонку, поэтому страницы, диаграммы и реестр
    показателей правок не потребовали.

    Кэшируется по версии данных: пока ETL не записал новую версию, повторные
    вызовы получают копию из памяти, а не ходят на диск. Записал — номер
    версии вырос, ключ кэша сменился, факты перечитались. Поэтому свежесть
    не страдает: кэш не «протухает», а привязан к данным.
    """
    return _facts_cached(get_data_version())


@cache.memoize()
def _facts_cached(version: int) -> pd.DataFrame:
    # version не используется в теле — он часть ключа кэша
    df = _query_storage("SELECT * FROM facts")
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


def get_kpi(year: int) -> pd.DataFrame:
    """Итоги по стране за год и изменение к предыдущему году."""
    df = load_facts()
    cfg = load_config()

    current = _country_totals(df, year)
    previous = _country_totals(df, year - 1)

    rows = []
    for indicator in cfg["kpi_order"]:
        if indicator not in current:
            continue
        meta = cfg["indicators"][indicator]
        value = current[indicator]
        before = previous.get(indicator)

        change = None
        if before:
            change = (value / before - 1) * 100

        rows.append(
            {
                "indicator": indicator,
                "short": meta["short"],
                "title": meta["title"],
                "value": value,
                "text": format_value(value, indicator),
                "change_pct": change,
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
    """Когда хранилище обновлялось в последний раз — «ЧЧ:ММ» для подписи."""
    ts = _query_storage("SELECT max(run_at) AS t FROM versions").iloc[0]["t"]
    return "—" if pd.isna(ts) else pd.to_datetime(ts).strftime("%H:%M")
