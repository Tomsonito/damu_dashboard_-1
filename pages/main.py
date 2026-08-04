"""Главный экран — витрина освоения плана по макету.

Собран по листу «Даму — Главная» из Claude Design (вариант 1b, светлая тема).
Сверху вниз: строка заголовка с переключателем года, полоса-итог
«Все инструменты», три карточки инструментов, разбивка по программам,
карта областей.

**Главная мысль раскладки — иерархия.** Раньше все четыре инструмента
стояли в одном ряду, и сводный терялся среди трёх частных. Теперь сводный
вынесен в тёмную полосу во всю ширину и подан крупно: сначала «сколько
всего», потом разбивка. Цвет при этом перестал красить заголовки и стал
чертой сверху карточки — он метка категории, а не выделение важности.

**Числа макетные** (`core/mockup.py`): разрезов по инструментам, программам
и уникальным проектам в боевой базе нет. На экране про это написано прямо —
плашка «Макетные числа» стоит рядом с заголовком, а не мелочью внизу.
Карта — настоящая, она рисуется по данным и слушает фильтры.

**Что на витрине живое.** Два переключателя, и оба меняют только макетные
числа: год (текущий / прошлый) и тумблер «Графики за весь год». Год влияет
на все числа сразу, тумблер разворачивает графики месяцев с шести последних
до всех прошедших. Будущие месяцы не показываются ни в одном состоянии —
столбик за декабрь в августе означал бы ноль и читался бы как провал.

Фильтры года и регионов из шапки на макетные числа НЕ влияют: подделывать
реакцию выдуманных чисел на настоящий фильтр — обман. Карта под ними живая
и слушает и то и другое.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html

from core import charts, data, mockup

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")

#: Показатель, по которому раскрашивается карта. Настоящий, из боевых данных.
MAP_INDICATOR = "budget_spent"

#: Годы витрины: текущий и прошлый. Настоящие годы придут из хранилища
#: вместе с разрезами — тогда список станет динамическим.
YEAR_NOW = 2026
YEAR_PREV = 2025

#: Высота области столбиков в полосе-итоге и в карточке, в пикселях.
BAND_CHART_H, CARD_CHART_H = 44, 52


def num(value: float, decimals: int = 0) -> str:
    """Число по-русски: разряды неразрывным пробелом, запятая для дробей."""
    text = f"{value:,.{decimals}f}".replace(",", " ")
    return text.replace(".", ",") if decimals else text


def _months(item: dict, height: int, css: str, tight: bool, show_values: bool):
    """Столбики «проектов за месяц»: значение сверху, месяц снизу.

    В развёрнутом виде числа над столбиками прячутся, а зазор сжимается:
    двенадцать подписей с числами в узкой колонке не читаются — проверено
    в макете, оттуда же и решение.
    """
    values = item["months"]
    top = max(values) or 1
    columns = []
    for label, value in zip(item["month_labels"], values):
        column = []
        if show_values:
            column.append(html.Span(num(value), className=f"{css}-value"))
        column.append(html.I(style={
            "height": f"{max(3, round(value / top * height))}px",
            # Самый высокий столбик в полную силу, остальные приглушены —
            # пик месяца видно, не читая чисел
            "opacity": 1 if value == top else 0.5,
        }))
        if css == "damu-inst2-month":
            column.append(html.Span(label, className=f"{css}-label"))
        columns.append(html.Div(column, className=css))

    block = [html.Div(columns, className=(f"{css}s damu-tight" if tight
                                          else f"{css}s"))]
    if css == "damu-band-month":
        block.append(html.Div([html.Span(m) for m in item["month_labels"]],
                              className="damu-band-labels"))
    return block


def band(item: dict, expanded: bool) -> html.Div:
    """Полоса-итог «Все инструменты» — пять колонок во всю ширину."""
    return html.Div(
        [
            html.Div([
                html.Div("Все инструменты", className="damu-band-title"),
                html.Div([
                    html.Span(num(item["percent"], 1), className="damu-band-percent"),
                    html.Span("%", style={"fontSize": "1.375rem", "fontWeight": 600,
                                          "color": "rgba(255,255,255,.6)"}),
                ], className="d-flex align-items-baseline gap-2 mt-1"),
                html.Div("от годового плана", className="damu-band-note mt-1"),
            ]),

            html.Div([
                html.Div(["Факт ",
                          html.B(num(item["fact"]), style={"color": "#fff",
                                                           "fontSize": "1.06rem"}),
                          f" из {num(item['plan'])} млрд ₸"],
                         style={"fontSize": "0.8rem",
                                "color": "rgba(255,255,255,.66)",
                                "marginBottom": "0.625rem"}),
                html.Div([
                    html.Div(className="damu-band-fill",
                             style={"width": f"{min(item['percent'], 100):.1f}%"}),
                    # Засечка ожидаемого темпа. Подписи к ней нет намеренно:
                    # в макете её убрали как лишний текст
                    html.Div(className="damu-band-tick",
                             style={"left": f"{min(item['pace'], 100):.1f}%"}),
                ], className="damu-band-track"),
            ]),

            html.Div([
                html.Div("Проекты факт / план", className="damu-band-kicker"),
                html.Div(f"{num(item['projects_fact'])} / {num(item['projects_plan'])}",
                         className="damu-band-value"),
                html.Div(html.Div(style={
                    "width": f"{min(item['projects_percent'], 100):.1f}%"}),
                    className="damu-band-bar mt-2"),
            ]),

            html.Div([
                html.Div("Состав проектов", className="damu-band-kicker"),
                html.Div([
                    html.Span(num(item["unique"]), className="damu-band-value"),
                    html.Span("уникальных", className="damu-band-note"),
                ], className="d-flex align-items-baseline gap-2 text-nowrap"),
                html.Div([
                    html.Div(className="damu-band-split-unique", style={
                        "width": f"{item['unique'] / max(item['projects_fact'], 1) * 100:.1f}%"}),
                    html.Div(className="damu-band-split-repeat"),
                ], className="damu-band-split mt-2"),
                html.Div(f"{num(item['repeat'])} повторных",
                         className="damu-band-note mt-1 text-end text-nowrap"),
            ]),

            html.Div([
                html.Div([
                    html.Span("Проектов за месяц, шт"),
                    html.Span(f"за год {num(sum(item['months']))}",
                              style={"color": "rgba(255,255,255,.75)"}),
                ], className="damu-band-kicker d-flex justify-content-between mb-1"),
                *_months(item, BAND_CHART_H, "damu-band-month",
                         tight=expanded, show_values=not expanded),
            ]),
        ],
        className="damu-band",
    )


def instrument_card(item: dict, expanded: bool) -> html.Div:
    """Карточка одного инструмента: процент, полоса, проекты, месяцы."""
    tone = {"guarantee": 1, "credit": 2, "subsidy": 3}[item["key"]]
    ok = item["status"] != "Отставание"
    status_color = ("var(--damu-accent, #1f7a4d)" if ok
                    else "var(--damu-accent-2-dark, #6a531c)")

    return html.Div(
        [
            html.Div([
                html.Span(item["title"], className="damu-inst2-title"),
                html.Span([html.I(style={"background": status_color}),
                           item["status"]],
                          className="damu-inst2-status",
                          style={"color": status_color}),
            ], className="damu-inst2-head"),

            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.Span(num(item["percent"], 1),
                                      className="damu-inst2-percent"),
                            html.Span("%", style={"fontSize": "1.06rem",
                                                  "fontWeight": 600,
                                                  "color": "var(--damu-c)",
                                                  "opacity": .65}),
                        ], className="d-flex align-items-baseline gap-1"),
                        html.Div("от плана", className="small text-muted mt-1"),
                    ]),
                    html.Div([
                        html.Div(num(item["fact"]), className="damu-inst2-fact"),
                        html.Div(f"из {num(item['plan'])} млрд ₸",
                                 className="small text-muted"),
                    ], className="ms-auto text-end"),
                ], className="d-flex align-items-end gap-3"),

                html.Div([
                    html.Div(className="fill",
                             style={"width": f"{min(item['percent'], 100):.1f}%"}),
                    html.Div(className="tick",
                             style={"left": f"{min(item['pace'], 100):.1f}%"}),
                ], className="damu-inst2-track"),

                html.Div([
                    html.Div([
                        html.Div("Проекты факт / план", className="damu-band-kicker",
                                 style={"color": "var(--damu-muted)"}),
                        html.Div(f"{num(item['projects_fact'])} / "
                                 f"{num(item['projects_plan'])}",
                                 className="damu-inst2-num"),
                        html.Div(html.Div(className="damu-bar-fill", style={
                            "width": f"{min(item['projects_percent'], 100):.1f}%"}),
                            className="damu-bar mt-1"),
                    ]),
                    html.Div([
                        html.Div("Уникальных", className="damu-band-kicker",
                                 style={"color": "var(--damu-muted)"}),
                        html.Div(num(item["unique"]), className="damu-inst2-num"),
                        html.Div(f"выполнение {num(item['projects_percent'], 1)} %",
                                 className="small text-muted mt-1"),
                    ]),
                ], className="damu-inst2-block damu-inst2-pair"),

                html.Div([
                    html.Div([
                        html.Span("Проектов за месяц, шт"),
                        # Цвет переменной, а не значением: вписанный
                        # `rgba(32,30,29,.75)` в тёмной теме давал контраст
                        # 1.03 : 1 — текст сливался с фоном (замерено 04.08.2026)
                        html.Span(f"за год {num(sum(item['months']))}",
                                  style={"color": "var(--damu-ink)"}),
                    ], className="damu-band-kicker d-flex justify-content-between mb-2",
                        style={"color": "var(--damu-muted)"}),
                    *_months(item, CARD_CHART_H, "damu-inst2-month",
                             tight=expanded, show_values=not expanded),
                ], className="damu-inst2-block"),
            ], className="damu-inst2-body"),
        ],
        className=f"damu-inst2 damu-c-{tone}",
    )


def programs_block() -> dbc.Card:
    """Разбивка по программам — три колонки по инструментам.

    Колонки «Все инструменты» здесь нет: сводные числа уже стоят в полосе
    наверху, и повторять их значило бы показать одно и то же дважды.
    Ширина полоски — доля от самой большой программы В СВОЕЙ колонке.
    """
    tones = {"Гарантирование": 1, "Кредитование": 2, "Субсидирование": 3}
    columns = []
    for column in mockup.PROGRAMS[1:]:
        short = column["title"].split(" — ")[0]
        top_amount = max(row[1] for row in column["rows"])
        top_count = max(row[2] for row in column["rows"])
        rows = [
            html.Div([
                html.Span(name, className="damu-prog-name text-truncate"),
                html.Div(html.Div(className="damu-bar-fill", style={
                    "width": f"{amount / top_amount * 100:.0f}%", "height": "7px"}),
                    className="damu-bar", style={"height": "7px"}),
                html.Span(num(amount), className="damu-prog-value"),
                html.Div(html.Div(className="damu-bar-fill", style={
                    "width": f"{count / top_count * 100:.0f}%", "height": "7px",
                    "opacity": .45}),
                    className="damu-bar", style={"height": "7px"}),
                html.Span(num(count), className="damu-prog-value",
                          style={"fontWeight": 400, "color": "var(--damu-muted)"}),
            ], className="damu-prog-row",
                style={"gridTemplateColumns": "minmax(0,1fr) 90px 42px 60px 32px",
                       "height": "23px", "fontSize": "0.78rem", "marginBottom": 0})
            for name, amount, count in column["rows"]
        ]
        columns.append(html.Div([
            html.Div([
                html.Span(short, className="damu-prog-head flex-grow-1",
                          style={"border": "none", "padding": 0, "margin": 0}),
                html.Span(num(sum(r[1] for r in column["rows"])), style={
                    "marginLeft": "auto", "fontSize": "0.81rem", "fontWeight": 800,
                    "color": "var(--damu-c)"}),
            ], className="d-flex align-items-baseline gap-2 pb-2 mb-2",
                style={"borderBottom": "2px solid var(--damu-c)"}),
            *rows,
        ], className=f"damu-prog-col damu-c-{tones[short]}"))

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div("Разбивка по программам", className="damu-block-title"),
                html.Span("факт по инструментам", className="small text-muted"),
                html.Div([
                    html.Span([html.I(style={"width": "22px"}), "Освоено, млрд ₸"]),
                    html.Span([html.I(style={"width": "12px"}), "Проектов, шт"]),
                ], className="damu-prog-legend"),
            ], className="damu-block-head"),
            html.Div(columns, className="damu-prog-grid",
                     style={"gridTemplateColumns": "repeat(3, minmax(0,1fr))"}),
        ]),
        class_name="shadow-sm",
    )


def title_row(year: int, expanded: bool) -> html.Div:
    """Заголовок витрины: год, плашка макетных чисел, тумблер графиков."""
    def year_button(value: int):
        return html.Button(
            str(value),
            id={"type": "main-year", "year": value},
            className="active" if value == year else "",
            n_clicks=0,
        )

    switch = html.Button(
        [
            html.Span("Графики за весь год"),
            html.Span(html.Span(className="damu-switch-knob"),
                      className="damu-switch-track"),
        ],
        id="main-expand",
        className="damu-switch" + (" active" if expanded else ""),
        title="Показать все прошедшие месяцы во всех графиках",
        n_clicks=0,
    )

    children = [
        html.H1("Освоение плана", className="h4 mb-0"),
        html.Div([year_button(YEAR_NOW), year_button(YEAR_PREV)],
                 className="damu-year"),
        html.Span("Макетные числа", className="damu-mock-badge",
                  title="Разрезов по инструментам в хранилище пока нет — "
                        "числа из эскиза"),
    ]
    if mockup.can_expand(year):
        children.append(switch)
    return html.Div(children, className="d-flex align-items-center gap-3")


def showcase(year: int, expanded: bool):
    """Вся макетная витрина целиком — её перерисовывает один коллбэк."""
    items = mockup.for_year(year, expanded)
    return [
        title_row(year, expanded),
        band(items[0], expanded),
        html.Div([instrument_card(it, expanded) for it in items[1:]],
                 className="damu-inst-grid"),
        programs_block(),
    ]


def layout(**kwargs):
    """Собирается на каждое открытие страницы."""
    try:
        data.get_years()          # хранилище на месте? иначе покажем подсказку
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    return dbc.Container(
        [
            # Состояние витрины держим на странице: коллбэк читает его отсюда,
            # а не восстанавливает по подсветке кнопок
            dcc.Store(id="main-view", data={"year": YEAR_NOW, "expanded": False}),
            html.Div(showcase(YEAR_NOW, False), id="main-showcase",
                     className="d-flex flex-column gap-3"),
            dbc.Card(
                dbc.CardBody([
                    html.Div([
                        html.Div("Освоение по регионам", className="damu-block-title"),
                        html.Span("картограмма по показателю «Освоено бюджета»",
                                  className="small text-muted"),
                        html.Span("Настоящие данные", className="damu-mock-badge",
                                  style={"color": "var(--damu-accent-dark)",
                                         "borderColor": "var(--damu-accent)",
                                         "marginLeft": "auto"}),
                    ], className="damu-block-head"),
                    dcc.Graph(id="main-map", config={"displayModeBar": False},
                              style={"height": "440px"}),
                ]),
                class_name="shadow-sm mt-3",
            ),
        ],
        fluid=True,
        className="pb-5",
    )


@callback(
    Output("main-view", "data"),
    Input({"type": "main-year", "year": ALL}, "n_clicks"),
    Input("main-expand", "n_clicks"),
    State("main-view", "data"),
    prevent_initial_call=True,
)
def switch_view(_years, _expand, view):
    """Запоминает выбор года и состояние тумблера.

    Проверка значения отсеивает «пустые» срабатывания в момент, когда кнопки
    только появились на странице: коллбэк перерисовывает витрину вместе
    с кнопками, и без этой проверки перерисовка звала бы сама себя.
    """
    trigger = ctx.triggered_id
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return dash.no_update
    if trigger == "main-expand":
        return {**view, "expanded": not view.get("expanded", False)}
    if isinstance(trigger, dict) and trigger.get("type") == "main-year":
        year = int(trigger["year"])
        # Смена года сбрасывает разворот: у прошлого года месяцев двенадцать,
        # и развёрнутый график из шести превратился бы в кашу молча
        return {"year": year, "expanded": False}
    return dash.no_update


@callback(
    Output("main-showcase", "children"),
    Input("main-view", "data"),
    prevent_initial_call=True,
)
def render_showcase(view):
    return showcase(int(view.get("year", YEAR_NOW)),
                    bool(view.get("expanded", False)))


@callback(
    Output("main-map", "figure"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
)
def render_map(year, regions, _version):
    """Карта — единственное на этой странице, что живёт по настоящим данным."""
    return charts.build("map", MAP_INDICATOR, year, regions, height=440)
