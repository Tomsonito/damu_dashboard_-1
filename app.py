import logging
import os
from urllib.parse import urlparse

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from flask import has_request_context, request

from core import auth, data, publish, theme, widgets
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
    # Заголовок вкладки браузера НЕ дёргается на «Updating…».
    #
    # Dash по умолчанию подменяет `document.title` на «Updating...» на всё
    # время ЛЮБОГО коллбэка — включая клиентский и включая вернувший
    # no_update. На странице раздела опрос прокрутки тикает четыре раза
    # в секунду, и заголовок мигал непрерывно (02.09.2026, повторно: то же
    # самое ловили 18.08.2026 и лечили со стороны таймера — помогло не до
    # конца, потому что мигание даёт и смена фильтра, и проверка свежести
    # раз в 30 сек).
    #
    # !! Обратная сторона: теперь у медленного коллбэка НЕТ никакого
    # признака работы — ни в заголовке, ни на странице (`dcc.Loading`
    # нигде не стоит). Пока коллбэки быстрые, это незаметно; станут
    # медленными — заводить показ работы на самой странице, а не
    # возвращать мигание вкладки.
    update_title=None,
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
        # Меню «Разбор ▾» здесь стояло, пока выбирали раскладку из шести
        # примеров. Выбор сделан 18.08.2026 (пример 5), примеры удалены
        # 19.08.2026 — вместе с ними ушло и меню: оно вело на страницы,
        # которых больше нет.
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
            html.Div("Данные опубликованы", className="damu-updated-label"),
            # Дата и время — ОДНОЙ строкой (11.08.2026, просьба пользователя):
            # блок занимал три строки и заметную ширину шапки, а ширина нужна
            # диаграммам разделов. Время осталось мельче и приглушённее даты:
            # точный час нужен редко, и в один размер с датой он оттягивал бы
            # внимание на себя.
            html.Div([
                html.Span(className="damu-published-dot", **{"aria-hidden": "true"}),
                html.Span(updated_date, id="data-updated"),
                html.Span(updated_time, id="data-updated-time",
                          className="damu-updated-time"),
            ], className="damu-updated-value"),
        ], className="damu-updated",
           title="Дата и время публикации версии данных, которую вы видите")
    )

    # data-navbar читает CSS: на тёмной шапке подсветка ссылки идёт светлым,
    # а не основным цветом — зелёный на почти чёрном не читается
    return html.Div(items, className="damu-nav",
                    **{"data-navbar": settings["navbar"]})


def filters_bar():
    """Глобальные фильтры года и регионов.

    Фильтры живут в каркасе, а не на страницах: `dash.page_container`
    меняет только содержимое страницы, поэтому выбор переживает переход
    между разделами и одинаково применяется ко всем их виджетам.

    Показатели заканчиваются в разные годы. Существующая подстановка
    `data.resolve_year()` остаётся: пустую диаграмму она заменяет последним
    доступным годом, но такой год обязан быть явно подписан в заголовке.
    """
    try:
        years = data.get_years()
        regions = data.get_region_choices()
    except Exception:
        years = [2026]
        regions = []

    latest_year = years[0] if years else None
    return html.Div(
        [
            html.Div([
                # Подписи скрыты только визуально: фильтры занимают одну
                # строку, но экранный диктор по-прежнему называет каждое поле.
                html.Label("Год", htmlFor="filter-year",
                           className="visually-hidden"),
                dbc.Select(
                    id="filter-year",
                    options=[{"label": str(y), "value": y} for y in years],
                    # Свежий год берётся из данных, а не вписан числом.
                    value=latest_year,
                    class_name="damu-filter-year",
                ),
            ], className="damu-filter-field"),
            html.Div([
                html.Label("Регионы", htmlFor="filter-regions",
                           className="visually-hidden"),
                dcc.Dropdown(
                    id="filter-regions",
                    options=_ordered_regions(regions),
                    multi=True,
                    placeholder="Все регионы",
                    # Умолчание Dash — 200 px, а регионов двадцать: в окно
                    # попадали ТРИ строки из двадцати (замерено в браузере
                    # 02.09.2026). Потолок поднят так, чтобы на широком
                    # экране список умещался ЦЕЛИКОМ — он идёт в два
                    # столбца по десять (см. `columns: 2` в custom.css).
                    # Прокрутка при этом не отключена: на узком экране
                    # столбец остаётся один, и она снова нужна.
                    maxHeight=480,
                    labels={
                        "select_all": "Выбрать все",
                        "deselect_all": "Снять выбор",
                        "selected_count": "Выбрано: {num_selected}",
                        "search": "Найти регион",
                        "clear_search": "Очистить поиск",
                        "clear_selection": "Очистить выбор",
                        "no_options_found": "Регионы не найдены",
                    },
                    className="damu-filter-regions",
                ),
            ], className="damu-filter-field damu-filter-region-field"),
            html.Div([
                html.Div(
                    _filter_summary(latest_year, None),
                    id="filter-summary",
                    className="damu-filter-summary",
                    **{"aria-live": "polite"},
                ),
                html.Button(
                    "Сбросить фильтры", id="reset-filters",
                    className="damu-reset-filters", disabled=True,
                ),
            ], className="damu-filter-actions"),
        ],
        className="damu-filters",
        role="region",
        **{"aria-label": "Глобальные фильтры"},
    )


#: Города республиканского значения отличаются от областей приставкой «г. ».
#: По ней их узнаёт и Python (порядок в списке), и CSS (селектор по value).
CITY_PREFIX = "г. "


def _region_value(option) -> str:
    """Значение варианта — хоть строкой, хоть словарём `{label, value}`.

    !! Обе формы законны для `dcc.Dropdown`, и сейчас `get_region_choices()`
    отдаёт строки. Но приняв только строки, порядок молча падал бы
    на словарях — а перейти на них могут ради подписи, отличной
    от значения (например, «г. Алматы» показывать как «Алматы»).
    """
    if isinstance(option, dict):
        return str(option.get("value", option.get("label", "")))
    return str(option)


def _ordered_regions(regions: list) -> list:
    """Сначала три города, потом области — и то и другое по алфавиту.

    Города республиканского значения — не то же самое, что область:
    у них своя строка в отчётности, и в данных они всегда наверху
    (Алматы и Астана — первые два места по выпуску). В общем алфавитном
    списке они терялись в самом низу, потому что «г.» с маленькой буквы
    сортируется после всех названий.

    Порядок — единственное, что здесь меняется. Состав и написание берутся
    из данных как есть: подмена названия расходится с тем, что показано
    в диаграммах.
    """
    def is_city(option) -> bool:
        return _region_value(option).startswith(CITY_PREFIX)

    cities = sorted((r for r in regions if is_city(r)), key=_region_value)
    oblasts = sorted((r for r in regions if not is_city(r)), key=_region_value)
    return cities + oblasts


def _filter_summary(year, regions) -> str:
    """Короткое подтверждение фактически выбранного контекста."""
    year_text = str(year) if year not in (None, "") else "год не выбран"
    selected = list(regions or [])
    if not selected:
        region_text = "все регионы"
    elif len(selected) == 1:
        region_text = selected[0]
    else:
        region_text = f"регионов: {len(selected)}"
    return f"Показано: {year_text} · {region_text}"



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
    Output("filter-summary", "children"),
    Output("reset-filters", "disabled"),
    Input("filter-year", "value"),
    Input("filter-regions", "value"),
)
def describe_filters(year, regions):
    """Выбор подтверждается рядом; сброс активен только когда есть что сбрасывать."""
    try:
        years = data.get_years()
        latest_year = years[0] if years else None
    except Exception:
        latest_year = year
    is_default = str(year) == str(latest_year) and not regions
    return _filter_summary(year, regions), is_default


#: Адреса, где ряд фильтров не показывается.
#:
#: Главная — обзорный экран: год на ней переключают собственные кнопки
#: витрины (см. `update_year_from_buttons`), а разрез по регионам ей нечем
#: применить — числа там макетные (`core/mockup.py`). Ряд фильтров на ней
#: был лишней панелью, которая ничего не меняет (02.09.2026).
FILTERLESS_PATHS = {"/"}


def filters_class(pathname: str | None) -> str:
    """Класс ряда фильтров для этого адреса: пусто — показывать, класс — прятать.

    !! Зовётся из ДВУХ мест — из `serve_layout` (первая отрисовка, адрес
    берётся из запроса) и из `toggle_filters` (переходы по ссылкам, адрес
    приходит из браузера). Оба обязаны решать одинаково, поэтому решение
    здесь одно на двоих, а не две похожие проверки: разойдись они — ряд
    фильтров мигнёт на главной при загрузке или останется на ней висеть.
    """
    return "damu-filters-hidden" if pathname in FILTERLESS_PATHS else ""


@callback(
    Output("filters-wrap", "className"),
    Input("url", "pathname"),
)
def toggle_filters(pathname):
    """Прячет ряд фильтров там, где на него нечему реагировать.

    !! Именно ПРЯЧЕТ классом, а не убирает поля из разметки. Убрать их
    насовсем нельзя, и не по одной причине:

    * кнопки года на витрине пишут в тот же `filter-year` — без поля
      коллбэк не сработает, и кнопки перестанут переключать год;
    * карта на главной читает `filter-year` и `filter-regions` — без полей
      её коллбэк не позовётся вообще, и карта останется пустой;
    * выбор обязан переживать переход между разделами (это ради него
      фильтры вынесены в каркас) — а поле, которого нет в разметке,
      возвращается со значением по умолчанию.

    Все три поломки — молчаливые: ошибки нет, просто перестаёт работать.

    Адрес ещё не пришёл — не трогаем: начальный класс уже проставлен
    сервером в `serve_layout`, и перебивать его догадкой значит мигнуть
    рядом фильтров на ровном месте.
    """
    if pathname is None:
        return no_update
    return filters_class(pathname)


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
        dcc.Interval(id="data-poll", interval=10 * 1000),
        dcc.Store(id="data-version", data=_safe_version()),
        # Адрес страницы нужен ряду фильтров: на главной его прячут
        # (см. `toggle_filters`). Свой `dcc.Location`, а не внутренний
        # `_pages_location` системы страниц: чужой служебный id может
        # смениться в любой версии Dash, и сломается это МОЛЧА.
        dcc.Location(id="url", refresh=False),
        navbar(),
        # Класс ставится уже здесь, на сервере: дождись мы коллбэка —
        # на главной ряд фильтров успел бы показаться и спрятаться,
        # то есть мигнуть при каждой загрузке.
        html.Div(filters_bar(), id="filters-wrap",
                 className=filters_class(_current_path())),
        sections_modal(),
        html.Div(
            [
                html.Div(id="publish-banner"),
                dash.page_container,
            ],
            className="damu-content",
        ),
    ])


def _current_path() -> str | None:
    """Адрес страницы, которую сейчас открывают, — или None, если он неизвестен.

    !! Каркас собирается не только на переходе по адресу страницы: Dash
    просит разметку отдельным запросом на служебный `/_dash-layout`, и там
    `request.path` — это он сам, а не страница. Настоящий адрес в таком
    запросе приходит заголовком `Referer`. Проверено запуском (02.09.2026),
    а не предположением: на догадке ряд фильтров мигал бы при каждой
    загрузке главной.

    None значит «адрес неизвестен» — ряд фильтров тогда показывается,
    и его прячет уже коллбэк. Показать лишнее и убрать — не страшно;
    спрятать нужное и оставить спрятанным — потеря управления.
    """
    if not has_request_context():
        return None
    if request.path != "/_dash-layout":
        return request.path
    referrer = request.referrer or ""
    return urlparse(referrer).path or None


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
    Output("data-poll", "interval"),
    Input("data-poll", "n_intervals"),
    State("data-version", "data"),
    State("data-poll", "interval"),
)
def poll_version(_, known_version, current_interval):
    """Первый тик через 10 сек — опрос. Далее каждые 30.

    dcc.Interval стартует с interval=10000. На первом тике коллбэк
    возвращает interval=30000, и следующие опросы идут раз в 30 сек.
    Так пользователь успевает посмотреть экран, прежде чем первый
    запрос свежести уйдёт в базу.

    Переехало сюда из pages/main.py вместе с таймером: теперь свежесть
    сторожится на любой странице, а не только на витрине.

    Сначала шлюз: publish_due() выпускает всё, чей срок наступил, — так
    ровно в первый опрос после 9:00 (или после подъёма сервера) публикация
    и происходит, отдельного планировщика нет. В холостую это два дешёвых
    чтения. Совпала версия — `no_update`, ничего не перерисовывается.

    После шлюза — poll_health(): ОДНО открытие DuckDB на всё (версия,
    план, время публикации). Раньше это было три отдельных открытия
    (get_display_version + get_last_update_parts), каждое 24–34 мс,
    потому что при закрытии DuckDB выгружает базу.
    """
    next_interval = 30_000 if current_interval == 10_000 else current_interval

    try:
        published = publish.publish_due()
        if published:
            log.info("опубликовано: %s", published)
    except Exception:
        log.exception("публикация дозревшего не прошла — попробуем через 30 сек")

    try:
        health = data.poll_health()
        fresh = data._display_version(health)
        banner = publish_banner()
        if known_version is not None and str(known_version) == fresh:
            return no_update, no_update, no_update, banner, next_interval
        updated_date, updated_time = data._last_update_from_health(health)
        return fresh, updated_date, updated_time, banner, next_interval
    except Exception:
        return no_update, no_update, no_update, None, next_interval


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
