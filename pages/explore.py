"""Разбор — список примеров раскладки.

Пока страница работает как оглавление: пользователь нарисовал в Claude
Design четыре варианта того, как может выглядеть разбор показателей,
и выбирает из них вживую. Сами примеры — `pages/explore_example.py`,
адреса `/explore/1` … `/explore/4`.

!! Это **временное состояние**. Когда вариант выберут, лишние примеры
удаляются, а выбранный переедет сюда и станет настоящей витриной
показателей. Тогда же исчезнет и меню «Разбор ▾» в шапке.

Чего на странице больше нет (убрано 30.07.2026): прежний «один график
на выбор» — два списка, 12 показателей × 20 видов, галка логарифма
и таблица с данными. Вместе с ними **с сайта ушли таблица с данными
и сохранение графика в PNG**: их не было больше нигде. Вернуть можно
из истории git — `pages/explore.py` до 30.07.2026.
"""

import dash
import dash_bootstrap_components as dbc
from dash import html

from core.examples import EXAMPLES

dash.register_page(__name__, path="/explore", name="Разбор",
                   title="Разбор — Дашборд Даму")


def _card(example: dict) -> dbc.Card:
    """Плитка одного примера: номер, откуда взят, про что вариант."""
    return dbc.Card(
        dbc.CardBody([
            html.Div(
                [
                    html.H4(example["title"], className="mb-0"),
                    html.Span(example["source"], className="text-muted small ms-auto",
                              title="номер варианта в макете"),
                ],
                className="d-flex align-items-baseline gap-2",
            ),
            html.P(example["note"], className="text-muted small mt-2 mb-3"),
            dbc.Button("Посмотреть", href=f"/explore/{example['key']}",
                       color="primary", size="sm"),
        ]),
        class_name="h-100 shadow-sm",
    )


def layout(**kwargs):
    return dbc.Container(
        [
            html.H2("Разбор", className="mt-4"),
            html.P(
                "Варианты раскладки — каждый отдельной страницей, чтобы "
                "посмотреть вживую и выбрать. Первые четыре взяты из макета, "
                "пятый — доработка третьего. Числа во всех примерах макетные "
                "и на фильтры не реагируют: страницы про раскладку, "
                "а не про данные.",
                className="text-muted small",
            ),
            dbc.Row(
                [dbc.Col(_card(e), xs=12, md=6, xl=4, class_name="mb-3")
                 for e in EXAMPLES],
                class_name="g-3",
            ),
        ],
        fluid=True,
        className="pb-5",
    )
