import logging
import os

import dash
import dash_bootstrap_components as dbc
from dash import html

from core import auth, publish
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

app = dash.Dash (
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP]
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
except Exception:
    log.exception("миграция хранилища на старте не прошла")


def serve_layout():
    """Каркас собирается на каждый запрос: состав меню зависит от роли.

    Зрителю ссылку «Ввод плана» не показываем. До этапа 5 роль отдаёт
    заглушка core/auth.py (в разработке админ каждый), но каркас уже
    сейчас спрашивает её, а не решает сам — LDAP подставится без правок здесь.
    """
    links = [dbc.NavItem(dbc.NavLink("Главная", href="/"))]
    if auth.is_admin():
        links.append(dbc.NavItem(dbc.NavLink("Ввод плана", href="/plan")))
    return html.Div([
        dbc.NavbarSimple(
            links,
            brand='Дашборд Даму',
            color='dark',
            dark=True,
            fluid=True,
        ),
        dash.page_container,
    ])


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
