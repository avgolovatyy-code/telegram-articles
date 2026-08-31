PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: install lint fmt typecheck test migrate revision run worker seed check

install:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

lint:
	.venv/bin/ruff check app tests
	.venv/bin/ruff format --check app tests

fmt:
	.venv/bin/ruff check --fix app tests
	.venv/bin/ruff format app tests

typecheck:
	.venv/bin/mypy app

test:
	.venv/bin/pytest

check: lint typecheck test

migrate:
	.venv/bin/alembic upgrade head

revision:
	.venv/bin/alembic revision --autogenerate -m "$(m)"

seed:
	$(PY) -m app.cli seed

run:
	.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	$(PY) -m app.cli worker
