"""Реестр диаграмм: он единственный источник правды о видах.

Проверяем не картинки, а договор реестра. На нём держатся три вещи:
список видов в настройщике виджетов, галка логарифма и разрез
в заголовке. Каждая из них уже была причиной правки — список видов
однажды был вписан словами в подпись галки и разошёлся с кодом.
"""

import pytest

from core import charts

#: Виды, которые режут данные по измерению. У них разрез ОБЯЗАН быть
#: назван словами — иначе на вкладке с несколькими диаграммами одного
#: показателя заголовки повторяются.
CUTTING = {
    "industries", "banks", "subjects", "purposes", "programs",
    "bar", "dot", "funnel", "pie", "treemap", "table",
    "facets", "sunburst", "icicle", "box",
}

#: Виды, которые сворачивают всё в одно число или пишут заголовок сами.
#: Разрез у них пустой намеренно.
NOT_CUTTING = {"total", "gauge", "years_total", "months", "years", "map"}


def test_реестр_не_пуст_и_список_строится_из_него():
    choices = charts.get_choices()
    assert len(choices) == len(charts._REGISTRY)
    assert all(c["label"] and c["value"] for c in choices)


def test_у_режущих_видов_разрез_назван():
    for key in CUTTING:
        assert key in charts._REGISTRY, f"вид {key} исчез из реестра"
        assert charts._REGISTRY[key].get("cut"), \
            f"у вида {key} нет разреза — заголовки будут повторяться"


def test_у_сворачивающих_видов_разреза_нет():
    for key in NOT_CUTTING:
        assert key in charts._REGISTRY, f"вид {key} исчез из реестра"
        assert not charts._REGISTRY[key].get("cut"), \
            f"вид {key} ничего не режет, разрез в заголовке соврёт"


def test_логарифм_только_там_где_он_честен():
    """На полосах логарифм врёт: длина обязана отсчитываться от нуля.

    Поэтому `log_ok` стоит у точек и ящика, но не у столбцов.
    """
    assert charts.supports_log("dot")
    assert charts.supports_log("box")
    assert not charts.supports_log("bar")
    assert not charts.supports_log("pie")


def test_неизвестный_вид_не_роняет_ни_реестр_ни_галку():
    """Виджет мог остаться в базе с видом, который удалили из кода."""
    assert charts.supports_log("такого-вида-нет") is False


def test_разрезы_записаны_по_русски_и_с_маленькой_буквы():
    """Разрез встраивается в предложение: «Выдано кредитов по банкам»."""
    for key, item in charts._REGISTRY.items():
        cut = item.get("cut")
        if not cut:
            continue
        assert cut.startswith("по "), f"{key}: разрез «{cut}» не встроится в строку"
        assert cut[3].islower(), f"{key}: разрез «{cut}» с заглавной буквы"


#: Виды, у которых названия (области, отрасли, банки) стоят подписями
#: ВЕРТИКАЛЬНОЙ оси. Им обязателен `automargin`.
WITH_SIDE_LABELS = [
    ("bar", "see_output", "СЭЭ"),
    ("dot", "see_output", "СЭЭ"),
    ("funnel", "see_output", "СЭЭ"),
    ("facets", "see_output", "СЭЭ"),
    ("years", "see_output", "СЭЭ"),
    ("industries", "see_output_industry", "СЭЭ"),
    ("banks", "credits_issued", "Өрлеу"),
]


@pytest.mark.needs_storage
@pytest.mark.parametrize("chart_type,indicator,program", WITH_SIDE_LABELS)
def test_подписи_сбоку_просят_себе_место(chart_type, indicator, program):
    """Без `automargin` Plotly СРЕЗАЕТ подписи, и молча.

    Общее левое поле — 10 px (`build`), а «Карагандинская» это около сотни.
    До 11.08.2026 просьба стояла только у видов, собранных через
    `_breakdown_figure`; у полос, точек, воронки, панелей и сравнения лет
    названия областей просто исчезали (поймано пользователем на разделе СЭЭ).

    Проверяем именно готовую фигуру, а не исходник: важно, что до неё
    настройка доехала, а не что строка написана.
    """
    fig = charts.build(chart_type, indicator, 2026, None,
                       program=program, height=420, columns=6)
    assert fig.data, f"у {chart_type} нет данных — проверка бессмысленна"
    axes = [name for name in dir(fig.layout) if name.startswith("yaxis")]
    for name in axes:
        assert getattr(fig.layout, name).automargin, \
            f"{chart_type}: у оси {name} нет automargin — подписи срежет"
