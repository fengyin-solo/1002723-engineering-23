#!/usr/bin/env bash
# 支线驳船模块搭建清单：五步走完才算就绪。
# 哪一步缺东西就停在哪一步、打印缺失项，绝不留下半套环境。
# 用法：scripts/setup.sh            全流程（依赖 → 底表 → 起进程 → 冒烟）
#       scripts/setup.sh --deps-only  只备齐三方组件
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
BASE_TABLE="$BACKEND/data/feeder_base.csv"
LOCK_FILE="$BACKEND/requirements.lock"
HOST="${SETUP_HOST:-127.0.0.1}"
PORT="${SETUP_PORT:-8000}"
BASE_URL="http://$HOST:$PORT"
DEPS_ONLY=0
[ "${1:-}" = "--deps-only" ] && DEPS_ONLY=1

step() { printf '\n== [%s] %s ==\n' "$1" "$2"; }
fail() { printf '✗ 第%s步未备齐，停在原地。\n缺失项：%s\n' "$1" "$2" >&2; exit 1; }

step "1/5" "检查本机工具链"
missing=""
command -v python3 >/dev/null 2>&1 || missing="$missing python3"
command -v node >/dev/null 2>&1 || missing="$missing node"
command -v npm >/dev/null 2>&1 || missing="$missing npm"
[ -n "$missing" ] && fail "1/5" "未安装：$missing"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail "1/5" "python3 版本 $(python3 --version 2>&1) 低于 3.10"
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ] \
  || fail "1/5" "node 版本 $(node --version) 低于 18"
echo "工具链就绪：$(python3 --version) / node $(node --version) / npm $(npm --version)"

step "2/5" "备齐三方组件（后端 venv + 前端 node_modules）"
# 别的机器上建的 venv 在本机跑不起来（pyvenv.cfg 里是他机的 Python 路径），验活不过就重建
if [ -d "$BACKEND/.venv" ] && ! "$BACKEND/.venv/bin/python" -c '' 2>/dev/null; then
  echo "现有 .venv 在本机不可执行（多为跨机器拷贝或 Python 版本不齐），重建"
  rm -rf "$BACKEND/.venv"
fi
if [ ! -x "$BACKEND/.venv/bin/python" ]; then
  if ! python3 -m venv "$BACKEND/.venv" 2>/dev/null; then
    # 系统缺 ensurepip（如 Debian 未装 python3-venv）时的兜底：无 pip 建环境再引导 pip
    rm -rf "$BACKEND/.venv"
    python3 -m venv --without-pip "$BACKEND/.venv"
    echo "ensurepip 缺失，改用 get-pip.py 引导 pip"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py \
      || fail "2/5" "无法下载 get-pip.py，请检查网络或手动安装 python3-venv"
    "$BACKEND/.venv/bin/python" /tmp/get-pip.py -q
  fi
fi
[ -f "$LOCK_FILE" ] || fail "2/5" "缺少版本锁定文件 backend/requirements.lock"
"$BACKEND/.venv/bin/pip" install -q -r "$LOCK_FILE" \
  || fail "2/5" "pip 按 requirements.lock 安装失败，检查网络或锁文件"
"$BACKEND/.venv/bin/python" -c 'import fastapi, uvicorn, pydantic' \
  || fail "2/5" "fastapi/uvicorn/pydantic 未装齐"
if [ ! -x "$FRONTEND/node_modules/.bin/vite" ]; then
  (cd "$FRONTEND" && npm ci --no-audit --no-fund) \
    || fail "2/5" "npm ci 失败，检查 package-lock.json 是否与 package.json 同步"
fi
echo "三方组件就绪：后端按 requirements.lock 对齐，前端按 package-lock.json 对齐"
[ "$DEPS_ONLY" = 1 ] && { echo "仅备依赖，到此为止。"; exit 0; }

step "3/5" "校验驳船底表并验证幂等导入"
[ -f "$BASE_TABLE" ] || fail "3/5" "缺少底表文件 backend/data/feeder_base.csv"
(cd "$BACKEND" && .venv/bin/python -m app.importer check data/feeder_base.csv) \
  || fail "3/5" "底表校验未通过（缺失项见上方输出）"
(cd "$BACKEND" && .venv/bin/python -m app.importer dryrun data/feeder_base.csv) \
  || fail "3/5" "底表重复导入会叠数据，幂等校验未通过"

step "4/5" "拉起后端进程"
if curl -fsS --max-time 2 "$BASE_URL/api/health" >/dev/null 2>&1; then
  echo "后端已在 $BASE_URL 运行，复用现有进程"
else
  (cd "$BACKEND" && nohup .venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" \
    > /tmp/feeder-backend.log 2>&1 & echo $! > /tmp/feeder-backend.pid)
  ready=0
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 "$BASE_URL/api/health" >/dev/null 2>&1 && { ready=1; break; }
    sleep 1
  done
  [ "$ready" = 1 ] || fail "4/5" "后端 30s 内未就绪，日志见 /tmp/feeder-backend.log"
  echo "后端已就绪：$BASE_URL（pid 见 /tmp/feeder-backend.pid，日志见 /tmp/feeder-backend.log）"
fi

step "5/5" "冒烟：驳船列表读得出、载箱量可读"
python3 "$ROOT/scripts/smoke_feeder.py" --base "$BASE_URL" --fingerprint "$ROOT/.feeder-fingerprint.json" \
  || fail "5/5" "冒烟未通过（缺失项见上方输出）"
printf '\n✓ 全部就绪：驳船列表可读，载箱量指纹已写入 .feeder-fingerprint.json\n'
