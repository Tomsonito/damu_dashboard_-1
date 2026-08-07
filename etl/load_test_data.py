import os
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

from core.data import _connect_write

DIR_PATH = Path(r"c:\Users\User\Desktop\файлы для теста")

FACT_COLUMNS = [
    "indicator", "report_year", "date", "period", "region", "industry",
    "bank", "subject_type", "loan_purpose",
    "instrument", "program", "source_program", "is_total", "value",
    "source_file", "loaded_at",
]

#: Разрезы, которые лежат в выгрузках, и колонка таблицы фактов под каждый.
#: Названия колонок в двух файлах разные, поэтому сопоставление своё у каждого
#: разборщика; общая здесь только цель — привести к одному имени.
#:
#: `!!` В «Гарантировании» колонка «Банк» идёт ДВАЖДЫ, и pandas называет
#: вторую «Банк.1». Значения в них совпадают (проверено), берём первую.
#: Там же у части колонок есть пара «полное / сгруппированное»
#: (`Отрасль`/`Отрасль_Г`, `Цель_кредитования`/`Цель`): берём
#: сгруппированную — источник уже свёл в ней разные формулировки одного
#: и того же, и делать это второй раз незачем.

#: Субъектность в двух файлах названа по-разному: «Средний» против «Средние».
#: Сводим к одному слову, иначе один и тот же тип субъекта разъедется на два.
SUBJECT_TYPE = {
    "Микро/Малый": "Микро и малые", "Микро и малые": "Микро и малые",
    "Средний": "Средние", "Средние": "Средние",
    "Крупный": "Крупные", "Крупные": "Крупные",
}

#: То же с целью кредитования. «ПОС» в «Гарантировании» — это пополнение
#: оборотных средств; «Рефинансирование» встречается только в базе ПОР.
LOAN_PURPOSE = {
    "Инвест": "Инвестиционный", "Инвестиционный": "Инвестиционный",
    "Смешан": "Смешанный", "Смешанный": "Смешанный",
    "ПОС": "Пополнение оборотных средств",
    "Пополнение оборотных средств": "Пополнение оборотных средств",
    "Рефинансирование": "Рефинансирование",
}


def clean_text(series: pd.Series) -> pd.Series:
    """Обрезает края и двойные пробелы. `Евразийский ` — из настоящих данных."""
    return (series.fillna("Неизвестно").astype(str)
            .str.replace(r"\s+", " ", regex=True).str.strip()
            .replace("", "Неизвестно"))


def by_dict(series: pd.Series, mapping: dict) -> pd.Series:
    """Приводит значение к канону. Незнакомое оставляем как есть.

    Прятать незнакомое нельзя: оно молча выпало бы из итога. Пусть лучше
    вылезет на экран лишней подписью — так его заметят и допишут в словарь.
    """
    text = clean_text(series)
    return text.map(lambda v: mapping.get(v, v))

#: !! Колонка `program` в этом проекте означает РАЗДЕЛ САЙТА, а не программу
#: финансирования. По ней страница раздела отбирает свои строки
#: (`widgets.program_of` берёт название из `config.yaml` → `sections`,
#: `data._only_program` по нему фильтрует).
#:
#: Первая версия разборщика клала сюда программу из выгрузки («ЕКП»,
#: «Обработка», «Гарантирование в рамках ГФ 1»…). Формально данные
#: загрузились, ошибок не было — но **все разделы, кроме СЭЭ, оказались
#: пустыми**: страница искала строки с `program == "Гар. выдача"`, а таких
#: в таблице не существовало (проверено 07.08.2026 — ровно 0 строк).
#:
#: Поэтому: в `program` едет название раздела, а родная программа выгрузки
#: не теряется — она переезжает в `source_program`. Оттуда её возьмут
#: вкладки «Программы/Цели займа», которые пока стоят с заглушками.
SECTION_OF_INSTRUMENT = {
    "Кредитование": "Кредит. выдача",
    "Гарантирование": "Гар. выдача",
}

#: Программы выгрузки, у которых на сайте есть СВОЙ раздел. Такие строки
#: уходят в него, а не в общий раздел инструмента: «Өрлеу» — отдельный
#: пункт меню, и показывать его же внутри «Кредит. выдачи» значило бы
#: посчитать одни и те же выдачи дважды в двух разных местах.
SECTION_OF_PROGRAM = {
    "Өрлеу": "Өрлеу",
}


def section_for(instrument: pd.Series, program: pd.Series) -> pd.Series:
    """Раздел сайта для каждой строки: по программе, иначе по инструменту."""
    own = program.map(SECTION_OF_PROGRAM)
    return own.fillna(instrument.map(SECTION_OF_INSTRUMENT)).fillna("Неизвестно")

def load_credits() -> pd.DataFrame:
    path = DIR_PATH / "База ПОР 01.07.2026 Өрлеу 31.07.2026.xlsx"
    print(f"Loading {path.name}...")
    df = pd.read_excel(path)
    
    # Mapping
    out = pd.DataFrame()
    out["indicator"] = ["credits_issued"] * len(df)
    
    # "Дата выдачи займа/ микрокредита/ оплаты по предмету лизинга"
    date_col = "Дата выдачи займа/ микрокредита/ оплаты по предмету лизинга"
    dates = pd.to_datetime(df[date_col], errors='coerce')
    out["report_year"] = dates.dt.year.fillna(datetime.now().year).astype(int)
    # We round dates to the first day of the month as in load_demo.py
    out["date"] = dates.dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d").fillna("2026-07-01")
    
    out["period"] = "month"
    out["region"] = clean_text(df["Область"])
    out["instrument"] = "Кредитование"
    out["source_program"] = clean_text(df["Программа"])
    out["program"] = section_for(out["instrument"], out["source_program"])
    # Разрезы, ради которых вкладки «ОКЭД», «БВУ», «Субъектность» и «Цели
    # займа» стояли с заглушкой «ждёт источника»: всё это лежало в файле
    # с самого начала, разборщик просто до них не доходил
    out["industry"] = clean_text(df["Отрасль экономики (сектор экономики) ОКЭД"])
    out["bank"] = clean_text(df["Наименование Банка/ Приниципала/ МФО/ ЛК"])
    out["subject_type"] = by_dict(df["Субъектность"], SUBJECT_TYPE)
    out["loan_purpose"] = by_dict(df["Объект кредитования"], LOAN_PURPOSE)
    out["is_total"] = False
    
    # Sum in excel might be in raw tenge or millions.
    # We will assume it's raw tenge and we convert to millions if it's very large, 
    # but the config can handle divisor: 1000000. Let's just output raw and let config handle it, 
    # or divide here. In `load_demo.py` they just take value as is.
    val_col = "Сумма фактической выдачи средств"
    # Convert to float, coercing errors
    out["value"] = pd.to_numeric(df[val_col], errors='coerce').fillna(0)
    
    out["source_file"] = path.name
    out["loaded_at"] = datetime.now().isoformat(timespec="seconds")
    
    return out[FACT_COLUMNS]

def load_guarantees() -> pd.DataFrame:
    path = DIR_PATH / "Гарантирование.xlsx"
    print(f"Loading {path.name}...")
    df = pd.read_excel(path)
    
    # This file has both Сумма_кредита and Сумма_гарантии
    # We need to melt it or create two separate sets of rows
    dates = pd.to_datetime(df["Дата"], errors='coerce')
    base_df = pd.DataFrame({
        "report_year": dates.dt.year.fillna(datetime.now().year).astype(int),
        "date": dates.dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d").fillna("2026-07-01"),
        "period": "month",
        "region": clean_text(df["Филиал"]),
        "instrument": "Гарантирование",
        "source_program": clean_text(df["Программа"]),
        "program": "Гар. выдача",
        # Те же четыре разреза, что и у кредитов, только колонки называются
        # иначе. Берём сгруппированные (`_Г`, `Тип`, `Цель`): источник уже
        # свёл в них разные формулировки одного и того же
        "industry": clean_text(df["Отрасль_Г"]),
        "bank": clean_text(df["Банк"]),
        "subject_type": by_dict(df["Тип"], SUBJECT_TYPE),
        "loan_purpose": by_dict(df["Цель"], LOAN_PURPOSE),
        "is_total": False,
        "source_file": path.name,
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    })
    
    # credits
    cred_df = base_df.copy()
    cred_df["indicator"] = "credits_issued"
    cred_df["value"] = pd.to_numeric(df["Сумма_кредита"], errors='coerce').fillna(0)
    
    # guarantees
    guar_df = base_df.copy()
    guar_df["indicator"] = "guarantees_issued"
    guar_df["value"] = pd.to_numeric(df["Сумма_гарантии"], errors='coerce').fillna(0)
    
    out = pd.concat([cred_df, guar_df], ignore_index=True)
    return out[FACT_COLUMNS]

#: Годы, за которые разрез по отраслям в выгрузке СЭЭ НЕ является разрезом.
#:
#: !! Проверено на данных 07.08.2026: за 2025 год все 19 отраслей имеют одно
#: и то же значение (выпуск 1385,05 у каждой; налоги 98,38 у каждой), тогда
#: как в 2024-м разброс честный — от 10 088 у обрабатывающей промышленности
#: до 0,9 у госуправления. Это похоже на республиканский итог, размазанный
#: по строкам, а не на разбивку по ОКЭД.
#:
#: Грузить такое нельзя: на экране получаются двадцать одинаковых полос под
#: настоящими подписями — тот же обман, что запрещает показывать макетные
#: числа без плашки. Разрез по регионам за 2025-й в файле и вовсе
#: отсутствует, так что после этой отсечки оба разреза СЭЭ честно кончаются
#: на 2024-м, и подстановка года (`data.resolve_year`) показывает его.
#:
#: Когда источник подтвердит, что за 2025-й есть настоящая разбивка, —
#: очистить этот список, и год поедет на витрину сам.
SKIP_INDUSTRY_YEARS = {2025}

#: Названия отраслей приходят в трёх видах одновременно, и их надо свести
#: к одному, иначе одна отрасль расколется на две и суммы разъедутся:
#:
#: 1. КАПСОМ в части лет («J-ИНФОРМАЦИЯ И СВЯЗЬ» в 2022-м против
#:    «J-Информация и связь» в остальных) — 4 отрасли из 19;
#: 2. с кириллической «О» вместо латинской «O» в коде секции
#:    («О-ГОСУДАРСТВЕННОЕ УПРАВЛЕНИЕ…») — глазом не отличить;
#: 3. с двойным пробелом внутри («ОБЯЗАТЕЛЬНОЕ  СОЦИАЛЬНОЕ»).
CYRILLIC_TO_LATIN = str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX")


def clean_industry(name) -> str:
    """Каноническое название отрасли: код секции латиницей, название с прописной.

    Приводим здесь, в разборе, а не на витрине: витрина обязана получать
    данные готовыми, иначе каждое место, где отрасли группируются, должно
    было бы повторять эту же чистку — и однажды одно из них её забудет.
    """
    text = " ".join(str(name).split())          # двойные пробелы и края
    code, sep, rest = text.partition("-")
    if sep and len(code) <= 2:
        code = code.upper().translate(CYRILLIC_TO_LATIN)
        rest = rest.strip()
        # Капс приводим к обычному виду: первая буква прописная, остальные
        # строчные. `capitalize()` не годится — он ломает слова после точек
        if rest.isupper():
            rest = rest[:1].upper() + rest[1:].lower()
        return f"{code}-{rest}"
    return text


def load_see() -> pd.DataFrame:
    path = DIR_PATH / "СЭЭ - Общий.xlsx"
    print(f"Loading {path.name} (Region and Industry sheets)...")

    # 1. Industry Sheet (Table1 (2))
    df_ind = pd.read_excel(path, sheet_name="Table1 (2)")
    out_ind = pd.DataFrame()
    indicator_map_ind = {
        "Выпуск продукции (в сумме, млрд тенге)": "see_output_industry",
        "Количество созданных рабочих мест (ед.)": "see_jobs_created_industry",
        "Количество сохраненных рабочих мест (ед.)": "see_jobs_saved_industry",
        "Налоговые поступления (в сумме, млрд тенге)": "see_tax_revenue_industry"
    }
    out_ind["indicator"] = df_ind["Attribute"].map(indicator_map_ind).fillna("see_unknown")
    out_ind["report_year"] = pd.to_numeric(df_ind["Год"], errors='coerce').fillna(datetime.now().year).astype(int)
    out_ind["date"] = out_ind["report_year"].astype(str) + "-12-31"
    out_ind["period"] = "YTD"
    out_ind["program"] = "СЭЭ"          # раздел сайта
    out_ind["source_program"] = "СЭЭ"   # своей программы у выгрузки нет
    out_ind["instrument"] = "СЭЭ"
    out_ind["industry"] = df_ind["ОКЭД"].fillna("Неизвестно").map(clean_industry)
    out_ind["region"] = "Неизвестно"
    # У выгрузки СЭЭ этих разрезов нет вовсе — ставим заглушку явно,
    # иначе строки не сойдутся по колонкам с остальными разборщиками
    out_ind["bank"] = "Неизвестно"
    out_ind["subject_type"] = "Неизвестно"
    out_ind["loan_purpose"] = "Неизвестно"
    out_ind["is_total"] = False
    out_ind["value"] = pd.to_numeric(df_ind["Value"], errors='coerce').fillna(0)
    out_ind["source_file"] = path.name
    out_ind["loaded_at"] = datetime.now().isoformat(timespec="seconds")

    # Годы, где «разрез» на деле один и тот же итог по всем отраслям
    if SKIP_INDUSTRY_YEARS:
        dropped = out_ind["report_year"].isin(SKIP_INDUSTRY_YEARS)
        if dropped.any():
            years = sorted(out_ind.loc[dropped, "report_year"].unique())
            print(f"  ! разрез по отраслям за {years} пропущен: "
                  f"{dropped.sum()} строк — все отрасли с одинаковым значением "
                  f"(см. SKIP_INDUSTRY_YEARS)")
            out_ind = out_ind[~dropped]

    # 2. Region Sheet (Table1)
    df_reg = pd.read_excel(path, sheet_name="Table1")
    out_reg = pd.DataFrame()
    indicator_map_reg = {
        "Выпуск продукции (в сумме, млрд тенге)": "see_output",
        "Количество созданных рабочих мест (ед.)": "see_jobs_created",
        "Количество сохраненных рабочих мест (ед.)": "see_jobs_saved",
        "Налоговые поступления (в сумме, млрд тенге)": "see_tax_revenue"
    }
    out_reg["indicator"] = df_reg["Column2"].map(indicator_map_reg).fillna("see_unknown")
    out_reg["report_year"] = pd.to_numeric(df_reg["Год"], errors='coerce').fillna(datetime.now().year).astype(int)
    out_reg["date"] = out_reg["report_year"].astype(str) + "-12-31"
    out_reg["period"] = "YTD"
    out_reg["program"] = "СЭЭ"
    out_reg["source_program"] = "СЭЭ"
    out_reg["instrument"] = "СЭЭ"
    out_reg["industry"] = "Неизвестно"
    out_reg["region"] = df_reg["Column1"].fillna("Неизвестно")
    # У выгрузки СЭЭ этих разрезов нет вовсе — ставим заглушку явно,
    # иначе строки не сойдутся по колонкам с остальными разборщиками
    out_reg["bank"] = "Неизвестно"
    out_reg["subject_type"] = "Неизвестно"
    out_reg["loan_purpose"] = "Неизвестно"
    out_reg["is_total"] = False
    out_reg["value"] = pd.to_numeric(df_reg["Value"], errors='coerce').fillna(0)
    out_reg["source_file"] = path.name
    out_reg["loaded_at"] = datetime.now().isoformat(timespec="seconds")
    
    out = pd.concat([out_ind, out_reg], ignore_index=True)
    return out[FACT_COLUMNS]

def run():
    print("Parsing files...")
    df1 = load_credits()
    df2 = load_guarantees()
    df3 = load_see()
    
    all_facts = pd.concat([df1, df2, df3], ignore_index=True)
    print(f"Total raw rows parsed: {len(all_facts)}")
    
    # Aggregate data to avoid passing massive transactional data into the dashboard's memory
    # !! "industry" здесь стояла ДВАЖДЫ. Pandas это стерпел, но ключ,
    # повторённый в списке, — верный способ однажды получить дубли строк
    # или падение на новой версии. Ключи группировки — все колонки таблицы
    # фактов, кроме самого значения: тогда список не разъедется со схемой
    group_cols = [c for c in FACT_COLUMNS if c != "value"]
    all_facts = all_facts.groupby(group_cols, as_index=False)["value"].sum()
    print(f"Total aggregated rows for DB: {len(all_facts)}")
    
    # Print sample values to determine scale
    print("\nSample values:")
    print(all_facts.groupby("indicator")["value"].describe())
    
    con = _connect_write()
    try:
        con.execute("BEGIN")
        con.register("fresh_demo", all_facts)
        # We replace the entire demo table for the test
        con.execute("DROP TABLE IF EXISTS demo_facts")
        con.execute("CREATE TABLE demo_facts AS SELECT * FROM fresh_demo")
        con.execute("COMMIT")
        print("Data successfully loaded into demo_facts!")
    except Exception as e:
        con.execute("ROLLBACK")
        print(f"Error loading to DB: {e}")
        raise
    finally:
        con.close()

if __name__ == "__main__":
    run()
