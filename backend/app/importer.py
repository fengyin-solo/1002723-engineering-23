"""驳船底表导入：从 CSV 把驳船与靠泊码头底表铺进数据仓库。

底表是交接时最容易缺的一环。这里把校验、去重、导入收在一个模块里：
- 校验不过就抛 BaseTableError，消息里列清缺失项，绝不导入半份；
- 按驳船编号去重，同一份底表重复导入只认第一次，不会叠出第二条。

命令行：
    python -m app.importer check data/feeder_base.csv    # 只校验底表
    python -m app.importer dryrun data/feeder_base.csv   # 在临时仓库连导两次，验证幂等
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

MODULE = "feeder"
KEY_FIELD = "驳船编号"
CAPACITY_FIELD = "载箱量"
STATUS_FIELD = "驳船状态"

COLUMNS = ["驳船编号", "驳船名称", "运营公司", "载箱量", "到港时间", "离港时间", "靠泊码头", "驳船状态"]
# 底表必须覆盖的三类状态：待靠、在港（靠泊/作业）、已离港
REQUIRED_STATUS_GROUPS = {
    "待靠": {"到港待靠"},
    "在港": {"靠泊中", "作业中"},
    "已离港": {"已离港"},
}
TERMINAL_STATUS = "已离港"


class BaseTableError(RuntimeError):
    """底表缺列、缺状态覆盖或载箱量不可读时抛出，消息里列清缺失项。"""


def load_base_table(path: str | Path) -> list[dict[str, Any]]:
    """读取并校验底表；任何一项不齐都抛 BaseTableError，绝不导入半份。"""
    path = Path(path)
    if not path.exists():
        raise BaseTableError(f"底表文件不存在：{path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = [dict(row) for row in reader]

    problems: list[str] = []
    missing_columns = [column for column in COLUMNS if column not in header]
    if missing_columns:
        problems.append(f"缺少列：{'、'.join(missing_columns)}")
    if not rows:
        problems.append("底表没有任何数据行")
    if problems:
        raise BaseTableError("；".join(problems))

    statuses = {str(row.get(STATUS_FIELD, "")).strip() for row in rows}
    missing_groups = [label for label, group in REQUIRED_STATUS_GROUPS.items() if not statuses & group]
    if missing_groups:
        problems.append(f"状态未覆盖：{'、'.join(missing_groups)}")

    seen: set[str] = set()
    duplicated: list[str] = []
    bad_capacity: list[str] = []
    blank_keys = 0
    for row in rows:
        key = str(row.get(KEY_FIELD) or "").strip()
        if not key:
            blank_keys += 1
            continue
        if key in seen:
            duplicated.append(key)
        seen.add(key)
        try:
            float(str(row.get(CAPACITY_FIELD) or "").strip())
        except ValueError:
            bad_capacity.append(key)
    if blank_keys:
        problems.append(f"{blank_keys} 行缺少{KEY_FIELD}")
    if duplicated:
        problems.append(f"底表内部{KEY_FIELD}重复：{'、'.join(sorted(set(duplicated)))}")
    if bad_capacity:
        problems.append(f"{CAPACITY_FIELD}不是数字：{'、'.join(bad_capacity)}")
    if problems:
        raise BaseTableError("；".join(problems))
    return rows


def import_base_table(store: Any, path: str | Path, *, module: str = MODULE) -> tuple[int, int]:
    """把底表铺进仓库，按驳船编号去重；返回 (新增条数, 跳过条数)。"""
    rows = load_base_table(path)
    table = store.rows(module)
    existing = {str(row.get(KEY_FIELD, "")).strip() for row in table}
    inserted = 0
    for row in rows:
        key = str(row[KEY_FIELD]).strip()
        if key in existing:
            continue
        entry: dict[str, Any] = {"id": max((int(item.get("id", 0)) for item in table), default=0) + 1}
        entry.update({column: str(row.get(column, "")).strip() for column in COLUMNS})
        entry["status"] = entry[STATUS_FIELD]
        entry["pending"] = entry["status"] != TERMINAL_STATUS
        entry["abnormal"] = False
        table.append(entry)
        existing.add(key)
        inserted += 1
    return inserted, len(rows) - inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="驳船底表校验与幂等导入")
    parser.add_argument("command", choices=["check", "dryrun"])
    parser.add_argument("csv", type=Path, help="底表 CSV 路径")
    args = parser.parse_args(argv)

    try:
        rows = load_base_table(args.csv)
    except BaseTableError as exc:
        print(f"[底表校验] 未通过，缺失项：{exc}")
        return 1
    print(f"[底表校验] 通过：{len(rows)} 行，状态覆盖 待靠/在港/已离港，载箱量全部可读")

    if args.command == "dryrun":
        from app.store import Store

        store = Store()
        first = import_base_table(store, args.csv)
        second = import_base_table(store, args.csv)
        print(f"[幂等校验] 第一次导入 新增{first[0]} 跳过{first[1]}；第二次导入 新增{second[0]} 跳过{second[1]}")
        if second[0] != 0:
            print("[幂等校验] 未通过：重复导入叠出了新记录")
            return 1
        print("[幂等校验] 通过：同一份底表重复导入只认第一次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
