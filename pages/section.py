"""Страница одного раздела — по макету 5b (и по образцу боевого портала).

Что на ней сверху вниз:

    ┌──────────┬──────────────────────────────────────────────┐
    │ разделы  │  Гар. выдача на 28.07.2026                   │
    │ списком  │ ┌ липкие вкладки ─────────────────────────┐  │
    │ слева    │ │ Годы │ Программы │ Регионы │ БВУ │ ГФ1 │  │  │
    │ (☰ —     │ └ ── под-вкладки группы: Лимиты · Пайп ──┘  │
    │  свернуть│  карточки-показатели                         │
    │  список) │  ── секция «Динамика по годам» ──            │
    │          │  ── секция «Программы» ──                    │
    │          │  ...                                         │
    └──────────┴──────────────────────────────────────────────┘

**Главное отличие от прежней версии страницы: вкладка больше не переключает
содержимое.** Раздел — одна длинная лента, все разрезы лежат на ней сразу,
а вкладка прокручивает ленту к своей секции. Прокрутили мышью — вкладка
подсветилась сама. Так устроен макет и так же ведёт себя боевой портал:
человек видит, что ниже есть ещё, и не гадает, что спрятано под вкладками.

Подсветка и прокрутка сделаны на стороне браузера (`assets/dashboard.js`),
без коллбэков: коллбэк на каждое движение колеса мыши гонял бы запросы
к серверу десятками в секунду.

Вкладки **переносятся на второй ряд**, а не уезжают в горизонтальную
прокрутку: прокрутку вбок на широком экране не видно, и часть вкладок
просто терялась бы.

Страница **одна на все разделы**: адрес `/section/guarantee` разбирается
по шаблону, ключ приходит в `layout(key=...)`. Двадцати одинаковых файлов
нет — разделы устроены одинаково, отличаются только данными.

Набор вкладок берётся из `config.yaml` (`section_tabs`, а для отдельных
разделов — `section_tabs_by_section`). Вкладки с общим полем `group`
сворачиваются в одну вкладку верхнего уровня, раскрывающую ряд «пилюль».

!! Разрезы, под которые данных ещё нет (Программы, БВУ, Бюджет), помечены
в конфиге `data: false` и показывают полосатые заглушки из макета плюс
честную строку «ждёт источника». Пустые рамки выглядели бы поломкой.
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

#: Сколько заглушек-диаграмм рисовать в секции без данных. Четыре —
#: как в макете: видно, что место под разрез готово.
STUB_COUNT = 4


def block_id(tab_key: str) -> str:
    """Идентификатор секции в ленте. По нему же вкладка её и находит."""
    return f"sec-block-{tab_key}"


def top_entries(tabs: list[dict]) -> list[dict]:
    """Вкладки верхнего уровня: обычные поодиночке, группы — одной штукой.

    Возвращает для каждой вкладки её состав (`members`) — ключи секций,
    которые она собой закрывает. Браузеру это нужно, чтобы понять, какую
    вкладку подсветить: доскроллили до «Пайп» — светится группа «ГФ1».
    """
    entries: list[dict] = []
    by_group: dict[str, dict] = {}
    for tab in tabs:
        group = tab.get("group")
        if not group:
            entries.append({
                "key": tab["key"], "title": tab["title"],
                "members": [tab["key"]], "group": None,
                "data": tab.get("data"),
            })
            continue
        if group not in by_group:
            by_group[group] = {
                "key": f"group:{group}", "title": group,
                "members": [], "group": group, "data": False,
            }
            entries.append(by_group[group])
        by_group[group]["members"].append(tab["key"])
        # У группы есть данные, если они есть хоть у одной её вкладки —
        # иначе группа висела бы приглушённой при живом разрезе внутри
        by_group[group]["data"] = by_group[group]["data"] or tab.get("data")
    return entries


def tab_bar(tabs: list[dict]):
    """Липкий ряд вкладок и, под ним, ряды «пилюль» для каждой группы.

    Разметку читает `assets/dashboard.js`, поэтому у элементов есть
    data-атрибуты: `data-scroll-to` — куда прокрутить, `data-members` —
    какие секции закрывает вкладка, `data-group-row` — к какой группе
    относится ряд пилюль. Никакой логики в самих атрибутах нет, это
    просто способ передать браузеру то, что и так знает конфиг.
    """
    entries = top_entries(tabs)
    buttons = []
    for i, entry in enumerate(entries):
        buttons.append(html.Button(
            entry["title"],
            className="damu-sec-tab" + (" active" if i == 0 else "")
                      + ("" if entry["data"] else " damu-empty"),
            **{
                "data-tab-key": entry["key"],
                "data-members": ",".join(entry["members"]),
                "data-scroll-to": block_id(entry["members"][0]),
            },
        ))

    rows = [html.Div(buttons, className="damu-sec-tabs")]
    for entry in entries:
        if not entry["group"]:
            continue
        pills = [
            html.Button(
                tab["title"],
                className="damu-sec-subtab" + (" damu-empty" if not tab.get("data") else ""),
                **{"data-scroll-to": block_id(tab["key"]),
                   "data-sub-key": tab["key"]},
            )
            for tab in tabs if tab.get("group") == entry["group"]
        ]
        rows.append(html.Div(
            pills,
            className="damu-sec-subtabs",
            # Ряд появляется только когда выбрана его группа — прячет
            # и показывает его тот же dashboard.js
            style={"display": "none"},
            **{"data-group-row": entry["key"]},
        ))
    return html.Div(rows, className="damu-sec-tabbar")


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
        id="section-sidebar",
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


def chart_stubs():
    """Заглушки из макета — для разреза, под который данных ещё нет."""
    return dbc.Row(
        [
            dbc.Col(
                html.Div([
                    html.Div(f"Диаграмма {i + 1}", className="damu-chart-title"),
                    html.Div("chart placeholder", className="damu-chart-stub"),
                ], className="damu-chart-card"),
                md=6, className="mb-3",
            )
            for i in range(STUB_COUNT)
        ],
        className="g-3",
    )


def widget_grid(section_key: str, tab_key: str, items: list[dict]):
    """Места под диаграммы одного разреза; фигуры подставит коллбэк.

    !! В id виджета склеены вкладка и номер (`years|3`). Иначе коллбэк
    не смог бы понять, из какого набора виджет: на ленте лежат разрезы
    сразу все, а наборы у них разные.
    """
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
                        id={"type": "section-widget",
                            "index": f"{tab_key}|{item['id']}"},
                        style={"height": f"{preset['height']}px"},
                        config={"displayModeBar": False},
                    ),
                    className="shadow-sm p-2 h-100",
                ),
                xs=12, lg=preset["columns"], className="mb-3",
            )
        )
    return dbc.Row(columns, className="g-3")


def section_block(section_key: str, tab: dict):
    """Одна секция ленты: заголовок разреза и его содержимое."""
    if tab.get("data"):
        body = widget_grid(
            section_key, tab["key"],
            widgets.get_widgets(widgets.page_key(section_key, tab["key"])),
        )
    else:
        body = html.Div([
            html.Div(
                "Разрез ждёт источника данных — ниже макет того, что здесь "
                "появится. Колонки под него в таблице фактов уже заведены.",
                className="damu-mock mb-3",
            ),
            chart_stubs(),
        ])

    return html.Div(
        [
            html.Div(tab["title"], className="damu-sec-block-title"),
            body,
        ],
        id=block_id(tab["key"]),
        className="damu-sec-block",
        **{"data-key": tab["key"]},
    )


def layout(key: str | None = None, **kwargs):
    """Собирается на каждое открытие: раздел, вкладки и набор виджетов свежие."""
    program = widgets.program_of(key) if key else None
    if program is None:
        return dbc.Alert("Такого раздела нет. Выберите его в списке слева.",
                         color="warning", className="m-4")

    tabs = widgets.tabs_of(key)

    try:
        updated = data.get_last_update()
    except Exception:
        updated = "—"

    return html.Div(
        [
            sections_menu(key),
            # Кнопка сворачивания списка. Работает целиком в браузере:
            # сворачивание — вопрос вида, а не данных, гонять его через
            # сервер незачем
            html.Button("☰", id="section-sidebar-toggle",
                        className="damu-side-toggle",
                        **{"data-toggle-sidebar": "1",
                           "aria-label": "Свернуть список разделов"}),
            html.Div(
                [
                    html.H2(f"{program} на {updated}", className="damu-sec-title"),
                    # Ключ раздела держим на странице: коллбэки читают его
                    # отсюда, а не разбирают адрес заново
                    dcc.Store(id="section-key", data=key),
                    tab_bar(tabs),
                    dbc.Row(id="section-kpi", className="my-3 g-3"),
                    *[section_block(key, tab) for tab in tabs],
                ],
                className="damu-sec-main",
            ),
        ],
        className="damu-sec-wrap",
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
    State({"type": "section-widget", "index": ALL}, "id"),
)
def render_widgets(year, regions, _version, key, ids):
    """Рисует виджеты всех разрезов разом, считая всё только по своему разделу.

    Наборы перечитываются по одному разу на разрез и запоминаются в словаре:
    на ленте разрезов несколько, и ходить в хранилище за каждым виджетом
    значило бы читать один и тот же набор по шесть раз.
    """
    program = widgets.program_of(key)
    by_tab: dict[str, dict] = {}
    figures = []
    for graph_id in ids:
        tab_key, _, widget_id = str(graph_id["index"]).partition("|")
        if tab_key not in by_tab:
            by_tab[tab_key] = {
                str(item["id"]): item
                for item in widgets.get_widgets(widgets.page_key(key, tab_key))
            }
        item = by_tab[tab_key].get(widget_id)
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
