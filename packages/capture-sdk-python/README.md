# AeroMaint Capture SDK for Python

Install the wheel and use `CaptureClient` against the versioned public API. The package has no runtime dependencies.

```python
from aeromaint_capture import CaptureClient

client = CaptureClient("http://localhost:8000", token="...")
for session in client.iter_sessions():
    print(session.id, session.start_ns)  # arbitrary-precision int
window = client.get_sensor_window("session", "imu", start_ns=0, end_ns=1_000_000_000)
```

Requests time out after 30 seconds and retry HTTP 408/429/5xx and transport failures three times. Override `timeout`, `max_attempts`, and `backoff` in the constructor. Pass a `threading.Event` as `cancel`; cancellation is checked before requests and during retry waits.

`CaptureHttpError` exposes `status`, `code`, `retryable`, and a structured `problem` containing the public API's request/trace IDs. `CaptureTransportError` represents exhausted network/timeout retries. Invalid local windows raise `ValueError`.
