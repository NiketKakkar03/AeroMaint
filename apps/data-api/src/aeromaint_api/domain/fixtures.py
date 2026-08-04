from aeromaint_api.domain.manifest import CaptureSessionManifest

FIXTURE_SESSION_ID = "fixture-session-001"

FIXTURE_MANIFEST = CaptureSessionManifest.model_validate(
    {
        "schema_version": "1.0.0",
        "session_id": FIXTURE_SESSION_ID,
        "display_name": "Deterministic stereo and IMU fixture",
        "start_ns": 9_007_199_254_740_993,
        "end_ns": 9_007_199_454_740_993,
        "streams": [
            {
                "id": "camera-left",
                "kind": "video",
                "clock_id": "session",
                "start_ns": 9_007_199_254_740_993,
                "end_ns": 9_007_199_454_740_993,
                "sample_count": 5,
            },
            {
                "id": "imu-main",
                "kind": "imu",
                "clock_id": "session",
                "start_ns": 9_007_199_254_740_993,
                "end_ns": 9_007_199_454_740_993,
                "sample_count": 41,
            },
        ],
    }
)
