import pyarrow as pa
from fastapi.testclient import TestClient

from aeromaint_api.domain.fixtures import FIXTURE_SESSION_ID
from aeromaint_api.domain.transport import BASE_NS, FIXTURE_MEDIA, FIXTURE_TOKEN
from aeromaint_api.main import app
from aeromaint_api.security.auth import create_development_token

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {create_development_token(['viewer'])}"}


def _read_arrow(body: bytes) -> pa.Table:
    return pa.ipc.open_stream(body).read_all()


def test_arrow_round_trip_preserves_contract_metadata_nulls_and_int64() -> None:
    response = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/imu-main/samples/arrow",
        headers=AUTH,
        params={"start_ns": BASE_NS, "end_ns": BASE_NS + 20_000_000},
    )

    assert response.status_code == 200
    table = _read_arrow(response.content)
    assert table.schema.field("timestamp_ns").type == pa.int64()
    assert table.schema.field("timestamp_ns").metadata == {b"unit": b"ns"}
    assert table.schema.field("ax").metadata == {b"unit": b"m/s^2"}
    assert table.column("ax").null_count == 1
    assert table.schema.metadata[b"aeromaint.stream_id"] == b"imu-main"
    assert table.schema.metadata[b"aeromaint.schema_version"] == b"1.0.0"
    assert table.schema.metadata[b"aeromaint.provenance.source_uri"].startswith(b"aeromaint://")
    assert response.headers["x-aeromaint-downsampling"] == "raw"


def test_documented_downsampling_preserves_endpoints_and_metadata() -> None:
    response = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/imu-main/samples/arrow",
        headers=AUTH,
        params={
            "start_ns": BASE_NS,
            "end_ns": BASE_NS + 200_000_000,
            "max_points": 5,
        },
    )

    table = _read_arrow(response.content)
    assert table.num_rows == 5
    assert table.column("timestamp_ns").to_pylist() == [
        BASE_NS + offset for offset in (0, 50_000_000, 100_000_000, 150_000_000, 200_000_000)
    ]
    metadata = table.schema.metadata
    assert metadata[b"aeromaint.downsampling.mode"] == b"downsampled"
    assert metadata[b"aeromaint.downsampling.algorithm"] == (b"endpoint-preserving-even-spacing-v1")
    assert metadata[b"aeromaint.downsampling.input_sample_count"] == b"41"


def test_frame_index_exposes_byte_lookup_and_decodable_keyframe_timestamp() -> None:
    response = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/camera-left/frames",
        headers=AUTH,
        params={"start_ns": BASE_NS + 100_000_000},
    )

    assert response.status_code == 200
    frames = response.json()["frames"]
    assert frames[0] == {
        "frame_number": 2,
        "presentation_ns": str(BASE_NS + 100_000_000),
        "byte_offset": 22,
        "byte_length": 11,
        "keyframe": False,
        "decodable_from_ns": str(BASE_NS),
    }
    assert frames[-1]["decodable_from_ns"] == frames[-1]["presentation_ns"]
    assert client.get(response.request.url, headers=AUTH).json() == response.json()


def test_media_requires_auth_and_honors_ranges_etag_and_immutable_cache() -> None:
    url = f"/v1/sessions/{FIXTURE_SESSION_ID}/media/camera-left-media"
    assert client.get(url).status_code == 401

    headers = {"Authorization": f"Bearer {FIXTURE_TOKEN}"}
    full = client.get(url, headers=headers)
    assert full.status_code == 200
    assert full.content == FIXTURE_MEDIA
    assert full.headers["accept-ranges"] == "bytes"
    assert "immutable" in full.headers["cache-control"]

    partial = client.get(url, headers={**headers, "Range": "bytes=11-21"})
    assert partial.status_code == 206
    assert partial.content == FIXTURE_MEDIA[11:22]
    assert partial.headers["content-range"] == f"bytes 11-21/{len(FIXTURE_MEDIA)}"
    assert partial.headers["etag"] == full.headers["etag"]

    cached = client.get(url, headers={**headers, "If-None-Match": full.headers["etag"]})
    assert cached.status_code == 304
    invalid = client.get(url, headers={**headers, "Range": "bytes=999-1000"})
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == f"bytes */{len(FIXTURE_MEDIA)}"
