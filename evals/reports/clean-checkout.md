# Clean-checkout rehearsal

- Status: `passed_with_documented_skips`
- Source commit rehearsed: `60e06c6982659a4e4fad6e0f08f0c2d85b2019e9`
- Host/runtime: macOS Darwin 25.0.0; Python 3.11.15; pnpm 11.16.0; bundled Node 22
- Completed elapsed time: **56 seconds**, including frozen dependency installation

The first detached `git archive` attempt used offline-only installation and stopped after one second
because the isolated pnpm store lacked the locked `@eslint/js` tarball. No later gate was claimed for
that attempt. The script was corrected to allow frozen network-capable installs.

The second detached-archive rehearsal completed:

1. `pnpm install --frozen-lockfile` — passed.
2. `uv sync --frozen --python 3.11` — passed.
3. `make release-check` — passed; 12 required files and local Markdown links validated.
4. `pnpm check` — passed: formatting, lint, typecheck, and 64 TypeScript tests.
5. Ruff format/lint and mypy over 81 Python source files — passed.
6. Pytest — 99 passed, 4 skipped, 81% statement/branch aggregate coverage in 11.40 seconds.

The four skipped tests are the PostgreSQL integration suite because
`AEROMAINT_TEST_DATABASE_URL` was not configured. Browser/Playwright suites, the retained 20-minute
benchmark, full C-MAPSS training, broad RAG evaluation, and external security testing were not part of
this short rehearsal; their status remains explicit elsewhere in the evidence index.

Because recording this evidence changes the final commit, the archived source commit above is the
content parent of the final amended documentation commit. The archive workflow itself is re-run on
the final clean commit and its checksum is reported in the handoff; this record does not pretend the
earlier hash is the final release hash.
