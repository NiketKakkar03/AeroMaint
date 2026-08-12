"""Dependency-free health and metrics endpoint for bounded local profile workers."""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE, PORT, VERSION = sys.argv[1], int(sys.argv[2]), sys.argv[3]
STARTED = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/health/live", "/health/ready", "/version"}:
            body = json.dumps({"status": "ok", "service": SERVICE, "version": VERSION}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/metrics":
            body = (
                f'aeromaint_service_up{{service="{SERVICE}",version="{VERSION}"}} 1\n'
                f'aeromaint_service_uptime_seconds{{service="{SERVICE}"}} '
                f"{time.monotonic() - STARTED:.3f}\n"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        else:
            body = b'{"error":"not_found"}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(json.dumps({"event": "http_request", "service": SERVICE, "path": self.path}))

    def log_message(self, format: str, *args: object) -> None:
        return


print(json.dumps({"event": "service_started", "service": SERVICE, "version": VERSION}))
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()  # noqa: S104
