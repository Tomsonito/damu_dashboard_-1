"""Ключи страниц и наборы виджетов.

Здесь живёт ошибка, которая уже случалась: номера виджетов свои у каждой
страницы, поэтому отбор всегда идёт по ПАРЕ (id, page). Без второго условия
удаление виджета било по чужой странице с тем же номером.

Вторая проверенная здесь тонкость — раздел, к которому относится страница:
по нему отбираются строки данных, и ошибка тут даёт не пустой экран,
а чужие числа под правильной подписью.
"""

import pytest

from core import widgets


def test_ключ_страницы_склеивается_и_разбирается_обратно():
    """Договор один на весь проект: «раздел:вкладка»."""
    assert widgets.page_key("orleu", "terms") == "orleu:terms"
    assert widgets.split_page("orleu:terms") == ("orleu", "terms")


def test_страница_без_вкладки_остаётся_разделом():
    assert widgets.page_key("orleu") == "orleu"
    section, tab = widgets.split_page("orleu")
    assert section == "orleu"
    assert not tab


def test_раздел_страницы_берётся_из_конфига():
    """`program_of` возвращает НАЗВАНИЕ раздела — по нему отбираются строки."""
    assert widgets.program_of("orleu") == "Өрлеу"
    assert widgets.program_of("orleu:terms") == "Өрлеу", \
        "вкладка выбирает набор виджетов, но не влияет на отбор данных"


def test_у_главной_раздела_нет():
    """Главная смотрит на всё сразу — фильтровать нечем и не нужно."""
    assert widgets.program_of(widgets.MAIN_PAGE) is None
    assert widgets.program_of("") is None


def test_несуществующий_раздел_не_роняет_страницу():
    assert widgets.program_of("такого-раздела-нет") is None


def test_пресет_размера_знает_ширину_и_высоту():
    """Ширина в колонках нужна не только сетке: по ней заголовок диаграммы
    решает, переносить ли строку."""
    for size in ("small", "medium", "large"):
        preset = widgets.size_meta(size)
        assert 1 <= preset["columns"] <= 12
        assert preset["height"] > 0


def test_размеры_идут_по_возрастанию():
    assert (widgets.size_meta("small")["columns"]
            < widgets.size_meta("medium")["columns"]
            < widgets.size_meta("large")["columns"])


def test_неизвестный_пресет_подменяется_средним():
    """Пресет могли удалить из конфига, а виджет с ним остался в базе.
    Экран обязан нарисоваться, а не упасть."""
    fallback = widgets.size_meta("такого-размера-нет")
    assert fallback["columns"] == 6 and fallback["height"] > 0


@pytest.mark.needs_storage
def test_умолчания_набора_виджетов_нумеруются_подряд():
    """У ненастроенной страницы номера всегда 1…N — на это опирается
    настройщик, когда показывает набор до первой правки."""
    items = widgets.default_widgets("orleu:terms")
    assert [w["id"] for w in items] == list(range(1, len(items) + 1))


@pytest.mark.needs_storage
def test_наборы_разных_страниц_не_пересекаются_по_смыслу():
    """Номера у страниц СВОИ: одинаковые id на разных страницах — норма,
    и именно поэтому отбор идёт по паре (id, page)."""
    a = widgets.get_widgets("orleu:terms")
    b = widgets.get_widgets("guarantee:programs")
    if not a or not b:
        pytest.skip("на этих страницах нет виджетов")
    assert {w["id"] for w in a} & {w["id"] for w in b}, \
        "номера обязаны повторяться — иначе проверка бессмысленна"
    assert all(w["chart"] for w in a + b)
