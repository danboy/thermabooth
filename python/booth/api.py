"""REST API for the photobooth UI. Registered onto a WebUI brick by main.py."""

import io
import json
import logging
import re
import secrets
import shutil
import socket
import time
from pathlib import Path

import segno
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image
from pydantic import BaseModel

from . import config, delivery, imaging, print_client

logger = logging.getLogger(__name__)

SID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


class CaptureBody(BaseModel):
    slot: int


class RenderBody(BaseModel):
    filter: str = "none"
    layout: str = "grid"
    frame: str = "white"
    caption: str = ""


class ToBody(BaseModel):
    to: str


def _jpeg(data: bytes) -> Response:
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def _session_dir(sid: str) -> Path:
    if not SID_RE.match(sid):
        raise HTTPException(400, "bad session id")
    d = config.SESSIONS_DIR / sid
    if not d.is_dir():
        raise HTTPException(404, "unknown session")
    return d


def _photo_paths(d: Path) -> list[Path]:
    return sorted(d.glob("raw_*.jpg"))


def _load_photos(d: Path, need: int) -> list[Image.Image]:
    paths = [d / f"raw_{i}.jpg" for i in range(need)]
    if not all(p.exists() for p in paths):
        raise HTTPException(409, "not all photos taken yet")
    return [Image.open(p).convert("RGB") for p in paths]


def _settings(d: Path) -> RenderBody:
    try:
        return RenderBody(**json.loads((d / "settings.json").read_text()))
    except (OSError, ValueError):
        return RenderBody()


def _render(d: Path, s: RenderBody, need: int) -> Image.Image:
    if s.filter not in imaging.FILTERS or s.layout not in imaging.LAYOUTS or s.frame not in imaging.FRAMES:
        raise HTTPException(400, "unknown filter, layout or frame")
    final = imaging.compose(_load_photos(d, need), s.filter, s.layout, s.frame, s.caption[:80])
    (d / "final.jpg").write_bytes(imaging.to_jpeg(final))
    (d / "settings.json").write_text(s.model_dump_json())
    return final


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _share_link(cfg: dict, request: Request, sid: str) -> str:
    base = cfg["public_base_url"].rstrip("/")
    if not base:
        host = request.headers.get("host", "")
        if not host or host.startswith(("localhost", "127.", "[::1]")):
            port = request.url.port or 7000
            host = f"{lan_ip()}:{port}"
        base = f"{request.url.scheme}://{host}"
    return f"{base}/share/{sid}"


def _prune(hours: float) -> None:
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - hours * 3600
    for d in config.SESSIONS_DIR.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _ensure_started(camera) -> None:
    started = camera.is_started
    if callable(started):  # a method in some brick versions, a property in others
        started = started()
    if not started:
        camera.start()


def register(web_ui, camera) -> None:
    api = web_ui.expose_api

    def status():
        cfg = config.load()
        return {
            "email": config.email_enabled(cfg),
            "sms": config.sms_enabled(cfg),
            "printer": bool(cfg["printer"]["enabled"]),
            "photos": int(cfg["photos_per_session"]),
            "countdown": int(cfg["countdown_seconds"]),
            "filters": imaging.FILTERS,
            "layouts": imaging.LAYOUTS,
            "frames": list(imaging.FRAMES),
        }

    def new_session():
        cfg = config.load()
        _prune(float(cfg["keep_sessions_hours"]))
        sid = secrets.token_urlsafe(8)
        (config.SESSIONS_DIR / sid).mkdir(parents=True)
        return {"id": sid}

    def capture(sid: str, body: CaptureBody):
        d = _session_dir(sid)
        n = int(config.load()["photos_per_session"])
        if not 0 <= body.slot < n:
            raise HTTPException(400, "bad slot")
        try:
            _ensure_started(camera)
        except Exception as e:
            logger.exception("camera start failed")
            raise HTTPException(503, f"camera unavailable: {e}")
        frame = None
        for _ in range(20):
            frame = camera.capture()
            if frame is not None:
                break
            time.sleep(0.1)
        if frame is None:
            raise HTTPException(503, "camera not ready")
        img = Image.fromarray(frame[..., ::-1] if frame.ndim == 3 else frame).convert("RGB")  # OpenCV BGR -> RGB
        img.save(d / f"raw_{body.slot}.jpg", "JPEG", quality=92)
        (d / "final.jpg").unlink(missing_ok=True)
        return {"slot": body.slot}

    def photo(sid: str, slot: int):
        p = _session_dir(sid) / f"raw_{slot}.jpg"
        if not p.exists():
            raise HTTPException(404)
        return _jpeg(p.read_bytes())

    def filter_thumb(sid: str, name: str):
        if name not in imaging.FILTERS:
            raise HTTPException(400)
        p = _session_dir(sid) / "raw_0.jpg"
        if not p.exists():
            raise HTTPException(404)
        return _jpeg(imaging.thumbnail(Image.open(p).convert("RGB"), name))

    def render(sid: str, body: RenderBody):
        d = _session_dir(sid)
        _render(d, body, int(config.load()["photos_per_session"]))
        return {"ok": True}

    def final(sid: str):
        p = _session_dir(sid) / "final.jpg"
        if not p.exists():
            raise HTTPException(404)
        return _jpeg(p.read_bytes())

    def _ensure_final(d: Path) -> bytes:
        p = d / "final.jpg"
        if not p.exists():
            _render(d, _settings(d), int(config.load()["photos_per_session"]))
        return p.read_bytes()

    def email(sid: str, request: Request, body: ToBody):
        cfg = config.load()
        d = _session_dir(sid)
        if not config.email_enabled(cfg):
            raise HTTPException(501, "Email is not configured")
        if not delivery.valid_email(body.to.strip()):
            raise HTTPException(400, "That email address doesn't look right")
        s = _settings(d)
        n = int(cfg["photos_per_session"])
        singles = [imaging.to_jpeg(imaging.apply_filter(p, s.filter)) for p in _load_photos(d, n)]
        try:
            delivery.send_email(cfg, body.to.strip(), _ensure_final(d), singles, _share_link(cfg, request, sid))
        except Exception as e:
            logger.exception("email failed")
            raise HTTPException(502, f"Couldn't send email: {e}")
        return {"ok": True}

    def sms(sid: str, request: Request, body: ToBody):
        cfg = config.load()
        d = _session_dir(sid)
        if not config.sms_enabled(cfg):
            raise HTTPException(501, "Text messages are not configured")
        phone = delivery.normalize_phone(body.to)
        if not phone:
            raise HTTPException(400, "That phone number doesn't look right")
        _ensure_final(d)
        try:
            delivery.send_sms(cfg, phone, _share_link(cfg, request, sid))
        except Exception as e:
            logger.exception("sms failed")
            raise HTTPException(502, str(e))
        return {"ok": True}

    def qr(sid: str, request: Request):
        d = _session_dir(sid)
        _ensure_final(d)
        buf = io.BytesIO()
        segno.make(_share_link(config.load(), request, sid), error="m").save(buf, kind="svg", scale=10, border=2)
        return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    def print_photo(sid: str):
        cfg = config.load()
        d = _session_dir(sid)
        if not cfg["printer"]["enabled"]:
            raise HTTPException(501, "Printing is disabled")
        s = _settings(d)
        _ensure_final(d)
        jpeg = imaging.to_jpeg(imaging.for_print(Image.open(d / "final.jpg"), s.layout, s.frame), 92)
        result = print_client.start_print(jpeg, cfg)
        if result.get("state") == "error":
            raise HTTPException(502, result.get("message", "Printing failed"))
        return result

    def print_status():
        return print_client.status()

    def share_page(sid: str):
        d = _session_dir(sid)
        _ensure_final(d)
        html = f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Your photobooth pictures</title>
<body style="margin:0;font-family:system-ui,sans-serif;background:#111;color:#fff;text-align:center;padding:16px">
<h2>Your pictures!</h2>
<img src="/api/session/{sid}/final.jpg" style="max-width:100%;border-radius:8px">
<p><a href="/api/session/{sid}/final.jpg" download="photobooth.jpg"
 style="display:inline-block;padding:14px 28px;border-radius:999px;background:#00979d;color:#fff;text-decoration:none;font-weight:600">Download</a></p>
</body>"""
        return HTMLResponse(html)

    api("GET", "/api/status", status)
    api("POST", "/api/session", new_session)
    api("POST", "/api/session/{sid}/capture", capture)
    api("GET", "/api/session/{sid}/photo/{slot}", photo)
    api("GET", "/api/session/{sid}/filter-thumb/{name}", filter_thumb)
    api("POST", "/api/session/{sid}/render", render)
    api("GET", "/api/session/{sid}/final.jpg", final)
    api("POST", "/api/session/{sid}/email", email)
    api("POST", "/api/session/{sid}/sms", sms)
    api("GET", "/api/session/{sid}/qr.svg", qr)
    api("POST", "/api/session/{sid}/print", print_photo)
    api("GET", "/api/print/status", print_status)
    api("GET", "/share/{sid}", share_page)
