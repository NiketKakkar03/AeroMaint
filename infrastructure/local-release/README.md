# Local release gate

`make ci` is the single release-candidate gate. It starts from checked-in locks and runs
formatting, linting, type checks, unit/contract/integration/load/failure/security/memory tests,
clean packed TypeScript and Python SDK consumers, Chromium and Firefox viewer compatibility,
artifact checksums/version metadata, dependency and container-image scans, and an empty-state
Compose smoke test.

The security policy is machine-readable at `tests/security/policy.json`: known, fixed high or
critical dependency/image vulnerabilities fail the release. Unfixed operating-system findings
are reported but do not block until a fixed base image exists.

Platform requirements beyond the normal toolchain are Docker with Compose, Playwright Chromium
and Firefox, `pip-audit`, `trivy`, and outbound advisory-database access. `make ci-portable` runs
the deterministic non-container subset when those platform dependencies are unavailable; it is
useful for development but is not a releasable result.

Artifacts are written to `artifacts/release/`. `release-manifest.json` records the source commit
and component versions; `SHA256SUMS` covers every SDK archive and the manifest.
