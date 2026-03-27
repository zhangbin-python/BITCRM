#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bitcrm}"
SERVICE_NAME="${SERVICE_NAME:-bitcrm}"
APP_USER="${APP_USER:-bitcrm}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGED_DB="${SCRIPT_DIR}/migration-data/bitcrm.db"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run this script with sudo, for example: sudo bash deploy_with_data.sh"
    exit 1
fi

if [[ ! -f "${PACKAGED_DB}" ]]; then
    echo "Packaged database not found: ${PACKAGED_DB}"
    exit 1
fi

echo "[1/4] Deploying application files..."
APP_DIR="${APP_DIR}" APP_USER="${APP_USER}" SERVICE_NAME="${SERVICE_NAME}" bash "${SCRIPT_DIR}/deploy.sh"

echo "[2/4] Stopping service before restoring database..."
systemctl stop "${SERVICE_NAME}"

mkdir -p "${APP_DIR}/instance"

if [[ -f "${APP_DIR}/instance/bitcrm.db" ]]; then
    backup_path="${APP_DIR}/instance/bitcrm.db.bak.$(date +%Y%m%d-%H%M%S)"
    echo "[3/4] Backing up existing database to ${backup_path}..."
    cp "${APP_DIR}/instance/bitcrm.db" "${backup_path}"
else
    echo "[3/4] No existing database found, skipping backup..."
fi

echo "[4/4] Restoring packaged database and restarting service..."
cp "${PACKAGED_DB}" "${APP_DIR}/instance/bitcrm.db"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}/instance/bitcrm.db"
chmod 640 "${APP_DIR}/instance/bitcrm.db"
systemctl restart "${SERVICE_NAME}"

echo
echo "BITCRM has been deployed with the packaged database."
echo "Open: http://<your-ubuntu-ip>:8000"
echo "Check logs with: sudo journalctl -u ${SERVICE_NAME} -f"
