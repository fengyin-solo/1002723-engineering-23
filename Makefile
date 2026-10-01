.PHONY: setup dev backend frontend smoke verify

# 一次性搭建：三方组件 + 库表 + 底表 + 冒烟，逐步检查，缺什么停什么
setup:
	bash scripts/bootstrap.sh

# 本地开发：清单校验 + 前后端进程 + 自动冒烟（含 vite 代理链路）
dev:
	bash scripts/dev.sh

# 只起单端（默认你已经 make setup 过）
backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

# 对已在运行的环境补跑冒烟（默认本机 8000，可用 BASE_URL 指向别处）
smoke:
	backend/.venv/bin/python backend/scripts/smoke.py --base-url "$(BASE_URL)"

# 上线前：两处环境各跑一遍冒烟并比对载箱量
# make verify ENV_A=http://pre ENV_B=http://prod
verify:
	bash scripts/verify.sh --env-a "$(ENV_A)" --env-b "$(ENV_B)"
