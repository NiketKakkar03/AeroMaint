from aeromaint_api.domain.manifest import CaptureSessionManifest

FIXTURE_SESSION_ID = "fixture-session-001"

FIXTURE_MANIFEST = CaptureSessionManifest.model_validate(
    {
        "schema_version": "1.0.0",
        "session_id": FIXTURE_SESSION_ID,
        "display_name": "Deterministic stereo and IMU fixture",
        "start_ns": 9_007_199_254_740_993,
        "end_ns": 9_007_199_454_740_993,
        "session_clock_id": "session",
        "clocks": [
            {
                "id": "session",
                "source_epoch_ns": 0,
                "session_epoch_ns": 0,
                "rate_numerator": 1,
                "rate_denominator": 1,
            },
            {
                "id": "imu-device",
                "source_epoch_ns": 1_000_000,
                "session_epoch_ns": 9_007_199_254_740_993,
                "rate_numerator": 1_000_001,
                "rate_denominator": 1_000_000,
            },
        ],
        "artifacts": [
            {
                "id": "video-left-index",
                "media_type": "application/vnd.aeromaint.frame-index+json",
                "logical_key": "sessions/fixture-session-001/camera-left/index.json",
                "size_bytes": 512,
                "sha256": "1" * 64,
            },
            {
                "id": "imu-arrow",
                "media_type": "application/vnd.apache.arrow.stream",
                "logical_key": "sessions/fixture-session-001/imu-main/samples.arrow",
                "size_bytes": 2048,
                "sha256": "2" * 64,
            },
            {
                "id": "stereo-calibration",
                "media_type": "application/json",
                "logical_key": "sessions/fixture-session-001/calibration/stereo.json",
                "size_bytes": 256,
                "sha256": "3" * 64,
            },
        ],
        "calibrations": [
            {
                "id": "stereo-rig",
                "kind": "stereo_camera",
                "artifact_id": "stereo-calibration",
            }
        ],
        "streams": [
            {
                "id": "camera-left",
                "kind": "video",
                "clock_id": "session",
                "start_ns": 9_007_199_254_740_993,
                "end_ns": 9_007_199_454_740_993,
                "sample_count": 5,
                "schema_ref": "aeromaint://schemas/video-frame-index/1.0.0",
                "artifact_ids": ["video-left-index"],
                "calibration_ids": ["stereo-rig"],
                "gaps": [
                    {
                        "start_ns": 9_007_199_334_740_993,
                        "end_ns": 9_007_199_374_740_993,
                        "reason": "missing",
                    }
                ],
            },
            {
                "id": "imu-main",
                "kind": "imu",
                "clock_id": "imu-device",
                "start_ns": 9_007_199_254_740_993,
                "end_ns": 9_007_199_454_740_993,
                "sample_count": 41,
                "schema_ref": "aeromaint://schemas/imu/1.0.0",
                "artifact_ids": ["imu-arrow"],
                "calibration_ids": [],
                "gaps": [],
            },
        ],
        "provenance": {
            "source_type": "synthetic",
            "source_uri": "aeromaint://fixtures/sync-v1",
            "source_sha256": "a" * 64,
            "adapter": "synthetic-fixture",
            "adapter_version": "1.0.0",
        },
    }
)
