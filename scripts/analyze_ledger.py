"""分析台账数据分布，为模型与导入设计提供依据。"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

path = Path(sys.argv[1])
workbook = load_workbook(path, data_only=True)
sheet = workbook.active
rows = list(sheet.iter_rows(min_row=2, values_only=True))
rows = [row for row in rows if any(value is not None for value in row)]

print("数据行数:", len(rows))

docket = [str(row[0]).strip() for row in rows if row[0]]
appno = [str(row[1]).strip() for row in rows if row[1]]
names = [str(row[2]).strip() for row in rows if row[2]]
owners = Counter(str(row[3]).strip() for row in rows if row[3])
amounts = Counter(row[6] for row in rows)
due_dates = [row[4] for row in rows if row[4]]
paid_dates = [row[7] for row in rows if row[7]]
coverage = [row[5] for row in rows if row[5]]

print("我方文号:", len(docket), "唯一:", len(set(docket)))
print("申请号:", len(appno), "唯一:", len(set(appno)))
print("案件名称:", len(names), "唯一:", len(set(names)))
print("权利人分布:", dict(owners))
print("金额分布:", dict(amounts))
print("应缴日范围:", min(due_dates), "→", max(due_dates))
print("缴纳日范围:", min(paid_dates), "→", max(paid_dates))
print("缴至范围:", min(coverage), "→", max(coverage))

dup_appno = [no for no, count in Counter(appno).items() if count > 1]
dup_name = [nm for nm, count in Counter(names).items() if count > 1]
print("重复申请号:", dup_appno)
print("重复名称:", dup_name)

missing = [
    (index + 2, row)
    for index, row in enumerate(rows)
    if any(row[col] in (None, "") for col in (0, 1, 2, 3, 4, 5, 6, 7))
]
print("存在空值的行:", len(missing))
for row_number, row in missing[:5]:
    print("  R", row_number, row)
