"""Разведка незнакомой базы: что в ней лежит и по чему ловить изменения.

Запуск из корня проекта:  python -m etl.explore

Ничего не меняет — только читает. Первое, что стоит запустить, получив
доступ к боевой базе: без этого непонятно, из чего вообще собирать витрину.
"""

from core import db

# Колонки с таким именем обычно и есть признак изменений для инкрементального ETL
CHANGE_MARKERS = ("updated_at", "modified_at", "changed_at", "modified_date", "last_update")


def main() -> None:
    print("=== СОЕДИНЕНИЕ ===")
    print(" ", db.check_connection().split(",")[0])

    print()
    print("=== ТАБЛИЦЫ ===")
    tables = db.list_tables()
    if tables.empty:
        print("  в схеме public таблиц нет")
        return

    for _, row in tables.iterrows():
        rows = db.count_rows(row["table"])
        print(f"  {row['table']:<24} {rows:>10,} строк, {row['columns']} колонок")
        print(f"    {row['column_names']}")

    print()
    print("=== ПРИЗНАК ИЗМЕНЕНИЙ ===")
    found = False
    for _, row in tables.iterrows():
        columns = [c.strip().lower() for c in row["column_names"].split(",")]
        markers = [c for c in columns if c in CHANGE_MARKERS]
        if markers:
            found = True
            print(f"  {row['table']}: {', '.join(markers)}")
    if not found:
        print("  колонок вида updated_at не найдено")
        print("  → спросить админов, чем ловить изменения: триггер, журнал,")
        print("    автоинкрементный id или полный пересчёт")


if __name__ == "__main__":
    main()
