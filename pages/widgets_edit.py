"""Настройщик виджетов главного экрана. Доступ — только админ.

Что здесь можно: добавить виджет, убрать, переставить, сменить у любого
показатель, вид диаграммы или размер. Набор общий для всех — персональные
экраны потребовали бы знать, кто вошёл, то есть LDAP из этапа 5.

Перестановка — кнопками «вверх/вниз», а не мышью: перетаскивания в Dash
нет, а сторонний компонент — чужой код, который однажды отстанет от новой
версии Dash.

Правки применяются сразу (шлюз 9:00 сторожит цифры, а не вид), но главная
страница собирает сетку при открытии — поэтому после правок её надо
обновить. Об этом написано прямо на странице, чтобы не выглядело поломкой.

Устройство коллбэков, и почему их два:

- **структура** (добавить / удалить / переставить / сбросить) перерисовывает
  список целиком;
- **поля** (показатель, вид, размер) только пишут в хранилище и отвечают
  строкой-подтверждением.

Разделение нужно, чтобы не поймать бесконечный круг: список перерисовывает
выпадающие списки, а их значения — вход того же коллбэка, и он позвал бы
сам себя. Вдобавок коллбэк полей сверяет новое значение с сохранённым
и на совпадении молчит — тогда лишнее срабатывание ничего не делает.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, html, no_update

from core import auth, widgets

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/widgets", name="Виджеты",
                   title="Виджеты — Дашборд Даму")


def _select(kind: str, widget_id: int, options: list[dict], value: str, width: str):
    return dbc.Select(
        id={"type": f"w-{kind}", "index": widget_id},
        options=options,
        value=value,
        size="sm",
        style={"minWidth": width},
    )


def widgets_list(page: str):
    """Таблица виджетов выбранной страницы: по строке на каждый."""
    items = widgets.get_widgets(page)
    if not items:
        return html.P("Виджетов нет — добавьте первый ниже.",
                      className="text-muted small")

    indicators = widgets.indicator_choices()
    chart_types = widgets.chart_choices()
    sizes = widgets.size_choices()

    head = html.Thead(html.Tr([html.Th(h) for h in
        ["№", "Показатель", "Вид диаграммы", "Размер", "Порядок", ""]]))

    rows = []
    for number, item in enumerate(items, start=1):
        wid = item["id"]
        rows.append(html.Tr([
            html.Td(str(number)),
            html.Td(_select("indicator", wid, indicators, item["indicator"], "16rem")),
            html.Td(_select("chart", wid, chart_types, item["chart"], "18rem")),
            html.Td(_select("size", wid, sizes, item["size"], "12rem")),
            html.Td([
                dbc.Button("↑", id={"type": "w-up", "index": wid}, size="sm",
                           color="secondary", outline=True, className="me-1",
                           # у крайних двигаться некуда — кнопка гаснет
                           disabled=number == 1),
                dbc.Button("↓", id={"type": "w-down", "index": wid}, size="sm",
                           color="secondary", outline=True,
                           disabled=number == len(items)),
            ]),
            html.Td(dbc.Button("Убрать", id={"type": "w-del", "index": wid},
                               size="sm", color="danger", outline=True)),
        ]))

    return dbc.Table([head, html.Tbody(rows)], hover=True, size="sm",
                     className="align-middle")


def status_line(page: str):
    """Откуда сейчас берётся набор этой страницы и кто его правил."""
    if not widgets.is_customized(page):
        return html.P(
            "Сейчас показывается набор по умолчанию из config.yaml. "
            "Первая же правка сохранит его в хранилище как ваш.",
            className="text-muted small",
        )
    changed = widgets.last_change(page)
    tail = f" Последняя правка: {changed[0]}, {changed[1]:%d.%m %H:%M}." if changed else ""
    return html.P("Набор настроен вручную и хранится в базе." + tail,
                  className="text-muted small")


def layout(**kwargs):
    if not auth.is_admin():
        return dbc.Alert("Страница доступна только администраторам.",
                         color="warning", className="m-4")
    try:
        indicators = widgets.indicator_choices()
    except FileNotFoundError as e:
        return dbc.Alert(str(e), color="warning", className="m-4")

    chart_types = widgets.chart_choices()
    sizes = widgets.size_choices()

    return dbc.Container(
        [
            html.H2("Виджеты главного экрана", className="mt-4"),
            html.P(
                "Набор общий для всех: так главную увидят и остальные "
                "сотрудники. Правки применяются сразу — чтобы увидеть их, "
                "откройте главную заново (F5).",
                className="text-muted small",
            ),
            dbc.Row(
                dbc.Col([
                    dbc.Label("Какую страницу настраиваем"),
                    dbc.Select(
                        id="w-page",
                        options=widgets.page_choices(),
                        value=widgets.MAIN_PAGE,
                    ),
                    dbc.FormText(
                        "У главной витрины и у каждого раздела свой набор. "
                        "Правка одного раздела не трогает остальные."
                    ),
                ], md=6),
                class_name="mb-3",
            ),
            html.Div(status_line(widgets.MAIN_PAGE), id="w-status"),
            html.Div(widgets_list(widgets.MAIN_PAGE), id="w-list", className="mb-4"),
            html.H5("Добавить виджет"),
            dbc.Row(
                [
                    dbc.Col([dbc.Label("Показатель"),
                             dbc.Select(id="w-new-indicator", options=indicators,
                                        value=indicators[0]["value"] if indicators else None)],
                            md=4),
                    dbc.Col([dbc.Label("Вид диаграммы"),
                             dbc.Select(id="w-new-chart", options=chart_types,
                                        value=chart_types[0]["value"])],
                            md=4),
                    dbc.Col([dbc.Label("Размер"),
                             dbc.Select(id="w-new-size", options=sizes,
                                        value="medium" if any(s["value"] == "medium" for s in sizes)
                                        else sizes[0]["value"])],
                            md=2),
                    dbc.Col(dbc.Button("Добавить", id="w-add", color="primary",
                                       className="w-100"),
                            md=2, className="align-self-end"),
                ],
                className="g-3 mb-3",
            ),
            dbc.Button("Вернуть набор по умолчанию", id="w-reset",
                       color="secondary", outline=True),
            html.Div(id="w-feedback", className="mt-3 mb-5"),
        ],
        fluid=True,
        className="pb-5",
    )


@callback(
    Output("w-list", "children"),
    Output("w-status", "children"),
    Output("w-feedback", "children"),
    Input("w-add", "n_clicks"),
    Input("w-reset", "n_clicks"),
    Input({"type": "w-up", "index": ALL}, "n_clicks"),
    Input({"type": "w-down", "index": ALL}, "n_clicks"),
    Input({"type": "w-del", "index": ALL}, "n_clicks"),
    Input("w-page", "value"),
    State("w-new-indicator", "value"),
    State("w-new-chart", "value"),
    State("w-new-size", "value"),
    prevent_initial_call=True,
)
def change_structure(_add, _reset, _up, _down, _del, page, indicator, chart, size):
    """Добавить, убрать, переставить, сбросить — всё, что меняет состав списка.

    `ctx.triggered_id` говорит, какую кнопку нажали; проверка значения
    отсеивает «пустые» срабатывания в момент, когда кнопки только появились
    на странице (у них n_clicks = None).
    """
    trigger = ctx.triggered_id
    page = page or widgets.MAIN_PAGE

    # Сменили страницу в списке — просто показываем её набор, ничего не пишем
    if trigger == "w-page":
        return widgets_list(page), status_line(page), None

    clicked = bool(ctx.triggered) and ctx.triggered[0]["value"]
    if not clicked:
        return no_update, no_update, no_update

    author = auth.current_user()
    feedback = no_update
    try:
        if trigger == "w-add":
            widgets.add(chart, indicator, size, author, page)
            feedback = dbc.Alert("Виджет добавлен в конец.", color="success",
                                 className="py-2")
        elif trigger == "w-reset":
            widgets.reset(page)
            feedback = dbc.Alert("Вернули набор из config.yaml.",
                                 color="secondary", className="py-2")
        elif isinstance(trigger, dict):
            if trigger["type"] == "w-del":
                widgets.remove(trigger["index"], author, page)
                feedback = dbc.Alert("Виджет убран.", color="secondary",
                                     className="py-2")
            elif trigger["type"] in ("w-up", "w-down"):
                widgets.move(trigger["index"], 1 if trigger["type"] == "w-down" else -1,
                             author, page)
                feedback = dbc.Alert("Порядок изменён.", color="secondary",
                                     className="py-2")
    except ValueError as e:
        return no_update, no_update, dbc.Alert(str(e), color="danger", className="py-2")
    except Exception as e:
        log.exception("правка набора виджетов не прошла")
        return no_update, no_update, dbc.Alert(f"Не получилось: {e}", color="danger",
                                               className="py-2")

    return widgets_list(page), status_line(page), feedback


@callback(
    Output("w-feedback", "children", allow_duplicate=True),
    Output("w-status", "children", allow_duplicate=True),
    Input({"type": "w-indicator", "index": ALL}, "value"),
    Input({"type": "w-chart", "index": ALL}, "value"),
    Input({"type": "w-size", "index": ALL}, "value"),
    State("w-page", "value"),
    prevent_initial_call=True,
)
def change_field(_indicators, _charts, _sizes, page):
    """Смена показателя, вида или размера у существующего виджета.

    Список НЕ перерисовывается: строка и так уже показывает выбранное,
    а перерисовка снова создала бы эти выпадающие списки и позвала бы
    коллбэк по кругу.

    Сверка с сохранённым значением — вторая защита от того же круга:
    если пришло то, что уже лежит в базе (так бывает, когда список
    перерисовала соседняя правка), делать нечего.
    """
    trigger = ctx.triggered_id
    if not isinstance(trigger, dict) or not ctx.triggered:
        return no_update, no_update

    value = ctx.triggered[0]["value"]
    if value in (None, ""):
        return no_update, no_update

    page = page or widgets.MAIN_PAGE
    field = {"w-indicator": "indicator", "w-chart": "chart", "w-size": "size"}[trigger["type"]]
    current = {item["id"]: item for item in widgets.get_widgets(page)}.get(trigger["index"])
    if current is None:
        return dbc.Alert("Виджет уже удалён — обновите страницу.", color="warning",
                         className="py-2"), no_update
    if current[field] == value:
        return no_update, no_update  # ничего не изменилось

    try:
        widgets.update(trigger["index"], field, value, auth.current_user(), page)
    except ValueError as e:
        return dbc.Alert(str(e), color="danger", className="py-2"), no_update
    except Exception as e:
        log.exception("правка виджета не прошла")
        return dbc.Alert(f"Не получилось: {e}", color="danger", className="py-2"), no_update

    return (
        dbc.Alert("Сохранено. Откройте главную заново, чтобы увидеть.",
                  color="success", className="py-2"),
        status_line(page),
    )
