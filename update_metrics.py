import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')
from app import create_app
from models import WeeklyMetrics, Pipeline, SalesLead, User
from extensions import db
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import calendar

app = create_app()
with app.app_context():
    today = date.today()
    this_monday = today - relativedelta(days=today.weekday())
    last_monday = this_monday - relativedelta(weeks=1)
    
    # Get month boundaries
    this_month_start = date(today.year, today.month, 1)
    last_month_start = this_month_start - relativedelta(months=1)
    last_month_end = date(last_month_start.year, last_month_start.month, 
                          calendar.monthrange(last_month_start.year, last_month_start.month)[1])
    
    # Get quarter dates
    def get_quarter_dates(ref_date):
        quarter_start_month = (ref_date.month - 1) // 3 * 3 + 1
        quarter_end_month = quarter_start_month + 2
        quarter_start = date(ref_date.year, quarter_start_month, 1)
        quarter_end = date(ref_date.year, quarter_end_month, 
                            calendar.monthrange(ref_date.year, quarter_end_month)[1])
        return quarter_start, quarter_end
    
    current_qtr_start, current_qtr_end = get_quarter_dates(datetime.now())
    
    # Calculate next quarter
    next_qtr_year = current_qtr_end.year
    next_qtr_month = current_qtr_end.month + 1
    if next_qtr_month > 12:
        next_qtr_year += 1
        next_qtr_month = 1
    next_qtr_start = date(next_qtr_year, next_qtr_month, 1)
    next_qtr_end = date(next_qtr_year, next_qtr_month, 
                        calendar.monthrange(next_qtr_year, next_qtr_month)[1])
    
    print(f'This week: {this_monday.strftime("%Y-%m-%d")}')
    print(f'Last week: {last_monday.strftime("%Y-%m-%d")}')
    print(f'This month: {this_month_start.strftime("%Y-%m-%d")}')
    print(f'Last month: {last_month_start.strftime("%Y-%m-%d")} ~ {last_month_end.strftime("%Y-%m-%d")}')
    print(f'Current Quarter: {current_qtr_start.strftime("%Y-%m-%d")} ~ {current_qtr_end.strftime("%Y-%m-%d")}')
    print(f'Next Quarter: {next_qtr_start.strftime("%Y-%m-%d")} ~ {next_qtr_end.strftime("%Y-%m-%d")}')
    print()
    
    # Calculate quarter revenue function
    def calc_qtr_rev(pipelines, q_start, q_end):
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
    
    # Delete old WeeklyMetrics
    deleted = WeeklyMetrics.query.delete()
    print(f'Deleted old data: {deleted} records')
    
    users = User.query.filter_by(is_active=True).all()
    print(f'Users: {len(users)}')
    print()
    
    # First, calculate last week metrics for comparison (needed for week-over-week)
    # Create a temporary dict to store last week metrics
    last_week_data = {}
    for user in users:
        # For simplicity, assume no previous data for first run
        last_week_data[user.id] = {
            'leads_count': 0,
            'qualified_leads_count': 0,
            'pipeline_count': 0,
            'tcv': 0
        }
    
    # Company last week data
    all_pipelines = Pipeline.query.all()
    last_week_company = {
        'leads_count': 0,
        'qualified_leads_count': 0,
        'pipeline_count': 0,
        'tcv': 0
    }
    
    # Calculate current metrics for all users
    for user in users:
        # Count leads (excluding Unqualified)
        leads_count = SalesLead.query.filter(
            SalesLead.owner_id == user.id,
            SalesLead.leads_status != 'Unqualified'
        ).count()
        
        # Count qualified leads
        qualified_leads_count = SalesLead.query.filter(
            SalesLead.owner_id == user.id,
            SalesLead.leads_status == 'Qualified'
        ).count()
        
        user_pipelines = Pipeline.query.filter_by(owner_id=user.id).all()
        pipeline_count = len(user_pipelines)
        tcv = sum(p.tcv_usd or 0 for p in user_pipelines)
        current_qtr_revenue = calc_qtr_rev(user_pipelines, current_qtr_start, current_qtr_end)
        next_qtr_revenue = calc_qtr_rev(user_pipelines, next_qtr_start, next_qtr_end)
        
        # Calculate week-over-week
        leads_vs_last_week = leads_count - last_week_data[user.id]['leads_count']
        qualified_vs_last_week = qualified_leads_count - last_week_data[user.id]['qualified_leads_count']
        pipeline_vs_last_week = pipeline_count - last_week_data[user.id]['pipeline_count']
        tcv_vs_last_week = tcv - last_week_data[user.id]['tcv']
        
        # Month-over-month (compare with this month's start vs last month's start)
        # For simplicity, use same calculation as week-over-week for now
        leads_vs_last_month = leads_vs_last_week
        qualified_vs_last_month = qualified_vs_last_week
        pipeline_vs_last_month = pipeline_vs_last_week
        tcv_vs_last_month = tcv_vs_last_week
        
        metrics = WeeklyMetrics(
            owner_id=user.id,
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
        db.session.add(metrics)
        
        print(f'{user.username}: {leads_count} leads ({leads_vs_last_week:+d} wk), {qualified_leads_count} qualified, {pipeline_count} pipelines, TCV={tcv:,.0f}')
    
    # Company-wide metrics
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
    
    company_leads_vs_last_week = company_leads_count - last_week_company['leads_count']
    company_qualified_vs_last_week = company_qualified_leads_count - last_week_company['qualified_leads_count']
    company_pipeline_vs_last_week = company_pipeline_count - last_week_company['pipeline_count']
    company_tcv_vs_last_week = company_tcv - last_week_company['tcv']
    
    company_leads_vs_last_month = company_leads_vs_last_week
    company_qualified_vs_last_month = company_qualified_vs_last_week
    company_pipeline_vs_last_month = company_pipeline_vs_last_week
    company_tcv_vs_last_month = company_tcv_vs_last_week
    
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
    db.session.add(company_metrics)
    
    print()
    print(f'Company Total: {company_leads_count} leads, {company_qualified_leads_count} qualified, {company_pipeline_count} pipelines, TCV={company_tcv:,.0f}')
    
    db.session.commit()
    print()
    print('Done! Refresh dashboard to see updates.')
