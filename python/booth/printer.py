"""Thermal printing over USB (ESC/POS), for the Sunydog mini thermal receipt printer and
other generic 58mm USB receipt printers built on the same vendor-specific USB chipset
(reports as a raw USB device, not the USB Printer Class - no /dev/usb/lp* node, so this
talks to it directly over libusb instead of a device file)."""

import io
import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_status = {"state": "idle", "message": ""}

PRINT_WIDTH = 384  # 58mm paper at 203dpi

# USB vendor/product ID for the Sunydog printer (and other "CLA58"-chipset rebrands).
DEFAULT_VENDOR_ID = 0x6868
DEFAULT_PRODUCT_ID = 0x0200


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
            from escpos.printer import Usb
            from usb.core import USBError
        except ImportError as e:
            raise RuntimeError(f"Printing library missing ({e}). Re-run host/install.sh to install python-escpos and pyusb.") from e

        img = _dithered_image(jpeg, PRINT_WIDTH)

        vendor_id = int(cfg.get("vendor_id") or DEFAULT_VENDOR_ID)
        product_id = int(cfg.get("product_id") or DEFAULT_PRODUCT_ID)
        _set("printing", "Sending photo to the printer...")
        try:
            p = Usb(vendor_id, product_id)
            p.image(img)
            p.cut()
            p.close()
        except USBError as e:
            raise RuntimeError(f"Can't reach the printer (USB {vendor_id:#06x}:{product_id:#06x}). Is it plugged in and turned on?") from e

        _set("done", "Done! Grab your print.")
    except Exception as e:
        logger.exception("Print failed")
        _set("error", str(e))
    finally:
        _lock.release()
