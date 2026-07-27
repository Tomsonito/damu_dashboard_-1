"""Оформление сайта: название, цвет, шрифт, размер текста, логотип.

Два слоя, и это главное, что стоит понять про этот файл:

- **умолчания** лежат в `config.yaml`, блок `theme` — «как сайт выглядит
  из коробки». Файл едет с проектом из git;
- **выбор админа** лежит в таблице `settings` хранилища и ложится поверх
  умолчаний. Страница «Настройки» пишет только сюда.

Почему не писать выбор обратно в `config.yaml`: два админа затирали бы
правки друг друга, кривой ввод ломал бы YAML целиком (упал бы весь сайт,
а не одна настройка), а выкат новой версии из git стирал бы настройки.
Файл — для того, что везут с кодом; база — для того, что меняют на ходу.

**Тема НЕ ждёт 9:00.** Шлюз отложенной публикации сторожит цифры: там цена
незамеченной ошибки — неверные данные на экране у семидесяти человек.
Цвет и шрифт видны автору сразу же, а откат — одна кнопка «Вернуть
умолчания», поэтому держать их сутки в очереди смысла нет.

Как тема доезжает до экрана:

    settings + config.yaml
        -> css_variables()  ->  <style> в <head> (app.py, interpolate_index)
        -> assets/custom.css читает var(--damu-*) и красит страницу
        -> core/charts.py берёт шрифт и цвет для диаграмм
        -> app.py строит шапку: логотип, название, цвет

Значения проверяются при сохранении, а не при показе: в хранилище не должно
оказаться цвета «зелёненький» или шрифта, которого нет в реестре.
"""

import re
from datetime import datetime
from pathlib import Path

import duckdb

from core.cache import cache
from core.data import DUCKDB_PATH, _connect_write, _query_storage, load_config

ASSETS_DIR = Path("assets")

# Что вообще можно настроить. Список закрытый: настройка — это не только
# поле в базе, но и элемент управления, проверка ввода и место, где она
# применяется. «Полная свобода» кончается тем, что кто-нибудь ставит
# 8 пикселей на белом — поэтому свободы ровно столько, сколько нужно.
KEYS = ("brand", "accent", "navbar", "font", "font_scale", "logo")

# Варианты шапки: тёмная, светлая, в цвет акцента
NAVBARS = {
    "dark": "Тёмная",
    "light": "Светлая",
    "accent": "В основной цвет",
}

#: Цвет принимаем только как #rrggbb — ровно то, что отдаёт поле выбора
#: цвета в браузере. Строку вроде «red» браузер бы понял, а вот наш
#: расчёт контраста для шапки — уже нет.
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Разрешённые картинки для логотипа — только то, что лежит в assets/.
#: Путь пользователь не вводит: он выбирает из найденных файлов, поэтому
#: «../../и что-нибудь чужое» в настройки не попадёт.
LOGO_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp")

#: «Логотипа нет» в списке выбора. В хранилище это пустая строка, но
#: показать её списком нельзя: dbc.Select сам добавляет скрытый пустой
#: пункт-заглушку, и наш вариант с ним слипался — поле выглядело пустым
#: (проверено в браузере). Поэтому у пустоты есть своё имя.
NO_LOGO = "none"


# --------------------------------------------------------------- чтение

def defaults() -> dict:
    """Умолчания из config.yaml. Пустой блок — не беда, подставим своё."""
    cfg = load_config().get("theme") or {}
    return {
        "brand": cfg.get("brand", "Дашборд Даму"),
        "accent": cfg.get("accent", "#0d6efd"),
        "navbar": cfg.get("navbar", "dark"),
        "font": cfg.get("font", "system"),
        "font_scale": cfg.get("font_scale", "normal"),
        "logo": cfg.get("logo", ""),
    }


@cache.memoize()
def _stored() -> dict:
    """Выбор админа из таблицы `settings`.

    Кэшируется без ключа и сбрасывается вручную из save()/reset() — тот же
    принцип, что и у фактов: кэш не «протухает по времени», а обновляется
    ровно в момент изменения. Иначе пришлось бы лезть в DuckDB на каждую
    отрисовку каждой диаграммы, а под Gunicorn — из каждого воркера.

    Хранилища может не быть вовсе (сайт открыли до первого прогона ETL) —
    тогда работаем на умолчаниях, а страница сама покажет свою подсказку.
    """
    try:
        df = _query_storage(
            "SELECT key, value FROM settings WHERE key IN "
            "(" + ", ".join(f"'{k}'" for k in KEYS) + ")"
        )
    except (FileNotFoundError, duckdb.Error):
        return {}
    return dict(zip(df["key"], df["value"]))


def get_theme() -> dict:
    """Итоговое оформление: умолчания, поверх них — выбор админа.

    Настройка, которой админ не касался, продолжает жить из config.yaml —
    значит правку умолчаний в файле сайт подхватит, если её не перекрыли.
    Незнакомые значения (шрифт удалили из реестра) молча падают обратно
    на умолчание: сайт не должен ломаться из-за строки в базе.
    """
    theme = defaults()
    theme.update({k: v for k, v in _stored().items() if k in KEYS})

    cfg = load_config()
    if theme["font"] not in (cfg.get("fonts") or {}):
        theme["font"] = defaults()["font"]
    if theme["font_scale"] not in (cfg.get("font_scales") or {}):
        theme["font_scale"] = defaults()["font_scale"]
    if theme["navbar"] not in NAVBARS:
        theme["navbar"] = defaults()["navbar"]
    if not COLOR_RE.match(str(theme["accent"])):
        theme["accent"] = defaults()["accent"]
    if theme["logo"] and not (ASSETS_DIR / theme["logo"]).exists():
        theme["logo"] = ""  # картинку удалили из assets/ — покажем одно название
    return theme


def font_stack(theme: dict | None = None) -> str:
    """Строка font-family выбранного набора — её понимают и CSS, и plotly."""
    theme = theme or get_theme()
    fonts = load_config().get("fonts") or {}
    entry = fonts.get(theme["font"]) or {}
    return entry.get("stack", "system-ui, sans-serif")


def base_size(theme: dict | None = None) -> str:
    """Базовый размер текста, например «16px».

    Всё остальное на странице задано в rem, поэтому одна эта величина
    тянет за собой весь масштаб — заголовки, карточки, таблицу.
    """
    theme = theme or get_theme()
    scales = load_config().get("font_scales") or {}
    entry = scales.get(theme["font_scale"]) or {}
    return entry.get("size", "16px")


# ------------------------------------------------------ выбор для формы

def font_choices() -> list[dict]:
    """Наборы шрифтов для выпадающего списка — из config.yaml, не из кода."""
    fonts = load_config().get("fonts") or {}
    return [{"label": v.get("label", key), "value": key} for key, v in fonts.items()]


def scale_choices() -> list[dict]:
    scales = load_config().get("font_scales") or {}
    return [
        {"label": f"{v.get('label', key)} — {v.get('size', '')}", "value": key}
        for key, v in scales.items()
    ]


def navbar_choices() -> list[dict]:
    return [{"label": label, "value": key} for key, label in NAVBARS.items()]


def logo_choices() -> list[dict]:
    """Картинки, найденные в assets/ — плюс вариант «без логотипа».

    Список строится обходом папки, а не вводом пути руками: админ кладёт
    файл в assets/ и выбирает его из списка. Так нельзя ни опечататься
    в имени, ни увести путь за пределы папки.
    """
    found: list[str] = []
    if ASSETS_DIR.exists():
        found = sorted(
            p.name for p in ASSETS_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in LOGO_SUFFIXES
        )
    return [{"label": "Без логотипа", "value": NO_LOGO}] + [
        {"label": name, "value": name} for name in found
    ]


# ------------------------------------------------------------ CSS и цвет

def _mix(color: str, other: str, weight: float) -> str:
    """Смешать два цвета: weight — доля второго. Для оттенков акцента.

    Нужен, чтобы из одного выбранного цвета получить и цвет наведения
    (темнее), и бледную подсветку. Просить у админа три цвета вместо
    одного — лишний труд и лишний способ получить нечитаемое.
    """
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(x + (y - x) * weight) for x, y in zip(a, b)]
    return "#" + "".join(f"{v:02x}" for v in mixed)


def readable_on(color: str) -> str:
    """Чёрный или белый текст — что читается на этом фоне.

    Яркость по формуле восприятия (глаз чувствительнее к зелёному, чем
    к синему), а не среднее трёх каналов: иначе на жёлтом фоне получался
    бы белый текст, которого не видно.
    """
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return "#000000" if brightness > 150 else "#ffffff"


def css_variables(theme: dict | None = None) -> str:
    """Переменные CSS для `:root` — то, чем страница красится.

    Дальше их читает assets/custom.css. Разделение труда такое: здесь —
    ЗНАЧЕНИЯ (что выбрал админ), там — ПРАВИЛА (какой элемент их берёт).
    Поэтому вёрстку можно править, не трогая Python, и наоборот.
    """
    theme = theme or get_theme()
    accent = theme["accent"]
    return "\n".join([
        ":root {",
        f"  --damu-font: {font_stack(theme)};",
        f"  --damu-font-size: {base_size(theme)};",
        f"  --damu-accent: {accent};",
        f"  --damu-accent-dark: {_mix(accent, '#000000', 0.2)};",
        f"  --damu-accent-soft: {_mix(accent, '#ffffff', 0.85)};",
        f"  --damu-on-accent: {readable_on(accent)};",
        "}",
    ])


def style_tag(theme: dict | None = None) -> str:
    """Готовый <style> для вставки в <head>. Зовётся из app.py на каждый запрос.

    Почему не отдельный файл в assets/: файл пришлось бы перезаписывать
    при каждой смене настроек, и два воркера Gunicorn могли бы писать
    в него одновременно. Строка в <head> ничего не хранит на диске
    и всегда соответствует тому, что сейчас в базе.
    """
    return f"\n<style>\n{css_variables(theme)}\n</style>\n"


# --------------------------------------------------------------- запись

def _require_storage() -> None:
    """Настройки живут в хранилище — без него писать некуда.

    !! Проверка обязательна: duckdb.connect на несуществующий файл СОЗДАЁТ
    его. Без этой строки первое же сохранение темы породило бы хранилище
    без фактов и версий, и главная страница вместо понятной подсказки
    «запустите ETL» показала бы ошибку про отсутствующую таблицу.
    """
    if not DUCKDB_PATH.exists():
        raise ValueError(
            "Хранилища ещё нет, а настройки хранятся в нём. "
            "Сначала запустите: python -m etl.run"
        )


def _ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    """Таблица настроек. Создаётся при первом сохранении, не раньше.

    Отдельная от `plan` и `versions`: у неё другая жизнь — ни статусов,
    ни версий, ни ожидания 9:00. Одна строка на настройку, старое значение
    заменяется новым; кто и когда менял — в самой строке.
    """
    con.execute(
        """CREATE TABLE IF NOT EXISTS settings (
               key        VARCHAR   NOT NULL,  -- ключ из KEYS
               value      VARCHAR   NOT NULL,  -- всегда строкой: значения разнотипные
               author     VARCHAR   NOT NULL,
               updated_at TIMESTAMP NOT NULL
           )"""
    )


def validate(values: dict) -> dict:
    """Проверяет и приводит значения. Кидает ValueError с текстом для экрана.

    Проверяем при записи, а не при показе: в базе не должно лежать того,
    чего мы не умеем показать. get_theme() всё равно подстрахован — но это
    защита от испорченной базы, а не замена проверке.
    """
    cfg = load_config()
    clean: dict[str, str] = {}

    brand = str(values.get("brand", "") or "").strip()
    if not brand:
        raise ValueError("Название в шапке не может быть пустым.")
    if len(brand) > 60:
        raise ValueError("Название длиннее 60 символов — в шапку не поместится.")
    clean["brand"] = brand

    accent = str(values.get("accent", "") or "").strip()
    if not COLOR_RE.match(accent):
        raise ValueError("Цвет должен быть в виде #rrggbb, например #0d6efd.")
    clean["accent"] = accent.lower()

    navbar = str(values.get("navbar", ""))
    if navbar not in NAVBARS:
        raise ValueError("Неизвестный вид шапки.")
    clean["navbar"] = navbar

    font = str(values.get("font", ""))
    if font not in (cfg.get("fonts") or {}):
        raise ValueError("Такого набора шрифтов нет в config.yaml.")
    clean["font"] = font

    scale = str(values.get("font_scale", ""))
    if scale not in (cfg.get("font_scales") or {}):
        raise ValueError("Такого размера текста нет в config.yaml.")
    clean["font_scale"] = scale

    logo = str(values.get("logo", "") or "")
    if logo == NO_LOGO:
        logo = ""  # выбор «Без логотипа» — в хранилище это пустая строка
    if logo and Path(logo).name != logo:
        raise ValueError("Логотип — имя файла из assets/, без путей.")
    if logo and not (ASSETS_DIR / logo).exists():
        raise ValueError(f"Файла assets/{logo} нет — положите картинку в assets/.")
    clean["logo"] = logo

    return clean


def save(values: dict, author: str) -> dict:
    """Сохраняет настройки и возвращает применённые значения.

    Одной транзакцией: экран не должен застать состояние «цвет уже новый,
    шрифт ещё старый». После записи сбрасываем кэш — иначе воркеры
    показывали бы старое до истечения таймаута.
    """
    clean = validate(values)
    _require_storage()
    now = datetime.now()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute("BEGIN")
        con.execute(
            "DELETE FROM settings WHERE key IN (" + ", ".join("?" for _ in clean) + ")",
            list(clean),
        )
        for key, value in clean.items():
            con.execute(
                "INSERT INTO settings (key, value, author, updated_at) VALUES (?, ?, ?, ?)",
                [key, str(value), author, now],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    cache.delete_memoized(_stored)
    return clean


def reset() -> None:
    """Убирает выбор админа — сайт возвращается к умолчаниям из config.yaml.

    Именно удаление строк, а не запись умолчаний значениями: тогда правка
    config.yaml снова начинает действовать, как будто настроек и не было.
    """
    _require_storage()
    con = _connect_write()
    try:
        _ensure_table(con)
        con.execute(
            "DELETE FROM settings WHERE key IN (" + ", ".join("?" for _ in KEYS) + ")",
            list(KEYS),
        )
    finally:
        con.close()
    cache.delete_memoized(_stored)


def last_change() -> tuple[str, datetime] | None:
    """Кто и когда менял оформление — для подписи на странице настроек."""
    try:
        df = _query_storage(
            "SELECT author, updated_at FROM settings ORDER BY updated_at DESC LIMIT 1"
        )
    except (FileNotFoundError, duckdb.Error):
        return None
    if df.empty:
        return None
    return str(df.iloc[0]["author"]), df.iloc[0]["updated_at"].to_pydatetime()
