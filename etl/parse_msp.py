"""Разбор выгрузки «Основные показатели деятельности субъектов МСП».

Превращает двухблочную таблицу, свёрстанную для печати, в длинную таблицу фактов.
Оригинал в data/raw/ никогда не изменяется — правится только этот разбор.

Запуск из корня проекта:  python -m etl.parse_msp
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

SRC_PATH = Path("data/raw/Основные показатели деятельности субъектов МСП.xlsx")
OUT_PATH = Path("data/facts.csv")

TOTAL_LABEL = "Республика Казахстан"
ROWS_PER_BLOCK = 21  # строка итога по РК + 20 регионов

# Канонические колонки таблицы фактов.
# Их знают все разборщики и все виджеты — в этом весь смысл общей формы.
COLUMNS = [
    "indicator", "report_year", "date", "period",
    "region", "instrument", "program",
    "is_total", "value", "source_file", "loaded_at",
]

# Что на самом деле лежит в каждой колонке каждого блока.
# Шапка в файле двухэтажная, с объединёнными ячейками и разнобоем в пробелах
# («2025 г.» против «2025г.»), поэтому описываем её вручную — так надёжнее,
# чем разбирать автоматически.
SPEC = [
    # блок, колонка, показатель,     год,  дата,         тип величины
    (1, 1, "registered_smb", 2025, "2025-10-01", "на дату"),
    (1, 2, "active_smb",     2025, "2025-10-01", "на дату"),
    (1, 3, "registered_smb", 2024, "2024-10-01", "на дату"),
    (1, 4, "active_smb",     2024, "2024-10-01", "на дату"),
    (2, 1, "employed",       2025, "2025-10-01", "на дату"),
    (2, 2, "output",         2025, "2025-09-30", "ytd"),
    (2, 3, "employed",       2024, "2024-10-01", "на дату"),
    (2, 4, "output",         2024, "2024-09-30", "ytd"),
]


def find_block_starts(raw: pd.DataFrame) -> list[int]:
    """Ищем блоки по строке итога, а не по номерам строк.

    Тогда сдвиг шапки на пару строк в следующей выгрузке ничего не сломает.
    """
    names = raw[0].astype(str).str.strip()
    starts = names.index[names == TOTAL_LABEL].tolist()
    if len(starts) != 2:
        raise ValueError(
            f"Ожидал 2 блока данных, нашёл {len(starts)}. Формат файла изменился?"
        )
    return starts


def parse(src: Path = SRC_PATH) -> pd.DataFrame:
    raw = pd.read_excel(src, sheet_name=0, header=None)
    starts = find_block_starts(raw)
    loaded_at = datetime.now().isoformat(timespec="seconds")

    rows = []
    for block_no, start in enumerate(starts, start=1):
        block = raw.iloc[start : start + ROWS_PER_BLOCK]
        for spec_block, col, indicator, year, date, period in SPEC:
            if spec_block != block_no:
                continue
            for _, r in block.iterrows():
                value = r[col]
                if pd.isna(value):
                    continue
                # В файле у части названий хвостовой пробел («Актюбинская »).
                # Глазом не видно, а группировку ломает — чистим сразу.
                region = str(r[0]).strip()
                rows.append(
                    {
                        "indicator": indicator,
                        "report_year": year,
                        "date": date,
                        "period": period,
                        "region": region,
                        "instrument": "",
                        "program": "",
                        "is_total": region == TOTAL_LABEL,
                        "value": float(value),
                        "source_file": src.name,
                        "loaded_at": loaded_at,
                    }
                )

    df = pd.DataFrame(rows)[COLUMNS]
    return df.sort_values(["indicator", "report_year", "region"]).reset_index(drop=True)


def check_totals(df: pd.DataFrame) -> list[str]:
    """Сумма регионов обязана сойтись со строкой «Республика Казахстан».

    Это дешёвая защита от съехавшей шапки: если разбор попадёт не в ту колонку,
    сверка почти наверняка развалится и мы узнаем об этом сразу, а не из отчёта.
    """
    problems = []
    for (indicator, year), g in df.groupby(["indicator", "report_year"]):
        total = g.loc[g.is_total, "value"]
        if total.empty:
            problems.append(f"{indicator} {year}: нет строки итога")
            continue
        diff = g.loc[~g.is_total, "value"].sum() - total.iloc[0]
        if abs(diff) > 0.5:
            problems.append(
                f"{indicator} {year}: сумма регионов расходится с итогом на {diff:+,.0f}"
            )
    return problems


def main() -> None:
    df = parse()

    problems = check_totals(df)
    if problems:
        raise SystemExit("Проверка не пройдена:\n  " + "\n  ".join(problems))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")

    checks = df.groupby(["indicator", "report_year"]).ngroups
    print(f"Готово: {OUT_PATH}")
    print(f"  строк: {len(df)}")
    print(f"  регионов: {df.region.nunique() - 1}  показателей: {df.indicator.nunique()}")
    print(f"  сверка сумм с итогом по РК: пройдена, {checks} проверок")


if __name__ == "__main__":
    main()
