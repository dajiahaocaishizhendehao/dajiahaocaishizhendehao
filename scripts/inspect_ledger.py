"""只读检查用户台账结构：工作表、表头、样例行。"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

path = Path(sys.argv[1])
workbook = load_workbook(path, data_only=True)
print("工作表:", workbook.sheetnames)
for sheet in workbook.worksheets:
    print()
    print(f"== {sheet.title} 维度={sheet.dimensions} 行={sheet.max_row} 列={sheet.max_column}")
    merged = [str(rng) for rng in sheet.merged_cells.ranges]
    if merged:
        print("合并单元格:", ", ".join(merged[:10]))
    for index, row in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 8), values_only=True), start=1):
        cells = ["" if value is None else str(value) for value in row]
        print(f"  R{index}: " + " | ".join(cells))
