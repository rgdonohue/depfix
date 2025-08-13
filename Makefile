.PHONY: dev test lint format typecheck clean

dev:
	uv sync --dev

test:
	uv run pytest tests/ -v

test-watch:
	uv run pytest tests/ -v --tb=short -x --lf

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy .

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -exec rm -rf {} +