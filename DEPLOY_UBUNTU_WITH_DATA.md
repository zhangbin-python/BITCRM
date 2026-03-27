# BITCRM Ubuntu Deployment Guide With Current Data

This package includes a copy of your current SQLite database.

## What is included

- application files
- deployment scripts
- `migration-data/bitcrm.db`

## Deployment steps on Ubuntu

### 1. Copy and extract the package

```bash
mkdir -p ~/packages
cp /media/$USER/<USB_NAME>/BITCRM-ubuntu-with-data-*.zip ~/packages/
cd ~/packages
unzip BITCRM-ubuntu-with-data-*.zip
cd BITCRM-ubuntu-with-data-*
```

### 2. Run the deployment script

```bash
sudo bash deploy_with_data.sh
```

This script will:

- deploy the application to `/opt/bitcrm`
- create or reuse `/opt/bitcrm/.env`
- install dependencies
- install the `bitcrm` systemd service
- back up any existing Ubuntu database
- restore the packaged `bitcrm.db`
- restart the service

### 3. Open the system

```bash
http://<your-ubuntu-ip>:8000
```

### 4. Check status

```bash
sudo systemctl status bitcrm
sudo journalctl -u bitcrm -f
```

## Database backup behavior

If `/opt/bitcrm/instance/bitcrm.db` already exists on Ubuntu, it will be backed up automatically to:

```bash
/opt/bitcrm/instance/bitcrm.db.bak.YYYYMMDD-HHMMSS
```

## Notes

- This package contains your real business data, so keep the USB drive secure.
- The packaged database is a snapshot taken when the package was built on Windows.
- If you continue using the Windows version after packaging, newer data will not be included unless you build a fresh migration package again.
