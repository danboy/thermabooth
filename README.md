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

This creates a venv in `host/.venv`, installs `python-escpos`, adds the service user to the `lp` group (so it can write to the printer's device node without root), and enables a `thermal-print` systemd service. Check it with `systemctl status thermal-print` and `journalctl -u thermal-print -f`.

Plug the printer into the board over USB and turn it on; it should show up as `/dev/usb/lp0`. The final photo is resized to 384 dots wide (58mm paper at 203dpi), Floyd-Steinberg dithered to black/white, and sent as standard ESC/POS commands via [python-escpos](https://github.com/python-escpos/python-escpos) — this works with the Sunydog mini thermal receipt printer and most other generic 58mm USB receipt printers.

If the printer enumerates at a different path, set `PRINTER_DEVICE_PATH` in `.env` (check with `ls /dev/usb/`).

The helper listens on all interfaces. To restrict it, set the same `PRINT_HELPER_TOKEN` in `.env` (both the app and the helper read it).

## Privacy

Photos are stored in `data/sessions/` and deleted after `KEEP_SESSIONS_HOURS` (default 24). Empty `data/` and remove `.env` before sharing this app. `.env` is read on every request, so edits apply without a restart.
