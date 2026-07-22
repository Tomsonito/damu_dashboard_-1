"""Главный экран: показатели МСП по регионам."""

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from dash import Input, Output, callback, dcc, html

from core import data

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")


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
                        md=3,
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
                        md=6,
                    ),
                ],
                className="mb-4 g-3",
            ),
            dbc.Row(id="kpi-row", className="mb-4 g-3"),
            dcc.Graph(id="regions-chart"),
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
)
def render_chart(indicator, year):
    meta = data.get_indicator_meta(indicator)
    df = data.get_regions(indicator, int(year))
    df["shown"] = df["value"] / meta["divisor"]

    fig = px.bar(
        df,
        x="shown",
        y="region",
        orientation="h",
        text=[data.format_value(v, indicator) for v in df["value"]],
        labels={"shown": meta["display_unit"] or meta["unit"], "region": ""},
        title=f"{meta['title']} — {year} год",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_yaxes(categoryorder="total ascending")
    fig.update_layout(
        height=700,
        margin=dict(l=10, r=120, t=60, b=40),
        plot_bgcolor="white",
    )
    return fig
