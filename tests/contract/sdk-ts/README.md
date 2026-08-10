# TypeScript SDK contract validation

`live-contract.mjs` is a consumer-driven check for a running API. Install the packed SDK into a clean
consumer directory, set `AEROMAINT_API_URL`, and run it with Node.js.

Run `node tests/contract/sdk-ts/run-packed-smoke.mjs` from the repository root. The harness builds and
packs both public packages, installs their tarballs into a fresh temporary consumer, and runs
`packed-smoke.mjs` there. This verifies that the SDK works without monorepo path resolution.
