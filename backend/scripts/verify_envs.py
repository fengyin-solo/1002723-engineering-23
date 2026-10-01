#!/usr/bin/env python3
"""上线前比对：同一份清单部署的两处环境，读到的驳船载箱量必须完全一致。

用法：
    python3 scripts/verify_envs.py --env-a http://10.0.0.1:8000 --env-b http://10.0.0.2:8000
    python3 scripts/verify_envs.py   # 不传参时默认本地两实例（8000 / 8001）做自检

任何一处冒烟不过，或同编号驳船的载箱量对不上，立即判失败并打印差异，退出码非 0。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke import run  # noqa: E402


def check_env(name: str, base_url: str) -> tuple[bool, dict]:
    ok, failures, summary = run(base_url)
    if not ok:
        print(f"[verify] {name}（{base_url}）冒烟未通过：", file=sys.stderr)
        for failure in failures:
            print(f"[verify]   - {failure}", file=sys.stderr)
    return ok, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="两处环境驳船载箱量一致性比对")
    parser.add_argument("--env-a", default="http://127.0.0.1:8000", help="环境 A（如预发）")
    parser.add_argument("--name-a", default="环境A/预发")
    parser.add_argument("--env-b", default="http://127.0.0.1:8001", help="环境 B（如生产）")
    parser.add_argument("--name-b", default="环境B/生产")
    args = parser.parse_args()

    ok_a, sum_a = check_env(args.name_a, args.env_a)
    ok_b, sum_b = check_env(args.name_b, args.env_b)
    if not (ok_a and ok_b):
        print("[verify] FAIL 有环境未通过冒烟，不进入载箱量比对", file=sys.stderr)
        return 1

    diffs: list[str] = []
    if sum_a.get("teu_total") != sum_b.get("teu_total"):
        diffs.append(f"载箱量合计不一致：{args.name_a}={sum_a.get('teu_total')} vs {args.name_b}={sum_b.get('teu_total')}")
    if sum_a.get("total") != sum_b.get("total"):
        diffs.append(f"驳船条数不一致：{args.name_a}={sum_a.get('total')} vs {args.name_b}={sum_b.get('total')}")
    codes_a = set(sum_a.get("per_barge", {}))
    codes_b = set(sum_b.get("per_barge", {}))
    for code_value in sorted(codes_a - codes_b):
        diffs.append(f"{code_value} 只在 {args.name_a} 存在")
    for code_value in sorted(codes_b - codes_a):
        diffs.append(f"{code_value} 只在 {args.name_b} 存在")
    for code_value in sorted(codes_a & codes_b):
        if sum_a["per_barge"][code_value] != sum_b["per_barge"][code_value]:
            diffs.append(
                f"{code_value} 载箱量不一致："
                f"{args.name_a}={sum_a['per_barge'][code_value]} vs {args.name_b}={sum_b['per_barge'][code_value]}"
            )

    if diffs:
        print("[verify] FAIL 两处环境数据不一致：", file=sys.stderr)
        for diff in diffs:
            print(f"[verify]   - {diff}", file=sys.stderr)
        return 1

    print("[verify] PASS 两处环境冒烟均通过，载箱量完全一致")
    print(f"[verify]   {args.name_a}（{args.env_a}）：{sum_a['total']} 条 / {sum_a['teu_total']} TEU")
    print(f"[verify]   {args.name_b}（{args.env_b}）：{sum_b['total']} 条 / {sum_b['teu_total']} TEU")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
