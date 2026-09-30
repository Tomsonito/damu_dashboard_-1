"""Слой данных: подстановка года, отбор по разделу, масштаб показа.

Цена ошибки здесь — не кривая вёрстка, а неверные цифры под правильной
подписью, поэтому проверок больше всего именно тут.

Часть тестов чистая (работает на своей табличке или на конфиге), часть
помечена `needs_storage` — им нужен `data/analytics.duckdb`.
"""

import pandas as pd
import pytest

from core import data


# ------------------------------------------------------- отбор по разделу

def frame():
    """Маленькая табличка фактов — своя, чтобы не зависеть от хранилища."""
    return pd.DataFrame({
        "indicator": ["a", "a", "b"],
        "program": ["Өрлеу", "СЭЭ", "Өрлеу"],
        "value": [1.0, 2.0, 3.0],
    })


def test_без_раздела_видно_всё():
    """None — «смотреть на всё сразу»: так работают главная и «Разбор»."""
    assert len(data._only_program(frame(), None)) == 3


def test_раздел_оставляет_только_свои_строки():
    only = data._only_program(frame(), "Өрлеу")
    assert len(only) == 2
    assert set(only["program"]) == {"Өрлеу"}


def test_пустая_строка_раздела_не_фильтрует():
    """У бюджетных строк раздел пустой — отбор по нему отрезал бы всё."""
    assert len(data._only_program(frame(), "")) == 3


def test_неизвестный_раздел_даёт_пусто_а_не_ошибку():
    assert data._only_program(frame(), "Такого нет").empty


# ------------------------------------------------- показатели из конфига

def test_показатель_описан_в_конфиге_а_не_в_коде():
    meta = data.get_indicator_meta("budget_spent")
    assert meta["title"]
    assert meta["divisor"] > 0
    assert meta["unit"] or meta["display_unit"]


def test_неизвестный_показатель_роняет_обращение_к_реестру():
    """`??` Тест закрепляет НЫНЕШНЕЕ поведение, а не желаемое.

    `get_indicator_meta` бросает `KeyError`, если показателя нет в конфиге.
    Соседний `widgets.size_meta` в такой же ситуации подставляет средний
    размер и прямо объясняет почему: «пресет удалили из config.yaml,
    а виджет с ним остался в базе — экран должен нарисоваться, а не упасть».

    С показателем это тоже возможно: виджет живёт в хранилище и переживает
    правку конфига. Тогда вместо диаграммы выйдет ошибка коллбэка. Единого
    правила у проекта тут нет, решать пользователю — поэтому тест фиксирует
    то, что есть, и сломается, если поведение поменяют молча.
    """
    with pytest.raises(KeyError):
        data.get_indicator_meta("такого-показателя-нет")


def test_число_форматируется_по_русски():
    """Разряды неразрывным пробелом, дробь запятой, следом единица.

    Питон по умолчанию делает ровно наоборот («1,234.6»), поэтому правило
    держится на порядке двух замен — ломается перестановкой строк.
    """
    text = data.format_value(1234567, "budget_spent")
    assert text.startswith("1 234,6"), text
    assert text.endswith("млрд ₸"), text
    assert "." not in text and "," in text


# ------------------------------------------------------- справочник регионов

def test_варианты_регионов_сводятся_к_каноническим_названиям():
    raw = pd.Series([
        "ВКО", "РФ по Восточно-Казахстанской области",
        "Жетысу", "РФ по области Жетiсу",
        "Улытау", "РФ по области Ұлытау",
        "г.Алматы", "РФ по г. Алматы",
    ])

    assert data._canonical_regions(raw).tolist() == [
        "Восточно-Казахстанская", "Восточно-Казахстанская",
        "Жетісу", "Жетісу",
        "Ұлытау", "Ұлытау",
        "г. Алматы", "г. Алматы",
    ]


@pytest.mark.needs_storage
def test_фильтр_содержит_20_регионов_без_служебных_значений():
    regions = data.get_region_choices()

    assert len(regions) == 20
    assert "Жетісу" in regions and "Ұлытау" in regions and "Абай" in regions
    assert not set(regions) & set(data.REGION_ALIASES)
    assert not set(regions) & data.NON_GEOGRAPHIC_REGIONS


# ------------------------------------------------------- подстановка года

@pytest.mark.needs_storage
def test_свой_год_возвращается_как_есть(facts):
    years = data.indicator_years("budget_spent")
    assert years, "у показателя нет ни одного года — проверить нечего"
    assert data.resolve_year("budget_spent", years[0]) == years[0]


@pytest.mark.needs_storage
def test_будущий_год_откатывается_к_ближайшему_прошлому():
    """Год один на весь сайт, а показатели кончаются в разные годы.
    Пустая ось вместо чисел — то, от чего это правило и завели."""
    years = data.indicator_years("budget_spent")
    ahead = years[0] + 5
    assert data.resolve_year("budget_spent", ahead) == years[0]


@pytest.mark.needs_storage
def test_слишком_старый_год_берёт_самый_старый_имеющийся():
    years = data.indicator_years("budget_spent")
    assert data.resolve_year("budget_spent", min(years) - 5) == min(years)


@pytest.mark.needs_storage
def test_показатель_без_данных_честно_возвращает_none():
    """Описан в реестре, а строк нет — подставлять нечего, и диаграмма
    обязана сказать «нет данных», а не показать чужой год."""
    assert data.resolve_year("demo_plan", 2026) is None


@pytest.mark.needs_storage
def test_годы_показателя_идут_свежим_вперёд():
    years = data.indicator_years("budget_spent")
    assert years == sorted(years, reverse=True)


@pytest.mark.needs_storage
def test_годы_показателя_уже_общего_списка():
    """`get_years()` отвечает «какие годы вообще есть», и это не то же
    самое, что годы конкретного показателя."""
    assert set(data.indicator_years("budget_spent")) <= set(data.get_years())


# ------------------------------------------------------------- хранилище

@pytest.mark.needs_storage
def test_таблица_фактов_держит_свою_форму(facts):
    """Форму таблицы сохраняем при любой смене источника — на ней стоит
    весь слой данных."""
    for column in ("indicator", "report_year", "value", "region", "program"):
        assert column in facts.columns


@pytest.mark.needs_storage
def test_разрезы_хранятся_категориями_а_не_строками(facts):
    """Замер 07.08.2026: строками таблица весила 197 МБ и читалась 369 мс,
    категориями — 5 МБ и 61 мс."""
    for column in ("region", "program", "indicator"):
        assert str(facts[column].dtype) == "category", column


@pytest.mark.needs_storage
def test_разделы_с_данными_совпадают_с_названиями_из_конфига():
    """Название раздела в `config.yaml` обязано совпадать со значением
    в колонке `program` — по нему страница отбирает свои строки."""
    titles = {s["title"] for s in data.load_config()["sections"]}
    for program in data.get_programs():
        assert program in titles, \
            f"в данных есть раздел «{program}», а в конфиге такого нет"
