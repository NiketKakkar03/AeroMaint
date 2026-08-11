# Dataset cards

## EuRoC MAV

### Selection and intended use

AeroMaint uses **V1_01_easy** as the short developer sequence and **MH_01_easy** as the complete
performance sequence. Neither sequence is required for CI or `make demo`. They are intended only for
development, integration, and performance evaluation of deterministic stereo/IMU/pose ingestion.
They are not suitable for aircraft-maintenance decisions, safety validation, object recognition, or
claims about operational aviation environments.

### Source, license, and provenance

EuRoC MAV was produced by the Autonomous Systems Lab at ETH Zurich and is described in M. Burri et
al., _The EuRoC micro aerial vehicle datasets_, IJRR 2016. The source page is
<https://projects.asl.ethz.ch/datasets/doku.php?id=kmavvisualinertialdatasets>. The publisher states
that the datasets are released under Creative Commons Attribution 3.0. Users must confirm the terms
at the source and preserve the requested attribution. AeroMaint does not redistribute EuRoC data.

The legacy per-sequence endpoint does not publish SHA-256 digests. For that reason the acquisition
command requires a 64-character SHA-256 supplied from a trusted acquisition record; it never treats a
newly downloaded archive as its own authority. Each successful extraction records the URL, digest,
archive size, and sequence in `AEROMAINT_ACQUISITION.json` beside the ignored local data.

| Purpose                | Sequence     | Expected archive layout | Approximate scale                                         |
| ---------------------- | ------------ | ----------------------- | --------------------------------------------------------- |
| Developer integration  | `V1_01_easy` | ZIP containing `mav0/`  | Full short Vicon-room flight; hundreds of MB              |
| Performance evaluation | `MH_01_easy` | ZIP containing `mav0/`  | Full machine-hall flight; approximately 1.5 GB compressed |

### Acquisition

Downloads are explicit and checksum-gated:

```bash
make euroc-download EUROC_SEQUENCE=V1_01_easy \
  EUROC_SHA256=<trusted-64-character-digest>
```

To verify an archive already obtained through an approved channel:

```bash
make euroc-verify EUROC_ARCHIVE=/path/to/V1_01_easy.zip \
  EUROC_SHA256=<trusted-64-character-digest>
```

The script rejects mismatches and unsafe ZIP paths before extraction. `data/`, archives, and generated
media are excluded from Git. Never add full sequences or derivatives to the repository.

### Layout and limitations

The adapter expects the EuRoC `mav0` layout: `cam0`, `cam1`, `imu0`, and a pose source named
`state_groundtruth_estimate0` or `vicon0`, each with EuRoC CSV metadata and sensor YAML where
applicable. Real sequences contain grayscale global-shutter stereo images, synchronized IMU records,
calibration, and external pose estimates. Ground truth availability and accuracy vary by environment;
timestamps, missing images, corrupt files, and sensor gaps must be validated rather than assumed.

### CI fixture

`tests/media-fixtures/euroc-mini` is an AeroMaint-authored synthetic fixture that imitates only the
directory and CSV conventions needed by the adapter. It contains no EuRoC measurements or images,
is redistribution-safe under the repository license, and is protected by `SHA256SUMS`. Validate it
with `make euroc-fixture-check`.

## ROS 2/MCAP

### Selection and intended use

The MCAP adapter is a contract fixture and import path for selected ROS 2 image, IMU, pose, and
maintenance-event topics. It demonstrates that canonical sessions and downstream consumers do not
depend on EuRoC conventions. Imported data remains unsuitable for maintenance or safety decisions
unless its producer, calibration, timing, and operating context have been independently validated.

### Supported source contract

The current dependency-free reader accepts deterministic, **unchunked** MCAP files with the `ros2`
profile, `ros2msg` schemas, and little-endian `cdr` messages for:

| ROS 2 type                      | Canonical kind | Preserved evidence                                                                |
| ------------------------------- | -------------- | --------------------------------------------------------------------------------- |
| `sensor_msgs/msg/Image`         | `video`        | topic, encoding, dimensions, step, frame ID, source and canonical times           |
| `sensor_msgs/msg/Imu`           | `imu`          | topic, frame ID, covariance, `rad/s` and `m/s²` units, source and canonical times |
| `geometry_msgs/msg/PoseStamped` | `pose`         | topic, frame ID, metre units, source and canonical times                          |
| `aeromaint_msgs/msg/Event`      | `event`        | topic, frame ID, severity, message, source and canonical times                    |

The earliest ROS publish timestamp becomes the source clock epoch and maps exactly to canonical
session time zero at a 1:1 rate. Original publish and log timestamps remain in canonical artifacts.
ROS topic/type/frame/unit details and unsupported-topic diagnostics are retained in namespaced
provenance. Viewer and TypeScript SDK contracts continue to expose only the canonical manifest and
stream fields.

Unsupported topics in an otherwise usable bag are recorded with the topic name, ROS type, schema
encoding, message encoding, and the complete supported-type list. A bag containing no supported
messages is rejected with that same actionable diagnostic. Chunked or compressed bags are rejected
with guidance to rewrite them as unchunked MCAP before import.

### CI fixture and provenance

`tests/media-fixtures/mcap-mini/ros2-mini.mcap` is generated entirely by AeroMaint from synthetic
values and contains no external dataset content. It has one message for each supported type and one
unsupported schema declaration. `SHA256SUMS` covers the fixture and its README; regenerate both
deterministically with:

```bash
uv run python scripts/generate_mcap_fixture.py
```

The fixture and EuRoC source run through the shared adapter conformance suite in
`tests/contract/source_adapters/test_conformance.py`, including canonical consumer validation and an
MCAP golden-manifest comparison.
