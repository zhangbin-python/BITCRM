import sys
from datetime import date

sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')

from app import create_app
from extensions import db
from models import User, WeeklyMetrics
from services.weekly_metrics_service import get_week_start, refresh_weekly_metrics


app = create_app()


with app.app_context():
    ref_date = date.today()
    week_start = get_week_start(ref_date)
    active_owner_ids = [user.id for user in User.query.filter_by(is_active=True).all()]

    print(f'Rebuilding weekly metrics for week starting {week_start}...')

    WeeklyMetrics.query.filter_by(week_start=week_start).delete()
    db.session.commit()

    refresh_weekly_metrics(owner_ids=active_owner_ids, ref_date=ref_date)

    print(f'Updated {len(active_owner_ids)} owner snapshots and company summary.')
