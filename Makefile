default:
	@echo "View Makefile for usage"

.PHONY: install format lint tests

install:
	uv sync --all-extras

format: install
	uv run --no-sync ruff check --fix .
	uv run --no-sync ruff format .

MYPY_TARGETS = opset/
lint: install
	uv run --no-sync ruff check .
	uv run --no-sync mypy $(MYPY_TARGETS)
	uv run --no-sync ruff format --check .

tests:
	uv run pytest --cov-report term-missing --cov opset tests

tests-ci:
	uv run pytest --cov-report term-missing --cov-report xml --cov opset tests
