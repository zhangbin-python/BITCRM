"""Business services shared by Sales Activities, Leads, Pipeline, and Tasks."""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import inspect

from extensions import db
from models import (
    DeletedRecord,
    Pipeline,
    SalesActivity,
    SalesActivityContact,
    SalesLead,
    Task,
)


def _serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def snapshot_model(instance):
    """Return a JSON-safe snapshot of a SQLAlchemy model."""
    return {
        column.key: _serialize_value(getattr(instance, column.key))
        for column in inspect(instance).mapper.column_attrs
    }


def soft_delete(instance, user_id, entity_type, entity_name=None, reason=None):
    """Mark a record deleted and preserve an immutable database snapshot."""
    now = datetime.utcnow()
    setattr(instance, 'is_deleted', True)
    setattr(instance, 'deleted_at', now)
    setattr(instance, 'deleted_by_id', user_id)
    archive = DeletedRecord(
        entity_type=entity_type,
        entity_id=instance.id,
        entity_name=entity_name,
        data_snapshot=json.dumps(snapshot_model(instance), ensure_ascii=False),
        deleted_by_id=user_id,
        deletion_reason=reason,
        deleted_at=now,
    )
    db.session.add(archive)
    return archive


def append_followup_history(
    entity, followup_text=None, todo_text=None, todo_due_date=None, timestamp=None,
    followup_activity_type=None, todo_activity_type=None,
    followup_start_at=None, followup_end_at=None,
    todo_start_at=None, todo_end_at=None,
):
    """Append new typed entries without parsing or changing historical text."""
    timestamp = timestamp or datetime.utcnow()
    entries = []
    if followup_text:
        type_text = f" [{followup_activity_type}]" if followup_activity_type else ''
        schedule_text = ''
        if followup_start_at and followup_end_at:
            schedule_text = (
                f" ({followup_start_at:%Y-%m-%d %H:%M} -> "
                f"{followup_end_at:%Y-%m-%d %H:%M})"
            )
        entries.append(
            f"Follow-up{type_text}, {timestamp.strftime('%Y-%m-%d %H:%M')}"
            f"{schedule_text}: {followup_text}"
        )
    if todo_text:
        type_text = f" [{todo_activity_type}]" if todo_activity_type else ''
        if todo_start_at and todo_end_at:
            timing_text = f" scheduled {todo_start_at:%Y-%m-%d %H:%M} -> {todo_end_at:%Y-%m-%d %H:%M}"
        else:
            due_text = todo_due_date.strftime('%Y-%m-%d') if isinstance(todo_due_date, date) else str(todo_due_date or '')
            timing_text = f" by {due_text}" if due_text else ''
        entries.append(
            f"To-do{type_text}, {timestamp.strftime('%Y-%m-%d')}: "
            f"{todo_text}{timing_text}"
        )
    if not entries:
        return []
    existing = getattr(entity, 'follow_up', None) or ''
    setattr(entity, 'follow_up', '\n'.join([part for part in [existing, *entries] if part]))
    return entries


def _entity_context(source_type, sales_lead_id=None, pipeline_id=None, company=None):
    """Validate and return the selected CRM source context."""
    lead = None
    pipeline = None
    if source_type == 'Sales Leads':
        if not sales_lead_id:
            raise ValueError('A Sales Lead must be selected from the system search results.')
        lead = db.session.get(SalesLead, int(sales_lead_id))
        if not lead or lead.is_deleted:
            raise ValueError('The selected Sales Lead is not available.')
        company = lead.company or lead.name
    elif source_type == 'Pipeline':
        if not pipeline_id:
            raise ValueError('A Pipeline record must be selected from the system search results.')
        pipeline = db.session.get(Pipeline, int(pipeline_id))
        if not pipeline or pipeline.is_deleted:
            raise ValueError('The selected Pipeline record is not available.')
        company = pipeline.company or pipeline.name
    elif not company:
        raise ValueError('Company is required for this activity source.')

    # Link both CRM records when the Lead and Pipeline are already associated.
    # This keeps new Activities and Tasks visible from either module without
    # duplicating the activity. Historical records remain unchanged.
    if lead and lead.pipeline and not lead.pipeline.is_deleted:
        pipeline = lead.pipeline
    if pipeline and pipeline.sales_lead and not pipeline.sales_lead.is_deleted:
        lead = pipeline.sales_lead
    return lead, pipeline, company


def resolve_new_activity_owner_id(
    source_type, *, lead=None, pipeline=None, requested_owner_id=None,
    fallback_owner_id=None, allow_source_owner_override=False,
):
    """Resolve the owner for a newly created Sales Activity or linked Task.

    CRM-backed activities inherit the current owner of their selected source.
    The standalone Sales Activity form may explicitly allow an administrator
    to override that default. Other sources may use a requested owner and
    otherwise fall back to the user creating the record. Existing activities
    are intentionally not rewritten when a Lead or Pipeline is reassigned.
    """
    if allow_source_owner_override and requested_owner_id:
        return requested_owner_id
    if source_type == 'Sales Leads' and lead and lead.owner_id:
        return lead.owner_id
    if source_type == 'Pipeline' and pipeline and pipeline.owner_id:
        return pipeline.owner_id
    return requested_owner_id or fallback_owner_id


def create_activity_contacts(activity, contacts):
    """Create repeatable contact rows, retaining one blank row if none supplied."""
    normalized = []
    for index, contact in enumerate(contacts or []):
        if not isinstance(contact, dict):
            continue
        name = (contact.get('contact_name') or contact.get('name') or '').strip()
        position = (contact.get('position') or '').strip()
        info = (contact.get('contact_information') or contact.get('information') or '').strip()
        if not any((name, position, info)):
            continue
        normalized.append(SalesActivityContact(
            contact_name=name or None,
            position=position or None,
            contact_information=info or None,
            sort_order=index,
        ))
    if not normalized:
        normalized.append(SalesActivityContact(sort_order=0))
    activity.contacts.extend(normalized)


def _normalize_required_activity_type(value, field_label):
    activity_type = SalesActivity.normalize_type((value or '').strip())
    if activity_type not in SalesActivity.TYPE_OPTIONS:
        raise ValueError(f'{field_label} is required and must be a valid Sales Activity Type.')
    return activity_type


def _validate_visit_window(start_at, end_at, field_label):
    if not start_at or not end_at:
        raise ValueError(f'{field_label} Start Date/Time and End Date/Time are required for a visit.')
    if end_at <= start_at:
        raise ValueError(f'{field_label} End Date/Time must be later than Start Date/Time.')


def create_followup_activities(
    *, source_type, owner_id, sales_lead_id=None, pipeline_id=None,
    company=None, followup_text=None, todo_text=None,
    followup_activity_type=None, todo_activity_type=None,
    followup_activity_date=None, followup_start_at=None, followup_end_at=None,
    followup_address=None, todo_due_date=None, todo_start_at=None,
    todo_end_at=None, todo_address=None, purpose_project=None,
    expected_result=None, remarks=None, contacts=None, actor_id=None,
):
    """Create typed Sales Activities from Follow-up Notes and Next Steps.

    Follow-up Notes represent an activity that has already happened and create a
    completed activity without a Task. Next Steps represent future work and
    create a scheduled activity plus one linked Task. The two activity types are
    selected and validated independently. Existing history is never parsed.
    """
    followup_text = (followup_text or '').strip()
    todo_text = (todo_text or '').strip()
    if not followup_text and not todo_text:
        raise ValueError('At least one of Follow-up Notes or Next Steps / To-do is required.')

    lead, pipeline, company = _entity_context(source_type, sales_lead_id, pipeline_id, company)
    owner_id = resolve_new_activity_owner_id(
        source_type, lead=lead, pipeline=pipeline,
        requested_owner_id=owner_id, fallback_owner_id=owner_id,
    )
    if not owner_id:
        raise ValueError('An owner is required for the Sales Activity.')
    created = []

    if followup_text:
        activity_type = _normalize_required_activity_type(
            followup_activity_type, 'Follow-up Activity Type'
        )
        is_visit = SalesActivity.is_scheduled_visit_type(activity_type)
        if is_visit:
            _validate_visit_window(followup_start_at, followup_end_at, 'Follow-up Visit')
            activity_date = followup_start_at.date()
        else:
            activity_date = followup_activity_date or date.today()

        activity = SalesActivity(
            activity_type=activity_type,
            remote_engagement_subtype='Follow-up' if not is_visit else None,
            source_type=source_type,
            sales_lead_id=lead.id if lead else None,
            pipeline_id=pipeline.id if pipeline else None,
            company=company,
            activity_date=activity_date,
            estimated_start_at=followup_start_at if is_visit else None,
            estimated_end_at=followup_end_at if is_visit else None,
            address=(followup_address or '').strip() or None if is_visit else None,
            purpose_project=purpose_project,
            expected_result=expected_result,
            remarks=remarks,
            followup_notes=followup_text,
            completion_notes=followup_text,
            status=SalesActivity.STATUS_COMPLETED,
            owner_id=owner_id,
            completed_at=datetime.utcnow(),
            completed_by_id=actor_id or owner_id,
        )
        db.session.add(activity)
        db.session.flush()
        create_activity_contacts(activity, contacts)
        created.append(activity)

    if todo_text:
        activity_type = _normalize_required_activity_type(
            todo_activity_type, 'Next Step Activity Type'
        )
        is_visit = SalesActivity.is_scheduled_visit_type(activity_type)
        if is_visit:
            _validate_visit_window(todo_start_at, todo_end_at, 'Next Step Visit')
            activity_date = todo_start_at.date()
            task_due_date = todo_end_at.date()
        else:
            if not todo_due_date:
                raise ValueError('To-do Due Date is required for a Remote Engagement Next Step.')
            activity_date = todo_due_date
            task_due_date = todo_due_date

        activity = SalesActivity(
            activity_type=activity_type,
            remote_engagement_subtype='Next Steps / To-do' if not is_visit else None,
            source_type=source_type,
            sales_lead_id=lead.id if lead else None,
            pipeline_id=pipeline.id if pipeline else None,
            company=company,
            activity_date=activity_date,
            estimated_start_at=todo_start_at if is_visit else None,
            estimated_end_at=todo_end_at if is_visit else None,
            address=(todo_address or '').strip() or None if is_visit else None,
            purpose_project=purpose_project,
            expected_result=expected_result,
            remarks=remarks,
            followup_notes=todo_text,
            status=SalesActivity.STATUS_SCHEDULED,
            owner_id=owner_id,
        )
        db.session.add(activity)
        db.session.flush()
        create_activity_contacts(activity, contacts)
        task = Task(
            content=todo_text,
            due_date=task_due_date,
            owner_id=owner_id,
            pipeline_id=pipeline.id if pipeline else None,
            sales_lead_id=lead.id if lead else None,
            sales_activity_id=activity.id,
            company=company,
            status='In Progress',
        )
        db.session.add(task)
        created.append(activity)

    return created


def create_remote_engagement_activities(
    *, source_type, owner_id, sales_lead_id=None, pipeline_id=None,
    company=None, followup_text=None, todo_text=None, todo_due_date=None,
    activity_date=None, purpose_project=None, expected_result=None,
    remarks=None, contacts=None, actor_id=None,
):
    """Backward-compatible wrapper for Remote Engagement-only callers."""
    return create_followup_activities(
        source_type=source_type,
        owner_id=owner_id,
        sales_lead_id=sales_lead_id,
        pipeline_id=pipeline_id,
        company=company,
        followup_text=followup_text,
        todo_text=todo_text,
        followup_activity_type=(
            SalesActivity.TYPE_REMOTE_ENGAGEMENT if (followup_text or '').strip() else None
        ),
        todo_activity_type=(
            SalesActivity.TYPE_REMOTE_ENGAGEMENT if (todo_text or '').strip() else None
        ),
        followup_activity_date=activity_date,
        todo_due_date=todo_due_date,
        purpose_project=purpose_project,
        expected_result=expected_result,
        remarks=remarks,
        contacts=contacts,
        actor_id=actor_id,
    )


def complete_activity(activity, user_id, completion_notes, complete_linked_task=True):
    """Complete an activity and, where applicable, its linked Task."""
    completion_notes = (completion_notes or '').strip()
    if not completion_notes:
        raise ValueError('Completion Notes are required.')
    now = datetime.utcnow()
    activity.status = SalesActivity.STATUS_COMPLETED
    activity.completed_at = now
    activity.completed_by_id = user_id
    activity.completion_notes = completion_notes
    if complete_linked_task and activity.linked_task and activity.linked_task.status != 'Completed':
        complete_task(activity.linked_task, completion_notes, user_id, update_activity=False)


def complete_task(task, completion_notes, user_id, update_activity=True):
    """Complete a Task with mandatory notes and update its linked activity."""
    if task.status == 'Cancelled':
        raise ValueError('Cancelled tasks cannot be completed.')
    completion_notes = (completion_notes or '').strip()
    if not completion_notes:
        raise ValueError('Completion Notes are required.')
    task.status = 'Completed'
    task.completion_notes = completion_notes
    task.completed_at = datetime.utcnow()
    task.completed_by_id = user_id
    if update_activity and task.sales_activity:
        task.sales_activity.status = SalesActivity.STATUS_COMPLETED
        task.sales_activity.completed_at = task.completed_at
        task.sales_activity.completed_by_id = user_id
        task.sales_activity.completion_notes = completion_notes


def append_task_completion_history(task, completion_notes):
    """Append one completion entry to every CRM record linked to a Task."""
    activity = task.sales_activity
    lead = task.sales_lead or (activity.sales_lead if activity else None)
    pipeline = task.pipeline or (activity.pipeline if activity else None)
    if lead and lead.pipeline and not lead.pipeline.is_deleted:
        pipeline = pipeline or lead.pipeline
    if pipeline and pipeline.sales_lead and not pipeline.sales_lead.is_deleted:
        lead = lead or pipeline.sales_lead

    targets = []
    seen = set()
    for target in (lead, pipeline):
        if not target or target.is_deleted:
            continue
        key = (type(target).__name__, target.id)
        if key not in seen:
            seen.add(key)
            targets.append(target)

    if activity:
        history_text = f'{task.content}; Feedback: {completion_notes}'
        activity_type = activity.activity_type
    else:
        history_text = f'Task completed: {task.content}; Feedback: {completion_notes}'
        activity_type = None
    for target in targets:
        append_followup_history(
            target,
            followup_text=history_text,
            followup_activity_type=activity_type,
        )
    return targets


def reopen_task(task):
    if task.status != 'Completed':
        raise ValueError('Only completed tasks can be reopened.')
    task.status = 'Overdue' if task.due_date and date.today() > task.due_date else 'In Progress'
    task.completion_notes = None
    task.completed_at = None
    task.completed_by_id = None
    if task.sales_activity:
        task.sales_activity.status = SalesActivity.STATUS_SCHEDULED
        task.sales_activity.completed_at = None
        task.sales_activity.completed_by_id = None
        task.sales_activity.completion_notes = None
