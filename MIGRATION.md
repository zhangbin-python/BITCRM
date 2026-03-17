# Database Migration Commands
# Run these commands in the BITCRM project directory

## 1. Local Development (using SQLite)
cd C:\Users\zhang\clawd\BITCRM

# Create migration (after model changes)
flask db migrate -m "描述修改内容"

# Apply migration
flask db upgrade

# If you are upgrading an existing database for rolling forecast fields
python fix_m1_m12_columns.py

## 2. Zeabur/Production (using PostgreSQL)
# Set environment variables first if needed
# DATABASE_URL is auto-configured by Zeabur

# Run migration in Zeabur:
# Option A: Via Zeabur Console
#   1. Go to your project → Variables
#   2. Add FLASK_APP=run_app.py
#   3. Add FLASK_ENV=production
#   4. Redeploy
#
# Option B: Via CLI (if configured)
#   heroku run flask db upgrade -a YOUR_APP_NAME

# If the database already contains data, run the rolling forecast upgrade script once:
#   python fix_m1_m12_columns.py

## Rolling forecast fields
- `M1~M12` are rolling 12-month revenue forecast fields stored in the `pipeline` table.
- `M1` always means the current month, `M2` the next month, and so on.
- The script `fix_m1_m12_columns.py` is the recommended upgrade path for old databases.
- For a brand new database, normal app startup is enough.

## Quick check current migration status
flask db current
