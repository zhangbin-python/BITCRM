"""
Patch for PostgreSQL UPSERT in refresh_weekly_metrics_for_user
"""
import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')

# Read the original file
with open('C:/Users/zhang/clawd/BITCRM/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the function
old_function = '''def refresh_weekly_metrics_for_user(user_id, db_session):
    """
    Refresh WeeklyMetrics for a specific user and company with week-over-week and month-over-month comparison.
    """
    from models import WeeklyMetrics, SalesLead, Pipeline, User
    
    this_monday = get_current_monday()
    last_monday = get_last_monday()
    this_month_start = get_current_month_start()
    last_month_start = get_current_month_start()
    last_month_end = get_last_month_end()
    
    current_qtr_start, current_qtr_end = get_quarter_dates(date.today())
    
    # Calculate next quarter
    next_qtr_year = current_qtr_end.year
    next_qtr_month = current_qtr_end.month + 1
    if next_qtr_month > 12:
        next_qtr_year += 1
        next_qtr_month = 1
    next_qtr_start = date(next_qtr_year, next_qtr_month, 1)
    next_qtr_end = date(next_qtr_year, next_qtr_month, 
                        calendar.monthrange(next_qtr_year, next_qtr_month)[1])
    
    def calc_qtr_rev(pipelines, q_start, q_end):
        """Calculate quarter revenue for a list of pipelines."""
        total = 0
        for p in pipelines:
            if p.stage == '6b) Deal Lost':
                continue
            if not p.est_act_date:
                continue
            if p.est_act_date > q_end:
                continue
            
            otc = p.otc_usd or 0
            
            mrc = 0
            months = [(q_start.replace(day=28) + relativedelta(days=4)).replace(day=1),
                      (q_start.replace(day=28) + relativedelta(months=1)).replace(day=1),
                      (q_start.replace(day=28) + relativedelta(months=2)).replace(day=1)]
            
            for m_start in months:
                m_end = (m_start + relativedelta(months=1)) - relativedelta(days=1)
                if p.est_act_date > m_end:
                    continue
                elif p.est_act_date >= m_start and p.est_act_date <= m_end:
                    act_day = p.est_act_date.day
                    days_in_month = (m_end - m_start).days + 1
                    mrc += (p.mrc_usd or 0) * (act_day / days_in_month)
                else:
                    mrc += (p.mrc_usd or 0)
            
            total += int(otc + mrc)
        return total
    
    # Calculate current metrics for user
    user_pipelines = Pipeline.query.filter_by(owner_id=user_id).all()
    
    leads_count = SalesLead.query.filter(
        SalesLead.owner_id == user_id,
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    qualified_leads_count = SalesLead.query.filter(
        SalesLead.owner_id == user_id,
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    pipeline_count = len(user_pipelines)
    tcv = sum(p.tcv_usd or 0 for p in user_pipelines)
    current_qtr_revenue = calc_qtr_rev(user_pipelines, current_qtr_start, current_qtr_end)
    next_qtr_revenue = calc_qtr_rev(user_pipelines, next_qtr_start, next_qtr_end)
    
    # Get last week metrics for week-over-week comparison
    last_week_metrics = WeeklyMetrics.query.filter_by(
        owner_id=user_id,
        week_start=last_monday
    ).first()
    
    # Get last month metrics for month-over-month comparison
    # Find the Monday of the last month's first week
    last_month_first_monday = last_month_start - relativedelta(days=last_month_start.weekday())
    last_month_metrics = WeeklyMetrics.query.filter_by(
        owner_id=user_id,
        week_start=last_month_first_monday
    ).first()
    
    # Calculate week-over-week changes
    leads_vs_last_week = leads_count - (last_week_metrics.leads_count if last_week_metrics else 0)
    qualified_vs_last_week = qualified_leads_count - (last_week_metrics.qualified_leads_count if last_week_metrics else 0)
    pipeline_vs_last_week = pipeline_count - (last_week_metrics.pipeline_count if last_week_metrics else 0)
    tcv_vs_last_week = tcv - (last_week_metrics.tcv if last_week_metrics else 0)
    
    # Calculate month-over-month changes (compare with last month's first week data)
    leads_vs_last_month = leads_count - (last_month_metrics.leads_count if last_month_metrics else 0)
    qualified_vs_last_month = qualified_leads_count - (last_month_metrics.qualified_leads_count if last_month_metrics else 0)
    pipeline_vs_last_month = pipeline_count - (last_month_metrics.pipeline_count if last_month_metrics else 0)
    tcv_vs_last_month = tcv - (last_month_metrics.tcv if last_month_metrics else 0)
    
    # Upsert user metrics - use no_autoflush to avoid premature INSERT
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
        db_session.add(user_metrics)
    
    # Also refresh company-wide metrics (owner_id = NULL)
    all_pipelines = Pipeline.query.all()
    
    company_leads_count = SalesLead.query.filter(
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    company_qualified_leads_count = SalesLead.query.filter(
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    company_pipeline_count = len([p for p in all_pipelines if p.stage != '6b) Deal Lost'])
    company_tcv = sum(p.tcv_usd or 0 for p in all_pipelines if p.stage != '6b) Deal Lost')
    company_current_qtr = calc_qtr_rev(all_pipelines, current_qtr_start, current_qtr_end)
    company_next_qtr = calc_qtr_rev(all_pipelines, next_qtr_start, next_qtr_end)
    
    # Company week-over-week comparison
    company_last_week = WeeklyMetrics.query.filter_by(
        owner_id=None,
        week_start=last_monday
    ).first()
    
    # Company month-over-month comparison
    company_last_month = WeeklyMetrics.query.filter_by(
        owner_id=None,
        week_start=last_month_first_monday
    ).first()
    
    company_leads_vs_last_week = company_leads_count - (company_last_week.leads_count if company_last_week else 0)
    company_qualified_vs_last_week = company_qualified_leads_count - (company_last_week.qualified_leads_count if company_last_week else 0)
    company_pipeline_vs_last_week = company_pipeline_count - (company_last_week.pipeline_count if company_last_week else 0)
    company_tcv_vs_last_week = company_tcv - (company_last_week.tcv if company_last_week else 0)
    
    company_leads_vs_last_month = company_leads_count - (company_last_month.leads_count if company_last_month else 0)
    company_qualified_vs_last_month = company_qualified_leads_count - (company_last_month.qualified_leads_count if company_last_month else 0)
    company_pipeline_vs_last_month = company_pipeline_count - (company_last_month.pipeline_count if company_last_month else 0)
    company_tcv_vs_last_month = company_tcv - (company_last_month.tcv if company_last_month else 0)
    
    # Upsert company metrics - use no_autoflush to avoid premature INSERT
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

new_function = '''def refresh_weekly_metrics_for_user(user_id, db_session):
    """
    Refresh WeeklyMetrics for a specific user and company.
    Uses PostgreSQL UPSERT (ON CONFLICT) for concurrent safety.
    """
    from models import WeeklyMetrics, SalesLead, Pipeline, User
    
    this_monday = get_current_monday()
    last_monday = get_last_monday()
    
    current_qtr_start, current_qtr_end = get_quarter_dates(date.today())
    
    # Calculate next quarter
    next_qtr_year = current_qtr_end.year
    next_qtr_month = current_qtr_end.month + 1
    if next_qtr_month > 12:
        next_qtr_year += 1
        next_qtr_month = 1
    next_qtr_start = date(next_qtr_year, next_qtr_month, 1)
    next_qtr_end = date(next_qtr_year, next_qtr_month, 
                        calendar.monthrange(next_qtr_year, next_qtr_month)[1])
    
    def calc_qtr_rev(pipelines, q_start, q_end):
        """Calculate quarter revenue for a list of pipelines."""
        total = 0
        for p in pipelines:
            if p.stage == '6b) Deal Lost':
                continue
            if not p.est_act_date:
                continue
            if p.est_act_date > q_end:
                continue
            
            otc = p.otc_usd or 0
            
            mrc = 0
            months = [(q_start.replace(day=28) + relativedelta(days=4)).replace(day=1),
                      (q_start.replace(day=28) + relativedelta(months=1)).replace(day=1),
                      (q_start.replace(day=28) + relativedelta(months=2)).replace(day=1)]
            
            for m_start in months:
                m_end = (m_start + relativedelta(months=1)) - relativedelta(days=1)
                if p.est_act_date > m_end:
                    continue
                elif p.est_act_date >= m_start and p.est_act_date <= m_end:
                    act_day = p.est_act_date.day
                    days_in_month = (m_end - m_start).days + 1
                    mrc += (p.mrc_usd or 0) * (act_day / days_in_month)
                else:
                    mrc += (p.mrc_usd or 0)
            
            total += int(otc + mrc)
        return total
    
    # Calculate current metrics for user
    user_pipelines = Pipeline.query.filter_by(owner_id=user_id).all()
    
    leads_count = SalesLead.query.filter(
        SalesLead.owner_id == user_id,
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    qualified_leads_count = SalesLead.query.filter(
        SalesLead.owner_id == user_id,
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    pipeline_count = len(user_pipelines)
    tcv = sum(p.tcv_usd or 0 for p in user_pipelines)
    current_qtr_revenue = calc_qtr_rev(user_pipelines, current_qtr_start, current_qtr_end)
    next_qtr_revenue = calc_qtr_rev(user_pipelines, next_qtr_start, next_qtr_end)
    
    # Get last week metrics
    last_week_metrics = WeeklyMetrics.query.filter_by(
        owner_id=user_id,
        week_start=last_monday
    ).first()
    
    # Get last month metrics
    last_month_start = get_current_month_start() - relativedelta(months=1)
    last_month_first_monday = last_month_start - relativedelta(days=last_month_start.weekday())
    last_month_metrics = WeeklyMetrics.query.filter_by(
        owner_id=user_id,
        week_start=last_month_first_monday
    ).first()
    
    # Calculate comparisons
    leads_vs_last_week = leads_count - (last_week_metrics.leads_count if last_week_metrics else 0)
    qualified_vs_last_week = qualified_leads_count - (last_week_metrics.qualified_leads_count if last_week_metrics else 0)
    pipeline_vs_last_week = pipeline_count - (last_week_metrics.pipeline_count if last_week_metrics else 0)
    tcv_vs_last_week = tcv - (last_week_metrics.tcv if last_week_metrics else 0)
    
    leads_vs_last_month = leads_count - (last_month_metrics.leads_count if last_month_metrics else 0)
    qualified_vs_last_month = qualified_leads_count - (last_month_metrics.qualified_leads_count if last_month_metrics else 0)
    pipeline_vs_last_month = pipeline_count - (last_month_metrics.pipeline_count if last_month_metrics else 0)
    tcv_vs_last_month = tcv - (last_month_metrics.tcv if last_month_metrics else 0)
    
    # UPSERT using raw SQL for PostgreSQL concurrent safety
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
    })
    
    # Also refresh company-wide metrics (owner_id = NULL)
    all_pipelines = Pipeline.query.all()
    
    company_leads_count = SalesLead.query.filter(
        SalesLead.leads_status != 'Unqualified'
    ).count()
    
    company_qualified_leads_count = SalesLead.query.filter(
        SalesLead.leads_status == 'Qualified'
    ).count()
    
    company_pipeline_count = len([p for p in all_pipelines if p.stage != '6b) Deal Lost'])
    company_tcv = sum(p.tcv_usd or 0 for p in all_pipelines if p.stage != '6b) Deal Lost')
    company_current_qtr = calc_qtr_rev(all_pipelines, current_qtr_start, current_qtr_end)
    company_next_qtr = calc_qtr_rev(all_pipelines, next_qtr_start, next_qtr_end)
    
    # Company comparisons
    company_last_week = WeeklyMetrics.query.filter_by(
        owner_id=None,
        week_start=last_monday
    ).first()
    
    company_last_month = WeeklyMetrics.query.filter_by(
        owner_id=None,
        week_start=last_month_first_monday
    ).first()
    
    company_leads_vs_last_week = company_leads_count - (company_last_week.leads_count if company_last_week else 0)
    company_qualified_vs_last_week = company_qualified_leads_count - (company_last_week.qualified_leads_count if company_last_week else 0)
    company_pipeline_vs_last_week = company_pipeline_count - (company_last_week.pipeline_count if company_last_week else 0)
    company_tcv_vs_last_week = company_tcv - (company_last_week.tcv if company_last_week else 0)
    
    company_leads_vs_last_month = company_leads_count - (company_last_month.leads_count if company_last_month else 0)
    company_qualified_vs_last_month = company_qualified_leads_count - (company_last_month.qualified_leads_count if company_last_month else 0)
    company_pipeline_vs_last_month = company_pipeline_count - (company_last_month.pipeline_count if company_last_month else 0)
    company_tcv_vs_last_month = company_tcv - (company_last_month.tcv if company_last_month else 0)
    
    # UPSERT company metrics
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

if old_function in content:
    content = content.replace(old_function, new_function)
    with open('C:/Users/zhang/clawd/BITCRM/models.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully patched models.py with PostgreSQL UPSERT!")
else:
    print("Could not find the function to patch. The file may have already been modified.")
    print("Please manually update models.py with the UPSERT version.")
