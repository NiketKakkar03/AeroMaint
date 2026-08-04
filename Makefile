.PHONY: bootstrap dev check test euroc-download euroc-verify euroc-fixture-check up-core down

bootstrap:
	pnpm install
	uv sync --python 3.11

dev:
	pnpm dev

check:
	pnpm check
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy apps/data-api/src apps/worker/src packages pipelines
	uv run pytest

test:
	pnpm test
	uv run pytest

EUROC_SEQUENCE ?= V1_01_easy
EUROC_DEST ?= data/euroc

euroc-download:
	@test -n "$(EUROC_SHA256)" || (echo "EUROC_SHA256 is required" >&2; exit 2)
	uv run python scripts/download_euroc.py download \
		--sequence "$(EUROC_SEQUENCE)" --destination "$(EUROC_DEST)" \
		--sha256 "$(EUROC_SHA256)"

euroc-verify:
	@test -n "$(EUROC_ARCHIVE)" || (echo "EUROC_ARCHIVE is required" >&2; exit 2)
	@test -n "$(EUROC_SHA256)" || (echo "EUROC_SHA256 is required" >&2; exit 2)
	uv run python scripts/download_euroc.py verify \
		--archive "$(EUROC_ARCHIVE)" --sha256 "$(EUROC_SHA256)"

euroc-fixture-check:
	uv run python scripts/download_euroc.py verify-fixture tests/media-fixtures/euroc-mini

up-core:
	docker compose --profile core up --build

down:
	docker compose down --remove-orphans
