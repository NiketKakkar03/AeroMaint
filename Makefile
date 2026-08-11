.PHONY: bootstrap dev check test euroc-download euroc-verify euroc-fixture-check cmapss-acquire cmapss-prepare cmapss-train up-core down

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

cmapss-acquire:
	@test -n "$(CMAPSS_URL)" || (echo "CMAPSS_URL is required" >&2; exit 2)
	@test -n "$(CMAPSS_SHA256)" || (echo "CMAPSS_SHA256 is required" >&2; exit 2)
	uv run python scripts/prepare_cmapss.py acquire --url "$(CMAPSS_URL)" \
		--sha256 "$(CMAPSS_SHA256)" --output "$(or $(CMAPSS_SOURCE),data/cmapss/train_FD001.txt)"

cmapss-prepare:
	@test -n "$(CMAPSS_SOURCE)" || (echo "CMAPSS_SOURCE is required" >&2; exit 2)
	uv run python scripts/prepare_cmapss.py prepare --source "$(CMAPSS_SOURCE)" \
		--destination "$(or $(CMAPSS_DEST),artifacts/datasets/cmapss-fd001)"

cmapss-train:
	uv run python scripts/train_rul.py \
		--dataset "$(or $(CMAPSS_DEST),artifacts/datasets/cmapss-fd001)" \
		--output "$(or $(RUL_OUTPUT),artifacts/models/cmapss-rul)"

up-core:
	docker compose --profile core up --build

down:
	docker compose down --remove-orphans
