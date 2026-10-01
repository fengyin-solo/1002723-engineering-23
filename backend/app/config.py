"""运行配置：端口、跨域、运行环境与支线驳船底表的 SQLite 位置。

配置只认环境变量，默认值保证克隆下来就能在本机起；
数据库路径默认放在 backend/data/feeder.sqlite3，可用 FEEDER_DB_PATH 覆盖
（本地 / 预发 / 生产各自指向自己的库文件）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _default_db_path() -> Path:
    override = os.environ.get("FEEDER_DB_PATH", "").strip()
    return Path(override) if override else _BACKEND_ROOT / "data" / "feeder.sqlite3"


@dataclass(frozen=True)
class Settings:
    app_name: str = "港口集装箱作业管理平台"
    env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "local"))
    port: int = field(default_factory=lambda: int(os.environ.get("BACKEND_PORT", "8000")))
    db_path: Path = field(default_factory=_default_db_path)
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    page_size_default: int = 20
    page_size_max: int = 200


settings = Settings()
