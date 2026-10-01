#!/usr/bin/env bash
# 支线驳船模块 · 一次性搭建清单（可复用：本地 / 预发 / 生产同一份）。
#
# 逐步执行，任何一步没备齐就停在那一步并打印全部缺失项，绝不留下半套环境：
#   1. 三方组件：Python/Node 版本 + 后端 .venv 锁定依赖 + 前端 npm ci
#   2. 库表：SQLite 建驳船 / 靠泊码头底表
#   3. 底表数据：幂等导入（同一份重复导入只认第一次）
#   4. 起后端：冒烟确认驳船列表读得出载箱量
#   5. 前端构建：三方组件版本齐不齐、页面能不能编译
#
# 用法：scripts/bootstrap.sh
set -uo pipefail
RUN_KIND=bootstrap
# shellcheck source=_lib.sh
source "$(dirname "$0")/_lib.sh"

echo "$(c_bold '支线驳船模块 · 环境搭建清单')"
echo "仓库根目录：$REPO_ROOT"
echo "日志归档：$LOG_FILE"

# ---------------------------------------------------------------- 第 1 步
step 1 "核对三方组件版本并安装锁定依赖"
missing=()

PYTHON_BIN=""
for cand in python3.11 python3.12 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    major_minor="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)"
    case "$major_minor" in
      3.1[0-9]|3.[2-9][0-9]) PYTHON_BIN="$cand"; break ;;
    esac
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  missing+=("未找到 Python 3.10+（当前只有：$(command -v python3 >/dev/null && python3 --version || echo 无 python3)）；Ubuntu 需 sudo apt install python3.11 python3.11-venv")
else
  ok "Python：$($PYTHON_BIN --version 2>&1)"
fi

if command -v node >/dev/null 2>&1; then
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  if [ "$node_major" -ge 18 ]; then ok "Node：$(node --version) / npm $(npm --version)"; else
    missing+=("Node 版本过低（$(node --version)），需要 Node 18+"); fi
else
  missing+=("未找到 Node.js 18+ / npm")
fi

[ ${#missing[@]} -eq 0 ] || fail_step "三方组件-运行时" "${missing[@]}"

# 后端虚拟环境：版本不对/venv 损坏（如用 3.12 建、机器只有 3.11）一律重建
need_venv=0
if [ ! -x "$VENV_PY" ]; then
  need_venv=1
elif ! "$VENV_PY" -c 'import fastapi, uvicorn, pydantic' >/dev/null 2>&1; then
  need_venv=1
fi
if [ "$need_venv" -eq 1 ]; then
  warn "后端 .venv 缺失或已损坏，用 $PYTHON_BIN 重建"
  rm -rf "$BACKEND_DIR/.venv"
  if ! "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv" >/dev/null 2>&1; then
    # Debian/Ubuntu 常缺 python3-venv 且没有 sudo：走 get-pip 兜底
    warn "venv 模块不可用，改用 --without-pip + get-pip.py 引导"
    "$PYTHON_BIN" -m venv --without-pip "$BACKEND_DIR/.venv" || fail_step "三方组件-后端" "创建 venv 失败（需 sudo apt install python3.11-venv）"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.$$ || fail_step "三方组件-后端" "下载 get-pip.py 失败（检查外网）"
    "$VENV_PY" /tmp/get-pip.$$ || fail_step "三方组件-后端" "get-pip.py 引导失败"
    rm -f /tmp/get-pip.$$
  fi
fi
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt" || fail_step "三方组件-后端" "pip install 失败（requirements.txt 锁定版本见日志）"
ok "后端依赖已按 requirements.txt 精确锁定版本安装"

# 前端：有 package-lock 用 npm ci，保证两人两机装出同一棵 node_modules
cd "$FRONTEND_DIR"
if [ -f package-lock.json ]; then
  npm ci --no-audit --no-fund >/dev/null || fail_step "三方组件-前端" "npm ci 失败（删除 node_modules 后重试，或核对 package-lock.json）"
  ok "前端依赖已按 package-lock.json 精确安装（npm ci）"
else
  npm install --no-audit --no-fund >/dev/null || fail_step "三方组件-前端" "npm install 失败"
  warn "没有 package-lock.json，已在本机生成，请提交进仓库以锁定版本"
fi
cd "$REPO_ROOT"

# ---------------------------------------------------------------- 第 2 步
step 2 "创建驳船与靠泊码头底表（SQLite）"
"$VENV_PY" "$BACKEND_DIR/scripts/init_db.py" || fail_step "库表" "建表失败（见上方报错；可删 data/feeder.sqlite3 后重试）"

# ---------------------------------------------------------------- 第 3 步
step 3 "导入驳船 / 靠泊码头底表（幂等，重复导入只认第一次）"
"$VENV_PY" "$BACKEND_DIR/scripts/seed_import.py" || fail_step "底表数据" "底表导入失败（缺失项见上方；CSV 不合法不会写库）"
# 立刻证明幂等：再导一次，行数不得变化
rows_before="$("$VENV_PY" -c 'import sys; sys.path.insert(0,"'"$BACKEND_DIR"'"); from app import db; print(db.count_barges())')"
"$VENV_PY" "$BACKEND_DIR/scripts/seed_import.py" >/dev/null
rows_after="$("$VENV_PY" -c 'import sys; sys.path.insert(0,"'"$BACKEND_DIR"'"); from app import db; print(db.count_barges())')"
if [ "$rows_before" != "$rows_after" ]; then
  fail_step "底表数据" "重复导入导致行数变化（${rows_before} -> ${rows_after}），幂等被破坏"
fi
ok "重复导入校验通过：行数保持 ${rows_after}，没有叠出第二份"

# ---------------------------------------------------------------- 第 4 步
step 4 "拉起后端并跑冒烟（读到驳船列表与载箱量才算就绪）"
port="${BACKEND_PORT:-8000}"
nohup setsid "$BACKEND_DIR/.venv/bin/uvicorn" --app-dir "$BACKEND_DIR" app.main:app --host 127.0.0.1 --port "$port" \
  >"$LOG_DIR/uvicorn-bootstrap-${RUN_STAMP}.log" 2>&1 &
server_pid=$!
cleanup() { kill -- -"$server_pid" >/dev/null 2>&1 || true; }
trap cleanup EXIT

ready=0
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$server_pid" 2>/dev/null || break
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  fail_step "后端进程" "uvicorn 未在 15 秒内就绪（日志：$LOG_DIR/uvicorn-bootstrap-${RUN_STAMP}.log）"
fi
"$VENV_PY" "$BACKEND_DIR/scripts/smoke.py" --base-url "http://127.0.0.1:${port}" || fail_step "冒烟" "驳船列表/载箱量冒烟未通过（缺失项见上方）"

# ---------------------------------------------------------------- 第 5 步
step 5 "前端构建校验（三方组件齐不齐、页面能否编译）"
cd "$FRONTEND_DIR"
npm run build >/dev/null || fail_step "前端构建" "npm run build 失败（类型或编译错误见上方）"
cd "$REPO_ROOT"
ok "前端构建通过（vue-tsc 类型检查 + vite 产物均正常）"

echo
echo "$(c_green "$(c_bold '✔ 支线驳船环境全部就绪')")"
echo "  启动开发：scripts/dev.sh（会自动再跑一遍冒烟）"
echo "  排障归档：docs/troubleshooting/troubleshooting.md"
echo "  本次日志：$LOG_FILE"
