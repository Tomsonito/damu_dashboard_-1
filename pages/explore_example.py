"""Страницы-примеры раскладки: «Разбор» → Пример 1…5.

!! **Это временные страницы под выбор дизайна.** Пользователь нарисовал
в Claude Design варианты того, как может выглядеть разбор показателей,
и попросил перенести каждый отдельной страницей, чтобы посмотреть их вживую
и выбрать. Лишние потом удаляются, выбранный переезжает в обычную страницу.

Что где:

| Страница | Из макета | Про что вариант |
|---|---|---|
| Пример 1 | 1a | ровная сетка: четыре инструмента строками таблицы |
| Пример 3 | 1c | два столбца: инструменты слева, все программы справа |
| Пример 4 | 1d | шкалы-полукруги (SVG вместо Plotly) и настоящая карта |
| Пример 5 | — | доработка третьего: год квадратиками, тёмная тема |

Пятый **не из макета** (04.08.2026): это третий, переделанный по замечаниям
пользователя. Сам третий при этом не тронут — варианты сравнивают рядом,
и правка одного ради другого лишила бы сравнение смысла.

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
from datetime import date

import dash
import dash_bootstrap_components as dbc
from dash import html

from core import charts, data, examples, mockup
from core.examples import (DIVIDER, GOLD, GREEN, HAIRLINE, INK, LATE, MUTED,
                           PALE, SHADOW, SURFACE, TEAL, TOTAL, TRACK, num)

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
            html.Span("2026", id="damu-btn-2026", style={**common, "fontWeight": 700,
                                     "background": GREEN, "color": "#fff", "cursor": "pointer"}),
            html.Span("2025", id="damu-btn-2025", style={**common, "fontWeight": 500,
                                     "borderLeft": "1px solid var(--damu-divider)",
                                     "background": "transparent",
                                     "color": "var(--damu-muted)", "cursor": "pointer"}),
        ],
        id="damu-year-toggle",
        title="Нажмите для переключения года",
        style={"display": "flex", "border": "1px solid var(--damu-divider)"},
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
        _programs_card(_programs([TOTAL, GREEN, GOLD, TEAL]), 4,
                       "1fr 56px 40px 44px 30px", 22, "12px", pad="14px 16px 0"),
    ]


# ──────────────────────── Пример 3 · два столбца ────────────────────────

GRID_3 = "1fr 160px auto"


def _example_3():
    items = _instruments()
    
    ink = "var(--damu-ink)"
    muted = "var(--damu-muted)"
    divider = "var(--damu-divider)"
    hairline = "var(--damu-hairline)"
    surface = "var(--damu-surface)"
    track = "var(--damu-track, #e2e0df)"

    head = html.Div(
        [
            html.Div("Инструмент · план → факт", style={"flex": 1, "textAlign": "left"}),
            html.Div([
                html.Span("Проекты", style={"marginRight": "10px"}),
                html.Span("Показать динамику ▾", id="damu-dyn-toggle", n_clicks=0,
                           style={"fontSize": "10px", "fontWeight": 600, "letterSpacing": "normal",
                                  "textTransform": "none", "color": ink,
                                  "background": "rgba(128,128,128,0.1)", "padding": "4px 12px",
                                  "borderRadius": "12px", "cursor": "pointer", "verticalAlign": "middle"}),
            ], className="damu-proj-col", style={"textAlign": "right"}),
        ],
        style={"display": "flex", "gap": "16px",
               "padding": "12px 20px 8px", "fontSize": "11px", "fontWeight": 700,
               "letterSpacing": ".09em", "textTransform": "uppercase", "color": muted,
               "borderBottom": f"1px solid {divider}"},
    )

    def make_rows(is_2025=False):
        rows = []
        for it in items:
            ratio = it["unique"] / max(it["projects_fact"], 1)
            
            if is_2025:
                months_labels = mockup.MONTHS12
                proj_data = it["projects_by_month_full"]
            else:
                months_labels = mockup.MONTHS
                proj_data = it["projects_by_month"]
                
            unique_by_month = [int(v * ratio) for v in proj_data]
            max_proj = max(proj_data) or 1
            
            proj_dyn = [
                html.Div([
                    html.Div([
                        html.Div(style={"height": f"{max(2, (v - u) / max_proj * 32)}px", "background": it["color"], "opacity": 0.3, "borderRadius": "2px 2px 0 0"}),
                        html.Div(style={"height": f"{max(2, u / max_proj * 32)}px", "background": it["color"], "borderRadius": "0 0 2px 2px"}),
                    ], style={"display": "flex", "flexDirection": "column", "justifyContent": "flex-end", "width": "16px", "margin": "0 auto"}),
                    html.Div(num(v), style={"fontSize": "10.5px", "fontWeight": 700, "color": ink, "marginTop": "3px", "lineHeight": 1}),
                    html.Div(num(u), style={"fontSize": "9.5px", "color": muted, "lineHeight": 1, "marginTop": "2px"}),
                    html.Div(m, style={"fontSize": "8.5px", "color": muted, "textTransform": "uppercase", "marginTop": "3px"})
                ], style={"display": "flex", "flexDirection": "column", "alignItems": "center", "justifyContent": "flex-end"})
                for m, v, u in zip(months_labels, proj_data, unique_by_month)
            ]
            
            row_content = html.Div([
                html.Div([
                    # LEFT COLUMN (Money)
                    html.Div([
                        html.Div([
                            html.Span(it["title"], style={"borderLeft": f"4px solid {it['color']}", "paddingLeft": "10px", "fontSize": "16px", "fontWeight": 700, "color": ink, "letterSpacing": "-0.01em", "whiteSpace": "nowrap"}),
                            html.Span([
                                html.B(num(it["fact"]), style={"fontSize": "18px", "fontWeight": 800, "color": ink, "letterSpacing": "-0.02em"}),
                                html.Span(f" из {num(it['plan'])} млрд ₸", style={"color": muted, "marginLeft": "6px", "whiteSpace": "nowrap"}),
                            ], style={"marginLeft": "auto", "fontSize": "13.5px", "background": "var(--damu-surface)", "padding": "6px 14px", "borderRadius": "30px", "display": "flex", "alignItems": "baseline", "boxShadow": "0 1px 4px rgba(0,0,0,0.08)", "whiteSpace": "nowrap"}),
                        ], style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "6px"}),
                        
                        html.Div([
                            _paced_bar(f"{min(it['percent'], 100):.1f}%", f"{it['pace']:.1f}%", it["color"], height=14, track=track),
                            html.Div(
                                html.Div(f"{num(it['percent'], 1)}%", 
                                         style={"position": "absolute", "right": 0, "transform": "translateX(50%)", "fontSize": "14px", "fontWeight": 700, "color": it["color"], "fontVariantNumeric": "tabular-nums", "marginTop": "4px", "whiteSpace": "nowrap"}),
                                style={"position": "relative", "width": f"{min(it['percent'], 100):.1f}%", "height": "22px"}
                            )
                        ])
                    ], style={"flex": 1, "padding": "14px 0", "minWidth": 0}),
                    
                    # RIGHT COLUMN (Projects)
                    html.Div([
                        # Default state: count + bar + unique
                        html.Div([
                            html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}", style={"fontSize": "15px", "fontWeight": 700, "color": ink, "fontVariantNumeric": "tabular-nums", "textAlign": "right"}),
                            _bar(f"{it['projects_percent']:.1f}%", it["color"], height=6, track="rgba(128,128,128,0.15)", extra={"marginTop": "8px"}),
                            html.Div(f"Уникальных: {num(it['unique'])}", style={"fontSize": "11px", "color": muted, "marginTop": "6px", "textAlign": "right"}),
                        ], className="damu-proj-default"),
                        
                        # Dynamics state
                        html.Div([
                            html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}", style={"fontSize": "13px", "fontWeight": 700, "color": ink, "fontVariantNumeric": "tabular-nums", "textAlign": "right", "marginBottom": "8px"}),
                            html.Div(proj_dyn, style={"display": "flex", "justifyContent": "flex-end", "gap": "20px" if not is_2025 else "10px"}),
                            html.Div(f"Уникальных: {num(it['unique'])}", style={"fontSize": "10px", "color": muted, "marginTop": "6px", "textAlign": "right"}),
                        ], className="damu-proj-dynamics"),
                    ], className="damu-proj-col", style={"--dyn-target-width": f"{max(220, 100 + len(months_labels) * (26 if not is_2025 else 22))}px", "padding": "14px 0", "borderLeft": f"1px solid {hairline}", "paddingLeft": "20px"})
                    
                ], style={"display": "flex", "gap": "20px", "padding": "0 20px", "borderBottom": f"1px solid {hairline}"})
            ])
            
            rows.append(row_content)
        
        if rows:
            rows[-1].children[0].style["borderBottom"] = "none"
            
        return rows
        
    rows_2026 = html.Div(make_rows(is_2025=False), id="damu-rows-2026")
    rows_2025 = html.Div(make_rows(is_2025=True), id="damu-rows-2025", style={"display": "none"})

    columns = _programs([TOTAL, GREEN, GOLD, TEAL])
    
    legend = html.Div([
        html.Span([html.I(style={"width": "24px", "height": "5px", "background": "#8f8b88", "display": "inline-block"}), "Освоено, млрд ₸"], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
        html.Span([html.I(style={"width": "14px", "height": "5px", "background": "#8f8b88", "display": "inline-block"}), "Проектов, шт"], style={"display": "flex", "alignItems": "center", "gap": "6px"})
    ], style={"marginLeft": "auto", "display": "flex", "alignItems": "center", "gap": "16px", "fontSize": "12px", "color": muted})

    programs = html.Div([
        html.Div([
            html.H2("Разбивка по программам", style={
                "margin": 0, "fontSize": "15px", "fontWeight": 800, "color": ink,
                "letterSpacing": "-0.015em"}),
            legend,
        ], style={"display": "flex", "alignItems": "center", "gap": "12px",
                  "padding": "14px 20px 10px", "borderBottom": f"1px solid {divider}"}),
        html.Div(
            [html.Div([
                html.Div([
                    html.Span(col["short"], style={
                        "fontSize": "11px", "fontWeight": 800, "letterSpacing": ".08em",
                        "textTransform": "uppercase", "color": col["color"]}),
                    html.Span(col["total"], style={
                        "marginLeft": "auto", "fontSize": "14px", "fontWeight": 800,
                        "color": col["color"], "fontVariantNumeric": "tabular-nums"}),
                ], style={"display": "flex", "alignItems": "baseline", "gap": "8px",
                          "paddingBottom": "8px", "marginBottom": "10px",
                          "borderBottom": f"2px solid {col['color']}"}),
                *[html.Div([
                    html.Span(r["name"], style={"color": ink,
                                                "overflow": "hidden",
                                                "textOverflow": "ellipsis",
                                                "whiteSpace": "nowrap"}),
                    _bar(r["amount_width"], col["color"], height=6, track=track),
                    html.Span(r["amount"], style={"fontWeight": 700, "color": ink,
                                                  "textAlign": "right",
                                                  "fontVariantNumeric": "tabular-nums"}),
                    _bar(r["count_width"], col["color"], height=6, opacity=".45", track=track),
                    html.Span(r["count"], style={"textAlign": "right",
                                                 "color": muted,
                                                 "fontVariantNumeric": "tabular-nums"}),
                ], style={"display": "grid",
                          "gridTemplateColumns": "1fr 50px 42px 38px 34px",
                          "alignItems": "center", "gap": "8px", "height": "24px",
                          "fontSize": "12.5px"}) for r in col["rows"]],
            ], style={"padding": "14px 18px 4px",
                      "borderRight": f"1px solid {hairline}"}) for col in columns],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                   "padding": "0 4px 14px"},
        ),
    ], style={"background": surface, "boxShadow": SHADOW, "color": ink})

    return [
        _title_row(),
        html.Div([
            html.Div([
                head,
                html.Div([rows_2026, rows_2025], style={"display": "flex", "flexDirection": "column", "justifyContent": "space-evenly", "flex": 1})
            ], style={"background": surface, "boxShadow": SHADOW, "color": ink, "height": "100%", "display": "flex", "flexDirection": "column"}),
            html.Div(programs.children, style={"background": surface, "boxShadow": SHADOW, "color": ink, "height": "100%"})
        ], style={"display": "grid", "gridTemplateColumns": "1fr 640px", "gap": "14px",
                  "marginTop": "14px"}),
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


# ─────────────── Пример 5 · доработка примера 3 ───────────────
#
# Состав тот же, что в примере 3, — ничего не убрано. Отличий четыре,
# и каждое разбиралось отдельно:
#
# 1. с полосы убрана засечка ожидаемого темпа (просьба пользователя);
# 2. год показан двенадцатью клетками прямо в свёрнутом виде, а кнопка
#    «Показать динамику» осталась и по-прежнему раскрывает подробности;
# 3. процент вынесен в свою колонку — в примере 3 он едет за краем
#    заливки, и четыре числа стоят на четырёх разных местах;
# 4. цвета, поверхности и текст взяты переменными темы, поэтому пример
#    читается и в тёмной теме.
#
# Пример 3 при этом НЕ ТРОГАЕТСЯ: варианты сравнивают рядом, и правка
# одного ради другого лишила бы сравнение смысла.

#: Класс строки кладёт цвет инструмента в переменную `--ex5-k`, а полоса,
#: клетки и подписи внутри берут её оттуда. Значения (и пара «светлый /
#: тёмный») — в `assets/custom.css`, блок «Пример 5»: тему выбирают
#: в браузере, и вписать её в inline-стиль из Python нечем.
EX5_CLASS = {"all": "damu-ex5-c1", "guarantee": "damu-ex5-c2",
             "credit": "damu-ex5-c3", "subsidy": "damu-ex5-c4"}

#: Колонки разбивки по программам идут в том же порядке, что и инструменты.
EX5_PROG_CLASS = ["damu-ex5-c1", "damu-ex5-c2", "damu-ex5-c3", "damu-ex5-c4"]

#: Цвет читается из переменной, которую положил класс, а не пишется значением.
EX5_K = "var(--ex5-k)"

#: Поверхность карточки: тень в тёмной теме превращается в `none`
#: (переменная так и задана), а глубину там даёт волосяная рамка.
EX5_CARD = {"background": "var(--damu-surface)", "color": "var(--damu-ink)",
            "boxShadow": "var(--damu-shadow-sm)",
            "border": "1px solid var(--damu-hairline)"}


def _ex5_cells(months: list[int]) -> html.Div:
    """Год двенадцатью клетками: прошедшие месяцы цветом, будущие рамкой.

    Плотность цвета — сколько проектов в месяце относительно самого сильного
    месяца ЭТОГО инструмента. Масштаб у каждой строки свой: субсидирование
    и кредитование несопоставимы по размеру, и общий масштаб превратил бы
    первое в двенадцать одинаково бледных клеток.

    Нижняя граница плотности 0.28, а не 0: клетка самого слабого месяца
    должна остаться видимой клеткой, иначе «мало» и «ничего» выглядят
    одинаково.

    Будущие месяцы рисуются пустой рамкой, а не пропускаются: иначе
    неполный год выглядел бы как полный, просто короче.
    """
    top = max(months) or 1
    cells, letters = [], []
    for i, name in enumerate(mockup.MONTHS12):
        if i < len(months):
            cells.append(html.Span(
                title=f"{name} — {num(months[i])} проектов",
                style={"flex": 1, "height": "17px", "background": EX5_K,
                       "opacity": round(0.28 + 0.72 * months[i] / top, 2)},
            ))
        else:
            cells.append(html.Span(style={
                "flex": 1, "height": "17px",
                "boxShadow": "inset 0 0 0 1px var(--damu-hairline)"}))
        # Подписан каждый третий месяц: первая буква на всех давала бы
        # «я ф м а м и и а с о н д» — где «м» и «и» встречаются дважды
        letters.append(html.Span(
            name.lower() if i % 3 == 0 else "",
            style={"flex": 1, "textAlign": "center", "fontSize": "8.5px",
                   "fontWeight": 700, "color": "var(--damu-muted)"},
        ))

    return html.Div([
        html.Div(cells, style={"display": "flex", "gap": "3px",
                               "marginTop": "10px"}),
        html.Div(letters, style={"display": "flex", "gap": "3px",
                                 "marginTop": "3px"}),
    ])


def _ex5_dynamics(months: list[int], labels) -> html.Div:
    """Подробная помесячная динамика — то, что раскрывает кнопка."""
    top = max(months) or 1
    columns = [
        html.Div([
            html.Div(style={"height": f"{max(3, v / top * 34):.0f}px",
                            "background": EX5_K, "width": "14px",
                            "margin": "0 auto"}),
            html.Div(num(v), style={"fontSize": "10px", "fontWeight": 700,
                                    "marginTop": "4px", "lineHeight": 1,
                                    "fontVariantNumeric": "tabular-nums"}),
            html.Div(m, style={"fontSize": "8.5px", "marginTop": "3px",
                               "color": "var(--damu-muted)"}),
        ], style={"flex": 1, "display": "flex", "flexDirection": "column",
                  "justifyContent": "flex-end", "textAlign": "center"})
        for m, v in zip(labels, months)
    ]
    return html.Div(columns, style={"display": "flex", "alignItems": "flex-end",
                                    "gap": "6px", "marginTop": "10px"})


def _ex5_row(item: dict, last: bool) -> html.Div:
    """Одна строка инструмента: слева деньги, справа проекты."""
    left = html.Div([
        html.Div([
            html.Span(item["title"], style={
                "borderLeft": f"4px solid {EX5_K}", "paddingLeft": "10px",
                "fontSize": "15px", "fontWeight": 700,
                "letterSpacing": "-0.01em", "whiteSpace": "nowrap"}),
            # Сумма плоским текстом, без пилюли со скруглением и тенью:
            # радиус в дизайн-системе нулевой везде
            html.Span([
                html.B(num(item["fact"]), style={
                    "fontSize": "17px", "fontWeight": 800,
                    "letterSpacing": "-0.02em"}),
                f" из {num(item['plan'])} млрд ₸",
            ], style={"marginLeft": "auto", "fontSize": "13px",
                      "color": "var(--damu-muted)", "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "alignItems": "baseline", "gap": "10px",
                  "marginBottom": "9px"}),
        # Полоса без засечки, процент — в своей колонке, а не за краем
        # заливки: так четыре числа стоят друг под другом.
        #
        # Волосяная рамка обязательна: без неё не видно, где кончается
        # стопроцентная отметка, и полоса выглядит обрывающейся. Задана
        # через outline, а не border: border вошёл бы в высоту (14 -> 16),
        # а outline рисуется поверх и раскладку не двигает
        html.Div([
            _bar(f"{min(item['percent'], 100):.1f}%", EX5_K, height=14,
                 track="var(--damu-track)",
                 extra={"flex": 1, "outline": "1px solid var(--damu-hairline)",
                        "outlineOffset": "-1px"}),
            html.Div(f"{num(item['percent'], 1)} %", style={
                "width": "58px", "textAlign": "right", "fontSize": "14px",
                "fontWeight": 800, "color": EX5_K,
                "fontVariantNumeric": "tabular-nums"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "12px"}),
    ], style={"flex": 1, "minWidth": 0, "padding": "13px 0"})

    counts = f"{num(item['projects_fact'])} / {num(item['projects_plan'])}"
    right = html.Div([
        html.Div([
            html.Div(counts, style={
                "fontSize": "15px", "fontWeight": 700, "textAlign": "right",
                "fontVariantNumeric": "tabular-nums"}),
            _bar(f"{item['projects_percent']:.1f}%", EX5_K, height=6,
                 track="var(--damu-track)", extra={"marginTop": "8px"}),
            html.Div(f"Уникальных: {num(item['unique'])}", style={
                "fontSize": "11px", "color": "var(--damu-muted)",
                "marginTop": "6px", "textAlign": "right"}),
            _ex5_cells(item["months"]),
        ], className="damu-proj-default"),
        html.Div([
            html.Div(counts, style={
                "fontSize": "13px", "fontWeight": 700, "textAlign": "right",
                "fontVariantNumeric": "tabular-nums"}),
            _ex5_dynamics(item["months"], item["month_labels"]),
        ], className="damu-proj-dynamics"),
    ],
        className="damu-proj-col",
        # Формула та же, что в примере 3 (там уже подобрана вживую): базовые
        # 100px под цифры сверху плюс по 26px на месяц, а у года из 12 —
        # по 22px, иначе полоса из двенадцати столбиков просит больше места,
        # чем есть у большинства мониторов
        style={"--dyn-target-width":
               f"{max(240, 100 + len(item['months']) * (26 if len(item['months']) <= 7 else 22))}px",
               "padding": "13px 0 13px 20px",
               "borderLeft": "1px solid var(--damu-hairline)"},
    )

    # minWidth: 0 — без него строка не сжимается вместе с остальными:
    # у flex-элемента по умолчанию минимальная ширина равна ширине его
    # содержимого, и на узком экране раскрытая динамика распирала бы
    # всю страницу вбок вместо того, чтобы ужаться (см. .damu-proj-col
    # в custom.css — там та же правка)
    style = {"display": "flex", "gap": "20px", "padding": "0 20px", "minWidth": 0}
    if not last:
        style["borderBottom"] = "1px solid var(--damu-hairline)"
    return html.Div([left, right], className=EX5_CLASS[item["key"]], style=style)


def _ex5_rows(year: int | None, block_id: str, hidden: bool) -> html.Div:
    """Готовый набор строк за один год.

    Оба года рисуются сразу и переключаются показом/скрытием в браузере —
    так же, как в примере 3. Числа при этом берутся из `mockup.for_year`,
    поэтому переключатель меняет и суммы, а не только набор месяцев.
    """
    items = mockup.for_year(year, expanded=True)
    rows = [_ex5_row(it, last=(i == len(items) - 1)) for i, it in enumerate(items)]
    style = {"display": "none"} if hidden else {}
    return html.Div(rows, id=block_id, style=style)


def _ex5_legend() -> html.Div:
    def one(width, text):
        return html.Span(
            [html.I(style={"width": f"{width}px", "height": "5px",
                           "background": "var(--damu-muted)",
                           "display": "inline-block"}), text],
            style={"display": "flex", "alignItems": "center", "gap": "6px"},
        )
    return html.Div(
        [one(24, "Освоено, млрд ₸"), one(12, "Проектов, шт")],
        style={"marginLeft": "auto", "display": "flex", "alignItems": "center",
               "gap": "16px", "fontSize": "12px", "color": "var(--damu-muted)"},
    )


def _ex5_programs() -> html.Div:
    """Разбивка по программам — тот же состав и та же сетка 2×2.

    Собрана здесь, а не через общий `_programs_card`: тот вписывает цвета
    светлой темы значениями (`rgba(32,30,29,.8)` и подобные), и в тёмной
    теме текст остался бы тёмным на тёмном.
    """
    body = []
    for column, klass in zip(_programs([EX5_K] * 4), EX5_PROG_CLASS):
        rows = [
            html.Div([
                html.Span(row["name"], style={
                    "overflow": "hidden", "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap"}),
                _bar(row["amount_width"], EX5_K, height=6,
                     track="var(--damu-track)"),
                html.Span(row["amount"], style={
                    "fontWeight": 700, "textAlign": "right",
                    "fontVariantNumeric": "tabular-nums"}),
                _bar(row["count_width"], EX5_K, height=6, opacity=".45",
                     track="var(--damu-track)"),
                html.Span(row["count"], style={
                    "textAlign": "right", "color": "var(--damu-muted)",
                    "fontVariantNumeric": "tabular-nums"}),
            ], style={"display": "grid",
                      "gridTemplateColumns": "1fr 50px 42px 38px 34px",
                      "alignItems": "center", "gap": "8px", "height": "24px",
                      "fontSize": "12.5px"})
            for row in column["rows"]
        ]
        body.append(html.Div([
            html.Div([
                html.Span(column["short"], style={
                    "fontSize": "11px", "fontWeight": 800,
                    "letterSpacing": ".08em", "textTransform": "uppercase",
                    "color": EX5_K}),
                html.Span(column["total"], style={
                    "marginLeft": "auto", "fontSize": "14px", "fontWeight": 800,
                    "color": EX5_K, "fontVariantNumeric": "tabular-nums"}),
            ], style={"display": "flex", "alignItems": "baseline", "gap": "8px",
                      "paddingBottom": "8px", "marginBottom": "10px",
                      "borderBottom": f"2px solid {EX5_K}"}),
            *rows,
        ], className=klass, style={"padding": "14px 18px 4px",
                                   "borderRight": "1px solid var(--damu-hairline)"}))

    return html.Div([
        html.Div([
            html.H2("Разбивка по программам", style={
                "margin": 0, "fontSize": "15px", "fontWeight": 800,
                "letterSpacing": "-0.015em"}),
            _ex5_legend(),
        ], style={"display": "flex", "alignItems": "center", "gap": "12px",
                  "padding": "14px 20px 10px",
                  "borderBottom": "1px solid var(--damu-divider)"}),
        html.Div(body, style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                              "padding": "0 4px 14px"}),
    ], style={**EX5_CARD, "height": "100%"})


def _example_5():
    head = html.Div(
        [
            html.Div("Инструмент · план → факт", style={"flex": 1}),
            html.Div([
                html.Span("Проекты", style={"marginRight": "10px"}),
                # Тот же id и те же классы, что в примере 3, — значит
                # работает уже написанный обработчик в assets/dashboard.js.
                # Столкновения нет: страница показывает один пример за раз
                html.Span("Показать динамику ▾", id="damu-dyn-toggle", n_clicks=0,
                          style={"fontSize": "10px", "fontWeight": 600,
                                 "letterSpacing": "normal", "textTransform": "none",
                                 "color": "var(--damu-ink)",
                                 "background": "var(--damu-track)",
                                 "padding": "4px 12px", "cursor": "pointer",
                                 "verticalAlign": "middle"}),
            ], style={"textAlign": "right"}),
        ],
        style={"display": "flex", "gap": "16px", "padding": "12px 20px 8px",
               "fontSize": "11px", "fontWeight": 700, "letterSpacing": ".09em",
               "textTransform": "uppercase", "color": "var(--damu-muted)",
               "borderBottom": "1px solid var(--damu-divider)"},
    )

    this_year = date.today().year
    instruments = html.Div(
        [
            head,
            html.Div(
                [_ex5_rows(None, "damu-rows-2026", hidden=False),
                 _ex5_rows(this_year - 1, "damu-rows-2025", hidden=True)],
                style={"display": "flex", "flexDirection": "column",
                       "justifyContent": "space-evenly", "flex": 1,
                       "minWidth": 0},
            ),
        ],
        # minWidth: 0 обязателен и здесь: это элемент CSS-сетки «1fr 640px»
        # ниже, а элемент сетки по умолчанию не сжимается уже своего
        # содержимого. Без этой строки узкая колонка «1fr» распирается
        # раскрытой динамикой, и вся страница уезжает вбок — тот же приём,
        # что у `.damu-sec-main` на странице раздела
        style={**EX5_CARD, "height": "100%", "display": "flex",
               "flexDirection": "column", "minWidth": 0},
    )

    title = html.Div(
        [
            html.H1("Освоение плана", style={
                "margin": 0, "fontSize": "19px", "fontWeight": 800,
                "letterSpacing": "-0.015em"}),
            _year_switch(),
            html.Span(
                "Макетные числа",
                title="Разрезов по инструментам в хранилище пока нет — числа из эскиза",
                style={"fontSize": "9.5px", "fontWeight": 700,
                       "letterSpacing": ".1em", "textTransform": "uppercase",
                       "color": "var(--damu-muted)",
                       "border": "1px solid var(--damu-hairline)",
                       "padding": "3px 7px"},
            ),
        ],
        style={"display": "flex", "alignItems": "center", "gap": "16px"},
    )

    return [
        title,
        html.Div([instruments, _ex5_programs()],
                 style={"display": "grid", "gridTemplateColumns": "1fr 640px",
                        "gap": "14px", "marginTop": "14px"}),
    ]


# ──────────────────────────── реестр примеров ────────────────────────────

#: Кто строит какой пример. Описания (номер, название, пояснение) лежат
#: в `core/examples.py` — их спрашивают ещё список и меню в шапке,
#: а сюда им ходить нельзя (см. комментарий там же).
BUILDERS = {
    "1": _example_1,
    "3": _example_3,
    "4": _example_4,
    "5": _example_5,
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

    children = []
    # Примеры 3 и 5 показываются во весь экран, без служебного заголовка:
    # их оценивают как готовую страницу, а не как карточку в списке
    if key not in ("3", "5"):
        children.extend([
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
        ])
    
    children.append(
        html.Div(BUILDERS[example["key"]](),
                 style={"display": "flex", "flexDirection": "column",
                        "gap": "14px"})
    )

    return dbc.Container(children, fluid=True, className="pb-5")
