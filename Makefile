default:
	@echo "View Makefile for usage"

.PHONY: install format lint tests

install:
	poetry install --sync -E gcp

format:
	poetry run ruff check --fix .
	poetry run ruff format .

MYPY_TARGETS = opset/
lint:
	poetry run ruff check .
	poetry run mypy $(MYPY_TARGETS)
	poetry run ruff format --check .

tests:
	poetry run pytest --cov-report term-missing --cov opset tests

tests-ci:
	poetry run pytest --cov-report term-missing --cov-report xml --cov opset tests
