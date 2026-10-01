#!/usr/bin/env python3
"""Thermal print helper. Runs on the board's host OS (not in the app container), which has no
SDK peripheral for a generic USB device. The photobooth app POSTs finished JPEGs to it.

    POST /print   body: image/jpeg   headers: X-Device-Vendor-Id, X-Device-Product-Id (optional)
    GET  /status
"""

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR / "python"))

from booth import config, printer  # noqa: E402

MAX_BYTES = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        token = config.load()["printer"]["helper_token"]
        return not token or self.headers.get("Authorization") == f"Bearer {token}"

    def do_GET(self):
        if not self._authorized():
            return self._send(401, {"state": "error", "message": "Unauthorized"})
        if self.path == "/status":
            return self._send(200, printer.status())
        self._send(404, {"state": "error", "message": "Not found"})

    def do_POST(self):
        if self.path != "/print":
            return self._send(404, {"state": "error", "message": "Not found"})
        if not self._authorized():
            return self._send(401, {"state": "error", "message": "Unauthorized"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BYTES:
            return self._send(400, {"state": "error", "message": "Bad image size"})
        jpeg = self.rfile.read(length)
        if not jpeg.startswith(b"\xff\xd8"):
            return self._send(400, {"state": "error", "message": "Not a JPEG"})
        cfg = {
            "vendor_id": self.headers.get("X-Device-Vendor-Id", ""),
            "product_id": self.headers.get("X-Device-Product-Id", ""),
        }
        if not printer.start_print(jpeg, cfg):
            return self._send(409, {"state": "error", "message": "The printer is busy, try again in a minute"})
        self._send(200, printer.status())

    def log_message(self, fmt, *args):
        sys.stderr.write("print-helper: " + fmt % args + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    print(f"Thermal print helper listening on {args.bind}:{args.port}", flush=True)
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
