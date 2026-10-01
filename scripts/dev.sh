#!/usr/bin/env bash
# 本地开发入口：先确保搭建清单全部备齐，再拉起前后端，自动跑一遍冒烟。
# 冒烟不过立即把两个进程都停掉，不留半套环境；冒烟通过后进程保持运行，Ctrl+C 一起退出。
#
# 用法：scripts/dev.sh
set -uo pipefail
RUN_KIND=dev
# shellcheck source=_lib.sh
source "$(dirname "$0")/_lib.sh"

echo "$(c_bold '支线驳船模块 · 本地开发启动')"

# 清单已备齐时 bootstrap 很快（依赖已装、底表已导会直接跳过）
bash "$REPO_ROOT/scripts/bootstrap.sh" || exit 1

port="${BACKEND_PORT:-8000}"
step D "拉起开发进程并自动冒烟"

# 用 setsid 起在独立进程组里：npm run dev 会派生 vite/esbuild，
# uvicorn --reload 会派生 watchfiles 子进程；退出时按进程组（负 PID）一锅端，不留孤儿占端口。
nohup setsid "$BACKEND_DIR/.venv/bin/uvicorn" --app-dir "$BACKEND_DIR" app.main:app \
  --host 127.0.0.1 --port "$port" --reload \
  >"$LOG_DIR/uvicorn-dev-${RUN_STAMP}.log" 2>&1 &
backend_pid=$!

cd "$FRONTEND_DIR"
VITE_PROXY_TARGET="http://127.0.0.1:${port}" nohup setsid npm run dev \
  >"$LOG_DIR/vite-dev-${RUN_STAMP}.log" 2>&1 &
frontend_pid=$!
cd "$REPO_ROOT"

shutting_down=0
cleanup() {
  [ "$shutting_down" -eq 1 ] && return
  shutting_down=1
  echo; echo "停止前后端进程 …"
  # 负 PID = 整个进程组，连 npm→vite→esbuild、uvicorn→reloader 子进程一起收
  kill -- -"$frontend_pid" -"$backend_pid" >/dev/null 2>&1 || true
  wait "$frontend_pid" "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

backend_ready=0
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then backend_ready=1; break; fi
  kill -0 "$backend_pid" 2>/dev/null || { echo "后端进程已退出，日志：$LOG_DIR/uvicorn-dev-${RUN_STAMP}.log"; exit 1; }
  sleep 0.5
done
[ "$backend_ready" -eq 1 ] || { echo "后端未在 15 秒内就绪"; exit 1; }

frontend_ready=0
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:5173/" >/dev/null 2>&1; then frontend_ready=1; break; fi
  kill -0 "$frontend_pid" 2>/dev/null || { echo "前端进程已退出，日志：$LOG_DIR/vite-dev-${RUN_STAMP}.log"; exit 1; }
  sleep 0.5
done
[ "$frontend_ready" -eq 1 ] || { echo "前端 dev server 未在 15 秒内就绪"; exit 1; }

# 冒烟 1：后端直连
"$VENV_PY" "$BACKEND_DIR/scripts/smoke.py" --base-url "http://127.0.0.1:${port}" || { echo "后端冒烟失败，停止两个进程"; exit 1; }
# 冒烟 2：走前端 vite 代理，确认页面真正调用的链路读得到驳船列表与载箱量
"$VENV_PY" "$BACKEND_DIR/scripts/smoke.py" --base-url "http://127.0.0.1:5173" || { echo "前端代理链路冒烟失败，停止两个进程"; exit 1; }

echo
echo "$(c_green '✔ 冒烟全部通过，开发环境就绪')"
echo "  前端页面：http://127.0.0.1:5173/  （支线驳船在侧边栏「支线驳船」)"
echo "  后端接口：http://127.0.0.1:${port}/api/feeder"
echo "  运行日志：$LOG_DIR/{uvicorn,vite}-dev-${RUN_STAMP}.log"
echo "  按 Ctrl+C 停止全部进程"
wait
