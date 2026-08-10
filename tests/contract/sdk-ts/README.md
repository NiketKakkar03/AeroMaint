# TypeScript SDK contract validation

`live-contract.mjs` is a consumer-driven check for a running API. Install the packed SDK into a clean
consumer directory, set `AEROMAINT_API_URL`, and run it with Node.js.

For package validation, build both public packages, run `pnpm pack` in `packages/contracts` and
`packages/capture-sdk-ts`, install both tarballs in a temporary directory, copy `packed-smoke.mjs`, and
run it. This verifies that the package works without monorepo path resolution.
