"""Sales Activities routes."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from activity_logger import log_activity
from extensions import db
from models import Pipeline, SalesActivity, SalesLead, Task, User, pipeline_support
from sales_activity_service import (
    _entity_context,
    append_followup_history,
    complete_activity,
    create_activity_contacts,
    create_remote_engagement_activities,
    soft_delete,
)
from utils import calculate_pipeline_metrics, validate_date

sales_activities_bp = Blueprint('sales_activities', __name__)


def _visible_activity_query():
    query = SalesActivity.query.filter(SalesActivity.is_deleted.is_(False))
    if not current_user.is_admin():
        query = query.filter(SalesActivity.owner_id == current_user.id)
    return query


def _can_manage(activity):
    return current_user.is_admin() or activity.owner_id == current_user.id


def _parse_datetime(date_value, time_value):
    if not date_value or not time_value:
        return None
    return datetime.combine(
        datetime.strptime(date_value, '%Y-%m-%d').date(),
        datetime.strptime(time_value, '%H:%M').time(),
    )


def _pending_deadline(activity):
    """Return the latest registered date/time before a pending activity is overdue."""
    if activity.activity_type == SalesActivity.TYPE_ON_SITE_VISIT and activity.estimated_end_at:
        return activity.estimated_end_at
    if activity.linked_task and activity.linked_task.due_date:
        # A date-only task is due through the end of that calendar day.
        return datetime.combine(activity.linked_task.due_date, time.max)
    if activity.activity_date:
        # Remote Engagement activities without a task are due through the end of their activity date.
        return datetime.combine(activity.activity_date, time.max)
    return None


def _is_pending_overdue(activity, now=None):
    if activity.status != 'Pending Follow-up':
        return False
    deadline = _pending_deadline(activity)
    return bool(deadline and (now or datetime.now()) > deadline)


def _contacts_from_form():
    names = request.form.getlist('contact_name[]')
    positions = request.form.getlist('contact_position[]')
    info = request.form.getlist('contact_information[]')
    count = max(len(names), len(positions), len(info), 1)
    return [{
        'contact_name': names[index] if index < len(names) else '',
        'position': positions[index] if index < len(positions) else '',
        'contact_information': info[index] if index < len(info) else '',
    } for index in range(count)]


def _sync_targets(lead, pipeline):
    targets = []
    if lead:
        targets.append(lead)
        if lead.pipeline and not lead.pipeline.is_deleted:
            targets.append(lead.pipeline)
    if pipeline:
        targets.append(pipeline)
        if pipeline.sales_lead and not pipeline.sales_lead.is_deleted:
            targets.append(pipeline.sales_lead)
    unique = []
    seen = set()
    for target in targets:
        key = (type(target).__name__, target.id)
        if key not in seen:
            seen.add(key)
            unique.append(target)
    return unique


@sales_activities_bp.route('/')
@login_required
def index():
    query = _visible_activity_query()
    activity_type = SalesActivity.normalize_type(request.args.get('type', 'All'))
    start_date = validate_date(request.args.get('start_date'))
    end_date = validate_date(request.args.get('end_date'))
    owner_id = request.args.get('owner_id', type=int)
    calendar_month_value = request.args.get('calendar_month', '').strip()
    try:
        calendar_month = datetime.strptime(calendar_month_value, '%Y-%m').date().replace(day=1)
    except (TypeError, ValueError):
        calendar_month = date.today().replace(day=1)
    selected_dates = [
        validate_date(value) for value in request.args.getlist('dates') if validate_date(value)
    ]

    if activity_type in SalesActivity.TYPE_OPTIONS:
        query = query.filter(SalesActivity.activity_type == activity_type)
    if start_date:
        query = query.filter(SalesActivity.activity_date >= start_date)
    if end_date:
        query = query.filter(SalesActivity.activity_date <= end_date)
    if current_user.is_admin() and owner_id:
        query = query.filter(SalesActivity.owner_id == owner_id)

    # Calendar data intentionally ignores the calendar date selections themselves.
    # Otherwise selecting one date would make every other marked date disappear and
    # prevent the user from selecting multiple dates.
    next_calendar_month = (
        calendar_month.replace(year=calendar_month.year + 1, month=1)
        if calendar_month.month == 12
        else calendar_month.replace(month=calendar_month.month + 1)
    )
    calendar_activities = query.filter(
        SalesActivity.activity_date >= calendar_month,
        SalesActivity.activity_date < next_calendar_month,
    ).all()

    if selected_dates:
        query = query.filter(SalesActivity.activity_date.in_(selected_dates))

    activities = query.order_by(SalesActivity.activity_date.desc(), SalesActivity.created_at.desc()).all()
    type_counts = Counter(activity.activity_type for activity in activities)
    source_counts = Counter(activity.source_type for activity in activities)
    stats = {
        'total': len(activities),
        'remote_engagement': type_counts[SalesActivity.TYPE_REMOTE_ENGAGEMENT],
        'on_site_visit': type_counts[SalesActivity.TYPE_ON_SITE_VISIT],
        'pending': sum(1 for activity in activities if activity.status == 'Pending Follow-up'),
        'sources': source_counts,
    }

    owner_stats = []
    if current_user.is_admin():
        grouped = defaultdict(lambda: {'total': 0, 'remote_engagement': 0, 'on_site_visit': 0, 'pending': 0})
        for activity in activities:
            item = grouped[activity.owner.username if activity.owner else 'Unknown']
            item['total'] += 1
            item['remote_engagement'] += activity.activity_type == SalesActivity.TYPE_REMOTE_ENGAGEMENT
            item['on_site_visit'] += activity.activity_type == SalesActivity.TYPE_ON_SITE_VISIT
            item['pending'] += activity.status == 'Pending Follow-up'
        owner_stats = sorted(({'owner': owner, **counts} for owner, counts in grouped.items()), key=lambda item: item['owner'])

    # Keep the compact horizontal source summary, but show the owner names and
    # each owner's count inside every source-type cell.
    owner_names = sorted({activity.owner.username if activity.owner else 'Unknown' for activity in activities})
    source_owner_counts = defaultdict(lambda: defaultdict(int))
    for activity in activities:
        owner_name = activity.owner.username if activity.owner else 'Unknown'
        source_owner_counts[activity.source_type][owner_name] += 1
    source_owner_rows = []
    for owner in owner_names:
        source_counts_for_owner = {
            source: source_owner_counts[source].get(owner, 0)
            for source in SalesActivity.SOURCE_OPTIONS
        }
        source_owner_rows.append({
            'owner': owner,
            'sources': source_counts_for_owner,
            'total': sum(source_counts_for_owner.values()),
        })
    source_totals = {
        source: sum(row['sources'][source] for row in source_owner_rows)
        for source in SalesActivity.SOURCE_OPTIONS
    }

    calendar = defaultdict(lambda: {'total': 0, 'pending': 0, 'overdue': 0, 'completed': 0})
    now = datetime.now()
    for activity in calendar_activities:
        key = activity.activity_date.isoformat()
        calendar[key]['total'] += 1
        calendar[key]['pending'] += activity.status == 'Pending Follow-up'
        calendar[key]['overdue'] += _is_pending_overdue(activity, now)
        calendar[key]['completed'] += activity.status == 'Completed'

    owners = User.query.filter_by(is_active=True).order_by(User.username).all() if current_user.is_admin() else []
    add_form_data = session.pop('sales_activity_form_data', {})
    reopen_add_modal = session.pop('sales_activity_reopen_form', False)
    return render_template(
        'sales_activities/index.html', activities=activities, stats=stats,
        owner_stats=owner_stats, source_owner_rows=source_owner_rows, source_totals=source_totals,
        owners=owners, calendar_data=dict(calendar),
        selected_type=activity_type, start_date=start_date, end_date=end_date,
        selected_dates=[item.isoformat() for item in selected_dates], selected_owner_id=owner_id,
        source_options=SalesActivity.SOURCE_OPTIONS, calendar_month=calendar_month,
        today_iso=date.today().isoformat(), add_form_data=add_form_data,
        reopen_add_modal=reopen_add_modal,
    )


@sales_activities_bp.route('/source-search')
@login_required
def source_search():
    source_type = request.args.get('source_type')
    keyword = request.args.get('q', '').strip()
    like = f'%{keyword}%'
    results = []
    if source_type == 'Sales Leads':
        query = SalesLead.query.filter(SalesLead.is_deleted.is_(False))
        if not current_user.can_view_all_leads():
            query = query.filter(SalesLead.owner_id == current_user.id)
        if keyword:
            query = query.filter(or_(SalesLead.company.ilike(like), SalesLead.name.ilike(like)))
        for lead in query.order_by(SalesLead.company, SalesLead.name).limit(30):
            results.append({
                'id': lead.id, 'company': lead.company or lead.name, 'contact': lead.name,
                'position': lead.position or '', 'contact_information': lead.email or lead.mobile_number or '',
                'owner': lead.owner.username if lead.owner else '', 'status': lead.leads_status,
            })
    elif source_type == 'Pipeline':
        query = Pipeline.query.filter(Pipeline.is_deleted.is_(False))
        if not current_user.is_admin():
            supported_ids = db.session.query(pipeline_support.c.pipeline_id).filter(pipeline_support.c.user_id == current_user.id)
            query = query.filter(or_(Pipeline.owner_id == current_user.id, Pipeline.id.in_(supported_ids)))
        if keyword:
            query = query.filter(or_(Pipeline.company.ilike(like), Pipeline.name.ilike(like)))
        for pipeline in query.order_by(Pipeline.company, Pipeline.name).limit(30):
            results.append({
                'id': pipeline.id, 'company': pipeline.company or pipeline.name, 'contact': pipeline.name,
                'position': pipeline.position or '', 'contact_information': pipeline.email or pipeline.mobile_number or '',
                'owner': pipeline.owner.username if pipeline.owner else '', 'status': pipeline.stage,
            })
    elif source_type == 'Existing Customer':
        query = Pipeline.query.filter(
            Pipeline.is_deleted.is_(False), Pipeline.stage.in_(['6a) Deal Won', '7) Activated']))
        if keyword:
            query = query.filter(or_(Pipeline.company.ilike(like), Pipeline.name.ilike(like)))
        seen = set()
        for pipeline in query.order_by(Pipeline.company).limit(30):
            company = pipeline.company or pipeline.name
            if company in seen:
                continue
            seen.add(company)
            results.append({'id': None, 'company': company, 'contact': pipeline.name, 'position': pipeline.position or '', 'contact_information': pipeline.email or pipeline.mobile_number or '', 'owner': pipeline.owner.username if pipeline.owner else '', 'status': pipeline.stage})
    elif source_type == 'Marketing Event':
        query = SalesLead.query.filter(SalesLead.is_deleted.is_(False), SalesLead.event.isnot(None))
        if keyword:
            query = query.filter(or_(SalesLead.event.ilike(like), SalesLead.company.ilike(like)))
        for lead in query.order_by(SalesLead.event).limit(30):
            results.append({'id': None, 'company': lead.company or lead.event, 'contact': lead.name, 'position': lead.position or '', 'contact_information': lead.email or lead.mobile_number or '', 'owner': lead.owner.username if lead.owner else '', 'status': lead.event})
    return jsonify({'items': results})


@sales_activities_bp.route('/add', methods=['POST'])
@login_required
def add():
    try:
        activity_type = SalesActivity.normalize_type(request.form.get('activity_type'))
        source_type = request.form.get('source_type')
        if activity_type not in SalesActivity.TYPE_OPTIONS or source_type not in SalesActivity.SOURCE_OPTIONS:
            raise ValueError('Please select a valid activity type and source type.')
        sales_lead_id = request.form.get('sales_lead_id', type=int)
        pipeline_id = request.form.get('pipeline_id', type=int)
        company = request.form.get('company', '').strip()
        lead, pipeline, company = _entity_context(source_type, sales_lead_id, pipeline_id, company)
        if lead and not (current_user.can_view_all_leads() or lead.owner_id == current_user.id):
            raise PermissionError('You do not have permission to use this Sales Lead.')
        if pipeline and not current_user.can_access_pipeline(pipeline):
            raise PermissionError('You do not have permission to use this Pipeline.')
        # Remote Engagement activities use Activity Date. On-site Visit uses its Estimated Start Date
        # as the activity date, so the form does not need a duplicate Visit Date field.
        activity_date = validate_date(request.form.get('activity_date'))
        if activity_type == SalesActivity.TYPE_ON_SITE_VISIT:
            # An On-site Visit's activity date is always its Estimated Start Date.
            activity_date = validate_date(request.form.get('start_date'))
        if not activity_date:
            raise ValueError('Activity Date is required for Remote Engagement, or Estimated Start Date is required for an On-site Visit.')
        owner_id = request.form.get('owner_id', type=int) if current_user.is_admin() else current_user.id
        owner_id = owner_id or current_user.id
        contacts = _contacts_from_form()
        purpose = request.form.get('purpose_project', '').strip()
        expected = request.form.get('expected_result', '').strip()
        remarks = request.form.get('remarks', '').strip()

        if activity_type == SalesActivity.TYPE_REMOTE_ENGAGEMENT:
            followup_text = request.form.get('followup_text', '').strip()
            todo_text = request.form.get('todo_text', '').strip()
            todo_due_date = validate_date(request.form.get('todo_due_date'))
            if todo_text and not todo_due_date:
                raise ValueError('To-do Due Date is required when Next Steps / To-do is filled.')
            activities = create_remote_engagement_activities(
                source_type=source_type, owner_id=owner_id, sales_lead_id=sales_lead_id,
                pipeline_id=pipeline_id, company=company, followup_text=followup_text,
                todo_text=todo_text, todo_due_date=todo_due_date, activity_date=activity_date,
                purpose_project=purpose, expected_result=expected, remarks=remarks, contacts=contacts,
            )
            for target in _sync_targets(lead, pipeline):
                append_followup_history(target, followup_text, todo_text, todo_due_date)
            description = f'Created {len(activities)} Remote Engagement sales activity record(s) for {company}'
        else:
            start_at = _parse_datetime(request.form.get('start_date') or request.form.get('activity_date'), request.form.get('start_time'))
            end_at = _parse_datetime(request.form.get('end_date') or request.form.get('activity_date'), request.form.get('end_time'))
            if not start_at or not end_at:
                raise ValueError('Estimated Start Date/Time and Estimated End Date/Time are required for an On-site Visit.')
            if end_at <= start_at:
                raise ValueError('Estimated End Time must be later than Estimated Start Time.')
            activity = SalesActivity(
                activity_type=SalesActivity.TYPE_ON_SITE_VISIT, source_type=source_type,
                sales_lead_id=lead.id if lead else None, pipeline_id=pipeline.id if pipeline else None,
                company=company, activity_date=activity_date, estimated_start_at=start_at,
                estimated_end_at=end_at, address=request.form.get('address', '').strip() or None,
                purpose_project=purpose or None, expected_result=expected or None,
                remarks=remarks or None, status='Pending Follow-up', owner_id=owner_id,
            )
            db.session.add(activity)
            db.session.flush()
            create_activity_contacts(activity, contacts)
            task = Task(
                content=f'On-site Visit follow-up: {company}' + (f' - {purpose}' if purpose else ''),
                due_date=activity_date, owner_id=owner_id, pipeline_id=pipeline.id if pipeline else None,
                sales_lead_id=lead.id if lead else None, sales_activity_id=activity.id,
                company=company, status='In Progress',
            )
            db.session.add(task)
            plan_note = f'On-site Visit scheduled for {activity_date.isoformat()} {start_at:%H:%M}-{end_at:%H:%M}'
            if purpose:
                plan_note += f'; Purpose / Project: {purpose}'
            for target in _sync_targets(lead, pipeline):
                append_followup_history(target, plan_note)
            description = f'Created On-site Visit for {company} on {activity_date.isoformat()} {start_at:%H:%M}-{end_at:%H:%M}'

        db.session.flush()
        log_activity(current_user, 'Sales Activity - Created', 'sales_activity',
                     (activities[0].id if activity_type == SalesActivity.TYPE_REMOTE_ENGAGEMENT else activity.id), company,
                     description, request.remote_addr)
        db.session.commit()
        flash('Sales Activity added successfully!', 'success')
    except (ValueError, PermissionError) as exc:
        db.session.rollback()
        session['sales_activity_form_data'] = request.form.to_dict(flat=False)
        session['sales_activity_reopen_form'] = True
        flash(str(exc), 'danger')
    except Exception as exc:
        db.session.rollback()
        session['sales_activity_form_data'] = request.form.to_dict(flat=False)
        session['sales_activity_reopen_form'] = True
        flash(f'Error adding Sales Activity: {exc}', 'danger')
    return redirect(url_for('sales_activities.index'))


@sales_activities_bp.route('/<int:activity_id>/followup', methods=['POST'])
@login_required
def followup(activity_id):
    activity = SalesActivity.query.filter_by(id=activity_id, is_deleted=False).first_or_404()
    if not _can_manage(activity):
        flash('Permission denied.', 'danger')
        return redirect(url_for('sales_activities.index'))
    try:
        if activity.activity_type == SalesActivity.TYPE_REMOTE_ENGAGEMENT and activity.remote_engagement_subtype == 'Next Steps / To-do':
            raise ValueError('This activity must be completed from its linked Task.')
        notes = request.form.get('completion_notes', '').strip()
        todo_text = request.form.get('todo_text', '').strip()
        todo_due_date = validate_date(request.form.get('todo_due_date'))
        if todo_text and not todo_due_date:
            raise ValueError('To-do Due Date is required when Next Steps / To-do is filled.')
        complete_activity(activity, current_user.id, notes)
        lead = activity.sales_lead
        pipeline = activity.pipeline
        if activity.activity_type == SalesActivity.TYPE_ON_SITE_VISIT:
            history_note = f'On-site Visit feedback: {notes}'
            for target in _sync_targets(lead, pipeline):
                append_followup_history(target, history_note)
            if pipeline:
                if 'stuckpoint_text' in request.form:
                    pipeline.stuckpoint = request.form.get('stuckpoint_text', '').strip() or None
                new_stage = request.form.get('stage', '').strip()
                if new_stage:
                    if new_stage not in Pipeline.STAGE_OPTIONS:
                        raise ValueError('Please select a valid Pipeline stage.')
                    pipeline.stage = new_stage
                    calculate_pipeline_metrics(pipeline)
            if todo_text:
                create_remote_engagement_activities(
                    source_type=activity.source_type,
                    owner_id=activity.owner_id,
                    sales_lead_id=activity.sales_lead_id,
                    pipeline_id=activity.pipeline_id,
                    company=activity.company,
                    todo_text=todo_text,
                    todo_due_date=todo_due_date,
                    activity_date=todo_due_date,
                )
                for target in _sync_targets(lead, pipeline):
                    append_followup_history(target, todo_text=todo_text, todo_due_date=todo_due_date)
        log_activity(current_user, 'Sales Activity - Completed', 'sales_activity', activity.id,
                     activity.company, f'Completed {activity.activity_type} for {activity.company}: {notes}', request.remote_addr,
                     new_values={'status': activity.status, 'completion_notes': notes},
                     extra_data={'next_steps_created': bool(todo_text)}, commit=False)
        db.session.commit()
        flash('Sales Activity completed successfully!', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error completing Sales Activity: {exc}', 'danger')
    return redirect(url_for('sales_activities.index'))


@sales_activities_bp.route('/<int:activity_id>/delete', methods=['POST'])
@login_required
def delete(activity_id):
    activity = SalesActivity.query.filter_by(id=activity_id, is_deleted=False).first_or_404()
    if not _can_manage(activity):
        flash('Permission denied.', 'danger')
        return redirect(url_for('sales_activities.index'))
    try:
        soft_delete(activity, current_user.id, 'sales_activity', activity.company, request.form.get('deletion_reason'))
        if activity.linked_task and not activity.linked_task.is_deleted:
            soft_delete(activity.linked_task, current_user.id, 'task', activity.linked_task.content, 'Linked Sales Activity deleted')
        log_activity(current_user, 'Sales Activity - Deleted', 'sales_activity', activity.id,
                     activity.company, f'Soft-deleted Sales Activity for {activity.company}', request.remote_addr)
        db.session.commit()
        flash('Sales Activity deleted and archived.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error deleting Sales Activity: {exc}', 'danger')
    return redirect(url_for('sales_activities.index'))
