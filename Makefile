.PHONY: bootstrap dev check test up-core down

bootstrap:
	pnpm install
	uv sync --python 3.11

dev:
	pnpm dev

check:
	pnpm check
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy apps/data-api/src apps/worker/src
	uv run pytest

test:
	pnpm test
	uv run pytest

up-core:
	docker compose --profile core up --build

down:
	docker compose down --remove-orphans
