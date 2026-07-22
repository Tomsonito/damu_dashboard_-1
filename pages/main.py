"""Главный экран: показатели МСП по регионам."""

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, callback, dash_table, dcc, html
from dash.dash_table.Format import Format, Group, Scheme

from core import charts, data

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")

# Формат чисел в таблице: разряды через пробел, без дробной части
TABLE_NUM_FORMAT = Format(
    group=Group.yes, groups=3, group_delimiter=" ", precision=0, scheme=Scheme.fixed
)


def kpi_card(row: pd.Series) -> dbc.Card:
    """Карточка одного показателя: значение и изменение к прошлому году."""
    change = row["change_pct"]
    if change is None or pd.isna(change):
        footer = html.Span("нет данных за прошлый год", className="small text-muted")
    else:
        grew = change >= 0
        footer = html.Span(
            f"{'▲' if grew else '▼'} {abs(change):.1f} % к прошлому году",
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


def layout(**kwargs):
    """Собирается на каждое открытие страницы — значит фильтры всегда свежие."""
    try:
        years = data.get_years()
        indicators = data.get_indicator_choices()
        regions = data.get_region_choices()
        updated = data.get_last_update()
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    return dbc.Container(
        [
            html.H2("Показатели МСП по регионам", className="mt-4"),
            html.P(f"данные разобраны {updated}", className="text-muted small"),
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
                            label="Логарифмическая шкала — сжимает разрыв между "
                                  "крупными и мелкими регионами "
                                  "(работает на «Точках» и «Ящике»)",
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


@callback(Output("kpi-row", "children"), Input("filter-year", "value"))
def render_kpi(year):
    kpi = data.get_kpi(int(year))
    return [dbc.Col(kpi_card(row), md=3) for _, row in kpi.iterrows()]


@callback(
    Output("regions-chart", "figure"),
    Input("filter-indicator", "value"),
    Input("filter-year", "value"),
    Input("filter-chart-type", "value"),
    Input("filter-regions", "value"),
    Input("filter-log", "value"),
)
def render_chart(indicator, year, chart_type, regions, log):
    """Вся отрисовка живёт в core/charts.py — здесь только передача выбора."""
    return charts.build(chart_type, indicator, year, regions, log)


@callback(
    Output("regions-table", "data"),
    Output("regions-table", "columns"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
)
def render_table(year, regions):
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
