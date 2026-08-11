"""Макетные числа главной: то, что выводится из чисел, обязано сходиться.

Файл `core/mockup.py` временный — придут настоящие разрезы, он удалится
целиком. Но пока он питает самый показываемый экран проекта, и расхождение
в нём выглядит как ошибка данных, а не как ошибка макета.

Здесь ловится и свежая правка 10.08.2026: «за год» складывалось из
ПОКАЗАННЫХ месяцев, поэтому число прыгало при развороте графика.
"""

from datetime import date

import pytest

from core import mockup


@pytest.fixture
def today():
    """Фиксированная дата: иначе тест начнёт зависеть от дня прогона."""
    return date(2026, 8, 11)


def test_итог_за_год_не_зависит_от_разворота(today):
    """Главное свойство: кнопка меняет ПОКАЗ, а не итог.

    До 10.08.2026 «за год» считался как сумма показанных месяцев —
    свёрнутый вид давал сумму шести, развёрнутый всех, и число менялось
    от нажатия кнопки.
    """
    collapsed = mockup.for_year(None, expanded=False, today=today)
    expanded = mockup.for_year(None, expanded=True, today=today)
    for a, b in zip(collapsed, expanded):
        assert a["months_total"] == b["months_total"], a["title"]


def test_итог_за_год_не_меньше_суммы_показанного(today):
    """Свёрнутый вид показывает часть месяцев — итог обязан быть не меньше."""
    for item in mockup.for_year(None, expanded=False, today=today):
        assert item["months_total"] >= sum(item["months"])


def test_свёрнутый_вид_короче_развёрнутого(today):
    collapsed = mockup.for_year(None, expanded=False, today=today)[0]
    expanded = mockup.for_year(None, expanded=True, today=today)[0]
    assert len(collapsed["months"]) <= len(expanded["months"])
    assert len(collapsed["months"]) <= mockup.MONTHS_COLLAPSED


def test_подписи_месяцев_идут_в_ногу_с_числами(today):
    """Разъедутся — столбик подпишется чужим месяцем, и молча."""
    for expanded in (False, True):
        for item in mockup.for_year(None, expanded=expanded, today=today):
            assert len(item["months"]) == len(item["month_labels"]), item["title"]


def test_уникальные_и_повторные_дают_факт(today):
    """На этом равенстве стоит вся полоса проектов в карточке: сплошной
    кусок плюс штриховка обязаны складываться в заливку."""
    for item in mockup.for_year(None, today=today):
        assert item["unique"] + item["repeat"] == item["projects_fact"]


def test_уникальных_не_больше_чем_проектов(today):
    for item in mockup.for_year(None, today=today):
        assert 0 <= item["unique"] <= item["projects_fact"]


def test_проценты_сходятся_со_своими_числами(today):
    """Процент — производное, и считаться он должен из тех же чисел,
    что стоят рядом на экране."""
    for item in mockup.for_year(None, today=today):
        assert item["percent"] == pytest.approx(
            item["fact"] / item["plan"] * 100, rel=1e-6)
        assert item["projects_percent"] == pytest.approx(
            item["projects_fact"] / item["projects_plan"] * 100, rel=1e-6)


def test_прошлый_год_закончился_и_показан_целиком(today):
    """У прошлого года ожидаемый темп равен 100 %: год кончился, догонять
    нечего. И месяцы показываются все двенадцать."""
    items = mockup.for_year(today.year - 1, expanded=True, today=today)
    assert items[0]["pace"] == 100.0
    assert len(items[0]["months"]) == 12


def test_текущий_год_показывает_только_прошедшие_месяцы(today):
    """Столбик за декабрь в августе означал бы ноль, а читался бы как провал."""
    items = mockup.for_year(None, expanded=True, today=today)
    assert len(items[0]["months"]) <= today.month


def test_статус_отвечает_проценту(today):
    """«Выполнено» отделено от «По графику» намеренно: перевыполненный
    план — это не «идём по графику»."""
    for item in mockup.for_year(None, today=today):
        if item["percent"] >= 100:
            assert item["status"] == "Выполнено"
        elif item["gap"] >= 0:
            assert item["status"] == "По графику"
        else:
            assert item["status"] == "Отставание"
