default:
	@echo "View Makefile for usage"

sys_deps := poetry==1.0.2 pre-commit

bootstrap: ## Install system dependencies for this project (macOS or pyenv)
	pip install -U $(sys_deps)

bootstrap-user: ## Install system dependencies for this project in user dir (Linux)
	pip install --user -U $(sys_deps)

install: ## Install project dependencies
	pre-commit install
	poetry config virtualenvs.in-project true
	poetry install

lint: ## Lint code with flake8
	poetry run flake8 opset tests

test: ## Run pytest test suite
	poetry run pytest --cov=opset tests

format:  ## Format the code using black and isort
	poetry run black opset tests
	poetry run isort -rc -y opset tests
