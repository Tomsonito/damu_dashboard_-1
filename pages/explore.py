"""Разбор: один график за раз, любой вид и показатель на выбор.

Это прежний главный экран. Он не выброшен, а переехал сюда, когда главная
стала собираться из нескольких настроенных виджетов: витрина показывает
то, что решил админ, а здесь можно покопаться самому — перебрать 17 видов,
сравнить показатели, посмотреть данные таблицей.

Идентификаторы у полей свои (`ex-...`): в Dash они общие на всё приложение,
а на главной теперь тоже есть фильтры года и регионов. Совпади имена —
коллбэки двух страниц полезли бы друг другу в выходы.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dash_table, dcc, html, no_update
from dash.dash_table.Format import Format, Group, Scheme

from core import charts, data

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/explore", name="Разбор",
                   title="Разбор — Дашборд Даму")

# Формат чисел в таблице: разряды через пробел, без дробной части
TABLE_NUM_FORMAT = Format(
    group=Group.yes, groups=3, group_delimiter=" ", precision=0, scheme=Scheme.fixed
)

# Подпись галки логарифма. Перечня видов в ней намеренно нет: кто умеет
# логарифм, знает реестр диаграмм, и подпись собирается из него в toggle_log.
LOG_LABEL = ("Логарифмическая шкала — сжимает разрыв между крупными "
             "и мелкими регионами")


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
            html.H2("Разбор показателей", className="mt-4"),
            html.P(f"данные обновлены в {updated}", id="ex-updated",
                   className="text-muted small"),
            # Невидимая пара, на которой держится автообновление: таймер
            # раз в 30 сек и запомненная display-версия (факты + план)
            dcc.Interval(id="ex-poll", interval=30 * 1000),
            dcc.Store(id="ex-version", data=version),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Отчётный год"),
                            dbc.Select(
                                id="ex-year",
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
                                id="ex-indicator",
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
                                id="ex-chart-type",
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
                            id="ex-regions",
                            options=regions,
                            multi=True,
                            placeholder="Все регионы — можно выбрать несколько",
                        ),
                        dbc.Checkbox(
                            id="ex-log",
                            label=LOG_LABEL,
                            value=False,
                            className="mt-2 small text-muted",
                        ),
                    ],
                ),
                className="mb-4",
            ),
            dcc.Graph(
                id="ex-chart",
                # Здесь панель инструментов нужна — страница для того и есть,
                # чтобы копаться. Убраны только два лишних: значок plotly
                # (ссылка на чужой сайт, во внутренней сети не откроется)
                # и выделение лассо с рамкой — они осмысленны на точечных
                # диаграммах с тысячами точек, а у нас двадцать областей.
                config={
                    "displaylogo": False,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                    # Имя файла при сохранении картинки — вместо «newplot»
                    "toImageButtonOptions": {"filename": "дашборд-даму"},
                },
            ),
            html.H4("Данные таблицей", className="mt-4"),
            html.P(
                "Клик по заголовку колонки сортирует",
                className="text-muted small",
            ),
            dash_table.DataTable(
                id="ex-table",
                sort_action="native",
                style_table={"overflowX": "auto"},
                style_cell={
                    # Через переменную темы, а не жёстким списком шрифтов:
                    # у таблицы свои стили, и без этой строки она осталась бы
                    # единственным местом на странице со старым шрифтом
                    "fontFamily": "var(--damu-font, system-ui, sans-serif)",
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
    Output("ex-version", "data"),
    Output("ex-updated", "children"),
    Input("ex-poll", "n_intervals"),
    State("ex-version", "data"),
)
def poll_version(_, known_version):
    """Раз в 30 сек сверяет версию данных с той, что помнит страница.

    Совпала — `no_update`, ничего не перерисовывается. Изменилась
    (опубликованы данные или план) — новый номер уходит в Store, и все
    коллбэки с `Input("ex-version", ...)` перерисуются сами. Фильтры при
    этом не трогаются: обновляются только выходы коллбэков, а состояние
    фильтров живёт в браузере.

    Шлюз публикации отсюда НЕ дёргается — им занимается главная страница
    и прогоны etl.run. Иначе две открытые вкладки лезли бы в хранилище
    на запись одновременно, а толку от второй нет.
    """
    fresh = data.get_display_version()
    if known_version is not None and str(known_version) == fresh:
        return no_update, no_update
    return fresh, f"данные обновлены в {data.get_last_update()}"


@callback(
    Output("ex-log", "disabled"),
    Output("ex-log", "label"),
    Input("ex-chart-type", "value"),
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
    Output("ex-chart", "figure"),
    Input("ex-indicator", "value"),
    Input("ex-year", "value"),
    Input("ex-chart-type", "value"),
    Input("ex-regions", "value"),
    Input("ex-log", "value"),
    Input("ex-version", "data"),
)
def render_chart(indicator, year, chart_type, regions, log, _version):
    """Вся отрисовка живёт в core/charts.py — здесь только передача выбора."""
    return charts.build(chart_type, indicator, year, regions, log)


@callback(
    Output("ex-table", "data"),
    Output("ex-table", "columns"),
    Input("ex-year", "value"),
    Input("ex-regions", "value"),
    Input("ex-version", "data"),
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
