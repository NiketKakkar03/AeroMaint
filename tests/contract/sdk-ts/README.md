# TypeScript SDK contract validation

`live-contract.mjs` is a consumer-driven check for a running API. Install the packed SDK into a clean
consumer directory, set `AEROMAINT_API_URL`, and run it with Node.js.

Run `node tests/contract/sdk-ts/run-packed-smoke.mjs` from the repository root. The harness builds and
packs both public packages, installs their tarballs into a fresh temporary consumer, and runs
`packed-smoke.mjs` there. The install is offline with an isolated npm cache, and the harness verifies
the tarball allowlists, SDK runtime behavior, and the packed reference CLI against a local mock API.
This verifies that neither package relies on monorepo path resolution.
