"""Fujifilm Instax Mini Link printing over Bluetooth LE (via the vendored InstaxBLE)."""

import io
import logging
import threading
import time

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


def _run(jpeg: bytes, cfg: dict) -> None:
    instax = None
    try:
        try:
            from instax_ble.InstaxBLE import InstaxBLE
        except ImportError as e:
            raise RuntimeError(f"Bluetooth printing library missing ({e}). Is simplepyble installed?") from e

        try:
            instax = InstaxBLE(
                device_name=cfg.get("device_name") or None,
                device_address=cfg.get("device_address") or None,
                print_enabled=True,
                quiet=True,
            )
        except SystemExit:  # InstaxBLE exits when no adapter exists
            raise RuntimeError("No Bluetooth adapter found on the board.")

        instax.connect(timeout=25)
        if not instax.peripheral or not instax.peripheral.is_connected():
            raise RuntimeError("Printer not found. Turn it on and keep it close.")
        if instax.photosLeft == 0:
            raise RuntimeError("Printer is out of film.")

        _set("printing", "Sending photo to the printer...")
        instax.print_image(io.BytesIO(jpeg))

        deadline = time.time() + 120
        while instax.packetsForPrinting and time.time() < deadline:
            time.sleep(0.5)
        if instax.packetsForPrinting:
            raise RuntimeError("Timed out sending the photo to the printer.")
        _set("printing", "Printing... your photo is on its way out!")
        time.sleep(20)  # keep the link up while the printer works
        _set("done", "Done! Grab your print.")
    except Exception as e:
        logger.exception("Print failed")
        _set("error", str(e))
    finally:
        try:
            if instax is not None:
                instax.disconnect()
        except Exception:
            pass
        _lock.release()
