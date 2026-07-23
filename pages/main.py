"""Главный экран: показатели МСП по регионам."""

import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
from dash.dash_table.Format import Format, Group, Scheme

from core import auth, charts, data, publish

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")

# Формат чисел в таблице: разряды через пробел, без дробной части
TABLE_NUM_FORMAT = Format(
    group=Group.yes, groups=3, group_delimiter=" ", precision=0, scheme=Scheme.fixed
)

# Подпись галки логарифма. Перечня видов в ней намеренно нет: кто умеет
# логарифм, знает реестр диаграмм, и подпись собирается из него в toggle_log.
LOG_LABEL = ("Логарифмическая шкала — сжимает разрыв между крупными "
             "и мелкими регионами")


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

    Так решено 23.07.2026: без неё окно на вето существовало бы только
    на бумаге. Зрителям плашка не показывается — им незачем знать
    про кухню публикации. Кто админ — спрашиваем у core/auth.py
    (до этапа 5 там заглушка: в разработке админ каждый).
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


def layout(**kwargs):
    """Собирается на каждое открытие страницы — значит фильтры всегда свежие."""
    try:
        years = data.get_years()
        indicators = data.get_indicator_choices()
        regions = data.get_region_choices()
        updated = data.get_last_update()
        version = data.get_display_version()
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    return dbc.Container(
        [
            html.H2("Показатели МСП по регионам", className="mt-4"),
            html.P(f"данные обновлены в {updated}", id="data-updated",
                   className="text-muted small"),
            # Плашку заполняет poll_version: она видна только админу
            # и живёт тем же 30-секундным ритмом, что и проверка версии
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
                            dbc.Label("Показатель на графике"),
                            dbc.Select(
                                id="filter-indicator",
                                options=indicators,
                                value=indicators[0]["value"],
                            ),
                        ],
                        md=5,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Вид диаграммы"),
                            dbc.Select(
                                id="filter-chart-type",
                                options=charts.get_choices(),
                                value="bar",
                            ),
                        ],
                        md=5,
                    ),
                ],
                className="mb-3 g-3",
            ),
            dbc.Row(
                dbc.Col(
                    [
                        dbc.Label("Регионы (пусто = все)"),
                        dcc.Dropdown(
                            id="filter-regions",
                            options=regions,
                            multi=True,
                            placeholder="Все регионы — можно выбрать несколько",
                        ),
                        dbc.Checkbox(
                            id="filter-log",
                            label=LOG_LABEL,
                            value=False,
                            className="mt-2 small text-muted",
                        ),
                    ],
                ),
                className="mb-4",
            ),
            dbc.Row(id="kpi-row", className="mb-4 g-3"),
            dcc.Graph(id="regions-chart"),
            html.H4("Данные таблицей", className="mt-4"),
            html.P(
                "Клик по заголовку колонки сортирует",
                className="text-muted small",
            ),
            dash_table.DataTable(
                id="regions-table",
                sort_action="native",
                style_table={"overflowX": "auto"},
                style_cell={
                    "fontFamily": "system-ui, sans-serif",
                    "padding": "6px 12px",
                },
                style_cell_conditional=[
                    {"if": {"column_id": "region"}, "textAlign": "left"}
                ],
                style_header={"fontWeight": "bold"},
            ),
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
    """Раз в 30 сек: публикует дозревшее и сверяет версию с той, что помнит страница.

    Сначала шлюз: publish_due() выпускает всё, чей срок наступил, — так
    ровно в первый опрос после 9:00 (или после подъёма сервера) публикация
    и происходит, отдельного планировщика нет. В холостую это две дешёвые
    строки чтения. До этапа 5 шлюз дёргается только отсюда и из прогонов
    etl.run; на этапе 5 добавится cron — но и эта проверка не помешает.

    Дальше как раньше: display-версия совпала — `no_update`, ничего не
    перерисовывается. Изменилась (опубликованы данные или план) — новый
    номер уходит в Store, и все коллбэки с `Input("data-version", ...)`
    перерисуются сами. Фильтры при этом не трогаются: обновляются только
    выходы коллбэков, а состояние фильтров живёт в браузере.

    Плашка админа обновляется каждый опрос: черновики и pending-версии
    появляются без смены опубликованной версии, no_update их бы прозевал.
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
    Output("filter-log", "disabled"),
    Output("filter-log", "label"),
    Input("filter-chart-type", "value"),
)
def toggle_log(chart_type):
    """Гасит галку логарифма на видах, которые его не умеют.

    Логарифм честен только там, где длина не обещает отсчёта от нуля —
    на точках и ящике. На столбцах он врёт, поэтому виды помечены в реестре
    флагом `log_ok`, и `build()` игнорирует галку на остальных.

    Раньше это было видно только по подписи, где виды перечислялись словами:
    галка нажималась на всех 17 видах, а действовала на двух. Теперь и
    доступность, и текст берутся из реестра — добавите вид с `log_ok=True`,
    и он подхватится сам, без правки этой страницы.
    """
    if charts.supports_log(chart_type):
        return False, LOG_LABEL
    return True, f"{LOG_LABEL} (этот вид её не поддерживает)"


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
    Output("regions-chart", "figure"),
    Input("filter-indicator", "value"),
    Input("filter-year", "value"),
    Input("filter-chart-type", "value"),
    Input("filter-regions", "value"),
    Input("filter-log", "value"),
    Input("data-version", "data"),
)
def render_chart(indicator, year, chart_type, regions, log, _version):
    """Вся отрисовка живёт в core/charts.py — здесь только передача выбора."""
    return charts.build(chart_type, indicator, year, regions, log)


@callback(
    Output("regions-table", "data"),
    Output("regions-table", "columns"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
)
def render_table(year, regions, _version):
    df = data.get_table(int(year), regions or None)

    columns = [{"name": "Регион", "id": "region"}]
    for key in df.columns[1:]:
        meta = data.get_indicator_meta(key)
        columns.append(
            {
                "name": f"{meta['short']}, {meta['unit']}",
                "id": key,
                "type": "numeric",  # без этого сортировка была бы алфавитной
                "format": TABLE_NUM_FORMAT,
            }
        )
    return df.to_dict("records"), columns
