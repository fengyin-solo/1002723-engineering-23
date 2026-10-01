#!/usr/bin/env bash
# 上线前核对：用同一份清单部署的两处环境各跑一遍冒烟，读到的驳船载箱量必须相同。
#
# 用法（推荐：预发 + 生产两个基地址）：
#   scripts/verify.sh --env-a http://pre.example.com --env-b http://prod.example.com
# 不带参数时在本机起两个实例（8000/8001，各自独立 SQLite）做自检：
#   scripts/verify.sh
set -uo pipefail
RUN_KIND=verify
# shellcheck source=_lib.sh
source "$(dirname "$0")/_lib.sh"

echo "$(c_bold '支线驳船模块 · 上线前双环境核对')"

if [ "$#" -eq 0 ]; then
  warn "未传入环境地址，改用本机双实例自检（8000 / 8001，独立库文件）"

  # 同一台机器模拟两处环境：不同端口 + 不同 SQLite 文件
  FEEDER_DB_PATH="$BACKEND_DIR/data/verify-a.sqlite3" BACKEND_PORT=8000 \
    APP_ENV=verify-a bash "$REPO_ROOT/scripts/bootstrap.sh" || fail_step "环境A自检" "bootstrap 未通过"
  cp "$BACKEND_DIR/data/verify-a.sqlite3" "$BACKEND_DIR/data/verify-b.sqlite3"

  env_a="http://127.0.0.1:8000"
  env_b="http://127.0.0.1:8001"
  FEEDER_DB_PATH="$BACKEND_DIR/data/verify-a.sqlite3" APP_ENV=verify-a \
    nohup setsid "$BACKEND_DIR/.venv/bin/uvicorn" --app-dir "$BACKEND_DIR" app.main:app --host 127.0.0.1 --port 8000 \
    >"$LOG_DIR/verify-a-${RUN_STAMP}.log" 2>&1 &
  pid_a=$!
  FEEDER_DB_PATH="$BACKEND_DIR/data/verify-b.sqlite3" APP_ENV=verify-b \
    nohup setsid "$BACKEND_DIR/.venv/bin/uvicorn" --app-dir "$BACKEND_DIR" app.main:app --host 127.0.0.1 --port 8001 \
    >"$LOG_DIR/verify-b-${RUN_STAMP}.log" 2>&1 &
  pid_b=$!
  cleanup() { kill -- -"$pid_a" -"$pid_b" >/dev/null 2>&1 || true; rm -f "$BACKEND_DIR/data/verify-a.sqlite3" "$BACKEND_DIR/data/verify-b.sqlite3"; }
  trap cleanup EXIT
  for _ in $(seq 1 30); do
    curl -sf "$env_a/api/health" >/dev/null 2>&1 && curl -sf "$env_b/api/health" >/dev/null 2>&1 && break
    sleep 0.5
  done
  name_a="本地自检-A(8000)"; name_b="本地自检-B(8001)"
else
  # 解析参数（兼容 --env-a URL / --env-b URL / --name-a / --name-b）
  env_a="http://127.0.0.1:8000"; env_b="http://127.0.0.1:8001"
  name_a="环境A/预发"; name_b="环境B/生产"
  while [ $# -gt 0 ]; do
    case "$1" in
      --env-a) env_a="$2"; shift 2 ;;
      --env-b) env_b="$2"; shift 2 ;;
      --name-a) name_a="$2"; shift 2 ;;
      --name-b) name_b="$2"; shift 2 ;;
      *) fail_step "参数" "不认识的参数：$1（用法见脚本头注释）" ;;
    esac
  done
fi

"$VENV_PY" "$BACKEND_DIR/scripts/verify_envs.py" \
  --env-a "$env_a" --name-a "$name_a" \
  --env-b "$env_b" --name-b "$name_b" || fail_step "双环境核对" "冒烟或载箱量比对未通过（差异见上方）"

echo
echo "$(c_green '✔ 上线前核对通过：两处环境载箱量一致')"
echo "  核对日志：$LOG_FILE"
