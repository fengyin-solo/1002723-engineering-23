"""港口集装箱作业管理平台 后端服务入口。

启动：uvicorn app.main:app --host 127.0.0.1 --port 8000
健康检查：GET /api/health
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.importer import import_base_table
from app.routers import ROUTERS
from app.store import store

BASE_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "feeder_base.csv"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 启动先铺驳船底表：底表缺失或校验不过，进程直接起不来，不留半套环境
    inserted, skipped = import_base_table(store, BASE_TABLE_PATH)
    print(f"[startup] 驳船底表就绪：新增 {inserted} 条，跳过 {skipped} 条（重复导入只认第一次）")
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
def health() -> dict[str, object]:
    """健康检查：确认服务已经监听、示例数据已经就绪。"""
    return {"ok": True, "app": settings.app_name, "modules": len(store.module_names())}


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
