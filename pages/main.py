"""Главный экран: показатели МСП по регионам."""

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from dash import Input, Output, callback, dash_table, dcc, html
from dash.dash_table.Format import Format, Group, Scheme

from core import data

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")

# Виды диаграмм. Добавить вид = строка здесь + ветка в render_chart.
CHART_TYPES = [
    {"label": "Полосы — рейтинг", "value": "bar"},
    {"label": "Круговая — доли", "value": "pie"},
    {"label": "Плитки — структура", "value": "treemap"},
    {"label": "Сравнение лет", "value": "years"},
]

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
                            dbc.RadioItems(
                                id="filter-chart-type",
                                options=CHART_TYPES,
                                value="bar",
                                inline=True,
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
)
def render_chart(indicator, year, chart_type, regions):
    meta = data.get_indicator_meta(indicator)
    year = int(year)
    regions = regions or None  # пустой список из фильтра означает «все»
    unit = meta["display_unit"] or meta["unit"]

    if chart_type == "years":
        # Единственный вид, которому нужны все годы сразу — фильтр года не участвует
        df = data.get_region_dynamics(indicator, regions)
        df["shown"] = df["value"] / meta["divisor"]
        df["год"] = df["report_year"].astype(str)
        fig = px.bar(
            df,
            x="shown",
            y="region",
            color="год",
            barmode="group",
            orientation="h",
            labels={"shown": unit, "region": ""},
            title=f"{meta['title']} — сравнение лет",
        )
        fig.update_yaxes(categoryorder="max ascending")
    else:
        df = data.get_regions(indicator, year, regions=regions)
        df["shown"] = df["value"] / meta["divisor"]
        title = f"{meta['title']} — {year} год"

        if chart_type == "pie":
            fig = px.pie(df, names="region", values="shown", title=title)
            fig.update_traces(textposition="inside", textinfo="percent+label")
        elif chart_type == "treemap":
            fig = px.treemap(df, path=["region"], values="shown", title=title)
            fig.update_traces(texttemplate="%{label}<br>%{value:,.1f}")
        else:  # bar
            fig = px.bar(
                df,
                x="shown",
                y="region",
                orientation="h",
                text=[data.format_value(v, indicator) for v in df["value"]],
                labels={"shown": unit, "region": ""},
                title=title,
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            fig.update_yaxes(categoryorder="total ascending")

    fig.update_layout(
        height=700,
        margin=dict(l=10, r=120, t=60, b=40),
        plot_bgcolor="white",
    )
    return fig


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
