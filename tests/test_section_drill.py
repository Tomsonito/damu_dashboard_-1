"""Раскрытие года в месяцы: когда оно уместно, а когда врёт.

Почему это проверяется тестом, а не глазами. У четырёх разделов из пяти
в хранилище лежат все двенадцать месяцев, а у СЭЭ — только декабрь
(проверено 17.08.2026). Раскрой мы декабрьский год «в месяцы», человек
увидел бы ОДИН столбец под заголовком «по месяцам 2024 года» — то есть
годовое число, выданное за внутригодовую динамику. Это не съехавшая
рамка, а неверное утверждение о данных, и цена ошибки тут ровно та,
ради которой тесты и пишут.

Второе, что здесь сторожится, — разбор клика. Ось «Годов» категориальная,
и после раскрытия на том же месте стоят «янв»…«дек». Прими мы «янв»
за год — запрос ушёл бы за несуществующий год, а диаграмма показала бы
пустоту без единого слова о причине.
"""

import pytest

# !! `import app` первым: страницы зовут `dash.register_page()` на импорте,
# а Dash разрешает это только после создания приложения. Сайт не поднимается.
import app  # noqa: F401

from core import data, widgets
from pages import section

pytestmark = pytest.mark.needs_storage


def test_month_label_is_not_taken_for_a_year():
    """«янв» — не год. Раскрытая диаграмма стоит на той же оси."""
    assert section._drill_year({"points": [{"x": "2024"}]}) == 2024
    assert section._drill_year({"points": [{"x": "янв"}]}) is None
    assert section._drill_year({"points": [{"x": "24"}]}) is None
    assert section._drill_year({"points": []}) is None
    assert section._drill_year(None) is None


def test_see_uses_test_months_because_source_is_december_only():
    """У СЭЭ в источнике один месяц — поэтому виджет раскрывается в ВЫДУМАННЫЕ,
    явно помеченные месяцы (`test_months`, 18.08.2026, просьба пользователя),
    а не в настоящий разрез, которого не существует.

    Тест сначала проверяет само предположение о данных: скажем, придёт
    выгрузка с настоящими месяцами — тест упадёт и заставит перечитать
    правило (`test_months` в config.yaml можно будет снять).
    """
    months = data.get_monthly("see_output", 2024, None, "СЭЭ")
    assert len(months) < section.DRILL_MIN_MONTHS, (
        "У СЭЭ появились помесячные данные — тестовую разбивку можно "
        "снять (test_months в config.yaml) и этот тест переписать"
    )

    item = widgets.get_widgets(widgets.page_key("see", "years_output"))[0]
    assert item.get("test_months"), (
        "У виджета годов СЭЭ пропал флаг test_months — источник по-прежнему "
        "знает только декабрь (см. проверку выше), раскрытие снова покажет "
        "один столбец под видом разбивки по месяцам"
    )
    index = f"years_output|{item['id']}"
    figures, notes, classes = section.render_widgets(
        2024, None, 1, "see", ["years_output"], {index: 2024},
        [{"type": "section-widget", "index": index}],
        [{"type": "section-drill-note", "index": index}],
        [{"type": "section-widget-bar", "index": index}],
    )
    # Диаграмма раскрылась в месяцы — тестовые, а не настоящие
    x = [str(v) for v in figures[0].data[0].x]
    assert "янв" in x and "дек" in x
    assert "Тестовая разбивка" in figures[0].layout.title.text
    # И это сказано человеку прямым текстом, а не тихой подменой
    assert "тестовые месяцы" in notes[0].children[0].children
    assert "damu-drilled" in classes[0]


def test_drill_switches_to_months_where_they_exist():
    """У «Гар. выдачи» двенадцать месяцев — раскрытие честное."""
    months = data.get_monthly("guarantees_issued", 2025, None, "Гар. выдача")
    assert len(months) >= section.DRILL_MIN_MONTHS

    item = next(w for w in widgets.get_widgets(widgets.page_key("guarantee", "years"))
                if w["chart"] == "years_total")
    index = f"years|{item['id']}"
    figures, notes, classes = section.render_widgets(
        2025, None, 1, "guarantee", ["years"], {index: 2025},
        [{"type": "section-widget", "index": index}],
        [{"type": "section-drill-note", "index": index}],
        [{"type": "section-widget-bar", "index": index}],
    )
    x = [str(v) for v in figures[0].data[0].x]
    assert "янв" in x and "дек" in x
    # Полка помечена раскрытой — по этой метке CSS прячет «Показать динамику»
    assert "damu-drilled" in classes[0]


def test_see2_drill_uses_explicit_test_months():
    """СЭЭ 2 раскрывается в 12 помеченных тестовых месяцев, не трогая источник."""
    item = widgets.get_widgets(widgets.page_key("see2", "years_output"))[0]
    index = f"years_output|{item['id']}"
    figures, notes, classes = section.render_widgets(
        2024, None, 1, "see2", ["years_output"], {index: 2024},
        [{"type": "section-widget", "index": index}],
        [{"type": "section-drill-note", "index": index}],
        [{"type": "section-widget-bar", "index": index}],
    )
    x = [str(v) for v in figures[0].data[0].x]
    assert "янв" in x and "дек" in x
    assert "Тестовая разбивка" in figures[0].layout.title.text
    assert "damu-drilled" in classes[0]


def test_without_drill_the_chart_stays_yearly():
    """Пустой `section-drill` ничего не меняет — обычный вид раздела."""
    item = next(w for w in widgets.get_widgets(widgets.page_key("guarantee", "years"))
                if w["chart"] == "years_total")
    index = f"years|{item['id']}"
    figures, notes, classes = section.render_widgets(
        2025, None, 1, "guarantee", ["years"], {},
        [{"type": "section-widget", "index": index}],
        [{"type": "section-drill-note", "index": index}],
        [{"type": "section-widget-bar", "index": index}],
    )
    x = [str(v) for v in figures[0].data[0].x]
    assert "2025" in x and "янв" not in x
    assert "Нажмите на столбец года" in notes[0].children
    assert "damu-drilled" not in classes[0]


def test_cut_selection_explains_action_and_has_reset():
    """Скрытая общая подсветка получила инструкцию и явный выход."""
    feedback = section._cut_selection_feedback()
    text, reset = feedback.children
    assert "во всех диаграммах разреза" in text.children
    assert text.to_plotly_json()["props"]["aria-live"] == "polite"
    assert reset.children == "Сбросить"
    assert reset.hidden is True


def test_cut_rows_are_keyboard_selectable():
    """Строка разреза — не только цель для мыши."""
    item = widgets.get_widgets(widgets.page_key("see", "industries"))[0]
    panel = section.cut_panel(item, 2024, None, "СЭЭ", 6, "see")
    row = panel.children[1].children[0]
    props = row.to_plotly_json()["props"]
    assert props["role"] == "button"
    assert props["tabIndex"] == 0
    assert props["aria-pressed"] == "false"
    assert "Подсветить категорию" in props["aria-label"]
