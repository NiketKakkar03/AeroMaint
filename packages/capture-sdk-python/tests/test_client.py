from __future__ import annotations

import io
import json
import socket
import unittest
from threading import Event
from urllib.error import HTTPError, URLError

from aeromaint_capture import CaptureClient, CaptureError, CaptureHttpError


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def response(value: object) -> Response:
    return Response(json.dumps(value).encode())


class QueueOpener:
    def __init__(self, *results: object):
        self.results = list(results)
        self.calls: list[tuple[object, float]] = []

    def __call__(self, request, *, timeout: float):
        self.calls.append((request, timeout))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class CaptureClientTests(unittest.TestCase):
    def test_sessions_pagination_bigints_and_auth(self):
        opener = QueueOpener(
            response({"items": [{"id": "a", "start_ns": "9007199254740993", "end_ns": "9007199254740994"}], "next_cursor": "c2"}),
            response({"items": [{"id": "b", "start_ns": "2", "end_ns": "3"}]}),
        )
        client = CaptureClient("https://api.test/", token="secret", opener=opener)
        sessions = list(client.iter_sessions(page_size=1, max_items=2))
        self.assertEqual([item.id for item in sessions], ["a", "b"])
        self.assertEqual(sessions[0].start_ns, 9_007_199_254_740_993)
        first = opener.calls[0][0]
        self.assertIn("limit=1", first.full_url)
        self.assertEqual(first.get_header("Authorization"), "Bearer secret")

    def test_typed_imu_window_preserves_extra_values(self):
        opener = QueueOpener(response({
            "items": [{"timestamp_ns": "9007199254740993", "values": {"ax": 1, "ay": 2.5, "az": "3", "temperature": 4}}],
            "range": {"start_ns": "9007199254740993", "end_ns": "9007199254740994"},
            "schema_ref": "aeromaint://schemas/imu/1.0.0",
            "next_cursor": "next",
        }))
        window = CaptureClient("https://api.test", opener=opener).get_imu_window("s/1", "imu/main", start_ns=1, end_ns=2)
        self.assertEqual(window.start_ns, 9_007_199_254_740_993)
        self.assertEqual((window.samples[0].ax, window.samples[0].ay, window.samples[0].az), (1.0, 2.5, 3.0))
        self.assertEqual(window.samples[0].values["temperature"], 4)
        self.assertIn("/sessions/s%2F1/streams/imu%2Fmain/samples", opener.calls[0][0].full_url)

    def test_retries_transport_and_retryable_http(self):
        http = HTTPError("https://api.test", 503, "busy", {"Retry-After": "0"}, io.BytesIO(b'{"code":"BUSY","detail":"try later","request_id":"r1"}'))
        opener = QueueOpener(http, URLError(socket.timeout("slow")), response({"items": []}))
        page = CaptureClient("https://api.test", opener=opener, backoff=0, max_attempts=3).list_sessions()
        self.assertEqual(page.items, ())
        self.assertEqual(len(opener.calls), 3)

    def test_structured_non_retryable_error(self):
        error = HTTPError("https://api.test", 404, "missing", {}, io.BytesIO(b'{"code":"NOT_FOUND","detail":"gone","trace_id":"t1"}'))
        with self.assertRaises(CaptureHttpError) as caught:
            CaptureClient("https://api.test", opener=QueueOpener(error)).list_sessions()
        self.assertEqual((caught.exception.status, caught.exception.code, caught.exception.problem.trace_id), (404, "NOT_FOUND", "t1"))
        self.assertFalse(caught.exception.retryable)

    def test_cancellation_timeout_and_validation(self):
        cancelled = Event(); cancelled.set()
        opener = QueueOpener(response({"items": []}))
        client = CaptureClient("https://api.test", opener=opener, timeout=0.25)
        with self.assertRaisesRegex(CaptureError, "cancelled"):
            client.list_sessions(cancel=cancelled)
        self.assertEqual(opener.calls, [])
        with self.assertRaises(ValueError):
            client.list_sessions(limit=0)
        client.list_sessions()
        self.assertEqual(opener.calls[0][1], 0.25)

    def test_invalid_imu_is_a_typed_response_error(self):
        client = CaptureClient("https://api.test", opener=QueueOpener(response({"items": [{"timestamp_ns": "1", "values": {"ax": 1}}]})))
        with self.assertRaises(CaptureError) as caught:
            client.get_imu_window("s", "imu", start_ns=1, end_ns=2)
        self.assertEqual(caught.exception.code, "INVALID_RESPONSE")


if __name__ == "__main__":
    unittest.main()
