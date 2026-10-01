"""支线驳船接口：维护驳船，覆盖安排靠泊、开始作业、确认离港等动作。

注意静态路径（/export、/berths）必须注册在 /{entry_id} 前面，
否则请求会被整型路径参数抢先匹配成 422。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.feeder import FeederService

router = APIRouter(prefix="/api/feeder", tags=["支线驳船"])

service = FeederService()

LIST_FIELDS = ["驳船编号", "驳船名称", "运营公司", "载箱量", "到港时间", "离港时间", "靠泊码头", "驳船状态"]
STATUSES = ["到港待靠", "靠泊中", "作业中", "已离港"]


def _parse_filters(
    keyword: str | None,
    barge_code: str | None,
    barge_name: str | None,
    operator: str | None,
) -> str | None:
    """前端筛选条按列名提交；显式列名优先，兼容旧的 keyword。"""
    for value in (barge_code, barge_name, operator, keyword):
        if value and value.strip():
            return value.strip()
    return None


@router.get("/berths")
def list_berths() -> dict[str, Any]:
    """靠泊码头底表：给驳船安排靠泊时选码头用。"""
    items = service.list_berths()
    return {"items": items, "total": len(items)}


@router.get("/export")
def export_entries(
    status: str | None = Query(default=None, description="到港待靠、靠泊中、作业中、已离港"),
) -> dict[str, Any]:
    """导出支线驳船清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(status=status, page=1, size=10000)
    return {"module": "feeder", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="驳船编号/名称/运营公司模糊检索（兼容旧参数）"),
    驳船编号: str | None = Query(default=None),
    驳船名称: str | None = Query(default=None),
    运营公司: str | None = Query(default=None),
    status: str | None = Query(default=None, description="到港待靠、靠泊中、作业中、已离港"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按驳船编号与状态过滤支线驳船列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态仅支持：{'、'.join(STATUSES)}")
    kw = _parse_filters(keyword, 驳船编号, 驳船名称, 运营公司)
    items, total = service.list_entries(keyword=kw, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条驳船明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"驳船 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条驳船，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段或字段不合法：{'、'.join(missing)}")
    return ActionResult(ok=True, message="驳船已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条驳船执行安排靠泊、开始作业、确认离港；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
