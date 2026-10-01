"""支线驳船底表访问层：驳船（feeder_barge）与靠泊码头（feeder_berth）。

只依赖标准库 sqlite3，不引入 ORM：底表两张、字段固定，直连最省心，
也不会因为三方驱动版本对不齐而起不来。

- 表结构由 SCHEMA_SQL 统一定义，init_db() 幂等建表（IF NOT EXISTS）；
- 导入底表走 scripts/seed_import.py，按业务编号去重，重复导入只认第一次；
- 应用启动时只保证「表在」，不灌数据；没导入底表就启动，健康检查会报缺表/空表。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import settings

BARGE_TABLE = "feeder_barge"
BERTH_TABLE = "feeder_berth"
LEDGER_TABLE = "seed_import_ledger"
REQUIRED_TABLES = (BARGE_TABLE, BERTH_TABLE)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feeder_berth (
    code        TEXT PRIMARY KEY,          -- 码头/泊位编号，如 BT-01
    name        TEXT NOT NULL,             -- 码头名称
    quay_length REAL,                      -- 泊位长度（米）
    depth       REAL,                      -- 前沿水深（米）
    berth_status TEXT NOT NULL,            -- 可用 / 维护中 / 停用
    created_at  TEXT NOT NULL              -- 导入时间，由写入方填
);

CREATE TABLE IF NOT EXISTS feeder_barge (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    barge_code    TEXT NOT NULL UNIQUE,    -- 驳船编号，业务唯一键
    barge_name    TEXT NOT NULL,           -- 驳船名称
    operator      TEXT NOT NULL,           -- 运营公司
    teu_count     INTEGER NOT NULL,        -- 载箱量（TEU）
    arrival_time  TEXT,                    -- 到港时间
    departure_time TEXT,                   -- 离港时间
    berth_code    TEXT REFERENCES feeder_berth(code),  -- 靠泊码头
    status        TEXT NOT NULL            -- 到港待靠 / 靠泊中 / 作业中 / 已离港
);
CREATE INDEX IF NOT EXISTS idx_feeder_barge_status ON feeder_barge(status);

-- 底表导入台账：同一份文件重复导入只认第一次（按内容哈希判重）
CREATE TABLE IF NOT EXISTS seed_import_ledger (
    file_name  TEXT PRIMARY KEY,
    sha256     TEXT NOT NULL,
    rows_added INTEGER NOT NULL,
    imported_at TEXT NOT NULL              -- 导入时间，由写入方填
);
"""

# 库里是规范英文字段，对外（前端/CSV/冒烟）统一用中文列名
BARGE_COLUMNS: list[tuple[str, str]] = [
    ("barge_code", "驳船编号"),
    ("barge_name", "驳船名称"),
    ("operator", "运营公司"),
    ("teu_count", "载箱量"),
    ("arrival_time", "到港时间"),
    ("departure_time", "离港时间"),
    ("berth_code", "靠泊码头"),
    ("status", "驳船状态"),
]

BERTH_COLUMNS: list[tuple[str, str]] = [
    ("code", "码头编号"),
    ("name", "码头名称"),
    ("quay_length", "泊位长度"),
    ("depth", "水深"),
    ("berth_status", "码头状态"),
]


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """打开一个连接。调用方负责关闭（或用 db_cursor 上下文）。"""
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor(db_path: Path | None = None, *, commit: bool = False) -> Iterator[sqlite3.Cursor]:
    conn = connect(db_path)
    try:
        yield conn.cursor()
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> Path:
    """幂等建表：表已存在不动，不存在才创建。返回库文件路径。"""
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    return path


def existing_tables(db_path: Path | None = None) -> set[str]:
    with db_cursor(db_path) as cur:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cur.fetchall()}


def tables_status(db_path: Path | None = None) -> dict[str, bool]:
    """每张底表是否存在；健康检查与冒烟共用这一份口径。"""
    tables = existing_tables(db_path)
    return {name: name in tables for name in REQUIRED_TABLES}


def to_barge_row(record: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """英文字段记录 -> 前端使用的中文列名行（id 保留给动作接口）。"""
    data = dict(record)
    row: dict[str, Any] = {"id": data["id"], "status": data["status"]}
    for eng, cn in BARGE_COLUMNS:
        row[cn] = data[eng]
    return row


def list_barges(
    *,
    keyword: str | None = None,
    status: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = []
    params: list[Any] = []
    if keyword:
        where.append("(barge_code LIKE ? OR barge_name LIKE ? OR operator LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    if status:
        where.append("status = ?")
        params.append(status)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    with db_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM {BARGE_TABLE}{where_sql}", params)
        total = int(cur.fetchone()["c"])
        offset = max(page - 1, 0) * size
        cur.execute(
            f"SELECT * FROM {BARGE_TABLE}{where_sql} ORDER BY id LIMIT ? OFFSET ?",
            [*params, size, offset],
        )
        items = [to_barge_row(row) for row in cur.fetchall()]
    return items, total


def all_barges() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM {BARGE_TABLE} ORDER BY id")
        return [to_barge_row(row) for row in cur.fetchall()]


def get_barge(entry_id: int) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM {BARGE_TABLE} WHERE id = ?", [entry_id])
        record = cur.fetchone()
        return to_barge_row(record) if record else None


def get_barge_by_code(code: str) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM {BARGE_TABLE} WHERE barge_code = ?", [code])
        record = cur.fetchone()
        return to_barge_row(record) if record else None


def insert_barge(data: dict[str, Any]) -> dict[str, Any]:
    """新增一条驳船；编号重复时抛 sqlite3.IntegrityError，由上层转成可读提示。"""
    cols = [eng for eng, _ in BARGE_COLUMNS]
    placeholders = ", ".join("?" for _ in cols)
    values = [data.get(eng) for eng in cols]
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO {BARGE_TABLE} ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )
        entry_id = int(cur.lastrowid)
    return get_barge(entry_id)  # type: ignore[return-value]


def update_barge_status(entry_id: int, status: str, departure_time: str | None = None) -> None:
    with db_cursor(commit=True) as cur:
        if departure_time is not None:
            cur.execute(
                f"UPDATE {BARGE_TABLE} SET status = ?, departure_time = ? WHERE id = ?",
                [status, departure_time, entry_id],
            )
        else:
            cur.execute(f"UPDATE {BARGE_TABLE} SET status = ? WHERE id = ?", [status, entry_id])


def list_berths() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM {BERTH_TABLE} ORDER BY code")
        return [dict(row) for row in cur.fetchall()]


def count_barges() -> int:
    with db_cursor() as cur:
        cur.execute(f"SELECT COUNT(*) AS c FROM {BARGE_TABLE}")
        return int(cur.fetchone()["c"])
