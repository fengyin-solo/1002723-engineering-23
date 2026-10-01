#!/usr/bin/env bash
# 支线驳船模块搭建清单的公共函数：日志、逐步检查、缺什么报什么。
# 被 bootstrap.sh / dev.sh / verify.sh source，不单独执行。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
VENV_PY="$BACKEND_DIR/.venv/bin/python"
LOG_DIR="$REPO_ROOT/docs/troubleshooting/logs"
mkdir -p "$LOG_DIR"

# 所有搭建/排障输出统一归档：logs/bootstrap-YYYYmmdd-HHMMSS.log
RUN_STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_KIND="${RUN_KIND:-bootstrap}"
LOG_FILE="$LOG_DIR/${RUN_KIND}-${RUN_STAMP}.log"
exec > >(tee "$LOG_FILE") 2>&1

c_red()   { printf '\033[31m%s\033[0m' "$1"; }
c_green() { printf '\033[32m%s\033[0m' "$1"; }
c_yellow(){ printf '\033[33m%s\033[0m' "$1"; }
c_bold()  { printf '\033[1m%s\033[0m' "$1"; }

step() { echo; echo "$(c_bold "==> [第 $1 步] $2")"; }
ok()   { echo "    $(c_green '✔') $1"; }
warn() { echo "    $(c_yellow '!') $1"; }

# fail_step <步骤名> <缺失项1> [缺失项2 ...]
fail_step() {
  local step_name="$1"; shift
  echo "$(c_red "✘ [${step_name}] 未备齐，停在这一步。缺失/异常项：")"
  local item
  for item in "$@"; do echo "    $(c_red '-') $item"; done
  echo "    排障记录：docs/troubleshooting/troubleshooting.md"
  echo "    本次完整日志：$LOG_FILE"
  exit 1
}
