#!/usr/bin/env python3
"""支线驳船冒烟：确认进程拉起后驳船列表读得出、载箱量可读。

只依赖标准库，直接用系统 python3 跑：
    python3 scripts/smoke_feeder.py --base http://127.0.0.1:8000
加 --fingerprint 把 (驳船编号, 载箱量) 指纹落盘，供两处环境比对载箱量是否一致。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request

REQUIRED_STATUS_GROUPS = {
    "待靠": {"到港待靠"},
    "在港": {"靠泊中", "作业中"},
    "已离港": {"已离港"},
}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="支线驳船冒烟检查")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--fingerprint", help="把载箱量指纹写到该文件")
    args = parser.parse_args()

    problems: list[str] = []
    try:
        health = fetch_json(f"{args.base}/api/health")
        if not health.get("ok"):
            problems.append("/api/health 返回 ok=false")
    except Exception as exc:  # noqa: BLE001 - 冒烟要把任何网络错误都报成人话
        print(f"[冒烟] 健康检查失败：{exc}")
        return 1

    try:
        page = fetch_json(f"{args.base}/api/feeder?page=1&size=200")
    except Exception as exc:  # noqa: BLE001
        print(f"[冒烟] 驳船列表读取失败：{exc}")
        return 1

    items = page.get("items") or []
    if not items:
        problems.append("驳船列表为空，底表可能没铺进去")

    statuses = {str(row.get("status", "")) for row in items}
    missing_groups = [label for label, group in REQUIRED_STATUS_GROUPS.items() if not statuses & group]
    if missing_groups:
        problems.append(f"列表状态未覆盖：{'、'.join(missing_groups)}")

    fingerprint_rows: list[list[str]] = []
    bad_capacity: list[str] = []
    for row in items:
        key = str(row.get("驳船编号", ""))
        capacity = str(row.get("载箱量", "")).strip()
        try:
            float(capacity)
        except ValueError:
            bad_capacity.append(key or "?")
        fingerprint_rows.append([key, capacity])
    if bad_capacity:
        problems.append(f"载箱量不可读：{'、'.join(bad_capacity)}")

    if problems:
        print("[冒烟] 未通过，缺失项：")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    fingerprint_rows.sort()
    digest = hashlib.sha256(json.dumps(fingerprint_rows, ensure_ascii=False).encode("utf-8")).hexdigest()
    print(f"[冒烟] 通过：{len(items)} 条驳船，状态覆盖 待靠/在港/已离港，载箱量全部可读")
    for key, capacity in fingerprint_rows:
        print(f"  {key}: 载箱量 {capacity} TEU")
    print(f"[冒烟] 载箱量指纹 sha256:{digest}")
    if args.fingerprint:
        payload = {"base": args.base, "rows": fingerprint_rows, "sha256": digest}
        with open(args.fingerprint, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"[冒烟] 指纹已写入 {args.fingerprint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
