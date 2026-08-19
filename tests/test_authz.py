"""Что защищает сервер, а не интерфейс.

Все три проверки здесь — про находки внешнего аудита 18.08.2026, и все три
про одно свойство: **спрятать кнопку не значит запретить действие**. Коллбэк
Dash — это обычный POST на `/_dash-update-component`, его можно позвать
напрямую, минуя разметку; запрос к хранилищу можно испортить значением
из адреса; прогон ETL можно запустить вторым, пока идёт первый.

Почему это стоит тестов, хотя правило проекта — «тесты только там, где цена
ошибки в неверных цифрах». Здесь цена выше: не разъехавшаяся рамка,
а чужая правка плана или подменённое условие запроса. И, в отличие от
рамки, глазами это не видно вообще — отказ и поломка на экране выглядят
одинаково.
"""

import time

import pytest

# !! `import app` первым: страницы зовут `dash.register_page()` на импорте,
# а Dash разрешает это только после создания приложения. Сайт не поднимается.
import app  # noqa: F401
from dash.exceptions import PreventUpdate

from core import auth, publish, widgets
from etl import run as etl_run
from pages import plan_input, widgets_edit


@pytest.fixture
def viewer(monkeypatch):
    """Подменяет роль на «зритель» — заглушка auth иначе всех считает админом."""
    monkeypatch.setattr(auth, "current_role", lambda: auth.VIEWER)
    return auth.VIEWER


# ------------------------------------------------- роль внутри коллбэка

@pytest.mark.parametrize("call", [
    pytest.param(
        lambda: widgets_edit.change_structure(
            1, None, [], [], [], "see:years_output", None, None, None),
        id="виджеты: состав набора",
    ),
    pytest.param(
        lambda: widgets_edit.change_field([], [], [], "see:years_output"),
        id="виджеты: поле виджета",
    ),
    pytest.param(
        lambda: plan_input.handle_actions([], [], [], 1),
        id="план: отмена черновика и вето",
    ),
])
def test_viewer_cannot_reach_mutating_callbacks(viewer, call):
    """Зритель не входит в изменяющий коллбэк, даже позвав его напрямую.

    Именно «позвав напрямую»: страницы этих коллбэков зрителю не открываются
    (`layout()` отдаёт плашку), но разметка — не преграда для POST.
    """
    with pytest.raises(PreventUpdate):
        call()


def test_admin_still_passes_the_guard():
    """Сторож не должен закрывать дорогу тому, ради кого страница и сделана.

    Проверяем сам сторож, а не коллбэк целиком: тело ходит в хранилище,
    и падение там означало бы «нет данных», а не «не пустили».
    """
    calls = []

    @auth.admin_only
    def action():
        calls.append(1)
        return "сделано"

    assert auth.is_admin(), "заглушка auth перестала считать разработчика админом"
    assert action() == "сделано"
    assert calls == [1]


# ------------------------------------------------- значение из адреса в SQL

def test_page_from_url_cannot_rewrite_the_query():
    """Классическая подстановка в `WHERE page = ...` не меняет условие.

    До 19.08.2026 номер страницы склеивался в текст запроса f-строкой,
    и `x' OR '1'='1` превращал «набор этой страницы настроен?» в «настроен
    хоть какой-нибудь?» — то есть отвечал `True` для страницы, которой нет.
    """
    assert widgets.is_customized("x' OR '1'='1") is False
    assert widgets.get_widgets("x' OR '1'='1") == widgets.default_widgets(
        "x' OR '1'='1")
    assert widgets.last_change("x' OR '1'='1") is None


def test_quote_in_page_name_does_not_break_the_query():
    """Кавычка в значении больше не ломает запрос — она просто значение.

    Обратная сторона той же правки: со склейкой такой ввод давал
    синтаксическую ошибку SQL, то есть страница падала на ровном месте.
    """
    assert widgets.is_customized("it's a page") is False


# ------------------------------------------------- один прогон ETL за раз

def test_second_etl_run_is_refused_while_first_holds_the_lock(tmp_path, monkeypatch):
    """Второй прогон уходит, не сделав ничего, — и это НЕ ошибка."""
    monkeypatch.setattr(etl_run, "LOCK_PATH", tmp_path / "etl.lock")

    with etl_run.single_run() as first:
        assert first is True, "первый прогон обязан получить замок"
        with etl_run.single_run() as second:
            assert second is False, "второй прогон не должен пройти внутрь"

    assert not (tmp_path / "etl.lock").exists(), "замок обязан сниматься на выходе"


def test_abandoned_lock_does_not_stop_etl_forever(tmp_path, monkeypatch):
    """Замок, оставшийся от убитого процесса, снимается по возрасту.

    Иначе одно падение остановило бы загрузку данных навсегда, а заметили
    бы это по остывшим цифрам через сутки — самый дорогой способ узнать.
    """
    lock = tmp_path / "etl.lock"
    monkeypatch.setattr(etl_run, "LOCK_PATH", lock)
    lock.write_text("pid=999999 started=давно\n", encoding="utf-8")
    old = time.time() - etl_run.LOCK_STALE_AFTER - 10
    import os
    os.utime(lock, (old, old))

    with etl_run.single_run() as got:
        assert got is True, "брошенный замок обязан перехватываться"


def test_fresh_lock_is_respected(tmp_path, monkeypatch):
    """А вот свежий чужой замок трогать нельзя — там идёт работа."""
    lock = tmp_path / "etl.lock"
    monkeypatch.setattr(etl_run, "LOCK_PATH", lock)
    lock.write_text("pid=1 started=сейчас\n", encoding="utf-8")

    with etl_run.single_run() as got:
        assert got is False
    assert lock.exists(), "чужой замок не должен исчезнуть после отказа"


# ------------------------------------------------- время публикации

def test_publish_time_does_not_depend_on_server_timezone():
    """9:00 — это девять по Астане, а не по настройке сервера.

    Проверяем не «который час», а что деловое время берётся из ИМЕНИ пояса:
    сравниваем с часами того же пояса. Совпадение с `datetime.now()` ничего
    не доказало бы — на машине разработчика пояс и так казахстанский.
    """
    from datetime import datetime

    expected = datetime.now(publish.BUSINESS_TZ).replace(tzinfo=None)
    got = publish.business_now()
    assert abs((got - expected).total_seconds()) < 5
    assert got.tzinfo is None, (
        "штампы в хранилище наивные — осведомлённое время с ними не сравнится"
    )
    assert str(publish.BUSINESS_TZ) == "Asia/Almaty"
