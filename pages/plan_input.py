"""Ввод плана и управление публикацией. Доступ — только админ.

Три раздела:
- форма: показатель + год + значение -> черновик с автором и временем;
- «Черновик»: что ждёт ближайших 9:00 и ещё может быть отменено;
- версии данных из БД: какие снимки ждут публикации, вето и его снятие.

Сама механика сроков и статусов живёт в core/publish.py — страница только
показывает состояние и передаёт нажатия. До этапа 5 «только админ» держится
на заглушке core/auth.py: в разработке админ каждый.
"""

import logging
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from core import auth, data, publish

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/plan", name="Ввод плана",
                   title="Ввод плана — Дашборд Даму")


def plan_indicators() -> list[dict]:
    """Показатели, для которых имеет смысл вводить план.

    Не все подряд, а те, которые реестр называет знаменателем производной
    карточки, — только их витрина сегодня использует («Согласно плану %»
    делит факт на план). Список собирается из config.yaml, а не перечислен
    словами: появится новая производная карточка — её знаменатель попадёт
    сюда сам, без правки страницы.
    """
    cfg = data.load_config()
    denominators: list[str] = []
    for meta in cfg["indicators"].values():
        spec = meta.get("derived")
        if spec and spec["denominator"] not in denominators:
            denominators.append(spec["denominator"])
    return [
        {"label": cfg["indicators"][key]["title"], "value": key}
        for key in denominators
        if key in cfg["indicators"]
    ]


def _fmt_when(ts) -> str:
    return pd.to_datetime(ts).strftime("%d.%m %H:%M")


def _value_text(value: float, indicator: str) -> str:
    """Значение плана в том же виде, что и на карточках витрины."""
    try:
        return data.format_value(value, indicator)
    except KeyError:  # показатель пропал из реестра — покажем как есть
        return str(value)


def _indicator_title(indicator: str) -> str:
    meta = data.load_config()["indicators"].get(indicator, {})
    return meta.get("title", indicator)


def drafts_table():
    df = publish.get_plan_rows(publish.PLAN_DRAFT)
    if df.empty:
        return html.P("Черновиков нет.", className="text-muted small")

    head = html.Thead(html.Tr([html.Th(h) for h in
        ["Показатель", "Год", "Значение", "Автор", "Сохранён", "Опубликуется", ""]]))
    rows = []
    for r in df.itertuples():
        when = publish.describe_publish_time(
            publish.next_publish_time(pd.to_datetime(r.updated_at).to_pydatetime())
        )
        rows.append(html.Tr([
            html.Td(_indicator_title(r.indicator)),
            html.Td(str(int(r.period_year))),
            html.Td(_value_text(r.value, r.indicator)),
            html.Td(r.author),
            html.Td(_fmt_when(r.updated_at)),
            html.Td(when),
            html.Td(dbc.Button(
                "Отменить",
                id={"type": "plan-cancel", "index": f"{r.indicator}|{int(r.period_year)}"},
                size="sm", color="danger", outline=True,
            )),
        ]))
    return dbc.Table([head, html.Tbody(rows)], hover=True, size="sm",
                     className="align-middle")


def published_table():
    df = publish.get_plan_rows(publish.PLAN_PUBLISHED)
    if df.empty:
        return html.P("Опубликованного плана пока нет — витрина считает "
                      "«Согласно плану %» от фактов, как раньше.",
                      className="text-muted small")

    head = html.Thead(html.Tr([html.Th(h) for h in
        ["Показатель", "Год", "Значение", "Автор", "Опубликован"]]))
    rows = [
        html.Tr([
            html.Td(_indicator_title(r.indicator)),
            html.Td(str(int(r.period_year))),
            html.Td(_value_text(r.value, r.indicator)),
            html.Td(r.author),
            html.Td(_fmt_when(r.published_at)),
        ])
        for r in df.itertuples()
    ]
    return dbc.Table([head, html.Tbody(rows)], hover=True, size="sm",
                     className="align-middle")


def versions_table():
    df = publish.list_versions(10)
    if df.empty:
        return html.P("Версий пока нет — запустите python -m etl.run.",
                      className="text-muted small")

    head = html.Thead(html.Tr([html.Th(h) for h in
        ["Версия", "Разобрана", "Строк", "Статус", ""]]))
    rows = []
    for r in df.itertuples():
        status = publish.STATUS_LABELS.get(r.status, r.status)
        action = ""
        if r.status == publish.VER_PENDING:
            when = publish.describe_publish_time(
                publish.next_publish_time(pd.to_datetime(r.run_at).to_pydatetime())
            )
            status = f"{status} — выйдет {when}"
            action = dbc.Button(
                "Забраковать",
                id={"type": "ver-reject", "index": int(r.version)},
                size="sm", color="danger", outline=True,
            )
        elif r.status == publish.VER_REJECTED:
            action = dbc.Button(
                "Снять вето",
                id={"type": "ver-restore", "index": int(r.version)},
                size="sm", color="secondary", outline=True,
            )
        elif r.status == publish.VER_PUBLISHED and not pd.isna(r.published_at):
            status = f"{status} {_fmt_when(r.published_at)}"
        rows.append(html.Tr([
            html.Td(str(int(r.version))),
            html.Td(_fmt_when(r.run_at)),
            html.Td(f"{int(r.facts_rows):,}".replace(",", " ")),
            html.Td(status),
            html.Td(action),
        ]))
    return dbc.Table([head, html.Tbody(rows)], hover=True, size="sm",
                     className="align-middle")


def layout(**kwargs):
    if not auth.is_admin():
        return dbc.Alert("Страница доступна только администраторам.",
                         color="warning", className="m-4")

    indicators = plan_indicators()
    return dbc.Container(
        [
            html.H2("Ввод плана", className="mt-4"),
            html.P(
                "Правки не попадают на сайт сразу: черновик публикуется "
                "в ближайшие 9:00, до этого его можно отменить. "
                "Публикация идёт каждый день, включая выходные.",
                className="text-muted small",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Label("Показатель"),
                            dbc.Select(
                                id="plan-indicator",
                                options=indicators,
                                value=indicators[0]["value"] if indicators else None,
                            ),
                        ],
                        md=4,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Год"),
                            dbc.Input(id="plan-year", type="number",
                                      value=datetime.now().year,
                                      min=2000, max=2100, step=1),
                        ],
                        md=2,
                    ),
                    dbc.Col(
                        [
                            dbc.Label("Значение годового плана"),
                            dbc.Input(id="plan-value", type="number", min=0,
                                      placeholder="число ≥ 0"),
                            dbc.FormText(id="plan-unit"),
                        ],
                        md=3,
                    ),
                    dbc.Col(
                        dbc.Button("Сохранить черновик", id="plan-save",
                                   color="primary", className="w-100"),
                        md=3, className="align-self-end",
                    ),
                ],
                className="g-3 mb-2",
            ),
            html.Div(id="plan-feedback", className="mb-4"),
            html.H4("Черновик — ещё можно отменить"),
            html.Div(id="plan-drafts", className="mb-4"),
            html.H4("Опубликованный план"),
            html.Div(id="plan-published", className="mb-4"),
            html.H4("Версии данных из БД"),
            html.P(
                "Свежая версия публикуется сама в ближайшие 9:00. "
                "«Забраковать» — версия не выйдет, сайт продолжит показывать "
                "прежнюю; исправлять надо источник, а не дашборд. "
                "«Снять вето» — версия опубликуется при ближайшей проверке.",
                className="text-muted small",
            ),
            html.Div(id="version-list", className="mb-5"),
            dcc.Interval(id="plan-poll", interval=30 * 1000),
        ],
        fluid=True,
        className="pb-5",
    )


def _save(indicator, year, value):
    """Проверка и сохранение черновика; возвращает плашку-ответ для формы."""
    if not indicator:
        return dbc.Alert("Выберите показатель.", color="danger", className="py-2")
    if year is None or not 2000 <= int(year) <= 2100:
        return dbc.Alert("Год выглядит странно — проверьте.", color="danger",
                         className="py-2")
    if value is None:
        return dbc.Alert("Введите значение плана.", color="danger", className="py-2")
    if float(value) < 0:
        return dbc.Alert("План не может быть отрицательным.", color="danger",
                         className="py-2")

    when = publish.save_draft(indicator, int(year), float(value), auth.current_user())
    return dbc.Alert(
        f"Черновик сохранён — опубликуется "
        f"{publish.describe_publish_time(when)}. До этого его можно отменить ниже.",
        color="success", className="py-2",
    )


@callback(
    Output("plan-unit", "children"),
    Input("plan-indicator", "value"),
)
def show_unit(indicator):
    """Единица измерения под полем значения — из реестра, не из головы."""
    if not indicator:
        return ""
    meta = data.get_indicator_meta(indicator)
    return f"в единицах источника: {meta['unit']}"


@callback(
    Output("plan-feedback", "children"),
    Output("plan-drafts", "children"),
    Output("plan-published", "children"),
    Output("version-list", "children"),
    Input("plan-save", "n_clicks"),
    Input({"type": "plan-cancel", "index": ALL}, "n_clicks"),
    Input({"type": "ver-reject", "index": ALL}, "n_clicks"),
    Input({"type": "ver-restore", "index": ALL}, "n_clicks"),
    Input("plan-poll", "n_intervals"),
    State("plan-indicator", "value"),
    State("plan-year", "value"),
    State("plan-value", "value"),
)
def handle_actions(_save_clicks, _cancel, _reject, _restore, _tick,
                   indicator, year, value):
    """Один коллбэк на все действия страницы — и на её периодическое обновление.

    Кто бы ни сработал — кнопка формы, «Отменить» у черновика, вето,
    таймер — в конце всё равно перерисовываются все три списка, поэтому
    разбирать источник нажатия нужно только действиям. `ctx.triggered_id`
    говорит, что нажали; проверка значения отсеивает «пустые» срабатывания
    при первой отрисовке кнопок.
    """
    trigger = ctx.triggered_id
    clicked = bool(ctx.triggered) and ctx.triggered[0]["value"]
    feedback = no_update

    try:
        if trigger == "plan-save" and clicked:
            feedback = _save(indicator, year, value)
        elif isinstance(trigger, dict) and clicked:
            if trigger["type"] == "plan-cancel":
                draft_indicator, draft_year = trigger["index"].split("|")
                publish.delete_draft(draft_indicator, int(draft_year))
                feedback = dbc.Alert("Черновик отменён.", color="secondary",
                                     className="py-2")
            elif trigger["type"] == "ver-reject":
                publish.reject_version(trigger["index"])
                feedback = dbc.Alert(
                    f"Версия {trigger['index']} забракована — публиковаться "
                    "не будет, сайт показывает прежнюю.",
                    color="secondary", className="py-2",
                )
            elif trigger["type"] == "ver-restore":
                publish.restore_version(trigger["index"])
                feedback = dbc.Alert(
                    f"Вето снято — версия {trigger['index']} опубликуется "
                    "при ближайшей проверке.",
                    color="secondary", className="py-2",
                )
    except Exception as e:
        log.exception("действие на странице плана не прошло")
        feedback = dbc.Alert(f"Не получилось: {e}", color="danger", className="py-2")

    # Шлюз публикации дышит и отсюда: админ может сидеть только на этой
    # странице, и 9:00 должны сработать без открытой главной
    try:
        published = publish.publish_due()
        if published:
            log.info("опубликовано: %s", published)
    except Exception:
        log.exception("публикация дозревшего не прошла — попробуем через 30 сек")

    return feedback, drafts_table(), published_table(), versions_table()
