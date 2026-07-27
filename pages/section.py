"""Страница одного раздела — по образцу боевого портала.

Что на ней сверху вниз:

    ┌──────────┬──────────────────────────────────────────────┐
    │ разделы  │  Субсидирование на 24.07.2026                │
    │ списком  │  [Динамика по годам][Программы][ОКЭД/Регионы]│
    │ слева    │  [План освоения][Лимиты][Пайп]               │
    │          │  [План][Освоено][Остаток][Освоение %]        │
    │          │  виджеты с диаграммами                       │
    └──────────┴──────────────────────────────────────────────┘

Страница **одна на все разделы**: адрес `/section/guarantee` разбирается
по шаблону, ключ приходит в `layout(key=...)`. Двадцати одинаковых файлов
нет — разделы устроены одинаково, отличаются только данными.

Список разделов слева — как на портале: внутри раздела удобно прыгать
к соседнему, не возвращаясь на главную. На самой главной его нет, там
разделы вынесены вкладками.

Вкладки-разрезы и подрезы описаны в `config.yaml` (`section_tabs`,
`section_subtabs`). Под каждым разрезом — **свой набор виджетов**: ключ
набора склеивается из раздела и вкладки (`guarantee:regions`), поэтому
«Динамика по годам» и «ОКЭД/Регионы» показывают разное, и настраиваются
независимо.

!! Разрезы, под которые данных ещё нет (Программы, БВУ, Бюджет), помечены
в конфиге `data: false` и открываются честной заглушкой. Пустые рамки
вместо этого выглядели бы поломкой.
"""

import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, dcc, html

from core import charts, data, widgets

log = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path_template="/section/<key>",
    name="Раздел",
    title="Раздел — Дашборд Даму",
)


def sections_menu(active_key: str):
    """Список всех разделов слева — как на боевом портале."""
    try:
        with_data = set(data.get_programs())
    except Exception:
        with_data = set()

    links = []
    for section in data.load_config().get("sections") or []:
        empty = section["title"] not in with_data
        links.append(dbc.NavLink(
            section["title"],
            href=f"/section/{section['key']}",
            active=section["key"] == active_key,
            class_name="damu-empty" if empty else "",
        ))
    return html.Div(
        dbc.Nav(links, vertical=True, pills=True),
        className="damu-side-list",
    )


def tabs_row(items: list[dict], active: str, kind: str):
    """Ряд вкладок. `kind` разводит верхний ряд и нижний по типу id."""
    return html.Div(
        [
            dbc.Button(
                item["title"],
                id={"type": f"sec-{kind}", "index": item["key"]},
                class_name="damu-sec-tab" + (" active" if item["key"] == active else "")
                           + ("" if item.get("data") else " damu-empty"),
            )
            for item in items
        ],
        className="damu-sec-tabs",
    )


def kpi_card(row: pd.Series) -> dbc.Card:
    """Карточка показателя: подпись, крупное число, изменение к прошлому году."""
    change = row["change_pct"]
    if change is None or pd.isna(change):
        footer = html.Span("нет данных за прошлый год", className="small text-muted")
    else:
        grew = change >= 0
        unit = "п.п." if row.get("change_kind") == "pp" else "%"
        footer = html.Span(
            f"{'▲' if grew else '▼'} {abs(change):.1f} {unit} к прошлому году",
            className=f"small {'text-success' if grew else 'text-danger'}",
        )
    return dbc.Card(
        dbc.CardBody([
            html.Div(row["short"], className="text-muted small"),
            html.H3(row["text"], className="my-2"),
            footer,
        ]),
        className="h-100 shadow-sm",
    )


def widget_grid(items: list[dict]):
    """Места под диаграммы; фигуры подставит коллбэк."""
    if not items:
        return dbc.Alert("Виджетов нет. Добавьте их на странице «Виджеты».",
                         color="light", className="border")
    columns = []
    for item in items:
        preset = widgets.size_meta(item["size"])
        columns.append(
            dbc.Col(
                dbc.Card(
                    dcc.Graph(
                        id={"type": "section-widget", "index": item["id"]},
                        style={"height": f"{preset['height']}px"},
                        config={"displayModeBar": False},
                    ),
                    className="shadow-sm p-2 h-100",
                ),
                xs=12, lg=preset["columns"], className="mb-3",
            )
        )
    return dbc.Row(columns, className="g-3")


def _tab_meta(key: str, block: str) -> dict:
    for item in data.load_config().get(block) or []:
        if item["key"] == key:
            return item
    return {}


def content(section_key: str, tab: str, subtab: str):
    """Содержимое под вкладками: карточки и виджеты — или заглушка."""
    meta = _tab_meta(tab, "section_tabs")
    sub_meta = _tab_meta(subtab, "section_subtabs")

    if not meta.get("data") or not sub_meta.get("data"):
        missing = meta["title"] if not meta.get("data") else sub_meta["title"]
        return dbc.Alert(
            [
                html.B(f"«{missing}» ждёт источника данных. "),
                html.Span(
                    "Каркас готов: разрез появится сам, как только данные "
                    "лягут в хранилище — колонки под них в таблице фактов "
                    "уже есть."
                ),
            ],
            color="secondary", className="mt-3",
        )

    return html.Div([
        dbc.Row(id="section-kpi", className="mb-3 g-3"),
        widget_grid(widgets.get_widgets(widgets.page_key(section_key, tab))),
    ])


def layout(key: str | None = None, **kwargs):
    """Собирается на каждое открытие: раздел, вкладки и набор виджетов свежие."""
    program = widgets.program_of(key) if key else None
    if program is None:
        return dbc.Alert("Такого раздела нет. Выберите его в списке слева.",
                         color="warning", className="m-4")

    cfg = data.load_config()
    tabs = cfg.get("section_tabs") or []
    subtabs = cfg.get("section_subtabs") or []
    first_tab = tabs[0]["key"] if tabs else ""
    first_sub = subtabs[0]["key"] if subtabs else ""

    try:
        updated = data.get_last_update()
    except Exception:
        updated = "—"

    return html.Div(
        [
            sections_menu(key),
            html.Div(
                [
                    html.H2(f"{program} на {updated}", className="damu-sec-title"),
                    # Выбранные вкладки держим на странице: коллбэк читает их
                    # отсюда, а не разбирает адрес заново
                    dcc.Store(id="section-key", data=key),
                    dcc.Store(id="section-tab", data=first_tab),
                    dcc.Store(id="section-subtab", data=first_sub),
                    html.Div(tabs_row(tabs, first_tab, "tab"), id="section-tabs"),
                    html.Div(tabs_row(subtabs, first_sub, "sub"), id="section-subtabs"),
                    html.Div(content(key, first_tab, first_sub), id="section-body"),
                ],
                className="damu-sec-main",
            ),
        ],
        className="damu-sec-wrap",
    )


@callback(
    Output("section-tab", "data"),
    Output("section-subtab", "data"),
    Input({"type": "sec-tab", "index": ALL}, "n_clicks"),
    Input({"type": "sec-sub", "index": ALL}, "n_clicks"),
    State("section-tab", "data"),
    State("section-subtab", "data"),
    prevent_initial_call=True,
)
def switch_tab(_tabs, _subs, tab, subtab):
    """Запоминает нажатую вкладку. Всё остальное перерисовывается от неё."""
    trigger = dash.ctx.triggered_id
    if not isinstance(trigger, dict) or not dash.ctx.triggered:
        return tab, subtab
    if not dash.ctx.triggered[0]["value"]:
        return tab, subtab          # кнопки только что появились, никто не жал
    if trigger["type"] == "sec-tab":
        return trigger["index"], subtab
    return tab, trigger["index"]


@callback(
    Output("section-tabs", "children"),
    Output("section-subtabs", "children"),
    Output("section-body", "children"),
    Input("section-tab", "data"),
    Input("section-subtab", "data"),
    State("section-key", "data"),
)
def render_tabs(tab, subtab, key):
    """Перерисовывает обе полосы вкладок и содержимое под ними."""
    cfg = data.load_config()
    return (
        tabs_row(cfg.get("section_tabs") or [], tab, "tab"),
        tabs_row(cfg.get("section_subtabs") or [], subtab, "sub"),
        content(key, tab, subtab),
    )


@callback(
    Output("section-kpi", "children"),
    Input("filter-year", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
)
def render_kpi(year, _version, key):
    """Карточки раздела: план, освоено, остаток, процент — состав из конфига."""
    program = widgets.program_of(key)
    kpi = data.get_kpi(int(year), program=program)
    order = data.load_config().get("section_kpi") or []
    if order:
        kpi = kpi[kpi["indicator"].isin(order)]
        kpi = kpi.set_index("indicator").reindex(
            [k for k in order if k in set(kpi["indicator"])]
        ).reset_index()
    if kpi.empty:
        return dbc.Alert("По этому разделу нет показателей за выбранный год.",
                         color="light", className="border")
    return [dbc.Col(kpi_card(row), xs=12, md=True) for _, row in kpi.iterrows()]


@callback(
    Output({"type": "section-widget", "index": ALL}, "figure"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
    Input("section-tab", "data"),
    State({"type": "section-widget", "index": ALL}, "id"),
)
def render_widgets(year, regions, _version, key, tab, ids):
    """Рисует виджеты вкладки разом, считая всё только по своему разделу."""
    program = widgets.program_of(key)
    by_id = {item["id"]: item
             for item in widgets.get_widgets(widgets.page_key(key, tab))}
    figures = []
    for graph_id in ids:
        item = by_id.get(graph_id["index"])
        if item is None:
            figures.append(charts.message("Этот виджет удалили.<br>Обновите страницу (F5)."))
            continue
        preset = widgets.size_meta(item["size"])
        figures.append(
            charts.build(
                item["chart"], item["indicator"], year, regions,
                log=False, height=preset["height"], program=program,
            )
        )
    return figures
