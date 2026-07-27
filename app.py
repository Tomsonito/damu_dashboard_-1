import logging
import os

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from core import auth, data, publish, theme, widgets
from core.cache import cache

# Без этой настройки log.info(...) со страниц молча пропадает: у Python
# уровень по умолчанию WARNING. А след «опубликовано: версия данных N»
# должен оставаться в консоли сервера — это журнал шлюза 9:00.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)

class ThemedDash(dash.Dash):
    """Dash, который подмешивает настройки оформления в <head> страницы.

    Зачем понадобилось наследование. Цвет и шрифт лежат в базе и меняются
    админом на ходу, а обычные стили — статический файл assets/custom.css,
    который на каждый запрос не перепишешь. Dash собирает страницу методом
    interpolate_index, и это единственная точка, где можно добавить
    в <head> что-то своё, посчитанное прямо сейчас.

    Так CSS-переменные (`--damu-accent` и прочие) оказываются в странице,
    а правила, которые их читают, остаются в custom.css.

    Тонкость Dash 4: html.Style как компонента не существует (проверено),
    поэтому вставить <style> внутрь layout нельзя — только сюда.
    Строка добавляется ПОСЛЕ ссылок на стили, значит переменные видны всем.
    """

    def interpolate_index(self, **kwargs):
        try:
            kwargs["css"] = kwargs.get("css", "") + theme.style_tag()
        except Exception:
            # Настройки не прочитались (хранилище занято, файла ещё нет) —
            # страница обязана открыться: в custom.css у каждой переменной
            # есть запасное значение, сайт будет в цветах по умолчанию
            log.exception("оформление не прочиталось — рисуем в умолчаниях")
        return super().interpolate_index(**kwargs)


app = ThemedDash(
    __name__,
    use_pages=True,
    # Коллбэки страниц ссылаются на поля, которых на других страницах нет
    # (карточки раздела, сетка витрины). Dash проверяет это по стартовой
    # разметке и ругался в консоль браузера на каждый переход. Флаг говорит
    # «проверяй в момент вызова, а не заранее» — обычное дело для сайта
    # из нескольких страниц с собственными коллбэками.
    suppress_callback_exceptions=True,
    # Стили Bootstrap лежат локально — assets/bootstrap.min.css, Dash
    # раздаёт эту папку сам. Здесь раньше стояло
    # external_stylesheets=[dbc.themes.BOOTSTRAP], а это ссылка на
    # cdn.jsdelivr.net: во внутренней сети без интернета файл не загрузился
    # бы и вёрстка развалилась — сетка исчезает, карточки вытягиваются
    # в столбик во всю ширину (проверено отключением стиля в браузере).
    # Тот же принцип, что у шрифтов и файла границ карты: всё своё возим с собой.
    #
    # !! Версия файла — 5.3.6, ровно та, на которую указывает пакет
    # dash-bootstrap-components 2.0.4. Связь пакета с файлом теперь ручная:
    # обновите пакет — обновите и файл, иначе они разойдутся МОЛЧА, без ошибки.
    # Куда смотрит пакет, видно так:
    #   python -c "import dash_bootstrap_components as dbc; print(dbc.themes.BOOTSTRAP)"
)

server = app.server

# Подключить кэш к Flask-приложению сайта. Без этого flask-caching внутри
# запроса не находит кэш и МОЛЧА работает без него: страница живёт, но
# каждый клик заново читает диск. Проверять — по логу сервера: там были бы
# строки «Exception possibly due to cache backend».
cache.init_app(server)

# Хранилище могло остаться со схемы до этапа 4 — довести до текущей
# (статусы версий, таблица plan). Повторный вызов ничего не меняет,
# без файла — тихо выходит. Упавшая миграция сайт не роняет: страницы
# сами покажут, что с данными, а причина останется в логе.
try:
    publish.migrate()
    widgets.migrate()
except Exception:
    log.exception("миграция хранилища на старте не прошла")


def header():
    """Верхняя полоса: логотип слева, общие фильтры справа.

    Фильтры живут здесь, а не на страницах, и это главное решение каркаса:
    компоненты каркаса Dash не пересобирает при переходе между страницами,
    поэтому выбранные год и регионы **переживают переход**. Выбрали 2025-й
    и три области — они действуют и на главной, и в любом разделе.
    """
    settings = theme.get_theme()

    brand = []
    if settings["logo"]:
        brand.append(html.Img(
            src=dash.get_asset_url(settings["logo"]),
            className="damu-logo",
            alt="",  # рядом стоит название — для читалки экрана картинка лишняя
        ))
    brand.append(html.Div(settings["brand"], className="damu-brand"))

    try:
        years = data.get_years()
        regions = data.get_region_choices()
        updated = data.get_last_update()
    except Exception:
        # Хранилища нет или оно занято — каркас обязан открыться,
        # а страница внутри сама покажет понятную подсказку
        return html.Div(html.Div(brand, className="damu-brand-box"),
                        className="damu-header")

    filters = dbc.Row(
        [
            dbc.Col([
                dbc.Label("Отчётный год", class_name="small mb-1"),
                dbc.Select(
                    id="filter-year",
                    options=[{"label": str(y), "value": y} for y in years],
                    value=years[0],
                    size="sm",
                ),
            ], xs=6, md=2),
            dbc.Col([
                dbc.Label("Регионы (пусто = все)", class_name="small mb-1"),
                dcc.Dropdown(
                    id="filter-regions",
                    options=regions,
                    multi=True,
                    placeholder="Все регионы",
                ),
            ], xs=12, md=6),
            dbc.Col([
                html.Div("данные обновлены", className="small text-muted"),
                html.Div(updated, id="data-updated", className="fw-semibold"),
            ], xs=6, md=4, class_name="text-md-end"),
        ],
        class_name="g-2 align-items-end flex-grow-1",
    )

    return html.Div(
        [html.Div(brand, className="damu-brand-box"), filters],
        className="damu-header",
    )


def tabs_bar():
    """Полоса вкладок под фильтрами: несколько разделов + «Все разделы».

    Наверху висят только те разделы, куда ходят чаще всего (список
    `main_tabs` в `config.yaml`) — их четыре, и полоса остаётся читаемой.
    Двадцать вкладок в ряд не поместились бы и превратились бы в кашу.

    Остальные разделы не спрятаны: кнопка справа открывает **поверх
    страницы** полный список, из него и выбирают, куда перейти.
    """
    cfg = data.load_config()
    sections = {s["key"]: s for s in cfg.get("sections") or []}

    items = [dbc.NavLink("Главная", href="/", active="exact")]
    for key in cfg.get("main_tabs") or []:
        section = sections.get(key)
        if section:
            items.append(dbc.NavLink(
                section["title"], href=f"/section/{key}", active="exact",
            ))

    return html.Div(
        [
            dbc.Nav(items, pills=True, class_name="damu-tabs-nav"),
            # Кнопка полного списка — отдельной строкой под вкладками
            # и во всю их ширину: так её видно сразу, а не как мелкую
            # кнопку с краю
            dbc.Button("Все разделы ▾", id="open-sections",
                       class_name="damu-all-sections"),
        ],
        className="damu-tabs",
    )


def sections_modal():
    """Полный список разделов — всплывает поверх страницы.

    Раздел, под которым ещё нет данных, приглушён: лучше честно показать,
    что там пусто, чем дать человеку обойти пять пустых страниц и решить,
    что дашборд сломан.

    Ссылки помечены общим типом id — по нажатию любой из них окно
    закрывается (см. коллбэк ниже). Иначе оно осталось бы висеть поверх
    только что открытого раздела.
    """
    try:
        with_data = set(data.get_programs())
    except Exception:
        with_data = set()

    links = []
    for section in data.load_config().get("sections") or []:
        empty = section["title"] not in with_data
        links.append(dbc.Col(
            dbc.NavLink(
                section["title"],
                href=f"/section/{section['key']}",
                id={"type": "section-link", "index": section["key"]},
                class_name="damu-modal-link" + (" damu-empty" if empty else ""),
            ),
            xs=12, sm=6, md=4,
        ))

    # !! Приставка «служ-» обязательна: ключи разделов и служебных страниц
    # живут в одном пространстве имён, а у раздела «План освоения» ключ
    # `plan` — ровно как у страницы ввода плана. Без приставки Dash падал
    # с DuplicateIdError ещё до отрисовки (поймано запуском).
    service = [
        dbc.NavLink("Разбор — один график на выбор", href="/explore",
                    id={"type": "section-link", "index": "служ-explore"}),
    ]
    if auth.is_admin():
        service += [
            dbc.NavLink("Ввод плана", href="/plan",
                        id={"type": "section-link", "index": "служ-plan"}),
            dbc.NavLink("Виджеты", href="/widgets",
                        id={"type": "section-link", "index": "служ-widgets"}),
            dbc.NavLink("Настройки", href="/settings",
                        id={"type": "section-link", "index": "служ-settings"}),
        ]

    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Разделы")),
            dbc.ModalBody([
                dbc.Row(links, class_name="g-1"),
                html.Hr(),
                html.Div("Служебные страницы", className="text-muted small mb-1"),
                dbc.Nav(service, vertical=True),
            ]),
        ],
        id="sections-modal", size="lg", scrollable=True, is_open=False,
    )


@callback(
    Output("sections-modal", "is_open"),
    Input("open-sections", "n_clicks"),
    Input({"type": "section-link", "index": ALL}, "n_clicks"),
    State("sections-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_sections(_open, _links, is_open):
    """Кнопка открывает список, выбор раздела — закрывает."""
    trigger = ctx.triggered_id
    if trigger == "open-sections":
        return not is_open
    return False


def serve_layout():
    """Каркас собирается на каждый запрос: состав меню зависит от роли.

    Зрителю служебные ссылки не показываем. До этапа 5 роль отдаёт заглушка
    core/auth.py (в разработке админ каждый), но каркас уже сейчас спрашивает
    её, а не решает сам — LDAP подставится без правок здесь. Сами страницы
    тоже проверяют роль: спрятанная ссылка — удобство, а не защита,
    адрес можно набрать руками.

    Здесь же живут невидимые части, общие для всего сайта: таймер свежести
    и запомненная версия данных. Раньше они лежали на главной, и при уходе
    с неё автообновление переставало работать.
    """
    return html.Div([
        dcc.Interval(id="data-poll", interval=30 * 1000),
        dcc.Store(id="data-version", data=_safe_version()),
        header(),
        tabs_bar(),
        sections_modal(),
        html.Div(
            [
                html.Div(id="publish-banner"),
                dash.page_container,
            ],
            className="damu-content",
        ),
    ])


def _safe_version() -> str:
    """Версия данных для Store; без хранилища — пусто, а не падение."""
    try:
        return data.get_display_version()
    except Exception:
        return ""


@callback(
    Output("data-version", "data"),
    Output("data-updated", "children"),
    Output("publish-banner", "children"),
    Input("data-poll", "n_intervals"),
    State("data-version", "data"),
)
def poll_version(_, known_version):
    """Раз в 30 сек: публикует дозревшее и сверяет версию данных.

    Переехало сюда из pages/main.py вместе с таймером: теперь свежесть
    сторожится на любой странице, а не только на витрине.

    Сначала шлюз: publish_due() выпускает всё, чей срок наступил, — так
    ровно в первый опрос после 9:00 (или после подъёма сервера) публикация
    и происходит, отдельного планировщика нет. В холостую это два дешёвых
    чтения. Совпала версия — `no_update`, ничего не перерисовывается.
    """
    try:
        published = publish.publish_due()
        if published:
            log.info("опубликовано: %s", published)
    except Exception:
        log.exception("публикация дозревшего не прошла — попробуем через 30 сек")

    try:
        fresh = data.get_display_version()
        banner = publish_banner()
        if known_version is not None and str(known_version) == fresh:
            return no_update, no_update, banner
        return fresh, data.get_last_update(), banner
    except Exception:
        return no_update, no_update, None


def publish_banner():
    """Плашка «что ждёт публикации в 9:00» — видит только админ.

    Без неё окно на вето существовало бы только на бумаге. Зрителям плашка
    не показывается — им незачем знать про кухню публикации.
    """
    if not auth.is_admin():
        return None
    try:
        pending = publish.pending_summary()
    except Exception:
        return None

    parts = []
    if pending["version"] is not None:
        when = publish.describe_publish_time(
            publish.next_publish_time(pending["version_run_at"])
        )
        parts.append(
            f"версия данных {pending['version']} "
            f"(разобрана {pending['version_run_at']:%H:%M}) — выйдет {when}"
        )
    if pending["drafts"]:
        parts.append(f"черновиков плана: {pending['drafts']}")
    if not parts:
        return None

    return dbc.Alert(
        [
            html.Span("Ждёт публикации: " + "; ".join(parts) + ". "),
            dcc.Link("Отменить или забраковать — на странице «Ввод плана»", href="/plan"),
        ],
        color="info", className="py-2 small mb-0",
    )


app.layout = serve_layout

if __name__ == "__main__":
    # !! debug берётся из переменной окружения и по умолчанию ВЫКЛЮЧЕН.
    # debug=True поднимает отладчик Werkzeug, а он при падении даёт
    # интерактивную Python-консоль прямо в браузере — на боевом сервере это
    # дыра (кто угодно вызовет ошибку и получит консоль). Поэтому включается
    # только явно: DASHBOARD_DEBUG=1 python app.py — для локальной разработки.
    #
    # На сервере (этап 5) сайт вообще поднимает Gunicorn, а не этот блок:
    # он импортирует объект `server`, и ветка `__main__` не исполняется —
    # но пусть безопасное значение будет и здесь, на случай ручного запуска.
    #
    # dev_tools_hot_reload=False — иначе Dash перезагружает страницу при любой
    # правке файла, и выбранные фильтры слетают. Правки кода видны по F5.
    debug = os.getenv("DASHBOARD_DEBUG", "") == "1"
    app.run(debug=debug, dev_tools_hot_reload=False)
