#!/usr/bin/env python3
"""支线驳船冒烟：进程拉起来后跑一遍，确认驳船列表读得出来、载箱量不为空。

用法：
    python3 scripts/smoke.py [--base-url http://127.0.0.1:8000] [--json]

检查项（任何一项不过即判未就绪，退出码非 0，并逐项打印缺失/异常）：
  1. /api/health 200 且 ok=true（底表存在且非空）
  2. /api/feeder 列表可读，total>0，三类状态（待靠/在港/已离港）都在
  3. 每条驳船「载箱量」字段存在且是非负整数；同时给出载箱量合计（双环境比对用）
  4. /api/feeder/export 与 /api/feeder/berths 静态路由不被 /{id} 抢匹配
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

IN_PORT_STATUSES = {"靠泊中", "作业中"}
EXPECTED_GROUPS = {"待靠": "到港待靠", "在港": ("靠泊中", "作业中"), "已离港": "已离港"}


def fetch(base_url: str, path: str) -> tuple[int, Any]:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"detail": exc.reason}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"detail": f"连不上 {url}：{exc}"}


def run(base_url: str) -> tuple[bool, list[str], dict[str, Any]]:
    failures: list[str] = []
    summary: dict[str, Any] = {"base_url": base_url}

    # 1. 健康检查
    code, health = fetch(base_url, "/api/health")
    if code != 200 or not health.get("ok"):
        failures.append(f"健康检查未就绪（HTTP {code}）：{health.get('detail') or health}")
        return False, failures, summary
    summary["env"] = health.get("env")

    # 2. 驳船列表
    code, listing = fetch(base_url, "/api/feeder?page=1&size=200")
    if code != 200:
        failures.append(f"驳船列表读取失败（HTTP {code}）：{listing}")
        return False, failures, summary
    items = listing.get("items")
    total = listing.get("total")
    if not isinstance(items, list) or not items:
        failures.append("驳船列表为空：底表未导入或接口未返回 items")
        return False, failures, summary

    # 3. 每条载箱量可读
    teu_total = 0
    per_barge: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for item in items:
        code_value = item.get("驳船编号") or f"id={item.get('id')}"
        raw_teu = item.get("载箱量")
        if not isinstance(raw_teu, int) or raw_teu < 0:
            failures.append(f"{code_value} 的载箱量缺失或不是非负整数：{raw_teu!r}")
            continue
        teu_total += raw_teu
        per_barge[str(code_value)] = raw_teu
        status = item.get("驳船状态") or item.get("status")
        statuses[str(status)] = statuses.get(str(status), 0) + 1
    summary.update(total=total, teu_total=teu_total, per_barge=per_barge, statuses=statuses)

    present = set(statuses)
    group_checks = {
        "待靠": "到港待靠" in present,
        "在港": bool(present & IN_PORT_STATUSES),
        "已离港": "已离港" in present,
    }
    for group, ok in group_checks.items():
        if not ok:
            failures.append(f"驳船底表缺少状态分组「{group}」，当前状态分布：{statuses}")
    if total != len(items):
        failures.append(f"分页 total({total}) 与返回条数({len(items)})不一致")

    # 4. 静态路由不被 /{entry_id} 抢匹配（抢匹配时会 422）
    code, exported = fetch(base_url, "/api/feeder/export")
    if code != 200 or exported.get("total") != total:
        failures.append(f"/api/feeder/export 异常（HTTP {code}），疑似被 /{{entry_id}} 路由抢匹配")
    code, berths = fetch(base_url, "/api/feeder/berths")
    if code != 200 or not berths.get("items"):
        failures.append(f"/api/feeder/berths 异常（HTTP {code}）：码头底表读不出来")
    else:
        summary["berths"] = berths.get("total")

    return not failures, failures, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="支线驳船模块冒烟")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--json", action="store_true", help="只输出 JSON 结果（供比对脚本调用）")
    args = parser.parse_args()

    ok, failures, summary = run(args.base_url)
    if args.json:
        print(json.dumps({"ok": ok, "failures": failures, "summary": summary}, ensure_ascii=False, indent=2))
    elif ok:
        print("[smoke] PASS 支线驳船冒烟通过")
        print(f"[smoke]   环境：{summary.get('env')}  驳船 {summary['total']} 条")
        print(f"[smoke]   状态分布：{summary['statuses']}")
        print(f"[smoke]   载箱量合计：{summary['teu_total']} TEU")
        for code_value, teu in summary["per_barge"].items():
            print(f"[smoke]     {code_value}: {teu}")
    else:
        print("[smoke] FAIL 环境未就绪，缺失/异常项：", file=sys.stderr)
        for failure in failures:
            print(f"[smoke]   - {failure}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
