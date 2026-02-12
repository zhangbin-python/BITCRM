# Database Migration Commands
# Run these commands in the BITCRM project directory

## 1. Local Development (using SQLite)
cd C:\Users\zhang\clawd\BITCRM

# Create migration (after model changes)
flask db migrate -m "描述修改内容"

# Apply migration
flask db upgrade

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

## Quick check current migration status
flask db current
