"""Страница одного раздела — по макету «Разделы — редизайн» (17.08.2026).

Что на ней сверху вниз:

    ┌──────────┬──────────────────────────────────────────────┐
    │ разделы  │  Гар. выдача на 28.07.2026  [Реальные данные]│
    │ списком  │ ┌ липкие вкладки ─────────────────────────┐  │
    │ слева    │ │ Годы │ Программы │ Регионы │ БВУ │ ГФ1 │  │  │
    │ (☰ —     │ └ ── под-вкладки группы: Лимиты · Пайп ──┘  │
    │  свернуть│  ┌ герой ┬ диаграмма ─────────────────────┐  │
    │  список) │  │ 24 598│ ▁▂▃▅▆█                         │  │
    │          │  └───────┴────────────────────────────────┘  │
    └──────────┴──────────────────────────────────────────────┘

**Вкладка ПЕРЕКЛЮЧАЕТ содержимое** (17.08.2026, решение пользователя
по макету редизайна). До этого раздел был одной длинной лентой, а вкладка
только прокручивал к своей секции; так было сделано осознанно и записано
в CLAUDE.md, поэтому смена — не «поправили как было удобнее», а сознательный
откат прежнего решения. Что от него осталось и почему:

* **внутри группы лента жива.** Вкладка «Динамика по годам» у СЭЭ держит
  четыре подсекции, и они по-прежнему лежат стопкой, а ряд «пилюль» под
  вкладками к ним прокручивает. Прокрутка и подсветка пилюль остались
  в браузере (`assets/dashboard.js`), без коллбэков: коллбэк на каждое
  движение колеса гонял бы к серверу десятки запросов в секунду;
* **подсветку вкладки верхнего уровня теперь ставит сервер,** а не браузер:
  активная вкладка — это уже не «докуда домотали», а состояние страницы
  (`dcc.Store` `section-tab`). Браузеру о ней знать нечего;
* **отложенная постройка диаграмм осталась** (`section-shown`,
  `visibleSections`): у группы из четырёх подсекций четыре графика,
  и строить нижние до того, как до них домотали, по-прежнему незачем.

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
from dash import (ALL, ClientsideFunction, Input, Output, State, callback,
                  clientside_callback, dcc, html, no_update)

from core import charts, data, examples, mockup, widgets

log = logging.getLogger(__name__)

dash.register_page(
    __name__,
    path_template="/section/<key>",
    name="Раздел",
    title="Раздел — Дашборд Даму",
)

#: МАКЕТНЫЕ отрасли ОКЭД — разреза по ним в боевой базе нет вовсе.
#: Числа пока нули — ждёт источника по ОКЭД; когда придёт, список
#: удаляется целиком, а `oked_card()` начинает звать `core/data.py`.
OKED = [
    ("Обрабатывающая пром.", 0), ("Торговля", 0),
    ("Сельское хозяйство", 0), ("Транспорт и склад", 0),
    ("Строительство", 0), ("Услуги", 0),
    ("Здравоохранение", 0), ("Прочее", 0),
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


def tab_class(entry: dict, active: bool) -> str:
    """Классы вкладки верхнего уровня. Одна функция на разметку и коллбэк.

    !! Именно одна: класс ставится и при первой отрисовке (`tab_bar`),
    и на каждое переключение (`switch_tab`). Разойдись эти два места —
    вкладка после клика выглядела бы иначе, чем при открытии страницы,
    а никакой ошибки бы не случилось.
    """
    return ("damu-sec-tab"
            + (" active" if active else "")
            + ("" if entry["data"] else " damu-empty"))


def tab_bar(tabs: list[dict], active_key: str | None = None):
    """Липкий ряд вкладок и место под ряд «пилюль» активной группы.

    Вкладка верхнего уровня — обычная кнопка с составным id: по клику
    коллбэк кладёт её ключ в `section-tab`, а оттуда уже перестраивается
    и лента, и подсветка. Никаких data-атрибутов для браузера у неё
    больше нет — браузеру про верхние вкладки знать нечего.

    «Пилюли» — наоборот, целиком браузерные: `data-scroll-to` (куда
    прокрутить) и `data-sub-key` (какую подсветить, когда домотали).
    Их ряд заполняет коллбэк, потому что состав зависит от того, какая
    группа сейчас открыта.
    """
    entries = top_entries(tabs)
    active_key = active_key or (entries[0]["key"] if entries else None)
    buttons = [
        html.Button(
            entry["title"],
            id={"type": "section-tab-btn", "index": entry["key"]},
            n_clicks=0,
            className=tab_class(entry, entry["key"] == active_key),
            title=("" if entry["data"] else "Данных под этот разрез пока нет"),
        )
        for entry in entries
    ]
    return html.Div(
        [
            html.Div(buttons, className="damu-sec-tabs"),
            html.Div(id="section-subtabs", className="damu-sec-subtabs-slot"),
        ],
        className="damu-sec-tabbar",
    )


def subtab_row(tabs: list[dict], entry: dict | None):
    """Ряд «пилюль» открытой группы. Не группа — пусто, ряда нет вовсе."""
    if not entry or not entry.get("group"):
        return None
    pills = [
        html.Button(
            tab["title"],
            className="damu-sec-subtab"
                      + (" damu-empty" if not tab.get("data") else "")
                      + (" active" if tab["key"] == entry["members"][0] else ""),
            **{"data-scroll-to": block_id(tab["key"]),
               "data-sub-key": tab["key"],
               "data-target-key": tab["key"],
               "title": ("" if tab.get("data")
                         else "Данных под этот разрез пока нет")},
        )
        for tab in tabs if tab.get("group") == entry["group"]
    ]
    return html.Div(
        [
            # Подпись группы из макета: ряд пилюль без неё читался как
            # второй, более мелкий ряд вкладок — непонятно, чему они
            # подчинены. Со стрелкой видно, что это раскрытая вкладка
            html.Span(f"{entry['title']} ▸", className="damu-sec-group-label"),
            html.Div(pills, className="damu-sec-subtabs"),
        ],
        className="damu-sec-subtabs-row",
    )


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
        # Приглушён раздел или нет, решают ДАННЫЕ, а значит — программа,
        # которую он показывает, а не его собственное имя. У «СЭЭ 2» это
        # разные строки: без `.get("program")` он висел бы приглушённым
        # при полных данных
        empty = (section.get("program") or section["title"]) not in with_data
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

    # !! Год, за который карточка на самом деле посчитана, стоит В ПОДПИСИ
    # сверху, а не отдельной строкой снизу (11.08.2026, просьба пользователя
    # — карточка была высокой и вместе с графиком не помещалась в экран).
    # Пишем его ТОЛЬКО когда он разошёлся с выбранным в шапке: у показателей
    # данные кончаются в разные годы, и слой данных подставляет ближайший
    # с числами (`data.resolve_year`). Молча показать 2024-й там, где выбран
    # 2026-й, — худший вид ошибки: цифра выглядит свежей и ничем не помечена.
    # Поэтому пометку не убрали совсем, а перенесли туда, где она не стоит
    # своей строки.
    label = row["short"]
    if row.get("year") and row.get("year") != row.get("asked_year"):
        label = f"{label} · {int(row['year'])}"

    body = [
        html.Div(label, className="damu-kpi2-label"),
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

    return html.Div(body, className="damu-kpi2 h-100"
                    + (" damu-kpi2--solo" if solo else ""))


#: Сколько лет показывает спарклайн герой-карточки. Шесть — столько же,
#: сколько влезает в её ширину (290 px) так, чтобы излом между соседними
#: годами был ещё различим; больше точек сливаются в линию.
#:
#: Значение по умолчанию — ключ `hero_spark_years` в config.yaml переопределяет
#: его для одной вкладки, когда полное окно портит форму (см. «Созданные
#: раб. места» в СЭЭ 2 — там ранний обвал утягивает недавние годы к полу).
HERO_SPARK_YEARS = 6


def hero_card(tab: dict, year: int, regions: list[str] | None,
              program: str | None, compact: bool = False):
    """Карточка слева от диаграммы: число года, движение и дельта.

    Заменяет собой ряд `kpi` у своей вкладки (см. `hero` в config.yaml).
    Смысл замены: у подсекции «Динамики по годам» показатель ОДИН, и
    карточка была одиноким числом во всю ширину — `kpi_card(solo=True)`
    даже поставили по центру, чтобы это не читалось пустой полосой.
    Герой-карточка занимает то же место содержательно: то же число плюс
    то, за чем на вкладку «по годам» и приходят, — куда оно движется.

    !! Цвет берётся у `charts.indicator_color()`, а не считается здесь: карточка
    стоит вплотную к своей диаграмме, и разойдись они в цвете — это была бы
    не ошибка, а просто некрасиво, то есть никто бы не починил.

    !! И цветом красится ТОЛЬКО черта сверху и спарклайн, но НЕ число
    и НЕ дельта, хотя в макете покрашены и они. Причина замерена
    17.08.2026 прямо в браузере: тон показателя на поверхности карточки
    даёт 2,66 : 1 (золото, светлая тема) — крупное число не добирает
    даже 3 : 1, положенных крупному тексту, а дельта в 11,5 px проваливает
    свои 4,5 : 1 во всех восьми случаях (четыре карточки × две темы).
    Черта и спарклайн — не текст, к ним этот порог не применяется,
    и цвет остаётся там, где он и работает опознавательным знаком.
    Существующая `kpi_card` не красит своё число ровно по той же причине.

    !! Год берётся ТОТ ЖЕ, что у диаграммы рядом: выбранный в шапке, а если
    у показателя за него данных нет — ближайший с числами (`resolve_year`,
    то же правило, что у `kpi_card`). Показать в карточке последний год
    ряда, как в макете, было бы проще, но тогда фильтр года в шапке
    молча не действовал бы на половину экрана.
    """
    indicator = (tab.get("kpi") or [None])[0]
    if not indicator:
        return None

    frame = data.get_country_years(indicator, regions, program)
    if frame.empty:
        return html.Div("За выбранный разрез данных нет.",
                        className="damu-hero damu-hero--empty")

    frame = frame.sort_values("report_year").reset_index(drop=True)
    years = [int(y) for y in frame["report_year"]]
    values = [float(v) for v in frame["value"]]

    # Ближайший год с числами, не позже выбранного. Тот же приём, что
    # в `data.resolve_year`, но по УЖЕ отобранному ряду: `resolve_year`
    # не знает про выбранные области, а карточка обязана совпасть
    # с диаграммой, которая области учитывает
    earlier = [i for i, y in enumerate(years) if y <= int(year)]
    at = earlier[-1] if earlier else len(years) - 1

    tone = charts.indicator_color(indicator)
    unit = (data.get_indicator_meta(indicator) or {}).get("display_unit") or ""
    text = data.format_value(values[at], indicator)
    number = text[:-len(unit)].strip() if unit and text.endswith(unit) else text
    label = (data.get_indicator_meta(indicator) or {}).get("short") or tab["title"]

    body = [html.Div(f"{label} · {years[at]}", className="damu-hero-label")]

    if tab.get("hero") == "compare" and at > 0:
        # Два года столбиком. Прошлый — тише и мельче, выбранный — крупно:
        # сравнение читается сверху вниз, как в макете
        body.append(html.Div([
            html.Span(str(years[at - 1]), className="damu-hero-cmp-year"),
            html.Span(data.format_value(values[at - 1], indicator),
                      className="damu-hero-cmp-value"),
        ], className="damu-hero-cmp"))
        body.append(html.Div([
            html.Span(str(years[at]), className="damu-hero-cmp-year now"),
            html.Span(number, className="damu-hero-cmp-value now"),
        ], className="damu-hero-cmp last"))
    else:
        body.append(html.Div([
            html.Span(number, className="damu-hero-value"),
            html.Span(unit, className="damu-hero-unit"),
        ], className="damu-hero-figure"))
        spark_years = tab.get("hero_spark_years") or HERO_SPARK_YEARS
        start = max(0, at - spark_years + 1)
        window = values[start:at + 1]
        if len(window) > 1:
            # !! Спарклайн берётся у `core/examples.py`, а не пишется здесь
            # заново. Модуль помечен как временный (умрёт вместе с выбором
            # раскладки «Разбора»), и теперь на нём висит боевая страница —
            # об этом сказано в его же шапке. Свой такой же рядом был бы
            # второй ломаной, которая обязана выглядеть как первая,
            # но ничем с ней не связана.
            body.append(html.Img(
                src=examples.spark(window, tone, height=30),
                className="damu-hero-spark", alt="",
            ))
            # Подписи относятся именно к этому годовому спарклайну. Месяцы
            # появятся только после раскрытия выбранного года в основной
            # диаграмме, иначе они создавали бы ложное впечатление.
            if compact:
                body.append(html.Div(
                    [html.Span(str(value)[-2:]) for value in years[start:at + 1]],
                    className="damu-hero-spark-years",
                ))

    if at > 0:
        delta = values[at] - values[at - 1]
        sign = "+" if delta >= 0 else "−"
        body.append(html.Div(
            f"{sign}{data.format_value(abs(delta), indicator)} к {years[at - 1]}",
            className="damu-hero-delta",
        ))

    if not compact:
        body.extend(_hero_regions(indicator, years[at], regions, program, tone))
    return html.Div(body, className="damu-hero"
                    + (" damu-see2-year-hero" if compact else ""),
                    style={"borderTopColor": tone, "--damu-hero-tone": tone})


#: Сколько регионов показывает карточка. Было пять — список кончался
#: заметно выше низа карточки, и `margin-top: auto` на заголовке блока
#: (custom.css, `.damu-sec-wrap--see .damu-hero-reg-head`) выбирал разницу
#: пустым воздухом НАД списком, а не под ним (замечание пользователя
#: 18.08.2026: «слишком много места»). Десять — половина из двадцати
#: регионов страны, подобрано прикидкой по высотам строк в CSS под
#: пресет `wide` (420 px); `??` точное число не перемерено в браузере.
HERO_REGIONS = 10


def _hero_regions(indicator: str, year: int, regions: list[str] | None,
                  program: str | None, tone: str) -> list:
    """Топ-5 регионов за тот же год — под числом и дельтой.

    Зачем это здесь. Под карточкой оставалось около 270 px пустоты: колонка
    тянется на всю высоту графика, а содержимого в ней было на 145. Заполнено
    не «чем-нибудь ради симметрии», а следующим вопросом, который человек
    и так задаёт, увидев общее число: «а за счёт кого?». Ответ на него
    в разделе есть, но лежит на другой вкладке — «Регионы».

    !! Год берётся ТОТ ЖЕ, что у числа над списком (`years[at]`), а не
    выбранный в шапке: у показателей данные кончаются в разные годы,
    и разойдись эти два года — карточка показывала бы итог за 2024-й
    и разбивку за 2026-й, ничем не пометив разницу.

    !! Выбранные в шапке области учитываются (`regions` уходит в запрос):
    иначе, отфильтровав экран одной областью, человек видел бы в карточке
    список из двадцати.
    """
    try:
        top = data.get_regions(indicator, int(year), HERO_REGIONS,
                               regions or None, program)
    except Exception:
        return []
    if top.empty:
        return []

    # Доли считаются от ПЕРВОГО места, а не от суммы: список короткий,
    # и сумма пяти строк — не целое, от которого имеет смысл брать процент.
    # Полоска здесь отвечает на «насколько меньше лидера», а не «какая доля»
    largest = float(top["value"].iloc[0]) or 1
    rows = [
        html.Div([
            html.Span(row.region, className="damu-hero-reg-name",
                      title=row.region),
            html.Span(data.format_value(row.value, indicator, with_unit=False),
                      className="damu-hero-reg-value"),
            html.Div(html.Div(className="damu-hero-reg-fill",
                              style={"width": f"{float(row.value) / largest * 100:.1f}%",
                                     "backgroundColor": tone}),
                     className="damu-hero-reg-track"),
        ], className="damu-hero-reg")
        for row in top.itertuples()
    ]
    return [
        html.Div(f"Больше всего · {year}", className="damu-hero-reg-head"),
        html.Div(rows, className="damu-hero-regs"),
    ]


def cut_panel(item: dict, year: int, regions: list[str] | None,
              program: str | None, columns: int | None,
              section_key: str | None = None):
    """Разрез полосами-дивами: строка «название — полоса — число».

    Заменил Plotly у видов-разрезов 17.08.2026, решение пользователя.
    Причина не в красоте: клик. В макете разрез — это строки-`div`,
    и кликается вся строка целиком; у Plotly подпись категории в его
    событиях не участвует вовсе, так что дотянуться до названия удалось
    только у СЭЭ и только через надписи с `captureevents`. На дивах клик
    достаётся даром и работает одинаково во всех разделах.

    Второе, что уходит вместе с Plotly: подсветка перестаёт быть
    перекраской фигуры (`Plotly.restyle`) и становится классом CSS.
    Кольцо «restyle → перерисовка → restyle», из-за которого 17.08.2026
    вешалась вкладка, при таком устройстве невозможно в принципе.

    !! Данные берутся `charts.cut_frame()` — той же функцией, что и у
    диаграммы Plotly на «Разборе», и заголовок — тем же `charts.cut_title()`.
    Один разрез не должен называться и считаться по-разному в двух местах.
    """
    column = charts.CUT_COLUMNS[item["chart"]]
    indicator = item["indicator"]
    # Тот же подставленный год, что у диаграмм: у показателей данные
    # кончаются в разные годы, и заголовок обязан говорить, за какой
    # год строки на самом деле
    shown = data.resolve_year(indicator, int(year), program)
    shown = int(year) if shown is None else shown

    frame = charts.cut_frame(indicator, shown, column, regions, program)
    # !! `<br>` из заголовка убираем. Это разметка Plotly: там заголовок —
    # одна строка, и перенос приходится расставлять руками, по замеренному
    # бюджету знаков на колонку. В HTML переносить умеет сам браузер,
    # а вставленный `<br>` отрисовался бы буквально, четырьмя символами
    # посреди названия (поймано сразу, `'Выпуск продукции по отраслям<br>(ОКЭД)'`).
    title = charts.cut_title(item["chart"], indicator, year, program,
                             columns).replace("<br>", " ")
    meta = data.get_indicator_meta(indicator) or {}
    tone = charts.indicator_color(indicator)
    title_view = html.Div(title, className="damu-cut-title")
    if section_key == "see2":
        reference_titles = {
            "see_jobs_created": "Созданные раб. места",
            "see_jobs_created_industry": "Созданные раб. места",
            "see_jobs_saved": "Сохранённые раб. места",
            "see_jobs_saved_industry": "Сохранённые раб. места",
        }
        metric = reference_titles.get(indicator, meta.get("short", title))
        unit = meta.get("display_unit", "")
        # В референсе первый и третий показатели отмечены одним зелёным.
        if indicator in {"see_tax_revenue", "see_tax_revenue_industry"}:
            tone = charts.indicator_color("see_output")
        title_view = html.Div([
            html.Span(f"{metric} · {shown}", className="damu-see2-cut-label"),
            html.Span(unit, className="damu-see2-cut-unit"),
        ], className="damu-cut-title damu-see2-cut-title",
           style={"borderBottomColor": tone})

    if frame.empty:
        return html.Div([
            title_view,
            html.Div("Данных по этому разрезу нет.", className="damu-cut-empty"),
        ], className="damu-cut")

    if charts.CUT_SORT.get(item["chart"]) == "alpha":
        frame = frame.sort_values("label")
    else:
        frame = frame.sort_values("value", ascending=False)

    # Цвет — тот же, что у диаграмм этого показателя (`tone: 1|2|3`
    # в config.yaml). Считается ОДНОЙ функцией с ними, разбор — у неё
    values = [float(v) for v in frame["value"]]
    # !! Границы считаются от min/max, а НЕ от нуля. У «Создано раб. мест»
    # по отраслям СЭЭ часть значений отрицательная (сокращение мест больше
    # найма — это данные источника, не сбой разбора). Жёсткий отсчёт от нуля
    # уже один раз молча съедал такие строки на диаграмме, и повторять
    # ошибку на дивах не будем: отрицательные растут ВЛЕВО от нулевой
    # засечки, и её видно.
    low, high = min(values), max(values)
    base = min(low, 0.0)
    span = (max(high, 0.0) - base) or 1
    zero = (0.0 - base) / span * 100

    rows = []
    for label, value in zip(frame["label"], values):
        width = abs(value) / span * 100
        left = zero if value >= 0 else zero - width
        rows.append(html.Div(
            [
                html.Span(label, className="damu-cut-name", title=label),
                html.Span(data.format_value(value, indicator, with_unit=False),
                          className="damu-cut-value"),
                html.Div(
                    [
                        html.Div(className="damu-cut-fill",
                                 style={"left": f"{left:.2f}%",
                                        "width": f"{max(width, 0.4):.2f}%",
                                        "backgroundColor": tone}),
                        # Нулевая засечка нужна только когда есть минус:
                        # без него ноль и так совпадает с левым краем
                        *([html.Div(className="damu-cut-zero",
                                    style={"left": f"{zero:.2f}%"})]
                          if low < 0 else []),
                    ],
                    className="damu-cut-track",
                ),
            ],
            className="damu-cut-row",
            # Договор с браузером: по этому имени строка находит свою
            # пару в соседних разрезах (assets/dashboard.js)
            role="button",
            tabIndex=0,
            **{"data-cat": str(label),
               "aria-pressed": "false",
               "aria-label":
                   f"Подсветить категорию {label} во всех диаграммах разреза"},
        ))

    return html.Div([
        title_view,
        html.Div(rows, className="damu-cut-rows"),
    ], className="damu-cut")


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
    """«ОКЭД — отрасли»: карточка-заглушка, ждёт источника.

    Разреза по ОКЭД в боевой базе нет вообще — есть только годы и регионы.
    Карточку всё же показываем: так видно, каким разрез будет, когда данные
    придут. Чтобы числа не приняли за настоящие, рядом стоит плашка
    «Данные в обработке».
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
            html.Span("Данные в обработке", className="damu-mock-badge ms-auto",
                      title="Разреза по ОКЭД в хранилище нет — ожидаем источник"),
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


def _drill_hint(item: dict):
    """Коротко объясняет скрытое действие у годовой диаграммы."""
    if item.get("chart") != "years_total":
        return None
    return html.Span(
        "Нажмите на столбец года — покажем месяцы",
        className="damu-drill-hint",
    )


def _cut_selection_feedback():
    """Подсказка и результат общей подсветки категории в разрезах."""
    return html.Div(
        [
            html.Span(
                "Выберите строку — подсветим её во всех диаграммах разреза",
                className="damu-cut-selection-text",
                **{"aria-live": "polite"},
            ),
            html.Button(
                "Сбросить",
                type="button",
                className="damu-cut-selection-reset",
                hidden=True,
            ),
        ],
        className="damu-cut-selection",
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
    see2_cut_grid = (
        section_key == "see2"
        and all(charts.is_cut(item["chart"]) and item.get("render") != "plotly"
                for item in items)
    )
    columns = []
    for item in items:
        preset = widgets.size_meta(item["size"])
        # Компактная карточка СЭЭ 2 показывает ровно шесть лет из макета,
        # поэтому раскрывать скрытые годы в ней нечего.
        toggle = None if item.get("compact_years") else _years_toggle(item, program)
        # !! Число ВНУТРИ столбца (только «Годы» у СЭЭ, core/charts.py
        # `_years_total`) красится не общей переменной `--damu-ink` — три
        # замера контраста из шести проваливали 4,5:1 (зелёный/зол.
        # заливка, обе темы), а фиксированный белый или чёрный до сих пор
        # не проходил не то зелёный, не то золото разом. `damu-inside-text`
        # переключает CSS-правило на белый текст с тёмной обводкой,
        # держит контраст независимо от того, какая из трёх заливок под
        # ним — см. custom.css, блок «Число внутри столбца (СЭЭ)».
        inside_text = (
            item["chart"] == "years_total" and program == "СЭЭ"
            and not item.get("compact_years")
        )
        index = f"{tab_key}|{item['id']}"

        # Виды-разрезы рисуются полосами-дивами, а не Plotly (17.08.2026,
        # решение пользователя). Место под них — обычный контейнер, строки
        # подставит `render_cuts`; ни высоты, ни пресета им резервировать
        # не нужно: дивы занимают ровно столько, сколько строк в разрезе,
        # а не столько, сколько попросил пресет.
        #
        # `render: plotly` в config.yaml возвращает разрезу СТАРЫЙ вид —
        # диаграммой. Заведено под временный раздел «СЭЭ 2», где оба
        # дизайна стоят рядом для сравнения глазами. Выберут — ключ
        # и раздел удаляются вместе.
        if charts.is_cut(item["chart"]) and item.get("render") != "plotly":
            cut_slot = html.Div(
                id={"type": "section-cut", "index": index},
                className="damu-see2-cut-panel" if see2_cut_grid else None,
            )
            content = cut_slot if see2_cut_grid else dbc.Card(
                cut_slot, className="shadow-sm p-3 h-100")
            columns.append(dbc.Col(
                content,
                xs=12, lg=preset["columns"],
                className="" if see2_cut_grid else "mb-3",
            ))
            continue

        columns.append(
            dbc.Col(
                dbc.Card(
                    [
                        # Полка над графиком: кнопка «Показать динамику»
                        # и, когда год раскрыт, возврат к годам. Место под
                        # возврат стоит всегда — иначе появление кнопки
                        # сдвигало бы график на свою высоту
                        html.Div(
                            [
                                html.Div(id={"type": "section-drill-note",
                                             "index": index},
                                         className="damu-drill-note"),
                                *([toggle] if toggle is not None else []),
                            ],
                            className="damu-widget-bar",
                            # Кнопка «Показать динамику» прячется, когда год
                            # раскрыт: она двигает окно оси ЛЕТ, а на оси
                            # месяцев её границы (`data-range-lo/hi`)
                            # означали бы совсем другое
                            id={"type": "section-widget-bar", "index": index},
                        ),
                        html.Div(
                            dcc.Graph(
                                id={"type": "section-widget", "index": index},
                                style={"height": f"{preset['height']}px"},
                                config={"displayModeBar": False},
                                className="damu-inside-text" if inside_text else None,
                            ),
                            # Договор с браузером: по виду диаграммы
                            # `assets/dashboard.js` понимает, можно ли
                            # подсвечивать по клику. У «Годов» клик занят
                            # раскрытием месяцев, там подсветки нет
                            **{"data-chart": item["chart"]},
                        ),
                    ],
                    className="shadow-sm p-2 h-100",
                    # !! Высота резервируется ДО того, как приедет диаграмма.
                    # Иначе пустое место схлопывается, вся лента становится
                    # короче двух экранов, и браузер решает, что показаны
                    # сразу все разрезы (замерено 12.08.2026: приходили все
                    # шесть секций СЭЭ вместо одной, отложенная постройка
                    # не работала вовсе). Заодно уходит скачок раскладки:
                    # готовая диаграмма встаёт в уже занятое ею место.
                    style={"minHeight": f"{preset['height'] + 16}px"},
                ),
                xs=12, lg=preset["columns"], className="mb-3",
            )
        )
    grid = dbc.Row(columns, className="g-4" if see2_cut_grid else "g-3")
    if see2_cut_grid:
        grid = dbc.Card(grid, className="damu-see2-cut-grid shadow-sm")

    # Подсказка одна на весь набор: выбор строки действует на все соседние
    # панели. Plotly-вариант сюда не входит — у него этого механизма нет.
    has_clickable_cuts = any(
        charts.is_cut(item["chart"]) and item.get("render") != "plotly"
        for item in items
    )
    if has_clickable_cuts:
        return html.Div([_cut_selection_feedback(), grid],
                        className="damu-cut-group")
    return grid


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
        # нули было бы прямым обманом — плашка «Данные в обработке»
        # спасает от этого только пока настоящих цифр не существует вовсе
        if "ОКЭД" in tab.get("title", "") and not data.has_breakdown(
                "industry", widgets.program_of(section_key)):
            body.insert(0, dbc.Row(dbc.Col(oked_card(), lg=6),
                                   className="g-3 mb-3"))
    else:
        body = [chart_stubs()]

    # Герой-карточка встаёт СЛЕВА от диаграмм, а не над ними, и поэтому
    # заворачивает всё содержимое вкладки в двухколоночную сетку. Ряд
    # карточек `kpi` при этом не рисуется вовсе: карточка одна и та же,
    # показывать её дважды незачем (см. `hero_card`)
    if tab.get("hero") and tab.get("data"):
        body = [html.Div(
            [
                html.Div(id={"type": "section-hero", "index": tab["key"]},
                         className="damu-hero-slot"),
                html.Div(body, className="damu-hero-side"),
            ],
            className="damu-hero-row",
        )]
    elif tab.get("kpi"):
        # Карточки-показатели этой вкладки — свои у каждой, а не один общий
        # ряд над всей лентой (так было до 04.08.2026). Место под них ставим
        # только если во вкладке есть чему показываться: пустой Row без кпи
        # в конфиге — лишний элемент, который никогда не заполнится
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


def section_feed(section_key: str, tabs: list[dict],
                 entry: dict | None) -> list:
    """Содержимое ОДНОЙ выбранной вкладки верхнего уровня.

    Обычная вкладка — один блок. Группа («Динамика по годам» у СЭЭ,
    «ГФ1» у гарантий) — стопка своих подсекций: они и правда читаются
    подряд, а ряд «пилюль» над ними к нужной прокручивает.

    !! Заголовка группы в ленте больше НЕТ, и это прямое следствие
    переключения вкладок. Он появился 06.08.2026 против такой картины
    на Казначействе: ВСДС · ГФ1 · ГФ2 · ВСДС · ГФ1 · ГФ2 · … — по тройке
    на каждую из трёх групп, и, долистав до «ГФ1», понять, чей он, было
    нечем (девять подписей из пятнадцати неуникальны). Теперь на экране
    группа всегда одна, её имя — в подсвеченной вкладке и в подписи над
    пилюлями, и повторять его третий раз незачем. Вернутся все группы
    на один экран — вернётся и заголовок.

    Порядок подсекций — порядок в `config.yaml`: он же порядок на экране.
    """
    if not entry:
        return []
    members = set(entry["members"])
    return [section_block(section_key, tab)
            for tab in tabs if tab["key"] in members]


def source_badge(program: str | None):
    """Плашка у заголовка: раздел на настоящих числах или на макетных.

    Спрашиваем не список разделов в конфиге, а сами данные
    (`data.get_programs()` — какие разделы реально есть в таблице фактов).
    Плашка о происхождении чисел обязана считаться ПО ЧИСЛАМ: конфиг —
    это намерение, а соврать здесь хуже, чем не показать вовсе.
    """
    try:
        real = program in set(data.get_programs())
    except Exception:                       # хранилища нет — судить не о чем
        return None
    if real:
        return html.Span("Реальные данные", className="damu-real-badge",
                         title="Числа приехали из хранилища, не из макета")
    return html.Span("Данные в обработке", className="damu-mock-badge",
                     title="Источника у раздела ещё нет — ожидаем источник")


def layout(key: str | None = None, **kwargs):
    """Собирается на каждое открытие: раздел, вкладки и набор виджетов свежие."""
    program = widgets.program_of(key) if key else None
    if program is None:
        return dbc.Alert("Такого раздела нет. Выберите его в списке слева.",
                         color="warning", className="m-4")

    tabs = widgets.tabs_of(key)
    entries = top_entries(tabs)
    first = entries[0] if entries else None

    try:
        updated = data.get_last_update()
    except Exception:
        updated = "—"

    return html.Div(
        [
            sections_menu(key),
            html.Div(
                [
                    html.Div([
                        # В заголовке — ИМЯ раздела, а не программа, чьи
                        # данные он показывает: у «СЭЭ 2» это разные строки
                        html.H2(f"{widgets.title_of(key) or program} на {updated}",
                                className="damu-sec-title"),
                        source_badge(program),
                    ], className="damu-sec-head"),
                    # Ключ раздела держим на странице: коллбэки читают его
                    # отсюда, а не разбирают адрес заново
                    dcc.Store(id="section-key", data=key),
                    # Выбранная вкладка верхнего уровня. Её ключ — состояние
                    # страницы, а не браузера: от него зависит, какие
                    # диаграммы сервер вообще станет строить
                    dcc.Store(id="section-tab",
                              data=first["key"] if first else None),
                    # Секции, диаграммы которых сервер уже строит. ПЕРВАЯ
                    # лежит здесь сразу, а не ждёт первого тика опроса:
                    # она видна всегда, и гонять ради неё лишний круг
                    # «опрос → коллбэк» значило бы показать пустое место
                    # там, где данные могли быть с самого начала.
                    # Дальше список пополняет браузер по мере прокрутки,
                    # см. `visibleSections` в assets/dashboard.js.
                    dcc.Store(id="section-shown",
                              data=[first["members"][0]] if first else []),
                    # Раскрытые в месяцы годы: {id виджета: год}. Словарь,
                    # а не одно значение, потому что на вкладке диаграмм
                    # бывает несколько, и раскрытие одной не должно
                    # схлопывать соседнюю
                    dcc.Store(id="section-drill", data={}),
                    # !! Опрос, а не обработчик прокрутки: он живёт
                    # в браузере и почти всегда возвращает `no_update`
                    # (см. там же). Четверть секунды — компромисс между
                    # «диаграмма готова до того, как домотали» и холостой
                    # работой; всё равно прекращается, когда лента
                    # показана целиком.
                    dcc.Interval(id="section-shown-poll", interval=250),
                    tab_bar(tabs, first["key"] if first else None),
                    html.Div(section_feed(key, tabs, first), id="section-feed"),
                ],
                className="damu-sec-main",
            ),
        ],
        # Ключ раздела — класс, а не ветка разметки: общая страница остаётся
        # одной, но у СЭЭ можно аккуратно выровнять связку «инсайт + график»
        # без побочного эффекта на остальные программы.
        className=f"damu-sec-wrap damu-sec-wrap--{key}",
    )


@callback(
    Output("section-tab", "data"),
    Input({"type": "section-tab-btn", "index": ALL}, "n_clicks"),
    Input("section-key", "data"),
    State({"type": "section-tab-btn", "index": ALL}, "id"),
)
def pick_tab(clicks, key, ids):
    """Какую вкладку выбрали. Сюда сходятся клик и смена раздела.

    !! Проверка `click` обязательна и неочевидна. Коллбэк с `ALL` будит
    не только нажатие: он срабатывает и когда кнопки просто ПОЯВИЛИСЬ
    на странице — перешли в другой раздел, кнопки создались заново.
    В этот момент `ctx.triggered_id` тоже указывает на кнопку, хотя никто
    ничего не нажимал. Без проверки счётчика раздел открывался бы
    на случайной вкладке — на той, чью кнопку Dash создал последней.
    """
    trigger = dash.ctx.triggered_id
    if isinstance(trigger, dict) and trigger.get("type") == "section-tab-btn":
        for click, comp_id in zip(clicks, ids):
            if comp_id == trigger and click:
                return trigger["index"]
    entries = top_entries(widgets.tabs_of(key))
    return entries[0]["key"] if entries else None


@callback(
    Output("section-feed", "children"),
    Output("section-subtabs", "children"),
    Output({"type": "section-tab-btn", "index": ALL}, "className"),
    Output("section-shown-poll", "disabled", allow_duplicate=True),
    Input("section-tab", "data"),
    State("section-key", "data"),
    State({"type": "section-tab-btn", "index": ALL}, "id"),
    prevent_initial_call="initial_duplicate",
)
def switch_tab(active_key, key, ids):
    """Перерисовывает ленту, ряд «пилюль» и подсветку под выбранную вкладку.

    Три выхода одним коллбэком, а не тремя: они обязаны меняться ВМЕСТЕ.
    Разнеси их по разным коллбэкам — и Dash не пообещает порядка, а между
    ними страница успеет побыть в состоянии «лента новая, подсвечена
    старая вкладка».

    Вкладок в разделе не больше пятнадцати, и вся работа здесь — собрать
    разметку: диаграммы строит уже `render_widgets`, по своему списку
    показанных секций.

    Четвёртый выход включает опрос `section-shown-poll` обратно: он мог
    выключить сам себя (см. `visibleSections` в assets/dashboard.js), когда
    прошлая вкладка была показана целиком, а у новой вкладки свои секции,
    ещё не показанные никому.
    """
    tabs = widgets.tabs_of(key)
    entries = top_entries(tabs)
    entry = next((e for e in entries if e["key"] == active_key), None)
    if entry is None:
        entry = entries[0] if entries else None

    by_key = {e["key"]: e for e in entries}
    classes = [
        tab_class(by_key[comp_id["index"]],
                  entry is not None and comp_id["index"] == entry["key"])
        for comp_id in ids
    ]
    return section_feed(key, tabs, entry), subtab_row(tabs, entry), classes, False


@callback(
    Output({"type": "section-hero", "index": ALL}, "children"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
    State({"type": "section-hero", "index": ALL}, "id"),
)
def render_hero(year, regions, _version, key, ids):
    """Герой-карточки показанных вкладок.

    Отдельный коллбэк от `render_kpi`, потому что карточка смотрит на
    ДРУГИЕ данные: там ряд показателей за один год (`get_kpi`), здесь один
    показатель за все годы (`get_country_years`) — нужна ещё и прошлогодняя
    цифра для дельты.
    """
    program = widgets.program_of(key)
    tabs_by_key = {tab["key"]: tab for tab in widgets.tabs_of(key)}
    out = []
    for comp_id in ids:
        tab = tabs_by_key.get(comp_id["index"])
        out.append(hero_card(tab, int(year), regions, program,
                             compact=(key == "see2")) if tab else None)
    return out


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


# Опрос страницы браузером: какие секции ленты уже показывались.
# Сама функция — в assets/dashboard.js (`dash_clientside.damu`), потому
# что это работа с DOM: она смотрит, докуда домотали. Здесь только
# связь «опрос → список», сервера она не касается.
#
# !! Второй выход — свой же флаг `disabled`. Без него интервал тикал
# каждые 250 мс вечно, даже когда лента полностью показана, и каждый тик —
# это коллбэк, на время которого Dash красит заголовок вкладки
# в «Updating…»: заголовок мигал без остановки (замечено 18.08.2026).
# Функция в JS выключает интервал сама, как только показывать больше
# нечего; обратно включает `switch_tab` при смене вкладки верхнего уровня.
clientside_callback(
    ClientsideFunction(namespace="damu", function_name="visibleSections"),
    Output("section-shown", "data"),
    Output("section-shown-poll", "disabled"),
    Input("section-shown-poll", "n_intervals"),
    State("section-shown", "data"),
)


#: Минимум месяцев, при котором раскрытие года вообще имеет смысл.
#: Один столбец — это не «динамика внутри года», а то же годовое число,
#: переставленное под другую подпись. Такое встречается: у СЭЭ в источнике
#: все строки за декабрь, и раскрытие 2024-го дало бы один столбец «дек».
DRILL_MIN_MONTHS = 2


def _drill_year(click: dict | None) -> int | None:
    """Год из клика по столбцу — или None, если кликнули не в год.

    Ось «Годов» объявлена категориальной (`type="category"` в `_years_total`),
    поэтому `x` приезжает строкой «2024», а не числом. Проверяем, что это
    и правда год: у раскрытой диаграммы на той же оси стоят «янв»…«дек»,
    и клик по месяцу не должен читаться как выбор года.
    """
    points = (click or {}).get("points") or []
    if not points:
        return None
    value = str(points[0].get("x", "")).strip()
    return int(value) if value.isdigit() and len(value) == 4 else None


@callback(
    Output("section-drill", "data"),
    Input({"type": "section-widget", "index": ALL}, "clickData"),
    Input({"type": "section-drill-back", "index": ALL}, "n_clicks"),
    State({"type": "section-widget", "index": ALL}, "id"),
    State({"type": "section-drill-back", "index": ALL}, "id"),
    State("section-drill", "data"),
    State("section-key", "data"),
)
def pick_drill_year(clicks, back, ids, back_ids, drill, key):
    """Клик по столбцу года раскрывает его в месяцы, повторный — сворачивает.

    Здесь же обрабатывается кнопка «✕ к годам»: оба действия правят один
    и тот же `section-drill`, а два коллбэка на один выход Dash не пустит.

    !! Раскрывается только вид «Годы» (`years_total`). Клик по любой другой
    диаграмме приходит сюда же — Dash шлёт `clickData` со всех, — и молча
    игнорируется: там клик занят подсветкой категории, и она живёт целиком
    в браузере (`assets/dashboard.js`).

    !! Клик по УЖЕ раскрытой диаграмме возвращает к годам, каким бы столбцом
    ни попали. Иначе человек, кликнувший в месяц, оказывался бы в тупике:
    ничего не происходит, а почему — непонятно.
    """
    trigger = dash.ctx.triggered_id
    drill = dict(drill or {})
    if not isinstance(trigger, dict):
        return no_update

    if trigger.get("type") == "section-drill-back":
        # !! Проверка счётчика обязательна. Кнопка «✕ к годам» РОЖДАЕТСЯ
        # раскрытием года — её кладёт в надпись тот самый коллбэк, который
        # раскрытие и отрисовал. Появление кнопки будит этот коллбэк точно
        # так же, как нажатие, и без проверки год сворачивался бы обратно
        # в тот же миг, в который раскрылся. Та же ловушка, что у `pick_tab`.
        if not any(n and i == trigger for n, i in zip(back, back_ids)):
            return no_update
        drill.pop(trigger["index"], None)
        return drill

    if trigger.get("type") != "section-widget":
        return no_update

    index = trigger["index"]
    click = next((c for c, i in zip(clicks, ids) if i == trigger), None)
    if not click:
        return no_update

    # Диаграмма уже раскрыта — любой клик по ней сворачивает обратно
    if index in drill:
        drill.pop(index, None)
        return drill

    tab_key, _, widget_id = str(index).partition("|")
    item = next(
        (w for w in widgets.get_widgets(widgets.page_key(key, tab_key))
         if str(w["id"]) == widget_id),
        None,
    )
    if item is None or item["chart"] != "years_total":
        return no_update

    year = _drill_year(click)
    if year is None:
        return no_update
    drill[index] = year
    return drill


@callback(
    Output({"type": "section-widget", "index": ALL}, "figure"),
    Output({"type": "section-drill-note", "index": ALL}, "children"),
    Output({"type": "section-widget-bar", "index": ALL}, "className"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
    Input("section-shown", "data"),
    Input("section-drill", "data"),
    State({"type": "section-widget", "index": ALL}, "id"),
    State({"type": "section-drill-note", "index": ALL}, "id"),
    State({"type": "section-widget-bar", "index": ALL}, "id"),
)
def render_widgets(year, regions, _version, key, shown, drill,
                   ids, note_ids, bar_ids):
    """Рисует виджеты ПОКАЗАННЫХ разрезов, считая всё только по своему разделу.

    Наборы перечитываются по одному разу на разрез и запоминаются в словаре:
    на ленте разрезов несколько, и ходить в хранилище за каждым виджетом
    значило бы читать один и тот же набор по шесть раз.

    !! Разрезы, до которых человек не домотал, НЕ строятся вовсе: их место
    остаётся пустым, а `shown` пополняется браузером по мере прокрутки
    (`visibleSections` в assets/dashboard.js). На СЭЭ это двенадцать
    диаграмм против одной при открытии.

    !! Непоказанным отдаётся `no_update`, а не пустая фигура, и разница
    тут не косметическая. `no_update` оставляет место нетронутым; пустая
    фигура СТЁРЛА бы уже построенную диаграмму при каждом пополнении
    списка — домотал до третьей секции, а первые две погасли.

    Устаревших чисел этот приём не создаёт: смена года, регионов или
    версии данных перестраивает ВСЕ показанные разрезы (они входят
    в `shown`), а непоказанные пусты — им нечему устареть. Разрез,
    до которого домотают позже, построится уже с новым фильтром.

    !! Фигура, надпись над ней и вид полки считаются ЗДЕСЬ ЖЕ, одним
    проходом, а не тремя коллбэками. Они обязаны сходиться: показать
    «✕ к годам» над диаграммой, которая осталась годовой, — прямая ложь
    о том, что сейчас на экране. Одно решение принимается один раз.
    """
    program = widgets.program_of(key)
    ready = set(shown or [])
    drill = drill or {}
    by_tab: dict[str, dict] = {}
    # Считаем по ключу виджета, а раскладываем по спискам ниже: у трёх
    # выходов свой порядок компонентов, и совпадать он не обязан
    figures: dict[str, object] = {}
    notes: dict[str, object] = {}
    drilled: dict[str, bool] = {}

    for graph_id in ids:
        index = str(graph_id["index"])
        tab_key, _, widget_id = index.partition("|")
        if tab_key not in ready:
            figures[index] = no_update
            notes[index] = no_update
            continue
        if tab_key not in by_tab:
            by_tab[tab_key] = {
                str(item["id"]): item
                for item in widgets.get_widgets(widgets.page_key(key, tab_key))
            }
        item = by_tab[tab_key].get(widget_id)
        if item is None:
            figures[index] = charts.message(
                "Этот виджет удалили.<br>Обновите страницу (F5).")
            notes[index] = None
            continue

        preset = widgets.size_meta(item["size"])
        chart_type, chart_year = item["chart"], year
        monthly = None
        monthly_is_test = False
        open_year = drill.get(index)
        if open_year is not None:
            monthly_is_test = bool(item.get("test_months"))
            months = (
                data.get_test_monthly(item["indicator"], int(open_year),
                                      regions or None, program)
                if monthly_is_test else
                data.get_monthly(item["indicator"], int(open_year),
                                 regions or None, program)
            )
            if len(months) >= DRILL_MIN_MONTHS:
                chart_type, chart_year = "months", int(open_year)
                monthly = months
                suffix = "тестовые месяцы" if monthly_is_test else "по месяцам"
                notes[index] = _drill_back(index, f"{open_year} — {suffix}")
                drilled[index] = True
            else:
                # !! Раскрывать нечего — и тогда НЕТ ни кнопки «✕ к годам»,
                # ни пометки `damu-drilled` (17.08.2026, замечание
                # пользователя: «пишет, что открылся, хотя по факту нет»).
                # Первая версия показывала кнопку возврата в обоих случаях,
                # чтобы из состояния всегда был выход, — и этим сама себе
                # противоречила: кнопка «вернуться к годам» над диаграммой,
                # которая от годов никуда не уходила, говорит человеку,
                # что он куда-то попал. Выход из этого состояния всё равно
                # есть: повторный клик по тому же году убирает надпись
                # (`pick_drill_year` сворачивает то, что уже в `drill`).
                notes[index] = html.Span(
                    f"Помесячных данных за {open_year} нет — "
                    f"в источнике только один месяц",
                    className="damu-drill-text damu-drill-warn",
                )
        else:
            notes[index] = _drill_hint(item)

        figures[index] = charts.build(
            chart_type, item["indicator"], chart_year, regions,
            log=False, height=preset["height"], program=program,
            recent_years=item.get("recent_years"),
            # Ширина нужна заголовку: по ней он решает, переносить ли
            # год на вторую строку (см. `Ctx.title` в core/charts.py)
            columns=preset["columns"],
            monthly=monthly,
            monthly_is_test=monthly_is_test and monthly is not None,
            compact_years=item.get("compact_years", False),
        )

    return (
        [figures.get(str(i["index"]), no_update) for i in ids],
        [notes.get(str(i["index"]), no_update) for i in note_ids],
        ["damu-widget-bar" + (" damu-drilled" if drilled.get(str(i["index"])) else "")
         for i in bar_ids],
    )


@callback(
    Output({"type": "section-cut", "index": ALL}, "children"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
    Input("data-version", "data"),
    Input("section-key", "data"),
    Input("section-shown", "data"),
    State({"type": "section-cut", "index": ALL}, "id"),
)
def render_cuts(year, regions, _version, key, shown, ids):
    """Разрезы полосами-дивами. Тот же приём, что у `render_widgets`.

    Отдельный коллбэк, а не ещё один выход у соседнего: у разрезов нет
    ни фигуры, ни полки над ней, ни раскрытия года — общего с виджетами
    Plotly у них только «строить лишь то, до чего домотали».

    !! Отложенная постройка сохранена и здесь. Дивы дешевле фигур, но
    ЧТЕНИЕ данных стоит столько же: разрез — это заход в таблицу фактов
    с группировкой, и четыре таких на невидимой вкладке — четыре лишних
    захода.
    """
    program = widgets.program_of(key)
    ready = set(shown or [])
    by_tab: dict[str, dict] = {}
    out = []
    for comp_id in ids:
        index = str(comp_id["index"])
        tab_key, _, widget_id = index.partition("|")
        if tab_key not in ready:
            out.append(no_update)
            continue
        if tab_key not in by_tab:
            by_tab[tab_key] = {
                str(w["id"]): w
                for w in widgets.get_widgets(widgets.page_key(key, tab_key))
            }
        item = by_tab[tab_key].get(widget_id)
        if item is None or not charts.is_cut(item["chart"]):
            out.append(html.Div("Этот виджет удалили. Обновите страницу (F5).",
                                className="damu-cut-empty"))
            continue
        preset = widgets.size_meta(item["size"])
        out.append(cut_panel(item, int(year), regions, program,
                             preset["columns"], key))
    return out


def _drill_back(index: str, text: str, warn: bool = False):
    """Надпись «что сейчас показано» и кнопка возврата к годам."""
    return html.Div(
        [
            html.Span(text, className="damu-drill-text"
                              + (" damu-drill-warn" if warn else "")),
            html.Button("✕ к годам", n_clicks=0,
                        id={"type": "section-drill-back", "index": index},
                        className="damu-drill-back"),
        ],
        className="d-flex align-items-center gap-2",
    )
