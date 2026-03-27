# BITCRM Ubuntu Deployment Guide

This package is intended to be copied to Ubuntu with a USB drive and then deployed there.

## Recommended method: systemd deployment

### 1. Copy the release package to Ubuntu

Example:

```bash
mkdir -p ~/packages
cp /media/$USER/<USB_NAME>/BITCRM-ubuntu-*.zip ~/packages/
cd ~/packages
unzip BITCRM-ubuntu-*.zip
cd BITCRM-ubuntu-*
```

### 2. Run the deployment script

```bash
sudo bash deploy.sh
```

The script will:

- install Python and virtualenv
- copy the application to `/opt/bitcrm`
- create `/opt/bitcrm/.env`
- install Python dependencies
- register `bitcrm.service`
- start the service automatically

### 3. Open the service

After deployment, open:

- `http://<your-ubuntu-ip>:8000`

Check the service:

```bash
sudo systemctl status bitcrm
sudo journalctl -u bitcrm -f
```

## If you want to migrate existing data

This release package intentionally does not include your local database.

If you want to bring existing data to Ubuntu, copy the database separately with your USB drive:

```bash
sudo mkdir -p /opt/bitcrm/instance
sudo cp /media/$USER/<USB_NAME>/bitcrm.db /opt/bitcrm/instance/bitcrm.db
sudo chown bitcrm:bitcrm /opt/bitcrm/instance/bitcrm.db
sudo systemctl restart bitcrm
```

Your current Windows database is usually here:

- `instance/bitcrm.db`

## Alternative method: Docker

If Docker is already installed on Ubuntu:

```bash
cp .env.example .env
docker compose up -d --build
```

Then open:

- `http://<your-ubuntu-ip>:8080`

## Useful commands

```bash
sudo systemctl restart bitcrm
sudo systemctl stop bitcrm
sudo systemctl start bitcrm
sudo systemctl status bitcrm
sudo journalctl -u bitcrm -f
```

## Notes

- The first startup will create the SQLite database automatically if it does not exist.
- Default data path: `/opt/bitcrm/instance/bitcrm.db`
- Before public exposure, edit `/opt/bitcrm/.env` and replace the generated `SECRET_KEY` if needed.
