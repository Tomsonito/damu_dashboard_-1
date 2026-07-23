"""Подключение к источнику данных — боевой БД компании.

Строка подключения живёт в `.env`, а не в коде: файл в `.gitignore`,
поэтому пароль не попадёт в git даже случайно.

Движок создаётся один раз и переиспользуется — SQLAlchemy держит пул
соединений, открывать новое на каждый запрос дорого и незачем.
"""

import os
from functools import lru_cache

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Движок SQLAlchemy. Кэшируется — пул соединений должен быть один на процесс."""
    if not DATABASE_URL:
        raise RuntimeError(
            "В .env нет DATABASE_URL. Пример:\n"
            "  DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname"
        )
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def check_connection() -> str:
    """Проверка живости: возвращает версию СУБД.

    `pool_pre_ping=True` в движке спасает от «протухших» соединений: пул мог
    держать соединение, которое сервер уже закрыл по таймауту.
    """
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT version()")).scalar_one()


def list_tables(schema: str = "public") -> pd.DataFrame:
    """Перечень таблиц со списком колонок — для разведки незнакомой базы."""
    inspector = inspect(get_engine())
    rows = []
    for name in inspector.get_table_names(schema=schema):
        columns = inspector.get_columns(name, schema=schema)
        rows.append(
            {
                "table": name,
                "columns": len(columns),
                "column_names": ", ".join(c["name"] for c in columns),
            }
        )
    return pd.DataFrame(rows)


def count_rows(table: str, schema: str = "public") -> int:
    """Сколько строк в таблице. Отдельно от list_tables — на больших таблицах
    COUNT(*) не бесплатен, и звать его стоит осознанно."""
    with get_engine().connect() as conn:
        return conn.execute(text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')).scalar_one()


def read_sql(query: str) -> pd.DataFrame:
    """Выполнить запрос и вернуть результат таблицей.

    **Агрегировать нужно здесь, на стороне БД** (`GROUP BY`), а не тянуть
    миллионы строк в Python. Наружу должны ехать десятки чисел, а не сырые данные.
    """
    return pd.read_sql(text(query), get_engine())
