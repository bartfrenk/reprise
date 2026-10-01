.PHONY: install lint

install:
	uv tool install --force --editable .

lint:
	black --check src
	isort --check-only src
	pyright src
