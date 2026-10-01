#!/usr/bin/env bash
# Installs the thermal print helper as a systemd service on the board. Run once with sudo:
#   sudo ./host/install.sh
set -euo pipefail

HOST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-$(id -un)}"

# USB vendor/product ID for the Sunydog printer (and other "CLA58"-chipset rebrands). It's a
# vendor-specific USB device, not the USB Printer Class, so it needs libusb/pyusb rather than
# a /dev/usb/lp* device file - which in turn needs a udev rule to grant non-root access.
VENDOR_ID="6868"
PRODUCT_ID="0200"

apt-get install -y python3-venv libusb-1.0-0 >/dev/null
sudo -u "$APP_USER" python3 -m venv "$HOST_DIR/.venv"
sudo -u "$APP_USER" "$HOST_DIR/.venv/bin/pip" install --quiet "python-escpos[usb]" pillow

cat > /etc/udev/rules.d/99-thermal-printer.rules <<RULES
SUBSYSTEM=="usb", ATTR{idVendor}=="$VENDOR_ID", ATTR{idProduct}=="$PRODUCT_ID", MODE="0666", GROUP="plugdev"
RULES
udevadm control --reload-rules
udevadm trigger
usermod -aG plugdev "$APP_USER"

cat > /etc/systemd/system/thermal-print.service <<UNIT
[Unit]
Description=Thermal photobooth print helper
After=network.target

[Service]
User=$APP_USER
ExecStart=$HOST_DIR/.venv/bin/python $HOST_DIR/print_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now thermal-print.service
systemctl --no-pager status thermal-print.service | head -5
