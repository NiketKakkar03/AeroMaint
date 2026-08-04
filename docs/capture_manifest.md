# Capture-session manifest contract

The capture-session manifest is AeroMaint's canonical public description of synchronized evidence.
Adapters publish it, the API preserves it, SDKs translate it to safe language types, and downstream
features consume it without accessing storage models.

The golden version 1 fixture is
[`tests/contract/fixtures/capture-manifest-v1.json`](../tests/contract/fixtures/capture-manifest-v1.json).

## Wire-format rules

- JSON property names use `snake_case`; SDKs may expose idiomatic language-specific names.
- Signed 64-bit nanosecond values are canonical decimal strings. Leading zeroes, decimal points,
  exponent notation, and values outside `[-2^63, 2^63 - 1]` are invalid.
- Array order is significant for streams and gaps. Identifiers are unique within their collection.
- SHA-256 values are 64 lowercase hexadecimal characters.
- Unknown additive properties are ignored by version 1 readers. Missing required properties and
  unknown enum values are rejected.

## Required sections

| Section      | Meaning                                                        | Key integrity rules                                            |
| ------------ | -------------------------------------------------------------- | -------------------------------------------------------------- |
| Session      | Identity, display name, authoritative range, and session clock | End is not before start; the clock exists                      |
| Clocks       | Integer affine mappings from source time to session time       | Unique IDs; positive rational rate                             |
| Artifacts    | Immutable media, indexes, samples, and calibration payloads    | Unique IDs; digest, size, media type, and logical key required |
| Calibrations | Typed references to calibration artifacts                      | Referenced artifact exists                                     |
| Streams      | Video, IMU, pose, event, or telemetry evidence                 | Range is inside session; clock and artifacts exist             |
| Gaps         | Explicit missing, corrupt, or discontinuous intervals          | Inside stream; ordered and non-overlapping                     |
| Provenance   | Source identity, digest, adapter, and adapter version          | Source and producer remain reproducible                        |

An artifact `logical_key` is an implementation-independent key. It must not contain an absolute
filesystem path or grant direct storage access.

## Clock mapping

Each clock defines an exact rational affine mapping:

```text
session_ns = session_epoch_ns
           + round_toward_negative_infinity(
               (source_ns - source_epoch_ns) * rate_numerator / rate_denominator
             )
```

All intermediate arithmetic is arbitrary precision. Implementations check the final value fits in a
signed 64-bit integer. The session clock normally has zero epochs and a `1/1` rate. Drift is encoded
with the rational rate rather than floating-point scale.

## Compatibility

The manifest uses semantic versions:

- Readers accept the exact supported major version and ignore unknown additive fields.
- Adding an optional field is backward-compatible and increments the minor version when published.
- Removing a field, changing meaning, tightening an accepted range, or changing an enum incompatibly
  requires a new major version.
- SDKs return a typed `unsupported_schema` error before parsing an unsupported major version.
- Golden fixtures must validate equivalently in TypeScript and Python before a version is released.

## Validation ownership

Runtime validation exists in `packages/contracts` and
`apps/data-api/src/aeromaint_api/domain/manifest.py`. Both validators reject reversed ranges,
out-of-range timestamps, duplicate identities, dangling references, out-of-bounds gaps, and
overlapping gaps. Qualitative tests use the same golden JSON and intentionally damage these semantic
relationships to prove failures are explicit.

## Deterministic synchronization fixture

`tests/media-fixtures/synthetic-session` contains two video frame indexes, IMU, pose, and event
records, stereo calibration, declared missing-data intervals, a clock with a known offset and drift,
and language-neutral expected lookups. Regenerate it with:

```bash
uv run python scripts/generate_sync_fixture.py
```

The committed `SHA256SUMS` file and cross-language tests prove regeneration is byte-for-byte stable.
Frame lookup defaults to presentation time at-or-before the request; nearest-frame ties choose the
earlier frame. Both lookup modes return no evidence when the requested time lies in a declared gap.
