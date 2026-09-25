"""Email (Mailgun) and SMS (Twilio) delivery."""

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match(addr or "")) and len(addr) < 255


def normalize_phone(raw: str) -> str | None:
    """Return E.164 or None. Bare 10-digit numbers are assumed to be US/Canada."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("+") and 8 <= len(digits) - 1 <= 15:
        return digits
    digits = digits.lstrip("+")
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def _multipart(fields: list[tuple[str, str]], files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "----photobooth" + uuid.uuid4().hex
    out = bytearray()
    for name, value in fields:
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    for field, filename, data in files:
        out += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode() + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def send_email(cfg: dict, to: str, final_jpg: bytes, singles: list[bytes], link: str) -> None:
    m = cfg["mailgun"]
    host = "api.eu.mailgun.net" if m["region"] == "eu" else "api.mailgun.net"
    sender = m["from"] or f"Photobooth <photobooth@{m['domain']}>"
    fields = [
        ("from", sender),
        ("to", to),
        ("subject", "Your photobooth pictures!"),
        ("text", f"Thanks for stopping by the photobooth! Your pictures are attached.\n\nOr grab them here: {link}\n"),
    ]
    files = [("attachment", "photobooth.jpg", final_jpg)]
    files += [("attachment", f"photo-{i}.jpg", jpg) for i, jpg in enumerate(singles, 1)]
    body, content_type = _multipart(fields, files)

    req = urllib.request.Request(f"https://{host}/v3/{m['domain']}/messages", data=body, method="POST")
    req.add_header("Content-Type", content_type)
    token = base64.b64encode(f"api:{m['api_key']}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Mailgun error {e.code}: {e.read().decode(errors='replace')[:200]}") from e


def send_sms(cfg: dict, to: str, link: str) -> None:
    t = cfg["twilio"]
    url = f"https://api.twilio.com/2010-04-01/Accounts/{t['account_sid']}/Messages.json"
    body = urllib.parse.urlencode({"To": to, "From": t["from"], "Body": f"Your photobooth pictures: {link}"}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    token = base64.b64encode(f"{t['account_sid']}:{t['auth_token']}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Twilio error {e.code}: {e.read().decode(errors='replace')[:200]}") from e
