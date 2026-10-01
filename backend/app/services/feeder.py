"""支线驳船业务规则：状态流转、字段校验与筛选口径都收在这里。

数据落在 SQLite 底表（feeder_barge / feeder_berth），不再走内存仓库；
这样进程重启、两处环境读到的都是同一份底表。
"""
from __future__ import annotations

from typing import Any

from app import db

REQUIRED_FIELDS = ["驳船编号", "驳船名称", "运营公司", "载箱量"]
# 状态只能顺着序列往前，不允许跳步或倒退
STATUS_ORDER = ["到港待靠", "靠泊中", "作业中", "已离港"]
ACTION_RULES = {"安排靠泊": "靠泊中", "开始作业": "作业中", "确认离港": "已离港"}

# 中文列名 -> 表字段，供手工登记接口复用
_CN_TO_EN = {cn: eng for eng, cn in db.BARGE_COLUMNS}


def _today() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M")


class FeederService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        return db.list_barges(keyword=keyword, status=status, page=page, size=size)

    def list_berths(self) -> list[dict[str, Any]]:
        return db.list_berths()

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return db.get_barge(entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if str(values.get(field) or "").strip() == ""]
        if missing:
            return None, missing
        try:
            teu = int(values["载箱量"])
            if teu < 0:
                raise ValueError
        except (TypeError, ValueError):
            return None, ["载箱量必须是不小于 0 的整数"]
        code = str(values["驳船编号"]).strip()
        if db.get_barge_by_code(code):
            return None, [f"驳船编号 {code} 已存在，底表不允许重复编号"]
        berth_code = str(values.get("靠泊码头") or "").strip() or None
        if berth_code and not any(b["code"] == berth_code for b in db.list_berths()):
            return None, [f"靠泊码头 {berth_code} 不在码头底表中"]
        data = {
            "barge_code": code,
            "barge_name": str(values["驳船名称"]).strip(),
            "operator": str(values["运营公司"]).strip(),
            "teu_count": teu,
            "arrival_time": _today(),
            "departure_time": None,
            "berth_code": berth_code,
            "status": STATUS_ORDER[0],
        }
        return db.insert_barge(data), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = db.get_barge(entry_id)
        if entry is None:
            return None, f"驳船 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于支线驳船可执行范围"
        target = ACTION_RULES[action]
        current_idx = STATUS_ORDER.index(entry["驳船状态"]) if entry["驳船状态"] in STATUS_ORDER else -1
        target_idx = STATUS_ORDER.index(target)
        # 只允许顺着序列走相邻一步：待靠→靠泊→作业→离港，不许跳步、不许倒退
        if target_idx != current_idx + 1:
            return None, f"驳船当前为「{entry['驳船状态']}」，不能跳过中间环节直接「{action}」"
        departure_time = _today() if target == STATUS_ORDER[-1] else None
        db.update_barge_status(entry_id, target, departure_time)
        return db.get_barge(entry_id), f"驳船已{action}"
