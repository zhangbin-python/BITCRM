# Read the file
with open('C:/Users/zhang/clawd/BITCRM/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The old function starts with this
old_start = '''def refresh_weekly_metrics_for_user(user_id, db_session):
    """Refresh WeeklyMetrics for a specific user and company with week-over-week and month-over-month comparison."""
    from models import WeeklyMetrics, SalesLead, Pipeline, User
    
    this_monday = get_current_monday()
    last_monday = get_last_monday()
    this_month_start = get_current_month_start()
    last_month_start = get_last_monday()
    last_month_end = get_last_month_end()'''

new_start = '''def refresh_weekly_metrics_for_user(user_id, db_session):
    """
    Refresh WeeklyMetrics for a specific user and company.
    Uses PostgreSQL UPSERT (ON CONFLICT) for concurrent safety.
    """
    from models import WeeklyMetrics, SalesLead, Pipeline, User
    
    this_monday = get_current_monday()
    last_monday = get_last_monday()'''

# Check if old_start exists
if old_start in content:
    # Replace old_start with new_start
    content = content.replace(old_start, new_start)
    
    # Now replace the if/else blocks with UPSERT
    old_upsert_pattern = '''    # Upsert user metrics - use no_autoflush to avoid premature INSERT
    with db_session.no_autoflush:
        user_metrics = WeeklyMetrics.query.filter_by(
            owner_id=user_id,
            week_start=this_monday
        ).first()
    
    if user_metrics:
        user_metrics.leads_count = leads_count
        user_metrics.qualified_leads_count = qualified_leads_count
        user_metrics.pipeline_count = pipeline_count
        user_metrics.tcv = tcv
        user_metrics.current_qtr_revenue = current_qtr_revenue
        user_metrics.next_qtr_revenue = next_qtr_revenue
        user_metrics.leads_vs_last_week = leads_vs_last_week
        user_metrics.qualified_vs_last_week = qualified_vs_last_week
        user_metrics.pipeline_vs_last_week = pipeline_vs_last_week
        user_metrics.tcv_vs_last_week = tcv_vs_last_week
        user_metrics.leads_vs_last_month = leads_vs_last_month
        user_metrics.qualified_vs_last_month = qualified_vs_last_month
        user_metrics.pipeline_vs_last_month = pipeline_vs_last_month
        user_metrics.tcv_vs_last_month = tcv_vs_last_month
        user_metrics.updated_at = datetime.utcnow()
    else:
        user_metrics = WeeklyMetrics(
            owner_id=user_id,
            week_start=this_monday,
            leads_count=leads_count,
            qualified_leads_count=qualified_leads_count,
            pipeline_count=pipeline_count,
            tcv=tcv,
            current_qtr_revenue=current_qtr_revenue,
            next_qtr_revenue=next_qtr_revenue,
            leads_vs_last_week=leads_vs_last_week,
            qualified_vs_last_week=qualified_vs_last_week,
            pipeline_vs_last_week=pipeline_vs_last_week,
            tcv_vs_last_week=tcv_vs_last_week,
            leads_vs_last_month=leads_vs_last_month,
            qualified_vs_last_month=qualified_vs_last_month,
            pipeline_vs_last_month=pipeline_vs_last_month,
            tcv_vs_last_month=tcv_vs_last_month
        )
        db_session.add(user_metrics)'''

    new_upsert = '''    # UPSERT user metrics using raw SQL for PostgreSQL concurrent safety
    upsert_sql = """
        INSERT INTO weekly_metrics (
            owner_id, week_start, leads_count, qualified_leads_count,
            pipeline_count, tcv, current_qtr_revenue, next_qtr_revenue,
            leads_vs_last_week, qualified_vs_last_week, pipeline_vs_last_week, tcv_vs_last_week,
            leads_vs_last_month, qualified_vs_last_month, pipeline_vs_last_month, tcv_vs_last_month,
            updated_at
        ) VALUES (
            :owner_id, :week_start, :leads_count, :qualified_leads_count,
            :pipeline_count, :tcv, :current_qtr_revenue, :next_qtr_revenue,
            :leads_vs_last_week, :qualified_vs_last_week, :pipeline_vs_last_week, :tcv_vs_last_week,
            :leads_vs_last_month, :qualified_vs_last_month, :pipeline_vs_last_month, :tcv_vs_last_month,
            NOW()
        )
        ON CONFLICT (owner_id, week_start) DO UPDATE SET
            leads_count = EXCLUDED.leads_count,
            qualified_leads_count = EXCLUDED.qualified_leads_count,
            pipeline_count = EXCLUDED.pipeline_count,
            tcv = EXCLUDED.tcv,
            current_qtr_revenue = EXCLUDED.current_qtr_revenue,
            next_qtr_revenue = EXCLUDED.next_qtr_revenue,
            leads_vs_last_week = EXCLUDED.leads_vs_last_week,
            qualified_vs_last_week = EXCLUDED.qualified_vs_last_week,
            pipeline_vs_last_week = EXCLUDED.pipeline_vs_last_week,
            tcv_vs_last_week = EXCLUDED.tcv_vs_last_week,
            leads_vs_last_month = EXCLUDED.leads_vs_last_month,
            qualified_vs_last_month = EXCLUDED.qualified_vs_last_month,
            pipeline_vs_last_month = EXCLUDED.pipeline_vs_last_month,
            tcv_vs_last_month = EXCLUDED.tcv_vs_last_month,
            updated_at = NOW()
    """
    
    db_session.execute(db.text(upsert_sql), {
        'owner_id': user_id,
        'week_start': this_monday,
        'leads_count': leads_count,
        'qualified_leads_count': qualified_leads_count,
        'pipeline_count': pipeline_count,
        'tcv': int(tcv),
        'current_qtr_revenue': current_qtr_revenue,
        'next_qtr_revenue': next_qtr_revenue,
        'leads_vs_last_week': leads_vs_last_week,
        'qualified_vs_last_week': qualified_vs_last_week,
        'pipeline_vs_last_week': pipeline_vs_last_week,
        'tcv_vs_last_week': int(tcv_vs_last_week),
        'leads_vs_last_month': leads_vs_last_month,
        'qualified_vs_last_month': qualified_vs_last_month,
        'pipeline_vs_last_month': pipeline_vs_last_month,
        'tcv_vs_last_month': int(tcv_vs_last_month),
    })'''

    if old_upsert_pattern in content:
        content = content.replace(old_upsert_pattern, new_upsert)
    else:
        print("Warning: Could not find user_metrics upsert pattern")
    
    # Replace company metrics upsert
    old_company_pattern = '''    # Upsert company metrics - use no_autoflush to avoid premature INSERT
    with db_session.no_autoflush:
        company_metrics = WeeklyMetrics.query.filter_by(
            owner_id=None,
            week_start=this_monday
        ).first()
    
    if company_metrics:
        company_metrics.leads_count = company_leads_count
        company_metrics.qualified_leads_count = company_qualified_leads_count
        company_metrics.pipeline_count = company_pipeline_count
        company_metrics.tcv = company_tcv
        company_metrics.current_qtr_revenue = company_current_qtr
        company_metrics.next_qtr_revenue = company_next_qtr
        company_metrics.leads_vs_last_week = company_leads_vs_last_week
        company_metrics.qualified_vs_last_week = company_qualified_vs_last_week
        company_metrics.pipeline_vs_last_week = company_pipeline_vs_last_week
        company_metrics.tcv_vs_last_week = company_tcv_vs_last_week
        company_metrics.leads_vs_last_month = company_leads_vs_last_month
        company_metrics.qualified_vs_last_month = company_qualified_vs_last_month
        company_metrics.pipeline_vs_last_month = company_pipeline_vs_last_month
        company_metrics.tcv_vs_last_month = company_tcv_vs_last_month
        company_metrics.updated_at = datetime.utcnow()
    else:
        company_metrics = WeeklyMetrics(
            owner_id=None,
            week_start=this_monday,
            leads_count=company_leads_count,
            qualified_leads_count=company_qualified_leads_count,
            pipeline_count=company_pipeline_count,
            tcv=company_tcv,
            current_qtr_revenue=company_current_qtr,
            next_qtr_revenue=company_next_qtr,
            leads_vs_last_week=company_leads_vs_last_week,
            qualified_vs_last_week=company_qualified_vs_last_week,
            pipeline_vs_last_week=company_pipeline_vs_last_week,
            tcv_vs_last_week=company_tcv_vs_last_week,
            leads_vs_last_month=company_leads_vs_last_month,
            qualified_vs_last_month=company_qualified_vs_last_month,
            pipeline_vs_last_month=company_pipeline_vs_last_month,
            tcv_vs_last_month=company_tcv_vs_last_month
        )
        db_session.add(company_metrics)'''

    new_company_upsert = '''    # UPSERT company metrics
    db_session.execute(db.text(upsert_sql), {
        'owner_id': None,
        'week_start': this_monday,
        'leads_count': company_leads_count,
        'qualified_leads_count': company_qualified_leads_count,
        'pipeline_count': company_pipeline_count,
        'tcv': int(company_tcv),
        'current_qtr_revenue': company_current_qtr,
        'next_qtr_revenue': company_next_qtr,
        'leads_vs_last_week': company_leads_vs_last_week,
        'qualified_vs_last_week': company_qualified_vs_last_week,
        'pipeline_vs_last_week': company_pipeline_vs_last_week,
        'tcv_vs_last_week': int(company_tcv_vs_last_week),
        'leads_vs_last_month': company_leads_vs_last_month,
        'qualified_vs_last_month': company_qualified_vs_last_month,
        'pipeline_vs_last_month': company_pipeline_vs_last_month,
        'tcv_vs_last_month': int(company_tcv_vs_last_month),
    })'''

    if old_company_pattern in content:
        content = content.replace(old_company_pattern, new_company_upsert)
    else:
        print("Warning: Could not find company_metrics upsert pattern")
    
    with open('C:/Users/zhang/clawd/BITCRM/models.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched models.py with PostgreSQL UPSERT!")
else:
    print("Could not find the function to patch. Manual update required.")
