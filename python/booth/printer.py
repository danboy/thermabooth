"""Thermal printing over Bluetooth LE, for the Huijuchen mini thermal printer and other
"cat printer" protocol clones (GB01/GB02/GB03, GT01, X5/X6/X7, ...)."""

import io
import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_status = {"state": "idle", "message": ""}


def status() -> dict:
    return dict(_status)


def _set(state: str, message: str = "") -> None:
    _status["state"] = state
    _status["message"] = message


def start_print(jpeg: bytes, printer_cfg: dict) -> bool:
    """Kick off a background print. Returns False if a job is already running."""
    if not _lock.acquire(blocking=False):
        return False
    _set("connecting", "Looking for the printer...")
    threading.Thread(target=_run, args=(jpeg, printer_cfg), daemon=True).start()
    return True


def _bitmap_rows(jpeg: bytes, width: int):
    from PIL import Image

    img = Image.open(io.BytesIO(jpeg)).convert("L")
    w, h = img.size
    new_h = max(1, round(h * width / w))
    img = img.resize((width, new_h), Image.LANCZOS)
    bw = img.convert("1", dither=Image.FLOYDSTEINBERG)
    data = list(bw.getdata())
    for y in range(new_h):
        row = data[y * width : (y + 1) * width]
        yield [px == 0 for px in row]  # mode "1": 0 = black


def _run(jpeg: bytes, cfg: dict) -> None:
    try:
        try:
            from catprinter_ble import cmds
            from catprinter_ble.ble import print_sync
        except ImportError as e:
            raise RuntimeError(f"Printing library missing ({e}). Re-run host/install.sh to install bleak and pillow.") from e

        _set("printing", "Rendering photo for the printer...")
        rows = list(_bitmap_rows(jpeg, cmds.PRINT_WIDTH))
        energy = int(cfg.get("energy") or 0xFFFF)
        data = cmds.cmds_print_img(rows, energy=energy)

        _set("connecting", "Looking for the printer...")
        print_sync(data, cfg.get("device_name"), cfg.get("device_address"))

        _set("done", "Done! Grab your print.")
    except Exception as e:
        logger.exception("Print failed")
        _set("error", str(e))
    finally:
        _lock.release()
