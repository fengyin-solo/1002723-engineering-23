"""港口集装箱作业管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health —— 除服务存活外，还会探支线驳船底表是否已建好并已导入
"""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import settings
from app.routers import ROUTERS
from app.store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时只保证「表在」；底表数据由 scripts/bootstrap.sh 的导入步骤负责。
    # 没跑导入就起服务不会崩，但 /api/health 会如实返回 503，不留下半套环境的假象。
    db.init_db()
    yield


app = FastAPI(title="港口集装箱作业管理平台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health(response: Response) -> dict[str, object]:
    """健康检查：确认服务监听、示例模块就绪、驳船底表已建好且已导入底表。"""
    ready = True
    checks: dict[str, object] = {}
    table_status = db.tables_status()
    missing_tables = [name for name, exists in table_status.items() if not exists]
    checks["feeder_tables"] = {"missing": missing_tables}
    if missing_tables:
        ready = False

    barge_count = 0
    db_error = ""
    if missing_tables:
        db_error = "缺少底表：" + "、".join(missing_tables)
    else:
        try:
            barge_count = db.count_barges()
            if barge_count == 0:
                ready = False
                db_error = "驳船底表为空，请先执行 scripts/bootstrap.sh（第 3 步导入底表）"
        except sqlite3.Error as exc:  # 库文件损坏等，照实报出来
            ready = False
            db_error = f"驳船底表读取失败：{exc}"
    checks["feeder_barges"] = {"count": barge_count, "error": db_error}

    if not ready:
        response.status_code = 503
    body: dict[str, object] = {
        "ok": ready,
        "app": settings.app_name,
        "env": settings.env,
        "modules": len(store.module_names()),
        "checks": checks,
    }
    if not ready:
        body["detail"] = db_error
    return body
