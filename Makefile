.PHONY: install lint

install:
	uv tool install --force --editable .

lint:
	uv run black --check src
	uv run isort --check-only src
	uv run basedpyright src
