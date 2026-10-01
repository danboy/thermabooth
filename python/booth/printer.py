"""Thermal printing over USB (ESC/POS), for the Sunydog mini thermal receipt printer and
other generic 58mm USB receipt printers that show up as a /dev/usb/lp* device."""

import io
import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_status = {"state": "idle", "message": ""}

PRINT_WIDTH = 384  # 58mm paper at 203dpi


def status() -> dict:
    return dict(_status)


def _set(state: str, message: str = "") -> None:
    _status["state"] = state
    _status["message"] = message


def start_print(jpeg: bytes, printer_cfg: dict) -> bool:
    """Kick off a background print. Returns False if a job is already running."""
    if not _lock.acquire(blocking=False):
        return False
    _set("printing", "Rendering photo for the printer...")
    threading.Thread(target=_run, args=(jpeg, printer_cfg), daemon=True).start()
    return True


def _dithered_image(jpeg: bytes, width: int):
    from PIL import Image

    img = Image.open(io.BytesIO(jpeg)).convert("L")
    w, h = img.size
    new_h = max(1, round(h * width / w))
    img = img.resize((width, new_h), Image.LANCZOS)
    return img.convert("1", dither=Image.FLOYDSTEINBERG)


def _run(jpeg: bytes, cfg: dict) -> None:
    try:
        try:
            from escpos.printer import File
        except ImportError as e:
            raise RuntimeError(f"Printing library missing ({e}). Re-run host/install.sh to install python-escpos and pillow.") from e

        img = _dithered_image(jpeg, PRINT_WIDTH)

        device_path = cfg.get("device_path") or "/dev/usb/lp0"
        _set("printing", "Sending photo to the printer...")
        try:
            p = File(devfile=device_path)
            p.image(img)
            p.cut()
            p.close()
        except OSError as e:
            raise RuntimeError(f"Can't reach the printer at {device_path}. Is it plugged in and turned on?") from e

        _set("done", "Done! Grab your print.")
    except Exception as e:
        logger.exception("Print failed")
        _set("error", str(e))
    finally:
        _lock.release()
