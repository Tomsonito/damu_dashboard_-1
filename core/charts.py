"""Все виды диаграмм в одном месте.

**Добавить вид диаграммы = написать одну функцию с декоратором `@chart`.**
Больше нигде править не нужно: и список в интерфейсе, и разбор выбора
строятся из реестра автоматически.

Каждая функция получает `Ctx` (что показывать) и возвращает готовую фигуру
plotly. Общее оформление — высота, поля, фон — навешивается в `build()`,
в самих функциях его повторять не надо.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core import data

# Реестр заполняется декоратором при импорте модуля
_REGISTRY: dict[str, dict] = {}


@dataclass
class Ctx:
    """Всё, что диаграмма может попросить: что показывать и в каком масштабе."""

    indicator: str
    year: int
    regions: list[str] | None
    log: bool = False

    @property
    def meta(self) -> dict:
        return data.get_indicator_meta(self.indicator)

    @property
    def unit(self) -> str:
        return self.meta["display_unit"] or self.meta["unit"]

    @property
    def title(self) -> str:
        return f"{self.meta['title']} — {self.year} год"

    def scaled(self, df: pd.DataFrame, column: str = "value") -> pd.DataFrame:
        """Готовит колонки для показа.

        `shown` — значение в масштабе показа (для осей и размеров).
        `текст`  — то же значение строкой с разрядами и единицей (для подписей).
        """
        out = df.copy()
        out["shown"] = out[column] / self.meta["divisor"]
        out["текст"] = [data.format_value(v, self.indicator) for v in out[column]]
        return out


def chart(value: str, label: str, log_ok: bool = False):
    """Регистрирует функцию как вид диаграммы.

    log_ok=True — вид умеет логарифмическую шкалу. Отмечен он только там,
    где логарифм честен: на точках, ящиках и подобном. На столбцах и площадях
    логарифм врёт, потому что длина столбца обязана быть пропорциональна
    значению и отсчитываться от нуля.
    """

    def register(fn):
        _REGISTRY[value] = {"label": label, "builder": fn, "log_ok": log_ok}
        return fn

    return register


def get_choices() -> list[dict]:
    """Список видов для переключателя в интерфейсе."""
    return [{"label": item["label"], "value": key} for key, item in _REGISTRY.items()]


def supports_log(chart_type: str) -> bool:
    entry = _REGISTRY.get(chart_type)
    return bool(entry and entry["log_ok"])


def build(chart_type: str, indicator: str, year, regions, log: bool = False) -> go.Figure:
    """Собирает выбранную диаграмму и навешивает общее оформление."""
    entry = _REGISTRY.get(chart_type) or _REGISTRY["bar"]
    ctx = Ctx(
        indicator=indicator,
        year=int(year),
        regions=regions or None,
        log=bool(log) and entry["log_ok"],
    )
    fig = entry["builder"](ctx)
    fig.update_layout(
        margin=dict(l=10, r=120, t=60, b=40),
        plot_bgcolor="white",
        # Русская типографика чисел: запятая для дробей, неразрывный пробел
        # для разрядов. Иначе plotly пишет по-английски: 454,416.0
        separators=", ",
    )
    if fig.layout.height is None:  # вид мог задать свою высоту
        fig.update_layout(height=700)
    return fig


#: Ниже этого размера подписи внутри секторов читать невозможно
MIN_LABEL_SIZE = 12


def _size_floor(values: pd.Series) -> float:
    """Минимальный размер сектора — доля от самого крупного.

    Осознанный компромисс: у мелких регионов сектор растягивается до порога,
    иначе подпись в него не помещается и вылезает поверх соседей.

    Чтобы это не превращалось в обман, соблюдаются два правила:
    числа в подписи и в подсказке — **всегда настоящие**, а в заголовке
    появляется пометка, что размеры подтянуты. Порог задаётся в config.yaml,
    ключ `charts.min_slice_percent`; 0 отключает подтягивание совсем.
    """
    percent = float(
        data.load_config().get("charts", {}).get("min_slice_percent", 0)
    )
    if percent <= 0 or values.empty:
        return 0.0
    return float(values.max()) * percent / 100


def _label(value: float, ctx: "Ctx") -> str:
    """Настоящее значение строкой: разряды пробелом, единица в конце."""
    shown = value / ctx.meta["divisor"]
    text = f"{shown:,.{ctx.meta['decimals']}f}".replace(",", " ")
    return f"{text} {ctx.meta['display_unit']}".strip()


def _adjusted_note(raised: int, ctx: "Ctx") -> str:
    """Пометка в заголовок, если размеры пришлось подтянуть."""
    if not raised:
        return ""
    percent = data.load_config().get("charts", {}).get("min_slice_percent", 0)
    return f"<br><sub>у {raised} регионов сектор увеличен до {percent} % — числа настоящие</sub>"


def _flat_nodes(ctx: "Ctx") -> tuple[pd.DataFrame, int]:
    """Плоский список регионов для круговой и плиток."""
    df = data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions).copy()
    floor = _size_floor(df["value"])
    df["display"] = df["value"].clip(lower=floor)
    df["подпись"] = [_label(v, ctx) for v in df["value"]]
    return df, int((df["value"] < floor).sum())


#: Что показать, когда за выбранный год у показателя нет данных.
#: Источники разной длины: выгрузка МСП — 2024–2025, таблицы БД — 2022–2026.
NO_DATA = "За этот год у показателя нет данных.<br>Выберите другой год или показатель."


def _tree_nodes(ctx: "Ctx") -> tuple[pd.DataFrame, int]:
    """Узлы для лучей и сосулек: макрорегионы и области.

    Строим вручную, а не через `px`, чтобы у каждого узла — включая
    макрорегионы — были и подтянутый размер, и настоящее значение в подписи.
    """
    df = data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions)
    if df.empty:
        return pd.DataFrame(columns=["id", "label", "parent", "value", "display", "подпись"]), 0
    floor = _size_floor(df["value"])

    rows: list[dict] = []
    for macro, group in df.groupby("macroregion"):
        leaves = [
            {
                "id": f"{macro}/{row['region']}",
                "label": row["region"],
                "parent": macro,
                "value": float(row["value"]),
                "display": max(float(row["value"]), floor),
            }
            for _, row in group.iterrows()
        ]
        rows.extend(leaves)
        rows.append(
            {
                "id": macro,
                "label": macro,
                "parent": "",
                "value": float(group["value"].sum()),
                # Родитель обязан быть суммой детей, иначе plotly ругается
                "display": sum(leaf["display"] for leaf in leaves),
            }
        )

    nodes = pd.DataFrame(rows)
    nodes["подпись"] = [_label(v, ctx) for v in nodes["value"]]
    return nodes, int((df["value"] < floor).sum())


def _hierarchy_style(fig: go.Figure) -> go.Figure:
    """Общее для круговой, плиток, лучей и сосулек: размер шрифта подписей."""
    fig.update_traces(insidetextfont=dict(size=MIN_LABEL_SIZE + 1))
    fig.update_layout(uniformtext=dict(minsize=MIN_LABEL_SIZE, mode="hide"))
    return fig


def _message(text: str) -> go.Figure:
    """Пустая фигура с текстом — вместо падения, когда рисовать нечего."""
    fig = go.Figure()
    fig.add_annotation(
        text=text, showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5,
        font=dict(size=14), align="center",
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ─────────────────────────── Рейтинги ───────────────────────────


@chart("bar", "Полосы — рейтинг")
def _bar(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.bar(
        df, x="shown", y="region", orientation="h",
        text=[data.format_value(v, ctx.indicator) for v in df["value"]],
        labels={"shown": ctx.unit, "region": ""}, title=ctx.title,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_yaxes(categoryorder="total ascending")
    return fig


@chart("dot", "Точки — рейтинг (умеет логарифм)", log_ok=True)
def _dot(ctx: Ctx) -> go.Figure:
    """То же, что полосы, но точкой.

    Точка не подразумевает отсчёт от нуля — значит на ней логарифмическая шкала
    честна. Это главный приём против «разница огромная»: на логарифме Ұлытау
    с 19 тысячами и Алматы с 454 тысячами видны одинаково хорошо.
    """
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.scatter(
        df, x="shown", y="region",
        text=[data.format_value(v, ctx.indicator) for v in df["value"]],
        labels={"shown": ctx.unit, "region": ""},
        title=ctx.title + (" — логарифмическая шкала" if ctx.log else ""),
    )
    fig.update_traces(marker=dict(size=11), textposition="middle right")
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_xaxes(showgrid=True, gridcolor="#eee")
    if ctx.log:
        fig.update_xaxes(type="log")
    return fig


@chart("facets", "Панели по макрорегионам — свой масштаб у каждой")
def _facets(ctx: Ctx) -> go.Figure:
    """Отдельная панель на макрорегион, оси независимы.

    Второй приём против разброса: не втискивать всё в одну шкалу, а сравнивать
    похожее с похожим. Ұлытау меряется с Карагандинской в своей панели,
    а не теряется рядом с Алматы.
    """
    df = ctx.scaled(
        data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions)
    )
    fig = px.bar(
        df, x="shown", y="region", orientation="h",
        facet_col="macroregion", facet_col_wrap=3,
        text=[data.format_value(v, ctx.indicator) for v in df["value"]],
        labels={"shown": ctx.unit, "region": ""},
        title=f"{ctx.title} — по макрорегионам, у каждого своя шкала",
    )
    # Вот ради этой строки всё и затевалось: оси не общие
    fig.update_xaxes(matches=None, showticklabels=True)
    fig.update_yaxes(matches=None, showticklabels=True)
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(height=900)
    return fig


@chart("funnel", "Воронка — убывание")
def _funnel(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.funnel(
        df, x="shown", y="region",
        labels={"shown": ctx.unit, "region": ""}, title=ctx.title,
    )
    fig.update_layout(yaxis=dict(autorange="reversed"))
    return fig


# ─────────────────────────── Доли и структура ───────────────────────────


@chart("pie", "Круговая — доли")
def _pie(ctx: Ctx) -> go.Figure:
    df, raised = _flat_nodes(ctx)
    if df.empty:
        return _message(NO_DATA)
    fig = go.Figure(
        go.Pie(
            labels=df["region"],
            values=df["display"],
            text=df["подпись"],
            sort=False,
            textposition="inside",
            texttemplate="%{label}<br>%{text}",
            hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(title=ctx.title + _adjusted_note(raised, ctx))
    return _hierarchy_style(fig)


@chart("treemap", "Плитки — структура")
def _treemap(ctx: Ctx) -> go.Figure:
    df, raised = _flat_nodes(ctx)
    if df.empty:
        return _message(NO_DATA)
    fig = go.Figure(
        go.Treemap(
            labels=df["region"],
            parents=[""] * len(df),
            values=df["display"],
            text=df["подпись"],
            texttemplate="%{label}<br>%{text}",
            hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(title=ctx.title + _adjusted_note(raised, ctx))
    return _hierarchy_style(fig)


@chart("sunburst", "Солнечные лучи — по макрорегионам")
def _sunburst(ctx: Ctx) -> go.Figure:
    nodes, raised = _tree_nodes(ctx)
    if nodes.empty:
        return _message(NO_DATA)
    fig = go.Figure(
        go.Sunburst(
            ids=nodes["id"],
            labels=nodes["label"],
            parents=nodes["parent"],
            values=nodes["display"],
            text=nodes["подпись"],
            branchvalues="total",
            texttemplate="%{label}<br>%{text}",
            hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(title=ctx.title + _adjusted_note(raised, ctx), height=900)
    return _hierarchy_style(fig)


@chart("icicle", "Сосульки — по макрорегионам")
def _icicle(ctx: Ctx) -> go.Figure:
    nodes, raised = _tree_nodes(ctx)
    if nodes.empty:
        return _message(NO_DATA)
    fig = go.Figure(
        go.Icicle(
            ids=nodes["id"],
            labels=nodes["label"],
            parents=nodes["parent"],
            values=nodes["display"],
            text=nodes["подпись"],
            branchvalues="total",
            texttemplate="%{label}<br>%{text}",
            hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(title=ctx.title + _adjusted_note(raised, ctx), height=900)
    return _hierarchy_style(fig)


# ─────────────────────────── Изменение во времени ───────────────────────────


@chart("years", "Сравнение лет")
def _years(ctx: Ctx) -> go.Figure:
    """Все годы сразу — фильтр года на этот вид не влияет."""
    df = ctx.scaled(data.get_region_dynamics(ctx.indicator, ctx.regions))
    df["год"] = df["report_year"].astype(str)
    fig = px.bar(
        df, x="shown", y="region", color="год", barmode="group", orientation="h",
        labels={"shown": ctx.unit, "region": ""},
        title=f"{ctx.meta['title']} — сравнение лет",
    )
    fig.update_yaxes(categoryorder="max ascending")
    return fig


@chart("slope", "Наклон — рост в процентах")
def _slope(ctx: Ctx) -> go.Figure:
    """Каждый регион приведён к 100 в первом году.

    В абсолютных величинах этот график бесполезен: у Алматы 450 тысяч, у Ұлытау 20 —
    на общей оси все линии выглядят плоскими. Приведение к 100 делает наклоны
    сопоставимыми, а в этом и весь смысл вида.
    """
    df = data.get_region_dynamics(ctx.indicator, ctx.regions)
    if df.empty:
        return _message("Нет данных")

    base_year = int(df["report_year"].min())
    base = (
        df[df.report_year == base_year][["region", "value"]]
        .rename(columns={"value": "base"})
    )
    df = df.merge(base, on="region")
    df = df[df["base"] > 0]
    if df.empty:
        return _message("Нет данных за базовый год")

    df["index"] = df["value"] / df["base"] * 100
    df["год"] = df["report_year"].astype(str)
    df["значение"] = [data.format_value(v, ctx.indicator) for v in df["value"]]

    fig = px.line(
        df, x="год", y="index", color="region", markers=True,
        hover_data={"значение": True, "index": ":.1f", "год": False},
        labels={"index": f"% к {base_year} году", "год": ""},
        title=f"{ctx.meta['title']} — рост относительно {base_year} года",
    )
    fig.add_hline(
        y=100, line_dash="dot", line_color="gray",
        annotation_text=f"уровень {base_year}", annotation_position="right",
    )
    # Категориальная ось: позиции 0 и 1. Расширяем диапазон, чтобы крайние
    # подписи и точки не липли к краям и не обрезались.
    n = df["год"].nunique()
    fig.update_xaxes(type="category", range=[-0.3, n - 0.7])
    return fig


@chart("waterfall", "Каскад — вклад в изменение")
def _waterfall(ctx: Ctx) -> go.Figure:
    df = data.get_change(ctx.indicator, ctx.year, ctx.regions)
    if df.empty:
        return _message(f"Нет данных за {ctx.year} или {ctx.year - 1} год<br>для сравнения")

    df = ctx.scaled(df, column="delta").sort_values("shown", ascending=False)
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            x=df["region"],
            y=df["shown"],
            measure=["relative"] * len(df),
            text=[f"{v:+,.1f}" for v in df["shown"]],
            textposition="outside",
            connector=dict(line=dict(color="lightgray")),
        )
    )
    fig.update_layout(
        title=f"{ctx.meta['title']} — вклад регионов, {ctx.year} к {ctx.year - 1}, {ctx.unit}",
        showlegend=False,
    )
    fig.update_xaxes(tickangle=-45)
    return fig


# ─────────────────────────── Связи и разброс ───────────────────────────


@chart("matrix", "Точки — связь показателей")
def _matrix(ctx: Ctx) -> go.Figure:
    """Все показатели сразу — выбор показателя на этот вид не влияет."""
    df = data.get_table(ctx.year, ctx.regions)
    dimensions = list(df.columns[1:])
    if df.empty or not dimensions:
        return _message(NO_DATA)
    fig = px.scatter_matrix(
        df, dimensions=dimensions, hover_name="region",
        labels={k: data.get_indicator_meta(k)["short"] for k in dimensions},
        title=f"Связь показателей между собой — {ctx.year} год",
    )
    fig.update_traces(diagonal_visible=False, showupperhalf=False)
    return fig


@chart("parallel", "Параллельные оси — профиль регионов")
def _parallel(ctx: Ctx) -> go.Figure:
    df = data.get_table(ctx.year, ctx.regions)
    dimensions = list(df.columns[1:])
    if df.empty or not dimensions:
        return _message(NO_DATA)
    if len(df) < 2:
        return _message("Нужно хотя бы два региона")
    fig = px.parallel_coordinates(
        df, dimensions=dimensions, color=dimensions[-1],
        labels={k: data.get_indicator_meta(k)["short"] for k in dimensions},
        title=f"Профиль регионов по всем показателям — {ctx.year} год",
    )
    return fig


@chart("box", "Ящик — разброс по макрорегионам", log_ok=True)
def _box(ctx: Ctx) -> go.Figure:
    """Ящик на каждый макрорегион.

    Один ящик на всю страну растягивался на всю ширину, а точки уезжали от него
    влево — смотреть было не на что. Разбивка по макрорегионам даёт шесть ящиков
    нормальной ширины и заодно отвечает на осмысленный вопрос: где области
    похожи друг на друга, а где разброс большой.
    """
    df = ctx.scaled(
        data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions)
    )
    fig = px.box(
        df, x="macroregion", y="shown", points="all", hover_name="region",
        labels={"shown": ctx.unit, "macroregion": ""},
        title=f"{ctx.title} — разброс внутри макрорегионов",
    )
    # Точки поверх ящика, а не сбоку от него
    fig.update_traces(pointpos=0, jitter=0.4, width=0.5)
    if ctx.log:
        fig.update_yaxes(type="log")
    return fig


@chart("histogram", "Гистограмма — распределение")
def _histogram(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.histogram(
        df, x="shown", nbins=10,
        labels={"shown": ctx.unit}, title=f"{ctx.title} — распределение регионов",
    )
    fig.update_layout(yaxis_title="регионов")
    return fig


# ─────────────────────────── Карта ───────────────────────────


@chart("map", "Карта Казахстана")
def _map(ctx: Ctx) -> go.Figure:
    geo = data.load_config().get("geo", {})
    path = Path(geo.get("geojson_path", "data/kz_regions.geojson"))

    if not path.exists():
        return _message(
            "Карта пока не подключена.<br><br>"
            f"Нужен файл границ областей Казахстана: <b>{path}</b><br>"
            "Формат — GeoJSON, в свойствах каждой области должно быть её название.<br>"
            "Имя поля с названием задаётся в config.yaml → geo.feature_key"
        )

    with path.open(encoding="utf-8") as f:
        geojson = json.load(f)

    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    if df.empty:
        return _message(NO_DATA)

    # Названия областей в файле границ и в данных совпадают не все:
    # у нас «Абай» и «г. Шымкент», в файле «Абайская» и «Чимкент».
    # Расхождения перечислены в config.yaml -> geo.region_map.
    renames = geo.get("region_map") or {}
    df["geo_name"] = df["region"].map(lambda r: renames.get(r, r))

    key = geo.get("feature_key", "properties.ADM1_RU")
    prop = key.split(".")[-1]
    known = {f["properties"].get(prop) for f in geojson.get("features", [])}
    missing = sorted(set(df["geo_name"]) - known)
    if missing:
        # Молча пропавший регион хуже явной ошибки: на карте он просто
        # не закрасится, и никто не заметит.
        return _message(
            "Эти области не найдены в файле границ:<br><b>"
            + ", ".join(missing)
            + "</b><br>Допишите соответствие в config.yaml → geo.region_map"
        )

    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="geo_name",
        featureidkey=key,
        color="shown",
        color_continuous_scale="Blues",
        hover_name="region",
        hover_data={"geo_name": False, "shown": False, "текст": True},
        labels={"shown": ctx.unit, "текст": ctx.meta["short"]},
        title=ctx.title,
    )
    fig.update_geos(fitbounds="locations", visible=False)
    return fig
