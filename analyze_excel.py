import pandas as pd
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

dir_path = r"c:\Users\User\Desktop\файлы для теста"
files = [
    "База ПОР 01.07.2026 Өрлеу 31.07.2026.xlsx",
    "Гарантирование.xlsx",
    "СЭЭ - Общий.xlsx",
    "СЭЭ.xlsx"
]

for file in files:
    file_path = os.path.join(dir_path, file)
    print(f"\n--- Analyzing {file} ---")
    try:
        xl = pd.ExcelFile(file_path)
        print("Sheet names:", xl.sheet_names)
        for sheet in xl.sheet_names:
            # Read just the first few rows to get columns
            df = xl.parse(sheet, nrows=2)
            print(f"\nSheet: {sheet}")
            print("Columns:", df.columns.tolist())
            print(f"Number of columns: {len(df.columns)}")
    except Exception as e:
        print("Error:", e)
