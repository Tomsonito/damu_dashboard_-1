"""Чистка кэша: сколько удалять и что трогать нельзя.

Проверка идёт на ВРЕМЕННОЙ папке, а не на настоящей: тест, который может
задеть рабочий кэш, однажды его и снесёт не вовремя.

Почему это вообще проверяется. Кэш — единственное место проекта, которое
растёт само по себе: каждая версия данных заводит свою запись, а старые
никто не спрашивает. К 11.08.2026 так накопилось 2,25 ГБ в 438 файлах.
Ограничитель молчаливый: если он перестанет работать, узнаем не по ошибке,
а по кончившемуся диску.
"""

import time

import pytest

from core import cache as cache_module


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """Своя папка кэша на время теста."""
    monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path))
    return tmp_path


def put(folder, name, mb, age_sec=0):
    """Кладёт файл нужного веса и возраста."""
    path = folder / name
    path.write_bytes(b"x" * int(mb * 1024 * 1024))
    if age_sec:
        old = time.time() - age_sec
        import os
        os.utime(path, (old, old))
    return path


def test_под_лимитом_ничего_не_трогаем(folder):
    put(folder, "a", 1)
    put(folder, "b", 1)
    removed, left = cache_module.sweep(limit_mb=10)
    assert removed == 0
    assert left == pytest.approx(2, abs=0.1)
    assert len(list(folder.iterdir())) == 2


def test_лишнее_удаляется_пока_не_влезет(folder):
    for i in range(6):
        put(folder, f"f{i}", 2, age_sec=600 - i * 60)
    removed, left = cache_module.sweep(limit_mb=6)
    assert removed == 3, "12 МБ при лимите 6 — три файла лишние"
    assert left <= 6


def test_удаляются_самые_старые_а_свежие_остаются(folder):
    old = put(folder, "старый", 4, age_sec=3600)
    fresh = put(folder, "свежий", 4, age_sec=1)
    cache_module.sweep(limit_mb=5)
    assert not old.exists(), "старую запись обязаны убрать первой"
    assert fresh.exists(), "свежая запись — это текущая версия данных"


def test_служебный_счётчик_библиотеки_не_трогаем(folder):
    """Без него библиотека считает кэш пустым, и её собственный порог
    перестаёт работать — то есть чистка сломала бы вторую защиту."""
    counter = put(folder, "__wz_cache_count", 0.001, age_sec=9999)
    put(folder, "жирный", 8, age_sec=1)
    cache_module.sweep(limit_mb=1)
    assert counter.exists()


def test_пустая_папка_не_ошибка(folder):
    assert cache_module.sweep(limit_mb=1) == (0, 0.0)


def test_несуществующая_папка_не_ошибка(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "CACHE_DIR", str(tmp_path / "нет-такой"))
    assert cache_module.sweep(limit_mb=1) == (0, 0.0)


def test_лимит_по_умолчанию_умеренный():
    """Слишком маленький лимит выбрасывал бы текущую версию и заставлял
    собирать таблицу заново (476 мс против 13). Одна запись фактов —
    6,6 МБ, значит в лимит обязано влезать хотя бы несколько штук."""
    assert cache_module.CACHE_LIMIT_MB >= 50
    assert cache_module.CACHE_THRESHOLD >= 10
