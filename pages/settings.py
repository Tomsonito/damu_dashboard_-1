"""Настройки оформления: название, цвет, шрифт, размер текста, логотип.

Доступ — только админ (до этапа 5 это заглушка core/auth.py, где админ
каждый). Страница ничего не решает сама: и проверка значений, и запись
живут в core/theme.py, здесь — форма, предпросмотр и передача нажатий.

Две особенности, из-за которых страница устроена именно так:

1. **Предпросмотр без сохранения.** Шрифт и цвет видно в образце сразу
   при выборе — до нажатия «Применить». Так не приходится сохранять
   наугад, а потом откатывать. В образце нарочно есть кириллица, знак ₸
   и разряды: именно на них шрифты и подводят.

2. **После сохранения страница перезагружается.** Переменные CSS
   подставляются в <head> при сборке страницы (app.py), а не коллбэком,
   поэтому новый цвет виден только на свежезагруженной странице.
   Перезагрузку делает dcc.Location, а подтверждение переживает её
   через параметр в адресе — иначе плашка «сохранено» исчезала бы
   вместе со старой страницей.
"""

import logging

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, ctx, dcc, html, no_update

from core import auth, theme

log = logging.getLogger(__name__)

dash.register_page(__name__, path="/settings", name="Настройки",
                   title="Настройки — Дашборд Даму")

PREVIEW_TEXT = "Дашборд Даму · Освоено 1 501,2 млрд ₸ · Согласно плану 78,5 %"


def _field(label: str, control, hint: str = "", width: int = 4) -> dbc.Col:
    """Подпись, элемент управления и пояснение под ним — одинаково у всех."""
    children = [dbc.Label(label), control]
    if hint:
        children.append(dbc.FormText(hint))
    return dbc.Col(children, md=width)


def layout(**kwargs):
    """Форма, заполненная тем, что действует сейчас.

    kwargs — параметры адреса: после сохранения страница возвращается
    сюда с меткой `saved`, и по ней рисуется подтверждение.
    """
    if not auth.is_admin():
        return dbc.Alert("Страница доступна только администраторам.",
                         color="warning", className="m-4")

    current = theme.get_theme()
    changed = theme.last_change()

    notes = []
    if "saved" in kwargs:
        notes.append(dbc.Alert("Оформление применено — так теперь видят сайт все.",
                               color="success", className="py-2"))
    if "reset" in kwargs:
        notes.append(dbc.Alert("Вернулись к умолчаниям из config.yaml.",
                               color="secondary", className="py-2"))
    if changed:
        notes.append(html.P(
            f"Последнее изменение: {changed[0]}, {changed[1]:%d.%m %H:%M}.",
            className="text-muted small",
        ))

    return dbc.Container(
        [
            # Перезагрузка после сохранения — чтобы новые переменные CSS
            # попали в <head>. refresh=True означает полную перезагрузку,
            # а не переход средствами Dash
            dcc.Location(id="settings-reload", refresh=True),
            html.H2("Настройки оформления", className="mt-4"),
            html.P(
                "Настройки общие для всех: сайт увидят так же и остальные "
                "сотрудники. В отличие от плана и данных, оформление "
                "не ждёт 9:00 — оно применяется сразу.",
                className="text-muted small",
            ),
            html.Div(notes),
            dbc.Row(
                [
                    _field(
                        "Название в шапке",
                        dbc.Input(id="set-brand", value=current["brand"],
                                  maxlength=60, type="text"),
                        "до 60 символов",
                    ),
                    _field(
                        "Основной цвет",
                        dbc.Input(id="set-accent", value=current["accent"],
                                  type="color", className="form-control-color"),
                        "кнопки, ссылки, галки и первый цвет диаграмм",
                        width=2,
                    ),
                    _field(
                        "Второй цвет",
                        dbc.Input(id="set-accent-2", value=current["accent_2"],
                                  type="color", className="form-control-color"),
                        "им помечены остальные инструменты на витрине",
                        width=2,
                    ),
                    _field(
                        "Шапка",
                        dbc.Select(id="set-navbar", options=theme.navbar_choices(),
                                   value=current["navbar"]),
                        width=2,
                    ),
                    _field(
                        "Логотип",
                        dbc.Select(id="set-logo", options=theme.logo_choices(),
                                   value=current["logo"] or theme.NO_LOGO),
                        "картинки из папки assets/",
                        width=3,
                    ),
                ],
                className="g-3 mb-3",
            ),
            dbc.Row(
                [
                    _field(
                        "Шрифт",
                        dbc.Select(id="set-font", options=theme.font_choices(),
                                   value=current["font"]),
                        "наборы описаны в config.yaml, блок fonts",
                        width=5,
                    ),
                    _field(
                        "Размер текста",
                        dbc.Select(id="set-scale", options=theme.scale_choices(),
                                   value=current["font_scale"]),
                        "базовый размер, от него считается вся страница",
                        width=4,
                    ),
                ],
                className="g-3 mb-3",
            ),
            html.H5("Как это будет выглядеть", className="mt-4"),
            html.P("Образец меняется сразу при выборе — до сохранения.",
                   className="text-muted small"),
            html.Div(id="set-preview", className="p-3 mb-4 border rounded"),
            dbc.Row(
                [
                    dbc.Col(dbc.Button("Применить", id="set-save", color="primary"),
                            width="auto"),
                    dbc.Col(dbc.Button("Вернуть умолчания", id="set-reset",
                                       color="secondary", outline=True),
                            width="auto"),
                ],
                className="g-2 mb-3",
            ),
            html.Div(id="set-feedback", className="mb-5"),
        ],
        fluid=True,
        className="pb-5",
    )


@callback(
    Output("set-preview", "children"),
    Input("set-brand", "value"),
    Input("set-accent", "value"),
    Input("set-accent-2", "value"),
    Input("set-font", "value"),
    Input("set-scale", "value"),
)
def preview(brand, accent, accent_2, font, scale):
    """Образец текста выбранным шрифтом, размером и цветом — без сохранения.

    Собирается из тех же справочников config.yaml, что и настоящая тема,
    поэтому образец не может «врать» относительно результата.
    """
    fake = {**theme.get_theme(), "font": font, "font_scale": scale}
    stack = theme.font_stack(fake)
    size = theme.base_size(fake)
    accent = accent if theme.COLOR_RE.match(str(accent or "")) else theme.defaults()["accent"]
    accent_2 = (accent_2 if theme.COLOR_RE.match(str(accent_2 or ""))
                else theme.defaults()["accent_2"])

    return html.Div(
        [
            html.Div(brand or "", style={"fontWeight": 800, "fontSize": "1.4rem",
                                         "color": accent}),
            html.Div(PREVIEW_TEXT, className="mt-1"),
            html.Div(
                [
                    html.Button("Кнопка", className="btn",
                                style={"backgroundColor": accent,
                                       "color": theme.readable_on(accent)}),
                    # Три полоски — ровно те три оттенка, которыми красятся
                    # карточки инструментов на главной. Иначе «второй цвет»
                    # оставался бы словами: где он применяется, не видно
                    html.Span("Все инструменты", className="ms-3 px-2 py-1",
                              style={"backgroundColor": accent,
                                     "color": theme.readable_on(accent)}),
                    html.Span("Гарантирование", className="ms-2 px-2 py-1",
                              style={"backgroundColor": accent_2,
                                     "color": theme.readable_on(accent_2)}),
                    html.Span("Субсидирование", className="ms-2 px-2 py-1",
                              style={"backgroundColor": theme.mix(accent_2, "#000000", 0.4),
                                     "color": "#ffffff"}),
                ],
                className="mt-3 d-flex align-items-center flex-wrap gap-1",
            ),
        ],
        style={"fontFamily": stack, "fontSize": size},
    )


@callback(
    Output("settings-reload", "href"),
    Output("set-feedback", "children"),
    Input("set-save", "n_clicks"),
    Input("set-reset", "n_clicks"),
    State("set-brand", "value"),
    State("set-accent", "value"),
    State("set-accent-2", "value"),
    State("set-navbar", "value"),
    State("set-font", "value"),
    State("set-scale", "value"),
    State("set-logo", "value"),
    prevent_initial_call=True,
)
def apply_settings(_save, _reset, brand, accent, accent_2, navbar, font, scale, logo):
    """Сохранение и сброс. Успех — перезагрузка страницы, ошибка — плашка.

    Ошибку показываем без перезагрузки: иначе введённое пропало бы вместе
    со страницей, и админ гадал бы, что именно не понравилось.
    """
    if not auth.is_admin():
        return no_update, dbc.Alert("Только для администраторов.", color="danger",
                                    className="py-2")
    try:
        if ctx.triggered_id == "set-reset":
            theme.reset()
            return "/settings?reset=1", no_update
        theme.save(
            {
                "brand": brand,
                "accent": accent,
                "accent_2": accent_2,
                "navbar": navbar,
                "font": font,
                "font_scale": scale,
                "logo": logo or "",
            },
            auth.current_user(),
        )
        return "/settings?saved=1", no_update
    except ValueError as e:
        # Не прошло проверку — текст ошибки написан для человека
        return no_update, dbc.Alert(str(e), color="danger", className="py-2")
    except Exception as e:
        log.exception("настройки оформления не сохранились")
        return no_update, dbc.Alert(f"Не получилось сохранить: {e}",
                                    color="danger", className="py-2")
