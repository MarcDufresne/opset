default:
	@echo "View Makefile for usage"

.PHONY: install format lint tests

install:
	poetry install -E gcp

format:
	poetry run ruff --fix .
	poetry run black .

MYPY_TARGETS = opset/

lint:
	poetry run ruff .
	poetry run mypy $(MYPY_TARGETS)
	poetry run black --check .

tests:
	poetry run pytest --cov-report term-missing --cov opset tests

tests-ci:
	poetry run pytest --cov-report term-missing --cov-report lcov --cov opset tests
