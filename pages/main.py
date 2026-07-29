"""Главный экран: витрина инструментов из макета + настоящие данные под ней.

Страница собрана из двух этажей, и это осознанно.

**Верхний этаж — витрина по макету** (Claude Design, страница «3a»):
четыре карточки инструментов со шкалой освоения, отметкой ожидаемого темпа
и мини-динамикой, под ними разбивка по программам, под ней карта.
Числа в карточках и разбивке — **макетные**, они лежат в `core/mockup.py`:
в боевой базе нет ни разреза по инструментам, ни программ, ни счётчика
уникальных проектов. На экране про это написано прямо, а не мелким шрифтом
в документации. Карта при этом **настоящая** — она рисуется по данным.

**Нижний этаж — то, что уже есть на самом деле:** карточки-показатели
и сетка виджетов, состав которой задаёт админ на странице «Виджеты»
(core/widgets.py). Этот этаж живой: он слушает фильтры года и регионов.

@@ **Вернуться к вопросу:** пользователь выбрал «карточки сверху, виджеты
ниже» (29.07.2026), но отметил, что в макете главная сделана целиком и,
возможно, сетку виджетов с главной стоит убрать совсем. Решение отложено.

Как рисуется сетка виджетов. Виджет знает свой пресет размера, пресет знает
ширину в колонках Bootstrap (4, 6 или 12) и высоту в пикселях. Строк как
таковых нет: колонки переносятся сами, когда 12 набралось, — поэтому
«два средних в ряд» получается само собой.

Один коллбэк рисует все виджеты разом (pattern-matching по id). Отдельный
коллбэк на каждый пришлось бы объявлять заранее и на фиксированное число,
а число виджетов заранее неизвестно — их набор меняет админ.
"""

import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, dcc, html

from core import auth, charts, data, mockup, widgets

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")

#: Показатель, по которому раскрашивается карта на главной.
#: Настоящий, из боевых данных — в отличие от карточек над ней.
MAP_INDICATOR = "budget_spent"

#: Высоты мини-столбиков «Динамика в отчетном году», в пикселях.
#: Столбики НЕ от нуля: разброс между февралём и июлем маленький, и от нуля
#: все шесть выглядели бы одинаковыми. Поэтому самый низкий — 30, самый
#: высокий — 50, остальные между ними. Так же сделано в макете.
MINI_MIN_H, MINI_MAX_H = 30, 50


def num(value: float, decimals: int = 0) -> str:
    """Число по-русски: разряды неразрывным пробелом, запятая для дробей."""
    text = f"{value:,.{decimals}f}".replace(",", " ")
    return text.replace(".", ",") if decimals else text


# ─────────────────────── витрина инструментов (макет) ───────────────────────

def mini_dynamics(item: dict) -> html.Div:
    """Шесть мини-столбиков: как копился факт с февраля по июль."""
    values = item["dynamics"]
    low, high = min(values), max(values)
    spread = high - low

    columns = []
    for label, value in zip(mockup.MONTHS, values):
        share = 0.5 if spread == 0 else (value - low) / spread
        height = MINI_MIN_H + (MINI_MAX_H - MINI_MIN_H) * share
        columns.append(html.Div(
            [
                html.Span(num(value), className="damu-mini-val"),
                html.Div(className="damu-mini-bar",
                         style={"height": f"{height:.0f}px"}),
                html.Span(label, className="damu-mini-label"),
            ],
            className="damu-mini-col",
        ))
    return html.Div(columns, className="damu-mini")


def instrument_card(item: dict, lead: bool = False) -> html.Div:
    """Одна карточка инструмента — шкала, статус, проекты, динамика.

    Цвет карточке задаёт ОДИН класс `damu-c-N` на самой карточке: он кладёт
    цвет в переменную CSS, а заголовок, полоски и столбики внутри берут её
    оттуда. Иначе цвет пришлось бы вписывать в десяток мест каждой карточки.
    """
    n = mockup.card_numbers(item)
    status_ok = n["on_track"]

    return html.Div(
        [
            html.Div(item["title"], className="damu-inst-head"),
            dcc.Graph(
                figure=charts.pace_gauge(n["percent"], n["pace"], item["tone"]),
                # Шкала — картинка, а не инструмент: панель plotly и подсказки
                # при наведении здесь только мешают
                config={"displayModeBar": False, "staticPlot": True},
                style={"height": "130px"},
            ),
            html.Div(f"план {num(item['plan'])} млрд ₸",
                     className="damu-mini-label text-end"),
            html.Div(
                [
                    html.Div(f"Факт {num(item['fact'])} млрд ₸", className="damu-muted"),
                    html.Div(
                        "В графике" if status_ok else "Отставание",
                        className="damu-inst-status " + ("ok" if status_ok else "late"),
                    ),
                ],
                className="damu-inst-row mt-2",
            ),
            html.Div(
                [
                    html.Div(f"Ожидаемо {num(n['pace'], 1)} %", className="damu-muted"),
                    html.Div(
                        f"опережение +{num(n['gap'], 1)} п.п." if status_ok
                        else f"−{num(abs(n['gap']), 1)} п.п. от ожидаемого темпа",
                        className="damu-muted",
                    ),
                ],
                className="damu-inst-row",
            ),
            html.Div(
                [
                    html.Div([
                        html.Span("Проекты — план / факт", className="damu-muted"),
                        html.Span(
                            f"{num(item['projects_plan'])} / {num(item['projects_fact'])}",
                            className="fw-bold",
                        ),
                    ], className="damu-inst-row"),
                    html.Div([
                        html.Span("Из них уникальных", className="damu-muted"),
                        html.Span(num(item["unique"]), className="fw-bold"),
                    ], className="damu-inst-row"),
                    html.Div([
                        html.Div([
                            html.Span("Выполнение проектов", className="damu-muted"),
                            html.Span(f"{num(n['projects_percent'], 1)} %",
                                      className="fw-bold"),
                        ], className="damu-inst-row"),
                        html.Div(
                            html.Div(
                                className="damu-bar-fill",
                                style={"width": f"{n['projects_percent']:.1f}%"},
                            ),
                            className="damu-bar mt-1",
                        ),
                    ]),
                ],
                className="damu-inst-block",
            ),
            html.Div(
                [
                    html.Div("Динамика в отчётном году", className="damu-mini-title"),
                    mini_dynamics(item),
                ],
                className="damu-inst-block",
            ),
        ],
        className=(f"damu-inst-card damu-c-{item['tone']}"
                   + (" damu-inst-lead" if lead else "")),
    )


def instruments_block() -> html.Div:
    """Заголовок с ожидаемым темпом и ряд из четырёх карточек."""
    pace, day, total = mockup.expected_pace()
    return html.Div([
        html.Div(
            [
                html.Div("Освоение плана — по инструментам",
                         className="damu-block-title"),
                html.Div(
                    [
                        html.Span(
                            f"Ожидаемый темп: прошло {day} из {total} дней года "
                            "· отметка на шкале",
                            className="damu-muted small",
                        ),
                        html.Span(f"{num(pace, 1)} %", className="fw-bold ms-2"),
                    ],
                ),
            ],
            className="damu-block-head",
        ),
        html.Div(
            [instrument_card(item, lead=(i == 0))
             for i, item in enumerate(mockup.INSTRUMENTS)],
            className="damu-inst-grid",
        ),
    ])


def programs_block() -> dbc.Card:
    """Разбивка по программам: четыре колонки со строками-полосками.

    Ширина полоски — доля от самой большой программы В СВОЕЙ колонке,
    а не от общей суммы: колонки про разное (три инструмента против
    восьми программ кредитования), и общий масштаб превратил бы правые
    колонки в еле заметные чёрточки.
    """
    columns = []
    for column in mockup.PROGRAMS:
        top_amount = max(row[1] for row in column["rows"])
        top_count = max(row[2] for row in column["rows"])
        rows = []
        for name, amount, count in column["rows"]:
            rows.append(html.Div(
                [
                    html.Span(name, className="damu-prog-name"),
                    html.Div(html.Div(className="damu-bar-fill",
                                      style={"width": f"{amount / top_amount * 100:.0f}%"}),
                             className="damu-bar"),
                    html.Span(num(amount), className="damu-prog-value"),
                    html.Span(),  # зазор между парами «полоска + число»
                    html.Div(html.Div(className="damu-bar-fill",
                                      style={"width": f"{count / top_count * 100:.0f}%"}),
                             className="damu-bar"),
                    html.Span(num(count), className="damu-prog-value"),
                ],
                className="damu-prog-row",
            ))
        columns.append(html.Div(
            [html.Div(column["title"], className="damu-prog-head"), *rows],
            className=f"damu-prog-col damu-c-{column['tone']}",
        ))

    return dbc.Card(
        dbc.CardBody([
            html.Div(
                [
                    html.Div("Разбивка по программам — факт по инструментам",
                             className="damu-block-title"),
                    html.Div(
                        [
                            html.Span([html.I(style={"width": "20px"}),
                                       "Освоено, млрд ₸"]),
                            html.Span([html.I(style={"width": "14px"}),
                                       "Проектов, шт"]),
                        ],
                        className="damu-prog-legend",
                    ),
                ],
                className="damu-block-head",
            ),
            html.Div(columns, className="damu-prog-grid"),
        ]),
        class_name="shadow-sm mb-3",
    )


def map_block() -> dbc.Card:
    """Карта областей. В макете здесь было фото — у нас настоящая карта."""
    return dbc.Card(
        dbc.CardBody([
            html.Div("Освоение по регионам — карта Казахстана",
                     className="damu-block-title mb-2"),
            dcc.Graph(id="main-map", config={"displayModeBar": False},
                      style={"height": "440px"}),
        ]),
        class_name="shadow-sm mb-3",
    )


# ─────────────────────────── настоящие данные ───────────────────────────

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
            instruments_block(),
            # Пометка стоит между макетными блоками и настоящими — ровно
            # на границе, чтобы было видно, к чему она относится
            html.Div(
                "Числа в карточках инструментов и в разбивке по программам — "
                "макетные, из эскиза: разрезов по инструментам и программам "
                "в хранилище пока нет. Фильтры года и регионов на них не "
                "влияют. Всё ниже карты — настоящие данные.",
                className="damu-mock my-3",
            ),
            programs_block(),
            map_block(),
            html.H2("Показатели МСП по регионам", className="mt-4"),
            html.P("Сводка по всем разделам сразу. Разрез по разделам — "
                   "в списке «Разделы» наверху.",
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
    Output("main-map", "figure"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
)
def render_map(year, regions, _version):
    """Карта живёт своей жизнью: она единственная в верхнем этаже настоящая."""
    return charts.build("map", MAP_INDICATOR, year, regions, height=440)


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
