"""Загрузка бюджетных показателей по регионам из БД в общую таблицу фактов.

Источник — 50 таблиц `budget_regions_ММ.ГГ`, по одной на месяц. Структура у всех
одинаковая, поэтому они склеиваются одним `UNION ALL` и разворачиваются в длинную
форму **на стороне БД**, а не в Python: наружу едут готовые факты.

Запуск из корня проекта:  python -m etl.load_budget
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from core import db

OUT_PATH = Path("data/facts_budget.csv")
TABLE_PREFIX = "budget_regions"

COLUMNS = [
    "indicator", "report_year", "date", "period",
    "region", "instrument", "program",
    "is_total", "value", "source_file", "loaded_at",
]

# Колонка в БД -> код показателя и тип величины.
# `stock` — срез на дату, `flow` — за месяц. Тип решает, как складывать за год:
# потоки суммируются, срезы берутся по последней дате.
INDICATORS = {
    "budget_allocated_mln": ("budget_allocated", "flow"),
    "budget_spent_mln": ("budget_spent", "flow"),
    "subsidies_issued_mln": ("subsidies_issued", "flow"),
    "new_workplaces_created": ("workplaces_created", "flow"),
    "sme_registered_qty": ("budget_sme_registered", "stock"),
    "sme_active_qty": ("budget_sme_active", "stock"),
    "avg_execution_days": ("avg_execution_days", "stock"),
}

# Названия регионов в БД и в выгрузке МСП не совпадают: «Абайская область»
# против «Абай», «Область Жетысу» против «Жетісу» (казахская і!), «Улытау»
# против «Ұлытау» (Ұ!). Пишем соответствие явно — угадывать такое опасно.
REGION_MAP = {
    "Абайская область": "Абай",
    "Акмолинская область": "Акмолинская",
    "Актюбинская область": "Актюбинская",
    "Алматинская область": "Алматинская",
    "Атырауская область": "Атырауская",
    "Восточно-Казахстанская область": "Восточно-Казахстанская",
    "Жамбылская область": "Жамбылская",
    "Западно-Казахстанская область": "Западно-Казахстанская",
    "Карагандинская область": "Карагандинская",
    "Костанайская область": "Костанайская",
    "Кызылординская область": "Кызылординская",
    "Мангистауская область": "Мангистауская",
    "Область Жетысу": "Жетісу",
    "Область Улытау": "Ұлытау",
    "Павлодарская область": "Павлодарская",
    "Северо-Казахстанская область": "Северо-Казахстанская",
    "Туркестанская область": "Туркестанская",
    "г. Алматы": "г. Алматы",
    "г. Астана": "г. Астана",
    "г. Шымкент": "г. Шымкент",
}


def month_tables() -> list[str]:
    """Список помесячных таблиц. Читается из базы, а не зашит в код:
    появится новый месяц — подхватится сам."""
    rows = db.read_sql(
        f"""SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name LIKE '{TABLE_PREFIX}%'
            ORDER BY table_name"""
    )
    return rows["table_name"].tolist()


def build_query(tables: list[str]) -> str:
    """Склеивает таблицы и разворачивает колонки в строки — всё одним запросом.

    Разворот (unpivot) делается в SQL, чтобы из базы приехала уже длинная форма.
    Тянуть широкие таблицы в Python и разворачивать там — лишний трафик.
    """
    union = " UNION ALL ".join(f'SELECT * FROM public."{t}"' for t in tables)
    parts = [
        f"""SELECT region_name, report_date, '{code}' AS indicator,
                   '{kind}' AS period, {column}::double precision AS value
            FROM all_months"""
        for column, (code, kind) in INDICATORS.items()
    ]
    return f"WITH all_months AS ({union})\n" + "\nUNION ALL\n".join(parts)


def load() -> pd.DataFrame:
    tables = month_tables()
    if not tables:
        raise SystemExit(f"В базе нет таблиц {TABLE_PREFIX}*. Проверьте DATABASE_URL в .env")

    df = db.read_sql(build_query(tables))

    unknown = set(df["region_name"]) - set(REGION_MAP)
    if unknown:
        raise SystemExit(
            "В базе появились регионы, которых нет в REGION_MAP:\n  "
            + "\n  ".join(sorted(unknown))
            + "\nДобавьте их в соответствие, иначе они молча не сойдутся с данными МСП."
        )

    df["region"] = df["region_name"].map(REGION_MAP)
    df["date"] = pd.to_datetime(df["report_date"]).dt.strftime("%Y-%m-%d")
    df["report_year"] = pd.to_datetime(df["report_date"]).dt.year
    df["instrument"] = ""
    df["program"] = ""
    df["is_total"] = False
    df["source_file"] = f"БД test_ai, {len(tables)} таблиц {TABLE_PREFIX}*"
    df["loaded_at"] = datetime.now().isoformat(timespec="seconds")

    return df[COLUMNS].sort_values(["indicator", "date", "region"]).reset_index(drop=True)


def main() -> None:
    df = load()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    print(f"Готово: {OUT_PATH}")
    print(f"  строк: {len(df):,}")
    print(f"  показателей: {df.indicator.nunique()}  регионов: {df.region.nunique()}")
    print(f"  период: {df.date.min()} — {df.date.max()}")


if __name__ == "__main__":
    main()
