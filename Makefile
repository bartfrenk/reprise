.PHONY: install lint test

install:
	uv tool install --force --editable .

lint:
	uv run black --check src tests
	uv run isort --check-only src tests
	uv run basedpyright src tests

test:
	uv run pytest
