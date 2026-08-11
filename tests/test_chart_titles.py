"""Заголовок диаграммы: разрез, подставленный год, перенос по ширине.

Правила все три написаны кровью:

1. **разрез в заголовке** — без него семь диаграмм Өрлеу назывались
   одинаково («Выдано кредитов — 2026 год»), и чем они отличаются,
   приходилось угадывать по картинке (11.08.2026);
2. **пометка подставленного года** — тихо показать 2024-й там, где выбран
   2026-й, худший вид ошибки: цифры выглядят свежими, а заметить подмену
   нечем;
3. **перенос вместо обрезки** — заголовок длиннее поля уезжает за край
   молча, без ошибки (замерено: 501 px текста в виджете 335 px).

Хранилище не нужно: `Ctx.title` берёт название и единицы из `config.yaml`.
"""

import pytest

from core import charts


def ctx(**kwargs):
    """Контекст диаграммы с разумными умолчаниями."""
    base = dict(indicator="budget_spent", year=2026, regions=None)
    base.update(kwargs)
    return charts.Ctx(**base)


def test_разрез_попадает_в_заголовок():
    assert "по банкам (БВУ)" in ctx(cut="по банкам (БВУ)").title


def test_без_разреза_заголовок_прежний():
    """Виды, которые ничего не режут (итог, шкала), не должны ничего дописывать."""
    assert ctx().title.endswith("— 2026 год")
    assert " по " not in ctx().title


def test_подставленный_год_помечен():
    """Показали не тот год, что просили, — обязаны сказать об этом."""
    title = ctx(year=2024, asked_year=2026).title
    assert "2024 год" in title
    assert "за 2026 данных нет" in title


def test_совпавший_год_не_помечается():
    assert "данных нет" not in ctx(year=2026, asked_year=2026).title


def test_широкий_виджет_держит_заголовок_одной_строкой():
    """12 колонок — вся ширина сетки, переносить нечего."""
    title = ctx(cut="по регионам", columns=12).title
    assert "<br>" not in title
    assert " — " in title


def test_узкий_виджет_переносит_год_на_вторую_строку():
    """6 колонок — самый тесный случай на экране 1024 (замер: 336 px)."""
    title = ctx(cut="по субъектности", columns=6).title
    head, _, tail = title.partition("<br>")
    assert tail, "в узком виджете заголовок обязан переноситься"
    assert "по субъектности" in head
    assert tail == "2026 год"


def test_год_никогда_не_рвётся_пополам():
    """«2026 / год» на двух строках — то, ради чего год переносится целиком."""
    for columns in (4, 6, 12):
        for indicator in ("budget_spent", "see_tax_revenue"):
            title = charts.Ctx(indicator=indicator, year=2026, regions=None,
                               cut="по отраслям (ОКЭД)", columns=columns).title
            for line in title.split("<br>"):
                assert line.strip() != "год", f"год оторвался: {title!r}"


def test_очень_длинный_заголовок_не_растёт_бесконечно():
    """Три строки — потолок, иначе заголовок съедает сам график."""
    title = charts.Ctx(indicator="see_tax_revenue", year=2024, regions=None,
                       asked_year=2026, cut="по отраслям (ОКЭД)",
                       columns=4).title
    assert title.count("<br>") + 1 <= charts.TITLE_MAX_LINES


def test_пометка_года_остаётся_при_переносе():
    """Строки режутся, но предупреждение про год теряться не должно."""
    title = charts.Ctx(indicator="see_tax_revenue", year=2024, regions=None,
                       asked_year=2026, cut="по регионам", columns=6).title
    assert "за 2026 данных нет" in title


@pytest.mark.parametrize("columns,expected_max", [(4, 22), (6, 33), (12, 66)])
def test_чем_уже_виджет_тем_короче_строка(columns, expected_max):
    """Бюджет строки считается от ширины пресета, а не одним числом на всех."""
    title = charts.Ctx(indicator="see_tax_revenue", year=2026, regions=None,
                       cut="по отраслям (ОКЭД)", columns=columns).title
    for line in title.split("<br>"):
        assert len(line) <= expected_max + 2, f"строка длиннее бюджета: {line!r}"
