"""Talks to the host-side print helper (host/print_server.py).

Bluetooth needs the host's system D-Bus, which app containers can't reach, so the actual
printing happens in a small service on the board itself.
"""

import json
import logging
import os
import urllib.error
import urllib.request

from . import config

logger = logging.getLogger(__name__)
PORT = 8765


def _default_gateway() -> str | None:
    """The docker host as seen from the container: the default route's gateway."""
    try:
        with open("/proc/net/route") as f:
            next(f)
            for line in f:
                fields = line.split()
                if fields[1] == "00000000":
                    raw = bytes.fromhex(fields[2])[::-1]
                    return ".".join(str(b) for b in raw)
    except (OSError, ValueError, IndexError, StopIteration):
        pass
    return None


def _base_url(cfg: dict) -> str:
    url = cfg["printer"]["helper_url"]
    if url:
        return url.rstrip("/")
    return f"http://{_default_gateway() or '172.17.0.1'}:{PORT}"


def _request(cfg: dict, method: str, path: str, body: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(_base_url(cfg) + path, data=body, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if cfg["printer"]["helper_token"]:
        req.add_header("Authorization", f"Bearer {cfg['printer']['helper_token']}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except ValueError:
            return {"state": "error", "message": f"Print helper error {e.code}"}
    except OSError as e:
        logger.warning("print helper unreachable: %s", e)
        return {
            "state": "error",
            "message": "Can't reach the print helper on the board. Is the instax-print service running? (see README)",
        }


def start_print(jpeg: bytes, cfg: dict) -> dict:
    p = cfg["printer"]
    return _request(
        cfg,
        "POST",
        "/print",
        jpeg,
        {"Content-Type": "image/jpeg", "X-Device-Name": p["device_name"], "X-Device-Address": p["device_address"]},
    )


def status() -> dict:
    return _request(config.load(), "GET", "/status")
