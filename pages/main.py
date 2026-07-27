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
from dash import ALL, Input, Output, State, callback, dcc, html, no_update

from core import auth, charts, data, publish, widgets

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


def publish_banner():
    """Плашка «что ждёт публикации в 9:00» — видит только админ.

    Без неё окно на вето существовало бы только на бумаге. Зрителям плашка
    не показывается — им незачем знать про кухню публикации. Кто админ —
    спрашиваем у core/auth.py (до этапа 5 там заглушка: админ каждый).
    """
    if not auth.is_admin():
        return None
    try:
        pending = publish.pending_summary()
    except Exception:
        return None  # хранилища ещё нет — страница и так покажет подсказку

    parts = []
    if pending["version"] is not None:
        when = publish.describe_publish_time(
            publish.next_publish_time(pending["version_run_at"])
        )
        parts.append(
            f"версия данных {pending['version']} "
            f"(разобрана {pending['version_run_at']:%H:%M}) — выйдет {when}"
        )
    if pending["drafts"]:
        parts.append(f"черновиков плана: {pending['drafts']}")
    if not parts:
        return None

    return dbc.Alert(
        [
            html.Span("Ждёт публикации: " + "; ".join(parts) + ". "),
            dcc.Link("Отменить или забраковать — на странице «Ввод плана»", href="/plan"),
        ],
        color="info",
        className="py-2 small mb-3",
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
        years = data.get_years()
        regions = data.get_region_choices()
        updated = data.get_last_update()
        version = data.get_display_version()
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    items = widgets.get_widgets()

    hint = None
    if auth.is_admin():
        hint = html.P(
            [
                "Набор виджетов " +
                ("настроен вручную. " if widgets.is_customized()
                 else "взят из config.yaml (по умолчанию). "),
                dcc.Link("Изменить — на странице «Виджеты»", href="/widgets"),
            ],
            className="text-muted small",
        )

    return dbc.Container(
        [
            html.H2("Показатели МСП по регионам", className="mt-4"),
            html.P(f"данные обновлены в {updated}", id="data-updated",
                   className="text-muted small"),
            html.Div(publish_banner(), id="publish-banner"),
            # Невидимая пара, на которой держится автообновление: таймер
            # раз в 30 сек и запомненная display-версия (факты + план)
            dcc.Interval(id="data-poll", interval=30 * 1000),
            dcc.Store(id="data-version", data=version),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Отчётный год"),
                            dbc.Select(
                                id="filter-year",
                                options=[{"label": str(y), "value": y} for y in years],
                                value=years[0],
                            ),
                        ],
                        md=2,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Регионы (пусто = все)"),
                            dcc.Dropdown(
                                id="filter-regions",
                                options=regions,
                                multi=True,
                                placeholder="Все регионы — можно выбрать несколько",
                            ),
                        ],
                        md=10,
                    ),
                ],
                className="mb-4 g-3",
            ),
            dbc.Row(id="kpi-row", className="mb-4 g-3"),
            widget_grid(items),
            hint,
        ],
        fluid=True,
        className="pb-5",
    )


@callback(
    Output("data-version", "data"),
    Output("data-updated", "children"),
    Output("publish-banner", "children"),
    Input("data-poll", "n_intervals"),
    State("data-version", "data"),
)
def poll_version(_, known_version):
    """Раз в 30 сек: публикует дозревшее и сверяет версию данных.

    Сначала шлюз: publish_due() выпускает всё, чей срок наступил, — так
    ровно в первый опрос после 9:00 (или после подъёма сервера) публикация
    и происходит, отдельного планировщика нет. В холостую это две дешёвые
    строки чтения.

    Дальше: display-версия совпала — `no_update`, ничего не перерисовывается.
    Изменилась — новый номер уходит в Store, и коллбэки перерисуются сами.
    Фильтры при этом не трогаются: обновляются только выходы коллбэков.
    """
    try:
        published = publish.publish_due()
        if published:
            log.info("опубликовано: %s", published)
    except Exception:
        log.exception("публикация дозревшего не прошла — попробуем через 30 сек")

    fresh = data.get_display_version()
    banner = publish_banner()
    if known_version is not None and str(known_version) == fresh:
        return no_update, no_update, banner
    return fresh, f"данные обновлены в {data.get_last_update()}", banner


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
    by_id = {item["id"]: item for item in widgets.get_widgets()}
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
