#!/usr/bin/env bash
# 上线前两处环境核对：同一份清单各跑一遍，两处读到的载箱量必须一致。
# 用法：scripts/compare_env.sh <环境A地址> <环境B地址>
# 例：scripts/compare_env.sh http://127.0.0.1:8000 http://127.0.0.1:8001
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ $# -eq 2 ] || { echo "用法：$0 <环境A地址> <环境B地址>" >&2; exit 2; }

dir="$(mktemp -d)"
trap 'rm -rf "$dir"' EXIT

echo "== 环境A：$1 =="
python3 "$ROOT/scripts/smoke_feeder.py" --base "$1" --fingerprint "$dir/a.json"
echo "== 环境B：$2 =="
python3 "$ROOT/scripts/smoke_feeder.py" --base "$2" --fingerprint "$dir/b.json"

if python3 - "$dir/a.json" "$dir/b.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    a = json.load(fh)
with open(sys.argv[2], encoding="utf-8") as fh:
    b = json.load(fh)

if a["rows"] == b["rows"]:
    print(f"[比对] 一致：两处环境载箱量指纹相同 sha256:{a['sha256']}")
    sys.exit(0)

print("[比对] 不一致，差异行：")
only_a = {tuple(row) for row in a["rows"]} - {tuple(row) for row in b["rows"]}
only_b = {tuple(row) for row in b["rows"]} - {tuple(row) for row in a["rows"]}
for key, capacity in sorted(only_a):
    print(f"  仅 {a['base']} 读到：{key} 载箱量 {capacity}")
for key, capacity in sorted(only_b):
    print(f"  仅 {b['base']} 读到：{key} 载箱量 {capacity}")
sys.exit(1)
PY
then
  echo "[比对] 两处环境载箱量一致，可以上线"
else
  echo "[比对] 两处环境载箱量不一致，先排障再上线（记录归档到 docs/troubleshooting.md）" >&2
  exit 1
fi
