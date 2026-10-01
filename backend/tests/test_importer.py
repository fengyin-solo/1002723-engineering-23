"""驳船底表导入的回归用例：校验拦截、状态覆盖、重复导入不叠加。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.importer import BaseTableError, import_base_table, load_base_table
from app.store import Store

BASE_TABLE = Path(__file__).resolve().parent.parent / "data" / "feeder_base.csv"
HEADER = "驳船编号,驳船名称,运营公司,载箱量,到港时间,离港时间,靠泊码头,驳船状态\n"


def write_csv(body: str) -> str:
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
    with fh:
        fh.write(body)
    return fh.name


class LoadBaseTableTest(unittest.TestCase):
    def test_repo_base_table_is_valid(self) -> None:
        rows = load_base_table(BASE_TABLE)
        self.assertGreaterEqual(len(rows), 3)

    def test_missing_columns_are_reported(self) -> None:
        path = write_csv("驳船编号,驳船名称\nFEED-X,测试驳船\n")
        with self.assertRaises(BaseTableError) as ctx:
            load_base_table(path)
        self.assertIn("载箱量", str(ctx.exception))

    def test_status_coverage_is_required(self) -> None:
        path = write_csv(HEADER + "FEED-X,测试驳船,测试公司,100,2026-09-01,,1号泊位,到港待靠\n")
        with self.assertRaises(BaseTableError) as ctx:
            load_base_table(path)
        message = str(ctx.exception)
        self.assertIn("在港", message)
        self.assertIn("已离港", message)

    def test_non_numeric_capacity_is_reported(self) -> None:
        path = write_csv(
            HEADER
            + "FEED-X,测试驳船,测试公司,占位文本,2026-09-01,,1号泊位,到港待靠\n"
            + "FEED-Y,测试驳船,测试公司,100,2026-09-01,,1号泊位,靠泊中\n"
            + "FEED-Z,测试驳船,测试公司,100,2026-09-01,2026-09-02,1号泊位,已离港\n"
        )
        with self.assertRaises(BaseTableError) as ctx:
            load_base_table(path)
        self.assertIn("FEED-X", str(ctx.exception))


class ImportBaseTableTest(unittest.TestCase):
    def test_import_covers_three_status_groups(self) -> None:
        store = Store()
        inserted, skipped = import_base_table(store, BASE_TABLE)
        statuses = {row["status"] for row in store.rows("feeder")}
        self.assertIn("到港待靠", statuses)
        self.assertTrue({"靠泊中", "作业中"} & statuses)
        self.assertIn("已离港", statuses)
        self.assertEqual(skipped, 0)

    def test_reimport_never_duplicates(self) -> None:
        store = Store()
        first, _ = import_base_table(store, BASE_TABLE)
        second, skipped = import_base_table(store, BASE_TABLE)
        self.assertEqual(second, 0)
        self.assertEqual(skipped, first)
        self.assertEqual(len(store.rows("feeder")), first)


if __name__ == "__main__":
    unittest.main()
