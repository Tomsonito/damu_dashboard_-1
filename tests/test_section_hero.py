"""Герой-карточка раздела: за какой год она показывает число.

Почему это вообще проверяется, а не оставлено на глаз. Карточка стоит
слева от диаграммы и пишет крупное число с годом в подписи. Ошибись она
в выборе года — на экране будет ПРАВДОПОДОБНОЕ число под неправильной
подписью: ни ошибки, ни пустого места, ни какого-либо признака поломки.
Это ровно тот сорт беды, ради которого тесты здесь и пишут, — цена
ошибки в неверных цифрах, а не в съехавшей рамке.

Три правила, которые обязаны держаться:

1. выбран год, за который данные есть, — показываем его;
2. выбран год, за который данных ещё нет (у СЭЭ история обрывается
   на 2024-м, а в шапке можно выбрать 2026-й), — показываем ближайший
   С ЧИСЛАМИ и не позже выбранного, а год пишем в подписи честно;
3. дельта считается к предыдущему году РЯДА, а не к «выбранный минус
   один»: между 2019-м и 2021-м может не быть 2020-го.

Вид карточки (цвета, спарклайн, порядок строк) намеренно не проверяется:
он меняется от замечаний пользователя, ломается заметно и чинится за
минуту. Тест на него только мешал бы правкам.
"""

import pytest

# !! `import app` обязателен и должен идти ПЕРВЫМ. Страницы зовут
# `dash.register_page()` на импорте, а Dash разрешает это только после
# того, как приложение создано. Без этой строки тест падает не на
# проверке, а на сборе: «register_page() must be called after app
# instantiation». Сайт при этом не поднимается — `app.run()` живёт
# под `if __name__ == "__main__"`, импорт до него не доходит.
import app  # noqa: F401  (нужен ради побочного эффекта, а не имени)

from core import widgets
from pages import section

pytestmark = pytest.mark.needs_storage

SECTION = "see"
PROGRAM = "СЭЭ"


def _texts(node, out=None):
    """Все строки внутри собранного куска разметки — сверху вниз."""
    out = [] if out is None else out
    children = getattr(node, "children", None)
    if isinstance(children, str):
        out.append(children)
    elif isinstance(children, list):
        for child in children:
            _texts(child, out)
    elif children is not None:
        _texts(children, out)
    return out


def _tab(key: str) -> dict:
    return next(t for t in widgets.tabs_of(SECTION) if t["key"] == key)


def test_hero_shows_selected_year_when_data_exists():
    card = section.hero_card(_tab("years_output"), 2023, None, PROGRAM)
    assert "Выпуск продукции · 2023" in _texts(card)


def test_hero_falls_back_to_nearest_year_and_says_which():
    """2026-й выбрать можно, данных СЭЭ за него нет — берём 2024-й.

    !! Молча показать число 2024 года под подписью «2026» было бы худшим
    из исходов: цифра выглядит свежей и ничем не помечена. Поэтому год
    в подписи — не украшение, а часть правильного ответа.
    """
    card = section.hero_card(_tab("years_output"), 2026, None, PROGRAM)
    labels = _texts(card)
    assert "Выпуск продукции · 2024" in labels
    assert "Выпуск продукции · 2026" not in labels


def test_hero_delta_counts_against_previous_year_of_the_series():
    """Дельта — к соседу по ряду, а не к «выбранный год минус один»."""
    from core import data

    frame = (data.get_country_years("see_output", None, PROGRAM)
             .sort_values("report_year").reset_index(drop=True))
    at = frame.index[frame["report_year"] <= 2024][-1]
    expected = float(frame.loc[at, "value"]) - float(frame.loc[at - 1, "value"])

    card = section.hero_card(_tab("years_output"), 2024, None, PROGRAM)
    delta_line = [t for t in _texts(card) if " к " in t]
    assert len(delta_line) == 1
    assert delta_line[0].startswith("+" if expected >= 0 else "−")
    assert str(int(frame.loc[at - 1, "report_year"])) in delta_line[0]


def test_indicator_colors_differ_by_tone():
    """Разные тона — разные цвета. Один тест на одну уже случившуюся беду.

    17.08.2026 в `core/charts.py` оказалось ДВЕ функции с именем
    `tone_color`, и Python оставил ту, что ниже по файлу. Карточка звала
    её со строкой вместо номера тона, ни с чем не совпадала и получала
    зелёный. Ни ошибки, ни предупреждения — просто четыре карточки СЭЭ
    одного цвета вместо трёх разных, что выглядит как замысел.

    Проверяем не конкретные цвета (их меняет админ в настройках),
    а то, что разные тона дают РАЗНОЕ. Именно это и сломалось.
    """
    from core import charts

    green = charts.indicator_color("see_output")          # тон 1
    gold = charts.indicator_color("see_jobs_created")     # тон 2
    teal = charts.indicator_color("see_tax_revenue")      # тон 3
    assert len({green, gold, teal}) == 3


def test_hero_number_matches_the_shared_formatter():
    """Число набирается тем же `format_value`, что и остальной сайт.

    Свой формат в карточке означал бы, что одно и то же число выглядит
    на соседних экранах по-разному — а разряды и запятая как раз то,
    на что смотрят, сверяя цифры с бумагой.
    """
    from core import data

    frame = (data.get_country_years("see_output", None, PROGRAM)
             .sort_values("report_year").reset_index(drop=True))
    at = frame.index[frame["report_year"] <= 2024][-1]
    text = data.format_value(float(frame.loc[at, "value"]), "see_output")
    number = text.rsplit(" ", 2)[0] if "млрд" in text else text

    assert number in _texts(section.hero_card(
        _tab("years_output"), 2024, None, PROGRAM))
