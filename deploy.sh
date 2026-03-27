#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bitcrm}"
APP_USER="${APP_USER:-bitcrm}"
SERVICE_NAME="${SERVICE_NAME:-bitcrm}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run this script with sudo, for example: sudo bash deploy.sh"
    exit 1
fi

if [[ ! -f /etc/debian_version ]]; then
    echo "This deployment script currently supports Debian/Ubuntu only."
    exit 1
fi

echo "[1/7] Installing system packages..."
apt-get update
apt-get install -y python3 python3-pip python3-venv rsync

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    echo "[2/7] Creating service user ${APP_USER}..."
    useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
else
    echo "[2/7] Reusing existing service user ${APP_USER}..."
fi

echo "[3/7] Syncing application files to ${APP_DIR}..."
mkdir -p "${APP_DIR}"
rsync -a --delete \
    --exclude '.git/' \
    --exclude '.playwright-cli/' \
    --exclude '__pycache__/' \
    --exclude 'venv/' \
    --exclude 'dist/' \
    --exclude 'instance/' \
    --exclude 'logs/' \
    --exclude '.env' \
    --exclude '*.db' \
    --exclude '*.log' \
    "${SCRIPT_DIR}/" "${APP_DIR}/"

mkdir -p "${APP_DIR}/instance" "${APP_DIR}/logs"

if [[ ! -f "${APP_DIR}/.env" ]]; then
    echo "[4/7] Creating ${APP_DIR}/.env from template..."
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    secret_key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    sed -i "s|change-me-to-a-long-random-string|${secret_key}|" "${APP_DIR}/.env"
else
    echo "[4/7] Keeping existing ${APP_DIR}/.env..."
fi

echo "[5/7] Building Python virtual environment..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install --no-cache-dir -r "${APP_DIR}/requirements.txt"

echo "[6/7] Installing systemd service..."
tmp_service="$(mktemp)"
sed "s|__APP_DIR__|${APP_DIR}|g" "${APP_DIR}/bitcrm.service" > "${tmp_service}"
install -m 644 "${tmp_service}" "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "${tmp_service}"

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "[7/7] Starting service..."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo
echo "BITCRM has been deployed to ${APP_DIR}"
echo "Service status:"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
echo "Common commands:"
echo "  sudo systemctl restart ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  sudo journalctl -u ${SERVICE_NAME} -f"
