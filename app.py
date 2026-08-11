import logging
import os

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update

from core import auth, data, examples, publish, theme, widgets
from core.cache import cache, sweep as sweep_cache

# Без этой настройки log.info(...) со страниц молча пропадает: у Python
# уровень по умолчанию WARNING. А след «опубликовано: версия данных N»
# должен оставаться в консоли сервера — это журнал шлюза 9:00.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)

#: Крошечный скрипт, который ставит тёмную тему ДО первой отрисовки.
#:
#: !! Он обязан быть именно здесь, в <head>, и обязан быть синхронным.
#: Выбор тёмной темы живёт в браузере (localStorage), сервер о нём не знает
#: и отдаёт всем одинаковую страницу. Если ставить класс из dashboard.js,
#: который грузится после стилей, человек с тёмной темой на долю секунды
#: увидит светлый экран — то самое неприятное мигание при каждом переходе.
#: Пять строк в <head> его убирают.
#:
#: try/catch нужен: в приватном режиме некоторых браузеров обращение
#: к localStorage бросает исключение, и без перехвата сломалась бы вся
#: страница ради необязательной настройки.
THEME_BOOT = """
<script>
(function () {
  try {
    if (localStorage.getItem('damu-theme') === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  } catch (e) { /* localStorage недоступен — остаёмся в светлой теме */ }
}());
</script>
"""


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
        kwargs["css"] = kwargs.get("css", "") + THEME_BOOT
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

# Убрать накопившиеся записи кэша, пока не влезет в лимит. Здесь, при старте,
# а не по таймеру: сайт поднимают и гасят, отдельного сторожа заводить не под
# что. Удалять записи безопасно — кэш выводится из хранилища и наполняется
# сам (см. `core/cache.py`, `sweep`).
try:
    sweep_cache()
except Exception:
    log.exception("чистка кэша при старте не удалась")

# Хранилище могло остаться со схемы до этапа 4 — довести до текущей
# (статусы версий, таблица plan). Повторный вызов ничего не меняет,
# без файла — тихо выходит. Упавшая миграция сайт не роняет: страницы
# сами покажут, что с данными, а причина останется в логе.
try:
    publish.migrate()
    widgets.migrate()
except Exception:
    log.exception("миграция хранилища на старте не прошла")


#: Иконки переключателя темы. Рисуются картинкой (data-URI), потому что
#: SVG-компонентов в Dash нет, а сторонний пакет — чужой код, который однажды
#: отстанет от новой версии Dash. Цвет вшит в каждую иконку: показывается
#: всегда ровно одна из двух, и каждая знает, на каком фоне окажется.
_SUN = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" '
        'stroke="%23b08a2e" stroke-width="1.4" stroke-linecap="round">'
        '<circle cx="8" cy="8" r="3.1"/><path d="M8 1.2v1.5M8 13.3v1.5M1.2 8h1.5'
        'M13.3 8h1.5M3.2 3.2l1.1 1.1M11.7 11.7l1.1 1.1M12.8 3.2l-1.1 1.1'
        'M4.3 11.7l-1.1 1.1"/></svg>')
_MOON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" '
         'stroke="%23e2c274" stroke-width="1.4" stroke-linecap="round" '
         'stroke-linejoin="round"><path d="M13.2 10.1A5.6 5.6 0 0 1 5.9 2.8'
         'a5.6 5.6 0 1 0 7.3 7.3Z"/></svg>')


def theme_toggle():
    """Кнопка «солнце / луна» — личный выбор светлой или тёмной темы.

    Выбор **у каждого свой** и живёт в браузере (localStorage), а не в общих
    настройках сайта: оформление на странице «Настройки» задаёт админ сразу
    всем семидесяти, а тёмная тема — дело вкуса и освещения на рабочем месте.

    Обе иконки лежат в разметке всегда, нужную показывает CSS по атрибуту
    `data-theme`. Так переключение не ждёт сервер: класс меняется в браузере,
    и вместе с ним меняется иконка.
    """
    return html.Button(
        [
            html.Img(src="data:image/svg+xml;charset=utf-8," + _SUN,
                     className="damu-theme-sun", alt=""),
            html.Img(src="data:image/svg+xml;charset=utf-8," + _MOON,
                     className="damu-theme-moon", alt=""),
        ],
        id="damu-theme-toggle",
        className="damu-theme-toggle",
        title="Переключить светлую и тёмную тему",
        **{"aria-label": "Переключить тему", "data-theme-toggle": "1"},
    )


def navbar():
    """Верхняя полоса навигации — как в макете.

    Слева название и логотип, справа ссылки, метка роли и меню админа.
    Полосы вкладок с разделами здесь больше нет: разделов двадцать,
    в ряд они не помещались, а в макете переход между ними живёт
    в списке слева на самой странице раздела. Наверху осталась кнопка
    «Разделы ▾», открывающая полный список поверх страницы.
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

    items = [
        html.Div(brand, className="damu-brand-box"),
        dbc.NavLink("Главная", href="/", active="exact", class_name="nav-link"),
        # «Разбор» — меню, а не одна ссылка: пока на нём выбирают раскладку
        # из шести примеров, и прыгать между ними через список каждый раз
        # неудобно. Первый пункт ведёт на сам список.
        dbc.DropdownMenu(
            label="Разбор",
            nav=True,
            class_name="damu-nav-menu",
            children=[
                dbc.DropdownMenuItem("Все примеры", href="/explore"),
                dbc.DropdownMenuItem(divider=True),
                *[dbc.DropdownMenuItem(f"{e['title']} — {e['note']}",
                                       href=f"/explore/{e['key']}")
                  for e in examples.EXAMPLES],
            ],
        ),
        # Кнопка, а не ссылка: список разделов всплывает поверх страницы,
        # никуда не уводя (см. sections_modal ниже)
        html.Button("Разделы ▾", id="open-sections", className="damu-nav-link"),
        theme_toggle(),
    ]

    if auth.is_admin():
        items.append(html.Span("Администратор", className="damu-tag"))
        # Один пункт вместо выпадающего меню из трёх: ввод плана, виджеты
        # и оформление — это одно место, и человек должен видеть его одним.
        # Внутри они разложены по вкладкам (core/admin.py).
        items.append(dbc.NavLink("Настройки", href="/settings",
                                 class_name="nav-link"))

    try:
        updated_date, updated_time = data.get_last_update_parts()
    except Exception:
        updated_date, updated_time = "", ""

    items.append(
        html.Div([
            html.Div("Данные обновлены", className="damu-updated-label"),
            html.Div([
                html.Span(className="damu-live-dot"),
                html.Span(updated_date, id="data-updated"),
            ], className="damu-updated-value"),
            html.Div(updated_time, id="data-updated-time",
                     className="damu-updated-time"),
        ], className="damu-updated")
    )

    # data-navbar читает CSS: на тёмной шапке подсветка ссылки идёт светлым,
    # а не основным цветом — зелёный на почти чёрном не читается
    return html.Div(items, className="damu-nav",
                    **{"data-navbar": settings["navbar"]})


def filters_bar():
    """Скрытый ряд фильтров: года и регионов.

    !! **На экране его НЕТ** — от видимых фильтров отказались, у блока стоит
    `display: none`. Но сами компоненты остаются в разметке, и убрать их
    нельзя: на `filter-year` и `filter-regions` завязаны входы почти всех
    коллбэков (карточки, виджеты разделов, карта). Пропадут элементы —
    Dash не найдёт вход и уронит коллбэк целиком.

    Из этого следует то, о чём легко забыть: **год не «по умолчанию»,
    а единственный.** Переключить его на сайте нечем, поэтому показатели
    со своим последним годом видны только благодаря подстановке
    (`data.resolve_year`), а какой год на экране — говорит подпись
    в заголовке диаграммы и строка на карточке.

    Фильтры живут в каркасе, а не на страницах: компоненты каркаса Dash
    не пересобирает при переходе между страницами, поэтому значение
    переживает переход.
    """
    try:
        years = data.get_years()
        regions = data.get_region_choices()
    except Exception:
        years = [2026]
        regions = []

    return html.Div(
        [
            dbc.Select(
                id="filter-year",
                options=[{"label": str(y), "value": y} for y in years],
                # Свежий год из данных, а не вписанный числом. Здесь стояло
                # `2025 if 2025 in years else ...` — затычка на время, пока
                # у части разрезов не было данных за 2026 и вкладки выходили
                # пустыми. Пустоту теперь лечит подстановка года в самих
                # диаграммах (`data.resolve_year`), каждая по своему
                # показателю, а фильтр снова показывает самое свежее
                value=years[0] if years else None,
            ),
            dcc.Dropdown(
                id="filter-regions",
                options=regions,
                multi=True,
            ),
            html.Button("Сбросить", id="reset-filters"),
        ],
        style={"display": "none"},
    )



@callback(
    Output("filter-year", "value"),
    Output("filter-regions", "value"),
    Input("reset-filters", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_clicks):
    """Возврат к виду «свежий год, все регионы».

    Год берётся первым из списка (он же самый свежий), регионы очищаются —
    пустой список у нас всегда значит «все», отдельного пункта «Все» нет.
    """
    try:
        years = data.get_years()
    except Exception:
        return no_update, None
    return (years[0] if years else no_update), None


@callback(
    Output("filter-year", "value", allow_duplicate=True),
    Input({"type": "year-btn", "year": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def update_year_from_buttons(n_clicks_list):
    """При клике по кнопке 2026 или 2025 переключает глобальный фильтр года."""
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        return no_update
    clicked_year = ctx.triggered_id.get("year")
    if clicked_year:
        return clicked_year
    return no_update


@callback(
    Output({"type": "year-btn", "year": ALL}, "className"),
    Input("filter-year", "value"),
    State({"type": "year-btn", "year": ALL}, "id"),
    prevent_initial_call=False,
)
def sync_year_button_styles(selected_year, id_list):
    """Подсвечивает активную кнопку года (2026 / 2025) при выборе года."""
    if not id_list:
        return []
    class_names = []
    for btn_id in id_list:
        year = btn_id.get("year")
        base_class = f"damu-year-btn damu-year-btn-{year}"
        if selected_year is not None and str(year) == str(selected_year):
            class_names.append(f"{base_class} active")
        else:
            class_names.append(f"{base_class} inactive")
    return class_names


def sections_modal():
    """Полный список разделов — всплывает поверх страницы.

    Раздел, под которым ещё нет данных, приглушён: лучше честно показать,
    что там пусто, чем дать человеку обойти пять пустых страниц и решить,
    что дашборд сломан.

    Ссылки помечены общим типом id — по нажатию любой из них окно
    закрывается (см. коллбэк ниже). Иначе оно осталось бы висеть поверх
    только что открытого раздела.

    Служебных страниц здесь больше нет: «Разбор» стоит ссылкой в шапке,
    а страницы админа собраны в меню «Панель администратора». Дублировать
    их ещё и здесь значило бы держать два списка одного и того же.
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

    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Разделы")),
            dbc.ModalBody(dbc.Row(links, class_name="g-1")),
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
        navbar(),
        html.Div(filters_bar(), id="filters-wrap"),
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
    Output("data-updated-time", "children"),
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
            return no_update, no_update, no_update, banner
        updated_date, updated_time = data.get_last_update_parts()
        return fresh, updated_date, updated_time, banner
    except Exception:
        return no_update, no_update, no_update, None


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
