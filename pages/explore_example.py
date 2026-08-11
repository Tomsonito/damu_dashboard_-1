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
            # Словами, а не знаком «+»: в прежней карточке стояло
            # «от плана +27,1 п.п.» — плюс к чему и от чего, приходилось
            # додумывать. Знаковая запись осталась там, где рядом есть
            # подпись, объясняющая её смысл
            "pace_phrase": ("быстрее плана на " if n["on_track"]
                            else "отстаёт от плана на ")
                           + num(abs(n["gap"]), 1) + " п.п.",
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


def _paced_bar(percent_width, color, height=12, track=TRACK):
    """Полоса «план → факт»: дорожка во весь план, заливка по факту.

    !! Засечки ожидаемого темпа здесь НЕТ, хотя параметр `pace_left` до
    07.08.2026 в подписи стоял: сама засечка была убрана раньше (просьба
    пользователя, она же отличает пример 5 от третьего), а параметр остался
    и ничего не делал. Убран, чтобы не выглядел работающим.
    """
    return html.Div(
        [
            html.Div(style={"position": "absolute", "left": 0, "top": 0,
                            "bottom": 0, "width": percent_width, "background": color,
                            "borderRadius": "4px"}),
        ],
        style={"position": "relative", "height": f"{height}px", "background": track,
               "borderRadius": "4px", "boxShadow": "inset 0 0 0 1px rgba(0,0,0,0.06)"},
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


def _mock_badge():
    """Плашка «Макетные числа» — одна на все примеры.

    Цвета взяты переменными второго цвета темы — ровно те же, что у класса
    `.damu-mock-badge` на главной. Раньше здесь стояло `#6a531c` значением,
    и в тёмной теме плашка была тёмно-коричневой на тёмном (тот же промах,
    что чинили на главной 04.08.2026).
    """
    return html.Span(
        "Макетные числа",
        title="Разрезов по инструментам в хранилище пока нет — числа из эскиза",
        style={"fontSize": "8.5px", "fontWeight": 700, "letterSpacing": ".1em",
               "textTransform": "uppercase", "whiteSpace": "nowrap",
               "color": "var(--damu-accent-2-dark, #6a531c)",
               "border": "1px solid var(--damu-accent-2, #b08a2e)",
               "padding": "2px 6px"},
    )


def _title_row(pace_note=None, right=None):
    """Строка заголовка: «Освоение плана», годы, плашка макетных чисел.

    Мелкая нарочно (07.08.2026, просьба пользователя — «сделать меньше,
    как в примере 1»). Заголовок примера — подпись к сравниваемой раскладке,
    а не самостоятельный экран: крупная H1 в 19 px забирала внимание у того,
    ради чего примеры и существуют. Размеры взяты у примера 1, где заголовок
    был мелким с самого начала.
    """
    children = [
        html.H1("Освоение плана",
                style={"margin": 0, "fontSize": "15px", "fontWeight": 900,
                       "letterSpacing": ".05em", "textTransform": "uppercase"}),
        _year_switch(),
        _mock_badge(),
    ]
    if pace_note:
        children.append(html.Div(pace_note, style={"marginLeft": "auto",
                                                   "fontSize": "12px", "color": MUTED}))
    if right is not None:
        children.append(right)
    return html.Div(children, style={"display": "flex", "alignItems": "center",
                                     "gap": "12px"})


def _year_switch():
    """Переключатель годов из макета.

    В примерах 3 и 5 он **работает** (обработчик в `assets/dashboard.js`
    прячет один набор строк и показывает другой), в примерах 1 и 4 — нет:
    там строки нарисованы один раз, и переключать нечего. Оставлен во всех
    четырёх нарочно — он часть раскладки, которую и оценивают.

    Размер мелкий: заголовок примера должен быть подписью, а не вывеской.
    Раньше пример 1 добивался того же, ужимая обычный переключатель через
    `transform: scale(0.8)` — но трансформация уменьшает картинку, а не
    место под неё, и рядом оставалась дырка в четверть ширины.
    """
    common = {"fontFamily": "inherit", "fontSize": "11.5px",
              "padding": "3px 13px", "border": "none", "cursor": "pointer"}
    return html.Div(
        [
            html.Span("2026", id="damu-btn-2026",
                      style={**common, "fontWeight": 700,
                             "background": "var(--damu-accent, #1f7a4d)",
                             "color": "var(--damu-on-accent, #fff)"}),
            html.Span("2025", id="damu-btn-2025",
                      style={**common, "fontWeight": 500,
                             "borderLeft": "1px solid var(--damu-divider)",
                             "background": "transparent",
                             "color": "var(--damu-muted)"}),
        ],
        id="damu-year-toggle",
        title="Нажмите для переключения года",
        style={"display": "flex", "border": "1px solid var(--damu-divider)"},
    )


def _pace_note(items) -> str:
    _, day, total = mockup.expected_pace()
    return f"прошло {day} из {total} дней года · ожидаемый темп {num(items[0]['pace'], 1)} %"


def _card(children, extra=None, klass=None):
    """Карточка-поверхность дизайн-системы."""
    style = {"background": SURFACE, "boxShadow": SHADOW}
    style.update(extra or {})
    return html.Div(children, className=klass, style=style)


def _dyn_toggle(extra=None):
    """Кнопка «Показать динамику» — одна на весь пример.

    !! id и обе подписи те же, что были у примера 3, и это единственное,
    на что смотрит обработчик в `assets/dashboard.js`. Он идёт вверх
    от кнопки до первого предка, внутри которого лежит `.damu-proj-dynamics`,
    вешает на него класс `damu-dyn-open` — и дальше всё делает CSS. Поэтому
    кнопку можно ставить куда угодно: в шапку колонки (пример 1), в заголовок
    страницы (пример 4) или в шапку таблицы (примеры 3 и 5). Своя подпись
    у примера была бы затёрта: текст кнопки при нажатии переписывает JS.
    """
    style = {"fontSize": "10px", "fontWeight": 600, "letterSpacing": "normal",
             "textTransform": "none", "whiteSpace": "nowrap", "cursor": "pointer",
             "color": "var(--damu-ink)", "background": "var(--damu-track)",
             "padding": "4px 12px"}
    style.update(extra or {})
    return html.Span("Показать динамику ▾", id="damu-dyn-toggle", n_clicks=0,
                     style=style)


def _month_bars(values, labels, color, bar_h=34, gap="4px", font="9px"):
    """Столбики по месяцам: число сверху, дорожка со столбиком, месяц снизу.

    Дорожка есть у КАЖДОГО месяца из `labels`, в том числе у ещё не
    наступившего, — у того она просто пустая, а вместо числа прочерк.
    Так неполный год виден как неполный, а не как более короткий: тот же
    приём, что у клеток примера 5. Пропускать будущие месяцы нельзя —
    двенадцать месяцев на экране должны остаться двенадцатью.

    Столбик растёт внутри дорожки, а не сам по себе: у дорожки высота
    постоянная, поэтому строка не скачет от месяца к месяцу и ничего
    не вылезает за отведённое место (в примере 4 до 07.08.2026 столбики
    рисовались высотой до 65 px в коробке высотой 46 и налезали на подпись).
    """
    top = max(values) or 1
    columns = []
    for i, label in enumerate(labels):
        value = values[i] if i < len(values) else None
        bar = (html.Div(style={"height": f"{max(2, round(value / top * bar_h))}px",
                               "background": color})
               if value is not None else None)
        columns.append(html.Div(
            [
                html.Div(num(value) if value is not None else "—",
                         style={"fontSize": font, "fontWeight": 700, "lineHeight": 1,
                                "color": INK if value is not None else PALE,
                                "fontVariantNumeric": "tabular-nums"}),
                html.Div(bar, style={"height": f"{bar_h}px", "marginTop": "4px",
                                     "background": TRACK, "display": "flex",
                                     "flexDirection": "column",
                                     "justifyContent": "flex-end"}),
                html.Div(label, style={"fontSize": font, "lineHeight": 1,
                                       "color": PALE, "marginTop": "4px"}),
            ],
            style={"flex": 1, "minWidth": 0, "textAlign": "center"},
        ))
    return html.Div(columns, style={"display": "flex", "alignItems": "flex-end",
                                    "gap": gap})


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
               "gap": "16px", "fontSize": "11px", "color": MUTED},
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
                        "color": INK, "overflow": "hidden",
                        "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                    _bar(row["amount_width"], column["color"], height=6),
                    html.Span(row["amount"], style={
                        "fontWeight": 700, "textAlign": "right",
                        "fontVariantNumeric": "tabular-nums"}),
                    _bar(row["count_width"], column["color"], height=6, opacity=".45"),
                    html.Span(row["count"], style={
                        "textAlign": "right", "color": MUTED,
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
#
# Ширина колонки «Динамика» лежит в переменной `--dyn-w`, а соседние колонки
# заданы долями (`fr`) с маленьким минимумом. Поэтому при раскрытии динамики
# они сжимаются, и «Факт, млрд ₸» уезжает влево, освобождая место, — то же
# движение, что в примере 5, только там его делает flex, а здесь grid.
#
# Значения переменной (232 px свёрнуто, 340 px раскрыто) — в `custom.css`,
# блок «Пример 1»: их переключает класс `damu-dyn-open`, который вешает
# на карточку общий обработчик кнопки, а он живёт в браузере, не в Python.

GRID_1 = ("minmax(130px,1.15fr) 112px 88px minmax(80px,1fr) "
          "128px 84px var(--dyn-w,232px) 100px")


def _spark_months(values, labels, color, font="10px", label_font="7.5px"):
    """Спарклайн и подписи месяцев под ним: месяц, под ним число.

    Когда подписей БОЛЬШЕ, чем значений (год показан целиком, а закрылись
    не все месяцы), точки ставятся по центрам месячных колонок — тогда
    каждая стоит ровно над своей подписью, а линия честно обрывается там,
    где кончился год. У ненаступивших месяцев вместо числа прочерк.

    Когда подписей столько же, сколько значений, точки стоят от края
    до края, а крайние подписи прижаты к краям — так линия занимает
    всю ширину колонки, как в макете.
    """
    slots = len(labels) if len(labels) != len(values) else None
    columns = []
    for i, label in enumerate(labels):
        value = values[i] if i < len(values) else None
        align = "center"
        if slots is None:
            align = ("left" if i == 0
                     else "right" if i == len(labels) - 1 else "center")
        columns.append(html.Div(
            [
                html.Div(label, style={
                    "fontSize": label_font, "textTransform": "uppercase",
                    "opacity": 0.6, "marginBottom": "2px",
                    "letterSpacing": "0.05em"}),
                html.Div(num(value) if value is not None else "—"),
            ],
            style={"flex": 1, "minWidth": 0, "textAlign": align},
        ))
    return html.Div([
        html.Img(src=examples.spark(values, color, 232, 34, slots=slots),
                 style={"display": "block", "width": "100%", "height": "34px"}),
        html.Div(columns, style={
            "display": "flex", "justifyContent": "space-between",
            "marginTop": "4px", "fontSize": font, "color": PALE,
            "fontVariantNumeric": "tabular-nums", "fontWeight": 600}),
    ])


def _ex1_dynamics(item: dict) -> html.Div:
    """Колонка «Динамика» в двух состояниях: свёрнутом и раскрытом.

    График в обоих один и тот же — спарклайн (просьба пользователя
    07.08.2026: «динамику за 12 месяцев можно оставлять в таком же
    графике»). Меняется только охват: шесть последних закрытых месяцев
    или весь год двенадцатью колонками.
    """
    money = list(item["money_by_month"])
    return html.Div(
        [
            html.Div(_spark_months(money[-6:], mockup.MONTHS7[-6:], item["color"]),
                     className="damu-proj-default"),
            html.Div(_spark_months(money, mockup.MONTHS12, item["color"],
                                   font="9px", label_font="7px"),
                     className="damu-proj-dynamics"),
        ],
        style={"minWidth": 0},
    )


def _example_1():
    items = _instruments()
    head = html.Div(
        [
            *[html.Div(t, style={"textAlign": a}) for t, a in [
                ("Инструмент", "left"), ("Факт, млрд ₸", "right"),
                ("Выполнение", "right"), ("План → факт", "left"),
                ("Проекты факт / план", "right"), ("Уникальных", "right"),
            ]],
            html.Div([html.Span("Динамика"), _dyn_toggle({"marginLeft": "auto"})],
                     style={"display": "flex", "alignItems": "center", "gap": "8px"}),
            html.Div("Статус", style={"textAlign": "right"}),
        ],
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
                        html.Div(it["title"], style={
                            "fontSize": "15px", "fontWeight": 700,
                            "letterSpacing": "-0.01em", "whiteSpace": "nowrap",
                            "overflow": "hidden", "textOverflow": "ellipsis"}),
                        html.Div(f"план {num(it['plan'])} млрд ₸",
                                 style={"fontSize": "11.5px", "color": MUTED,
                                        "whiteSpace": "nowrap"}),
                    ], style={"minWidth": 0}),
                ], style={"display": "flex", "alignItems": "center", "gap": "10px",
                          "minWidth": 0}),
                html.Div(html.Span(num(it["fact"]), style={
                    "fontSize": "23px", "fontWeight": 800, "letterSpacing": "-0.02em",
                    "fontVariantNumeric": "tabular-nums"}), style={"textAlign": "right"}),
                html.Div([
                    html.Div(f"{num(it['percent'], 1)} %", style={
                        "fontSize": "17px", "fontWeight": 800, "color": it["color"],
                        "fontVariantNumeric": "tabular-nums"}),
                ], style={"textAlign": "right"}),
                html.Div([
                    _paced_bar(f"{min(it['percent'], 100):.1f}%", it["color"],
                               height=14),
                    html.Div([html.Span("0"), html.Span(f"{num(it['plan'])} млрд ₸")],
                             style={"display": "flex", "justifyContent": "space-between",
                                    "marginTop": "4px", "fontSize": "10.5px",
                                    "color": PALE, "whiteSpace": "nowrap"}),
                ], style={"minWidth": 0}),
                html.Div([
                    html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}",
                             style={"fontSize": "15px", "fontWeight": 600,
                                    "fontVariantNumeric": "tabular-nums"}),
                    _bar(f"{it['projects_percent']:.1f}%", it["color"],
                         extra={"marginTop": "5px"}),
                ], style={"textAlign": "right"}),
                # Раньше здесь была плашка с заливкой и скруглением: она
                # выбивалась из ряда (радиус в дизайн-системе нулевой везде)
                # и весила больше соседних колонок, хотя число в ней —
                # такое же справочное. Теперь колонка устроена как соседняя:
                # число и мелкая строка «из скольких»
                html.Div([
                    html.Div(num(it["unique"]), style={
                        "fontSize": "15px", "fontWeight": 700,
                        "fontVariantNumeric": "tabular-nums"}),
                    html.Div(f"из {num(it['projects_fact'])}", style={
                        "fontSize": "10.5px", "color": PALE, "marginTop": "3px",
                        "whiteSpace": "nowrap"}),
                ], style={"textAlign": "right"}),
                _ex1_dynamics(it),
                html.Div(_status(it), style={"textAlign": "right"}),
            ],
            style={"display": "grid", "gridTemplateColumns": GRID_1,
                   "alignItems": "center", "gap": "0 16px", "padding": "14px 20px",
                   "borderBottom": f"1px solid {HAIRLINE}"},
            ))

    return [
        _title_row(),
        _card([head, *rows], klass="damu-ex1"),
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
                # !! Здесь стоял список из ШЕСТИ месяцев (Фев–Июл) при семи
                # числах (Янв–Июл). `zip` ниже молча обрезал лишнее — и год
                # выходил подписан со сдвигом на месяц: под «Фев» стояло
                # январское число, июльское не показывалось вовсе. Найдено
                # 07.08.2026, когда шестимесячный список убрали из mockup
                months_labels = mockup.MONTHS7
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
                            _paced_bar(f"{min(it['percent'], 100):.1f}%", it["color"], height=14, track=track),
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


# ─────────────────── Пример 4 · четыре дизайна карточки ───────────────────
#
# 07.08.2026 страница переделана. Пользователь сказал, что карточки
# не нравятся («строка факт план выглядит вообще странно»), и попросил
# показать на этой странице ЧЕТЫРЕ РАЗНЫХ дизайна — чтобы выбрать один.
#
# Поэтому каждая из четырёх карточек оформлена по-своему, а данные в них
# прежние: у каждой свой инструмент. Подпись «Вариант N» стоит в шапке,
# чтобы выбор можно было назвать номером.
#
# Разбор прежней карточки, из которого выросли варианты:
#
# 1. `ФАКТ 540 · ПЛАН 620 · млрд ₸` тремя колонками — единица висела
#    отдельным столбцом и не принадлежала ни одному числу, а план был
#    набран тем же кеглем, только серым, будто это выключенное число того
#    же ранга. Факт и план — одна дробь, и теперь они так и написаны:
#    «540 из 620 млрд ₸» (`_ex4_money`);
# 2. шкала-полукруг рядом с крупным процентом показывала одно и то же
#    число дважды и занимала 120×68 px. Осталась в первом варианте — там
#    она и есть предмет сравнения;
# 3. три процента в карточке (87,1 · +27,1 п.п. · 86,0) не были подписаны —
#    теперь у каждого своя подпись, а разрыв с планом написан словами
#    («быстрее плана на 27,1 п.п.»), а не знаком плюс;
# 4. столбики динамики вылезали за свою коробку (65 px в коробке 46);
# 5. цвета, вписанные значением, в тёмной теме давали тёмное по тёмному.


def _ex4_block(children, first: bool = False):
    """Секция карточки: сверху линия-разделитель, кроме самой первой."""
    style = {} if first else {"marginTop": "12px", "paddingTop": "11px",
                              "borderTop": f"1px solid {HAIRLINE}"}
    return html.Div(children, style=style)


def _ex4_money(item, size="22px"):
    """«540 из 620 млрд ₸» — факт крупно, остальное подписью.

    Единица привязана к числу, а не висит отдельной колонкой, и сразу
    видно, что это одна дробь, а не два независимых показателя. Ровно эта
    строка в прежней карточке и не нравилась пользователю.
    """
    return html.Div([
        html.B(num(item["fact"]), style={
            "fontSize": size, "fontWeight": 800, "letterSpacing": "-0.02em",
            "fontVariantNumeric": "tabular-nums"}),
        html.Span(f"из {num(item['plan'])} млрд ₸", style={
            "fontSize": "12.5px", "color": MUTED, "whiteSpace": "nowrap"}),
    ], style={"display": "flex", "alignItems": "baseline", "gap": "6px"})


def _ex4_metric(label, value, percent, color, extra=None):
    """Строка-показатель: подпись и число, под ними полоска с процентом.

    Один и тот же кирпичик для денег, проектов и уникальных — на нём
    держится четвёртый вариант: три показателя, набранные одинаково,
    сравниваются взглядом без арифметики.
    """
    style = {"display": "flex", "flexDirection": "column", "gap": "5px"}
    style.update(extra or {})
    return html.Div([
        html.Div([
            _kicker(label),
            html.Span(value, style={
                "marginLeft": "auto", "fontSize": "13px", "fontWeight": 700,
                "whiteSpace": "nowrap", "fontVariantNumeric": "tabular-nums"}),
        ], style={"display": "flex", "alignItems": "baseline", "gap": "8px"}),
        html.Div([
            _bar(f"{min(percent, 100):.1f}%", color, height=6, extra={"flex": 1}),
            html.Span(f"{num(percent, 1)} %", style={
                "width": "44px", "textAlign": "right", "fontSize": "10px",
                "color": PALE, "fontVariantNumeric": "tabular-nums"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px"}),
    ], style=style)


def _year_cells(values, color, height=16):
    """Год двенадцатью клетками: плотность цвета — доля от лучшего месяца.

    Тот же приём, что в примере 5, но цвет здесь приходит значением:
    у примера 5 он едет переменной темы, а карточки этой страницы взяты
    из макета вместе со своей палитрой. Ненаступившие месяцы — пустая
    рамка, иначе неполный год выглядел бы как полный, просто короче.

    Нижняя граница плотности 0.28: клетка самого слабого месяца должна
    остаться видимой клеткой, иначе «мало» и «ничего» выглядят одинаково.
    """
    top = max(values) or 1
    cells, letters = [], []
    for i, name in enumerate(mockup.MONTHS12):
        if i < len(values):
            cells.append(html.Span(
                title=f"{name} — {num(values[i])} млрд ₸",
                style={"flex": 1, "height": f"{height}px", "background": color,
                       "opacity": round(0.28 + 0.72 * values[i] / top, 2)}))
        else:
            cells.append(html.Span(style={
                "flex": 1, "height": f"{height}px",
                "boxShadow": f"inset 0 0 0 1px {HAIRLINE}"}))
        # Подписан каждый третий месяц: первая буква на всех дала бы
        # «я ф м а м и и а с о н д», где «м» и «и» встречаются дважды
        letters.append(html.Span(
            name.lower() if i % 3 == 0 else "",
            style={"flex": 1, "textAlign": "center", "fontSize": "8.5px",
                   "fontWeight": 700, "color": PALE}))
    return html.Div([
        html.Div(cells, style={"display": "flex", "gap": "3px", "marginTop": "8px"}),
        html.Div(letters, style={"display": "flex", "gap": "3px", "marginTop": "3px"}),
    ])


def _ex4_dyn(item, kind="bars"):
    """Динамика в двух состояниях: шесть месяцев и весь год.

    Оба состояния лежат в разметке сразу, показ переключает общая кнопка
    (`_dyn_toggle`) через классы `damu-proj-default` / `damu-proj-dynamics`.
    Вид графика — часть дизайна варианта, поэтому он здесь параметром.
    """
    money = list(item["money_by_month"])
    # Пары «96 → 335» в подписи нет намеренно: она называла первый и последний
    # месяц ГОДА, а в свёрнутом виде показаны последние шесть — числа
    # не сходились с картинкой. Все значения и так подписаны под графиком
    head = html.Div("Динамика, млрд ₸",
                    style={"fontSize": "9.5px", "fontWeight": 700,
                           "letterSpacing": ".09em", "textTransform": "uppercase",
                           "color": PALE, "marginBottom": "7px"})

    if kind == "spark":
        short = _spark_months(money[-6:], mockup.MONTHS7[-6:], item["color"],
                              font="9px")
        full = _spark_months(money, mockup.MONTHS12, item["color"],
                             font="7.5px", label_font="6.5px")
    elif kind == "cells":
        short = _year_cells(money, item["color"])
        full = _month_bars(money, mockup.MONTHS12, item["color"],
                           bar_h=32, gap="2px", font="8.5px")
    else:
        short = _month_bars(money[-6:], mockup.MONTHS7[-6:], item["color"],
                            bar_h=32, gap="5px", font="9.5px")
        full = _month_bars(money, mockup.MONTHS12, item["color"],
                           bar_h=32, gap="2px", font="8.5px")

    return [head,
            html.Div(short, className="damu-proj-default"),
            html.Div(full, className="damu-proj-dynamics")]


def _ex4_pace(item, extra=None):
    """Отставание или опережение — словами, а не знаком «+»."""
    style = {"fontSize": "11px", "fontWeight": 600, "color": item["status_color"]}
    style.update(extra or {})
    return html.Div(item["pace_phrase"], style=style)


# ── Вариант 1 · шкала ──
# Ближе всех к прежней карточке: шкала на месте, но строка денег
# переписана одной фразой, а подписи получили все три числа.

def _ex4_v1(it):
    return [
        _ex4_block([
            html.Div([
                html.Img(src=examples.gauge(it["percent"], it["pace"], it["color"]),
                         style={"display": "block", "width": "108px",
                                "height": "61px", "flex": "none"}),
                html.Div([
                    html.Div([
                        html.Span(num(it["percent"], 1), style={
                            "fontSize": "29px", "fontWeight": 800, "lineHeight": 1,
                            "letterSpacing": "-0.03em", "color": it["color"],
                            "fontVariantNumeric": "tabular-nums"}),
                        html.Span("%", style={
                            "fontSize": "15px", "fontWeight": 600,
                            "color": it["color"], "opacity": .65}),
                    ], style={"display": "flex", "alignItems": "baseline",
                              "gap": "3px"}),
                    html.Div("освоено от плана", style={
                        "fontSize": "10px", "color": PALE, "marginTop": "3px"}),
                    _ex4_pace(it, {"marginTop": "6px"}),
                ], style={"minWidth": 0}),
            ], style={"display": "flex", "alignItems": "center", "gap": "12px"}),
        ], first=True),
        _ex4_block([
            _ex4_money(it),
            _bar(f"{min(it['percent'], 100):.1f}%", it["color"], height=8,
                 extra={"marginTop": "8px"}),
        ]),
        _ex4_block([
            html.Div([
                html.Div([
                    _kicker("Проектов"),
                    html.Div(f"{num(it['projects_fact'])} / {num(it['projects_plan'])}",
                             style={"fontSize": "14px", "fontWeight": 700,
                                    "marginTop": "3px",
                                    "fontVariantNumeric": "tabular-nums"}),
                ]),
                html.Div([
                    _kicker("Из них уникальных"),
                    html.Div(num(it["unique"]), style={
                        "fontSize": "14px", "fontWeight": 700, "marginTop": "3px",
                        "fontVariantNumeric": "tabular-nums"}),
                ], style={"textAlign": "right"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "gap": "12px"}),
        ]),
        _ex4_block(_ex4_dyn(it, "bars")),
    ]


# ── Вариант 2 · полоса ──
# Без шкалы: главное здесь деньги, а не процент. Процент стоит справа
# от полосы — там же, где она кончается, и читается как её подпись.

def _ex4_v2(it):
    return [
        _ex4_block([
            _ex4_money(it, size="30px"),
            html.Div([
                _bar(f"{min(it['percent'], 100):.1f}%", it["color"], height=14,
                     extra={"flex": 1, "outline": f"1px solid {HAIRLINE}",
                            "outlineOffset": "-1px"}),
                html.Div(f"{num(it['percent'], 1)} %", style={
                    "width": "54px", "textAlign": "right", "fontSize": "14px",
                    "fontWeight": 800, "color": it["color"],
                    "fontVariantNumeric": "tabular-nums"}),
            ], style={"display": "flex", "alignItems": "center", "gap": "10px",
                      "marginTop": "11px"}),
            _ex4_pace(it, {"marginTop": "7px"}),
        ], first=True),
        _ex4_block([
            _ex4_metric("Проектов, шт",
                        f"{num(it['projects_fact'])} из {num(it['projects_plan'])}",
                        it["projects_percent"], it["color"]),
            _ex4_metric("Уникальных из них",
                        f"{num(it['unique'])} из {num(it['projects_fact'])}",
                        it["unique"] / max(it["projects_fact"], 1) * 100,
                        it["color"], extra={"marginTop": "11px"}),
        ]),
        _ex4_block(_ex4_dyn(it, "spark")),
    ]


# ── Вариант 3 · крупный процент ──
# Процент занимает всю верхнюю часть, остальное уходит в строгую таблицу
# «подпись → значение»: числа выстроены по правому краю и сравниваются
# сверху вниз. Год — клетками, как в примере 5.

def _ex4_v3(it):
    rows = [
        ("Факт", f"{num(it['fact'])} млрд ₸"),
        ("План", f"{num(it['plan'])} млрд ₸"),
        ("Проектов", f"{num(it['projects_fact'])} / {num(it['projects_plan'])}"),
        ("Уникальных", num(it["unique"])),
    ]
    return [
        _ex4_block([
            html.Div([
                html.Span(num(it["percent"], 1), style={
                    "fontSize": "42px", "fontWeight": 800, "lineHeight": 1,
                    "letterSpacing": "-0.04em", "color": it["color"],
                    "fontVariantNumeric": "tabular-nums"}),
                html.Span("%", style={"fontSize": "18px", "fontWeight": 600,
                                      "color": it["color"], "opacity": .6}),
            ], style={"display": "flex", "alignItems": "baseline", "gap": "4px"}),
            html.Div("освоено от плана", style={
                "fontSize": "10px", "color": PALE, "marginTop": "3px"}),
            _bar(f"{min(it['percent'], 100):.1f}%", it["color"], height=10,
                 extra={"marginTop": "10px"}),
            _ex4_pace(it, {"marginTop": "7px"}),
        ], first=True),
        _ex4_block([
            html.Div([
                html.Span(label, style={"color": MUTED}),
                html.Span(value, style={
                    "marginLeft": "auto", "fontWeight": 700, "whiteSpace": "nowrap",
                    "fontVariantNumeric": "tabular-nums"}),
            ], style={"display": "flex", "alignItems": "baseline", "gap": "8px",
                      "fontSize": "12.5px", "height": "23px"})
            for label, value in rows
        ]),
        _ex4_block(_ex4_dyn(it, "cells")),
    ]


# ── Вариант 4 · три полосы ──
# Крупного числа нет вовсе, и это осознанно: три показателя набраны
# одинаково и стоят друг под другом, поэтому сравниваются взглядом —
# и между собой, и с такой же карточкой соседнего инструмента.

def _ex4_v4(it):
    return [
        _ex4_block([
            _ex4_metric("Освоено, млрд ₸",
                        f"{num(it['fact'])} из {num(it['plan'])}",
                        it["percent"], it["color"]),
            _ex4_metric("Проектов, шт",
                        f"{num(it['projects_fact'])} из {num(it['projects_plan'])}",
                        it["projects_percent"], it["color"],
                        extra={"marginTop": "12px"}),
            _ex4_metric("Уникальных из них",
                        f"{num(it['unique'])} из {num(it['projects_fact'])}",
                        it["unique"] / max(it["projects_fact"], 1) * 100,
                        it["color"], extra={"marginTop": "12px"}),
            _ex4_pace(it, {"marginTop": "11px"}),
        ], first=True),
        _ex4_block(_ex4_dyn(it, "bars")),
    ]


#: Название варианта и то, чем он собран. Порядок — порядок карточек
#: в ряду, то есть номер варианта совпадает с номером инструмента.
EX4_VARIANTS = [
    ("Шкала", _ex4_v1),
    ("Полоса", _ex4_v2),
    ("Крупный процент", _ex4_v3),
    ("Три полосы", _ex4_v4),
]


def _ex4_card(item, number: int, name: str, body):
    """Общая оболочка: цветная черта, номер варианта, название, статус."""
    return html.Div(
        [
            html.Div([
                _kicker(f"Вариант {number} · {name}"),
                html.Div([
                    html.Span(item["title"], style={
                        "fontSize": "13.5px", "fontWeight": 800,
                        "letterSpacing": "-0.01em"}),
                    html.Span(_status(item, "10px", 6),
                              style={"marginLeft": "auto"}),
                ], style={"display": "flex", "alignItems": "center", "gap": "8px",
                          "marginTop": "4px"}),
            ], style={"padding": "10px 16px 9px",
                      "borderBottom": f"1px solid {HAIRLINE}"}),
            html.Div(body, style={"padding": "12px 16px 14px", "flex": 1}),
        ],
        style={"background": SURFACE, "boxShadow": SHADOW,
               "borderTop": f"3px solid {item['color']}",
               "display": "flex", "flexDirection": "column"},
    )


def _example_4():
    items = _instruments()
    cards = [
        _ex4_card(it, i + 1, name, build(it))
        for i, (it, (name, build)) in enumerate(zip(items, EX4_VARIANTS))
    ]

    return [
        # Кнопка одна на все четыре карточки: обработчик вешает класс
        # на общего предка, и раскрываются они разом. Ставить кнопку
        # в каждую карточку значило бы четыре одинаковых id на странице
        _title_row(right=_dyn_toggle({"marginLeft": "auto"})),
        html.Div(
            "Четыре варианта оформления одной и той же карточки — данные "
            "в них настоящие для этой страницы, отличается только подача. "
            "Выбранный вариант потом останется один на все инструменты.",
            style={"fontSize": "12px", "color": MUTED, "marginTop": "-4px"},
        ),
        html.Div(cards, style={"display": "grid",
                               "gridTemplateColumns": "repeat(4,1fr)", "gap": "14px",
                               "alignItems": "stretch"}),
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


#: Сетка строки программ в примере 5 — как была.
EX5_PROG_GRID = "1fr 50px 42px 38px 34px"

#: Сетка той же строки в примере 6: как на главной после правок
#: 10.08.2026 — пары «полоса + своё число» и пустая колонка-разделитель
#: между ними. Ячейки под числа «в притык», чтобы правое выравнивание
#: не отодвигало короткие числа от своей полосы.
EX6_PROG_GRID = "minmax(0,1fr) minmax(48px,1fr) 30px 8px minmax(34px,0.55fr) 26px"


def _ex5_programs(per_row: int = 2, with_all: bool = True,
                  grid: str = EX5_PROG_GRID, gap: str = "8px",
                  spacer: bool = False) -> html.Div:
    """Разбивка по программам — тот же состав и та же сетка 2×2.

    Собрана здесь, а не через общий `_programs_card`: тот вписывает цвета
    светлой темы значениями (`rgba(32,30,29,.8)` и подобные), и в тёмной
    теме текст остался бы тёмным на тёмном.

    Разложить иначе просит пример 6: в развёрнутом виде карточка едет вниз
    во всю ширину, и колонки встают в один ряд по три — без «Всех
    инструментов», их числа там уже стоят в полосе-итоге.
    """
    columns = list(zip(_programs([EX5_K] * 4), EX5_PROG_CLASS))
    if not with_all:
        columns = columns[1:]

    def cells(row):
        out = [
            html.Span(row["name"], style={
                "overflow": "hidden", "textOverflow": "ellipsis",
                "whiteSpace": "nowrap"}),
            _bar(row["amount_width"], EX5_K, height=6,
                 track="var(--damu-track)"),
            html.Span(row["amount"], style={
                "fontWeight": 700, "textAlign": "right",
                "fontVariantNumeric": "tabular-nums"}),
        ]
        # Пустая колонка между парами — она и делает группировку: зазор
        # внутри пары втрое меньше, чем между парами, и число перестаёт
        # висеть равноудалённо от двух полос
        if spacer:
            out.append(html.Span())
        out += [
            _bar(row["count_width"], EX5_K, height=6, opacity=".45",
                 track="var(--damu-track)"),
            html.Span(row["count"], style={
                "textAlign": "right", "color": "var(--damu-muted)",
                "fontVariantNumeric": "tabular-nums"}),
        ]
        return out

    body = []
    for column, klass in columns:
        rows = [
            html.Div(cells(row),
                     style={"display": "grid", "gridTemplateColumns": grid,
                            "alignItems": "center", "columnGap": gap,
                            "height": "24px", "fontSize": "12.5px"})
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
        html.Div(body, style={"display": "grid",
                              "gridTemplateColumns": f"repeat({per_row}, 1fr)",
                              "padding": "0 4px 14px"}),
    ], style={**EX5_CARD, "height": "100%"})


def _ex5_body():
    """Тело примера 5 без заголовка страницы.

    Вынесено отдельно ради примера 6: там ровно этот же сжатый вид лежит
    первым состоянием, а собственный заголовок у него один на оба
    состояния. Копировать раскладку было нельзя — сравнивают именно её,
    и две копии разъехались бы после первой же правки.
    """
    head = html.Div(
        [
            html.Div("Инструмент · план → факт", style={"flex": 1}),
            html.Div([
                html.Span("Проекты", style={"marginRight": "10px"}),
                # Кнопка общая на все примеры (`_dyn_toggle`): id и подписи
                # те же, что были в примере 3, — значит работает уже
                # написанный обработчик в assets/dashboard.js. Столкновения
                # нет: страница показывает один пример за раз
                _dyn_toggle({"verticalAlign": "middle"}),
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

    return html.Div([instruments, _ex5_programs()],
                    style={"display": "grid", "gridTemplateColumns": "1fr 640px",
                           "gap": "14px", "marginTop": "14px"})


def _example_5():
    return [
        # Заголовок общий с примерами 1, 3 и 4 (`_title_row`) — мелкий,
        # чтобы не спорить с раскладкой, которую и сравнивают
        _title_row(),
        _ex5_body(),
    ]


# ────────── Пример 6 · пример 5, разворачивающийся в главную ──────────
#
# Один экран в двух состояниях. Свёрнутое — ровно пример 5 (та же функция
# `_ex5_body`, не копия). Развёрнутое — раскладка главной: полоса-итог,
# три большие карточки, программы во всю ширину внизу.
#
# `!!` **Оба состояния лежат в разметке сразу, переключает их браузер**
# по атрибуту `data-mode` на обёртке `#damu-ex6`. Коллбэком было бы проще
# написать, но тогда каждое нажатие шло бы на сервер и возвращало новое
# дерево — а перерисованный узел анимировать нечем: браузеру не с чем
# сравнивать. Тот же довод, по которому в проекте вообще сделана подсветка
# вкладок в JS.
#
# `!!` **Цвета взяты у примера 5** (`--ex5-k` через `EX5_CLASS`), а не
# у главной. Так задумано: в анимации важно, чтобы глаз узнал те же данные
# в новой раскладке, а смена цвета на полпути читалась бы как «показали
# что-то другое».
#
# Анимация — CSS: `grid-template-rows: 0fr -> 1fr` плюс проявление
# блоков друг за другом. Правила лежат в `custom.css`, блок «Пример 6»;
# высоту никто не измеряет и не подставляет числом — потому и не ломается
# от количества строк.


def _ex6_toggle():
    """Кнопка разворота. Текст переписывает JS — как у `_dyn_toggle`."""
    return html.Button("Развернуть как на главной ▾", id="damu-ex6-toggle",
                       className="damu-ex6-toggle", n_clicks=0)


def _ex6_metric(kicker, value, extra_value=None, note=None, bar=None):
    """Колонка полосы-итога: метка, число, полоса, примечание."""
    children = [_kicker(kicker, color="rgba(255,255,255,.5)")]
    children.append(html.Div(
        [html.B(value, style={"fontSize": "20px", "fontWeight": 800,
                              "letterSpacing": "-0.02em"}),
         html.Span(extra_value, style={"fontSize": "12px",
                                       "color": "rgba(255,255,255,.66)"})
         if extra_value else None],
        style={"display": "flex", "alignItems": "baseline", "gap": "6px",
               "marginTop": "4px", "fontVariantNumeric": "tabular-nums"}))
    if bar is not None:
        children.append(html.Div(bar, style={"marginTop": "8px"}))
    if note:
        children.append(html.Div(note, style={"fontSize": "11px", "marginTop": "6px",
                                              "color": "rgba(255,255,255,.62)"}))
    return html.Div(children)


def _ex6_band(item: dict) -> html.Div:
    """Полоса-итог «Все инструменты» — как на главной.

    Колонки выровнены ПО ВЕРХУ: строк в них разное число, и центрирование
    поднимало бы короткие колонки над длинными (та же правка, что сделана
    на главной 10.08.2026).
    """
    track = "rgba(255,255,255,.16)"
    white = "#ffffff"
    unique_share = item["unique"] / max(item["projects_fact"], 1) * 100
    return html.Div(
        [
            html.Div([
                _kicker("Все инструменты", color="#d9b871"),
                html.Div([
                    html.Span(num(item["percent"], 1), style={
                        "fontSize": "44px", "fontWeight": 800,
                        "letterSpacing": "-0.03em", "lineHeight": 1}),
                    html.Span("%", style={"fontSize": "20px", "fontWeight": 600,
                                          "color": "rgba(255,255,255,.6)"}),
                ], style={"display": "flex", "alignItems": "baseline", "gap": "6px",
                          "marginTop": "6px"}),
                html.Div("от годового плана", style={
                    "fontSize": "11px", "marginTop": "6px",
                    "color": "rgba(255,255,255,.62)"}),
            ]),
            _ex6_metric("Освоено, млрд ₸", num(item["fact"]),
                        f"из {num(item['plan'])} млрд ₸",
                        bar=_paced_bar(f"{min(item['percent'], 100):.1f}%", white,
                                       height=12, track=track)),
            _ex6_metric("Проекты факт / план",
                        f"{num(item['projects_fact'])} / {num(item['projects_plan'])}",
                        note=f"выполнение {num(item['projects_percent'], 1)} %",
                        bar=_bar(f"{item['projects_percent']:.1f}%", "#d9b871",
                                 height=6, track=track)),
            _ex6_metric("Состав проектов", num(item["unique"]), "уникальных",
                        note=f"{num(item['repeat'])} повторных",
                        bar=html.Div([
                            html.Div(style={"width": f"{unique_share:.1f}%",
                                            "background": white}),
                            # Штриховка, а не второй цвет: повторные —
                            # не отдельная категория, а «остальное»
                            html.Div(style={
                                "flex": 1,
                                "background": "repeating-linear-gradient(135deg,"
                                              "rgba(255,255,255,.5) 0,"
                                              "rgba(255,255,255,.5) 2px,"
                                              "transparent 2px,transparent 4px)"}),
                        ], style={"display": "flex", "height": "6px", "gap": "2px"})),
            html.Div([
                html.Div([
                    html.Span("Проектов за месяц, шт"),
                    html.Span(f"за год {num(item['months_total'])}", style={
                        "color": "rgba(255,255,255,.75)"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "fontSize": "9.5px", "fontWeight": 700,
                          "letterSpacing": ".09em", "textTransform": "uppercase",
                          "color": "rgba(255,255,255,.5)", "marginBottom": "6px"}),
                _month_bars(item["months"], item["month_labels"], "#d9b871",
                            bar_h=40, font="9px"),
            ]),
        ],
        style={"background": TOTAL, "color": "#ffffff", "display": "grid",
               "gridTemplateColumns": "230px minmax(170px,1fr) 180px 150px 300px",
               "alignItems": "start", "gap": "24px", "padding": "20px 24px",
               "fontVariantNumeric": "tabular-nums"},
    )


def _ex6_card(item: dict) -> html.Div:
    """Большая карточка инструмента — как на главной после правок 10.08.2026.

    Проекты одной полосой: дорожка — план, заливка — факт, внутри сплошной
    кусок уникальные и штриховка повторные. Два числа лежат на одной шкале,
    поэтому «уникальных меньше факта» видно глазом.
    """
    unique_share = item["unique"] / max(item["projects_fact"], 1) * 100
    fill = min(item["projects_percent"], 100)
    # `mockup.for_year` даёт статус словом и признак `on_track`, а цвет
    # плашки живёт в примерах (`_status` ждёт его готовым): тревога —
    # тёплым золотом, а не третьим цветом инструментов
    item = {**item, "status_color": GREEN if item["on_track"] else LATE}

    def key(hatch: bool, text: str):
        mark = {"width": "9px", "height": "9px", "display": "inline-block",
                "flex": "none"}
        mark["background"] = (
            f"repeating-linear-gradient(135deg,{EX5_K} 0,{EX5_K} 2px,"
            "transparent 2px,transparent 4px)" if hatch else EX5_K)
        return html.Span([html.I(style=mark), text],
                         style={"display": "inline-flex", "alignItems": "center",
                                "gap": "5px"})

    return html.Div([
        html.Div([
            html.Span(item["title"], style={"fontSize": "15px", "fontWeight": 800,
                                            "letterSpacing": "-0.015em"}),
            _status(item),
        ], style={"display": "flex", "alignItems": "center", "gap": "10px",
                  "borderBottom": f"1px solid {HAIRLINE}", "padding": "12px 16px"}),

        html.Div([
            html.Div([
                html.Div([
                    html.Div([
                        html.Span(num(item["percent"], 1), style={
                            "fontSize": "30px", "fontWeight": 800,
                            "letterSpacing": "-0.03em", "lineHeight": 1}),
                        html.Span("%", style={"fontSize": "15px", "fontWeight": 600,
                                              "color": EX5_K, "opacity": .65}),
                    ], style={"display": "flex", "alignItems": "baseline",
                              "gap": "4px"}),
                    html.Div("от плана", style={"fontSize": "11px",
                                                "color": "var(--damu-muted)",
                                                "marginTop": "4px"}),
                ]),
                html.Div([
                    html.Div(num(item["fact"]), style={"fontSize": "20px",
                                                       "fontWeight": 800}),
                    html.Div(f"из {num(item['plan'])} млрд ₸", style={
                        "fontSize": "11px", "color": "var(--damu-muted)"}),
                ], style={"marginLeft": "auto", "textAlign": "right"}),
            ], style={"display": "flex", "alignItems": "flex-end", "gap": "12px"}),

            _paced_bar(f"{min(item['percent'], 100):.1f}%", EX5_K, height=12,
                       track="var(--damu-track)"),

            html.Div([
                html.Div([
                    _kicker("Проекты факт / план"),
                    html.Div(f"{num(item['projects_fact'])} / "
                             f"{num(item['projects_plan'])}",
                             style={"fontSize": "15px", "fontWeight": 700,
                                    "marginTop": "3px"}),
                ]),
                html.Div(f"выполнение {num(item['projects_percent'], 1)} %",
                         style={"fontSize": "11px", "color": "var(--damu-muted)"}),
            ], style={"display": "flex", "alignItems": "baseline",
                      "justifyContent": "space-between", "gap": "8px",
                      "marginTop": "14px", "paddingTop": "12px",
                      "borderTop": f"1px solid {HAIRLINE}"}),

            html.Div(
                html.Div([
                    html.Div(style={"width": f"{unique_share:.1f}%",
                                    "background": EX5_K}),
                    html.Div(style={
                        "flex": 1,
                        "background": f"repeating-linear-gradient(135deg,{EX5_K} 0,"
                                      f"{EX5_K} 2px,transparent 2px,transparent 4px)"}),
                ], style={"display": "flex", "height": "100%",
                          "width": f"{fill:.1f}%"}),
                style={"height": "10px", "background": "var(--damu-track)",
                       "marginTop": "6px"}),

            html.Div([key(False, f"уникальных {num(item['unique'])}"),
                      key(True, f"повторных {num(item['repeat'])}")],
                     style={"display": "flex", "gap": "16px", "marginTop": "6px",
                            "fontSize": "11px", "color": "var(--damu-muted)"}),

            html.Div([
                html.Div([
                    html.Span("Проектов за месяц, шт"),
                    html.Span(f"за год {num(item['months_total'])}",
                              style={"color": "var(--damu-ink)"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "fontSize": "9.5px", "fontWeight": 700,
                          "letterSpacing": ".09em", "textTransform": "uppercase",
                          "color": "var(--damu-muted)", "marginBottom": "8px"}),
                _month_bars(item["months"], item["month_labels"], EX5_K,
                            bar_h=44, font="9px"),
            ], style={"marginTop": "14px", "paddingTop": "12px",
                      "borderTop": f"1px solid {HAIRLINE}"}),
        ], style={"padding": "14px 16px 16px"}),
    ],
        className=EX5_CLASS[item["key"]],
        style={**EX5_CARD, "fontVariantNumeric": "tabular-nums"},
    )


def _ex6_map():
    """Картограмма для развёрнутого вида — та же, что в примере 4.

    `!!` Строится сразу, а лежит внутри свёрнутого блока нулевой высоты.
    Plotly меряет место при первой отрисовке, поэтому в схлопнутом
    контейнере он получит ноль и останется таким после разворота.
    Лечится не здесь, а в браузере: `assets/dashboard.js` после разворота
    зовёт `Plotly.Plots.resize` для графиков внутри. Строить карту
    по нажатию нельзя — это был бы запрос на сервер, а он сбивает
    анимацию (см. шапку блока).
    """
    return _map_block()


def _ex6_full(items: list[dict]) -> list:
    """Развёрнутый вид: полоса-итог, три карточки, программы внизу.

    Класс `damu-ex6-rise` на каждом куске — точка входа для анимации:
    блоки проявляются друг за другом сверху вниз, а не все разом.
    """
    return [
        html.Div(_ex6_band(items[0]), className="damu-ex6-rise"),
        html.Div([_ex6_card(it) for it in items[1:]],
                 className="damu-ex6-rise",
                 style={"display": "grid",
                        "gridTemplateColumns": "repeat(3, minmax(0,1fr))",
                        "gap": "14px", "marginTop": "14px"}),
        # Три колонки в ряд и без «Всех инструментов»: их числа стоят
        # в полосе-итоге выше, и повторять их значило бы показать одно
        # и то же дважды — то же решение, что на главной
        html.Div(_ex5_programs(per_row=3, with_all=False,
                               grid=EX6_PROG_GRID, gap="5px", spacer=True),
                 className="damu-ex6-rise", style={"marginTop": "14px"}),
        # Карта — четвёртый и последний блок главной. Числа в примере
        # макетные, а карта настоящая: это единственное живое место,
        # и плашка «Настоящие данные» стоит именно поэтому
        html.Div([
            html.Div([
                html.H2("Освоение по регионам", style={
                    "margin": 0, "fontSize": "15px", "fontWeight": 800,
                    "letterSpacing": "-0.015em"}),
                html.Span("картограмма по показателю «Освоено бюджета»",
                          style={"fontSize": "12px", "color": MUTED}),
                html.Span("Настоящие данные", className="damu-mock-badge",
                          style={"color": "var(--damu-accent-dark)",
                                 "borderColor": "var(--damu-accent)",
                                 "marginLeft": "auto"}),
            ], style={"display": "flex", "alignItems": "center", "gap": "12px",
                      "padding": "14px 20px 10px",
                      "borderBottom": "1px solid var(--damu-divider)"}),
            html.Div(_ex6_map(), style={"padding": "6px 10px 12px"}),
        ], className="damu-ex6-rise",
            style={**EX5_CARD, "marginTop": "14px"}),
    ]


def _example_6():
    items = mockup.for_year(None, expanded=True)
    return [
        _title_row(right=_ex6_toggle()),
        html.Div(
            [
                html.Div(html.Div(_ex5_body(), className="damu-ex6-inner"),
                         className="damu-ex6-slot damu-ex6-compact"),
                html.Div(html.Div(_ex6_full(items), className="damu-ex6-inner"),
                         className="damu-ex6-slot damu-ex6-full"),
            ],
            id="damu-ex6",
            className="damu-ex6",
            **{"data-mode": "compact"},
        ),
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
    # !! Шестой построен НА пятом (`_ex5_body`, `_ex5_programs`): удалять
    # пятый, оставив шестой, нельзя — сначала перенести эти две функции
    "6": _example_6,
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

    children.append(
        html.Div(BUILDERS[example["key"]](),
                 style={"display": "flex", "flexDirection": "column",
                        "gap": "14px"})
    )

    return dbc.Container(children, fluid=True, className="pb-5")
