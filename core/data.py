"""Единственная дверь к данным.

Страницы никогда не читают файлы напрямую — только вызывают функции отсюда.
Благодаря этому смена источника (Excel → БД) не потребует правок в pages/.
"""

from pathlib import Path

import pandas as pd
import yaml

FACTS_PATH = Path("data/facts.csv")
CONFIG_PATH = Path("config.yaml")


def load_config() -> dict:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_facts() -> pd.DataFrame:
    """Читает таблицу фактов.

    **Это единственная точка, знающая формат источника.** Excel/CSV сейчас —
    временная затычка, пока нет доступа к боевой БД. При переезде на БД
    меняется только тело этой функции: она должна вернуть DataFrame с теми же
    колонками. Страницы, диаграммы и реестр показателей не трогаются.

    Намеренно читаем на каждый вызов, а не один раз при импорте модуля:
    тогда после перегона ETL страница показывает свежие цифры без перезапуска
    приложения. Файл маленький (сотни строк), это ничего не стоит.
    """
    if not FACTS_PATH.exists():
        raise FileNotFoundError(
            f"Нет файла {FACTS_PATH}. Сначала запустите: python -m etl.parse_msp"
        )
    df = pd.read_csv(FACTS_PATH)
    df["is_total"] = df["is_total"].astype(bool)
    return df


def get_indicator_meta(indicator: str) -> dict:
    return load_config()["indicators"][indicator]


def get_indicator_choices() -> list[dict]:
    """Список показателей для выпадающего фильтра."""
    cfg = load_config()
    return [{"label": m["title"], "value": key} for key, m in cfg["indicators"].items()]


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


def get_kpi(year: int) -> pd.DataFrame:
    """Итоги по стране за год и изменение к предыдущему году."""
    df = load_facts()
    cfg = load_config()

    current = df[(df.report_year == year) & df.is_total].set_index("indicator")["value"]
    previous = df[(df.report_year == year - 1) & df.is_total].set_index("indicator")["value"]

    rows = []
    for indicator in cfg["kpi_order"]:
        if indicator not in current.index:
            continue
        meta = cfg["indicators"][indicator]
        value = float(current[indicator])
        before = previous.get(indicator)

        change = None
        if before is not None and not pd.isna(before) and before != 0:
            change = (value / float(before) - 1) * 100

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
    selected = selected[["region", "value"]].sort_values("value", ascending=False)
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
    return (
        selected[["region", "report_year", "value"]]
        .sort_values(["report_year", "value"])
        .reset_index(drop=True)
    )


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


def get_change(indicator: str, regions: list[str] | None = None) -> pd.DataFrame:
    """Изменение показателя между двумя последними годами, по регионам.

    Колонки: region, prev, current, delta. Отсортировано по убыванию delta.
    """
    df = load_facts()
    selected = df[(df.indicator == indicator) & (~df.is_total)]
    if regions:
        selected = selected[selected.region.isin(regions)]

    years = sorted(selected["report_year"].unique())
    if len(years) < 2:
        return pd.DataFrame(columns=["region", "prev", "current", "delta"])

    prev = selected[selected.report_year == years[-2]].set_index("region")["value"]
    current = selected[selected.report_year == years[-1]].set_index("region")["value"]

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
    """Когда данные были разобраны в последний раз."""
    return load_facts()["loaded_at"].max()
