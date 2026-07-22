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
        """Добавляет колонку `shown` — значение, приведённое к масштабу показа."""
        out = df.copy()
        out["shown"] = out[column] / self.meta["divisor"]
        return out


def chart(value: str, label: str):
    """Регистрирует функцию как вид диаграммы."""

    def register(fn):
        _REGISTRY[value] = {"label": label, "builder": fn}
        return fn

    return register


def get_choices() -> list[dict]:
    """Список видов для переключателя в интерфейсе."""
    return [{"label": item["label"], "value": key} for key, item in _REGISTRY.items()]


def build(chart_type: str, indicator: str, year, regions) -> go.Figure:
    """Собирает выбранную диаграмму и навешивает общее оформление."""
    ctx = Ctx(indicator=indicator, year=int(year), regions=regions or None)
    entry = _REGISTRY.get(chart_type) or _REGISTRY["bar"]
    fig = entry["builder"](ctx)
    fig.update_layout(
        height=700,
        margin=dict(l=10, r=120, t=60, b=40),
        plot_bgcolor="white",
    )
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
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.pie(df, names="region", values="shown", title=ctx.title)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


@chart("treemap", "Плитки — структура")
def _treemap(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.treemap(df, path=["region"], values="shown", title=ctx.title)
    fig.update_traces(texttemplate="%{label}<br>%{value:,.1f}")
    return fig


@chart("sunburst", "Солнечные лучи — по макрорегионам")
def _sunburst(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(
        data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions)
    )
    fig = px.sunburst(
        df, path=["macroregion", "region"], values="shown", title=ctx.title
    )
    fig.update_traces(texttemplate="%{label}<br>%{value:,.1f}")
    return fig


@chart("icicle", "Сосульки — по макрорегионам")
def _icicle(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(
        data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions)
    )
    fig = px.icicle(
        df, path=["macroregion", "region"], values="shown", title=ctx.title
    )
    fig.update_traces(texttemplate="%{label}<br>%{value:,.1f}")
    return fig


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


@chart("slope", "Наклон — кто вырос, кто просел")
def _slope(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(data.get_region_dynamics(ctx.indicator, ctx.regions))
    df["год"] = df["report_year"].astype(str)
    fig = px.line(
        df, x="год", y="shown", color="region", markers=True,
        labels={"shown": ctx.unit, "год": ""},
        title=f"{ctx.meta['title']} — изменение по годам",
    )
    return fig


@chart("waterfall", "Каскад — вклад в изменение")
def _waterfall(ctx: Ctx) -> go.Figure:
    df = data.get_change(ctx.indicator, ctx.regions)
    if df.empty:
        return _message("Нужны данные минимум за два года")

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
        title=f"{ctx.meta['title']} — вклад регионов в изменение, {ctx.unit}",
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
    if len(df) < 2:
        return _message("Нужно хотя бы два региона")
    fig = px.parallel_coordinates(
        df, dimensions=dimensions, color=dimensions[-1],
        labels={k: data.get_indicator_meta(k)["short"] for k in dimensions},
        title=f"Профиль регионов по всем показателям — {ctx.year} год",
    )
    return fig


@chart("box", "Ящик — разброс между регионами")
def _box(ctx: Ctx) -> go.Figure:
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions))
    fig = px.box(
        df, y="shown", points="all", hover_name="region",
        labels={"shown": ctx.unit}, title=f"{ctx.title} — разброс",
    )
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
    fig = px.choropleth(
        df,
        geojson=geojson,
        locations="region",
        featureidkey=geo.get("feature_key", "properties.name"),
        color="shown",
        color_continuous_scale="Blues",
        labels={"shown": ctx.unit},
        title=ctx.title,
    )
    fig.update_geos(fitbounds="locations", visible=False)
    return fig
