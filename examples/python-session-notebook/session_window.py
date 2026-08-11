"""Minimal script/notebook cell using only the installed public Python SDK."""

import os

from aeromaint_capture import CaptureClient

client = CaptureClient(
    os.environ.get("AEROMAINT_API_URL", "http://localhost:8000"),
    token=os.environ.get("AEROMAINT_TOKEN"),
)
session = next(client.iter_sessions(max_items=1))
stream = next(item for item in client.list_streams(session.id).items if item.kind == "imu")
window = client.get_sensor_window(
    session.id,
    stream.id,
    start_ns=stream.start_ns,
    end_ns=min(stream.start_ns + 1_000_000_000, stream.end_ns),
)
for sample in window.samples:
    print(sample.timestamp_ns, sample.values)
