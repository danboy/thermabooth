#!/usr/bin/env bash
# Installs the thermal print helper as a systemd service on the board. Run once with sudo:
#   sudo ./host/install.sh
set -euo pipefail

HOST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-$(id -un)}"

apt-get install -y python3-venv bluez >/dev/null
sudo -u "$APP_USER" python3 -m venv "$HOST_DIR/.venv"
sudo -u "$APP_USER" "$HOST_DIR/.venv/bin/pip" install --quiet bleak pillow

cat > /etc/systemd/system/thermal-print.service <<UNIT
[Unit]
Description=Thermal photobooth print helper
After=bluetooth.target network.target
Wants=bluetooth.target

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
