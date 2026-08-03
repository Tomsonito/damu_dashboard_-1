"""Страницы-примеры раскладки: «Разбор» → Пример 1…4.

!! **Это временные страницы под выбор дизайна.** Пользователь нарисовал
в Claude Design варианты того, как может выглядеть разбор показателей,
и попросил перенести каждый отдельной страницей, чтобы посмотреть их вживую
и выбрать. Лишние потом удаляются, выбранный переезжает в обычную страницу.

Что где:

| Страница | Из макета | Про что вариант |
|---|---|---|
| Пример 1 | 1a | ровная сетка: четыре инструмента строками таблицы |
| Пример 2 | 1b | иерархия: «Все инструменты» полосой-итогом, три плитки |
| Пример 3 | 1c | два столбца: инструменты слева, все программы справа |
| Пример 4 | 1d | шкалы-полукруги (SVG вместо Plotly) и настоящая карта |

**Числа макетные и НЕ реагируют на фильтры** — так решено с пользователем:
страницы существуют ради раскладки, а не ради данных. Единственное живое
место — карта в Примере 4, она рисуется по настоящим данным.

**Почему здесь инлайновые стили, хотя в проекте так не принято.** Обычные
страницы держат оформление классами в `assets/custom.css` — это правильно,
пока страница живёт долго. Эти примеры живут до выбора: лишние будут
удалены. Инлайн держит вариант целиком в одном месте — удалил функцию,
и следов не осталось; классы в общем CSS пришлось бы выискивать и подчищать
руками, а забытые правила копятся молча.

Разные варианты нарочно отличаются цветом третьего инструмента и составом
блоков — так их нарисовал автор макета, и подгонять их друг под друга
значило бы лишить смысла само сравнение.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import html

from core import charts, data, examples, mockup
from core.examples import (DIVIDER, GOLD, GREEN, HAIRLINE, INK, LATE, MUTED,
                           OLIVE, PALE, SHADOW, SURFACE, TOTAL, TRACK, num)

log = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path_template="/explore/<key>",
    name="Пример раскладки",
    title="Пример — Дашборд Даму",
)

#: Показатель для настоящей карты в Примере 4.
MAP_INDICATOR = "budget_spent"


# ──────────────────────────── общие данные ────────────────────────────

def _instruments() -> list[dict]:
    """Инструменты с посчитанными числами — общая основа всех примеров."""
    out = []
    for item in mockup.INSTRUMENTS:
        n = mockup.card_numbers(item)
        color = examples.COLORS[item["key"]]
        out.append({
            **item, **n,
            "color": color,
            "status_color": GREEN if n["on_track"] else LATE,
            "status": "В графике" if n["on_track"] else "Отставание",
            "gap_short": ("+" if n["on_track"] else "−") + num(abs(n["gap"]), 1) + " п.п.",
        })
    return out


def _programs(colors: list[str]) -> list[dict]:
    """Колонки разбивки по программам с шириной полосок.

    Ширина — доля от самой большой программы В СВОЕЙ колонке: колонки про
    разное, и общий масштаб превратил бы правые в еле заметные чёрточки.
    """
    out = []
    for column, color in zip(mockup.PROGRAMS, colors):
        top_amount = max(row[1] for row in column["rows"])
        top_count = max(row[2] for row in column["rows"])
        out.append({
            "short": column["title"].split(" — ")[0],
            "color": color,
            "total": num(sum(row[1] for row in column["rows"])),
            "rows": [
                {
                    "name": name,
                    "amount": num(amount), "count": num(count),
                    "amount_width": f"{amount / top_amount * 100:.0f}%",
                    "count_width": f"{count / top_count * 100:.0f}%",
                }
                for name, amount, count in column["rows"]
            ],
        })
    return out


# ──────────────────────────── кирпичики ────────────────────────────

def _kicker(text, color=PALE, size="9.5px", extra=None):
    """Метка-капслок — самый частый элемент макета."""
    style = {"fontSize": size, "fontWeight": 700, "letterSpacing": ".09em",
             "textTransform": "uppercase", "color": color}
    style.update(extra or {})
    return html.Div(text, style=style)


def _bar(width, color, height=5, track=TRACK, opacity=None, extra=None):
    """Полоска: дорожка и заливка."""
    fill = {"height": f"{height}px", "width": width, "background": color}
    if opacity is not None:
        fill["opacity"] = opacity
    style = {"height": f"{height}px", "background": track}
    style.update(extra or {})
    return html.Div(html.Div(style=fill), style=style)


def _paced_bar(percent_width, pace_left, color, height=12, track=TRACK):
    """Полоса «план → факт» с засечкой ожидаемого темпа.

    Три числа в одной графике: сколько плана, сколько факта и где сейчас
    должен был быть факт, если осваивать ровно.
    """
    return html.Div(
        [
            html.Div(style={"position": "absolute", "left": 0, "top": 0,
                            "bottom": 0, "width": percent_width, "background": color}),
            html.Div(style={"position": "absolute", "top": "-3px", "bottom": "-3px",
                            "left": pace_left, "width": "2px", "background": INK}),
        ],
        style={"position": "relative", "height": f"{height}px", "background": track},
    )


def _status(item, size="11px", dot=7):
    """Плашка статуса: квадратик цветом и подпись."""
    return html.Span(
        [
            html.Span(style={"width": f"{dot}px", "height": f"{dot}px",
                             "background": item["status_color"], "flex": "none"}),
            item["status"],
        ],
        style={"display": "inline-flex", "alignItems": "center", "gap": "6px",
               "fontSize": size, "fontWeight": 700, "letterSpacing": ".05em",
               "textTransform": "uppercase", "color": item["status_color"]},
    )


def _title_row(pace_note=None, right=None):
    """Строка заголовка: «Освоение плана», годы, плашка макетных чисел."""
    children = [
        html.H1("Освоение плана",
                style={"margin": 0, "fontSize": "19px", "fontWeight": 800,
                       "letterSpacing": "-0.015em"}),
        _year_switch(),
        html.Span(
            "Макетные числа",
            title="Разрезов по инструментам в хранилище пока нет — числа из эскиза",
            style={"fontSize": "9.5px", "fontWeight": 700, "letterSpacing": ".1em",
                   "textTransform": "uppercase", "color": "#6a531c",
                   "border": f"1px solid {GOLD}", "padding": "3px 7px"},
        ),
    ]
    if pace_note:
        children.append(html.Div(pace_note, style={"marginLeft": "auto",
                                                   "fontSize": "12px", "color": MUTED}))
    if right is not None:
        children.append(right)
    return html.Div(children, style={"display": "flex", "alignItems": "center",
                                     "gap": "16px"})


def _year_switch():
    """Переключатель годов из макета. В примерах он **не работает**.

    Оставлен нарочно: он часть раскладки, которую и оценивают. Чтобы кнопка
    не выглядела сломанной, про это написано в подсказке при наведении.
    """
    common = {"fontFamily": "inherit", "fontSize": "13px", "padding": "5px 16px",
              "border": "none", "cursor": "default"}
    return html.Div(
        [
            html.Span("2026", style={**common, "fontWeight": 700,
                                     "background": GREEN, "color": "#fff"}),
            html.Span("2025", style={**common, "fontWeight": 500,
                                     "borderLeft": f"1px solid rgba(32,30,29,.4)",
                                     "background": "transparent",
                                     "color": "rgba(32,30,29,.7)"}),
        ],
        title="В примере переключатель не работает — страница для выбора раскладки",
        style={"display": "flex", "border": "1px solid rgba(32,30,29,.4)"},
    )


def _pace_note(items) -> str:
    _, day, total = mockup.expected_pace()
    return f"прошло {day} из {total} дней года · ожидаемый темп {num(items[0]['pace'], 1)} %"


def _card(children, extra=None):
    """Карточка-поверхность дизайн-системы."""
    style = {"background": SURFACE, "boxShadow": SHADOW}
    style.update(extra or {})
    return html.Div(children, style=style)


def _card_head(title, note=None, right=None, size="15px", pad="13px 20px 11px"):
    children = [html.H2(title, style={"margin": 0, "fontSize": size,
                                      "fontWeight": 800, "letterSpacing": "-0.015em"})]
    if note:
        children.append(html.Span(note, style={"fontSize": "12px", "color": MUTED}))
    if right is not None:
        children.append(right)
    return html.Div(children, style={"display": "flex", "alignItems": "center",
                                     "gap": "16px", "padding": pad,
                                     "borderBottom": f"1px solid {DIVIDER}"})


def _legend(long=22, short=12):
    """Легенда разбивки: длинная полоска — суммы, короткая — количества."""
    def one(width, text):
        return html.Span(
            [html.I(style={"width": f"{width}px", "height": "5px",
                           "background": "#8f8b88", "display": "inline-block"}), text],
            style={"display": "flex", "alignItems": "center", "gap": "6px"},
        )
    return html.Div(
        [one(long, "Освоено, млрд ₸"), one(short, "Проектов, шт")],
        style={"marginLeft": "auto", "display": "flex", "alignItems": "center",
               "gap": "16px", "fontSize": "11px", "color": "rgba(32,30,29,.55)"},
    )


def _programs_card(columns, per_row, grid, row_height, font_size,
                   head_size="15px", pad="14px 20px 0"):
    """Разбивка по программам: колонки инструментов со строками программ."""
    body = []
    for column in columns:
        rows = [
            html.Div(
                [
                    html.Span(row["name"], style={
                        "color": "rgba(32,30,29,.8)", "overflow": "hidden",
                        "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                    _bar(row["amount_width"], column["color"], height=6),
                    html.Span(row["amount"], style={
                        "fontWeight": 700, "textAlign": "right",
                        "fontVariantNumeric": "tabular-nums"}),
                    _bar(row["count_width"], column["color"], height=6, opacity=".45"),
                    html.Span(row["count"], style={
                        "textAlign": "right", "color": "rgba(32,30,29,.6)",
                        "fontVariantNumeric": "tabular-nums"}),
                ],
                style={"display": "grid", "gridTemplateColumns": grid,
                       "alignItems": "center", "gap": "8px",
                       "height": f"{row_height}px", "fontSize": font_size},
            )
            for row in column["rows"]
        ]
        body.append(html.Div(
            [
                html.Div(
                    [
                        html.Span(column["short"], style={
                            "fontSize": "10px", "fontWeight": 800,
                            "letterSpacing": ".08em", "textTransform": "uppercase",
                            "color": column["color"]}),
                        html.Span(column["total"], style={
                            "marginLeft": "auto", "fontSize": "13px", "fontWeight": 800,
                            "color": column["color"],
                            "fontVariantNumeric": "tabular-nums"}),
                    ],
                    style={"display": "flex", "alignItems": "baseline", "gap": "8px",
                           "paddingBottom": "8px", "marginBottom": "10px",
                           "borderBottom": f"2px solid {column['color']}"},
                ),
                *rows,
            ],
            style={"padding": pad, "borderRight": f"1px solid {HAIRLINE}"},
        ))

    return _card([
        _card_head("Разбивка по программам", "факт по инструментам",
                   _legend(), size=head_size),
        html.Div(body, style={"display": "grid",
                              "gridTemplateColumns": f"repeat({per_row},1fr)",
                              "padding": "0 4px 12px"}),
    ])


# ──────────────────────── Пример 1 · ровная сетка ────────────────────────

GRID_1 = "236px 132px 128px 1fr 158px 96px 232px 116px"


def _example_1():
    items = _instruments()
    head = html.Div(
        [html.Div(t, style={"textAlign": a}) for t, a in [
            ("Инструмент", "left"), ("Факт, млрд ₸", "right"),
            ("Выполнение", "right"), ("План → факт, засечка = ожидаемый темп", "left"),
            ("Проекты факт / план", "right"), ("Уникальных", "right"),
            ("Динамика Фев → Июл", "left"), ("Статус", "right"),
        ]],
        style={"display": "grid", "gridTemplateColumns": GRID_1, "alignItems": "end",
               "gap": "0 16px", "padding": "12px 20px 8px", "fontSize": "9.5px",
               "fontWeight": 700, "letterSpacing": ".09em", "textTransform": "uppercase",
               "color": PALE, "borderBottom": f"1px solid {HAIRLINE}"},
    )

    rows = []
    for it in items:
        rows.append(html.Div(
            [
                html.Div([
                    html.Span(style={"width": "4px", "height": "30px",
                                     "background": it["color"], "flex": "none"}),
                    html.Div([
                        html.Div(it["title"], style={"fontSize": "15px",
                                                     "fontWeight": 700,
                                                     "letterSpacing": "-0.01em"}),
                        html.Div(f"план {num(it['plan'])} млрд ₸",
                                 style={"fontSize": "11.5px", "color": MUTED}),
                    ]),
                ], style={"display": "flex", "alignItems": "center", "gap": "10px"}),
                html.Div(html.Span(num(it["fact"]), style={
                    "fontSize": "24px", "fontWeight": 800, "letterSpacing": "-0.02em",
                    "fontVariantNumeric": "tabular-nums"}), style={"textAlign": "right"}),
                html.Div([
                    html.Div(f"{num(it['percent'], 1)} %", style={
                        "fontSize": "17px", "fontWeight": 800, "color": it["color"],
                        "fontVariantNumeric": "tabular-nums"}),
                    html.Div(it["gap_short"], style={"fontSize": "11px",
                                                     "color": it["status_color"],
                                                     "fontWeight": 600}),
                ], style={"textAlign": "right"}),
                html.Div([
                    _paced_bar(f"{min(it['percent'], 100):.1f}%",
                               f"{it['pace']:.1f}%", it["color"], height=14),
                    html.Div([html.Span("0"), html.Span(f"{num(it['plan'])} млрд ₸")],
                             style={"display": "flex", "justifyContent": "space-between",
                                    "marginTop": "4px", "fontSize": "10.5px",
                                    "color": PALE}),
                ]),
                html.Div([
                    html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}",
                             style={"fontSize": "15px", "fontWeight": 600,
                                    "fontVariantNumeric": "tabular-nums"}),
                    _bar(f"{it['projects_percent']:.1f}%", it["color"],
                         extra={"marginTop": "5px"}),
                ], style={"textAlign": "right"}),
                html.Div(num(it["unique"]), style={
                    "textAlign": "right", "fontSize": "15px", "fontWeight": 600,
                    "color": "rgba(32,30,29,.75)", "fontVariantNumeric": "tabular-nums"}),
                html.Div([
                    html.Img(src=examples.spark(it["dynamics"], it["color"], 232, 34),
                             style={"display": "block", "width": "232px",
                                    "height": "34px"}),
                    html.Div([
                        html.Span(num(it["dynamics"][0])),
                        html.Span(num(it["fact"]), style={"fontWeight": 700,
                                                          "color": "rgba(32,30,29,.7)"}),
                    ], style={"display": "flex", "justifyContent": "space-between",
                              "marginTop": "3px", "fontSize": "10px", "color": PALE,
                              "fontVariantNumeric": "tabular-nums"}),
                ]),
                html.Div(_status(it), style={"textAlign": "right"}),
            ],
            style={"display": "grid", "gridTemplateColumns": GRID_1,
                   "alignItems": "center", "gap": "0 16px", "padding": "14px 20px",
                   "borderBottom": f"1px solid {HAIRLINE}"},
        ))

    return [
        _card([
            html.Div(
                [
                    html.H1("Освоение плана", style={
                        "margin": 0, "fontSize": "19px", "fontWeight": 800,
                        "letterSpacing": "-0.015em"}),
                    _year_switch(),
                    html.Div([
                        html.Div(_pace_note(items), style={"fontSize": "12px",
                                                           "color": MUTED}),
                        html.Span("Макетные числа", style={
                            "fontSize": "9.5px", "fontWeight": 700,
                            "letterSpacing": ".1em", "textTransform": "uppercase",
                            "color": "#6a531c", "border": f"1px solid {GOLD}",
                            "padding": "3px 7px", "whiteSpace": "nowrap"}),
                    ], style={"marginLeft": "auto", "display": "flex",
                              "alignItems": "center", "gap": "14px"}),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "16px",
                       "padding": "14px 20px 12px",
                       "borderBottom": f"1px solid {DIVIDER}"},
            ),
            head,
            *rows,
        ]),
        _programs_card(_programs([TOTAL, GREEN, GOLD, OLIVE]), 4,
                       "1fr 56px 40px 44px 30px", 22, "12px", pad="14px 16px 0"),
    ]


# ───────────────────── Пример 2 · иерархия с полосой-итогом ─────────────────────

def _example_2():
    items = _instruments()
    hero, tiles = items[0], items[1:]

    def hero_cell(label, value, extra=None):
        return html.Div([
            _kicker(label, "rgba(255,255,255,.5)"),
            html.Div(value, style={"fontSize": "20px", "fontWeight": 700,
                                   "marginTop": "4px",
                                   "fontVariantNumeric": "tabular-nums"}),
            *(extra or []),
        ])

    band = html.Div(
        [
            html.Div([
                _kicker("Все инструменты", "#dcb862", "10px",
                        {"letterSpacing": ".11em", "fontWeight": 800}),
                html.Div([
                    html.Span(num(hero["percent"], 1), style={
                        "fontSize": "46px", "fontWeight": 800,
                        "letterSpacing": "-0.03em", "lineHeight": 1,
                        "fontVariantNumeric": "tabular-nums"}),
                    html.Span("%", style={"fontSize": "22px", "fontWeight": 600,
                                          "color": "rgba(255,255,255,.6)"}),
                ], style={"display": "flex", "alignItems": "baseline", "gap": "8px",
                          "marginTop": "6px"}),
                html.Div("от годового плана", style={"fontSize": "11.5px",
                                                     "color": "rgba(255,255,255,.66)",
                                                     "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div([
                    html.Span(["Факт ",
                               html.B(num(hero["fact"]), style={"color": "#fff",
                                                                "fontSize": "15px"}),
                               f" из {num(hero['plan'])} млрд ₸"]),
                    html.Span(f"засечка — ожидаемый темп {num(hero['pace'], 1)} %"),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "alignItems": "baseline", "fontSize": "12px",
                          "color": "rgba(255,255,255,.66)", "marginBottom": "7px"}),
                html.Div([
                    html.Div(style={"position": "absolute", "left": 0, "top": 0,
                                    "bottom": 0,
                                    "width": f"{min(hero['percent'], 100):.1f}%",
                                    "background": "#5aab78"}),
                    html.Div(style={"position": "absolute", "top": "-4px",
                                    "bottom": "-4px", "left": f"{hero['pace']:.1f}%",
                                    "width": "2px", "background": "#fff"}),
                ], style={"position": "relative", "height": "22px",
                          "background": "rgba(255,255,255,.16)"}),
                html.Div([
                    html.Span(style={"width": "7px", "height": "7px",
                                     "background": "#5aab78"}),
                    html.Span(hero["gap_short"], style={"fontWeight": 700,
                                                        "color": "#a9d9bd"}),
                    html.Span("от ожидаемого темпа",
                              style={"color": "rgba(255,255,255,.5)"}),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px",
                          "marginTop": "7px", "fontSize": "12px"}),
            ]),
            hero_cell(
                "Проекты факт / план",
                f"{num(hero['projects_fact'])} / {num(hero['projects_plan'])}",
                [
                    _bar(f"{hero['projects_percent']:.1f}%", "#dcb862",
                         track="rgba(255,255,255,.16)", extra={"marginTop": "6px"}),
                    html.Div(f"выполнение {num(hero['projects_percent'], 1)} %",
                             style={"fontSize": "11px",
                                    "color": "rgba(255,255,255,.55)",
                                    "marginTop": "5px"}),
                ],
            ),
            hero_cell("Уникальных", num(hero["unique"]), [
                html.Div(f"из {num(hero['projects_fact'])} проектов",
                         style={"fontSize": "11px", "color": "rgba(255,255,255,.55)",
                                "marginTop": "11px"}),
            ]),
            html.Div([
                html.Div([
                    html.Span("Проектов за месяц, шт"),
                    html.Span(f"за год {num(sum(hero['projects_by_month']))}",
                              style={"color": "rgba(255,255,255,.75)"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "fontSize": "9.5px", "fontWeight": 700,
                          "letterSpacing": ".09em", "textTransform": "uppercase",
                          "color": "rgba(255,255,255,.5)", "marginBottom": "4px"}),
                html.Img(src=examples.spark(hero["projects_by_month"], "#a9d9bd",
                                            260, 44, fill_opacity=0.32, stroke=2),
                         style={"display": "block", "width": "100%", "height": "44px"}),
                html.Div([html.Span(m, style={"flex": 1, "textAlign": "center"})
                          for m in mockup.MONTHS7],
                         style={"display": "flex", "marginTop": "3px",
                                "fontSize": "10px", "color": "rgba(255,255,255,.45)"}),
            ]),
        ],
        style={"background": TOTAL, "color": "#fff", "display": "grid",
               "gridTemplateColumns": "250px 1fr 190px 132px 260px",
               "alignItems": "center", "gap": "28px", "padding": "20px 24px"},
    )

    cards = []
    for it in tiles:
        cards.append(html.Div([
            html.Div([
                html.Span(it["title"], style={"fontSize": "14px", "fontWeight": 800,
                                              "letterSpacing": "-0.01em"}),
                html.Span(_status(it, "10.5px"), style={"marginLeft": "auto"}),
            ], style={"display": "flex", "alignItems": "center", "gap": "10px",
                      "padding": "12px 18px 10px",
                      "borderBottom": f"1px solid rgba(32,30,29,.14)"}),
            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.Span(num(it["percent"], 1), style={
                                "fontSize": "38px", "fontWeight": 800,
                                "letterSpacing": "-0.03em", "lineHeight": 1,
                                "color": it["color"],
                                "fontVariantNumeric": "tabular-nums"}),
                            html.Span("%", style={"fontSize": "17px", "fontWeight": 600,
                                                  "color": it["color"], "opacity": .65}),
                        ], style={"display": "flex", "alignItems": "baseline",
                                  "gap": "5px"}),
                        html.Div("от плана", style={"fontSize": "11px", "color": MUTED,
                                                    "marginTop": "3px"}),
                    ]),
                    html.Div([
                        html.Div(num(it["fact"]), style={
                            "fontSize": "22px", "fontWeight": 800,
                            "letterSpacing": "-0.02em",
                            "fontVariantNumeric": "tabular-nums"}),
                        html.Div(f"из {num(it['plan'])} млрд ₸",
                                 style={"fontSize": "11px", "color": MUTED}),
                    ], style={"marginLeft": "auto", "textAlign": "right"}),
                ], style={"display": "flex", "alignItems": "flex-end", "gap": "16px"}),
                html.Div(_paced_bar(f"{min(it['percent'], 100):.1f}%",
                                    f"{it['pace']:.1f}%", it["color"]),
                         style={"marginTop": "12px"}),
                html.Div([
                    html.Div([
                        _kicker("Проекты факт / план"),
                        html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}",
                                 style={"fontSize": "16px", "fontWeight": 700,
                                        "marginTop": "3px",
                                        "fontVariantNumeric": "tabular-nums"}),
                        _bar(f"{it['projects_percent']:.1f}%", it["color"],
                             extra={"marginTop": "5px"}),
                    ]),
                    html.Div([
                        _kicker("Уникальных"),
                        html.Div(num(it["unique"]), style={
                            "fontSize": "16px", "fontWeight": 700, "marginTop": "3px",
                            "fontVariantNumeric": "tabular-nums"}),
                        html.Div(f"выполнение {num(it['projects_percent'], 1)} %",
                                 style={"fontSize": "10.5px", "color": PALE,
                                        "marginTop": "6px"}),
                    ]),
                ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                          "gap": "16px", "marginTop": "14px", "paddingTop": "12px",
                          "borderTop": f"1px solid {HAIRLINE}"}),
                html.Div([
                    html.Div([
                        html.Span("Проектов за месяц, шт"),
                        html.Span(f"за год {num(sum(it['projects_by_month']))}",
                                  style={"fontSize": "12px",
                                         "color": "rgba(32,30,29,.75)"}),
                    ], style={"display": "flex", "justifyContent": "space-between",
                              "alignItems": "baseline", "fontSize": "9.5px",
                              "fontWeight": 700, "letterSpacing": ".09em",
                              "textTransform": "uppercase", "color": PALE,
                              "marginBottom": "6px"}),
                    html.Img(src=examples.spark(it["projects_by_month"], it["color"],
                                                380, 40, stroke=2),
                             style={"display": "block", "width": "100%",
                                    "height": "40px"}),
                    html.Div([
                        html.Span([m, " ", html.B(num(v), style={
                            "color": "rgba(32,30,29,.75)",
                            "fontVariantNumeric": "tabular-nums"})],
                            style={"flex": 1, "textAlign": "center"})
                        for m, v in zip(mockup.MONTHS7, it["projects_by_month"])
                    ], style={"display": "flex", "marginTop": "4px",
                              "fontSize": "10px", "color": PALE}),
                ], style={"marginTop": "14px", "paddingTop": "12px",
                          "borderTop": f"1px solid {HAIRLINE}"}),
            ], style={"padding": "14px 18px 16px"}),
        ], style={"background": SURFACE, "boxShadow": SHADOW,
                  "borderTop": f"3px solid {it['color']}"}))

    return [
        _title_row(),
        band,
        html.Div(cards, style={"display": "grid",
                               "gridTemplateColumns": "repeat(3,1fr)", "gap": "14px"}),
        _programs_card(_programs([TOTAL, GREEN, GOLD, OLIVE])[1:], 3,
                       "1fr 90px 42px 60px 32px", 23, "12.5px"),
    ]


# ──────────────────────── Пример 3 · два столбца ────────────────────────

GRID_3 = "1fr 108px 118px 92px"


def _example_3():
    items = _instruments()

    head = html.Div(
        [html.Div(t, style={"textAlign": a}) for t, a in [
            ("Инструмент · план → факт", "left"), ("Проекты", "right"),
            ("Уникальных", "right"), ("Динамика", "right"),
        ]],
        style={"display": "grid", "gridTemplateColumns": GRID_3, "gap": "0 14px",
               "padding": "13px 20px 9px", "fontSize": "9.5px", "fontWeight": 700,
               "letterSpacing": ".09em", "textTransform": "uppercase", "color": PALE,
               "borderBottom": f"1px solid {DIVIDER}"},
    )

    rows = []
    for it in items:
        rows.append(html.Div(
            [
                html.Div([
                    html.Div([
                        html.Span(style={"width": "4px", "height": "16px",
                                         "background": it["color"],
                                         "alignSelf": "center", "flex": "none"}),
                        html.Span(it["title"], style={"fontSize": "15px",
                                                      "fontWeight": 700,
                                                      "letterSpacing": "-0.01em"}),
                        html.Span(f"{num(it['percent'], 1)} %", style={
                            "fontSize": "20px", "fontWeight": 800, "color": it["color"],
                            "letterSpacing": "-0.02em",
                            "fontVariantNumeric": "tabular-nums"}),
                        html.Span(it["gap_short"], style={"fontSize": "11px",
                                                          "fontWeight": 600,
                                                          "color": it["status_color"]}),
                        html.Span([
                            html.B(num(it["fact"]), style={
                                "fontSize": "17px", "fontWeight": 800, "color": INK,
                                "letterSpacing": "-0.02em"}),
                            f" из {num(it['plan'])} млрд ₸",
                        ], style={"marginLeft": "auto", "fontSize": "12px",
                                  "color": "rgba(32,30,29,.55)"}),
                    ], style={"display": "flex", "alignItems": "baseline", "gap": "10px",
                              "marginBottom": "9px"}),
                    _paced_bar(f"{min(it['percent'], 100):.1f}%",
                               f"{it['pace']:.1f}%", it["color"], height=13),
                ]),
                html.Div([
                    html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}",
                             style={"fontSize": "14px", "fontWeight": 700,
                                    "fontVariantNumeric": "tabular-nums"}),
                    _bar(f"{it['projects_percent']:.1f}%", it["color"],
                         extra={"marginTop": "5px"}),
                    html.Div(f"{num(it['projects_percent'], 1)} %",
                             style={"fontSize": "10.5px", "color": PALE,
                                    "marginTop": "4px"}),
                ], style={"textAlign": "right"}),
                html.Div([
                    html.Div(num(it["unique"]), style={
                        "fontSize": "14px", "fontWeight": 700,
                        "fontVariantNumeric": "tabular-nums"}),
                    html.Div(f"из {num(it['projects_fact'])}",
                             style={"fontSize": "10.5px", "color": PALE,
                                    "marginTop": "4px"}),
                ], style={"textAlign": "right"}),
                html.Div([
                    html.Img(src=examples.spark(it["dynamics"], it["color"], 92, 30),
                             style={"display": "block", "width": "92px",
                                    "height": "30px"}),
                    html.Div([html.Span("Фев"), html.Span("Июл")],
                             style={"display": "flex",
                                    "justifyContent": "space-between",
                                    "marginTop": "3px", "fontSize": "9.5px",
                                    "color": "rgba(32,30,29,.4)"}),
                    html.Div(it["status"], style={
                        "marginTop": "5px", "fontSize": "10.5px", "fontWeight": 700,
                        "letterSpacing": ".05em", "textTransform": "uppercase",
                        "color": it["status_color"], "textAlign": "right"}),
                ]),
            ],
            style={"display": "grid", "gridTemplateColumns": GRID_3, "gap": "0 14px",
                   "padding": "15px 20px", "borderBottom": f"1px solid {HAIRLINE}",
                   "alignItems": "center"},
        ))

    columns = _programs([TOTAL, GREEN, GOLD, OLIVE])
    programs = _card([
        html.Div([
            html.H2("Разбивка по программам", style={
                "margin": 0, "fontSize": "13px", "fontWeight": 800,
                "letterSpacing": "-0.015em"}),
            _legend(18, 10),
        ], style={"display": "flex", "alignItems": "center", "gap": "12px",
                  "padding": "13px 20px 9px", "borderBottom": f"1px solid {DIVIDER}"}),
        html.Div(
            [html.Div([
                html.Div([
                    html.Span(col["short"], style={
                        "fontSize": "9.5px", "fontWeight": 800, "letterSpacing": ".08em",
                        "textTransform": "uppercase", "color": col["color"]}),
                    html.Span(col["total"], style={
                        "marginLeft": "auto", "fontSize": "12px", "fontWeight": 800,
                        "color": col["color"], "fontVariantNumeric": "tabular-nums"}),
                ], style={"display": "flex", "alignItems": "baseline", "gap": "8px",
                          "paddingBottom": "7px", "marginBottom": "8px",
                          "borderBottom": f"2px solid {col['color']}"}),
                *[html.Div([
                    html.Span(r["name"], style={"color": "rgba(32,30,29,.8)",
                                                "overflow": "hidden",
                                                "textOverflow": "ellipsis",
                                                "whiteSpace": "nowrap"}),
                    _bar(r["amount_width"], col["color"], height=6),
                    html.Span(r["amount"], style={"fontWeight": 700,
                                                  "textAlign": "right",
                                                  "fontVariantNumeric": "tabular-nums"}),
                    _bar(r["count_width"], col["color"], height=6, opacity=".45"),
                    html.Span(r["count"], style={"textAlign": "right",
                                                 "color": "rgba(32,30,29,.6)",
                                                 "fontVariantNumeric": "tabular-nums"}),
                ], style={"display": "grid",
                          "gridTemplateColumns": "1fr 46px 36px 34px 28px",
                          "alignItems": "center", "gap": "7px", "height": "21px",
                          "fontSize": "11.5px"}) for r in col["rows"]],
            ], style={"padding": "12px 16px 4px",
                      "borderRight": f"1px solid {HAIRLINE}"}) for col in columns],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                   "padding": "0 4px 12px"},
        ),
    ])

    return [
        _title_row(pace_note=_pace_note(items) + " — засечка на полосах"),
        html.Div([
            _card([head, *rows]),
            programs,
        ], style={"display": "grid", "gridTemplateColumns": "1fr 620px", "gap": "14px",
                  "alignItems": "start", "marginTop": "14px"}),
    ]


# ─────────────────── Пример 4 · компактные шкалы и карта ───────────────────

def _example_4():
    items = _instruments()

    cards = []
    for i, it in enumerate(items):
        values = it["dynamics"]
        low, high = min(values), max(values)
        spread = (high - low) or 1
        bars = [
            html.Div([
                html.Div(style={"width": "100%", "background": it["color"],
                                "height": f"{16 + 30 * (v - low) / spread:.0f}px",
                                "opacity": 1 if j == len(values) - 1
                                else 0.45 + 0.4 * j / (len(values) - 1)}),
                html.Span(m, style={"fontSize": "10px", "color": PALE}),
            ], style={"flex": 1, "display": "flex", "flexDirection": "column",
                      "alignItems": "center", "gap": "4px"})
            for j, (m, v) in enumerate(zip(mockup.MONTHS, values))
        ]

        cards.append(html.Div([
            html.Div([
                html.Span(it["title"], style={"fontSize": "13.5px", "fontWeight": 800,
                                              "letterSpacing": "-0.01em"}),
                html.Span(_status(it, "10px", 6), style={"marginLeft": "auto"}),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px",
                      "padding": "11px 16px 9px",
                      "borderBottom": f"1px solid rgba(32,30,29,.14)"}),
            html.Div([
                html.Div([
                    html.Div([
                        html.Img(src=examples.gauge(it["percent"], it["pace"],
                                                    it["color"]),
                                 style={"display": "block", "width": "120px",
                                        "height": "68px"}),
                        html.Div("0 · 100 %", style={
                            "textAlign": "center", "fontSize": "10px",
                            "fontWeight": 700, "color": PALE, "letterSpacing": ".08em",
                            "marginTop": "-6px"}),
                    ], style={"flex": "none"}),
                    html.Div([
                        html.Div([
                            html.Span(num(it["percent"], 1), style={
                                "fontSize": "34px", "fontWeight": 800,
                                "letterSpacing": "-0.03em", "lineHeight": 1,
                                "color": it["color"],
                                "fontVariantNumeric": "tabular-nums"}),
                            html.Span("%", style={"fontSize": "16px", "fontWeight": 600,
                                                  "color": it["color"], "opacity": .65}),
                        ], style={"display": "flex", "alignItems": "baseline",
                                  "gap": "4px"}),
                        html.Div("от плана", style={"fontSize": "11px", "color": MUTED,
                                                    "marginTop": "3px"}),
                        html.Div(it["gap_short"], style={
                            "fontSize": "11.5px", "fontWeight": 700,
                            "color": it["status_color"], "marginTop": "5px"}),
                    ], style={"minWidth": 0}),
                ], style={"display": "flex", "alignItems": "center", "gap": "14px"}),
                html.Div([
                    html.Div([_kicker("Факт"),
                              html.Div(num(it["fact"]), style={
                                  "fontSize": "20px", "fontWeight": 800,
                                  "letterSpacing": "-0.02em",
                                  "fontVariantNumeric": "tabular-nums"})]),
                    html.Div([_kicker("План"),
                              html.Div(num(it["plan"]), style={
                                  "fontSize": "20px", "fontWeight": 600, "color": PALE,
                                  "letterSpacing": "-0.02em",
                                  "fontVariantNumeric": "tabular-nums"})],
                             style={"textAlign": "right"}),
                    html.Div("млрд ₸", style={"fontSize": "10.5px", "color": PALE,
                                              "alignSelf": "flex-end"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "alignItems": "baseline", "marginTop": "12px",
                          "paddingTop": "11px", "borderTop": f"1px solid {HAIRLINE}"}),
                html.Div([
                    html.Div([
                        _kicker("Проекты ф/п"),
                        html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}",
                                 style={"fontSize": "14px", "fontWeight": 700,
                                        "marginTop": "3px",
                                        "fontVariantNumeric": "tabular-nums"}),
                        _bar(f"{it['projects_percent']:.1f}%", it["color"],
                             extra={"marginTop": "5px"}),
                        html.Div(f"{num(it['projects_percent'], 1)} %",
                                 style={"fontSize": "10px", "color": PALE,
                                        "marginTop": "4px"}),
                    ]),
                    html.Div([
                        _kicker("Уникальных"),
                        html.Div(num(it["unique"]), style={
                            "fontSize": "14px", "fontWeight": 700, "marginTop": "3px",
                            "fontVariantNumeric": "tabular-nums"}),
                        html.Div(f"из {num(it['projects_fact'])}",
                                 style={"fontSize": "10px", "color": PALE,
                                        "marginTop": "10px"}),
                    ]),
                ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                          "gap": "12px", "marginTop": "12px", "paddingTop": "11px",
                          "borderTop": f"1px solid {HAIRLINE}"}),
                html.Div([
                    html.Div([
                        html.Span("Динамика"),
                        html.Span(f"{num(values[0])} → {num(it['fact'])}",
                                  style={"color": "rgba(32,30,29,.7)"}),
                    ], style={"display": "flex", "justifyContent": "space-between",
                              "fontSize": "9.5px", "fontWeight": 700,
                              "letterSpacing": ".09em", "textTransform": "uppercase",
                              "color": PALE, "marginBottom": "7px"}),
                    html.Div(bars, style={"display": "flex", "alignItems": "flex-end",
                                          "gap": "5px", "height": "46px"}),
                ], style={"marginTop": "12px", "paddingTop": "11px",
                          "borderTop": f"1px solid {HAIRLINE}"}),
            ], style={"padding": "12px 16px 14px"}),
        ], style={"background": SURFACE,
                  "boxShadow": "0 3px 10px rgba(45,43,43,.16)" if i == 0 else SHADOW,
                  "borderTop": f"3px solid {it['color']}", "display": "flex",
                  "flexDirection": "column"}))

    return [
        _title_row(pace_note=_pace_note(items) + " — засечка на шкале"),
        html.Div(cards, style={"display": "grid",
                               "gridTemplateColumns": "repeat(4,1fr)", "gap": "14px"}),
        _card([
            _card_head(
                "Освоение по регионам", "картограмма по показателю «Освоено бюджета»",
                html.Div([
                    html.Span("Настоящие данные", style={
                        "fontSize": "9.5px", "fontWeight": 700, "letterSpacing": ".1em",
                        "textTransform": "uppercase", "color": "#185f3d",
                        "border": f"1px solid {GREEN}", "padding": "3px 7px",
                        "whiteSpace": "nowrap"}),
                ], style={"marginLeft": "auto"}),
            ),
            html.Div(_map_block(), style={"padding": "14px 20px 18px"}),
        ]),
    ]


def _map_block():
    """Настоящая картограмма — единственное живое место среди примеров.

    Строится прямо здесь, без коллбэка: примеры не слушают фильтры, а год
    берётся самый свежий из загруженных. Коллбэк ради неизменной картинки
    только добавил бы запрос на каждое открытие страницы.
    """
    try:
        years = data.get_years()
    except Exception as e:                     # хранилища нет — честная строка
        log.warning("карта в примере не построилась: %s", e)
        return dbc.Alert("Карта появится после первого прогона ETL.",
                         color="light", className="border")
    figure = charts.build("map", MAP_INDICATOR, years[0], None, height=420)
    return dbc.Spinner(dbc.Card(
        dash.dcc.Graph(figure=figure, config={"displayModeBar": False},
                       style={"height": "420px"}),
        class_name="border-0 bg-transparent",
    ), color="secondary")


# ──────────────────────────── реестр примеров ────────────────────────────

#: Кто строит какой пример. Описания (номер, название, пояснение) лежат
#: в `core/examples.py` — их спрашивают ещё список и меню в шапке,
#: а сюда им ходить нельзя (см. комментарий там же).
BUILDERS = {
    "1": _example_1,
    "2": _example_2,
    "3": _example_3,
    "4": _example_4,
}


def layout(key: str | None = None, **kwargs):
    """Один пример целиком. Ключ приходит из адреса `/explore/<key>`."""
    example = examples.by_key(key) if key else None
    if example is None or example["key"] not in BUILDERS:
        return dbc.Alert(
            ["Такого примера нет. ",
             dash.dcc.Link("Вернуться к списку", href="/explore")],
            color="warning", className="m-4",
        )

    return dbc.Container(
        [
            html.Div(
                [
                    html.H2(example["title"], className="mt-4 mb-0"),
                    html.Span(f"вариант {example['source']} из макета",
                              className="text-muted small"),
                    html.Div(
                        dash.dcc.Link("← все примеры", href="/explore",
                                      className="small"),
                        className="ms-auto",
                    ),
                ],
                className="d-flex align-items-baseline gap-3",
            ),
            html.P(example["note"], className="text-muted small mb-3"),
            html.Div(BUILDERS[example["key"]](),
                     style={"display": "flex", "flexDirection": "column",
                            "gap": "14px"}),
        ],
        fluid=True,
        className="pb-5",
    )
