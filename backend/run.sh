#!/usr/bin/env bash
# 后端直接启动入口（已跑过 scripts/bootstrap.sh 时用）。
# 首次接手请直接用 ../../scripts/bootstrap.sh 或 scripts/dev.sh，会自动备齐依赖、库表、底表。
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "后端虚拟环境不存在，请先执行 scripts/bootstrap.sh（第 1 步会自动创建）" >&2
  exit 1
fi
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT:-8000}"
