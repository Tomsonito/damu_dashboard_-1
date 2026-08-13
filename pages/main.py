"""Главный экран — витрина освоения плана по макету.

Собран по листу «Даму — Главная» из Claude Design (вариант 1b, светлая тема).
Сверху вниз: строка заголовка с переключателем года, полоса-итог
«Все инструменты», три карточки инструментов, разбивка по программам,
карта областей.

**Главная мысль раскладки — иерархия.** Раньше все четыре инструмента
стояли в одном ряду, и сводный терялся среди трёх частных. Теперь сводный
вынесен в тёмную полосу во всю ширину и подан крупно: сначала «сколько
всего», потом разбивка. Цвет при этом перестал красить заголовки и стал
чертой сверху карточки — он метка категории, а не выделение важности.

**Числа макетные** (`core/mockup.py`): разрезов по инструментам, программам
и уникальным проектам в боевой базе нет. На экране про это написано прямо —
плашка «Макетные числа» стоит рядом с заголовком, а не мелочью внизу.
Карта — настоящая, она рисуется по данным и слушает фильтры.

**Что на витрине живое.** Два переключателя, и оба меняют только макетные
числа: год (текущий / прошлый) и тумблер «Графики за весь год». Год влияет
на все числа сразу, тумблер разворачивает графики месяцев с шести последних
до всех прошедших. Будущие месяцы не показываются ни в одном состоянии —
столбик за декабрь в августе означал бы ноль и читался бы как провал.

Фильтры года и регионов из шапки на макетные числа НЕ влияют: подделывать
реакцию выдуманных чисел на настоящий фильтр — обман. Карта под ними живая
и слушает и то и другое.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html

from core import charts, data, mockup

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")

#: Показатель, по которому раскрашивается карта. Настоящий, из боевых данных.
MAP_INDICATOR = "budget_spent"

#: Запасные годы: только если хранилище недоступно и спросить не у кого.
#: Обычные годы витрины даёт `showcase_years()` — из данных, а не числом.
YEAR_FALLBACK = 2026

#: Высота области столбиков в полосе-итоге и в карточке, в пикселях.
BAND_CHART_H, CARD_CHART_H = 44, 52


def showcase_years() -> tuple[int, int]:
    """Годы витрины: последний, по которому есть данные, и предыдущий.

    До 11.08.2026 здесь стояли числа 2026 и 2025 (просьба пользователя —
    показывать последний год с данными). Вписанный год плох двумя способами
    сразу: наступит 2027-й — витрина останется в 2026-м; а если выгрузки
    оборвутся на 2025-м, она предложит год, которого в данных нет.
    Спросить хранилище дешевле, чем помнить об этом.

    Годы берутся у **хранилища целиком** (`data.get_years()`), а не у одного
    показателя: витрина макетная, своего показателя у неё нет. Когда придут
    настоящие разрезы по инструментам, спрашивать надо будет уже их —
    `data.indicator_years()`, как это делают разделы.

    Чтения не боимся: факты за запрос читаются один раз (`_request_memo`),
    поэтому вызов внутри отрисовки почти бесплатен.
    """
    try:
        years = data.get_years()
    except Exception as e:                      # хранилища нет — не падаем
        log.warning("годы витрины: хранилище недоступно (%s)", e)
        years = []
    if not years:
        return YEAR_FALLBACK, YEAR_FALLBACK - 1
    # Второй год — тоже из данных, а не «первый минус один»: если выгрузки
    # идут через год, соседняя кнопка вела бы в пустоту
    return years[0], years[1] if len(years) > 1 else years[0] - 1


def num(value: float, decimals: int = 0) -> str:
    """Число по-русски: разряды неразрывным пробелом, запятая для дробей."""
    text = f"{value:,.{decimals}f}".replace(",", " ")
    return text.replace(".", ",") if decimals else text


def _months(item: dict, height: int, css: str, tight: bool):
    """Столбики «проектов за месяц»: значение сверху, месяц снизу.

    !! Числа над столбиками стоят ВСЕГДА, в том числе в развёрнутом виде.
    Раньше при развороте они пропадали — двенадцать подписей не помещались
    рядом. Но график без чисел отвечает на «какой месяц больше» и не
    отвечает на «сколько», а разворачивают его как раз чтобы посмотреть
    месяцы (замечено пользователем 10.08.2026). Вместо того чтобы прятать,
    в развёрнутом виде сжимается зазор и мельчает шрифт самих чисел —
    класс `damu-tight` на ряду столбиков.
    """
    values = item["months"]
    top = max(values) or 1
    columns = []
    for label, value in zip(item["month_labels"], values):
        column = [html.Span(num(value), className=f"{css}-value")]
        column.append(html.I(style={
            "height": f"{max(3, round(value / top * height))}px",
            # Самый высокий столбик в полную силу, остальные приглушены —
            # пик месяца видно, не читая чисел
            "opacity": 1 if value == top else 0.5,
        }))
        if css == "damu-inst2-month":
            column.append(html.Span(label, className=f"{css}-label"))
        columns.append(html.Div(column, className=css))

    block = [html.Div(columns, className=(f"{css}s damu-tight" if tight
                                          else f"{css}s"))]
    if css == "damu-band-month":
        block.append(html.Div([html.Span(m) for m in item["month_labels"]],
                              className="damu-band-labels"))
    return block


def band(item: dict, expanded: bool) -> html.Div:
    """Полоса-итог «Все инструменты» — пять колонок во всю ширину."""
    return html.Div(
        [
            html.Div([
                html.Div("Все инструменты", className="damu-band-title"),
                html.Div([
                    html.Span(num(item["percent"], 1), className="damu-band-percent"),
                    html.Span("%", style={"fontSize": "1.375rem", "fontWeight": 600,
                                          "color": "rgba(255,255,255,.6)"}),
                ], className="d-flex align-items-baseline gap-2 mt-1"),
                html.Div("от годового плана", className="damu-band-note mt-1"),
            ]),

            html.Div([
                html.Div(["Факт ",
                          html.B(num(item["fact"]), style={"color": "#fff",
                                                           "fontSize": "1.06rem"}),
                          f" из {num(item['plan'])} млрд ₸"],
                         style={"fontSize": "0.8rem",
                                "color": "rgba(255,255,255,.66)",
                                "marginBottom": "0.625rem"}),
                html.Div([
                    html.Div(className="damu-band-fill",
                             style={"width": f"{min(item['percent'], 100):.1f}%"}),
                    # Засечка ожидаемого темпа. Подписи к ней нет намеренно:
                    # в макете её убрали как лишний текст
                    html.Div(className="damu-band-tick",
                             style={"left": f"{min(item['pace'], 100):.1f}%"}),
                ], className="damu-band-track"),
            ]),

            html.Div([
                html.Div("Проекты факт / план", className="damu-band-kicker"),
                html.Div(f"{num(item['projects_fact'])} / {num(item['projects_plan'])}",
                         className="damu-band-value"),
                html.Div(html.Div(style={
                    "width": f"{min(item['projects_percent'], 100):.1f}%"}),
                    className="damu-band-bar mt-2"),
                # Четвёртая строка здесь не только ради числа: у соседней
                # колонки «Состав проектов» под полосой стоит «N повторных»,
                # и без пары полосы двух колонок вставали на разной высоте
                html.Div(f"выполнение {num(item['projects_percent'], 1)} %",
                         className="damu-band-note mt-1 text-nowrap"),
            ]),

            html.Div([
                html.Div("Состав проектов", className="damu-band-kicker"),
                html.Div([
                    html.Span(num(item["unique"]), className="damu-band-value"),
                    html.Span("уникальных", className="damu-band-note"),
                ], className="d-flex align-items-baseline gap-2 text-nowrap"),
                html.Div([
                    html.Div(className="damu-band-split-unique", style={
                        "width": f"{item['unique'] / max(item['projects_fact'], 1) * 100:.1f}%"}),
                    html.Div(className="damu-band-split-repeat"),
                ], className="damu-band-split mt-2"),
                html.Div(f"{num(item['repeat'])} повторных",
                         className="damu-band-note mt-1 text-end text-nowrap"),
            ]),

            html.Div([
                html.Div([
                    html.Span("Проектов за месяц, шт"),
                    html.Span(f"за год {num(item['months_total'])}",
                              style={"color": "rgba(255,255,255,.75)"}),
                ], className="damu-band-kicker d-flex justify-content-between mb-1"),
                *_months(item, BAND_CHART_H, "damu-band-month", tight=expanded),
            ]),
        ],
        className="damu-band",
    )


def instrument_card(item: dict, expanded: bool) -> html.Div:
    """Карточка одного инструмента: процент, полоса, проекты, месяцы."""
    tone = {"guarantee": 1, "credit": 2, "subsidy": 3}[item["key"]]

    return html.Div(
        [
            html.Div([
                html.Span(item["title"], className="damu-inst2-title"),
            ], className="damu-inst2-head"),

            html.Div([
                html.Div([
                    html.Div([
                        html.Div([
                            html.Span(num(item["percent"], 1),
                                      className="damu-inst2-percent"),
                            html.Span("%", style={"fontSize": "1.06rem",
                                                  "fontWeight": 600,
                                                  "color": "var(--damu-c)",
                                                  "opacity": .65}),
                        ], className="d-flex align-items-baseline gap-1"),
                        html.Div("от плана", className="small text-muted mt-1"),
                    ]),
                    html.Div([
                        html.Div(num(item["fact"]), className="damu-inst2-fact"),
                        html.Div(f"из {num(item['plan'])} млрд ₸",
                                 className="small text-muted"),
                    ], className="ms-auto text-end"),
                ], className="d-flex align-items-end gap-3"),

                html.Div([
                    html.Div(className="fill",
                             style={"width": f"{min(item['percent'], 100):.1f}%"}),
                    html.Div(className="tick",
                             style={"left": f"{min(item['pace'], 100):.1f}%"}),
                ], className="damu-inst2-track"),

                # !! Проекты — ОДНА полоса, а не две колонки: дорожка это
                # план, заливка — факт, а внутри заливки сплошной кусок
                # уникальные и штриховка повторные. Два числа лежат на одной
                # шкале, поэтому «уникальных меньше факта» видно глазом,
                # без сравнения двух процентов.
                #
                # Было хуже дважды. До 10.08.2026 полоса стояла только
                # у левой колонки, а под правой («Уникальных») печаталось
                # «выполнение 86,0 %» — процент ЛЕВОЙ (430/500). Потом обе
                # колонки сделали одинаковыми, но у правой «выполнение»
                # осталось враньём: плана по уникальным нет вовсе, там была
                # доля от состоявшихся. Одна полоса снимает вопрос — процент
                # теперь один и относится к паре факт/план.
                #
                # Ширины: у заливки — доля факта от плана, у сплошного куска
                # внутри — доля уникальных от ФАКТА (штриховка добирает
                # остаток сама, `flex: 1`). Тот же приём, что в полосе-итоге
                # наверху страницы (`damu-band-split`).
                html.Div([
                    html.Div([
                        html.Div("Проекты факт / план", className="damu-band-kicker",
                                 style={"color": "var(--damu-muted)"}),
                        html.Div(f"{num(item['projects_fact'])} / "
                                 f"{num(item['projects_plan'])}",
                                 className="damu-inst2-num"),
                    ]),
                    html.Div(f"выполнение {num(item['projects_percent'], 1)} %",
                             className="small text-muted"),
                ], className="damu-inst2-block d-flex align-items-baseline"
                             " justify-content-between gap-2"),

                html.Div(
                    html.Div([
                        html.Div(className="unique", style={"width":
                            f"{item['unique'] / max(item['projects_fact'], 1) * 100:.1f}%"}),
                        html.Div(className="repeat"),
                    ], className="damu-bar-split",
                        style={"width": f"{min(item['projects_percent'], 100):.1f}%"}),
                    className="damu-bar damu-bar-proj mt-1"),

                # Подписи — ЛЕГЕНДА с образцами, а не по краям полосы.
                # По краям было бы враньём: «повторных» встало бы у правого
                # края дорожки, то есть под НЕзаполненным остатком плана,
                # хотя сама штриховка кончается на 86 %.
                html.Div([
                    # Процента у «уникальных» НЕТ намеренно: у «повторных»
                    # его нет и быть не может (это остаток), а одинокий
                    # процент у соседа читается как «здесь важнее».
                    # Пара подписей должна быть в одних единицах.
                    html.Span([html.I(className="damu-key-solid"),
                               f"уникальных {num(item['unique'])}"],
                              className="damu-key"),
                    html.Span([html.I(className="damu-key-hatch"),
                               f"повторных {num(item['repeat'])}"],
                              className="damu-key"),
                ], className="small text-muted mt-1 d-flex gap-3"),

                html.Div([
                    html.Div([
                        html.Span("Проектов за месяц, шт"),
                        # Цвет переменной, а не значением: вписанный
                        # `rgba(32,30,29,.75)` в тёмной теме давал контраст
                        # 1.03 : 1 — текст сливался с фоном (замерено 04.08.2026)
                        html.Span(f"за год {num(item['months_total'])}",
                                  style={"color": "var(--damu-ink)"}),
                    ], className="damu-band-kicker d-flex justify-content-between mb-2",
                        style={"color": "var(--damu-muted)"}),
                    *_months(item, CARD_CHART_H, "damu-inst2-month",
                             tight=expanded),
                ], className="damu-inst2-block"),
            ], className="damu-inst2-body"),
        ],
        className=f"damu-inst2 damu-c-{tone}",
    )


# Место, которое «бабочка» держит под число на конце полосы: ширина трёх
# знаков плюс зазор. Число едет вместе с полосой, поэтому место под него
# вычитается из длины самой полосы, а не стоит отдельной колонкой.
FLY_LABEL = "2.1rem"


def _prog_muted(value: int):
    """Число проектов: цвет текста, а не цвет данных.

    Цвет несут полосы; подписи и значения везде носят `ink`/`muted`.
    Светлый акцент (золото, бирюза) как текст на светлой поверхности
    не читается — это правило вынесено из общего разбора диаграмм.
    """
    return html.Span(num(value), className="damu-prog-value",
                     style={"fontWeight": 400, "color": "var(--damu-muted)"})


def _prog_rows_fly(rows, top_amount, top_count):
    """Вариант 1 — «бабочка»: ось посередине, деньги влево, проекты вправо.

    По эскизу пользователя. Числа стоят НА КОНЦАХ своих полос и едут
    вместе с ними: у расходящихся полос фиксированная колонка под число
    оторвала бы его от данных тем сильнее, чем короче полоса.

    Перекос виден сразу: длинное левое плечо при коротком правом —
    «мало крупных сделок», наоборот — «много мелких».
    """
    return [
        html.Div([
            html.Span(name, className="damu-prog-name text-truncate"),
            html.Div([
                # !! Ширина полосы — доля от ОСТАТКА строки за вычетом места
                # под число (`calc`). Иначе самая длинная полоса упёрлась бы
                # в своё же число и сжалась одна: пропорции между строками
                # разъехались бы молча.
                html.Div(className="damu-fly-bar", style={
                    "width": f"calc((100% - {FLY_LABEL}) * {amount / top_amount:.3f})"}),
                html.Span(num(amount), className="damu-prog-value"),
            ], className="damu-fly-left"),
            html.Div([
                html.Div(className="damu-fly-bar damu-bar-soft", style={
                    "width": f"calc((100% - {FLY_LABEL}) * {count / top_count:.3f})"}),
                _prog_muted(count),
            ], className="damu-fly-right"),
        ], className="damu-prog-row damu-prog-fly")
        for name, amount, count in rows
    ]


def _prog_rows(rows, top_amount, top_count):
    """Строки дашборда для программ (Стеклянная бабочка: Однострочная).
    Название слева. Сама бабочка правее.
    Это делает список более строгим и структурным, как классическая таблица.
    Экономит вертикальное место.
    """
    out = []
    for name, amount, count in rows:
        a_pct = (amount / top_amount * 100) if top_amount else 0
        c_pct = (count / top_count * 100) if top_count else 0
        
        out.append(html.Div([
            html.Div(name, className="damu-prog-name text-truncate", style={"width": "30%", "paddingRight": "8px"}),
            
            html.Div([
                html.Div([
                    html.Div(f"{num(amount)} млрд", className="glass-val glow-text-c text-end", style={"marginRight": "6px", "minWidth": "55px"}),
                    html.Div(className="glass-track", children=[
                        html.Div(className="glass-fill glass-glow-c", style={"width": f"max(2%, {a_pct}%)", "marginLeft": "auto"})
                    ]),
                ], className="glass-wing glass-wing-left"),
                
                html.Div(className="glass-center-node", style={"margin": "0 6px"}),
                
                html.Div([
                    html.Div(className="glass-track", children=[
                        html.Div(className="glass-fill glass-glow-muted", style={"width": f"max(2%, {c_pct}%)", "marginRight": "auto"})
                    ]),
                    html.Div(f"{num(count)} шт", className="glass-val text-muted text-start", style={"marginLeft": "6px", "minWidth": "45px"})
                ], className="glass-wing glass-wing-right"),
                
            ], style={"display": "flex", "alignItems": "center", "flex": "1"})
        ], className="damu-prog-row damu-glass-inline-row"))
    return out


def programs_block() -> dbc.Card:
    """Разбивка по программам — три колонки по инструментам.

    Колонки «Все инструменты» здесь нет: сводные числа уже стоят в полосе
    наверху, и повторять их значило бы показать одно и то же дважды.
    Ширина полоски — доля от самой большой программы В СВОЕЙ колонке.
    """
    tones = {"Гарантирование": 1, "Кредитование": 2, "Субсидирование": 3}
    columns = []
    for column in mockup.PROGRAMS[1:]:
        short = column["title"].split(" — ")[0]
        top_amount = max(row[1] for row in column["rows"])
        top_count = max(row[2] for row in column["rows"])
        columns.append(html.Div([
            html.Div([
                html.Span(short, className="damu-prog-head flex-grow-1",
                          style={"border": "none", "padding": 0, "margin": 0}),
                html.Span(num(sum(r[1] for r in column["rows"])), style={
                    "marginLeft": "auto", "fontSize": "0.81rem", "fontWeight": 800,
                    "color": "var(--damu-c)"}),
            ], className="d-flex align-items-baseline gap-2 pb-2",
                style={"borderBottom": "2px solid var(--damu-c)"}),
            *_prog_rows(column["rows"], top_amount, top_count),
        ], className=f"damu-prog-col damu-c-{tones[short]}"))

    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.Div("Разбивка по программам", className="damu-block-title"),
                html.Span("факт по инструментам", className="small text-muted"),
                html.Div([
                    html.Span([html.I(style={"width": "22px"}), "Освоено, млрд ₸"]),
                    html.Span([html.I(style={"width": "12px"}), "Проектов, шт"]),
                ], className="damu-prog-legend"),
            ], className="damu-block-head"),
            html.Div(columns, className="damu-prog-grid",
                     style={"gridTemplateColumns": "repeat(3, minmax(0,1fr))"}),
        ]),
        class_name="shadow-sm",
    )


def title_row(year: int, expanded: bool) -> html.Div:
    """Заголовок витрины: год, плашка макетных чисел, тумблер графиков."""
    def year_button(value: int):
        return html.Button(
            str(value),
            id={"type": "main-year", "year": value},
            className="active" if value == year else "",
            n_clicks=0,
        )

    switch = html.Button(
        [
            html.Span("Графики за весь год"),
            html.Span(html.Span(className="damu-switch-knob"),
                      className="damu-switch-track"),
        ],
        id="main-expand",
        className="damu-switch" + (" active" if expanded else ""),
        title="Показать все прошедшие месяцы во всех графиках",
        n_clicks=0,
    )

    year_now, year_prev = showcase_years()
    children = [
        html.H1("Освоение плана", className="h4 mb-0"),
        html.Div([year_button(year_now), year_button(year_prev)],
                 className="damu-year"),
        html.Span("Макетные числа", className="damu-mock-badge",
                  title="Разрезов по инструментам в хранилище пока нет — "
                        "числа из эскиза"),
    ]
    if mockup.can_expand(year):
        children.append(switch)
    return html.Div(children, className="d-flex align-items-center gap-3")


def showcase(year: int, expanded: bool):
    """Вся макетная витрина целиком — её перерисовывает один коллбэк."""
    items = mockup.for_year(year, expanded)
    return [
        title_row(year, expanded),
        band(items[0], expanded),
        html.Div([instrument_card(it, expanded) for it in items[1:]],
                 className="damu-inst-grid"),
        programs_block(),
    ]


def layout(**kwargs):
    """Собирается на каждое открытие страницы."""
    try:
        data.get_years()          # хранилище на месте? иначе покажем подсказку
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    year_now, _ = showcase_years()
    return dbc.Container(
        [
            # Состояние витрины держим на странице: коллбэк читает его отсюда,
            # а не восстанавливает по подсветке кнопок
            dcc.Store(id="main-view", data={"year": year_now, "expanded": False}),
            html.Div(showcase(year_now, False), id="main-showcase",
                     className="d-flex flex-column gap-3"),
            dbc.Card(
                dbc.CardBody([
                    html.Div([
                        html.Div("Освоение по регионам", className="damu-block-title"),
                        html.Span("картограмма по показателю «Освоено бюджета»",
                                  className="small text-muted"),
                        html.Span("Настоящие данные", className="damu-mock-badge",
                                  style={"color": "var(--damu-accent-dark)",
                                         "borderColor": "var(--damu-accent)",
                                         "marginLeft": "auto"}),
                    ], className="damu-block-head"),
                    dcc.Graph(id="main-map", config={"displayModeBar": False},
                              style={"height": "440px"}),
                ]),
                class_name="shadow-sm mt-3",
            ),
        ],
        fluid=True,
        className="pb-5",
    )


@callback(
    Output("main-view", "data"),
    Input({"type": "main-year", "year": ALL}, "n_clicks"),
    Input("main-expand", "n_clicks"),
    State("main-view", "data"),
    prevent_initial_call=True,
)
def switch_view(_years, _expand, view):
    """Запоминает выбор года и состояние тумблера.

    Проверка значения отсеивает «пустые» срабатывания в момент, когда кнопки
    только появились на странице: коллбэк перерисовывает витрину вместе
    с кнопками, и без этой проверки перерисовка звала бы сама себя.
    """
    trigger = ctx.triggered_id
    if not ctx.triggered or not ctx.triggered[0]["value"]:
        return dash.no_update
    if trigger == "main-expand":
        return {**view, "expanded": not view.get("expanded", False)}
    if isinstance(trigger, dict) and trigger.get("type") == "main-year":
        year = int(trigger["year"])
        # Смена года сбрасывает разворот: у прошлого года месяцев двенадцать,
        # и развёрнутый график из шести превратился бы в кашу молча
        return {"year": year, "expanded": False}
    return dash.no_update


@callback(
    Output("main-showcase", "children"),
    Input("main-view", "data"),
    prevent_initial_call=True,
)
def render_showcase(view):
    return showcase(int(view.get("year") or showcase_years()[0]),
                    bool(view.get("expanded", False)))


@callback(
    Output("main-map", "figure"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
)
def render_map(year, regions, _version):
    """Карта — единственное на этой странице, что живёт по настоящим данным."""
    return charts.build("map", MAP_INDICATOR, year, regions, height=440)
