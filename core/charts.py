"""Все виды диаграмм в одном месте.

**Добавить вид диаграммы = написать одну функцию с декоратором `@chart`.**
Больше нигде править не нужно: и список в интерфейсе, и разбор выбора
строятся из реестра автоматически.

Каждая функция получает `Ctx` (что показывать) и возвращает готовую фигуру
plotly. Общее оформление — высота, поля, фон — навешивается в `build()`,
в самих функциях его повторять не надо.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from core import data, theme

# Реестр заполняется декоратором при импорте модуля
_REGISTRY: dict[str, dict] = {}

#: Запасные цвета для рядов после первого. Первым идёт цвет темы —
#: у большинства наших видов ряд всего один, и он окрашивается им.
_PALETTE_TAIL = px.colors.qualitative.Plotly[1:]


@dataclass
class Ctx:
    """Всё, что диаграмма может попросить: что показывать и в каком масштабе."""

    indicator: str
    year: int
    regions: list[str] | None
    log: bool = False
    #: Раздел (колонка `program`). None — считать по всем разделам сразу:
    #: так смотрят главная и «Разбор». Страница раздела передаёт свой.
    program: str | None = None

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


#: Цвета, одинаково читаемые и на светлом, и на тёмном фоне.
#:
#: !! Диаграммы собираются на СЕРВЕРЕ, а тему человек выбирает в браузере
#: (localStorage) — сервер о ней не знает. Значит фигура должна выглядеть
#: прилично при обеих. Отсюда полупрозрачный серый вместо чёрного текста
#: и вместо светлой сетки: контраст чуть ниже предельного, зато не бывает
#: чёрного по чёрному. Захотим полный контраст — придётся протащить тему
#: в каждый коллбэк, который строит диаграмму.
NEUTRAL_INK = "rgba(128,124,122,1)"
NEUTRAL_GRID = "rgba(128,124,122,0.25)"


def build(chart_type: str, indicator: str, year, regions, log: bool = False,
          height: int | None = None, program: str | None = None) -> go.Figure:
    """Собирает выбранную диаграмму и навешивает общее оформление.

    height — высота в пикселях. Задан (виджет на главной со своим пресетом
    размера) — диаграмма подгоняется под него, даже если вид просил себе
    другую высоту. Не задан (страница «Разбор», один график во весь экран) —
    вид оставляет свою, а если не просил — 700, как было.
    """
    entry = _REGISTRY.get(chart_type) or _REGISTRY["bar"]
    ctx = Ctx(
        indicator=indicator,
        year=int(year),
        regions=regions or None,
        log=bool(log) and entry["log_ok"],
        program=program,
    )
    # Оформление сайта распространяется и на диаграммы: иначе страница была
    # бы одним шрифтом, а подписи внутри графиков — другим. Тему спрашиваем
    # здесь, в единственном общем месте, а не в каждой из 17 функций.
    settings = theme.get_theme()
    palette = [settings["accent"], *_PALETTE_TAIL]

    # !! Цвет приходится задавать ДО постройки, и вот почему: plotly express
    # вписывает цвет прямо в ряд данных, а не берёт его из разметки в момент
    # показа. Поэтому layout.colorway на столбцы уже не влияет (проверено
    # в браузере: столбцы оставались синими #636efa). px.defaults —
    # единственный способ поменять палитру всем 17 видам разом, не трогая
    # каждую функцию.
    px.defaults.color_discrete_sequence = palette

    fig = entry["builder"](ctx)
    fig.update_layout(
        font=dict(family=theme.font_stack(settings), color=NEUTRAL_INK),
        # Для видов, собранных не через express, а руками на go.Figure:
        # у них цвет ряда не задан, и они берут его отсюда
        colorway=palette,
        margin=dict(l=10, r=120, t=60, b=40),
        # !! Фон прозрачный, а не белый, и это про тёмную тему. Тему человек
        # выбирает в браузере (localStorage), сервер о ней не знает и одну
        # и ту же фигуру отдаёт обоим. Белая подложка на тёмной странице
        # была бы светлой заплатой; прозрачная принимает цвет карточки.
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        # Русская типографика чисел: запятая для дробей, неразрывный пробел
        # для разрядов. Иначе plotly пишет по-английски: 454,416.0
        separators=", ",
    )
    # Сетка и оси — полупрозрачным серым по той же причине: он читается
    # и на светлом, и на тёмном, а фиксированный цвет пришлось бы менять
    # вместе с темой, то есть протаскивать её в каждый коллбэк
    fig.update_xaxes(gridcolor=NEUTRAL_GRID, zerolinecolor=NEUTRAL_GRID)
    fig.update_yaxes(gridcolor=NEUTRAL_GRID, zerolinecolor=NEUTRAL_GRID)

    if height:
        # Пресет виджета сильнее собственной высоты вида: на экране из
        # нескольких виджетов сетку задаёт раскладка, а не диаграмма
        fig.update_layout(height=int(height))
    elif fig.layout.height is None:  # вид мог задать свою высоту
        fig.update_layout(height=700)
    return fig


#: Ниже этого размера подписи внутри секторов читать невозможно.
#:
#: !! Было 12 (то есть шрифт 13). При таком размере plotly **прятал две
#: подписи** — «Западно-Казахстанская» и «Восточно-Казахстанская»: они
#: длиннее остальных и не влезали в свой сектор, а режим `hide` убирает
#: то, что не влезло, целиком. Сектор оставался, подпись исчезала.
#: Замерено в браузере (27.07.2026) на высотах 700, 420 и 320 px:
#: при 13 px прячутся ровно эти две на любой высоте, при 11 px — ни одной.
#: Поэтому 10 (шрифт 11): два пикселя размера в обмен на две подписи.
MIN_LABEL_SIZE = 10


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
    df = data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program).copy()
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
    df = data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program)
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


def _hierarchy_style(fig: go.Figure, size: int = MIN_LABEL_SIZE + 1) -> go.Figure:
    """Общее для круговой, плиток, лучей и сосулек: размер шрифта подписей.

    `size` — на случай, когда виду тесно даже при общем размере. Такой вид
    один, «сосульки»: там ширина ячейки пропорциональна значению, и у самых
    маленьких областей места под подпись меньше, чем у остальных.

    Режим `hide` значит: то, что не влезло, plotly **убирает целиком** —
    сектор остаётся, подпись исчезает. Это осознанный выбор: альтернатива —
    подписи, налезающие друг на друга и на соседние сектора. Но раз уж
    исчезновение молчаливое, размер подобран замером, а не на глаз.
    """
    fig.update_traces(insidetextfont=dict(size=size))
    fig.update_layout(uniformtext=dict(minsize=size - 1, mode="hide"))
    return fig


def message(text: str) -> go.Figure:
    """Та же пустая фигура с текстом, но для страниц.

    Нужна главной: если набор виджетов изменили в другой вкладке, на месте
    исчезнувшего виджета честнее показать надпись, чем пустой прямоугольник.
    """
    return _message(text)


def tone_color(tone: int = 1) -> str:
    """Цвет по номеру оттенка: 1 — основной, 2 — второй, 3 — второй тёмный.

    Витрина инструментов на главной красится не одним цветом, а тремя,
    как в макете. Номер оттенка живёт в макете (core/mockup.py), а какой
    это цвет сегодня — знает тема. Так перекраска сайта из настроек
    доезжает и до карточек инструментов.
    """
    settings = theme.get_theme()
    if tone == 2:
        return settings["accent_2"]
    if tone == 3:
        return theme.mix(settings["accent_2"], "#000000", 0.4)
    return settings["accent"]


def pace_gauge(percent: float, expected: float, tone: int = 1,
               height: int = 130) -> go.Figure:
    """Полукруглая шкала «сколько освоено» с отметкой ожидаемого темпа.

    Главная мысль макета: сама по себе цифра «48 %» ни о чём не говорит —
    важно, сколько должно быть освоено к сегодняшнему дню. Поэтому поперёк
    шкалы стоит засечка ожидаемого темпа: заливка не дотянула до неё —
    отставание, перешла — идём с опережением.

    !! Кольцо (а не залитый полукруг) получается связкой двух вещей:
    у полосы задана `thickness`, и ровно такая же `thickness` задана
    подложке-ступени. Без ступени `bgcolor` заливает весь полукруг целиком,
    и вместо тонкой дуги выходит сплошной сектор (проверено в браузере).
    """
    color = tone_color(tone)
    thickness = 0.32
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=percent,
        number={"suffix": " %", "valueformat": ".1f",
                "font": {"size": 30, "color": color}},
        gauge={
            "axis": {"range": [0, 100], "visible": False},
            "bar": {"color": color, "thickness": thickness},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            # Подложка кольца — та самая ступень во всю шкалу
            "steps": [{"range": [0, 100], "color": "#eae7e7",
                       "thickness": thickness}],
            "threshold": {
                "value": expected,
                "thickness": 1,
                "line": {"color": "#201e1d", "width": 3},
            },
        },
    ))
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=6, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family=theme.font_stack()),
        separators=", ",
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
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program))
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
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program))
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
        data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program)
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
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program))
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
            # Все подписи вдоль луча — ради единообразия. По умолчанию
            # (`auto`) plotly выбирает ориентацию каждому сектору отдельно:
            # широким оставляет горизонтальную, узким разворачивает, и вид
            # получается разнобойным. Замер (27.07.2026, шрифт 11 px):
            # auto — 0 скрытых, повёрнуто 6 из 26; radial — 0 скрытых,
            # повёрнуты все; horizontal — 3 подписи прячутся, так нельзя.
            insidetextorientation="radial",
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
    # Шрифт мельче, чем у остальных иерархических видов: ширина ячейки здесь
    # пропорциональна значению, и при 11 px у трёх самых маленьких областей
    # (Актюбинская, г. Алматы, Карагандинская) подпись пропадала. При 9 px
    # видны все 27 — замерено в браузере 27.07.2026.
    return _hierarchy_style(fig, size=9)


# ─────────────────────────── Изменение во времени ───────────────────────────


@chart("months", "Динамика по месяцам — внутри года")
def _months(ctx: Ctx) -> go.Figure:
    """Единственный вид, показывающий месяцы, а не свёрнутый год.

    Все остальные виды сворачивают двенадцать строк региона в одну годовую.
    Здесь наоборот: регионы сворачиваются в страну, а месяцы остаются —
    видно, как показатель шёл внутри отчётного года.
    """
    df = ctx.scaled(data.get_monthly(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program))
    if df.empty:
        return _message(NO_DATA)
    fig = px.bar(
        df, x="month_name", y="shown", text="текст",
        labels={"shown": ctx.unit, "month_name": ""},
        title=f"{ctx.meta['title']} — по месяцам {ctx.year} года",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    return fig


@chart("years", "Сравнение лет")
def _years(ctx: Ctx) -> go.Figure:
    """Все годы сразу — фильтр года на этот вид не влияет."""
    df = ctx.scaled(data.get_region_dynamics(ctx.indicator, ctx.regions, ctx.program))
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
    df = data.get_region_dynamics(ctx.indicator, ctx.regions, ctx.program)
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
    df = data.get_change(ctx.indicator, ctx.year, ctx.regions, ctx.program)
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
    df = data.get_table(ctx.year, ctx.regions, ctx.program)
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
    df = data.get_table(ctx.year, ctx.regions, ctx.program)
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
        data.get_regions_grouped(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program)
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
    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program))
    fig = px.histogram(
        df, x="shown", nbins=10,
        labels={"shown": ctx.unit}, title=f"{ctx.title} — распределение регионов",
    )
    fig.update_layout(yaxis_title="регионов")
    return fig


# ──────────────────── Общие цифры по стране ────────────────────
#
# Эти виды — не разрез по областям, а «сколько всего». Именно они нужны
# виджетам вроде «сколько МСП» или «как идёт освоение плана»: на главном
# экране рядом с подробными разрезами должно быть и общее число, иначе
# читателю приходится складывать двадцать столбцов глазами.
#
# Фильтр регионов они уважают: выбрали три области — цифра будет по трём.


def _accent() -> str:
    """Цвет темы. build() кладёт палитру сюда перед постройкой диаграммы."""
    palette = px.defaults.color_discrete_sequence
    return palette[0] if palette else "#0d6efd"


@chart("total", "Число — итог по стране")
def _total(ctx: Ctx) -> go.Figure:
    """Одна крупная цифра и изменение к прошлому году.

    Показывается в масштабе показа из config.yaml (млрд ₸, трлн ₸), иначе
    на экране был бы ряд из двенадцати цифр, который никто не прочтёт.
    """
    meta = ctx.meta
    if meta.get("derived"):
        # Показатель-доля в фактах не лежит, он считается из двух других.
        # Без этой ветки виджет «Число» с «Согласно плану» показывал бы
        # «нет данных», хотя цифра прекрасно считается — просто иначе.
        value, _ = data.get_derived_percent(ctx.indicator, ctx.year, ctx.regions, ctx.program)
        previous, _ = data.get_derived_percent(ctx.indicator, ctx.year - 1, ctx.regions, ctx.program)
    else:
        value = data.get_country_total(ctx.indicator, ctx.year, ctx.regions, ctx.program)
        previous = data.get_country_total(ctx.indicator, ctx.year - 1, ctx.regions, ctx.program)
    if value is None:
        return _message(NO_DATA)
    unit = meta["display_unit"] or meta["unit"]

    number = {
        "valueformat": f",.{meta['decimals']}f",
        "suffix": f" {unit}" if unit else "",
        "font": {"size": 44, "color": _accent()},
    }
    indicator_kwargs = dict(value=value / meta["divisor"], number=number)
    if previous:
        indicator_kwargs["mode"] = "number+delta"
        indicator_kwargs["delta"] = {
            "reference": previous / meta["divisor"],
            "relative": True,
            "valueformat": ".1%",
        }
    else:
        indicator_kwargs["mode"] = "number"

    fig = go.Figure(go.Indicator(**indicator_kwargs))
    fig.update_layout(title=ctx.title)
    return fig


@chart("gauge", "Шкала — процент выполнения")
def _gauge(ctx: Ctx) -> go.Figure:
    """Полукруглая шкала для производного показателя — «Согласно плану %».

    Работает только с показателями, у которых в config.yaml есть блок
    `derived`: шкала показывает долю одного показателя от другого. Для
    обычного показателя доли не существует — тогда честнее сказать это
    словами, чем нарисовать шкалу непонятно чего.
    """
    spec = ctx.meta.get("derived")
    if not spec:
        return _message(
            "Этот вид — для показателей-долей.<br>"
            "Выберите «Освоение бюджета — факт от плана»<br>"
            "или другой показатель с блоком derived в config.yaml."
        )

    value, source = data.get_derived_percent(ctx.indicator, ctx.year, ctx.regions, ctx.program)
    if value is None:
        return _message(NO_DATA)

    # Шкала до 100 %, но если перевыполнили — до самого значения, иначе
    # стрелка упиралась бы в край и «120 %» выглядели бы как «100 %»
    top = max(100, value)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": " %", "valueformat": ".1f", "font": {"size": 36}},
        gauge={
            "axis": {"range": [0, top]},
            "bar": {"color": _accent()},
            # Бледная засечка на 100 %: видно, добрали до плана или нет
            "threshold": {"value": 100, "line": {"color": "#6c757d", "width": 2}},
        },
    ))
    fig.update_layout(title=f"{ctx.title}<br><sub>считается {source}</sub>")
    return fig


@chart("years_total", "Годы — итог по стране")
def _years_total(ctx: Ctx) -> go.Figure:
    """Как показатель менялся по годам, без разбивки по областям."""
    df = data.get_country_years(ctx.indicator, regions=ctx.regions, program=ctx.program)
    if df.empty:
        return _message(NO_DATA)

    df = ctx.scaled(df)
    fig = px.bar(
        df, x="report_year", y="shown", text="текст",
        labels={"shown": ctx.unit, "report_year": ""},
        title=f"{ctx.meta['title']} — по годам",
    )
    fig.update_traces(textposition="outside")
    # Год — подпись, а не число на шкале: 2 022,5 года не бывает
    fig.update_xaxes(type="category")
    return fig


# ─────────────────────────── Карта ───────────────────────────


def _map_scale() -> list[list]:
    """Шкала цвета карты — из цвета темы, а не готовый набор «Blues».

    Раньше здесь стояло имя plotly-шкалы, и карта оставалась синей при
    любой перекраске сайта — единственное место, куда цвет темы не доезжал.
    Два узла достаточно: plotly сам разложит между ними промежуточные
    оттенки. Светлый край не белый, а чуть тонированный — на белом фоне
    карточки иначе не видно, что область вообще закрашена.
    """
    accent = theme.get_theme()["accent"]
    return [
        [0.0, theme.mix(accent, "#ffffff", 0.88)],
        [1.0, theme.mix(accent, "#000000", 0.15)],
    ]


@chart("map", "Карта Казахстана")
def _map(ctx: Ctx) -> go.Figure:
    """Картограмма областей.

    Рисуется обычными закрашенными контурами на простых осях, а не через
    `px.choropleth`. Проекционная машинерия plotly с этим файлом не справилась:
    ни `fitbounds="locations"`, ни ручной `projection.scale` не масштабировали
    страну — она оставалась пятном в несколько пикселей. Проверено
    растеризацией: в поле карты закрашивалось 4 тысячи пикселей вместо сотен
    тысяч.

    Здесь координаты кладутся на оси как есть, а искажение долготы
    компенсируется соотношением сторон. Для одной страны этого достаточно,
    и результат предсказуем.
    """
    geo = data.load_config().get("geo", {})
    path = Path(geo.get("geojson_path", "assets/geo/kz_regions.geojson"))

    if not path.exists():
        return _message(
            "Карта пока не подключена.<br><br>"
            f"Нужен файл границ областей Казахстана: <b>{path}</b><br>"
            "Формат — GeoJSON, в свойствах каждой области должно быть её название.<br>"
            "Имя поля с названием задаётся в config.yaml → geo.feature_key"
        )

    with path.open(encoding="utf-8") as f:
        geojson = json.load(f)

    df = ctx.scaled(data.get_regions(ctx.indicator, ctx.year, regions=ctx.regions, program=ctx.program))
    if df.empty:
        return _message(NO_DATA)

    # Названия областей в файле границ и в данных совпадают не все:
    # у нас «Абай» и «г. Шымкент», в файле «Абайская» и «Чимкент».
    renames = geo.get("region_map") or {}
    df["geo_name"] = df["region"].map(lambda r: renames.get(r, r))

    prop = geo.get("feature_key", "properties.ADM1_RU").split(".")[-1]
    shapes = {
        feature["properties"].get(prop): feature["geometry"]
        for feature in geojson.get("features", [])
    }
    missing = sorted(set(df["geo_name"]) - set(shapes))
    if missing:
        # Молча пропавший регион хуже явной ошибки: он просто не закрасился бы
        return _message(
            "Эти области не найдены в файле границ:<br><b>"
            + ", ".join(missing)
            + "</b><br>Допишите соответствие в config.yaml → geo.region_map"
        )

    low, high = float(df["shown"].min()), float(df["shown"].max())
    spread = high - low
    scale = _map_scale()
    shades = sample_colorscale(
        scale,
        [0.5 if spread == 0 else 0.15 + 0.85 * (v - low) / spread for v in df["shown"]],
    )

    fig = go.Figure()
    all_lat: list[float] = []
    for (_, row), shade in zip(df.iterrows(), shades):
        xs, ys = _rings(shapes[row["geo_name"]])
        all_lat += [y for y in ys if y is not None]
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys, fill="toself", fillcolor=shade,
                line=dict(color="white", width=0.6),
                mode="lines", hoveron="fills", hoverinfo="text",
                text=f"<b>{row['region']}</b><br>{row['текст']}",
                showlegend=False,
            )
        )

    # Невидимая точка — только ради шкалы цвета сбоку
    fig.add_trace(
        go.Scatter(
            x=[None], y=[None], mode="markers", hoverinfo="skip", showlegend=False,
            marker=dict(
                colorscale=scale, cmin=low, cmax=high, color=[low], opacity=0,
                colorbar=dict(title=ctx.unit),
            ),
        )
    )

    # Один градус долготы короче градуса широты — тем сильнее, чем севернее.
    # Без поправки страна выглядит растянутой вширь.
    mid_lat = sum(all_lat) / len(all_lat) if all_lat else 48.0
    fig.update_xaxes(visible=False)
    fig.update_yaxes(
        visible=False, scaleanchor="x",
        scaleratio=1 / max(math.cos(math.radians(mid_lat)), 0.1),
    )
    fig.update_layout(title=ctx.title, hovermode="closest")
    return fig


def _rings(geometry: dict) -> tuple[list, list]:
    """Контуры области одним списком точек, части разделены разрывом.

    `None` между кольцами говорит plotly оборвать линию — иначе конец одного
    острова соединился бы прямой с началом следующего.
    """
    polygons = (
        geometry["coordinates"]
        if geometry["type"] == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    xs: list = []
    ys: list = []
    for polygon in polygons:
        for ring in polygon:
            if xs:
                xs.append(None)
                ys.append(None)
            xs += [point[0] for point in ring]
            ys += [point[1] for point in ring]
    return xs, ys


def _geo_bounds(geojson: dict, prop: str, names: set[str]) -> tuple | None:
    """Охватывающий прямоугольник показываемых областей: (lon_min, lat_min, lon_max, lat_max).

    Обходит координаты вручную, потому что форма бывает и Polygon,
    и MultiPolygon — вложенность разная, а нужен один плоский список точек.
    """
    lons: list[float] = []
    lats: list[float] = []

    def walk(node) -> None:
        # Точка — это пара чисел; всё остальное — список списков
        if isinstance(node, (list, tuple)) and len(node) == 2 and isinstance(node[0], (int, float)):
            lons.append(float(node[0]))
            lats.append(float(node[1]))
            return
        for item in node:
            walk(item)

    for feature in geojson.get("features", []):
        if feature["properties"].get(prop) in names:
            walk(feature["geometry"]["coordinates"])

    if not lons:
        return None
    return min(lons), min(lats), max(lons), max(lats)
