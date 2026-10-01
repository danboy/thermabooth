# Instax Photobooth

Touch-screen photobooth for the Arduino UNO Q. Take 4 photos, pick a filter, layout, frame and caption, then email, text or print them on a mini thermal printer (e.g. Sunydog mini thermal receipt printer).

## Setup

1. Plug a USB camera into the board.
2. Copy `.env.example` to `.env` (app root) and fill in what you need:
   - `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` (and optionally `MAILGUN_FROM`, `MAILGUN_REGION=eu`): enables **Email me**. Mailgun sandbox domains only deliver to authorized recipients.
   - `TWILIO_*`: enables **Text me**. The text contains a link to the photos.
   - `PUBLIC_BASE_URL`: optional. Link phones use to reach the board, for example `http://192.168.1.50:7000`. If empty, the board's LAN IP is used.
   - `PRINTER_ENABLED=false` hides printing.
3. Run the app in App Lab, then open `http://<board-ip>:7000` on the touch screen (full-screen the browser for kiosk use).

Buttons only show for features you configured. **Scan with phone** (QR code) always works and needs no credentials, but the phone must be on the same network as the board.

## Printing

The app container has no SDK peripheral for a generic USB device (only camera/mic/speaker/remote_sensor), so printing is done by a small helper service that runs on the board's host OS; the app sends it the finished photo over HTTP (port 8765).

Install it once, on the board, from this app's folder:

```
sudo ./host/install.sh
```

This creates a venv in `host/.venv`, installs `python-escpos` + `pyusb`, adds a udev rule granting non-root USB access to the printer, and enables a `thermal-print` systemd service. Check it with `systemctl status thermal-print` and `journalctl -u thermal-print -f`.

Plug the printer into the board over USB and turn it on. The Sunydog printer (and other "CLA58"-chipset rebrands) enumerates as a vendor-specific USB device rather than the USB Printer Class, so it won't show up as `/dev/usb/lp0` — the helper talks to it directly over libusb instead, using its USB vendor/product ID (`6868:0200` by default). The final photo is resized to 384 dots wide (58mm paper at 203dpi), Floyd-Steinberg dithered to black/white, and sent as standard ESC/POS commands via [python-escpos](https://github.com/python-escpos/python-escpos).

If you have a different printer, find its IDs with `lsusb` and set `PRINTER_USB_VENDOR_ID` / `PRINTER_USB_PRODUCT_ID` in `.env` (and re-run `host/install.sh` so the udev rule covers it too).

The helper listens on all interfaces. To restrict it, set the same `PRINT_HELPER_TOKEN` in `.env` (both the app and the helper read it).

## Privacy

Photos are stored in `data/sessions/` and deleted after `KEEP_SESSIONS_HOURS` (default 24). Empty `data/` and remove `.env` before sharing this app. `.env` is read on every request, so edits apply without a restart.
