#!/usr/bin/env python3
"""驳船 / 靠泊码头底表导入：幂等，重复执行只认第一次，绝不叠出两份。

用法：
    python3 scripts/seed_import.py                 # 导入 data/fixtures 下两份底表
    python3 scripts/seed_import.py --check         # 只校验不写库（bootstrap 预检用）

幂等保证（双层）：
1. 文件级：seed_import_ledger 按文件内容 sha256 记账，同一份文件再导直接跳过；
2. 行级：即使文件被改名/改了一个无关字符，已存在的业务编号也不会重复插入，
   已存在行保持第一次导入的内容，本次只补入新编号。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = BACKEND_ROOT / "data" / "fixtures"

VALID_STATUSES = {"到港待靠", "靠泊中", "作业中", "已离港"}
EXPECTED_STATUSES = {"到港待靠", "靠泊中/作业中(在港)", "已离港"}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(row) for row in reader]
        return reader.fieldnames or [], rows


def validate_barges(rows: list[dict[str, str]], berth_codes: set[str]) -> list[str]:
    errors: list[str] = []
    seen_codes: set[str] = set()
    present_statuses: set[str] = set()
    for index, row in enumerate(rows, start=2):  # CSV 第 1 行是表头
        code = (row.get("驳船编号") or "").strip()
        if not code:
            errors.append(f"第 {index} 行：驳船编号为空")
        elif code in seen_codes:
            errors.append(f"第 {index} 行：驳船编号 {code} 在文件内重复")
        seen_codes.add(code)
        for field in ("驳船名称", "运营公司"):
            if not (row.get(field) or "").strip():
                errors.append(f"第 {index} 行（{code}）：{field}为空")
        try:
            teu = int((row.get("载箱量") or "").strip())
            if teu < 0:
                raise ValueError
        except ValueError:
            errors.append(f"第 {index} 行（{code}）：载箱量必须是不小于 0 的整数，实际为 {row.get('载箱量')!r}")
        status = (row.get("驳船状态") or "").strip()
        if status not in VALID_STATUSES:
            errors.append(f"第 {index} 行（{code}）：驳船状态非法 {status!r}，允许 {sorted(VALID_STATUSES)}")
        else:
            present_statuses.add(status)
        berth_code = (row.get("靠泊码头") or "").strip()
        if berth_code and berth_code not in berth_codes:
            errors.append(f"第 {index} 行（{code}）：靠泊码头 {berth_code} 不在码头底表中")
    if not rows:
        errors.append("驳船底表为空文件")
    covered = {
        ("到港待靠" if s == "到港待靠" else "靠泊中/作业中(在港)" if s in ("靠泊中", "作业中") else "已离港")
        for s in present_statuses
    }
    missing_groups = EXPECTED_STATUSES - covered
    for group in sorted(missing_groups):
        errors.append(f"驳船底表缺少状态分组：{group}（必须含待靠/在港/已离港三类）")
    return errors


def validate_berths(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=2):
        code = (row.get("码头编号") or "").strip()
        if not code:
            errors.append(f"第 {index} 行：码头编号为空")
        elif code in seen:
            errors.append(f"第 {index} 行：码头编号 {code} 在文件内重复")
        seen.add(code)
        if not (row.get("码头名称") or "").strip():
            errors.append(f"第 {index} 行（{code}）：码头名称为空")
        for field in ("泊位长度", "水深"):
            try:
                float((row.get(field) or "").strip())
            except ValueError:
                errors.append(f"第 {index} 行（{code}）：{field} 必须是数字，实际为 {row.get(field)!r}")
        if (row.get("码头状态") or "").strip() not in {"可用", "维护中", "停用"}:
            errors.append(f"第 {index} 行（{code}）：码头状态必须是 可用/维护中/停用")
    if not rows:
        errors.append("码头底表为空文件")
    return errors


def import_berths(path: Path, digest: str, check_only: bool) -> tuple[bool, int, int]:
    """返回 (整文件是否已导入过, 新增行数, 跳过行数)。"""
    _header, rows = read_csv(path)
    errors = validate_berths(rows)
    if errors:
        raise ValueError("码头底表校验未通过：\n  " + "\n  ".join(errors))
    if check_only:
        return False, len(rows), 0

    with db.db_cursor(commit=True) as cur:
        cur.execute(f"SELECT 1 FROM {db.LEDGER_TABLE} WHERE file_name = ? AND sha256 = ?", [path.name, digest])
        if cur.fetchone():
            return True, 0, len(rows)
        added = skipped = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            cur.execute(
                f"""INSERT INTO {db.BERTH_TABLE} (code, name, quay_length, depth, berth_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code) DO NOTHING""",
                [row["码头编号"].strip(), row["码头名称"].strip(),
                 float(row["泊位长度"]), float(row["水深"]), row["码头状态"].strip(), now],
            )
            if cur.rowcount:
                added += 1
            else:
                skipped += 1
        cur.execute(
            f"INSERT OR REPLACE INTO {db.LEDGER_TABLE} (file_name, sha256, rows_added, imported_at) VALUES (?, ?, ?, ?)",
            [path.name, digest, added, now],
        )
    return False, added, skipped


def import_barges(path: Path, digest: str, check_only: bool) -> tuple[bool, int, int]:
    _header, berth_rows = read_csv(FIXTURE_DIR / "feeder_berths.csv")
    berth_codes = {r["码头编号"].strip() for r in berth_rows}
    # 库里已有的码头也算数（首次先导码头后导驳船的场景）
    berth_codes |= {b["code"] for b in db.list_berths()}
    _header2, rows = read_csv(path)
    errors = validate_barges(rows, berth_codes)
    if errors:
        raise ValueError("驳船底表校验未通过：\n  " + "\n  ".join(errors))
    if check_only:
        return False, len(rows), 0

    with db.db_cursor(commit=True) as cur:
        cur.execute(f"SELECT 1 FROM {db.LEDGER_TABLE} WHERE file_name = ? AND sha256 = ?", [path.name, digest])
        if cur.fetchone():
            return True, 0, len(rows)
        added = skipped = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            status = row["驳船状态"].strip()
            cur.execute(
                f"""INSERT INTO {db.BARGE_TABLE}
                    (barge_code, barge_name, operator, teu_count,
                     arrival_time, departure_time, berth_code, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(barge_code) DO NOTHING""",
                [
                    row["驳船编号"].strip(),
                    row["驳船名称"].strip(),
                    row["运营公司"].strip(),
                    int(row["载箱量"]),
                    (row.get("到港时间") or "").strip() or None,
                    (row.get("离港时间") or "").strip() or None,
                    (row.get("靠泊码头") or "").strip() or None,
                    status,
                ],
            )
            if cur.rowcount:
                added += 1
            else:
                skipped += 1
        cur.execute(
            f"INSERT OR REPLACE INTO {db.LEDGER_TABLE} (file_name, sha256, rows_added, imported_at) VALUES (?, ?, ?, ?)",
            [path.name, digest, added, now],
        )
    return False, added, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="导入支线驳船底表（幂等）")
    parser.add_argument("--check", action="store_true", help="只校验 CSV，不写库")
    args = parser.parse_args()

    db.init_db()
    print(f"[seed] 数据库：{settings.db_path}")
    jobs = [
        (FIXTURE_DIR / "feeder_berths.csv", import_berths, "靠泊码头底表"),
        (FIXTURE_DIR / "feeder_barges.csv", import_barges, "驳船底表"),
    ]
    for csv_path, importer, label in jobs:
        if not csv_path.exists():
            print(f"[seed] 失败：找不到 {label} 文件 {csv_path}", file=sys.stderr)
            return 2
        digest = sha256_of(csv_path)
        try:
            already, added, skipped = importer(csv_path, digest, args.check)
        except ValueError as exc:
            print(f"[seed] {label}：{exc}", file=sys.stderr)
            return 3
        except sqlite3.Error as exc:
            print(f"[seed] {label}：写库失败：{exc}", file=sys.stderr)
            return 4
        if args.check:
            print(f"[seed] [校验] {label}：{added} 行格式正确，状态分组齐全")
        elif already:
            print(f"[seed] {label}：同一文件已导入过（sha256 {digest[:12]}…），整文件跳过，不重复导入")
        else:
            print(f"[seed] {label}：新增 {added} 行，已存在跳过 {skipped} 行")

    if not args.check:
        total = db.count_barges()
        print(f"[seed] OK  当前驳船底表共 {total} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
