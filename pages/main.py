"""Главный экран: карточки-показатели и несколько виджетов сразу.

Что изменилось по сравнению с прежним экраном. Раньше здесь был **один**
график, который зритель выбирал из списка. Теперь на экране **несколько**
диаграмм, а их состав — какой показатель, каким видом, какого размера —
задаёт админ на странице «Виджеты» (core/widgets.py). Прежний экран
никуда не делся: он переехал на страницу «Разбор» (pages/explore.py),
где по-прежнему можно перебирать виды и показатели самому.

Фильтры года и регионов остались общими: они действуют сразу на все
виджеты и на карточки. Так и задумано — на дашборде смотрят один срез
данных под разными углами, а не каждый виджет в своём году.

Как рисуется сетка. Виджет знает свой пресет размера, пресет знает
ширину в колонках Bootstrap (4, 6 или 12) и высоту в пикселях. Строк
как таковых нет: колонки переносятся сами, когда 12 набралось, —
поэтому «два средних в ряд» получается само собой.

Один коллбэк рисует все виджеты разом (pattern-matching по id). Отдельный
коллбэк на каждый пришлось бы объявлять заранее и на фиксированное число,
а число виджетов заранее неизвестно — их набор меняет админ.
"""

import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, dcc, html

from core import auth, charts, data, widgets

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")


def kpi_card(row: pd.Series) -> dbc.Card:
    """Карточка одного показателя: значение и изменение к прошлому году."""
    change = row["change_pct"]
    if change is None or pd.isna(change):
        footer = html.Span("нет данных за прошлый год", className="small text-muted")
    else:
        grew = change >= 0
        # У обычных карточек изменение в процентах, у карточки-доли
        # («Согласно плану») — в процентных пунктах
        unit = "п.п." if row.get("change_kind") == "pp" else "%"
        footer = html.Span(
            f"{'▲' if grew else '▼'} {abs(change):.1f} {unit} к прошлому году",
            className=f"small {'text-success' if grew else 'text-danger'}",
        )

    return dbc.Card(
        dbc.CardBody(
            [
                html.Div(row["short"], className="text-muted small"),
                html.H3(row["text"], className="my-2"),
                footer,
            ]
        ),
        className="h-100 shadow-sm",
    )


def widget_grid(items: list[dict]):
    """Сетка виджетов: каждый — своей ширины, с высотой из пресета.

    Сами фигуры сюда не кладутся: их подставит коллбэк. Здесь только места
    под них — иначе при открытии страницы пришлось бы строить все диаграммы
    дважды, сначала в разметке, потом в коллбэке.
    """
    if not items:
        return dbc.Alert(
            "Виджетов нет. Добавьте их на странице «Виджеты».",
            color="light", className="border",
        )

    columns = []
    for item in items:
        preset = widgets.size_meta(item["size"])
        columns.append(
            dbc.Col(
                dbc.Card(
                    dcc.Graph(
                        id={"type": "widget-graph", "index": item["id"]},
                        style={"height": f"{preset['height']}px"},
                        # Панель инструментов plotly (лупа, лассо, «камера»)
                        # на витрине убрана: она всплывает при наведении,
                        # мешает читать и ведёт на plotly.com — чужой сайт,
                        # который во внутренней сети всё равно не откроется.
                        # Кому нужно покопаться в графике — страница «Разбор»,
                        # там панель оставлена.
                        config={"displayModeBar": False},
                    ),
                    className="shadow-sm p-2 h-100",
                ),
                xs=12,               # на узком экране виджеты встают в столбик
                lg=preset["columns"],  # на широком — по пресету
                className="mb-3",
            )
        )
    return dbc.Row(columns, className="g-3")


def layout(**kwargs):
    """Собирается на каждое открытие страницы — значит и фильтры, и набор свежие."""
    try:
        data.get_years()          # хранилище на месте? иначе покажем подсказку
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    items = widgets.get_widgets(widgets.MAIN_PAGE)

    hint = None
    if auth.is_admin():
        hint = html.P(
            [
                "Набор виджетов " +
                ("настроен вручную. " if widgets.is_customized(widgets.MAIN_PAGE)
                 else "взят из config.yaml (по умолчанию). "),
                dcc.Link("Изменить — на странице «Виджеты»", href="/widgets"),
            ],
            className="text-muted small",
        )

    return dbc.Container(
        [
            html.H2("Показатели МСП по регионам", className="mt-2"),
            html.P("Сводка по всем разделам сразу. Разрез по разделам — в меню слева.",
                   className="text-muted small"),
            dbc.Row(id="kpi-row", className="mb-4 g-3"),
            widget_grid(items),
            hint,
        ],
        fluid=True,
        className="pb-5",
    )


@callback(
    Output("kpi-row", "children"),
    Input("filter-year", "value"),
    Input("data-version", "data"),
)
def render_kpi(year, _version):
    kpi = data.get_kpi(int(year))
    # md=True — поделить ряд поровну между карточками, сколько бы их ни было;
    # xs=12 — на узких экранах карточки встают в столбик
    return [dbc.Col(kpi_card(row), xs=12, md=True) for _, row in kpi.iterrows()]


@callback(
    Output({"type": "widget-graph", "index": ALL}, "figure"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
    State({"type": "widget-graph", "index": ALL}, "id"),
)
def render_widgets(year, regions, _version, ids):
    """Рисует все виджеты разом — по одному вызову на смену фильтра.

    Набор перечитывается здесь, а не берётся из разметки: между открытием
    страницы и этим вызовом админ мог его поменять. Если виджет за это
    время исчез, на его месте появляется надпись, а не пустота и не ошибка —
    остальные виджеты при этом рисуются как ни в чём не бывало.
    """
    by_id = {item["id"]: item for item in widgets.get_widgets(widgets.MAIN_PAGE)}
    figures = []
    for graph_id in ids:
        item = by_id.get(graph_id["index"])
        if item is None:
            figures.append(charts.message(
                "Этот виджет удалили.<br>Обновите страницу (F5)."
            ))
            continue
        preset = widgets.size_meta(item["size"])
        figures.append(
            charts.build(
                item["chart"], item["indicator"], year, regions,
                log=False, height=preset["height"],
            )
        )
    return figures
