.PHONY: bootstrap demo local-ci ci ci-portable sdk-pack browser-compatibility release-artifacts security-scan compose-smoke seed backup restore reset smoke smoke-matrix backup-restore-drill failure-injection dev check test euroc-download euroc-verify euroc-fixture-check cmapss-acquire cmapss-prepare cmapss-train rag-acquire rag-index rag-evaluate up-core up-media up-ml up-ai up-observe up-full down

bootstrap:
	./scripts/local-release bootstrap

demo:
	./scripts/local-release demo

local-ci:
	./scripts/local-release ci

seed:
	./scripts/local-release seed

backup:
	./scripts/local-release backup --target "$(TARGET)" $(if $(OUTPUT),--output "$(OUTPUT)")

restore:
	./scripts/local-release restore --target "$(TARGET)" --input "$(INPUT)"

reset:
	./scripts/local-release reset --target "$(TARGET)" --confirm "$(CONFIRM)"

smoke:
	./scripts/local-release smoke $(if $(PROFILE),--profile "$(PROFILE)")

smoke-matrix:
	./scripts/profile-smoke-matrix.sh

backup-restore-drill:
	./scripts/backup-restore-drill.sh

failure-injection:
	./scripts/failure-injection.sh

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

sdk-pack:
	pnpm test:sdk-pack
	pnpm test:sdk-python-pack

browser-compatibility:
	pnpm --filter @aeromaint/viewer exec playwright test --project=chromium --project=firefox

release-artifacts:
	uv run python scripts/build_release.py

security-scan:
	sh infrastructure/local-release/security-scan.sh

compose-smoke:
	sh infrastructure/local-release/compose-smoke.sh

ci-portable: check sdk-pack release-artifacts

ci: ci-portable browser-compatibility security-scan compose-smoke

sdk-pack:
	pnpm test:sdk-pack
	pnpm test:sdk-python-pack

browser-compatibility:
	pnpm --filter @aeromaint/viewer exec playwright test --project=chromium --project=firefox

release-artifacts:
	uv run python scripts/build_release.py

security-scan:
	sh infrastructure/local-release/security-scan.sh

compose-smoke:
	sh infrastructure/local-release/compose-smoke.sh

ci-portable: check sdk-pack release-artifacts

ci: ci-portable browser-compatibility security-scan compose-smoke

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

rag-index:
	@test -n "$(RAG_MANIFEST)" || (echo "RAG_MANIFEST is required" >&2; exit 2)
	uv run python -c 'from pathlib import Path; from pipelines.documents.index import build_from_manifest; build_from_manifest(Path("$(RAG_MANIFEST)"), Path("$(or $(RAG_INDEX),artifacts/retrieval/index.json)"))'

rag-acquire:
	@test -n "$(RAG_MANIFEST)" || (echo "RAG_MANIFEST is required" >&2; exit 2)
	uv run python -c 'from pathlib import Path; from pipelines.documents.index import acquire_from_manifest; acquire_from_manifest(Path("$(RAG_MANIFEST)"))'

rag-evaluate:
	uv run python evals/rag/evaluate.py --index "$(or $(RAG_INDEX),artifacts/retrieval/index.json)"

up-core:
	./scripts/local-release up --profile core

up-media:
	./scripts/local-release up --profile media

up-ml:
	./scripts/local-release up --profile ml

up-ai:
	./scripts/local-release up --profile ai

up-observe:
	./scripts/local-release up --profile observe

up-full:
	./scripts/local-release up --profile full

down:
	./scripts/local-release down
