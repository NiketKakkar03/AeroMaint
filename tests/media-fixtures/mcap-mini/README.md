# AeroMaint synthetic ROS 2 MCAP fixture

This deterministic, unchunked MCAP was authored for AeroMaint CI. It contains one synthetic CDR
message each for ROS 2 image, IMU, pose, and maintenance-event topics, plus an unsupported schema
declaration used to exercise diagnostics. It contains no third-party measurements or imagery and
is redistribution-safe under the repository license.

Regenerate it with `uv run python scripts/generate_mcap_fixture.py` and verify both files against
`SHA256SUMS`. The unchunked layout deliberately keeps the adapter and fixture dependency-free;
production chunked/compressed bags must be rewritten to unchunked MCAP before import.
