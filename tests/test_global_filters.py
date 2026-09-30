"""Глобальные фильтры и честная подпись времени публикации."""

import app


def test_filters_are_visible_global_controls(monkeypatch):
    monkeypatch.setattr(app.data, "get_years", lambda: [2026, 2025])
    monkeypatch.setattr(
        app.data,
        "get_region_choices",
        lambda: [{"label": "Астана", "value": "Астана"}],
    )

    bar = app.filters_bar()
    year_field, region_field, actions = bar.children

    assert bar.className == "damu-filters"
    assert bar.to_plotly_json()["props"]["role"] == "region"
    assert year_field.children[1].value == 2026
    assert year_field.children[0].className == "visually-hidden"
    assert region_field.children[1].placeholder == "Все регионы"
    assert region_field.children[0].className == "visually-hidden"
    assert region_field.children[1].labels["search"] == "Найти регион"
    assert region_field.children[1].labels["select_all"] == "Выбрать все"
    assert actions.children[0].children == "Показано: 2026 · все регионы"
    assert actions.children[1].disabled is True


def test_filter_summary_and_reset_state(monkeypatch):
    monkeypatch.setattr(app.data, "get_years", lambda: [2026, 2025])

    summary, disabled = app.describe_filters(2025, ["Астана", "Алматы"])
    assert summary == "Показано: 2025 · регионов: 2"
    assert disabled is False

    summary, disabled = app.describe_filters(2026, None)
    assert summary == "Показано: 2026 · все регионы"
    assert disabled is True


def test_navbar_calls_timestamp_a_publication(monkeypatch):
    monkeypatch.setattr(
        app.theme,
        "get_theme",
        lambda: {"logo": "", "brand": "Дашборд", "navbar": "light"},
    )
    monkeypatch.setattr(app.auth, "is_admin", lambda: False)
    monkeypatch.setattr(app.data, "get_last_update_parts", lambda: ("2 сентября", "11:30"))

    updated = app.navbar().children[-1]
    assert updated.children[0].children == "Данные опубликованы"
    assert "публикации версии" in updated.title
    assert updated.children[1].children[1].children == "2 сентября"
    assert updated.children[1].children[2].children == "11:30"
