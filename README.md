# Instax Photobooth

Touch-screen photobooth for the Arduino UNO Q. Take 4 photos, pick a filter, layout, frame and caption, then email, text or print them on a Fujifilm Instax Mini Link.

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

Turn the Instax Mini Link on and keep it within a couple of meters of the board. Photos print as 600x800 JPEGs over Bluetooth LE using the vendored [InstaxBLE](https://github.com/javl/InstaxBLE) (MIT, in `python/instax_ble/`). The strip layout prints two copies side by side.

## Privacy

Photos are stored in `data/sessions/` and deleted after `KEEP_SESSIONS_HOURS` (default 24). Empty `data/` and remove `.env` before sharing this app. `.env` is read on every request, so edits apply without a restart.
