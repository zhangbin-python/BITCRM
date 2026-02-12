"""
Dashboard Cron Job
Daily snapshot generation at 00:01
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from extensions import db
from models import User, SalesLead, Pipeline
from utils import (
    calculate_quarter_revenue,
    get_quarter_dates,
    get_next_quarter_dates
)
from dashboard_snapshot import DashboardSnapshot, save_snapshot


def create_daily_snapshots():
    """
    Generate daily snapshots for all users at 00:01.
    This function should be called by a scheduler (e.g., cron, APScheduler).
    """
    today = date.today()
    
    # Get date ranges
    this_monday = today - timedelta(days=today.weekday())
    prev_monday = this_monday - timedelta(weeks=1)
    prev_sunday = prev_monday + timedelta(days=6)
    
    # Get quarter dates
    current_qtr = get_quarter_dates(today)
    next_qtr = get_next_quarter_dates(today)
    
    # Get all accessible pipelines (exclude Deal Lost)
    base_pipeline_query = Pipeline.query.filter(
        Pipeline.stage.notin_(['6b) Deal Lost'])
    )
    
    # Calculate summary metrics
    summary_leads_count = SalesLead.query.filter(
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    summary_qualified_leads_count = SalesLead.query.filter(
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    # Include leads转入 Pipeline (qualified leads that converted)
    # Use Pipeline.sales_lead_id subquery instead of non-existent SalesLead.sales_lead_id
    converted_lead_ids = db.session.query(Pipeline.sales_lead_id).filter(
        Pipeline.sales_lead_id.isnot(None)
    ).subquery()
    pipeline_leads = SalesLead.query.filter(
        SalesLead.id.in_(converted_lead_ids)
    ).count()
    summary_qualified_leads_count += pipeline_leads
    
    summary_pipeline_count = base_pipeline_query.count()
    summary_tcv = sum(p.tcv_usd for p in base_pipeline_query.all())
    
    # Calculate quarter revenue
    summary_current_qtr_revenue = calculate_quarter_revenue(
        base_pipeline_query.all(), current_qtr[0], current_qtr[1]
    )
    summary_next_qtr_revenue = calculate_quarter_revenue(
        base_pipeline_query.all(), next_qtr[0], next_qtr[1]
    )
    
    # VS Last Week
    summary_leads_vs_last_week = SalesLead.query.filter(
        SalesLead.date_added <= prev_sunday,
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    # Save summary snapshot (owner_id = NULL)
    save_snapshot(
        owner_id=None,
        snapshot_date=today,
        leads_count=summary_leads_count,
        qualified_leads_count=summary_qualified_leads_count,
        pipeline_count=summary_pipeline_count,
        tcv=summary_tcv,
        current_qtr_revenue=summary_current_qtr_revenue,
        next_qtr_revenue=summary_next_qtr_revenue,
        leads_vs_last_week=summary_leads_vs_last_week,
        qualified_vs_last_week=0,  # Simplified
        pipeline_vs_last_week=0,   # Simplified
        tcv_vs_last_week=0        # Simplified
    )
    
    # Generate per-user snapshots
    for user in User.query.filter_by(is_active=True).all():
        # User leads
        user_leads_count = SalesLead.query.filter_by(owner_id=user.id).filter(
            SalesLead.leads_status != 'Unqualified'
        ).count()
        
        # User qualified leads
        user_qualified_count = SalesLead.query.filter_by(owner_id=user.id).filter(
            SalesLead.leads_status == 'Qualified'
        ).count()
        # Use Pipeline.sales_lead_id subquery for user
        user_converted_ids = db.session.query(Pipeline.sales_lead_id).filter(
            Pipeline.owner_id == user.id,
            Pipeline.sales_lead_id.isnot(None)
        ).subquery()
        user_pipeline_leads = SalesLead.query.filter(
            SalesLead.id.in_(user_converted_ids)
        ).count()
        user_qualified_count += user_pipeline_leads
        
        # User pipelines
        user_pipeline_query = base_pipeline_query.filter(
            Pipeline.owner_id == user.id
        )
        user_pipeline_count = user_pipeline_query.count()
        user_tcv = sum(p.tcv_usd for p in user_pipeline_query.all())
        
        # User quarter revenue
        user_current_qtr_revenue = calculate_quarter_revenue(
            user_pipeline_query.all(), current_qtr[0], current_qtr[1]
        )
        user_next_qtr_revenue = calculate_quarter_revenue(
            user_pipeline_query.all(), next_qtr[0], next_qtr[1]
        )
        
        # VS Last Week
        user_leads_vs_last_week = SalesLead.query.filter_by(owner_id=user.id).filter(
            SalesLead.date_added <= prev_sunday,
            SalesLead.leads_status != 'Unqualified'
        ).count()
        
        # Save user snapshot
        save_snapshot(
            owner_id=user.id,
            snapshot_date=today,
            leads_count=user_leads_count,
            qualified_leads_count=user_qualified_count,
            pipeline_count=user_pipeline_count,
            tcv=user_tcv,
            current_qtr_revenue=user_current_qtr_revenue,
            next_qtr_revenue=user_next_qtr_revenue,
            leads_vs_last_week=user_leads_vs_last_week,
            qualified_vs_last_week=0,
            pipeline_vs_last_week=0,
            tcv_vs_last_week=0
        )
    
    db.session.commit()
    print(f"[{today}] Daily dashboard snapshots created successfully")


def initialize_all_snapshots():
    """
    Initialize snapshots for the past 7 days + today.
    Called on first access if snapshots don't exist.
    """
    from dashboard_snapshot import initialize_snapshots_for_user
    
    today = date.today()
    created_count = 0
    
    # Initialize summary snapshots
    created_count += initialize_snapshots_for_user(owner_id=None, days=7)
    
    # Initialize user snapshots
    for user in User.query.filter_by(is_active=True).all():
        created_count += initialize_snapshots_for_user(owner_id=user.id, days=7)
    
    print(f"[{today}] Initialized {created_count} dashboard snapshots")
    return created_count


if __name__ == '__main__':
    # This can be run as a standalone script
    import sys
    from app import create_app
    
    app = create_app()
    with app.app_context():
        if len(sys.argv) > 1 and sys.argv[1] == 'init':
            initialize_all_snapshots()
        else:
            create_daily_snapshots()
