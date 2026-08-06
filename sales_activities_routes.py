"""Sales Activities routes."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, or_

from activity_logger import log_activity
from extensions import db
from models import Pipeline, SalesActivity, SalesLead, Task, User, pipeline_support
from sales_activity_service import (
    _entity_context,
    append_followup_history,
    complete_activity,
    create_activity_contacts,
    create_remote_engagement_activities,
    resolve_new_activity_owner_id,
    soft_delete,
)
from utils import calculate_pipeline_metrics, validate_date

sales_activities_bp = Blueprint('sales_activities', __name__)


def _visible_activity_query():
    query = SalesActivity.query.filter(SalesActivity.is_deleted.is_(False))
    if not current_user.can_view_all_business_data():
        query = query.filter(SalesActivity.owner_id == current_user.id)
    return query


def _can_manage(activity):
    return (
        not current_user.is_readonly()
        and (current_user.is_admin() or activity.owner_id == current_user.id)
    )


def _activity_date_range_condition(start_date=None, end_date=None):
    """Build an inclusive activity-date condition.

    Remote Engagement records occur on ``activity_date``. Scheduled visits may
    span more than one day, so they match when their scheduled interval
    overlaps the requested date range. Legacy visits without schedule times
    fall back to ``activity_date``.
    """
    conditions = []
    scheduled_visit = SalesActivity.activity_type.in_(SalesActivity.SCHEDULED_VISIT_TYPES)

    if start_date:
        start_at = datetime.combine(start_date, time.min)
        conditions.append(or_(
            and_(
                scheduled_visit,
                SalesActivity.estimated_end_at.isnot(None),
                SalesActivity.estimated_end_at >= start_at,
            ),
            and_(
                scheduled_visit,
                SalesActivity.estimated_end_at.is_(None),
                SalesActivity.activity_date >= start_date,
            ),
            and_(
                SalesActivity.activity_type.notin_(SalesActivity.SCHEDULED_VISIT_TYPES),
                SalesActivity.activity_date >= start_date,
            ),
        ))

    if end_date:
        end_at = datetime.combine(end_date, time.max)
        conditions.append(or_(
            and_(
                scheduled_visit,
                SalesActivity.estimated_start_at.isnot(None),
                SalesActivity.estimated_start_at <= end_at,
            ),
            and_(
                scheduled_visit,
                SalesActivity.estimated_start_at.is_(None),
                SalesActivity.activity_date <= end_date,
            ),
            and_(
                SalesActivity.activity_type.notin_(SalesActivity.SCHEDULED_VISIT_TYPES),
                SalesActivity.activity_date <= end_date,
            ),
        ))

    return and_(*conditions) if conditions else None


def _parse_datetime(date_value, time_value):
    if not date_value or not time_value:
        return None
    return datetime.combine(
        datetime.strptime(date_value, '%Y-%m-%d').date(),
        datetime.strptime(time_value, '%H:%M').time(),
    )


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
    requested_type = SalesActivity.normalize_type(request.args.get('type', 'All'))
    activity_type = requested_type if requested_type in SalesActivity.TYPE_OPTIONS else 'All'
    start_date = validate_date(request.args.get('start_date'))
    end_date = validate_date(request.args.get('end_date'))
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date
    owner_ids = []
    for value in request.args.getlist('owner_id'):
        try:
            owner_id = int(value)
        except (TypeError, ValueError):
            continue
        if owner_id > 0 and owner_id not in owner_ids:
            owner_ids.append(owner_id)
    if not current_user.can_view_all_business_data():
        owner_ids = []
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
    date_range_condition = _activity_date_range_condition(start_date, end_date)
    if date_range_condition is not None:
        query = query.filter(date_range_condition)
    if current_user.can_view_all_business_data() and owner_ids:
        query = query.filter(SalesActivity.owner_id.in_(owner_ids))

    # Calendar data intentionally ignores the calendar date selections themselves.
    # Otherwise selecting one date would make every other marked date disappear and
    # prevent the user from selecting multiple dates.
    next_calendar_month = (
        calendar_month.replace(year=calendar_month.year + 1, month=1)
        if calendar_month.month == 12
        else calendar_month.replace(month=calendar_month.month + 1)
    )
    calendar_month_end = next_calendar_month - timedelta(days=1)
    calendar_activities = query.filter(
        _activity_date_range_condition(calendar_month, calendar_month_end)
    ).all()

    if selected_dates:
        query = query.filter(or_(*(
            _activity_date_range_condition(selected_date, selected_date)
            for selected_date in selected_dates
        )))

    ordered_query = query.order_by(
        SalesActivity.activity_date.desc(), SalesActivity.created_at.desc(), SalesActivity.id.desc()
    )
    matching_activities = ordered_query.all()
    page = max(request.args.get('page', 1, type=int) or 1, 1)
    pagination = ordered_query.paginate(page=page, per_page=20, error_out=False)
    activities = pagination.items

    now = datetime.now()
    display_statuses = {activity.id: activity.get_display_status(now) for activity in matching_activities}
    deadline_indicators = {activity.id: activity.get_deadline_indicator(now) for activity in matching_activities}
    stats = {
        'total': len(matching_activities),
        'scheduled': sum(1 for status in display_statuses.values() if status == SalesActivity.STATUS_SCHEDULED),
        'follow_up_required': sum(1 for status in display_statuses.values() if status == SalesActivity.STATUS_FOLLOW_UP_REQUIRED),
        'completed': sum(1 for status in display_statuses.values() if status == SalesActivity.STATUS_COMPLETED),
        'cancelled': sum(1 for status in display_statuses.values() if status == SalesActivity.STATUS_CANCELLED),
    }

    # The visible activity query is already scoped to the current user's own
    # activities for non-admin users, so this summary is safe for everyone:
    # regular users get one row for themselves; administrators get all owners
    # within the current type/date/owner filters.
    grouped = defaultdict(lambda: {
        'total': 0, 'scheduled': 0, 'follow_up_required': 0,
        'completed': 0, 'cancelled': 0,
    })
    for activity in matching_activities:
        item = grouped[activity.owner.username if activity.owner else 'Unknown']
        item['total'] += 1
        status_key = {
            SalesActivity.STATUS_SCHEDULED: 'scheduled',
            SalesActivity.STATUS_FOLLOW_UP_REQUIRED: 'follow_up_required',
            SalesActivity.STATUS_COMPLETED: 'completed',
            SalesActivity.STATUS_CANCELLED: 'cancelled',
        }[display_statuses[activity.id]]
        item[status_key] += 1
    owner_stats = sorted(({'owner': owner, **counts} for owner, counts in grouped.items()), key=lambda item: item['owner'])

    # Keep the compact horizontal source summary, but show the owner names and
    # each owner's count inside every source-type cell.
    owner_names = sorted({activity.owner.username if activity.owner else 'Unknown' for activity in matching_activities})
    source_owner_counts = defaultdict(lambda: defaultdict(int))
    for activity in matching_activities:
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

    calendar = defaultdict(lambda: {
        'total': 0, 'scheduled': 0, 'follow_up_required': 0,
        'due_today': 0, 'overdue': 0, 'completed': 0, 'cancelled': 0,
    })
    for activity in calendar_activities:
        display_status = activity.get_display_status(now)
        indicator = activity.get_deadline_indicator(now)
        first_activity_date = activity.activity_date
        last_activity_date = activity.activity_date
        if activity.is_scheduled_visit:
            if activity.estimated_start_at:
                first_activity_date = activity.estimated_start_at.date()
            if activity.estimated_end_at:
                last_activity_date = activity.estimated_end_at.date()

        first_activity_date = max(first_activity_date, calendar_month)
        last_activity_date = min(last_activity_date, calendar_month_end)
        activity_calendar_date = first_activity_date
        while activity_calendar_date <= last_activity_date:
            key = activity_calendar_date.isoformat()
            calendar[key]['total'] += 1
            calendar[key]['scheduled'] += display_status == SalesActivity.STATUS_SCHEDULED
            calendar[key]['follow_up_required'] += display_status == SalesActivity.STATUS_FOLLOW_UP_REQUIRED
            calendar[key]['due_today'] += indicator == 'Due Today'
            calendar[key]['overdue'] += indicator == 'Overdue'
            calendar[key]['completed'] += display_status == SalesActivity.STATUS_COMPLETED
            calendar[key]['cancelled'] += display_status == SalesActivity.STATUS_CANCELLED
            activity_calendar_date += timedelta(days=1)

    # Keep the Owner selector concise: list only users who actually own at
    # least one non-deleted Sales Activity. Historical owners remain available
    # even if their user account is no longer active.
    owners = (
        User.query
        .join(SalesActivity, SalesActivity.owner_id == User.id)
        .filter(SalesActivity.is_deleted.is_(False))
        .distinct()
        .order_by(User.username)
        .all()
        if current_user.can_view_all_business_data()
        else []
    )
    assignable_owners = (
        User.query.filter_by(is_active=True).order_by(User.username).all()
        if current_user.is_admin()
        else [current_user]
    )
    add_form_data = session.pop('sales_activity_form_data', {})
    reopen_add_modal = session.pop('sales_activity_reopen_form', False)
    return render_template(
        'sales_activities/index.html', activities=activities, pagination=pagination,
        pagination_query={key: values for key, values in request.args.to_dict(flat=False).items() if key != 'page'},
        stats=stats, owner_stats=owner_stats, source_owner_rows=source_owner_rows, source_totals=source_totals,
        owners=owners, assignable_owners=assignable_owners, calendar_data=dict(calendar),
        selected_type=activity_type, start_date=start_date, end_date=end_date,
        selected_dates=[item.isoformat() for item in selected_dates], selected_owner_ids=owner_ids,
        source_options=SalesActivity.SOURCE_OPTIONS, calendar_month=calendar_month,
        today_iso=date.today().isoformat(), add_form_data=add_form_data,
        reopen_add_modal=reopen_add_modal,
    )


@sales_activities_bp.route('/source-search')
@login_required
def source_search():
    source_type = SalesActivity.normalize_source_type(request.args.get('source_type'))
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
                'owner_id': lead.owner_id,
                'owner': lead.owner.username if lead.owner else '', 'status': lead.leads_status,
            })
    elif source_type == 'Pipeline':
        query = Pipeline.query.filter(Pipeline.is_deleted.is_(False))
        if not current_user.can_view_all_business_data():
            supported_ids = db.session.query(pipeline_support.c.pipeline_id).filter(pipeline_support.c.user_id == current_user.id)
            query = query.filter(or_(Pipeline.owner_id == current_user.id, Pipeline.id.in_(supported_ids)))
        if keyword:
            query = query.filter(or_(Pipeline.company.ilike(like), Pipeline.name.ilike(like)))
        for pipeline in query.order_by(Pipeline.company, Pipeline.name).limit(30):
            results.append({
                'id': pipeline.id, 'company': pipeline.company or pipeline.name, 'contact': pipeline.name,
                'position': pipeline.position or '', 'contact_information': pipeline.email or pipeline.mobile_number or '',
                'owner_id': pipeline.owner_id,
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
    elif source_type == SalesActivity.SOURCE_EVENT:
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
        source_type = SalesActivity.normalize_source_type(request.form.get('source_type'))
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
        # Remote Engagement uses Activity Date. Scheduled visits use Estimated Start Date
        # as the activity date, so the form does not need a duplicate Visit Date field.
        activity_date = validate_date(request.form.get('activity_date'))
        is_scheduled_visit = SalesActivity.is_scheduled_visit_type(activity_type)
        if is_scheduled_visit:
            # A scheduled visit's activity date is always its Estimated Start Date.
            activity_date = validate_date(request.form.get('start_date'))
        if not activity_date:
            raise ValueError('Activity Date is required for Remote Engagement, or Estimated Start Date is required for a scheduled visit.')
        requested_owner_id = request.form.get('owner_id', type=int) if current_user.is_admin() else None
        owner_id = resolve_new_activity_owner_id(
            source_type, lead=lead, pipeline=pipeline,
            requested_owner_id=requested_owner_id,
            fallback_owner_id=current_user.id,
            allow_source_owner_override=current_user.is_admin(),
        )
        if not db.session.get(User, owner_id):
            raise ValueError('Please select a valid owner.')
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
                actor_id=current_user.id,
            )
            for target in _sync_targets(lead, pipeline):
                append_followup_history(target, followup_text, todo_text, todo_due_date)
            description = f'Created {len(activities)} Remote Engagement sales activity record(s) for {company}'
        else:
            start_at = _parse_datetime(request.form.get('start_date') or request.form.get('activity_date'), request.form.get('start_time'))
            end_at = _parse_datetime(request.form.get('end_date') or request.form.get('activity_date'), request.form.get('end_time'))
            if not start_at or not end_at:
                raise ValueError('Estimated Start Date/Time and Estimated End Date/Time are required for a scheduled visit.')
            if end_at <= start_at:
                raise ValueError('Estimated End Time must be later than Estimated Start Time.')
            activity = SalesActivity(
                activity_type=activity_type, source_type=source_type,
                sales_lead_id=lead.id if lead else None, pipeline_id=pipeline.id if pipeline else None,
                company=company, activity_date=activity_date, estimated_start_at=start_at,
                estimated_end_at=end_at, address=request.form.get('address', '').strip() or None,
                purpose_project=purpose or None, expected_result=expected or None,
                remarks=remarks or None, status=SalesActivity.STATUS_SCHEDULED, owner_id=owner_id,
            )
            db.session.add(activity)
            db.session.flush()
            create_activity_contacts(activity, contacts)
            task = Task(
                content=f'{activity_type} follow-up: {company}' + (f' - {purpose}' if purpose else ''),
                due_date=end_at.date(), owner_id=owner_id, pipeline_id=pipeline.id if pipeline else None,
                sales_lead_id=lead.id if lead else None, sales_activity_id=activity.id,
                company=company, status='In Progress',
            )
            db.session.add(task)
            plan_note = f'{activity_type} scheduled for {activity_date.isoformat()} {start_at:%H:%M}-{end_at:%H:%M}'
            if purpose:
                plan_note += f'; Purpose / Project: {purpose}'
            for target in _sync_targets(lead, pipeline):
                append_followup_history(target, plan_note)
            description = f'Created {activity_type} for {company} on {activity_date.isoformat()} {start_at:%H:%M}-{end_at:%H:%M}'

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
        if activity.get_display_status() != SalesActivity.STATUS_FOLLOW_UP_REQUIRED:
            raise ValueError('Only activities requiring follow-up can be completed here.')
        notes = request.form.get('completion_notes', '').strip()
        todo_text = request.form.get('todo_text', '').strip()
        todo_due_date = validate_date(request.form.get('todo_due_date'))
        if todo_text and not todo_due_date:
            raise ValueError('To-do Due Date is required when Next Steps / To-do is filled.')
        complete_activity(activity, current_user.id, notes)
        lead = activity.sales_lead
        pipeline = activity.pipeline
        history_note = f'{activity.activity_type} feedback: {notes}'
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


@sales_activities_bp.route('/<int:activity_id>/edit', methods=['POST'])
@login_required
def edit(activity_id):
    """Edit or reschedule an open Sales Activity and keep its linked Task aligned."""
    activity = SalesActivity.query.filter_by(id=activity_id, is_deleted=False).first_or_404()
    if not _can_manage(activity):
        flash('Permission denied.', 'danger')
        return redirect(url_for('sales_activities.index'))

    try:
        if not activity.can_edit:
            raise ValueError('Completed or cancelled activities cannot be edited. Create a new activity instead.')

        old_values = {
            'activity_date': activity.activity_date,
            'estimated_start_at': activity.estimated_start_at,
            'estimated_end_at': activity.estimated_end_at,
            'owner_id': activity.owner_id,
            'address': activity.address,
            'purpose_project': activity.purpose_project,
            'expected_result': activity.expected_result,
            'remarks': activity.remarks,
            'task_content': activity.linked_task.content if activity.linked_task else None,
            'task_due_date': activity.linked_task.due_date if activity.linked_task else None,
        }

        owner_id = request.form.get('owner_id', type=int) if current_user.is_admin() else current_user.id
        owner_id = owner_id or activity.owner_id
        if not db.session.get(User, owner_id):
            raise ValueError('Please select a valid owner.')

        if activity.is_scheduled_visit:
            start_at = _parse_datetime(request.form.get('start_date'), request.form.get('start_time'))
            end_at = _parse_datetime(request.form.get('end_date'), request.form.get('end_time'))
            if not start_at or not end_at:
                raise ValueError('Estimated Start Date/Time and Estimated End Date/Time are required for a scheduled visit.')
            if end_at <= start_at:
                raise ValueError('Estimated End Time must be later than Estimated Start Time.')
            activity.activity_date = start_at.date()
            activity.estimated_start_at = start_at
            activity.estimated_end_at = end_at
            activity.address = request.form.get('address', '').strip() or None
            if activity.linked_task:
                activity.linked_task.due_date = end_at.date()
        elif activity.remote_engagement_subtype == 'Next Steps / To-do':
            due_date = validate_date(request.form.get('activity_date'))
            task_content = request.form.get('task_content', '').strip()
            if not due_date:
                raise ValueError('To-do Due Date is required.')
            if not task_content:
                raise ValueError('Next Steps / To-do is required.')
            activity.activity_date = due_date
            activity.followup_notes = task_content
            if not activity.linked_task:
                raise ValueError('The linked Task is missing. Please contact an administrator.')
            activity.linked_task.content = task_content
            activity.linked_task.due_date = due_date
        else:
            activity_date = validate_date(request.form.get('activity_date'))
            if not activity_date:
                raise ValueError('Activity Date is required.')
            activity.activity_date = activity_date

        activity.owner_id = owner_id
        activity.purpose_project = request.form.get('purpose_project', '').strip() or None
        activity.expected_result = request.form.get('expected_result', '').strip() or None
        activity.remarks = request.form.get('remarks', '').strip() or None
        activity.status = SalesActivity.STATUS_SCHEDULED
        activity.contacts.clear()
        create_activity_contacts(activity, _contacts_from_form())

        if activity.linked_task:
            activity.linked_task.owner_id = owner_id
            activity.linked_task.company = activity.company
            activity.linked_task.status = 'In Progress'
            activity.linked_task.check_overdue()

        new_values = {
            'activity_date': activity.activity_date,
            'estimated_start_at': activity.estimated_start_at,
            'estimated_end_at': activity.estimated_end_at,
            'owner_id': activity.owner_id,
            'address': activity.address,
            'purpose_project': activity.purpose_project,
            'expected_result': activity.expected_result,
            'remarks': activity.remarks,
            'task_content': activity.linked_task.content if activity.linked_task else None,
            'task_due_date': activity.linked_task.due_date if activity.linked_task else None,
        }
        log_activity(
            current_user, 'Sales Activity - Rescheduled', 'sales_activity', activity.id,
            activity.company, f'Updated/rescheduled {activity.activity_type} for {activity.company}',
            request.remote_addr, old_values=old_values, new_values=new_values, commit=False,
        )
        db.session.commit()
        flash('Sales Activity updated successfully!', 'success')
    except (ValueError, PermissionError) as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error updating Sales Activity: {exc}', 'danger')
    return redirect(url_for('sales_activities.index'))


@sales_activities_bp.route('/<int:activity_id>/cancel', methods=['POST'])
@login_required
def cancel(activity_id):
    """Cancel an open activity without deleting its history."""
    activity = SalesActivity.query.filter_by(id=activity_id, is_deleted=False).first_or_404()
    if not _can_manage(activity):
        flash('Permission denied.', 'danger')
        return redirect(url_for('sales_activities.index'))

    try:
        if activity.status in (SalesActivity.STATUS_COMPLETED, SalesActivity.STATUS_CANCELLED):
            raise ValueError('Only open activities can be cancelled.')
        reason = request.form.get('cancellation_reason', '').strip()
        if not reason:
            raise ValueError('Cancellation Reason is required.')
        old_status = activity.get_display_status()
        activity.status = SalesActivity.STATUS_CANCELLED
        activity.cancelled_at = datetime.utcnow()
        activity.cancelled_by_id = current_user.id
        activity.cancellation_reason = reason
        if activity.linked_task and activity.linked_task.status != 'Completed':
            activity.linked_task.status = 'Cancelled'
            activity.linked_task.completion_notes = None
            activity.linked_task.completed_at = None
            activity.linked_task.completed_by_id = None
        log_activity(
            current_user, 'Sales Activity - Cancelled', 'sales_activity', activity.id,
            activity.company, f'Cancelled {activity.activity_type} for {activity.company}: {reason}',
            request.remote_addr, old_values={'status': old_status},
            new_values={'status': SalesActivity.STATUS_CANCELLED, 'cancellation_reason': reason}, commit=False,
        )
        db.session.commit()
        flash('Sales Activity cancelled.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    except Exception as exc:
        db.session.rollback()
        flash(f'Error cancelling Sales Activity: {exc}', 'danger')
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
