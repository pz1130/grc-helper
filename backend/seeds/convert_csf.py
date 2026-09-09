"""NIST CSF 2.0 官方 CSV/JSON → 框架导入模板。

用法：python seeds/convert_csf.py <官方文件> seeds/nist-csf-2.0.csv

CSF 层级：Function(1) → Category(2) → Subcategory(3)。
只有 Subcategory 是真要求，交由「叶子即要求」的默认规则处理，
因此本脚本不写 is_requirement。
"""

import csv
import json
import sys
from pathlib import Path

COLUMNS = ["code", "title", "description", "parent_code", "attributes_json"]


def parent_of(code: str) -> str:
    """PR.AA-01 → PR.AA；PR.AA → PR；PR → 空。"""
    if "-" in code:
        return code.rsplit("-", 1)[0]
    if "." in code:
        return code.rsplit(".", 1)[0]
    return ""


def convert(source: Path, target: Path) -> int:
    raw = json.loads(source.read_text(encoding="utf-8"))
    rows = []
    for entry in raw:
        code = entry["element_identifier"].strip()
        rows.append([
            code,
            entry.get("title", "").strip() or code,
            entry.get("text", "").strip(),
            parent_of(code),
            "",
        ])
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    count = convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"wrote {count} rows to {sys.argv[2]}")
