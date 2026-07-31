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


def append_followup_history(entity, followup_text=None, todo_text=None, todo_due_date=None, timestamp=None):
    """Append the existing Follow-up History format without parsing old records."""
    timestamp = timestamp or datetime.utcnow()
    entries = []
    if followup_text:
        entries.append(f"Follow-up, {timestamp.strftime('%Y-%m-%d %H:%M')}: {followup_text}")
    if todo_text:
        due_text = todo_due_date.strftime('%Y-%m-%d') if isinstance(todo_due_date, date) else str(todo_due_date or '')
        entries.append(f"To-do, {timestamp.strftime('%Y-%m-%d')}: {todo_text} by {due_text}")
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
    return lead, pipeline, company


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


def create_online_activities(
    *, source_type, owner_id, sales_lead_id=None, pipeline_id=None,
    company=None, followup_text=None, todo_text=None, todo_due_date=None,
    activity_date=None, purpose_project=None, expected_result=None,
    remarks=None, contacts=None,
):
    """Create separate Online activities for Follow-up Notes and To-do.

    Follow-up Notes produce a completed activity. Next Steps / To-do produces
    another pending activity and one linked Task. Existing history is never read
    or parsed here.
    """
    followup_text = (followup_text or '').strip()
    todo_text = (todo_text or '').strip()
    if not followup_text and not todo_text:
        raise ValueError('At least one of Follow-up Notes or Next Steps / To-do is required.')
    lead, pipeline, company = _entity_context(source_type, sales_lead_id, pipeline_id, company)
    activity_date = activity_date or date.today()
    created = []

    if followup_text:
        activity = SalesActivity(
            activity_type='Online',
            online_subtype='Follow-up',
            source_type=source_type,
            sales_lead_id=lead.id if lead else None,
            pipeline_id=pipeline.id if pipeline else None,
            company=company,
            activity_date=activity_date,
            purpose_project=purpose_project,
            expected_result=expected_result,
            remarks=remarks,
            followup_notes=followup_text,
            completion_notes=followup_text,
            status='Completed',
            owner_id=owner_id,
            completed_at=datetime.utcnow(),
            completed_by_id=owner_id,
        )
        db.session.add(activity)
        db.session.flush()
        create_activity_contacts(activity, contacts)
        created.append(activity)

    if todo_text:
        todo_date = todo_due_date or activity_date
        activity = SalesActivity(
            activity_type='Online',
            online_subtype='Next Steps / To-do',
            source_type=source_type,
            sales_lead_id=lead.id if lead else None,
            pipeline_id=pipeline.id if pipeline else None,
            company=company,
            activity_date=todo_date,
            purpose_project=purpose_project,
            expected_result=expected_result,
            remarks=remarks,
            followup_notes=todo_text,
            status='Pending Follow-up',
            owner_id=owner_id,
        )
        db.session.add(activity)
        db.session.flush()
        create_activity_contacts(activity, contacts)
        task = Task(
            content=todo_text,
            due_date=todo_date,
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


def complete_activity(activity, user_id, completion_notes, complete_linked_task=True):
    """Complete an activity and, where applicable, its linked Task."""
    completion_notes = (completion_notes or '').strip()
    if not completion_notes:
        raise ValueError('Completion Notes are required.')
    now = datetime.utcnow()
    activity.status = 'Completed'
    activity.completed_at = now
    activity.completed_by_id = user_id
    activity.completion_notes = completion_notes
    if complete_linked_task and activity.linked_task and activity.linked_task.status != 'Completed':
        complete_task(activity.linked_task, completion_notes, user_id, update_activity=False)


def complete_task(task, completion_notes, user_id, update_activity=True):
    """Complete a Task with mandatory notes and update its linked activity."""
    completion_notes = (completion_notes or '').strip()
    if not completion_notes:
        raise ValueError('Completion Notes are required.')
    task.status = 'Completed'
    task.completion_notes = completion_notes
    task.completed_at = datetime.utcnow()
    task.completed_by_id = user_id
    if update_activity and task.sales_activity:
        task.sales_activity.status = 'Completed'
        task.sales_activity.completed_at = task.completed_at
        task.sales_activity.completed_by_id = user_id
        task.sales_activity.completion_notes = completion_notes


def reopen_task(task):
    task.status = 'Overdue' if task.due_date and date.today() > task.due_date else 'In Progress'
    task.completion_notes = None
    task.completed_at = None
    task.completed_by_id = None
    if task.sales_activity:
        task.sales_activity.status = 'Pending Follow-up'
        task.sales_activity.completed_at = None
        task.sales_activity.completed_by_id = None
        task.sales_activity.completion_notes = None
