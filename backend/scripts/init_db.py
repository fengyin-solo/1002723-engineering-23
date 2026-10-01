#!/usr/bin/env python3
"""建库脚本：在 FEEDER_DB_PATH 指向的 SQLite 文件里幂等创建驳船底表。

用法：python3 scripts/init_db.py
表已存在时不动任何数据，可重复执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402


def main() -> int:
    path = db.init_db()
    status = db.tables_status(path)
    missing = [name for name, exists in status.items() if not exists]
    if missing:
        print(f"[init_db] 失败，缺失底表：{', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"[init_db] OK  库文件：{path}")
    for name in db.REQUIRED_TABLES:
        print(f"[init_db]   - 底表 {name} 就绪")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
