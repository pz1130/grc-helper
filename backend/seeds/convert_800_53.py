"""NIST SP 800-53 Rev.5 官方 OSCAL/CSV → 框架导入模板。

用法：python seeds/convert_800_53.py <控制项文件> <baseline 文件> seeds/nist-800-53-r5.csv

层级：Family(1) → Control(2) → Enhancement(3)。
**AC-2 本身即一条真控制**，而 AC-2(1) 是它的子节点，所以「叶子即要求」
会错误地把 AC-2 排除。故凡是控制项（非 Family）一律显式标 is_requirement=true。
"""

import csv
import json
import re
import sys
from pathlib import Path

COLUMNS = ["code", "title", "description", "parent_code", "attributes_json"]
ENHANCEMENT = re.compile(r"^([A-Z]{2}-\d+)(?:\(\d+\)|\.\d+)$")


def parent_of(code: str) -> str:
    match = ENHANCEMENT.match(code)
    if match:
        return match.group(1)
    if "-" in code:
        return code.split("-", 1)[0]
    return ""


def convert(controls: Path, baselines: Path, target: Path) -> int:
    entries = json.loads(controls.read_text(encoding="utf-8"))
    membership = json.loads(baselines.read_text(encoding="utf-8"))

    families: dict[str, str] = {}
    rows = []
    for entry in entries:
        code = entry["id"].strip().upper()
        family = code.split("-", 1)[0]
        families.setdefault(family, entry.get("family", family))
        rows.append([
            code,
            entry.get("title", "").strip() or code,
            entry.get("statement", "").strip(),
            parent_of(code),
            json.dumps(
                {
                    "baselines": sorted(membership.get(code, [])),
                    "is_requirement": True,
                },
                ensure_ascii=False,
            ),
        ])

    family_rows = [
        [family, name, "", "", ""] for family, name in sorted(families.items())
    ]
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(family_rows + rows)
    return len(family_rows) + len(rows)


if __name__ == "__main__":
    count = convert(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(f"wrote {count} rows to {sys.argv[3]}")
