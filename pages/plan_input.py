"""Ввод плана и управление публикацией. Доступ — только админ.

!! **Формы ввода на странице сейчас НЕТ** (убрана 04.08.2026). Пользователь
переосмысливает, как план вообще должен вводиться, и до решения страница
работает только на показ и на управление публикацией. Практическое
следствие, о котором важно помнить: **таблица `plan` ничем не наполняется**,
поэтому «Согласно плану %» всегда считается от фактов, а ветка «есть ручной
план» в `data.get_kpi` сейчас недостижима и ничем не проверяется.

`publish.save_draft()` при этом жива и рабочая — просто её никто не зовёт.
Когда форма вернётся, писать заново её не придётся.

Что на странице осталось:
- «Черновик»: что ждёт ближайших 9:00 и ещё может быть отменено;
- опубликованный план: что уже действует;
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

from core import admin, auth, data, publish

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

    return dbc.Container(
        [
            admin.tabs("/plan"),
            html.H2("Ввод плана", className="mt-3"),
            html.P(
                "Правки не попадают на сайт сразу: черновик публикуется "
                "в ближайшие 9:00, до этого его можно отменить. "
                "Публикация идёт каждый день, включая выходные.",
                className="text-muted small",
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


@callback(
    Output("plan-feedback", "children"),
    Output("plan-drafts", "children"),
    Output("plan-published", "children"),
    Output("version-list", "children"),
    Input({"type": "plan-cancel", "index": ALL}, "n_clicks"),
    Input({"type": "ver-reject", "index": ALL}, "n_clicks"),
    Input({"type": "ver-restore", "index": ALL}, "n_clicks"),
    Input("plan-poll", "n_intervals"),
)
@auth.admin_only
def handle_actions(_cancel, _reject, _restore, _tick):
    """Один коллбэк на все действия страницы — и на её периодическое обновление.

    Кто бы ни сработал — «Отменить» у черновика, вето, таймер — в конце
    всё равно перерисовываются все три списка. `ctx.triggered_id` говорит,
    что нажали.

    `!!` `@admin_only` закрывает коллбэк ЦЕЛИКОМ, вместе с обновлением
    по таймеру, и это правильно: страница админская, и у зрителя нет
    законного повода сюда стучаться — ни ради отмены черновика, ни ради
    перерисовки списков. Отсюда же дышит шлюз публикации (`publish_due`
    ниже), так что пускать в тело кого попало тем более незачем.
    """
    trigger = ctx.triggered_id
    clicked = bool(ctx.triggered) and ctx.triggered[0]["value"]
    feedback = no_update

    try:
        if isinstance(trigger, dict) and clicked:
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
