#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# 别的机器上建的 venv 在本机跑不起来（pyvenv.cfg 里是他机的 Python 路径），先验活再决定重建
if [ -d .venv ] && ! .venv/bin/python -c '' 2>/dev/null; then
  echo "现有 .venv 在本机不可执行，重建"
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
  if ! python3 -m venv .venv 2>/dev/null; then
    # 系统缺 ensurepip（如 Debian 未装 python3-venv）时的兜底：无 pip 建环境再引导 pip
    rm -rf .venv
    python3 -m venv --without-pip .venv
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    .venv/bin/python /tmp/get-pip.py -q
  fi
fi
# 按锁定版本安装，保证每台机器上的三方组件对齐
.venv/bin/pip install -q -r requirements.lock
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
