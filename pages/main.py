"""Главный экран сайта — «Освоение плана» в двух состояниях.

Свёрнутое: инструменты строками, у каждого полоса освоения, проекты
кварталами и разбивка по программам справа. По кнопке справа сверху
разворачивается **витрина** — прежняя главная страница: полоса-итог,
три большие карточки, программы во всю ширину и карта областей
(`core/showcase.py`).

**Откуда это взялось.** Экран вырос из страницы-примера `/explore/5` —
одного из шести вариантов раскладки, которые пользователь нарисовал
в Claude Design и сравнивал вживую. 18.08.2026 он выбрал пятый, туда же
переехала главная, а остальные примеры и страница со списком удалены
(19.08.2026). Историю выбора и разбор отвергнутых вариантов искать
в ROADMAP и в истории git — до этого коммита файл назывался
`pages/explore_example.py` и держал все шесть.

**Числа пока нули** (`core/mockup.py`) и НЕ реагируют на фильтры года
и регионов из шапки — так решено с пользователем: разрезов по инструментам,
программам и уникальным проектам в боевой базе нет. На экране про это написано
плашкой «Данные в обработке». Живая здесь только карта в развёрнутом состоянии.

`!!` **Оформление инлайновое, хотя в проекте так не принято.** Осталось
от страницы-примера: пока вариантов было шесть, инлайн держал каждый
целиком в одном месте — удалил функцию, и следов не осталось, тогда как
классы в общем CSS пришлось бы выискивать руками. Теперь вариант один,
и довод отпал; переезд стилей в `assets/custom.css` — отдельная задача,
делать её заодно с удалением значило бы смешать два разных изменения
в одном коммите.
"""

from datetime import date

import dash
import dash_bootstrap_components as dbc
from dash import html

from core import data, mockup, showcase
from core.examples import HAIRLINE, INK, MUTED, TRACK, num

dash.register_page(__name__, path="/", name="Главная", title="Дашборд Даму")


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
            # Сумма проектов — нужна варианту 2 разбивки (одобрен
            # пользователем 13.08.2026): шапка колонки показывает оба
            # итога, деньги и проекты, а не один без объяснения почему.
            "total_count": num(sum(row[2] for row in column["rows"])),
            "rows": [
                {
                    "name": name,
                    "amount": num(amount), "count": num(count),
                    "amount_width": f"{amount / top_amount * 100:.0f}%" if top_amount else "0%",
                    "count_width": f"{count / top_count * 100:.0f}%" if top_count else "0%",
                }
                for name, amount, count in column["rows"]
            ],
        })
    return out


def _bar(width, color, height=5, track=TRACK, opacity=None, extra=None):
    """Полоска: дорожка и заливка."""
    fill = {"height": f"{height}px", "width": width, "background": color}
    if opacity is not None:
        fill["opacity"] = opacity
    style = {"height": f"{height}px", "background": track}
    style.update(extra or {})
    return html.Div(html.Div(style=fill), style=style)


def _mock_badge():
    """Плашка статуса на главной — «Данные в обработке».

    Числа пока нули — ждём источника по инструментам (Гарантирование /
    Кредитование / Субсидирование). Когда источник подключится, эта функция
    уйдёт или покажет «Свежие данные».

    Цвета взяты переменными второго цвета темы — ровно те же, что у класса
    `.damu-mock-badge` на главной.
    """
    return html.Span(
        "Данные в обработке",
        title="Разрезов по инструментам в хранилище пока нет — ожидаем источник",
        style={"fontSize": "8.5px", "fontWeight": 700, "letterSpacing": ".1em",
               "textTransform": "uppercase", "whiteSpace": "nowrap",
               "color": "var(--damu-accent-2-dark, #6a531c)",
               "border": "1px solid var(--damu-accent-2, #b08a2e)",
               "padding": "2px 6px"},
    )


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


def _unit(text) -> html.Span:
    """Единица измерения рядом с числом — мельче и светлее самого числа."""
    return html.Span(text, style={"fontSize": "9.5px", "fontWeight": 600,
                                  "color": MUTED, "marginLeft": "3px"})


def _program_row(row, color, compact=False) -> html.Div:
    """Строка разбивки в ОДНУ линию.

    Два режима:

    * **обычный** (по умолчанию) — имя · сумма денег над своей полосой ·
      число проектов бейджем. Вариант 2 из макета (одобрен 13.08.2026).
    * **compact** — имя · полоса · сумма. Бейдж «шт» убран, полоса
      стоит между именем и суммой, а не под суммой: строка становится
      ниже, и панель программ умещается на экране без скролла (просьба
      пользователя 14.08.2026). Используется в примере 5.
    """
    if compact:
        return html.Div(
            [
                html.Div(row["name"], style={
                    "flex": "0 0 30%", "minWidth": 0, "fontSize": "12px",
                    "color": INK, "lineHeight": 1.2}),
                html.Div(
                    html.Div(style={"height": "100%",
                                    "width": row["amount_width"],
                                    "background": color,
                                    "borderRadius": "3px"}),
                    style={"flex": 1, "height": "5px", "background": TRACK,
                           "borderRadius": "3px", "overflow": "hidden"},
                ),
                html.Span([row["amount"], _unit("млрд ₸")],
                          style={"flex": "none", "fontSize": "12px",
                                 "fontWeight": 700, "color": INK,
                                 "whiteSpace": "nowrap",
                                 "fontVariantNumeric": "tabular-nums"}),
            ],
            style={"display": "flex", "alignItems": "center", "gap": "10px",
                   "padding": "6px 0",
                   "borderBottom": f"1px solid {HAIRLINE}"},
        )

    return html.Div(
        [
            html.Div(row["name"], style={
                "flex": "0 0 30%", "minWidth": 0, "fontSize": "12.5px",
                "color": INK, "lineHeight": 1.2}),
            html.Div(
                [
                    html.Span([row["amount"], _unit("млрд ₸")],
                              style={"fontSize": "12.5px", "fontWeight": 700,
                                    "color": INK, "whiteSpace": "nowrap",
                                    "fontVariantNumeric": "tabular-nums"}),
                    html.Div(
                        html.Div(style={"height": "100%",
                                        "width": row["amount_width"],
                                        "background": color,
                                        "borderRadius": "3px"}),
                        style={"height": "5px", "background": TRACK,
                              "borderRadius": "3px", "overflow": "hidden",
                              "marginTop": "3px"},
                    ),
                ],
                style={"flex": 1, "minWidth": 0},
            ),
            html.Span(
                [row["count"], _unit("шт")],
                style={"flex": "none", "background": TRACK,
                      "borderRadius": "6px", "padding": "3px 8px",
                      "fontSize": "12px", "color": MUTED,
                      "fontVariantNumeric": "tabular-nums",
                      "whiteSpace": "nowrap"},
            ),
        ],
        style={"display": "flex", "alignItems": "center", "gap": "10px",
              "padding": "8px 0", "borderBottom": f"1px solid {HAIRLINE}"},
    )


def _program_head(column) -> html.Div:
    """Шапка колонки: название и оба итога (деньги и проекты).

    Раньше шапка показывала ОДИН итог без объяснения, почему не оба
    и не ни одного (просьба пользователя 13.08.2026).

    `!!` Три вещи в ОДНОЙ строке (название + деньги + проекты) ломались
    посреди слова: в колонку 173 px они не влезали, и «₸» переносился
    отдельно от своего числа. Поэтому название стоит своей строкой,
    а деньги и проекты — вместе на второй: там им хватает места
    (~110 px из 173), и это ровно то, о чём просил пользователь —
    «шт на одной линии с бюджетом». `nowrap` на обоих числах: перенос
    внутри пары «число + единица» и есть та поломка, от которой ушли.

    Строка «полоса — доля от X по деньгам» была здесь же и её убрали
    (та же просьба, 13.08.2026): в узкой колонке она сама переносилась
    на две строки и добавляла шапке высоты больше, чем объясняла.
    """
    return html.Div(
        [
            html.Span(column["short"], style={
                "fontSize": "11px", "fontWeight": 800,
                "letterSpacing": ".08em", "textTransform": "uppercase",
                "color": column["color"]}),
            html.Span([column["total"], _unit("млрд ₸")], style={
                "fontSize": "15px", "fontWeight": 800,
                "color": column["color"],
                "fontVariantNumeric": "tabular-nums",
                "whiteSpace": "nowrap"}),
            html.Span([column["total_count"], _unit("шт")], style={
                "fontSize": "12px", "fontWeight": 600, "color": MUTED,
                "fontVariantNumeric": "tabular-nums",
                "whiteSpace": "nowrap"}),
        ],
        style={"display": "flex", "alignItems": "baseline", "gap": "10px",
              "paddingBottom": "8px", "marginBottom": "10px",
              "borderBottom": f"2px solid {column['color']}"},
    )


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


#: Римские номера кварталов для подписи под клеткой — рабочая цифра, а не
#: буква месяца, раз клетка теперь держит три месяца сразу.
_ROMAN_QUARTERS = ("I", "II", "III", "IV")


def _ex5_cells(months: list[int]) -> html.Div:
    """Год кварталами: три прошедших месяца сворачиваются в одну клетку
    с их суммой; хвост года короче трёх месяцев остаётся отдельными
    месячными клетками — сворачивать там ещё нечего (тест по просьбе
    пользователя 13.08.2026).

    Кварталы, которые ещё не начались, не рисуются вовсе — раньше на их
    месте стояла пустая рамка, но для клетки-квартала это не подходит:
    было бы неясно, рамка держит место под один будущий месяц или под
    целый квартал.

    Плотность цвета — сколько клетка (квартал или отдельный месяц из
    хвоста) даёт относительно самой сильной клетки ЭТОЙ строки; шкала
    своя у каждого инструмента, как и раньше — квартал квартала
    сопоставим по масштабу с кварталом другого инструмента, а
    субсидирование и кредитование нет.

    Нижняя граница плотности 0.28, а не 0: клетка самого слабого квартала
    (или месяца из хвоста) должна остаться видимой клеткой, иначе «мало»
    и «ничего» выглядят одинаково.

    !! Квартал рисуется В ДВА РАЗА ШИРЕ месячной клетки (`flex: 2` против
    `flex: 1`) — решено 13.08.2026; сначала стояло втрое, пользователь
    попросил меньше.

    !! Число внутри клетки — белым текстом с тенью, а не переменной темы
    `--damu-ink`, как у остальных подписей на диаграммах. Причина: клетка
    красится плотностью 0.28–1.0 от НЕПРОЗРАЧНОСТИ, то есть под текстом
    в одной и той же клетке то яркий акцентный цвет, то полупрозрачный —
    ни тёмный, ни светлый фиксированный цвет не читался бы одинаково
    на обоих концах диапазона. Тень — то же решение, что берут карты
    и фото под подписью: держит контраст независимо от прозрачности
    низа, не проверено на глаз (сайт не запускался на момент правки).
    """
    entries = []  # (подпись, значение, вес, подсказка)
    i = 0
    while i < len(months):
        chunk = months[i:i + 3]
        if len(chunk) == 3:
            q = i // 3
            label = f"{_ROMAN_QUARTERS[q]} кв"
            total = sum(chunk)
            entries.append((label, total, 2, f"{label} — {num(total)} проектов"))
        else:
            # Хвост года короче квартала — по клетке на каждый месяц,
            # без свёртки, ровно как просил пользователь (1–2 клетки)
            for k, v in enumerate(chunk):
                name = mockup.MONTHS12[i + k]
                entries.append((name.lower(), v, 1, f"{name} — {num(v)} проектов"))
        i += len(chunk)

    top = max((v for _, v, _, _ in entries), default=0) or 1
    cells, letters = [], []
    for label, value, weight, tip in entries:
        cells.append(html.Div(
            num(value), title=tip,
            style={"flex": weight, "height": "26px", "background": EX5_K,
                   "opacity": round(0.28 + 0.72 * value / top, 2),
                   "display": "flex", "alignItems": "center",
                   "justifyContent": "center", "overflow": "hidden",
                   "fontSize": "9.5px", "fontWeight": 800, "color": "#fff",
                   "textShadow": "0 1px 2px rgba(0,0,0,.6)",
                   "fontVariantNumeric": "tabular-nums", "whiteSpace": "nowrap"},
        ))
        # Клеток теперь максимум 4–5 (кварталы + хвост), а не 12 — подпись
        # под каждой умещается, прежнее прореживание («каждый третий»)
        # больше не нужно
        letters.append(html.Span(
            label, style={"flex": weight, "textAlign": "center", "fontSize": "8.5px",
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
                "fontSize": "16px", "fontWeight": 700,
                "letterSpacing": "-0.01em", "whiteSpace": "nowrap"}),
            # Сумма плоским текстом, без пилюли со скруглением и тенью:
            # радиус в дизайн-системе нулевой везде
            html.Span([
                # !! Свой цвет ОБЯЗАТЕЛЕН: число вложено в span с MUTED
                # (тот же цвет, что у хвоста «из X млрд ₸» — приём как
                # в `_ex4_money` выше в файле, только там число стоит
                # СНАРУЖИ приглушённого span, а здесь внутри), и без
                # своего цвета число унаследовало бы приглушённый тон
                # вместо полновесного, потеряв контраст.
                html.B(num(item["fact"]), style={
                    "fontSize": "19px", "fontWeight": 800,
                    "letterSpacing": "-0.02em", "color": INK}),
                f" из {num(item['plan'])} млрд ₸",
            ], style={"marginLeft": "auto", "fontSize": "14px",
                      "color": MUTED, "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "alignItems": "baseline", "gap": "10px",
                  "marginBottom": "9px"}),
        # Полоса без засечки, процент — в своей колонке, а не за краем
        # заливки: так четыре числа стоят друг под другом.
        #
        # Волосяная рамка обязательна: без неё не видно, где кончается
        # стопроцентная отметка, и полоса выглядит обрывающейся. Задана
        # через outline, а не border: border вошёл бы в высоту (14 -> 16),
        # а outline рисуется поверх и раскладку не двигает
        # Полоса и процент крупнее прежнего (18.08.2026, просьба
        # пользователя): было 14 px высоты и 14 px у процента. Это главная
        # строка примера — на неё смотрят первой, а весила она столько же,
        # сколько подписи вокруг. Колонка процента расширена вместе со
        # шрифтом: при 66 px «100,0 %» встаёт одной строкой, при прежних
        # 58 px оно переносилось бы
        html.Div([
            _bar(f"{min(item['percent'], 100):.1f}%", EX5_K, height=18,
                 track="var(--damu-track)",
                 extra={"flex": 1, "outline": "1px solid var(--damu-hairline)",
                        "outlineOffset": "-1px"}),
            html.Div(f"{num(item['percent'], 1)} %", style={
                "width": "66px", "textAlign": "right", "fontSize": "17px",
                "fontWeight": 800, "color": EX5_K,
                "fontVariantNumeric": "tabular-nums"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "12px"}),
    ], style={"flex": 1, "minWidth": 0, "padding": "13px 0"})

    counts = f"{num(item['projects_fact'])} / {num(item['projects_plan'])}"
    right = html.Div([
        html.Div([
            html.Div(counts, style={
                "fontSize": "16px", "fontWeight": 700, "textAlign": "right",
                "fontVariantNumeric": "tabular-nums"}),
            # !! Полосы проектов здесь БОЛЬШЕ НЕТ (18.08.2026, просьба
            # пользователя). Она повторяла ту же мысль, что полоса слева,
            # но тоньше и без числа — и в паре с выросшей левой полосой
            # читалась как её бледная копия. Осталось «Уникальных: N» —
            # единственное, чего в строке больше нигде нет.
            html.Div(f"Уникальных: {num(item['unique'])}", style={
                "fontSize": "11px", "color": "var(--damu-muted)",
                "marginTop": "8px", "textAlign": "right"}),
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
    style = {"display": "flex", "gap": "20px", "padding": "0 20px", "minWidth": 0,
             # Строки делят между собой лишнюю высоту карточки поровну
             # (19.08.2026). Без этого она копилась пустой полосой под
             # последней строкой — см. разбор в `_ex5_body`
             "flex": "1"}
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
    # Видимый набор — колонка, которая растёт вместе с карточкой: лишнюю
    # высоту разбирают сами строки (`flex: 1` у каждой в `_ex5_row`),
    # а не пустая полоса под последней. Разбор — в `_ex5_body`.
    # !! У спрятанного набора остаётся `display: none`: он и должен
    # не занимать места вовсе, а не растягиваться заодно с видимым.
    style = ({"display": "none"} if hidden else
             {"display": "flex", "flexDirection": "column",
              "flex": "1", "minHeight": 0})
    return html.Div(rows, id=block_id, style=style)


def _ex5_kicker(text: str) -> html.Div:
    """Подпись-кикер над блоком: мелко, вразрядку, приглушённо.

    Тот же приём, что у полосы-итога и карточек витрины
    (`core/showcase.py`, класс `damu-band-kicker`) — здесь инлайном,
    как и всё остальное оформление этого файла.
    """
    return html.Div(text, style={
        "fontSize": "9.5px", "fontWeight": 700, "letterSpacing": ".09em",
        "textTransform": "uppercase", "color": MUTED, "marginBottom": "5px"})


def _ex5_total_line(label: str, fact: int, plan: int, unit: str,
                    percent: float) -> html.Div:
    """Блок «план → факт» одной величины: кикер, числа, полоса.

    Два таких в карточке итогов — по бюджету и по проектам. Устроены
    одинаково намеренно: величины разные, а вопрос к ним один («сколько
    от плана»), и разная подача заставляла бы сравнивать формы вместо чисел.

    `!!` Единица стоит В КИКЕРЕ («Бюджет, млрд ₸»), а не после числа —
    общее правило проекта: единица на блок одна. Раньше она стояла
    в хвосте «из 1 912 млрд ₸», и рядом с процентом это читалось третьей
    величиной в строке.

    `!!` Процент — в одной строке с числами и СПРАВА, а не под полосой:
    так у обоих блоков правый край держит одна вертикаль, и глазу есть
    за что зацепиться при сравнении 74,3 и 74,9.
    """
    return html.Div([
        _ex5_kicker(f"{label}, {unit}"),
        html.Div([
            html.B(num(fact), style={"fontSize": "19px", "fontWeight": 800,
                                     "letterSpacing": "-0.02em", "color": INK}),
            html.Span(f"из {num(plan)}", style={
                "fontSize": "11.5px", "color": MUTED, "whiteSpace": "nowrap"}),
            html.Span(f"{num(percent, 1)} %", style={
                "marginLeft": "auto", "fontSize": "15px", "fontWeight": 800,
                "color": EX5_K, "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "alignItems": "baseline", "gap": "6px",
                  "marginBottom": "5px"}),
        _bar(f"{min(percent, 100):.1f}%", EX5_K, height=10,
             track="var(--damu-track)",
             extra={"outline": "1px solid var(--damu-hairline)",
                    "outlineOffset": "-1px"}),
    ])


def _ex5_totals_card(item: dict) -> html.Div:
    """Четвёртая карточка разбивки — план и факт по всем инструментам сразу.

    Заведена 18.08.2026 по просьбе пользователя. Занимает место, которое
    в сетке 2×2 пустовало: программных колонок три, а клеток четыре.

    `!!` Это НЕ возвращение колонки «Все инструменты», которую убрали
    13.08.2026. Ту убрали за дело: она повторяла программными строками
    ровно те же числа, что стоят карточками слева. Здесь другое содержание —
    план против факта, чего в разбивке по программам нет вовсе: там только
    факт. Повтора не возникает, потому что показывается то, чего рядом нет.

    `!!` Проекты — ОДНОЙ полосой, как на главной и в карточке инструмента:
    дорожка это план, заливка — факт, внутри заливки сплошной кусок
    уникальные и штриховка повторные. Разбор, почему не двумя полосами
    и почему у «уникальных» нет своего процента, — в `core/showcase.py`,
    `instrument_card()`. Своя вторая правда об одних и тех же числах
    рядом с первой — это то, как они однажды и разъезжаются.

    `!!` **Класс `damu-ex5-c1` обязателен, и без него карточка ЛОМАЕТСЯ
    молча** (поймано 19.08.2026 по снимку пользователя). Тон в этой
    раскладке приходит не значением, а переменной `--ex5-k`, и ставит её
    именно класс (`custom.css`, «Пример 5 — цвета инструментов»). Без
    класса `var(--ex5-k)` не разрешается: заголовок теряет цвет, а заливка
    полос становится ПРОЗРАЧНОЙ — дорожки стоят пустыми, хотя рядом
    написано «74,3 %». Ошибки при этом нет ни одной, и глазами это выглядит
    как «просто не покрасили». Соседние карточки класс получают в
    `_ex5_programs` из `EX5_PROG_CLASS`, эта собирается отдельно — потому
    и осталась без него.
    """
    unique_share = item["unique"] / max(item["projects_fact"], 1) * 100
    fill = min(item["projects_percent"], 100)

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
            html.Span("Все инструменты", style={
                "fontSize": "11px", "fontWeight": 800, "letterSpacing": ".08em",
                "textTransform": "uppercase", "color": EX5_K}),
            html.Span("план → факт", style={
                "marginLeft": "auto", "fontSize": "11px", "color": MUTED,
                "whiteSpace": "nowrap"}),
        ], style={"display": "flex", "alignItems": "baseline", "gap": "10px",
                  "paddingBottom": "8px", "marginBottom": "14px",
                  "borderBottom": f"2px solid {EX5_K}"}),

        _ex5_total_line("Бюджет", item["fact"], item["plan"], "млрд ₸",
                        item["percent"]),
        html.Div(style={"height": "14px"}),
        _ex5_total_line("Проекты", item["projects_fact"], item["projects_plan"],
                        "шт", item["projects_percent"]),

        # Состав проектов прижат к низу карточки: между ним и блоками выше
        # проходит черта, и он читается как расшифровка, а не как третья
        # равноправная величина. `margin-top: auto` тянет его вниз, когда
        # соседняя колонка выше, — тем же приёмом собрана герой-карточка
        # раздела (`pages/section.py`).
        html.Div([
            _ex5_kicker("Состав проектов"),
            html.Div(html.Div([
                html.Div(style={"width": f"{unique_share:.1f}%",
                                "background": EX5_K}),
                # Штриховка, а не второй цвет: повторные — не отдельная
                # категория, а «остальное» от факта
                html.Div(style={
                    "flex": 1,
                    "background": f"repeating-linear-gradient(135deg,{EX5_K} 0,"
                                  f"{EX5_K} 2px,transparent 2px,transparent 4px)"}),
            ], style={"display": "flex", "height": "100%",
                      "width": f"{fill:.1f}%"}),
                style={"height": "10px", "background": "var(--damu-track)",
                       "outline": "1px solid var(--damu-hairline)",
                       "outlineOffset": "-1px"}),
            html.Div([key(False, f"уникальных {num(item['unique'])}"),
                      key(True, f"повторных {num(item['repeat'])}")],
                     style={"display": "flex", "gap": "14px", "marginTop": "7px",
                            "fontSize": "11px", "color": MUTED}),
        ], style={"marginTop": "auto", "paddingTop": "14px",
                  "borderTop": f"1px solid {HAIRLINE}"}),
    ],
        # !! Класс несёт ЦВЕТ (см. докстринг): `damu-ex5-c1` — тон
        # «все инструменты», тот же, что у первой строки слева
        className="damu-ex5-c1",
        style={**EX5_CARD, "padding": "12px 16px 14px",
               "fontVariantNumeric": "tabular-nums",
               # Карточка тянется в высоту соседней (Кредитование, 8 строк):
               # свободное место уходит в промежуток перед «Составом
               # проектов», а не остаётся дырой под нижним краем
               "display": "flex", "flexDirection": "column", "height": "100%"})


def _ex5_programs(per_row: int = 2, with_all: bool = True,
                  with_totals: bool = False) -> html.Div:
    """Разбивка по программам — строка и шапка через общие `_program_row`/
    `_program_head` (вариант 2, см. их докстринги).

    Цвет — `EX5_K` (переменная `--ex5-k`, своя на пример 5/6), а не
    литеральный GREEN/GOLD/TEAL, как в примерах 1 и 3: остальной пример 5
    целиком уже красится через `--ex5-k`, заводить для одной этой панели
    другой цвет значило бы разъехаться с остальными строками того же
    примера при переключении темы. `_program_row`/`_program_head` берут
    цвет параметром именно ради этого — им всё равно, хекс это или
    CSS-переменная.

    Разложить иначе просит пример 6: в развёрнутом виде карточка едет вниз
    во всю ширину, и колонки встают в один ряд по три — без «Всех
    инструментов», их числа там уже стоят в полосе-итоге.

    `with_totals` (18.08.2026) добавляет четвёртой карточку итогов
    (`_ex5_totals_card`). Просят её ТОЛЬКО в примере 5, и вот почему это
    не каприз: там сетка два в ряд, программных колонок три, и четвёртая
    клетка пустует. В примере 6 колонки стоят по три в ряд — четвёртая
    карточка там начала бы вторую строку в одиночестве, то есть на месте
    одной дыры появилась бы другая, шире прежней.
    """
    columns = list(zip(_programs([EX5_K] * 4), EX5_PROG_CLASS))
    if not with_all:
        columns = columns[1:]
    # Кредитование (8 программ) длиннее остальных — ставим его последним,
    # чтобы Гарантирование и Субсидирование стояли в одном ряду, а
    # Кредитование уходило вниз (просьба пользователя 14.08.2026)
    if len(columns) == 3:
        columns[1], columns[2] = columns[2], columns[1]

    cards = []
    for column, klass in columns:
        cards.append(html.Div([
            _program_head(column),
            *[_program_row(row, EX5_K, compact=True) for row in column["rows"]],
        ], className=klass, style={
            **EX5_CARD,
            "padding": "12px 16px 6px",
        }))

    if with_totals:
        # Год тот же, что у видимого по умолчанию набора строк слева
        # (`_ex5_rows(None, ...)`), а не сегодняшний календарный: карточка
        # обязана говорить о том же годе, что и числа рядом с ней
        cards.append(_ex5_totals_card(mockup.for_year(None, expanded=True)[0]))

    # !! На месте кнопки была ЛЕГЕНДА («Освоено, млрд ₸» / «Проектов, шт»),
    # убрана 19.08.2026 по просьбе пользователя. Потеря невелика: у каждой
    # строки разбивки число подписано прямо у полосы и с единицей
    # («126 млрд», «19 шт»), так что легенда объясняла то, что и так
    # написано рядом. Кнопка встала сюда же, чтобы не занимать своей строки.
    header = html.Div([
        html.H2("Разбивка по программам", style={
            "margin": 0, "fontSize": "16px", "fontWeight": 800,
            "letterSpacing": "-0.015em"}),
        html.Span("Полосы сравниваются внутри каждого инструмента",
                  className="damu-prog-scale-note"),
        _ex6_toggle("Развернуть ▾", "damu-ex5-toggle"),
    ], style={"display": "flex", "alignItems": "center", "gap": "12px",
              "marginBottom": "0px", "gridColumn": "1 / -1",
              # !! Полоса заголовка держит ту же высоту, что шапка карточки
              # слева (замерено 19.08.2026: 40 px против 36,5 — из-за этих
              # 4 px первая карточка разбивки начиналась ВЫШЕ первой строки
              # инструментов, и два столбца ехали друг относительно друга).
              # Высота, а не отступ: содержимое шапок разной высоты,
              # и подгонять надо полосу целиком.
              "minHeight": "32px"})

    return html.Div([header, *cards], style={
        "display": "grid", "gridTemplateColumns": f"repeat({per_row}, 1fr)",
        "gap": "8px", "height": "100%"})


def _ex5_body(embed_title=False):
    """Тело примера 5 без заголовка страницы.

    Вынесено отдельно ради примера 6: там ровно этот же сжатый вид лежит
    первым состоянием, а собственный заголовок у него один на оба
    состояния. Копировать раскладку было нельзя — сравнивают именно её,
    и две копии разъехались бы после первой же правки.

    ``embed_title`` (14.08.2026): когда True, шапка карточки содержит
    заголовок страницы «ОСВОЕНИЕ ПЛАНА», переключатель годов и плашку
    «Данные в обработке» — тот же набор, что раньше стоял отдельной строкой
    через ``_title_row``. Пример 6 оставляет False (у него свой заголовок).
    """
    if embed_title:
        left = html.Div([
            html.Span("Освоение плана", style={
                "fontSize": "16px", "fontWeight": 900, "letterSpacing": ".05em",
                "textTransform": "uppercase", "color": INK}),
            _year_switch(),
            _mock_badge(),
        ], style={"display": "flex", "alignItems": "center", "gap": "10px",
                  "flex": 1})
    else:
        left = html.Div("Инструмент · план → факт", style={"flex": 1})

    head = html.Div(
        [
            left,
            html.Div([
                html.Span("Проекты", style={"marginRight": "10px"}),
                _dyn_toggle({"verticalAlign": "middle"}),
            ], style={"textAlign": "right"}),
        ],
        style={"display": "flex", "gap": "16px", "padding": "8px 20px 6px",
               "fontSize": "11px", "fontWeight": 700, "letterSpacing": ".09em",
               "textTransform": "uppercase", "color": "var(--damu-muted)",
               "borderBottom": "1px solid var(--damu-divider)"},
    )

    this_year = date.today().year
    instruments = html.Div(
        [
            head,
            # !! `flex-start`, а не `space-evenly` (13.08.2026, замечание
            # пользователя «выглядит сплющено... много свободного места»).
            # `space-evenly` раздавал лишнюю высоту пустыми промежутками
            # МЕЖДУ строками: строки разъезжались, а сверху оставалась
            # дыра в пол-экрана. Лишнюю высоту с 19.08.2026 разбирают
            # сами строки (`flex: 1` у каждой), поэтому раздавать нечего.
            html.Div(
                [_ex5_rows(None, "damu-rows-2026", hidden=False),
                 _ex5_rows(this_year - 1, "damu-rows-2025", hidden=True)],
                style={"display": "flex", "flexDirection": "column",
                       "justifyContent": "flex-start", "flex": 1,
                       "minWidth": 0},
            ),
        ],
        # minWidth: 0 обязателен и здесь: это элемент CSS-сетки «1fr 640px»
        # ниже, а элемент сетки по умолчанию не сжимается уже своего
        # содержимого. Без этой строки узкая колонка «1fr» распирается
        # раскрытой динамикой, и вся страница уезжает вбок — тот же приём,
        # что у `.damu-sec-main` на странице раздела
        #
        # !! Карточка ТЯНЕТСЯ в высоту соседней колонки (19.08.2026,
        # замечание пользователя «всё какое-то кривое»). Замерено: левая
        # была 549 px против 599 у правой — нижние края колонок не сходились
        # на полсотни пикселей, и это первое, что читалось кривизной.
        #
        # `!!` Тянуть её пробовали и раньше — 13.08.2026, и тогда ОТКАТИЛИ
        # на `alignSelf: start`: карточка растягивалась, а строки внутри
        # оставались своей высоты, и разница копилась пустой полосой
        # (137 px, замерено). Разница теперь в том, ЧТО тянется: высоту
        # разбирают сами строки (`flex: 1` у каждой в `_ex5_row`), поэтому
        # пустой полосе взяться неоткуда — раздаётся не воздух, а строки.
        # Прежний откат отменяет не забывчивость, а другое устройство.
        style={**EX5_CARD, "display": "flex",
               "flexDirection": "column", "minWidth": 0},
    )

    # Колонка «Все инструменты» убрана 13.08.2026 (просьба пользователя):
    # её три строки — это ровно те же числа, что стоят слева карточками
    # инструментов, то есть один и тот же разрез показывался дважды
    # на одном экране. Пример 6 избавился от неё раньше и по тому же
    # доводу, теперь оба сжатых вида согласованы.
    #
    # `per_row=2` — две колонки в ряд, третья уходит вниз (просьба
    # пользователя 13.08.2026: «программы всё ещё 3 в ряд, закинь одну
    # вниз»). Пробовали три: формально влезали, но 173 px на колонку
    # ломали шапку переносом внутри «540 млрд ₸». При двух колонка
    # получает 284 px, и число с единицей стоят одной строкой.
    return html.Div([instruments,
                     _ex5_programs(per_row=2, with_all=False, with_totals=True)],
                     style={"display": "grid", "gridTemplateColumns": "1fr 640px",
                            "gap": "10px", "marginTop": "8px"})


def _expandable(wrap_id: str, full_children: list) -> list:
    """Два состояния экрана и кнопка перехода в каждом из них.

    `!!` **Кнопок ДВЕ, по одной на состояние, и это вынужденно** (19.08.2026).
    Пользователь попросил убрать легенду из строки «Разбивка по программам»
    и поставить кнопку на её место. Но эта строка лежит ВНУТРИ свёрнутого
    состояния, а оно при развороте гасится — в `custom.css` у него
    `opacity: 0` и `pointer-events: none`. Одна кнопка, переехавшая туда,
    после разворота стала бы невидимой и ненажимаемой: свернуть обратно
    было бы нечем. Поэтому «Свернуть» живёт своей кнопкой в развёрнутом
    состоянии — там, где её видно.

    Отсюда же следует, что **подписи у кнопок постоянные**, а не
    переписываются на лету, как было у одной. Раньше текст менял JS после
    каждого нажатия; теперь каждая кнопка всегда говорит одно и то же,
    и переписывать нечего (см. `assets/dashboard.js`).
    """
    return [
        html.Div(
            [
                # «Развернуть» стоит внутри — в шапке разбивки по программам
                # (`_ex5_programs`), на месте бывшей легенды
                html.Div(html.Div(_ex5_body(embed_title=True),
                                  className="damu-ex6-inner"),
                         className="damu-ex6-slot damu-ex6-compact"),
                html.Div(html.Div(
                    [html.Div(_ex6_toggle("Свернуть ▴", "damu-ex5-collapse"),
                              style={"display": "flex", "alignItems": "center",
                                     "marginBottom": "8px"}),
                     *full_children],
                    className="damu-ex6-inner"),
                    className="damu-ex6-slot damu-ex6-full"),
            ],
            id=wrap_id,
            className="damu-ex6",
            **{"data-mode": "compact"},
        ),
    ]


def _example_5():
    """Пример 5 сверху, НАСТОЯЩАЯ главная — по кнопке.

    Главная переезжает сюда насовсем (решение пользователя 18.08.2026):
    это будущий боевой экран, а не ещё один вариант на сравнение. Поэтому
    в развёрнутом состоянии стоит сама главная — та же функция, что рисует
    «/» (`core/showcase.body()`), — а не копия её раскладки. Копия обязана
    повторять оригинал и молча отстаёт от него после первой же правки.

    `!!` Отсюда видно глазами: развёрнутое идёт в СВОИХ цветах темы, и все
    органы главной живые — кнопки года, тумблер «Графики за весь год»,
    карта по настоящим данным. Срезать их было бы нечестно: смотрят
    как раз на то, что достанется бою.

    `!!` `showcase.body()` кладёт в разметку `dcc.Store(id="main-view")`
    и `dcc.Graph(id="main-map")` — те же имена, что на «/». Это не
    столкновение: Dash показывает одну страницу за раз, и коллбэки
    из `core/showcase.py` находят те поля, что сейчас на экране.
    """
    # Каждый кусок витрины — своим блоком с `damu-ex6-rise`, чтобы они
    # проявлялись друг за другом. Обёртки добавляются ЗДЕСЬ, а не
    # в `showcase.body()`: то общий код главной, и классу примера там не место
    return _expandable(
        "damu-ex5",
        [html.Div(part, className="damu-ex6-rise") for part in showcase.body()],
    )


# ────────── Разворот в витрину ──────────
#
# `!!` **Оба состояния лежат в разметке сразу, переключает их браузер**
# по атрибуту `data-mode` на обёртке. Коллбэком было бы проще написать,
# но тогда каждое нажатие шло бы на сервер и возвращало новое дерево —
# а перерисованный узел анимировать нечем: браузеру не с чем сравнивать
# прежнее состояние. Тот же довод, по которому в проекте вообще сделана
# подсветка вкладок в JS.
#
# Анимация — CSS: `grid-template-rows: 0fr -> 1fr` плюс проявление блоков
# друг за другом. Правила лежат в `custom.css`, блок «Пример 6»; высоту
# никто не измеряет и не подставляет числом — потому она и не ломается
# ни от числа строк, ни от раскрытой динамики, ни от смены года.
#
# `!!` Имена классов (`damu-ex6-*`) остались от страниц-примеров, которых
# больше нет: переименовывать их — правка в трёх файлах разом (CSS, JS,
# здесь) ради косметики имени. Договор с браузером описан в `dashboard.js`.


def _ex6_toggle(label: str, button_id: str):
    """Кнопка перехода между состояниями. Подпись ПОСТОЯННАЯ.

    Обработчик в `assets/dashboard.js` смотрит НЕ на id, а на класс
    `damu-ex6-toggle`; id остаётся, потому что Dash его требует и потому
    что двум кнопкам на одной странице нельзя делить одно имя.

    `!!` Текст сюда передаётся и больше НЕ переписывается браузером.
    Пока кнопка была одна, JS менял ей подпись после каждого нажатия;
    с двумя кнопками (по одной на состояние) переписывать нечего — каждая
    всегда говорит одно и то же. Разбор, почему кнопок две, — `_expandable`.
    """
    return html.Button(label, id=button_id,
                       className="damu-ex6-toggle", n_clicks=0)


def layout(**kwargs):
    """Главный экран сайта — собирается на каждое открытие страницы."""
    try:
        data.get_years()          # хранилище на месте? иначе покажем подсказку
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    return dbc.Container(
        html.Div(_example_5(), style={"display": "flex",
                                      "flexDirection": "column", "gap": "8px"}),
        fluid=True,
        className="pb-5",
    )
