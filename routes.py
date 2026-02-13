"""
BITCRM Route Definitions
All Flask routes for the application.
"""
import pandas as pd
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify, make_response
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _, get_locale
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, and_, or_, select
from datetime import datetime, date, timedelta
from io import BytesIO
import pandas as pd
import os

from extensions import db, cache
from models import User, SalesLead, Pipeline, Task, ActivityLog, disable_metrics_events
from utils import (
    allowed_file, validate_date, validate_numeric,
    create_excel_template, export_to_excel, import_from_excel,
    validate_sales_lead_import, validate_pipeline_import,
    calculate_pipeline_metrics,
    excel_date_to_str, excel_date_to_date,
    get_this_week_range, get_previous_week_range,
    calculate_weekly_growth, format_currency,
    get_quarter_dates, get_next_quarter_dates, calculate_quarter_revenue,
    format_currency_thousands, format_currency_short, format_vs_indicator
)
from activity_logger import log_activity, log_lead_import, log_lead_created, log_lead_updated, log_pipeline_created, log_pipeline_stage_changed, log_task_created, log_task_completed, log_task_reopened, log_followup_created, log_account_created, log_lead_deleted, log_lead_exported, log_pipeline_deleted, log_pipeline_exported, log_pipeline_imported, log_task_edited, log_task_deleted, log_task_status_changed, log_password_changed, log_language_changed, log_user_created, log_user_status_changed, log_filter_applied, log_column_visibility_changed, log_login, log_logout
from extensions import cache

# ============================================================================
# MAIN BLUEPRINT
# ============================================================================

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """Redirect to dashboard."""
    return redirect(url_for('main.dashboard'))


@main_bp.route('/dashboard')
@login_required
# @cache.cached(timeout=300, query_string=True)  # Disabled for debugging
def dashboard():
    """
    Dashboard with key metrics.

    Optimized with eager loading and SQL aggregations.
    """
    from sqlalchemy.orm import joinedload

    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(weeks=1)

    # =========================================================================
    # 获取季度日期
    # =========================================================================
    current_qtr = get_quarter_dates(today)
    next_qtr = get_next_quarter_dates(today)

    # =========================================================================
    # 预加载所有 Pipeline 数据（带 owner 关联）
    # =========================================================================
    base_query = Pipeline.query.options(joinedload(Pipeline.owner))

    # 根据权限过滤
    if not current_user.is_admin():
        # Get the Pipeline IDs that current_user supports
        supported_pipeline_ids = db.session.query(Pipeline.id).filter(
            Pipeline.support_team.contains(current_user)
        ).subquery()
        base_query = base_query.filter(
            or_(
                Pipeline.owner_id == current_user.id,
                Pipeline.id.in_(supported_pipeline_ids)
            )
        )

    all_pipelines = base_query.all()

    # 拆分 active 和 deal_lost
    active_pipelines = [p for p in all_pipelines if p.stage != '6b) Deal Lost']
    deal_lost_pipelines = [p for p in all_pipelines if p.stage == '6b) Deal Lost']

    # =========================================================================
    # 全公司数据（用 Python 聚合，比多次 SQL 查询快）
    # =========================================================================
    company_this = {
        'leads_count': SalesLead.query.filter(SalesLead.leads_status != 'Unqualified').count(),
        'qualified_leads_count': SalesLead.query.filter(SalesLead.leads_status == 'Qualified').count(),
        'pipeline_count': len(active_pipelines),
        'tcv': sum(p.tcv_usd or 0 for p in active_pipelines),
        'current_qtr_revenue': calculate_quarter_revenue(active_pipelines, current_qtr[0], current_qtr[1]),
        'next_qtr_revenue': calculate_quarter_revenue(active_pipelines, next_qtr[0], next_qtr[1])
    }

    # 上周数据（暂时用当前数据作为占位）
    company_last = {k: 0 for k in company_this}

    # =========================================================================
    # PER-OWNER BREAKDOWN（优化：避免 Python 循环中的 N+1 查询）
    # =========================================================================
    users = User.query.filter_by(is_active=True).all()

    # 预构建 owner_id 到 user 的映射
    user_map = {u.id: u for u in users}

    # 按 owner_id 分组（数据库层面分组比 Python 循环快）
    from collections import defaultdict
    owner_pipeline_map = defaultdict(list)
    for p in active_pipelines:
        owner_pipeline_map[p.owner_id].append(p)

    owner_metrics = []
    for user in users:
        user_pipelines = owner_pipeline_map.get(user.id, [])

        # 该 owner 的 Leads
        user_leads_count = SalesLead.query.filter_by(owner_id=user.id).filter(
            SalesLead.leads_status != 'Unqualified'
        ).count()

        qualified_leads_count = SalesLead.query.filter(
            or_(SalesLead.owner_id == user.id)
        ).filter(
            or_(SalesLead.leads_status == 'Qualified')
        ).count()

        owner_metrics.append({
            'user': user,
            'user_id': user.id,
            'leads_count': user_leads_count,
            'leads_vs_last_week': 0,
            'qualified_leads_count': qualified_leads_count,
            'qualified_vs_last_week': 0,
            'pipeline_count': len(user_pipelines),
            'tcv': sum(p.tcv_usd or 0 for p in user_pipelines),
            'current_qtr_revenue': calculate_quarter_revenue(user_pipelines, current_qtr[0], current_qtr[1]),
            'next_qtr_revenue': calculate_quarter_revenue(user_pipelines, next_qtr[0], next_qtr[1]),
            'username': user.username,
            'role': user.role
        })

    # 按 TCV 排序
    owner_metrics.sort(key=lambda x: x['tcv'], reverse=True)

    # =========================================================================
    # KANBAN BOARD DATA（用预加载的数据，避免 N+1）
    # =========================================================================
    import re
    date_pattern = r'(\d{4}-\d{2}-\d{2})'

    pipeline_stages = [{'value': stage, 'label': stage, 'is_lost': False}
                       for stage in Pipeline.STAGE_OPTIONS if stage != '6b) Deal Lost']
    pipeline_stages.append({'value': '6b) Deal Lost', 'label': '6b) Deal Lost', 'is_lost': True})

    pipeline_deals = []
    # 处理 active pipelines
    for p in active_pipelines:
        latest_followup = None
        if p.follow_up:
            dates = re.findall(date_pattern, p.follow_up)
            if dates:
                latest_followup = max(dates)

        pipeline_deals.append({
            'id': p.id,
            'company': p.company,
            'name': p.name,
            'owner_name': p.owner.username if p.owner else None,
            'owner_id': p.owner_id,
            'tcv_usd': p.tcv_usd or 0,
            'mrc_usd': p.mrc_usd or 0,
            'win_rate': p.win_rate,
            'stage': p.stage,
            'est_sign_date': p.est_sign_date.strftime('%Y-%m-%d') if p.est_sign_date else None,
            'latest_followup': latest_followup,
            'level': p.level,
            'is_lost': False
        })

    # 处理 deal lost
    for p in deal_lost_pipelines:
        latest_followup = None
        if p.follow_up:
            dates = re.findall(date_pattern, p.follow_up)
            if dates:
                latest_followup = max(dates)

        pipeline_deals.append({
            'id': p.id,
            'company': p.company,
            'name': p.name,
            'owner_name': p.owner.username if p.owner else None,
            'owner_id': p.owner_id,
            'tcv_usd': p.tcv_usd or 0,
            'mrc_usd': p.mrc_usd or 0,
            'win_rate': p.win_rate,
            'stage': p.stage,
            'est_sign_date': p.est_sign_date.strftime('%Y-%m-%d') if p.est_sign_date else None,
            'latest_followup': latest_followup,
            'level': p.level,
            'is_lost': True
        })

    # =========================================================================
    # RENDER TEMPLATE
    # =========================================================================

    return render_template('dashboard.html',
                          total_leads=company_this.get('leads_count', 0),
                          vs_last_week_leads=company_this.get('leads_count', 0) - company_last.get('leads_count', 0),
                          qualified_leads=company_this.get('qualified_leads_count', 0),
                          vs_last_week_qualified=company_this.get('qualified_leads_count', 0) - company_last.get('qualified_leads_count', 0),
                          pipeline_count=company_this.get('pipeline_count', 0),
                          vs_last_week_pipeline=company_this.get('pipeline_count', 0) - company_last.get('pipeline_count', 0),
                          current_tcv=company_this.get('tcv', 0),
                          vs_last_week_tcv=company_this.get('tcv', 0) - company_last.get('tcv', 0),
                          current_quarter_revenue=company_this.get('current_qtr_revenue', 0),
                          next_quarter_revenue=company_this.get('next_qtr_revenue', 0),
                          owner_metrics=owner_metrics,
                          users=users,
                          pipeline_stages=pipeline_stages,
                          pipeline_deals=pipeline_deals,
                          format_currency=format_currency,
                          format_currency_thousands=format_currency_thousands,
                          format_currency_short=format_currency_short,
                          now=datetime.now(),
                          get_locale=get_locale)


class EmptyMetrics:
    """空指标类，用于处理没有数据的情况"""
    leads_count = 0
    qualified_leads_count = 0
    pipeline_count = 0
    tcv = 0
    current_qtr_revenue = 0
    next_qtr_revenue = 0


@main_bp.route('/set-language/<lang>')
def set_language(lang):
    """Set language preference and redirect back."""
    if lang not in ['en', 'zh']:
        lang = 'en'
    
    # Set cookie first
    response = make_response(redirect(request.referrer or url_for('main.dashboard')))
    response.set_cookie('lang', lang, max_age=60*60*24*365, path='/', samesite='Lax')
    
    # Log the activity (only for authenticated users)
    try:
        if current_user.is_authenticated:
            log_language_changed(current_user, lang, request.remote_addr)
    except:
        pass
    
    return response


@main_bp.route('/manual')
@login_required
def manual():
    """User manual page."""
    return render_template('manual.html')


@main_bp.route('/activities')
@login_required
def activities():
    """Activities/Operation Logs page."""
    from datetime import datetime, timedelta
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id')
    action_type = request.args.get('action_type')
    subject_type = request.args.get('subject_type')
    keyword = request.args.get('keyword', '')
    export = request.args.get('export')
    
    # Build query
    query = ActivityLog.query
    
    # Apply permission filters
    if current_user.role == 'sales':
        # Sales can only view own logs
        query = query.filter(ActivityLog.user_id == current_user.id)
    elif current_user.role == 'marketing':
        # Marketing can view all leads-related logs
        query = query.filter(
            or_(
                ActivityLog.subject_type == 'lead',
                ActivityLog.action_type.like('Leads%')
            )
        )
    # Admin can view all logs
    
    # Apply date filters
    if start_date:
        query = query.filter(ActivityLog.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(ActivityLog.created_at < end_date_obj)
    
    # Apply user filter
    if user_id:
        query = query.filter(ActivityLog.user_id == int(user_id))
    
    # Apply subject type filter
    if subject_type:
        query = query.filter(ActivityLog.subject_type == subject_type)
    
    # Apply action type filter
    if action_type:
        query = query.filter(ActivityLog.action_type == action_type)
    
    # Apply keyword search
    if keyword:
        query = query.filter(
            or_(
                ActivityLog.description.ilike(f'%{keyword}%'),
                ActivityLog.subject_name.ilike(f'%{keyword}%'),
                ActivityLog.user_name.ilike(f'%{keyword}%')
            )
        )
    
    # Get statistics
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Base stats query (permission filtered only, no search filters)
    stats_query = ActivityLog.query
    if current_user.role == 'sales':
        stats_query = stats_query.filter(ActivityLog.user_id == current_user.id)
    elif current_user.role == 'marketing':
        stats_query = stats_query.filter(
            or_(
                ActivityLog.subject_type == 'lead',
                ActivityLog.action_type.like('Leads%')
            )
        )
    
    stats = {
        'total': stats_query.count(),
        'today': stats_query.filter(ActivityLog.created_at >= datetime.combine(today, datetime.min.time())).count(),
        'week': stats_query.filter(ActivityLog.created_at >= datetime.combine(week_ago, datetime.min.time())).count(),
        'month': stats_query.filter(ActivityLog.created_at >= datetime.combine(month_ago, datetime.min.time())).count()
    }
    
    # Export functionality
    if export == 'csv':
        from io import StringIO
        import csv
        
        activities = query.order_by(ActivityLog.created_at.desc()).all()
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Time', 'User', 'Action Type', 'Subject Type', 'Subject ID', 'Subject Name', 'Description', 'IP Address'])
        
        for a in activities:
            writer.writerow([
                a.id,
                a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                a.user_name,
                a.action_type,
                a.subject_type or '',
                a.subject_id or '',
                a.subject_name or '',
                a.description or '',
                a.ip_address or ''
            ])
        
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=activities_{today}.csv'
        return response
    
    # Get all action types for filter dropdown
    action_types = db.session.query(ActivityLog.action_type).distinct().all()
    action_types = [a[0] for a in action_types]
    
    # Get users who have activity logs for filter dropdown (only show users with data)
    users = db.session.query(User).join(ActivityLog).filter(
        User.is_active == True
    ).distinct().order_by(User.username).all()
    
    # Order by created_at descending and paginate
    query = query.order_by(ActivityLog.created_at.desc())
    page = request.args.get('page', 1, type=int)
    per_page = 100
    activities = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Prepare filters dict for template
    filters = {
        'start_date': start_date,
        'end_date': end_date,
        'user_id': user_id,
        'action_type': action_type,
        'subject_type': subject_type,
        'keyword': keyword
    }
    
    return render_template('activities.html',
                          activities=activities,
                          stats=stats,
                          users=users,
                          action_types=action_types,
                          filters=filters)


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            log_login(user, request.remote_addr, success=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            log_login(user or username, request.remote_addr, success=False)
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')


@main_bp.route('/logout')
@login_required
def logout():
    """User logout."""
    log_logout(current_user, request.remote_addr)
    logout_user()
    return redirect(url_for('main.login'))


# ============================================================================
# LEADS BLUEPRINT
# ============================================================================

leads_bp = Blueprint('leads', __name__)


@leads_bp.route('/')
@login_required
def index():
    """Sales Leads Management page."""
    
    # Check access permissions
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get filter parameters
    show_unqualified = request.args.get('show_unqualified', 'false') == 'true'
    status_filter = request.args.get('status', None)
    source_filter = request.args.get('source', None)
    owner_filter = request.args.get('owner', None)
    
    # Build query
    query = SalesLead.query
    
    # Sales can only see their own leads + leads owned by marketing
    if not current_user.can_view_all_leads():
        marketing_users = User.query.filter(User.role.ilike('marketing')).all()
        marketing_ids = [u.id for u in marketing_users]
        query = query.filter(
            db.or_(
                SalesLead.owner_id == current_user.id,
                SalesLead.owner_id.in_(marketing_ids)
            )
        )
    
    # Filter by unqualified status
    if not show_unqualified:
        query = query.filter(SalesLead.leads_status != 'Unqualified')
    
    # Apply filters
    if status_filter:
        query = query.filter(SalesLead.leads_status == status_filter)
    if source_filter:
        query = query.filter(SalesLead.source == source_filter)
    if owner_filter:
        query = query.filter(SalesLead.owner_id == owner_filter)
    
    # Order by date_added descending, then by name
    query = query.order_by(SalesLead.date_added.desc(), SalesLead.name)
    
    # Get total count before pagination
    total_count = query.count()
    
    # Paginate
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    leads = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get all active users for owner dropdown
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    
    # Get column preferences
    prefs = current_user.get_column_preferences('leads')
    selected_columns = prefs.get('columns', ['name', 'company', 'leads_status', 'owner', 'date_added'])
    
    # Available columns definition
    available_columns = [
        {'key': 'name', 'label': _('Name'), 'sortable': True},
        {'key': 'company', 'label': _('Company'), 'sortable': True},
        {'key': 'industry', 'label': _('Industry'), 'sortable': True},
        {'key': 'position', 'label': _('Position'), 'sortable': True},
        {'key': 'email', 'label': _('Email'), 'sortable': True},
        {'key': 'mobile_number', 'label': _('Mobile'), 'sortable': False},
        {'key': 'leads_status', 'label': _('Status'), 'sortable': True},
        {'key': 'source', 'label': _('Source'), 'sortable': True},
        {'key': 'event', 'label': _('Event'), 'sortable': False},
        {'key': 'date_added', 'label': _('Date Added'), 'sortable': True},
        {'key': 'owner', 'label': _('Owner'), 'sortable': True},
        {'key': 'requirements', 'label': _('Requirements'), 'sortable': False},
        {'key': 'note', 'label': _('Notes'), 'sortable': False},
        {'key': 'created_at', 'label': _('Created'), 'sortable': True},
    ]
    
    # Default columns keys if none selected
    default_columns = ['name', 'company', 'leads_status', 'owner', 'date_added']
    
    # If preferences exist, use them
    if selected_columns:
        default_columns = selected_columns
    
    # Build visible_columns as full column objects
    visible_columns = []
    visible_column_keys = []
    for col_key in default_columns:
        for col in available_columns:
            if col['key'] == col_key:
                visible_columns.append(col)
                visible_column_keys.append(col_key)
                break
    
    return render_template('leads/index.html',
                          SalesLead=SalesLead,
                          leads=leads,
                          total_count=total_count,
                          show_unqualified=show_unqualified,
                          status_filter=status_filter,
                          source_filter=source_filter,
                          owner_filter=owner_filter,
                          available_columns=available_columns,
                          default_columns=default_columns,
                          visible_columns=visible_columns,
                          visible_column_keys=visible_column_keys,
                          users=users)


@leads_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add new Sales Lead."""
    
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            lead = SalesLead(
                name=request.form.get('name'),
                company=request.form.get('company'),
                industry=request.form.get('industry'),
                position=request.form.get('position'),
                email=request.form.get('email'),
                mobile_number=request.form.get('mobile_number'),
                requirements=request.form.get('requirements'),
                leads_status=request.form.get('leads_status', 'Waiting to be Contacted'),
                source=request.form.get('source'),
                event=request.form.get('event'),
                owner_id=request.form.get('owner_id'),
                note=request.form.get('note'),
                date_added=validate_date(request.form.get('date_added')) or date.today()
            )
            
            db.session.add(lead)
            db.session.commit()
            
            # Log the activity
            log_lead_created(current_user, lead, request.remote_addr)
            
            flash('Sales Lead added successfully!', 'success')
            
            if 'continue' in request.form:
                return redirect(url_for('leads.add'))
            else:
                return redirect(url_for('leads.index'))
                
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding Sales Lead: {str(e)}', 'danger')
    
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('leads/form.html', lead=None, users=users, title='Add Sales Lead')


@leads_bp.route('/<int:lead_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(lead_id):
    """Edit Sales Lead."""
    
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    lead = SalesLead.query.get_or_404(lead_id)
    
    if request.method == 'POST':
        try:
            lead.name = request.form.get('name')
            lead.company = request.form.get('company')
            lead.industry = request.form.get('industry')
            lead.position = request.form.get('position')
            lead.email = request.form.get('email')
            lead.mobile_number = request.form.get('mobile_number')
            lead.requirements = request.form.get('requirements')
            lead.leads_status = request.form.get('leads_status')
            lead.source = request.form.get('source')
            lead.event = request.form.get('event')
            lead.owner_id = request.form.get('owner_id')
            lead.note = request.form.get('note')
            date_added = validate_date(request.form.get('date_added'))
            if date_added:
                lead.date_added = date_added
            
            # Check if status changed to Qualified
            if lead.leads_status == 'Qualified' and not lead.pipeline:
                pipeline = lead.convert_to_pipeline()
                db.session.add(pipeline)
            
            db.session.commit()
            flash('Sales Lead updated successfully!', 'success')
            
            return redirect(url_for('leads.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating Sales Lead: {str(e)}', 'danger')
    
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('leads/form.html', lead=lead, users=users, title='Edit Sales Lead')


@leads_bp.route('/<int:lead_id>/delete', methods=['POST'])
@login_required
def delete(lead_id):
    """Delete Sales Lead."""
    
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    lead = SalesLead.query.get_or_404(lead_id)
    
    try:
        db.session.delete(lead)
        db.session.commit()
        
        # Log the activity
        log_lead_deleted(current_user, lead.name, request.remote_addr)
        
        flash('Sales Lead deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting Sales Lead: {str(e)}', 'danger')
    
    return redirect(url_for('leads.index'))


@leads_bp.route('/<int:lead_id>/quick-update', methods=['POST'])
@login_required
def quick_update(lead_id):
    """
    Quick update API endpoint for inline editing.
    Accepts JSON: {"field": "company", "value": "New Company"}
    Returns success/error JSON response.
    """
    
    if not current_user.can_access_leads():
        return jsonify({'success': False, 'error': '无权访问销售线索'}), 403
    
    lead = SalesLead.query.get_or_404(lead_id)
    
    try:
        data = request.get_json()
        
        if not data or 'field' not in data or 'value' not in data:
            return jsonify({'success': False, 'error': '无效的请求数据'}), 400
        
        field = data['field']
        value = data['value']
        
        # Validate field exists and is editable
        editable_fields = [
            'name', 'company', 'industry', 'position', 'email', 
            'mobile_number', 'requirements', 'leads_status', 'source', 
            'event', 'date_added', 'owner_id', 'note'
        ]
        
        if field not in editable_fields:
            return jsonify({'success': False, 'error': f'字段 {field} 不允许快速编辑'}), 400
        
        # Get old value for logging
        old_value = getattr(lead, field, None)
        
        # Use model validation method
        is_valid, error_message, cleaned_value = lead.validate_field(field, value)
        
        if not is_valid:
            return jsonify({'success': False, 'error': error_message}), 400
        
        # Special handling for status change to Qualified
        if field == 'leads_status' and value == 'Qualified' and lead.leads_status != 'Qualified':
            print(f"[LEAD STATUS CHANGE] Lead {lead.id} ({lead.name}): {lead.leads_status} -> Qualified")
            # Auto-convert to pipeline
            if not lead.pipeline:
                pipeline = lead.convert_to_pipeline()
                db.session.add(pipeline)
                print(f"[LEAD STATUS CHANGE] Auto-converted lead {lead.id} to pipeline")
        
        # Set the cleaned value
        setattr(lead, field, cleaned_value)
        
        db.session.commit()
        
        # Log the activity
        log_lead_updated(current_user, lead, f'Updated {field} to {cleaned_value}', request.remote_addr)
        
        # Get the new display value
        new_value = getattr(lead, field, None)
        
        # Format display value based on field type
        display_value = new_value
        if field == 'leads_status':
            display_value = _(new_value) if new_value else ''
        elif field == 'date_added':
            display_value = new_value.strftime('%Y-%m-%d') if new_value else ''
        elif field == 'owner_id':
            owner = User.query.get(new_value)
            display_value = owner.username if owner else ''
        
        print(f"[QUICK UPDATE] Lead {lead.id}: {field} changed from '{old_value}' to '{new_value}'")
        
        return jsonify({
            'success': True,
            'message': '更新成功',
            'field': field,
            'value': display_value if field not in ['owner_id'] else new_value,
            'raw_value': new_value
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"[QUICK UPDATE ERROR] Lead {lead_id}: {str(e)}")
        return jsonify({'success': False, 'error': f'更新失败: {str(e)}'}), 500


@leads_bp.route('/import-template')
@login_required
def import_template():
    """Download Excel import template."""
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    columns = ['Name', 'Company', 'Industry', 'Position', 'Email', 'Mobile Number',
              'Requirements', 'Leads Status', 'Source', 'Event', 'Date Added', 'Owner', 'Note']
    
    output = create_excel_template(columns, 'sales_leads_template.xlsx')
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='sales_leads_template.xlsx'
    )


@leads_bp.route('/export')
@login_required
def export():
    """Export Sales Leads to Excel."""
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get filtered leads
    query = SalesLead.query
    
    # Sales can only see their own leads + leads owned by marketing
    if not current_user.can_view_all_leads():
        marketing_users = User.query.filter(User.role.ilike('marketing')).all()
        marketing_ids = [u.id for u in marketing_users]
        query = query.filter(
            db.or_(
                SalesLead.owner_id == current_user.id,
                SalesLead.owner_id.in_(marketing_ids)
            )
        )
    
    # Apply current filters
    show_unqualified = request.args.get('show_unqualified', 'false') == 'true'
    if not show_unqualified:
        query = query.filter(SalesLead.leads_status != 'Unqualified')
    
    leads = query.order_by(SalesLead.date_added.desc()).all()
    
    # Prepare data
    data = []
    for lead in leads:
        data.append({
            'Name': lead.name,
            'Company': lead.company,
            'Industry': lead.industry,
            'Position': lead.position,
            'Email': lead.email,
            'Mobile Number': lead.mobile_number,
            'Requirements': lead.requirements,
            'Leads Status': lead.leads_status,
            'Source': lead.source,
            'Event': lead.event,
            'Date Added': str(lead.date_added) if lead.date_added else '',
            'Owner': lead.owner.username if lead.owner else '',
            'Note': lead.note
        })
    
    if data:
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(columns=['Name', 'Company', 'Industry', 'Position', 'Email',
                                   'Mobile Number', 'Requirements', 'Leads Status', 
                                   'Source', 'Event', 'Date Added', 'Owner', 'Note'])
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sales Leads')
    
    output.seek(0)
    
    # Log the export activity
    log_lead_exported(current_user, len(leads), request.remote_addr)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'sales_leads_export_{date.today()}.xlsx'
    )


@leads_bp.route('/import', methods=['POST'])
@login_required
def import_data():
    """Import Sales Leads from Excel."""
    if not current_user.can_access_leads():
        flash('You do not have permission to access Sales Leads.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('leads.index'))
    
    file = request.files['file']
    
    if not file.filename or not allowed_file(file.filename):
        flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)', 'danger')
        return redirect(url_for('leads.index'))
    
    try:
        df = import_from_excel(file)
        
        # Validate each row
        all_errors = []
        valid_rows = []
        
        for idx, row in df.iterrows():
            # Convert row to dict with proper keys
            row_dict = row.to_dict()
            # Normalize keys (remove spaces, periods, parentheses, lowercase, dedupe underscores)
            normalized = {}
            for k, v in row_dict.items():
                k2 = k.strip().replace(' ', '_').replace('.', '_').replace('-', '_').replace('(', '').replace(')', '').lower()
                # Remove duplicate underscores
                while '__' in k2:
                    k2 = k2.replace('__', '_')
                normalized[k2] = v
            row_dict = normalized
            
            # Clean all values - comprehensive type handling
            cleaned_row = {}
            for key, val in row_dict.items():
                if val is None:
                    cleaned_row[key] = None
                elif isinstance(val, float):
                    if val != val or str(val).lower() == 'nan':
                        cleaned_row[key] = None
                    else:
                        # Check if this looks like an Excel date (numeric around 40000-50000)
                        # 包括 date_added, date 等常见日期字段
                        if key.endswith('_date') or key == 'date_added' or key == 'added':
                            if 40000 < val < 60000:
                                cleaned_row[key] = excel_date_to_str(val)
                            else:
                                cleaned_row[key] = val
                        else:
                            cleaned_row[key] = val
                elif isinstance(val, int):
                    # Check if this looks like an Excel date (numeric around 40000-50000)
                    if key.endswith('_date') or key == 'date_added' or key == 'added':
                        if 40000 < val < 60000:
                            cleaned_row[key] = excel_date_to_date(val)
                        else:
                            cleaned_row[key] = val
                    else:
                        cleaned_row[key] = val
                elif hasattr(val, 'strftime'):  # pandas Timestamp/datetime (but not NaT)
                    if pd.isna(val):
                        cleaned_row[key] = None
                    else:
                        cleaned_row[key] = val.date()  # Convert to date object
                elif isinstance(val, str):
                    val_clean = val.strip()
                    if val_clean.lower() == 'nan' or val_clean == '':
                        cleaned_row[key] = None
                    elif key.endswith('_date') or key == 'date_added' or key == 'added':
                        # This is a date string - try multiple formats including YYYY-MM-DD
                        from utils import validate_date
                        parsed_date = validate_date(val_clean)
                        if parsed_date:
                            cleaned_row[key] = parsed_date
                        else:
                            # Still keep the original string as fallback
                            cleaned_row[key] = val_clean
                    else:
                        cleaned_row[key] = val_clean
                else:
                    cleaned_row[key] = val
            
            errors = validate_sales_lead_import(cleaned_row)
            
            if errors:
                all_errors.append(f"Row {idx + 1}: {', '.join(errors)}")
            else:
                valid_rows.append(cleaned_row)
        
        if all_errors:
            flash(f"Import errors found:\n" + "\n".join(all_errors[:10]), 'danger')
            if len(all_errors) > 10:
                flash(f"...and {len(all_errors) - 10} more errors", 'info')
            return redirect(url_for('leads.index'))
        
        # Import valid rows
        imported_count = 0
        with disable_metrics_events():
            for row in valid_rows:
                try:
                    # Find owner by username
                    owner = None
                    if row.get('owner'):
                        owner = User.query.filter_by(username=row.get('owner')).first()
                    
                    lead = SalesLead(
                        name=row.get('name') or None,
                        company=row.get('company') or None,
                        industry=row.get('industry') or None,
                        position=row.get('position') or None,
                        email=row.get('email') or None,
                        mobile_number=row.get('mobile_number') or None,
                        requirements=row.get('requirements') or None,
                        leads_status=row.get('leads_status', 'Waiting to be Contacted'),
                        source=row.get('source') or None,
                        event=row.get('event') or None,
                        date_added=row.get('date_added') or date.today(),
                        owner_id=owner.id if owner else current_user.id,
                        note=row.get('note') or None
                    )
                    
                    db.session.add(lead)
                    imported_count += 1
                    
                except Exception as e:
                    flash(f"Error importing row: {str(e)}", 'danger')
            
            db.session.commit()
        
        # Log the import activity
        if imported_count > 0:
            log_lead_import(current_user, imported_count, request.remote_addr)
        
        flash(f'Successfully imported {imported_count} Sales Leads!', 'success')
        
    except Exception as e:
        flash(f'Error importing file: {str(e)}', 'danger')
    
    return redirect(url_for('leads.index'))


# ============================================================================
# PIPELINE BLUEPRINT
# ============================================================================

pipeline_bp = Blueprint('pipeline', __name__)


@pipeline_bp.route('/')
@login_required
def index():
    """Pipeline Management page."""
    
    # Get filter parameters
    show_lost = request.args.get('show_lost', 'false') == 'true'
    stage_filter = request.args.get('stage', None)
    level_filter = request.args.get('level', None)
    owner_filter = request.args.get('owner', None)
    est_sign_date_from = request.args.get('est_sign_date_from', None)
    est_sign_date_to = request.args.get('est_sign_date_to', None)
    est_activate_date_from = request.args.get('est_activate_date_from', None)
    est_activate_date_to = request.args.get('est_activate_date_to', None)
    
    # Build base query
    query = Pipeline.query
    
    # Filter by access permissions
    if not current_user.is_admin():
        # Get the Pipeline IDs that current_user supports
        supported_pipeline_ids = db.session.query(Pipeline.id).filter(
            Pipeline.support_team.contains(current_user)
        ).subquery()
        query = query.filter(
            or_(
                Pipeline.owner_id == current_user.id,
                Pipeline.id.in_(supported_pipeline_ids)
            )
        )
    
    # Filter by lost status
    if not show_lost:
        query = query.filter(Pipeline.stage != '6b) Deal Lost')
    
    # Apply filters
    if stage_filter:
        query = query.filter(Pipeline.stage == stage_filter)
    if level_filter:
        query = query.filter(func.lower(Pipeline.level) == func.lower(level_filter))
    if owner_filter:
        query = query.filter(Pipeline.owner_id == owner_filter)
    
    # Filter by Est. Sign Date range
    if est_sign_date_from:
        query = query.filter(Pipeline.est_sign_date >= est_sign_date_from)
    if est_sign_date_to:
        query = query.filter(Pipeline.est_sign_date <= est_sign_date_to)
    
    # Filter by Est. Activate Date range
    if est_activate_date_from:
        query = query.filter(Pipeline.est_act_date >= est_activate_date_from)
    if est_activate_date_to:
        query = query.filter(Pipeline.est_act_date <= est_activate_date_to)
    
    # Order by date_added descending
    query = query.order_by(Pipeline.date_added.desc())
    
    # Get total count
    total_count = query.count()
    
    # Calculate total TCV
    total_tcv = sum(p.tcv_usd for p in query.all())
    
    # Paginate
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    pipelines = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get users who have pipelines for owner dropdown (only show users with pipelines)
    users = db.session.query(User).join(Pipeline).filter(
        User.is_active == True
    ).distinct().order_by(User.username).all()
    
    # Get column preferences
    prefs = current_user.get_column_preferences('pipeline')
    selected_columns = prefs.get('columns', ['company', 'product', 'owner', 'stage', 'level', 'tcv_usd'])
    
    # Available columns definition (all fields from Pipeline model)
    available_columns = [
        # Basic info
        {'key': 'company', 'label': _('Company'), 'sortable': True},
        {'key': 'name', 'label': _('Contact'), 'sortable': True},
        {'key': 'industry', 'label': _('Industry'), 'sortable': True},
        {'key': 'position', 'label': _('Position'), 'sortable': True},
        {'key': 'email', 'label': _('Email'), 'sortable': True},
        {'key': 'mobile_number', 'label': _('Mobile'), 'sortable': True},
        
        # Product & Value
        {'key': 'product', 'label': _('Product'), 'sortable': True},
        {'key': 'tcv_usd', 'label': _('TCV'), 'sortable': True},
        {'key': 'mrc_usd', 'label': _('MRC'), 'sortable': True},
        {'key': 'otc_usd', 'label': _('OTC'), 'sortable': True},
        {'key': 'gp', 'label': _('Gross Profit'), 'sortable': True},
        {'key': 'contract_term_yrs', 'label': _('Term (Yrs)'), 'sortable': True},
        {'key': 'gp_margin', 'label': _('GP %'), 'sortable': True},
        
        # Ownership & Stage
        {'key': 'owner', 'label': _('Owner'), 'sortable': True},
        {'key': 'stage', 'label': _('Stage'), 'sortable': True},
        {'key': 'win_rate', 'label': _('Win Rate'), 'sortable': True},
        
        # Dates
        {'key': 'est_sign_date', 'label': _('Est. Sign'), 'sortable': True},
        {'key': 'est_act_date', 'label': _('Est. Activate'), 'sortable': True},
        {'key': 'award_date', 'label': _('Award Date'), 'sortable': True},
        {'key': 'proposal_sent_date', 'label': _('Proposal Sent'), 'sortable': True},
        {'key': 'date_added', 'label': _('Date Added'), 'sortable': True},
        
        # Additional
        {'key': 'follow_up', 'label': _('Follow-up'), 'sortable': False},
        {'key': 'comments', 'label': _('Comments'), 'sortable': False},
        {'key': 'stuckpoint', 'label': _('Current Stuckpoint'), 'sortable': False},
    ]
    
    # Default columns keys if none selected
    default_columns = ['company', 'product', 'owner', 'stage', 'tcv_usd']
    
    # If preferences exist, use them
    if selected_columns:
        default_columns = selected_columns
    
    # Build visible_columns as full column objects
    visible_columns = []
    visible_column_keys = []
    for col_key in default_columns:
        for col in available_columns:
            if col['key'] == col_key:
                visible_columns.append(col)
                visible_column_keys.append(col_key)
                break
    
    return render_template('pipeline/index.html',
                          pipelines=pipelines,
                          total_count=total_count,
                          total_tcv=total_tcv,
                          users=users,
                          show_lost=show_lost,
                          stage_filter=stage_filter,
                          level_filter=level_filter,
                          owner_filter=owner_filter,
                          est_sign_date_from=est_sign_date_from,
                          est_sign_date_to=est_sign_date_to,
                          est_activate_date_from=est_activate_date_from,
                          est_activate_date_to=est_activate_date_to,
                          format_currency=format_currency,
                          date=date,
                          available_columns=available_columns,
                          default_columns=default_columns,
                          visible_columns=visible_columns,
                          visible_column_keys=visible_column_keys)


# ============================================================================
# PIPELINE API
# ============================================================================

@pipeline_bp.route('/api/kanban-data')
@login_required
def kanban_data():
    """Get Kanban board data as JSON."""
    owner_filter = request.args.get('owner', None)
    
    # Build query
    query = Pipeline.query
    
    # Filter by access permissions
    if not current_user.is_admin():
        # Get the Pipeline IDs that current_user supports
        supported_pipeline_ids = db.session.query(Pipeline.id).filter(
            Pipeline.support_team.contains(current_user)
        ).subquery()
        query = query.filter(
            or_(
                Pipeline.owner_id == current_user.id,
                Pipeline.id.in_(supported_pipeline_ids)
            )
        )
    
    # Apply owner filter
    if owner_filter:
        query = query.filter(Pipeline.owner_id == int(owner_filter))
    
    # Get all pipelines (no pagination for Kanban)
    pipelines = query.order_by(Pipeline.date_added.desc()).all()
    
    # Group by stage
    stages = ['1) Prospecting', '2) Lead Qualified', '3) Demo/Meeting', 
              '4) Proposal Submitted', '5) Negotiation', '6a) Deal Won', '6b) Deal Lost', '7) Activated']
    
    kanban_data = {}
    for stage in stages:
        stage_pipelines = [p for p in pipelines if p.stage == stage]
        kanban_data[stage] = [{
            'id': p.id,
            'company': p.company or '',
            'name': p.name or '',
            'product': p.product or '',
            'tcv_usd': p.tcv_usd or 0,
            'owner': p.owner.username if p.owner else '',
            'level': p.level or '',
            'win_rate': p.win_rate or 0,
            'est_sign_date': p.est_sign_date.strftime('%Y-%m-%d') if p.est_sign_date else None,
            'date_added': p.date_added.strftime('%Y-%m-%d') if p.date_added else None,
        } for p in stage_pipelines]
    
    return jsonify({'success': True, 'data': kanban_data})


@pipeline_bp.route('/api/update-stage', methods=['POST'])
@login_required
def update_stage():
    """Update pipeline stage via drag-drop."""
    data = request.get_json()
    
    pipeline_id = data.get('pipeline_id')
    new_stage = data.get('stage')
    
    if not pipeline_id or not new_stage:
        return jsonify({'success': False, 'error': 'Missing pipeline_id or stage'})
    
    pipeline = Pipeline.query.get(pipeline_id)
    if not pipeline:
        return jsonify({'success': False, 'error': 'Pipeline not found'})
    
    # Check access
    if not current_user.can_access_pipeline(pipeline):
        return jsonify({'success': False, 'error': 'Permission denied'})
    
    old_stage = pipeline.stage
    pipeline.stage = new_stage
    
    # Recalculate metrics
    calculate_pipeline_metrics(pipeline)
    
    db.session.commit()
    
    # Log the activity
    log_pipeline_stage_changed(current_user, pipeline, old_stage, new_stage, request.remote_addr)
    
    return jsonify({'success': True})


@pipeline_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """Add new Pipeline entry."""
    
    if request.method == 'POST':
        try:
            pipeline = Pipeline(
                name=request.form.get('name'),
                company=request.form.get('company'),
                industry=request.form.get('industry'),
                position=request.form.get('position'),
                email=request.form.get('email'),
                mobile_number=request.form.get('mobile_number'),
                product=request.form.get('product'),
                mrc_usd=validate_numeric(request.form.get('mrc_usd'), 'MRC USD'),
                otc_usd=validate_numeric(request.form.get('otc_usd'), 'OTC USD'),
                contract_term_yrs=validate_numeric(request.form.get('contract_term_yrs', 1), 'Contract Term'),
                gp_margin=validate_numeric(request.form.get('gp_margin', 0), 'GP Margin') / 100,
                est_sign_date=validate_date(request.form.get('est_sign_date')),
                est_act_date=validate_date(request.form.get('est_act_date')),
                award_date=validate_date(request.form.get('award_date')),
                proposal_sent_date=validate_date(request.form.get('proposal_sent_date')),
                win_rate=validate_numeric(request.form.get('win_rate', 0), 'Win Rate') / 100,
                stage=request.form.get('stage', 'Prospecting'),
                level=request.form.get('level', 'Stretch'),
                comments=request.form.get('comments'),
                owner_id=request.form.get('owner_id', current_user.id),
                date_added=date.today()
            )
            
            # Calculate TCV and GP
            calculate_pipeline_metrics(pipeline)
            
            # Handle support team (multi-select)
            support_ids = request.form.getlist('support')
            for uid in support_ids:
                user = User.query.get(int(uid))
                if user:
                    pipeline.support_team.append(user)
            
            db.session.add(pipeline)
            db.session.commit()
            
            # Log the activity
            log_pipeline_created(current_user, pipeline, request.remote_addr)
            
            flash('Pipeline entry added successfully!', 'success')
            
            if 'continue' in request.form:
                return redirect(url_for('pipeline.add'))
            else:
                return redirect(url_for('pipeline.index'))
                
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding Pipeline: {str(e)}', 'danger')
    
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    support_users = User.query.filter_by(is_active=True).order_by(User.username).all()
    
    return render_template('pipeline/form.html', 
                          pipeline=None, 
                          users=users,
                          support_users=support_users,
                          title='Add Pipeline')


@pipeline_bp.route('/<int:pipeline_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(pipeline_id):
    """Edit Pipeline entry."""
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    # Check access
    if not current_user.can_access_pipeline(pipeline):
        flash('You do not have permission to edit this Pipeline.', 'danger')
        return redirect(url_for('pipeline.index'))
    
    if request.method == 'POST':
        try:
            pipeline.name = request.form.get('name')
            pipeline.company = request.form.get('company')
            pipeline.industry = request.form.get('industry')
            pipeline.position = request.form.get('position')
            pipeline.email = request.form.get('email')
            pipeline.mobile_number = request.form.get('mobile_number')
            pipeline.product = request.form.get('product')
            pipeline.mrc_usd = validate_numeric(request.form.get('mrc_usd'), 'MRC USD')
            pipeline.otc_usd = validate_numeric(request.form.get('otc_usd'), 'OTC USD')
            pipeline.contract_term_yrs = validate_numeric(request.form.get('contract_term_yrs', 1), 'Contract Term')
            pipeline.gp_margin = validate_numeric(request.form.get('gp_margin', 0), 'GP Margin') / 100
            pipeline.est_sign_date = validate_date(request.form.get('est_sign_date'))
            pipeline.est_act_date = validate_date(request.form.get('est_act_date'))
            pipeline.award_date = validate_date(request.form.get('award_date'))
            pipeline.proposal_sent_date = validate_date(request.form.get('proposal_sent_date'))
            pipeline.win_rate = validate_numeric(request.form.get('win_rate', 0), 'Win Rate') / 100
            
            old_stage = pipeline.stage
            new_stage = request.form.get('stage')
            pipeline.stage = new_stage
            
            pipeline.level = request.form.get('level')
            pipeline.comments = request.form.get('comments')
            pipeline.follow_up = request.form.get('follow_up')
            pipeline.stuckpoint = request.form.get('stuckpoint')
            pipeline.owner_id = request.form.get('owner_id')
            
            # Update support team
            support_ids = request.form.getlist('support')
            pipeline.support_team = []
            for uid in support_ids:
                user = User.query.get(int(uid))
                if user:
                    pipeline.support_team.append(user)
            
            # Recalculate metrics
            calculate_pipeline_metrics(pipeline)
            
            db.session.commit()
            
            # Log stage change
            if old_stage != new_stage:
                log_pipeline_stage_changed(current_user, pipeline, old_stage, new_stage, request.remote_addr)
            
            flash('Pipeline entry updated successfully!', 'success')
            
            return redirect(url_for('pipeline.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating Pipeline: {str(e)}', 'danger')
    
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    support_users = User.query.filter_by(is_active=True).order_by(User.username).all()
    
    return render_template('pipeline/form.html',
                          pipeline=pipeline,
                          users=users,
                          support_users=support_users,
                          title='Edit Pipeline')


@pipeline_bp.route('/<int:pipeline_id>/delete', methods=['POST'])
@login_required
def delete(pipeline_id):
    """Delete Pipeline entry."""
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    if not current_user.can_access_pipeline(pipeline):
        flash('You do not have permission to delete this Pipeline.', 'danger')
        return redirect(url_for('pipeline.index'))
    
    try:
        db.session.delete(pipeline)
        db.session.commit()
        
        # Log the activity
        log_pipeline_deleted(current_user, pipeline_id, pipeline.company, request.remote_addr)
        
        flash('Pipeline entry deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting Pipeline: {str(e)}', 'danger')
    
    return redirect(url_for('pipeline.index'))


@pipeline_bp.route('/<int:pipeline_id>/followup-data')
@login_required
def get_followup_data(pipeline_id):
    """Get follow-up data as HTML for modal."""
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    if not current_user.can_access_pipeline(pipeline):
        return '<div class="alert alert-danger">Permission denied</div>'
    
    # Build follow-up history HTML
    history_html = ''
    if pipeline.follow_up:
        history_html = f'''
        <div class="mb-4">
            <label class="form-label small text-muted mb-1">
                <i class="fas fa-history me-1"></i>{_('Follow-up History')}
            </label>
            <textarea class="form-control bg-light" rows="10" readonly 
                style="resize: vertical; font-size: 0.875rem; max-height: 300px; overflow-y: auto;">{pipeline.follow_up}</textarea>
        </div>
        '''
    
    # Build stage options
    stage_options = ''.join([
        f'<option value="{stage}" {"selected" if stage == pipeline.stage else ""}>{_(stage)}</option>'
        for stage in Pipeline.STAGE_OPTIONS
    ])
    
    # Build form HTML
    form_html = f'''
    {history_html}
    <input type="hidden" name="pipeline_id" value="{pipeline.id}">
    <div class="row g-3">
        <div class="col-12">
            <label class="form-label">{_('Follow-up Notes')} *</label>
            <textarea name="followup_text" class="form-control" rows="4" required placeholder="{_('Describe what was discussed...')}"></textarea>
        </div>
        <div class="col-md-6">
            <label class="form-label">{_('Current Stuckpoint')}</label>
            <textarea name="stuckpoint_text" class="form-control" rows="2" placeholder="{_('What is blocking progress?')}">{pipeline.stuckpoint or ''}</textarea>
        </div>
        <div class="col-md-6">
            <label class="form-label">{_('Next Steps / To-do')}</label>
            <textarea name="todo_text" class="form-control" rows="2" placeholder="{_('What needs to be done next?')}"></textarea>
        </div>
        <div class="col-md-6">
            <label class="form-label">{_('To-do Due Date')}</label>
            <input type="date" name="todo_due_date" class="form-control">
        </div>
        <div class="col-md-6">
            <label class="form-label">{_('Current Stage')}</label>
            <select name="stage" class="form-select">
                {stage_options}
            </select>
        </div>
    </div>
    '''
    
    return form_html


@pipeline_bp.route('/<int:pipeline_id>/add-followup', methods=['POST'])
@login_required
def add_followup(pipeline_id):
    """Add follow-up to Pipeline entry."""
    import traceback
    
    print(f"[DEBUG] add_followup called for pipeline {pipeline_id}")
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    print(f"[DEBUG] Pipeline found: {pipeline.company}")
    
    if not current_user.can_access_pipeline(pipeline):
        print("[DEBUG] Permission denied")
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    try:
        followup_text = request.form.get('followup_text', '').strip()
        stuckpoint_text = request.form.get('stuckpoint_text', '').strip()
        todo_text = request.form.get('todo_text', '').strip()
        todo_due_date = request.form.get('todo_due_date', '').strip()
        
        print(f"[DEBUG] followup_text: {followup_text[:50]}...")
        
        if not followup_text:
            print("[DEBUG] No followup text provided")
            return jsonify({'success': False, 'error': 'Follow-up text is required'})
        
        # Add follow-up
        print("[DEBUG] Calling pipeline.add_followup()...")
        pipeline.add_followup(
            followup_text=followup_text,
            stuckpoint_text=stuckpoint_text,
            todo_text=todo_text if todo_text else None,
            todo_due_date=validate_date(todo_due_date) if todo_text else None,
            user_id=current_user.id
        )
        
        print("[DEBUG] Committing to database...")
        db.session.commit()
        
        # Log the activity
        log_followup_created(current_user, pipeline, request.remote_addr)
        
        print("[DEBUG] Success!")
        
        return jsonify({'success': True, 'message': 'Follow-up added successfully!'})
        
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@pipeline_bp.route('/import-template')
@login_required
def import_template():
    """Download Excel import template."""
    
    columns = ['Name', 'Company', 'Industry', 'Position', 'Email', 'Mobile Number',
              'Owner', 'Support', 'Product', 'TCV USD', 'Contract Term (Yrs)',
              'MRC USD', 'OTC USD', 'GP Margin', 'Est. Sign Date', 'Est. Act. Date',
              'Win Rate', 'Stage', 'Award Date', 'Proposal Sent Date', 'Level', 'Comments']
    
    output = create_excel_template(columns, 'pipeline_template.xlsx')
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='pipeline_template.xlsx'
    )


@pipeline_bp.route('/export')
@login_required
def export():
    """Export Pipeline to Excel."""
    from dateutil.relativedelta import relativedelta
    
    # Get filtered pipelines
    query = Pipeline.query
    
    if not current_user.is_admin():
        # Get the Pipeline IDs that current_user supports
        supported_pipeline_ids = db.session.query(Pipeline.id).filter(
            Pipeline.support_team.contains(current_user)
        ).subquery()
        query = query.filter(
            or_(
                Pipeline.owner_id == current_user.id,
                Pipeline.id.in_(supported_pipeline_ids)
            )
        )
    
    pipelines = query.order_by(Pipeline.date_added.desc()).all()
    
    # Find reference date for column naming (use earliest est_act_date or current month)
    reference_dates = [p.est_act_date for p in pipelines if p.est_act_date]
    if reference_dates:
        ref_date = min(reference_dates)
    else:
        ref_date = date.today()
    
    # Create month column names based on reference date
    month_columns = {}
    for i in range(1, 13):
        month_date = ref_date + relativedelta(months=i-1)
        month_columns[f'm{i}'] = month_date.strftime('%b %Y')  # e.g., Feb 2026
    
    # Prepare data
    data = []
    for p in pipelines:
        support_names = '/'.join([u.username for u in p.support_team])
        
        row_data = {
            'Name': p.name,
            'Company': p.company,
            'Industry': p.industry,
            'Position': p.position,
            'Email': p.email,
            'Mobile Number': p.mobile_number,
            'Owner': p.owner.username if p.owner else '',
            'Support': support_names,
            'Product': p.product,
            'TCV USD': p.tcv_usd,
            'Contract Term (Yrs)': p.contract_term_yrs,
            'MRC USD': p.mrc_usd,
            'OTC USD': p.otc_usd,
            'GP Margin': f"{p.gp_margin * 100:.0f}%",
            'GP': p.get_gp(),
            'MG': p.mg,
            'Est. Sign Date': p.est_sign_date.strftime('%Y-%m-%d') if p.est_sign_date else '',
            'Est. Act. Date': p.est_act_date.strftime('%Y-%m-%d') if p.est_act_date else '',
            'Win Rate': f"{p.win_rate * 100:.0f}%",
            'Stage': p.stage,
            'Award Date': p.award_date.strftime('%Y-%m-%d') if p.award_date else '',
            'Proposal Sent Date': p.proposal_sent_date.strftime('%Y-%m-%d') if p.proposal_sent_date else '',
            'Level': p.level,
            'Stuckpoint': p.stuckpoint or '',
            'Follow-up': p.follow_up or '',
            'Comments': p.comments or '',
            'Date Added': p.date_added.strftime('%Y-%m-%d') if p.date_added else '',
            'Created At': p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '',
            'Updated At': p.updated_at.strftime('%Y-%m-%d %H:%M') if p.updated_at else ''
        }
        
        # Add M1-M12 values (columns will be renamed to actual months)
        for i in range(1, 13):
            row_data[f'm{i}'] = getattr(p, f'm{i}')
        
        data.append(row_data)
    
    if data:
        df = pd.DataFrame(data)
        # Rename m1-m12 columns to actual month names
        df = df.rename(columns=month_columns)
    else:
        # Create empty dataframe with proper column names
        base_columns = ['Name', 'Company', 'Industry', 'Position', 'Email',
                       'Mobile Number', 'Owner', 'Support', 'Product', 
                       'TCV USD', 'Contract Term (Yrs)', 'MRC USD', 'OTC USD',
                       'GP Margin', 'GP', 'MG', 'Est. Sign Date', 'Est. Act. Date',
                       'Win Rate', 'Stage', 'Award Date', 'Proposal Sent Date', 'Level', 
                       'Stuckpoint', 'Follow-up', 'Comments', 'Date Added', 
                       'Created At', 'Updated At']
        df = pd.DataFrame(columns=base_columns + list(month_columns.values()))
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Pipeline')
    
    output.seek(0)
    
    # Log the export activity
    log_pipeline_exported(current_user, len(pipelines), request.remote_addr)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'pipeline_export_{date.today()}.xlsx'
    )


@pipeline_bp.route('/import', methods=['POST'])
@login_required
def import_data():
    """Import Pipeline from Excel."""
    
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('pipeline.index'))
    
    file = request.files['file']
    
    if not file.filename or not allowed_file(file.filename):
        flash('Invalid file type. Please upload an Excel file (.xlsx or .xls)', 'danger')
        return redirect(url_for('pipeline.index'))
    
    try:
        df = import_from_excel(file)
        
        # Validate each row
        all_errors = []
        valid_rows = []
        
        # Field type definitions
        numeric_fields = ['tcv_usd', 'mrc_usd', 'otc_usd', 'gp_margin', 'win_rate', 'gp', 
                         'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']
        integer_fields = ['contract_term_yrs', 'id', 'owner_id', 'sales_lead_id']
        date_fields = ['est_sign_date', 'est_act_date', 'award_date', 'proposal_sent_date', 'date_added']
        
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            
            # Normalize keys (remove spaces, periods, parentheses, lowercase, dedupe underscores)
            normalized = {}
            for k, v in row_dict.items():
                k2 = k.strip().replace(' ', '_').replace('.', '_').replace('-', '_').replace('(', '').replace(')', '').lower()
                # Remove duplicate underscores
                while '__' in k2:
                    k2 = k2.replace('__', '_')
                normalized[k2] = v
            row_dict = normalized
            
            # Clean all values - comprehensive type handling
            cleaned_row = {}
            for key, val in row_dict.items():
                if val is None:
                    cleaned_row[key] = None
                elif isinstance(val, float):
                    if val != val or str(val).lower() == 'nan':  # NaN
                        cleaned_row[key] = 0 if key in numeric_fields else None
                    else:
                        # Check if this looks like an Excel date (numeric around 40000-50000)
                        if key.endswith('_date') or key == 'date_added' or key == 'added':
                            if 40000 < val < 60000:
                                cleaned_row[key] = excel_date_to_date(val)
                            else:
                                cleaned_row[key] = round(val, 4) if key in numeric_fields else val
                        else:
                            cleaned_row[key] = round(val, 4) if key in numeric_fields else val
                elif isinstance(val, int):
                    # Check if this looks like an Excel date (numeric around 40000-50000)
                    if key.endswith('_date') or key == 'date_added' or key == 'added':
                        if 40000 < val < 60000:
                            cleaned_row[key] = excel_date_to_date(val)
                        else:
                            cleaned_row[key] = val
                    else:
                        cleaned_row[key] = val
                elif hasattr(val, 'strftime'):  # pandas Timestamp/datetime (but not NaT)
                    if pd.isna(val):
                        cleaned_row[key] = None
                    else:
                        cleaned_row[key] = val.date()  # Convert to date object
                elif isinstance(val, str):
                    val_clean = val.strip()
                    if val_clean.lower() == 'nan' or val_clean == '':
                        cleaned_row[key] = 0 if key in numeric_fields else None
                    elif key.endswith('_date') or key == 'date_added' or key == 'added':
                        # This is a date string - use validate_date for all formats
                        date_val = validate_date(val_clean)
                        if date_val:
                            cleaned_row[key] = date_val
                        else:
                            cleaned_row[key] = None
                    elif key in numeric_fields:
                        try:
                            cleaned_row[key] = round(float(val_clean), 4)
                        except:
                            cleaned_row[key] = 0
                    else:
                        cleaned_row[key] = val_clean if val_clean else None
                else:
                    cleaned_row[key] = val
            
            errors = validate_pipeline_import(cleaned_row)
            
            if errors:
                all_errors.append(f"Row {idx + 1}: {', '.join(errors)}")
            else:
                # Normalize stage values to correct case
                stage = cleaned_row.get('stage')
                if stage:
                    stage_normalize_map = {
                        '1) prospecting': '1) Prospecting',
                        '2) lead qualified': '2) Lead Qualified',
                        '2) lead qualification': '2) Lead Qualified',
                        '3) demo/meeting': '3) Demo/Meeting',
                        '4) proposal submitted': '4) Proposal Submitted',
                        '5) negotiation': '5) Negotiation',
                        '6a) deal won': '6a) Deal Won',
                        '6b) deal lost': '6b) Deal Lost',
                    }
                    stage_lower = stage.lower().strip()
                    cleaned_row['stage'] = stage_normalize_map.get(stage_lower, stage)
                valid_rows.append(cleaned_row)
        
        if all_errors:
            flash(f"Import errors found:\n" + "\n".join(all_errors[:10]), 'danger')
            if len(all_errors) > 10:
                flash(f"...and {len(all_errors) - 10} more errors", 'info')
            return redirect(url_for('pipeline.index'))
        
        # Import valid rows
        imported_count = 0
        for row_num, row in enumerate(valid_rows):
            try:
                # Find owner by username
                owner = None
                if row.get('owner'):
                    owner = User.query.filter_by(username=row.get('owner')).first()
                
                # Handle support team
                support_users = []
                if row.get('support'):
                    support_names = str(row.get('support')).split('/')
                    for name in support_names:
                        user = User.query.filter_by(username=name.strip()).first()
                        if user:
                            support_users.append(user)
                
                # Ensure name is not empty - use company or generate placeholder
                pipeline_name = row.get('name')
                if not pipeline_name or str(pipeline_name).strip() == '':
                    pipeline_name = row.get('company') or f'Pipeline-{row_num + 1}'
                
                pipeline = Pipeline(
                    name=pipeline_name,
                    company=row.get('company'),
                    industry=row.get('industry'),
                    position=row.get('position'),
                    email=row.get('email'),
                    mobile_number=row.get('mobile_number'),
                    product=row.get('product'),
                    sales_lead_id=row.get('sales_lead_id'),
                    mrc_usd=row.get('mrc_usd', 0),
                    otc_usd=row.get('otc_usd', 0),
                    contract_term_yrs=row.get('contract_term_yrs', 1),
                    gp_margin=row.get('gp_margin', 0),
                    est_sign_date=row.get('est_sign_date'),
                    est_act_date=row.get('est_act_date'),
                    award_date=row.get('award_date'),
                    proposal_sent_date=row.get('proposal_sent_date'),
                    win_rate=row.get('win_rate', 0),
                    stage=row.get('stage', '1) Prospecting'),
                    level=row.get('level', 'Stretch'),
                    comments=row.get('comments'),
                    stuckpoint=row.get('stuckpoint'),
                    follow_up=row.get('follow_up'),
                    owner_id=owner.id if owner else current_user.id,
                    date_added=date.today()
                )
                
                # Calculate TCV
                calculate_pipeline_metrics(pipeline)
                
                # Add support users
                for user in support_users:
                    pipeline.support_team.append(user)
                
                db.session.add(pipeline)
                imported_count += 1
                
            except Exception as e:
                flash(f"Error importing row {row_num + 1}: {str(e)}", 'danger')
        
        db.session.commit()
        
        # Log the import activity
        if imported_count > 0:
            log_pipeline_imported(current_user, imported_count, request.remote_addr)
        
        flash(f'Successfully imported {imported_count} Pipeline entries!', 'success')
        
    except Exception as e:
        flash(f'Error importing file: {str(e)}', 'danger')
    
    return redirect(url_for('pipeline.index'))


# ============================================================================
# TASKS BLUEPRINT
# ============================================================================

tasks_bp = Blueprint('tasks', __name__)


@tasks_bp.route('/')
@login_required
def index():
    """Task Management page."""
    
    # Get all tasks accessible to user
    query = Task.query
    
    if not current_user.is_admin():
        query = query.filter(Task.owner_id == current_user.id)
    
    # Check for overdue tasks
    for task in query.all():
        task.check_overdue()
    db.session.commit()
    
    # Order by due date, then by status
    query = query.order_by(Task.due_date.asc().nullsfirst(), Task.status)
    
    tasks = query.all()
    
    # Group by status
    overdue_tasks = [t for t in tasks if t.status == 'Overdue']
    in_progress_tasks = [t for t in tasks if t.status == 'In Progress']
    completed_tasks = [t for t in tasks if t.status == 'Completed']
    
    # Get all users for owner dropdown
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    
    return render_template('tasks.html',
                          overdue_tasks=overdue_tasks,
                          in_progress_tasks=in_progress_tasks,
                          completed_tasks=completed_tasks,
                          users=users,
                          current_user=current_user)


@tasks_bp.route('/add', methods=['POST'])
@login_required
def add():
    """Add new Task."""
    
    try:
        content = request.form.get('content', '').strip()
        company = request.form.get('company', '').strip()
        due_date = validate_date(request.form.get('due_date'))
        
        if not content:
            flash('Task content is required', 'danger')
            return redirect(url_for('tasks.index'))
        
        task = Task(
            content=content,
            company=company if company else None,
            due_date=due_date,
            owner_id=current_user.id,
            status='In Progress'
        )
        
        db.session.add(task)
        db.session.commit()
        
        # Log the activity
        log_task_created(current_user, task, request.remote_addr)
        
        flash('Task added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding task: {str(e)}', 'danger')
    
    return redirect(url_for('tasks.index'))


@tasks_bp.route('/<int:task_id>/complete', methods=['POST'])
@login_required
def complete(task_id):
    """Mark task as completed."""
    
    task = Task.query.get_or_404(task_id)
    
    # Check ownership
    if not current_user.is_admin() and task.owner_id != current_user.id:
        flash('You do not have permission to complete this task.', 'danger')
        return redirect(url_for('tasks.index'))
    
    try:
        task.status = 'Completed'
        db.session.commit()
        
        # Log the activity
        log_task_completed(current_user, task, request.remote_addr)
        
        flash('Task marked as completed!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error completing task: {str(e)}', 'danger')
    
    return redirect(url_for('tasks.index'))


@tasks_bp.route('/<int:task_id>/reopen', methods=['POST'])
@login_required
def reopen(task_id):
    """Reopen a completed task."""
    
    task = Task.query.get_or_404(task_id)
    
    # Check ownership
    if not current_user.is_admin() and task.owner_id != current_user.id:
        flash('You do not have permission to reopen this task.', 'danger')
        return redirect(url_for('tasks.index'))
    
    try:
        task.status = 'In Progress'
        db.session.commit()
        
        # Log the activity
        log_task_reopened(current_user, task, request.remote_addr)
        
        flash('Task reopened!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error reopening task: {str(e)}', 'danger')
    
    return redirect(url_for('tasks.index'))


@tasks_bp.route('/<int:task_id>/edit', methods=['POST'])
@login_required
def edit_task(task_id):
    """Edit task."""
    
    task = Task.query.get_or_404(task_id)
    
    # Check ownership
    if not current_user.is_admin() and task.owner_id != current_user.id:
        flash('You do not have permission to edit this task.', 'danger')
        return redirect(url_for('tasks.index'))
    
    try:
        task.content = request.form.get('content')
        task.company = request.form.get('company')
        task.owner_id = request.form.get('owner_id')
        due_date = request.form.get('due_date')
        task.due_date = datetime.strptime(due_date, '%Y-%m-%d').date() if due_date else None
        
        db.session.commit()
        
        # Log the activity
        log_task_edited(current_user, task_id, task.content, request.remote_addr)
        
        flash('Task updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating task: {str(e)}', 'danger')
    
    return redirect(url_for('tasks.index'))


@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete(task_id):
    """Delete task."""
    
    task = Task.query.get_or_404(task_id)
    
    # Check ownership
    if not current_user.is_admin() and task.owner_id != current_user.id:
        flash('You do not have permission to delete this task.', 'danger')
        return redirect(url_for('tasks.index'))
    
    try:
        db.session.delete(task)
        db.session.commit()
        
        # Log the activity
        log_task_deleted(current_user, task_id, request.remote_addr)
        
        flash('Task deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting task: {str(e)}', 'danger')
    
    return redirect(url_for('tasks.index'))


# ============================================================================
# ADMIN BLUEPRINT
# ============================================================================

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/users')
@login_required
def users():
    """User Management page (admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    users = User.query.order_by(User.username).all()
    
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    """Add new user (admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role', 'sales')
        password = request.form.get('password', '').strip()
        
        if not username:
            flash('Username is required', 'danger')
            return redirect(url_for('admin.users'))
        
        # Check if username exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('admin.users'))
        
        user = User(
            username=username,
            email=email if email else None,
            role=role
        )
        user.set_password(password if password else 'bitcrm')
        
        db.session.add(user)
        db.session.commit()
        
        # Log the activity
        log_user_created(current_user, username, request.remote_addr)
        
        flash(f'User {username} created successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating user: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
def edit_user(user_id):
    """Edit user (admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    try:
        user.username = request.form.get('username', '').strip()
        user.email = request.form.get('email', '').strip() or None
        user.role = request.form.get('role', 'sales')
        
        db.session.commit()
        flash(f'User {user.username} updated successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating user: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_user(user_id):
    """Toggle user active status (admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent disabling yourself
    if user.id == current_user.id:
        flash('You cannot disable your own account.', 'danger')
        return redirect(url_for('admin.users'))
    
    try:
        user.is_active = not user.is_active
        status = 'activated' if user.is_active else 'deactivated'
        db.session.commit()
        
        # Log the activity
        log_user_status_changed(current_user, user.username, user.is_active, request.remote_addr)
        
        flash(f'User {user.username} {status}!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error toggling user: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def reset_password(user_id):
    """Reset user password to default (admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(user_id)
    
    try:
        user.set_password('bitcrm')
        db.session.commit()
        flash(f'Password for {user.username} reset to default!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error resetting password: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))


# ============================================================================
# LOGIN LOGS (Admin only)
# ============================================================================

@admin_bp.route('/login-logs')
@login_required
def login_logs():
    """View login/logout activity logs (admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    # Get filter parameters
    action_filter = request.args.get('action', None)
    user_filter = request.args.get('user', None)
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)
    
    # Build query
    query = ActivityLog.query
    
    # Filter by action type (login/logout)
    if action_filter:
        if action_filter == 'login':
            query = query.filter(ActivityLog.action_type.like('%Login%'))
        elif action_filter == 'logout':
            query = query.filter(ActivityLog.action_type.like('%Logout%'))
        elif action_filter == 'failed':
            query = query.filter(ActivityLog.action_type.like('%Failed%'))
    
    # Filter by user
    if user_filter:
        query = query.filter(ActivityLog.user_name.ilike(f'%{user_filter}%'))
    
    # Filter by date range
    if start_date:
        query = query.filter(ActivityLog.created_at >= start_date)
    if end_date:
        query = query.filter(ActivityLog.created_at <= f'{end_date} 23:59:59')
    
    # Get logs (most recent first)
    logs = query.order_by(ActivityLog.created_at.desc()).limit(500).all()
    
    return render_template('admin/login_logs.html', logs=logs)


@admin_bp.route('/login-logs/clear', methods=['POST'])
@login_required
def clear_login_logs():
    """Clear old login logs (older than 30 days, admin only)."""
    
    if not current_user.is_admin():
        flash('Admin access required.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        deleted = ActivityLog.query.filter(
            ActivityLog.action_type.like('%Login%'),
            ActivityLog.created_at < cutoff_date
        ).delete()
        
        db.session.commit()
        
        flash(f'Cleared {deleted} old login logs.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error clearing logs: {str(e)}', 'danger')
    
    return redirect(url_for('admin.login_logs'))


# ============================================================================
# COLUMN PREFERENCES API
# ============================================================================

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/column-preferences/<page>', methods=['GET'])
@login_required
def get_column_preferences(page):
    """Get user's column preferences for a specific page."""
    valid_pages = ['leads', 'pipeline', 'tasks', 'users']
    
    if page not in valid_pages:
        return jsonify({'error': 'Invalid page'}), 400
    
    prefs = current_user.get_column_preferences(page)
    return jsonify(prefs)


@api_bp.route('/column-preferences/<page>', methods=['POST'])
@login_required
def set_column_preferences(page):
    """Save user's column preferences for a specific page."""
    valid_pages = ['leads', 'pipeline', 'tasks', 'users']
    
    if page not in valid_pages:
        return jsonify({'error': 'Invalid page'}), 400
    
    data = request.get_json()
    
    if not data or 'columns' not in data:
        return jsonify({'error': 'Missing columns data'}), 400
    
    columns = data.get('columns', [])
    order = data.get('order')
    
    try:
        current_user.set_column_preferences(page, columns, order)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Preferences saved'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@api_bp.route('/leads/<int:lead_id>/quick-update', methods=['POST'])
@login_required
def api_quick_update(lead_id):
    """Quick update API endpoint for inline editing."""
    
    if not current_user.can_access_leads():
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    lead = SalesLead.query.get_or_404(lead_id)
    
    try:
        data = request.get_json()
        
        if not data or 'field' not in data or 'value' not in data:
            return jsonify({'success': False, 'error': 'Invalid request data'}), 400
        
        field = data['field']
        value = data['value']
        
        # Validate field exists and is editable
        editable_fields = [
            'name', 'company', 'industry', 'position', 'email', 
            'mobile_number', 'requirements', 'leads_status', 'source', 
            'event', 'date_added', 'owner_id', 'note'
        ]
        
        if field not in editable_fields:
            return jsonify({'success': False, 'error': f'Field {field} is not editable'}), 400
        
        # Handle status changes - log to pipeline comments
        if field == 'leads_status' and lead.leads_status != value:
            # Get or create pipeline
            if not lead.pipeline:
                pipeline = lead.convert_to_pipeline()
                db.session.add(pipeline)
                db.session.flush()  # Get pipeline ID
            
            # Add status change log to pipeline comments
            username = current_user.username if current_user.is_authenticated else 'Unknown'
            today = date.today().strftime('%Y-%m-%d')
            
            if lead.pipeline:
                old_comment = lead.pipeline.comments or ''
                status_action = value  # Qualified or Unqualified
                new_comment = f"{old_comment}\n{today}, {username} {status_action}".strip()
                lead.pipeline.comments = new_comment
        
        # Set the value directly
        setattr(lead, field, value)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Update successful'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# AVAILABLE COLUMNS DEFINITIONS
# ============================================================================

# Define available columns for each page
LEADS_COLUMNS = [
    {'key': 'name', 'label': 'Name', 'sortable': True},
    {'key': 'company', 'label': 'Company', 'sortable': True},
    {'key': 'industry', 'label': 'Industry', 'sortable': True},
    {'key': 'position', 'label': 'Position', 'sortable': True},
    {'key': 'email', 'label': 'Email', 'sortable': True},
    {'key': 'mobile_number', 'label': 'Mobile', 'sortable': False},
    {'key': 'leads_status', 'label': 'Status', 'sortable': True},
    {'key': 'source', 'label': 'Source', 'sortable': True},
    {'key': 'event', 'label': 'Event', 'sortable': False},
    {'key': 'date_added', 'label': 'Date Added', 'sortable': True},
    {'key': 'owner', 'label': 'Owner', 'sortable': True},  # Special: displays owner.username
    {'key': 'requirements', 'label': 'Requirements', 'sortable': False},
    {'key': 'note', 'label': 'Notes', 'sortable': False},
    {'key': 'created_at', 'label': 'Created', 'sortable': True},
]

PIPELINE_COLUMNS = [
    {'key': 'name', 'label': 'Name', 'sortable': True},
    {'key': 'company', 'label': 'Company', 'sortable': True},
    {'key': 'industry', 'label': 'Industry', 'sortable': True},
    {'key': 'position', 'label': 'Position', 'sortable': True},
    {'key': 'owner', 'label': 'Owner', 'sortable': True},
    {'key': 'product', 'label': 'Product', 'sortable': True},
    {'key': 'stage', 'label': 'Stage', 'sortable': True},
    {'key': 'level', 'label': 'Level', 'sortable': True},
    {'key': 'tcv_usd', 'label': 'TCV', 'sortable': True},
    {'key': 'mrc_usd', 'label': 'MRC', 'sortable': True},
    {'key': 'otc_usd', 'label': 'OTC', 'sortable': True},
    {'key': 'win_rate', 'label': 'Win Rate', 'sortable': True},
    {'key': 'est_sign_date', 'label': 'Est. Sign', 'sortable': True},
    {'key': 'stuckpoint', 'label': 'Stuckpoint', 'sortable': False},
    {'key': 'created_at', 'label': 'Created', 'sortable': True},
]

TASKS_COLUMNS = [
    {'key': 'content', 'label': 'Content', 'sortable': True},
    {'key': 'status', 'label': 'Status', 'sortable': True},
    {'key': 'owner', 'label': 'Owner', 'sortable': True},
    {'key': 'company', 'label': 'Company', 'sortable': True},
    {'key': 'due_date', 'label': 'Due Date', 'sortable': True},
    {'key': 'created_at', 'label': 'Created', 'sortable': True},
]

USERS_COLUMNS = [
    {'key': 'username', 'label': 'Username', 'sortable': True},
    {'key': 'email', 'label': 'Email', 'sortable': True},
    {'key': 'role', 'label': 'Role', 'sortable': True},
    {'key': 'is_active', 'label': 'Active', 'sortable': True},
    {'key': 'created_at', 'label': 'Created', 'sortable': True},
]


@api_bp.route('/available-columns/<page>', methods=['GET'])
@login_required
def get_available_columns(page):
    """Get available columns for a specific page."""
    valid_pages = ['leads', 'pipeline', 'tasks', 'users']
    
    if page not in valid_pages:
        return jsonify({'error': 'Invalid page'}), 400
    
    columns_map = {
        'leads': LEADS_COLUMNS,
        'pipeline': PIPELINE_COLUMNS,
        'tasks': TASKS_COLUMNS,
        'users': USERS_COLUMNS
    }
    
    # Get user's current preferences
    prefs = current_user.get_column_preferences(page)
    selected_columns = prefs.get('columns', [])
    
    return jsonify({
        'available': columns_map[page],
        'selected': selected_columns
    })


@api_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password."""
    data = request.get_json()

    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'All password fields are required.'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters.'}), 400

    # Verify current password
    if not current_user.check_password(current_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect.'}), 400

    # Update password
    try:
        current_user.set_password(new_password)
        db.session.commit()
        
        # Log the activity
        log_password_changed(current_user, request.remote_addr)
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'An error occurred. Please try again.'}), 500


# ============================================================================
# ACTIVITIES API
# ============================================================================

@api_bp.route('/activities/', methods=['GET'])
@login_required
def get_activities():
    """Get activities list with filters."""
    from datetime import datetime, timedelta
    
    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 100, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_id = request.args.get('user_id')
    action_type = request.args.get('action_type')
    keyword = request.args.get('keyword', '')
    subject_type = request.args.get('subject_type')
    
    # Build query
    query = ActivityLog.query
    
    # Apply permission filters
    if current_user.role == 'sales':
        query = query.filter(ActivityLog.user_id == current_user.id)
    elif current_user.role == 'marketing':
        query = query.filter(
            or_(
                ActivityLog.subject_type == 'lead',
                ActivityLog.action_type.like('Leads%')
            )
        )
    
    # Apply filters
    if start_date:
        query = query.filter(ActivityLog.created_at >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(ActivityLog.created_at < end_date_obj)
    if user_id:
        query = query.filter(ActivityLog.user_id == int(user_id))
    if action_type:
        query = query.filter(ActivityLog.action_type == action_type)
    if subject_type:
        query = query.filter(ActivityLog.subject_type == subject_type)
    if keyword:
        query = query.filter(
            or_(
                ActivityLog.description.ilike(f'%{keyword}%'),
                ActivityLog.subject_name.ilike(f'%{keyword}%'),
                ActivityLog.user_name.ilike(f'%{keyword}%')
            )
        )
    
    # Get paginated results
    query = query.order_by(ActivityLog.created_at.desc())
    activities = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Serialize results
    data = {
        'items': [{
            'id': a.id,
            'user_id': a.user_id,
            'user_name': a.user_name,
            'action_type': a.action_type,
            'subject_type': a.subject_type,
            'subject_id': a.subject_id,
            'subject_name': a.subject_name,
            'description': a.description,
            'ip_address': a.ip_address,
            'created_at': a.created_at.isoformat(),
            'action_icon': a.get_action_icon(),
            'action_badge': a.get_action_badge()
        } for a in activities.items],
        'total': activities.total,
        'page': activities.page,
        'per_page': activities.per_page,
        'pages': activities.pages
    }
    
    return jsonify(data)


@api_bp.route('/activities/log', methods=['POST'])
@login_required
def create_activity_log():
    """Create a new activity log entry."""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    required_fields = ['action_type']
    for field in required_fields:
        if field not in data:
            return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
    
    try:
        activity = log_activity(
            user=current_user,
            action_type=data['action_type'],
            subject_type=data.get('subject_type'),
            subject_id=data.get('subject_id'),
            subject_name=data.get('subject_name'),
            description=data.get('description'),
            ip_address=data.get('ip_address')
        )
        
        return jsonify({
            'success': True,
            'message': 'Activity logged successfully',
            'activity_id': activity.id
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/activities/stats', methods=['GET'])
@login_required
def get_activity_stats():
    """Get activity statistics."""
    from datetime import datetime, timedelta
    
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Build base query with permissions
    base_query = ActivityLog.query
    if current_user.role == 'sales':
        base_query = base_query.filter(ActivityLog.user_id == current_user.id)
    elif current_user.role == 'marketing':
        base_query = base_query.filter(
            or_(
                ActivityLog.subject_type == 'lead',
                ActivityLog.action_type.like('Leads%')
            )
        )
    
    # Calculate stats
    stats = {
        'total': base_query.count(),
        'today': base_query.filter(ActivityLog.created_at >= datetime.combine(today, datetime.min.time())).count(),
        'week': base_query.filter(ActivityLog.created_at >= datetime.combine(week_ago, datetime.min.time())).count(),
        'month': base_query.filter(ActivityLog.created_at >= datetime.combine(month_ago, datetime.min.time())).count()
    }
    
    return jsonify(stats)


@api_bp.route('/activities/stream', methods=['GET'])
@login_required
def stream_activities():
    """
    Stream activities for real-time updates.
    Supports polling with 'after_id' parameter.
    """
    from datetime import datetime, timedelta
    
    # Get the last activity ID
    after_id = request.args.get('after_id', 0, type=int)
    
    # Build query for new activities
    query = ActivityLog.query.filter(ActivityLog.id > after_id)
    
    # Apply permission filters
    if current_user.role == 'sales':
        query = query.filter(ActivityLog.user_id == current_user.id)
    elif current_user.role == 'marketing':
        query = query.filter(
            or_(
                ActivityLog.subject_type == 'lead',
                ActivityLog.action_type.like('Leads%')
            )
        )
    
    # Order by created_at ascending (oldest first for polling)
    query = query.order_by(ActivityLog.created_at.asc())
    
    # Get activities
    activities = query.limit(50).all()
    
    # Get current stats
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    base_query = ActivityLog.query
    if current_user.role == 'sales':
        base_query = base_query.filter(ActivityLog.user_id == current_user.id)
    elif current_user.role == 'marketing':
        base_query = base_query.filter(
            or_(
                ActivityLog.subject_type == 'lead',
                ActivityLog.action_type.like('Leads%')
            )
        )
    
    stats = {
        'total': base_query.count(),
        'today': base_query.filter(ActivityLog.created_at >= datetime.combine(today, datetime.min.time())).count(),
        'week': base_query.filter(ActivityLog.created_at >= datetime.combine(week_ago, datetime.min.time())).count(),
        'month': base_query.filter(ActivityLog.created_at >= datetime.combine(month_ago, datetime.min.time())).count()
    }
    
    # Serialize results
    data = {
        'items': [{
            'id': a.id,
            'user_id': a.user_id,
            'user_name': a.user_name,
            'action_type': a.action_type,
            'subject_type': a.subject_type,
            'subject_id': a.subject_id,
            'subject_name': a.subject_name,
            'description': a.description,
            'ip_address': a.ip_address,
            'created_at': a.created_at.isoformat(),
            'action_icon': a.get_action_icon(),
            'action_badge': a.get_action_badge()
        } for a in activities],
        'stats': stats,
        'has_more': len(activities) == 50
    }
    
    return jsonify(data)


# ============================================================================
# TASKS API - Task Status Toggle
# ============================================================================

@api_bp.route('/tasks/<int:task_id>/toggle-status', methods=['POST'])
@login_required
def toggle_task_status(task_id):
    """Toggle task status between In Progress and Completed."""
    task = Task.query.get_or_404(task_id)
    
    # Check if user has permission to modify this task
    if not current_user.is_admin() and task.owner_id != current_user.id:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    
    try:
        data = request.get_json() or {}
        new_status = data.get('new_status')
        
        # Determine new status
        if new_status:
            task.status = new_status
        else:
            # Toggle between In Progress and Completed
            if task.status == 'In Progress':
                task.status = 'Completed'
                # Log task completion
                log_task_completed(current_user, task, request.remote_addr)
            elif task.status == 'Completed':
                task.status = 'In Progress'
                # Log task reopening
                log_task_reopened(current_user, task, request.remote_addr)
            elif task.status == 'Overdue':
                # Direct toggle from Overdue to Completed (no alert)
                task.status = 'Completed'
                log_task_completed(current_user, task, request.remote_addr)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Task status updated successfully',
            'new_status': task.status
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# DASHBOARD API - Pipeline Data for Kanban Board
# ============================================================================

@api_bp.route('/dashboard/pipeline-kanban', methods=['GET'])
@login_required
def get_pipeline_kanban_data():
    """Get pipeline data for the Kanban board visualization."""
    
    # Get filter parameters
    show_lost = request.args.get('show_lost', 'false') == 'true'
    
    # Build base query
    query = Pipeline.query
    
    # Filter by access permissions
    if not current_user.is_admin():
        # Get the Pipeline IDs that current_user supports
        supported_pipeline_ids = db.session.query(Pipeline.id).filter(
            Pipeline.support_team.contains(current_user)
        ).subquery()
        query = query.filter(
            or_(
                Pipeline.owner_id == current_user.id,
                Pipeline.id.in_(supported_pipeline_ids)
            )
        )
    
    # Filter by lost status
    if not show_lost:
        query = query.filter(Pipeline.stage != '6b) Deal Lost')
    
    # Get all active deals
    pipelines = query.order_by(Pipeline.date_added.desc()).all()
    
    # Define pipeline stages for kanban board
    stages = [
        {'value': 'Prospecting', 'label': '1) Prospecting'},
        {'value': 'Qualification', 'label': '2) Qualification'},
        {'value': 'Needs Analysis', 'label': '3) Needs Analysis'},
        {'value': 'Value Proposition', 'label': '4) Value Proposition'},
        {'value': 'Proposal', 'label': '5) Proposal'},
        {'value': 'Negotiation', 'label': '6) Negotiation'},
        {'value': '6a) Deal Won', 'label': '6a) Deal Won'},
        {'value': '7) Activated', 'label': '7) Activated'},
    ]
    
    # Serialize deals data
    deals_data = []
    for p in pipelines:
        # Get latest follow-up date
        latest_followup = None
        if p.follow_up:
            # Parse follow-up dates from the text
            import re
            date_pattern = r'(\d{4}-\d{2}-\d{2})'
            dates = re.findall(date_pattern, p.follow_up)
            if dates:
                latest_followup = max(dates)
        
        deal = {
            'id': p.id,
            'company': p.company,
            'name': p.name,
            'owner_name': p.owner.username if p.owner else None,
            'tcv_usd': p.tcv_usd,
            'mrc_usd': p.mrc_usd,
            'win_rate': p.win_rate,
            'stage': p.stage,
            'est_sign_date': p.est_sign_date.strftime('%Y-%m-%d') if p.est_sign_date else None,
            'latest_followup': latest_followup,
            'level': p.level
        }
        deals_data.append(deal)
    
    return jsonify({
        'stages': stages,
        'deals': deals_data
    })

@api_bp.route('/dashboard/owner-metrics', methods=['GET'])
@login_required
def get_owner_metrics_data():
    """Get per-owner breakdown metrics for dashboard filtering."""
    
    # Get all active users
    users = User.query.filter_by(is_active=True).all()
    
    # Build base pipeline query
    base_pipeline_query = Pipeline.query
    if not current_user.is_admin():
        # Get the Pipeline IDs that current_user supports
        supported_pipeline_ids = db.session.query(Pipeline.id).filter(
            Pipeline.support_team.contains(current_user)
        ).subquery()
        base_pipeline_query = base_pipeline_query.filter(
            or_(
                Pipeline.owner_id == current_user.id,
                Pipeline.id.in_(supported_pipeline_ids)
            )
        )
    
    # Get quarter dates
    today = date.today()
    current_qtr = get_quarter_dates(today)
    next_qtr = get_next_quarter_dates(today)
    
    # Get metrics for each user
    metrics = []
    for user in users:
        # Count leads for this user (exclude Unqualified)
        leads_count = SalesLead.query.filter_by(owner_id=user.id).filter(
            SalesLead.leads_status != 'Unqualified'
        ).count()
        
        # Qualified leads (include 转入 Pipeline的) - owner of lead OR owner of pipeline
        api_user_pipeline_lead_ids = db.session.query(Pipeline.sales_lead_id).filter(
            Pipeline.owner_id == user.id,
            Pipeline.sales_lead_id.isnot(None)
        ).subquery()
        
        qualified_leads_count = SalesLead.query.filter(
            or_(
                SalesLead.owner_id == user.id,
                SalesLead.id.in_(api_user_pipeline_lead_ids)
            )
        ).filter(
            or_(
                SalesLead.leads_status == 'Qualified',
                SalesLead.id.in_(api_user_pipeline_lead_ids)
            )
        ).count()
        
        # Count pipeline deals for this user (exclude Deal Lost)
        pipeline_deals = base_pipeline_query.filter(
            Pipeline.owner_id == user.id
        ).filter(
            Pipeline.stage.notin_(['6b) Deal Lost'])
        ).all()
        pipeline_count = len(pipeline_deals)
        tcv = sum(p.tcv_usd for p in pipeline_deals)
        
        # Count customers (companies in pipeline)
        customer_count = len(set(p.company for p in pipeline_deals if p.company))
        
        # Calculate quarter revenue
        current_qtr_revenue = calculate_quarter_revenue(
            pipeline_deals, current_qtr[0], current_qtr[1]
        )
        next_qtr_revenue = calculate_quarter_revenue(
            pipeline_deals, next_qtr[0], next_qtr[1]
        )
        
        metrics.append({
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'leads_count': leads_count,
            'qualified_leads_count': qualified_leads_count,
            'pipeline_count': pipeline_count,
            'customer_count': customer_count,
            'tcv': tcv,
            'current_qtr_revenue': current_qtr_revenue,
            'next_qtr_revenue': next_qtr_revenue
        })
    
    return jsonify({'metrics': metrics})


# ============================================================================
# DASHBOARD FILTERS API
# ============================================================================

@api_bp.route('/dashboard/filters', methods=['GET'])
@login_required
def get_dashboard_filters():
    """Get user's dashboard filter preferences."""
    filters = current_user.get_dashboard_filters()
    return jsonify(filters)


@api_bp.route('/dashboard/filters', methods=['POST'])
@login_required
def set_dashboard_filters():
    """Save user's dashboard filter preferences."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    try:
        # Validate filter structure
        filters = {
            'owners': data.get('owners', []),
            'stages': data.get('stages', []),
            'date_range': data.get('date_range', {})
        }
        
        # Save to database
        current_user.set_dashboard_filters(filters)
        db.session.commit()
        
        # Log the activity
        log_filter_applied(current_user, 'Dashboard', request.remote_addr)
        
        return jsonify({'success': True, 'message': 'Filters saved'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# HTTP CACHE HEADERS (moved to app.py)
# ============================================================================
# The add_cache_headers function is now defined in app.py
# to avoid import cycle issues
