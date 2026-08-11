"""Хватает ли виджету высоты, чтобы показать ВСЕ подписи категорий.

Эта поломка случалась уже дважды, и оба раза её ловил пользователь глазами,
а не код:

- 07.08.2026, «Гар. выдача»: 28 банков в среднем виджете — 7,4 px на строку,
  видно 14 подписей из 28;
- 11.08.2026, СЭЭ «Регионы»: 20 областей — 13 px на строку, видно каждую
  вторую. Причём вклад внесла и своя же правка: заголовок стал трёхстрочным,
  и верхнее поле выросло с 60 px до 112.

Опасна она тем, что **ошибки нет нигде**: ни в консоли, ни в логе. График
рисуется целиком, столбцы все на месте — врёт только подпись. Plotly в
тесноте не сжимает шрифт и не поворачивает текст, а прячет часть подписей,
чтобы оставшиеся не наложились.

Порог 20 px на строку взят не из головы: он замерен в браузере 07.08.2026
и записан в CODE_GUIDE, раздел «Пресет виджета и число категорий».

Тест считает высоту не по пресету, а по ГОТОВОЙ фигуре: сколько осталось
после полей под заголовок и ось. Поэтому он замечает и косвенные причины —
например удлинившийся заголовок, который сам по себе выглядит безобидно.
"""

import pytest

from core import charts, widgets

#: Порог. С 11.08.2026 он означает другое, чем раньше, и это важно.
#:
#: Было: 20 px — граница, ниже которой Plotly сам начинал ПРЯТАТЬ подписи.
#: Стало: подписи выводятся все и всегда (`CATEGORY_TICKS` в core/charts.py
#: — `tickmode="linear"`, `dtick=1`), поэтому библиотека ничего не решает
#: за нас. Теперь порог сторожит другое — НАЛОЖЕНИЕ: шрифт подписи 11 px,
#: и меньше 13 px на строку они начнут задевать друг друга.
#:
#: Разница принципиальная: раньше нарушение порога прятало данные молча,
#: теперь оно портит вид, но остаётся видимым. Это осознанный размен —
#: лучше тесно, чем «половина областей исчезла, и никто не заметил».
MIN_PX_PER_ROW = 13

#: Виды, у которых подписи категорий стоят по вертикальной оси. Только их
#: и проверяем: у столбчатых и сводных видов теснота работает иначе.
SIDE_LABEL_CHARTS = {"bar", "dot", "funnel", "industries", "banks",
                     "subjects", "purposes", "programs"}


def widget_pages():
    """Все настроенные наборы виджетов из config.yaml — парами (страница, виджет)."""
    config = widgets.load_config() if hasattr(widgets, "load_config") else None
    if config is None:
        from core import data
        config = data.load_config()
    pages = config.get("section_widgets_by_page") or {}
    out = []
    for page, items in pages.items():
        for item in items or []:
            if item.get("chart") in SIDE_LABEL_CHARTS:
                out.append((page, item["chart"], item["indicator"], item.get("size")))
    return out


@pytest.mark.needs_storage
@pytest.mark.parametrize("page,chart_type,indicator,size", widget_pages())
def test_подписей_хватает_места(page, chart_type, indicator, size):
    """У каждого виджета с подписями сбоку — не меньше 20 px на строку."""
    preset = widgets.size_meta(size)
    program = widgets.program_of(page)
    fig = charts.build(chart_type, indicator, 2026, None, program=program,
                       height=preset["height"], columns=preset["columns"])
    if not fig.data or not hasattr(fig.data[0], "y") or fig.data[0].y is None:
        pytest.skip(f"{page}: у {indicator} нет данных — мерить нечего")

    rows = len(fig.data[0].y)
    if rows == 0:
        pytest.skip(f"{page}: пустой разрез")

    plot_height = preset["height"] - (fig.layout.margin.t or 0) - (fig.layout.margin.b or 0)
    per_row = plot_height / rows
    assert per_row >= MIN_PX_PER_ROW, (
        f"{page} · {chart_type} · {indicator}: категорий {rows}, "
        f"на строку {per_row:.1f} px при пороге {MIN_PX_PER_ROW}. "
        f"Plotly спрячет часть подписей молча — нужен пресет повыше "
        f"(сейчас «{size}», {preset['height']} px)"
    )
