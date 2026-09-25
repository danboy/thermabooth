"""Email (SMTP) and SMS (Twilio) delivery."""

import base64
import json
import re
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

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


def send_email(cfg: dict, to: str, final_jpg: bytes, singles: list[bytes], link: str) -> None:
    s = cfg["smtp"]
    msg = EmailMessage()
    msg["Subject"] = "Your photobooth pictures!"
    msg["From"] = s["from"]
    msg["To"] = to
    msg.set_content(f"Thanks for stopping by the photobooth! Your pictures are attached.\n\nOr grab them here: {link}\n")
    msg.add_attachment(final_jpg, maintype="image", subtype="jpeg", filename="photobooth.jpg")
    for i, jpg in enumerate(singles, 1):
        msg.add_attachment(jpg, maintype="image", subtype="jpeg", filename=f"photo-{i}.jpg")

    with smtplib.SMTP(s["host"], int(s["port"]), timeout=30) as smtp:
        if s.get("starttls", True):
            smtp.starttls()
        if s["username"]:
            smtp.login(s["username"], s["password"])
        smtp.send_message(msg)


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
