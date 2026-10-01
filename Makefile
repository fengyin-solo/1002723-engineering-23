.PHONY: install setup smoke test backend frontend

install:
	scripts/setup.sh --deps-only

setup:
	scripts/setup.sh

smoke:
	python3 scripts/smoke_feeder.py

test:
	cd backend && .venv/bin/python -m unittest discover -s tests -v

backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev
