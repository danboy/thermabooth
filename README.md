# Instax Photobooth

Touch-screen photobooth for the Arduino UNO Q. Take 4 photos, pick a filter, layout, frame and caption, then email, text or print them on a mini thermal printer (e.g. Huijuchen mini thermal printer).

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

Bluetooth needs the board's system D-Bus, which app containers can't reach. So printing is done by a small helper service that runs on the board itself; the app sends it the finished photo over HTTP (port 8765).

Install it once, on the board, from this app's folder:

```
sudo ./host/install.sh
```

This creates a venv in `host/.venv`, installs `bleak`, and enables a `thermal-print` systemd service. Check it with `systemctl status thermal-print` and `journalctl -u thermal-print -f`.

Then turn the printer on and keep it within a couple of meters of the board. The final photo is resized to 384 dots wide (58mm paper at 203dpi), Floyd-Steinberg dithered to black/white, and sent using the vendored `python/catprinter_ble/` (adapted from [rbaron/catprinter](https://github.com/rbaron/catprinter), MIT) — the reverse-engineered "cat printer" BLE protocol shared by cheap thermal printers like the Huijuchen mini thermal printer (also sold as GB01/GB02/GB03, GT01, X5/X6/X7, and other rebrands). Leave `PRINTER_DEVICE_NAME` blank to autodiscover by BLE service UUID, or set it if you know the printer's advertised name. `PRINTER_ENERGY` controls darkness (`0x0000`-`0xffff`, default darkest).

The helper listens on all interfaces. To restrict it, set the same `PRINT_HELPER_TOKEN` in `.env` (both the app and the helper read it).

## Privacy

Photos are stored in `data/sessions/` and deleted after `KEEP_SESSIONS_HOURS` (default 24). Empty `data/` and remove `.env` before sharing this app. `.env` is read on every request, so edits apply without a restart.
