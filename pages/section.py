"""Страница одного раздела — по макету 5b (и по образцу боевого портала).

Что на ней сверху вниз:

    ┌──────────┬──────────────────────────────────────────────┐
    │ разделы  │  Гар. выдача на 28.07.2026                   │
    │ списком  │ ┌ липкие вкладки ─────────────────────────┐  │
    │ слева    │ │ Годы │ Программы │ Регионы │ БВУ │ ГФ1 │  │  │
    │ (☰ —     │ └ ── под-вкладки группы: Лимиты · Пайп ──┘  │
    │  свернуть│  карточки-показатели                         │
    │  список) │  ── секция «Динамика по годам» ──            │
    │          │  ── секция «Программы» ──                    │
    │          │  ...                                         │
    └──────────┴──────────────────────────────────────────────┘

**Главное отличие от прежней версии страницы: вкладка больше не переключает
содержимое.** Раздел — одна длинная лента, все разрезы лежат на ней сразу,
а вкладка прокручивает ленту к своей секции. Прокрутили мышью — вкладка
подсветилась сама. Так устроен макет и так же ведёт себя боевой портал:
человек видит, что ниже есть ещё, и не гадает, что спрятано под вкладками.

Подсветка и прокрутка сделаны на стороне браузера (`assets/dashboard.js`),
без коллбэков: коллбэк на каждое движение колеса мыши гонял бы запросы
к серверу десятками в секунду.

Вкладки **переносятся на второй ряд**, а не уезжают в горизонтальную
прокрутку: прокрутку вбок на широком экране не видно, и часть вкладок
просто терялась бы.

Страница **одна на все разделы**: адрес `/section/guarantee` разбирается
по шаблону, ключ приходит в `layout(key=...)`. Двадцати одинаковых файлов
нет — разделы устроены одинаково, отличаются только данными.

Набор вкладок берётся из `config.yaml` (`section_tabs`, а для отдельных
разделов — `section_tabs_by_section`). Вкладки с общим полем `group`
сворачиваются в одну вкладку верхнего уровня, раскрывающую ряд «пилюль».

!! Разрезы, под которые данных ещё нет (Программы, БВУ, Бюджет), помечены
в конфиге `data: false` и показывают полосатые заглушки из макета плюс
честную строку «ждёт источника». Пустые рамки выглядели бы поломкой.
"""

import logging

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, dcc, html

from core import charts, data, mockup, widgets

log = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path_template="/section/<key>",
    name="Раздел",
    title="Раздел — Дашборд Даму",
)

#: МАКЕТНЫЕ отрасли ОКЭД — разреза по ним в боевой базе нет вовсе.
#: Числа из макета; когда придёт источник, список удаляется целиком,
#: а `oked_card()` начинает звать `core/data.py`.
OKED = [
    ("Обрабатывающая пром.", 148), ("Торговля", 121),
    ("Сельское хозяйство", 96), ("Транспорт и склад", 64),
    ("Строительство", 52), ("Услуги", 38),
    ("Здравоохранение", 12), ("Прочее", 9),
]


def block_id(tab_key: str) -> str:
    """Идентификатор секции в ленте. По нему же вкладка её и находит."""
    return f"sec-block-{tab_key}"


def top_entries(tabs: list[dict]) -> list[dict]:
    """Вкладки верхнего уровня: обычные поодиночке, группы — одной штукой.

    Возвращает для каждой вкладки её состав (`members`) — ключи секций,
    которые она собой закрывает. Браузеру это нужно, чтобы понять, какую
    вкладку подсветить: доскроллили до «Пайп» — светится группа «ГФ1».
    """
    entries: list[dict] = []
    by_group: dict[str, dict] = {}
    for tab in tabs:
        group = tab.get("group")
        if not group:
            entries.append({
                "key": tab["key"], "title": tab["title"],
                "members": [tab["key"]], "group": None,
                "data": tab.get("data"),
            })
            continue
        if group not in by_group:
            by_group[group] = {
                "key": f"group:{group}", "title": group,
                "members": [], "group": group, "data": False,
            }
            entries.append(by_group[group])
        by_group[group]["members"].append(tab["key"])
        # У группы есть данные, если они есть хоть у одной её вкладки —
        # иначе группа висела бы приглушённой при живом разрезе внутри
        by_group[group]["data"] = by_group[group]["data"] or tab.get("data")
    return entries


def tab_bar(tabs: list[dict]):
    """Липкий ряд вкладок и, под ним, ряды «пилюль» для каждой группы.

    Разметку читает `assets/dashboard.js`, поэтому у элементов есть
    data-атрибуты: `data-scroll-to` — куда прокрутить, `data-members` —
    какие секции закрывает вкладка, `data-group-row` — к какой группе
    относится ряд пилюль. Никакой логики в самих атрибутах нет, это
    просто способ передать браузеру то, что и так знает конфиг.
    """
    entries = top_entries(tabs)
    buttons = []
    for i, entry in enumerate(entries):
        buttons.append(html.Button(
            entry["title"],
            className="damu-sec-tab" + (" active" if i == 0 else "")
                      + ("" if entry["data"] else " damu-empty"),
            **{
                "data-tab-key": entry["key"],
                "data-members": ",".join(entry["members"]),
                "data-scroll-to": block_id(entry["members"][0]),
                # Ключ секции-цели: по нему браузер подсвечивает цель ещё
                # до прокрутки, чтобы ряд «пилюль» появился заранее
                # и полоса вкладок не подросла на ходу
                "data-target-key": entry["members"][0],
                "title": ("" if entry["data"]
                          else "Данных под этот разрез пока нет"),
            },
        ))

    rows = [html.Div(buttons, className="damu-sec-tabs")]
    for entry in entries:
        if not entry["group"]:
            continue
        pills = [
            html.Button(
                tab["title"],
                className="damu-sec-subtab" + (" damu-empty" if not tab.get("data") else ""),
                **{"data-scroll-to": block_id(tab["key"]),
                   "data-sub-key": tab["key"],
                   "data-target-key": tab["key"],
                   "title": ("" if tab.get("data")
                             else "Данных под этот разрез пока нет")},
            )
            for tab in tabs if tab.get("group") == entry["group"]
        ]
        rows.append(html.Div(
            pills,
            className="damu-sec-subtabs",
            # Ряд появляется только когда выбрана его группа — прячет
            # и показывает его тот же dashboard.js
            style={"display": "none"},
            **{"data-group-row": entry["key"]},
        ))
    return html.Div(rows, className="damu-sec-tabbar")


def sections_menu(active_key: str):
    """Полоса разделов слева: аббревиатура и название.

    Свёрнутая полоса показывает одни аббревиатуры (46 px), развёрнутая —
    и названия (212 px). Обе колонки лежат в разметке всегда, прячет
    названия сама полоса своей шириной: так при сворачивании ничего
    не перестраивается и аббревиатуры не дёргаются.
    """
    try:
        with_data = set(data.get_programs())
    except Exception:
        with_data = set()

    links = []
    for section in data.load_config().get("sections") or []:
        empty = section["title"] not in with_data
        links.append(dbc.NavLink(
            [
                html.Span(section.get("abbr", "?"), className="damu-side-abbr"),
                html.Span(section["title"], className="damu-side-name"),
            ],
            href=f"/section/{section['key']}",
            active=section["key"] == active_key,
            class_name="damu-empty" if empty else "",
        ))

    return html.Div(
        [
            # Кнопка ☰ — первый элемент списка; при сворачивании остаётся
            # видимой, потому что живёт внутри той же полосы
            html.Div([
                html.Button("☰", id="section-sidebar-toggle",
                            className="damu-side-toggle",
                            **{"data-toggle-sidebar": "1",
                               "aria-label": "Свернуть список разделов"}),
                html.Span("Все разделы", className="damu-side-head-label"),
            ], className="damu-side-head"),
            dbc.Nav(links, vertical=True, pills=True),
        ],
        className="damu-side-list",
        id="section-sidebar",
    )


def kpi_card(row: pd.Series, pace: float | None = None,
             solo: bool = False) -> html.Div:
    """Карточка показателя: метка, крупное число, единица.

    !! Подписи «▲ 4,2 % к прошлому году» здесь больше нет — её убрали
    по просьбе заказчика вместе с прочими пояснительными строчками.

    У карточки «Освоение» вместо неё тихая строка про ожидаемый темп,
    а у «Факта» — полоса с засечкой этого темпа: то же сравнение, но
    графикой, которая читается быстрее фразы.

    `solo` — карточка у вкладки одна (подсекции «Динамики по годам»
    у СЭЭ). Тогда она не стоит в ряду с соседями, а держит целую строку
    над своим графиком, и левое выравнивание оставляло число одиноко
    жаться к краю пустой полосы. Такая карточка встаёт по центру
    и набирается крупнее — весь остальной вид даёт разбивку, а она
    отвечает за единственное число раздела, поэтому его и видно первым.
    Раскладку (ширину и центрирование колонки) задаёт `render_kpi`,
    здесь — только вид самой карточки.
    """
    # Значение и единица приезжают одной строкой («1 307,9 млрд ₸»), а набрать
    # их надо разным кеглем. Единицу берём из реестра показателей, а не режем
    # строку по последнему пробелу: у «млрд ₸» пробел внутри, и от такого
    # разреза оставалось бы «1 307,9 млрд» и «₸»
    text = str(row["text"])
    unit = (data.get_indicator_meta(row["indicator"]) or {}).get("display_unit") or ""
    value = text[:-len(unit)].strip() if unit and text.endswith(unit) else text

    body = [
        html.Div(row["short"], className="damu-kpi2-label"),
        html.Div([
            html.Span(value, className="damu-kpi2-value"),
            html.Span(unit, className="damu-kpi2-unit"),
        ], className="damu-kpi2-figure d-flex align-items-baseline gap-2 mt-2"),
    ]

    percent = row.get("share_pct")
    if percent is not None and not pd.isna(percent) and pace is not None:
        body.append(html.Div([
            html.Div(className="fill", style={"width": f"{min(percent, 100):.1f}%"}),
            html.Div(className="tick", style={"left": f"{min(pace, 100):.1f}%"}),
        ], className="damu-kpi2-track"))
    elif row.get("note"):
        body.append(html.Div(row["note"], className="small text-muted mt-2"))

    # !! Год, за который карточка на самом деле посчитана. Пишем его ТОЛЬКО
    # когда он разошёлся с выбранным в шапке: у показателей данные кончаются
    # в разные годы, и слой данных подставляет ближайший с числами
    # (`data.resolve_year`). Молча показать 2024-й там, где выбран 2026-й, —
    # худший вид ошибки: цифра выглядит свежей и ничем не помечена
    if row.get("year") and row.get("year") != row.get("asked_year"):
        body.append(html.Div(f"данные за {int(row['year'])} год",
                             className="damu-kpi2-year"))

    return html.Div(body, className="damu-kpi2 h-100"
                    + (" damu-kpi2--solo" if solo else ""))


def chart_stubs():
    """Заглушка разреза без данных: честная строка и два поля со штриховкой.

    Ровно как в макете. Пустые рамки без пояснения читались бы как поломка,
    а надпись «нет данных» без места под них не показывала бы, что разрез
    уже спроектирован и ждёт только источника.
    """
    return html.Div([
        html.Div("Колонки под этот разрез в таблице фактов заведены, "
                 "данных пока нет.",
                 style={"fontSize": "0.75rem", "color": "var(--damu-muted)"}),
        html.Div([html.Div(className="damu-stub-field") for _ in range(2)],
                 className="damu-stub-fields"),
    ], className="damu-kpi2")


def oked_card():
    """«ОКЭД — отрасли»: карточка из макета на макетных числах.

    Разреза по ОКЭД в боевой базе нет вообще — есть только годы и регионы.
    Карточку всё же показываем: так видно, каким разрез будет, когда данные
    придут. Чтобы числа не приняли за настоящие, рядом стоит та же плашка
    «Макетные числа», что и на главной.
    """
    top = max(v for _, v in OKED)
    rows = [
        html.Div([
            html.Span(name, className="name"),
            html.Div(html.Div(className="damu-bar-fill",
                              style={"width": f"{value / top * 100:.1f}%",
                                     "height": "7px"}),
                     className="damu-bar", style={"height": "7px"}),
            html.Span(str(value), className="value"),
        ], className="damu-rowbar",
            style={"gridTemplateColumns": "minmax(0,1fr) 70px 40px"})
        for name, value in OKED
    ]
    return html.Div([
        html.Div([
            html.Span("ОКЭД — отрасли", style={"fontSize": "0.78rem",
                                               "fontWeight": 700}),
            html.Span("млрд ₸", className="small text-muted"),
            html.Span("Макетные числа", className="damu-mock-badge ms-auto",
                      title="Разреза по ОКЭД в хранилище нет — числа из эскиза"),
        ], className="d-flex align-items-baseline gap-2 mb-3"),
        *rows,
    ], className="damu-kpi2 h-100")


def _years_toggle(item: dict, program: str | None) -> html.Div | None:
    """Кнопка «Показать динамику» для вида «Годы» со свёрнутым показом.

    `None`, если у виджета нет `recent_years` (08.08.2026 — только у СЭЭ)
    или у показателя и так не больше лет, чем в свёрнутом виде: разворачивать
    было бы нечего, а кнопка без действия выглядела бы сломанной.

    Переключение сделано в браузере (`assets/dashboard.js`, обработчик
    `[data-years-toggle]`), без коллбэка: сервер уже прислал ВСЕ года
    в фигуре, клик только раздвигает видимое окно оси через
    `Plotly.relayout` — новый запрос к серверу не нужен.

    `!!` Границы окна (`data-range-lo/hi`) обязаны совпадать с тем, что
    выставляет `_years_total` в `core/charts.py` — иначе кнопка «Скрыть»
    вернёт не тот диапазон, что был изначально.
    """
    recent = item.get("recent_years")
    if not recent:
        return None
    total = len(data.indicator_years(item["indicator"], program))
    if total <= recent:
        return None
    lo, hi = total - recent - 0.5, total - 0.5
    return html.Div(
        html.Button(
            "Показать динамику ▾", n_clicks=0,
            # `data-open` — состояние кнопки. Держим его атрибутом, а не
            # классом на колонке, как в первой версии: там кнопка заодно
            # раздвигала карточку на всю ширину, а теперь график и так
            # во всю линию своей подсекцией, и менять раскладку нечем
            **{"data-years-toggle": "1", "data-open": "0",
               "data-range-lo": lo, "data-range-hi": hi},
            className="damu-years-toggle",
        ),
        className="d-flex justify-content-end mb-1",
    )


def widget_grid(section_key: str, tab_key: str, items: list[dict]):
    """Места под диаграммы одного разреза; фигуры подставит коллбэк.

    !! В id виджета склеены вкладка и номер (`years|3`). Иначе коллбэк
    не смог бы понять, из какого набора виджет: на ленте лежат разрезы
    сразу все, а наборы у них разные.
    """
    if not items:
        return dbc.Alert("Виджетов нет. Добавьте их на странице «Виджеты».",
                         color="light", className="border")
    program = widgets.program_of(section_key)
    columns = []
    for item in items:
        preset = widgets.size_meta(item["size"])
        toggle = _years_toggle(item, program)
        columns.append(
            dbc.Col(
                dbc.Card(
                    [
                        *([toggle] if toggle is not None else []),
                        dcc.Graph(
                            id={"type": "section-widget",
                                "index": f"{tab_key}|{item['id']}"},
                            style={"height": f"{preset['height']}px"},
                            config={"displayModeBar": False},
                        ),
                    ],
                    className="shadow-sm p-2 h-100",
                ),
                xs=12, lg=preset["columns"], className="mb-3",
            )
        )
    return dbc.Row(columns, className="g-3")


def section_block(section_key: str, tab: dict):
    """Одна секция ленты: заголовок разреза и его содержимое."""
    if tab.get("data"):
        body = [widget_grid(
            section_key, tab["key"],
            widgets.get_widgets(widgets.page_key(section_key, tab["key"])),
        )]
        # У разреза «ОКЭД/Регионы» половина смысла — отрасли, а их в базе
        # нет. Показываем макетную карточку рядом с настоящими виджетами,
        # честно помеченную; регионы под ней — уже по-настоящему.
        #
        # !! Раньше проверялся ключ вкладки (`tab["key"] == "regions"`) —
        # ломалось на разделах, где «Регионы» вынесены отдельно от «Отрасли»
        # (СЭЭ, 04.08.2026): та вкладка называется «Регионы», ключ тот же
        # «regions», но про ОКЭД там речи нет — своя вкладка «Отрасли» рядом.
        # Проверяем название вкладки, а не её ключ: он для навигации,
        # а не про то, что на самом деле должно на ней быть
        # !! Карточка показывается, только пока настоящего разреза по ОКЭД
        # у раздела НЕТ. С 07.08.2026 у гарантий, кредитов и Өрлеу он есть
        # (приехал из тех же файлов), и держать рядом с настоящими полосами
        # выдуманные числа было бы прямым обманом — плашка «Макетные числа»
        # спасает от этого только пока настоящих цифр не существует вовсе
        if "ОКЭД" in tab.get("title", "") and not data.has_breakdown(
                "industry", widgets.program_of(section_key)):
            body.insert(0, dbc.Row(dbc.Col(oked_card(), lg=6),
                                   className="g-3 mb-3"))
    else:
        body = [chart_stubs()]

    # Карточки-показатели этой вкладки — свои у каждой, а не один общий
    # ряд над всей лентой (так было до 04.08.2026). Место под них ставим
    # только если во вкладке есть чему показываться: пустой Row без кпи
    # в конфиге — лишний элемент, который никогда не заполнится
    if tab.get("kpi"):
        body.insert(0, dbc.Row(
            id={"type": "section-kpi", "index": tab["key"]},
            className="g-3 mb-3",
        ))

    title = [html.Span(tab["title"])]
    if not tab.get("data"):
        title.append(html.Span("ждёт источника", className="damu-stub-badge ms-2"))

    return html.Div(
        [
            html.Div(title, className="damu-sec-block-title"),
            *body,
        ],
        id=block_id(tab["key"]),
        className="damu-sec-block",
        **{"data-key": tab["key"]},
    )


def section_feed(section_key: str, tabs: list[dict]) -> list:
    """Лента раздела: вкладки одной группы собираются под общий заголовок.

    Полоса вкладок наверху уже показывает группу ОДНОЙ кнопкой, которая
    раскрывает ряд «пилюль». Лента повторяет то же устройство: заголовок
    группы один раз, под ним её подсекции с отступом и полосой слева.

    !! Без этого на Казначействе лента читалась так: ВСДС · ГФ1 · ГФ2 ·
    ВСДС · ГФ1 · ГФ2 · … · ВСДС · ГФ1 · ГФ2 — по тройке на каждую из трёх
    групп («Информация», «Доходность», «Trades»), и, долистав до «ГФ1»,
    понять, чей он, было нечем: девять подписей из пятнадцати неуникальны
    (замерено 06.08.2026). Заголовок группы возвращает потерянный контекст.

    Группы идут в конфиге подряд, поэтому собираем их одним проходом,
    а не сортировкой: порядок вкладок в `config.yaml` — это и порядок
    секций на экране, менять его нельзя.
    """
    feed: list = []
    index = 0
    while index < len(tabs):
        group = tabs[index].get("group")
        if not group:
            feed.append(section_block(section_key, tabs[index]))
            index += 1
            continue

        members = []
        while index < len(tabs) and tabs[index].get("group") == group:
            members.append(section_block(section_key, tabs[index]))
            index += 1
        feed.append(html.Div(
            [
                html.Div(group, className="damu-sec-group-title"),
                html.Div(members, className="damu-sec-group-body"),
            ],
            className="damu-sec-group",
        ))
    return feed


def layout(key: str | None = None, **kwargs):
    """Собирается на каждое открытие: раздел, вкладки и набор виджетов свежие."""
    program = widgets.program_of(key) if key else None
    if program is None:
        return dbc.Alert("Такого раздела нет. Выберите его в списке слева.",
                         color="warning", className="m-4")

    tabs = widgets.tabs_of(key)

    try:
        updated = data.get_last_update()
    except Exception:
        updated = "—"

    return html.Div(
        [
            sections_menu(key),
            html.Div(
                [
                    html.H2(f"{program} на {updated}", className="damu-sec-title"),
                    # Ключ раздела держим на странице: коллбэки читают его
                    # отсюда, а не разбирают адрес заново
                    dcc.Store(id="section-key", data=key),
                    tab_bar(tabs),
                    *section_feed(key, tabs),
                ],
                className="damu-sec-main",
            ),
        ],
        className="damu-sec-wrap",
    )


@callback(
    Output({"type": "section-kpi", "index": ALL}, "children"),
    Input("filter-year", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
    State({"type": "section-kpi", "index": ALL}, "id"),
)
def render_kpi(year, _version, key, ids):
    """Карточки-показатели каждой вкладки со своим `kpi` в конфиге.

    Раньше был один общий ряд над всей лентой — с 04.08.2026 у каждой
    вкладки свой набор и своё место, `widgets.tabs_of()` подсказывает,
    что именно показывать. Приём тот же, что у `render_widgets`: одна
    вкладка на месте не найдена — рисуем то, что есть в остальных,
    вместо того чтобы падать целиком.
    """
    program = widgets.program_of(key)
    tabs_by_key = {tab["key"]: tab for tab in widgets.tabs_of(key)}
    kpi_all = data.get_kpi(int(year), program=program)
    # Ожидаемый темп — доля прошедшего года. Он же засечка на полосе факта
    # и он же тихая строка под процентом освоения: одно число, два способа
    # показать, отстаём мы или идём ровно
    pace, _, _ = mockup.expected_pace()

    out = []
    for comp_id in ids:
        order = (tabs_by_key.get(comp_id["index"]) or {}).get("kpi") or []
        kpi = kpi_all[kpi_all["indicator"].isin(order)]
        kpi = kpi.set_index("indicator").reindex(
            [k for k in order if k in set(kpi["indicator"])]
        ).reset_index()
        if kpi.empty:
            out.append(dbc.Alert(
                "По этому разделу нет показателей за выбранный год.",
                color="light", className="border"))
            continue
        # Одна карточка на вкладку — особый случай, а не «ряд из одного»:
        # растянутая во всю ширину, она читалась как пустая полоса с числом
        # у левого края. Такую ставим по центру и уже колонкой заметной
        # ширины (`mx-auto` центрирует колонку внутри `dbc.Row` — это
        # обычный flex-ряд). Ряд из двух и больше остаётся как был:
        # `md=True` делит строку поровну между соседями.
        solo = len(kpi) == 1
        cards = []
        for _, row in kpi.iterrows():
            row = row.copy()
            # Что выбрано в шапке — чтобы карточка знала, когда её год
            # подставлен, и написала об этом
            row["asked_year"] = int(year)
            # «Факт» получает полосу с засечкой, «Освоение» — строку про темп
            if row["indicator"] == "demo_fact":
                row["share_pct"] = _fact_share(kpi)
            elif row["indicator"] == "demo_execution":
                faster = "быстрее" if _execution_value(row) >= pace else "медленнее"
                row["note"] = f"{faster} плана — прошло {pace:.1f} % года".replace(".", ",")
            if solo:
                cards.append(dbc.Col(kpi_card(row, pace, solo=True), xs=12))
            else:
                cards.append(dbc.Col(kpi_card(row, pace), xs=12, md=True))
        out.append(cards)
    return out


def _fact_share(kpi: pd.DataFrame) -> float | None:
    """Доля факта от плана — для полосы на карточке «Факт»."""
    values = dict(zip(kpi["indicator"], kpi["value"]))
    plan, fact = values.get("demo_plan"), values.get("demo_fact")
    if not plan or fact is None or pd.isna(plan) or pd.isna(fact):
        return None
    return fact / plan * 100


def _execution_value(row: pd.Series) -> float:
    """Число из карточки освоения — она и так в процентах."""
    try:
        return float(row["value"])
    except (TypeError, ValueError):
        return 0.0


@callback(
    Output({"type": "section-widget", "index": ALL}, "figure"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
    State({"type": "section-widget", "index": ALL}, "id"),
)
def render_widgets(year, regions, _version, key, ids):
    """Рисует виджеты всех разрезов разом, считая всё только по своему разделу.

    Наборы перечитываются по одному разу на разрез и запоминаются в словаре:
    на ленте разрезов несколько, и ходить в хранилище за каждым виджетом
    значило бы читать один и тот же набор по шесть раз.
    """
    program = widgets.program_of(key)
    by_tab: dict[str, dict] = {}
    figures = []
    for graph_id in ids:
        tab_key, _, widget_id = str(graph_id["index"]).partition("|")
        if tab_key not in by_tab:
            by_tab[tab_key] = {
                str(item["id"]): item
                for item in widgets.get_widgets(widgets.page_key(key, tab_key))
            }
        item = by_tab[tab_key].get(widget_id)
        if item is None:
            figures.append(charts.message("Этот виджет удалили.<br>Обновите страницу (F5)."))
            continue
        preset = widgets.size_meta(item["size"])
        figures.append(
            charts.build(
                item["chart"], item["indicator"], year, regions,
                log=False, height=preset["height"], program=program,
                recent_years=item.get("recent_years"),
            )
        )
    return figures
