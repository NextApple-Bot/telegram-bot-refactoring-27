.PHONY: help install lint format test test-integration coverage clean

help:
	@echo "Available commands:"
	@echo "  make install       - install dependencies"
	@echo "  make lint          - run ruff linter"
	@echo "  make format        - format code with ruff and black"
	@echo "  make test          - run unit tests (fast)"
	@echo "  make test-all      - run all tests (unit + integration)"
	@echo "  make coverage      - generate coverage report"
	@echo "  make clean         - remove cache and temp files"

install:
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

lint:
	ruff check .

format:
	ruff check --fix .
	ruff format .

test:
	pytest tests/ -m "not integration" -v

test-all:
	pytest tests/ -v --cov=bot --cov=web_admin

test-integration:
	pytest tests/ -m integration -v

coverage:
	pytest tests/ --cov=bot --cov=web_admin --cov-report=html --cov-report=term
	@echo "Coverage report generated at htmlcov/index.html"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage coverage.xml htmlcov
