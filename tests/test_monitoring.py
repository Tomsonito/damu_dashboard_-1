"""Sentry подключён только к ETL — проверяем именно этот договор.

Почему тест вообще нужен: связка «поймали исключение сами → в Sentry всё
равно ушло» неочевидна и один раз уже сбила с толку при написании кода
(см. комментарий в `etl/run.py`, main()). `sentry_sdk` не перехватывает
исключение здесь глобально — оно уходит через LoggingIntegration, потому
что `log.exception()` это ERROR-запись со стектрейсом. Замени её на
`log.error(..., exc_info=False)` или понизь уровень логгера — отправка
молча прекратится, а тест это заметит раньше пользователя.

Сеть не трогаем: `transport` подменяется на функцию, складывающую конверты
в список (сам `sentry_sdk` называет такую замену «function transport»).
"""

import logging
import warnings

import pytest

from core import monitoring


@pytest.fixture
def sentry_stub(monkeypatch):
    """Свой Sentry на время теста: без сети, без чужого DSN в окружении."""
    import sentry_sdk

    captured = []
    monkeypatch.setenv("SENTRY_DSN", "https://stub@example.ingest.sentry.io/1")
    monkeypatch.setattr(monitoring, "SENTRY_DSN",
                        "https://stub@example.ingest.sentry.io/1")
    with warnings.catch_warnings():
        # sentry_sdk сам предупреждает, что функция-транспорт устарела —
        # предупреждение наше, подавляем его намеренно, а не боремся с ним
        warnings.simplefilter("ignore", DeprecationWarning)
        sentry_sdk.init(dsn=monitoring.SENTRY_DSN,
                        transport=lambda envelope: captured.append(envelope))
    yield captured
    sentry_sdk.init(dsn=None)          # не оставляем клиент висеть между тестами


def test_без_dsn_ничего_не_включается(monkeypatch):
    """Локальная разработка без Sentry — рабочий сценарий, а не ошибка."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(monitoring, "SENTRY_DSN", "")
    assert monitoring.init_etl() is False


def test_пойманное_исключение_всё_равно_доходит_до_sentry(sentry_stub):
    """Главное свойство: except + log.exception() — этого достаточно.

    Явно вызывать sentry_sdk.capture_exception() не нужно — но если это
    свойство когда-нибудь перестанет выполняться (например, поменяют
    интеграцию), тест сообщит об этом раньше, чем пропадёт первая ошибка.
    """
    log = logging.getLogger("etl.run")
    try:
        raise ValueError("прогон упал")
    except Exception:
        log.exception("прогон упал")

    import sentry_sdk
    sentry_sdk.flush(timeout=2)
    assert len(sentry_stub) == 1


def test_обычный_info_не_летит_в_sentry(sentry_stub):
    """Событие ERROR — не каждая строка лога. Иначе кабинет Sentry
    захлебнётся сотнями обычных записей о свежих версиях данных."""
    log = logging.getLogger("etl.run")
    log.info("версия 12: 7 000 строк, сверка сошлась")

    import sentry_sdk
    sentry_sdk.flush(timeout=2)
    assert len(sentry_stub) == 0
