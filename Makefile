default:
	@echo "View Makefile for usage"

sys_deps := poetry==0.12.9 pre-commit

bootstrap: ## Install system dependencies for this project (macOS or pyenv)
	pip install -U $(sys_deps)

bootstrap-user: ## Install system dependencies for this project in user dir (Linux)
	pip install --user -U $(sys_deps)

install: ## Install project dependencies
	pre-commit install
	poetry config settings.virtualenvs.in-project true
	poetry install

lint: ## Lint code with flake8
	poetry run flake8 opset tests

test: ## Run pytest test suite
	poetry run pytest --cov=opset tests
