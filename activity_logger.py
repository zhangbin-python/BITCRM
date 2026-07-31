"""
Activity Logger Utility
Provides functions to log user activities throughout the application.
"""
from extensions import db
from models import ActivityLog
from flask import has_request_context, request
import json
from datetime import date, datetime


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _dump_json(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=_json_default)


def log_activity(user, action_type, subject_type, subject_id=None, subject_name=None,
                 description=None, ip_address=None, old_values=None, new_values=None,
                 extra_data=None, commit=True):
    """Create a durable operation log entry with optional before/after details."""
    if hasattr(user, 'id'):
        user_id = user.id
        user_name = getattr(user, 'username', None) or 'Unknown'
    else:
        user_id = user
        user_name = 'Unknown'

    if ip_address is None and has_request_context():
        ip_address = request.remote_addr

    activity = ActivityLog(
        user_id=user_id,
        user_name=user_name,
        action_type=action_type,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_name=subject_name,
        description=description,
        old_values=_dump_json(old_values),
        new_values=_dump_json(new_values),
        extra_data=_dump_json(extra_data),
        ip_address=ip_address,
    )
    db.session.add(activity)
    if commit:
        db.session.commit()
    return activity


def log_lead_import(user, count, ip_address=None):
    """Log lead import activity."""
    return log_activity(
        user=user,
        action_type='Leads - Imported',
        subject_type='lead',
        subject_name=f'{count} leads imported',
        description=f'Imported {count} leads from file',
        ip_address=ip_address
    )


def log_lead_created(user, lead, ip_address=None):
    """Log lead creation activity."""
    return log_activity(
        user=user,
        action_type='Leads - Created',
        subject_type='lead',
        subject_id=lead.id,
        subject_name=lead.name,
        description=f'Created new lead: {lead.name}',
        ip_address=ip_address
    )


def log_lead_updated(user, lead, changes=None, ip_address=None):
    """Log lead update activity."""
    return log_activity(
        user=user,
        action_type='Leads - Updated',
        subject_type='lead',
        subject_id=lead.id,
        subject_name=lead.name,
        description=changes or f'Updated lead: {lead.name}',
        ip_address=ip_address
    )


def log_lead_deleted(user, lead_name, ip_address=None):
    """Log lead deletion activity."""
    return log_activity(
        user=user,
        action_type='Leads - Deleted',
        subject_type='lead',
        subject_name=lead_name,
        description=f'Deleted lead: {lead_name}',
        ip_address=ip_address
    )


def log_pipeline_created(user, pipeline, ip_address=None):
    """Log pipeline creation activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Created',
        subject_type='pipeline',
        subject_id=pipeline.id,
        subject_name=pipeline.name or pipeline.company,
        description=f'Created new pipeline entry: {pipeline.name or pipeline.company}',
        ip_address=ip_address
    )


def log_pipeline_stage_changed(user, pipeline, old_stage, new_stage, ip_address=None):
    """Log pipeline stage change activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Stage Changed',
        subject_type='pipeline',
        subject_id=pipeline.id,
        subject_name=pipeline.name or pipeline.company,
        description=f'Stage changed from "{old_stage}" to "{new_stage}"',
        ip_address=ip_address
    )


def log_pipeline_updated(user, pipeline, changes=None, ip_address=None):
    """Log pipeline update activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Updated',
        subject_type='pipeline',
        subject_id=pipeline.id,
        subject_name=pipeline.name or pipeline.company,
        description=changes or f'Updated pipeline: {pipeline.name or pipeline.company}',
        ip_address=ip_address
    )


def log_pipeline_deleted(user, pipeline_id, company_name, ip_address=None):
    """Log pipeline deletion activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Deleted',
        subject_type='pipeline',
        subject_id=pipeline_id,
        subject_name=company_name,
        description=f'Deleted pipeline entry: {company_name}',
        ip_address=ip_address
    )


def log_task_created(user, task, ip_address=None):
    """Log task creation activity."""
    return log_activity(
        user=user,
        action_type='Task - Created',
        subject_type='task',
        subject_id=task.id,
        subject_name=task.content[:50] if task.content else 'Untitled Task',
        description=f'Created task: {task.content[:50]}',
        ip_address=ip_address
    )


def log_task_completed(user, task, ip_address=None):
    """Log task completion activity."""
    return log_activity(
        user=user,
        action_type='Task - Completed',
        subject_type='task',
        subject_id=task.id,
        subject_name=task.content[:50] if task.content else 'Untitled Task',
        description=f'Completed task: {task.content[:50]}',
        ip_address=ip_address
    )


def log_task_reopened(user, task, ip_address=None):
    """Log task reopen activity."""
    return log_activity(
        user=user,
        action_type='Task - Reopened',
        subject_type='task',
        subject_id=task.id,
        subject_name=task.content[:50] if task.content else 'Untitled Task',
        description=f'Reopened task: {task.content[:50]}',
        ip_address=ip_address
    )


def log_followup_created(user, pipeline, ip_address=None):
    """Log follow-up creation activity."""
    return log_activity(
        user=user,
        action_type='Follow up - Note',
        subject_type='pipeline',
        subject_id=pipeline.id,
        subject_name=pipeline.name or pipeline.company,
        description=f'Added follow-up note to: {pipeline.name or pipeline.company}',
        ip_address=ip_address
    )


def log_account_created(user, account_name, ip_address=None):
    """Log account creation activity."""
    return log_activity(
        user=user,
        action_type='Account - Created',
        subject_type='account',
        subject_name=account_name,
        description=f'Created account: {account_name}',
        ip_address=ip_address
    )


def log_lead_exported(user, count, ip_address=None):
    """Log lead export activity."""
    return log_activity(
        user=user,
        action_type='Leads - Exported',
        subject_type='lead',
        subject_name=f'{count} leads exported',
        description=f'Exported {count} leads to file',
        ip_address=ip_address
    )


def log_pipeline_deleted(user, pipeline_id, company_name, ip_address=None):
    """Log pipeline deletion activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Deleted',
        subject_type='pipeline',
        subject_id=pipeline_id,
        subject_name=company_name,
        description=f'Deleted pipeline entry: {company_name}',
        ip_address=ip_address
    )


def log_pipeline_exported(user, count, ip_address=None):
    """Log pipeline export activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Exported',
        subject_type='pipeline',
        subject_name=f'{count} pipelines exported',
        description=f'Exported {count} pipeline entries to file',
        ip_address=ip_address
    )


def log_pipeline_imported(user, count, ip_address=None):
    """Log pipeline import activity."""
    return log_activity(
        user=user,
        action_type='Pipeline - Imported',
        subject_type='pipeline',
        subject_name=f'{count} pipelines imported',
        description=f'Imported {count} pipeline entries from file',
        ip_address=ip_address
    )


def log_task_edited(user, task_id, content_preview, ip_address=None):
    """Log task edit activity."""
    return log_activity(
        user=user,
        action_type='Task - Edited',
        subject_type='task',
        subject_id=task_id,
        subject_name=content_preview[:50] if content_preview else 'Untitled Task',
        description=f'Edited task: {content_preview[:50]}',
        ip_address=ip_address
    )


def log_task_deleted(user, task_id, ip_address=None):
    """Log task deletion activity."""
    return log_activity(
        user=user,
        action_type='Task - Deleted',
        subject_type='task',
        subject_id=task_id,
        subject_name=f'Task #{task_id}',
        description=f'Deleted task #{task_id}',
        ip_address=ip_address
    )


def log_task_status_changed(user, task_id, old_status, new_status, ip_address=None):
    """Log task status change activity."""
    return log_activity(
        user=user,
        action_type='Task - Status Changed',
        subject_type='task',
        subject_id=task_id,
        subject_name=f'Task #{task_id}',
        description=f'Status changed from "{old_status}" to "{new_status}"',
        ip_address=ip_address
    )


def log_password_changed(user, ip_address=None):
    """Log password change activity."""
    return log_activity(
        user=user,
        action_type='System - Password Changed',
        subject_type='account',
        subject_id=user.id if hasattr(user, 'id') else None,
        subject_name=user.username if hasattr(user, 'username') else 'Unknown',
        description='User changed their password',
        ip_address=ip_address
    )


def log_language_changed(user, language, ip_address=None):
    """Log language change activity."""
    language_name = 'Chinese' if language == 'zh' else 'English'
    return log_activity(
        user=user,
        action_type='System - Language Changed',
        subject_type='account',
        subject_id=user.id if hasattr(user, 'id') else None,
        subject_name=user.username if hasattr(user, 'username') else 'Unknown',
        description=f'Changed language to {language_name}',
        ip_address=ip_address
    )


def log_user_created(user, target_username, ip_address=None):
    """Log user creation activity."""
    return log_activity(
        user=user,
        action_type='Admin - User Created',
        subject_type='account',
        subject_name=target_username,
        description=f'Created new user account: {target_username}',
        ip_address=ip_address
    )


def log_user_status_changed(user, target_username, new_status, ip_address=None):
    """Log user status change activity."""
    status_text = 'activated' if new_status else 'deactivated'
    return log_activity(
        user=user,
        action_type='Admin - User Status Changed',
        subject_type='account',
        subject_name=target_username,
        description=f'User {target_username} {status_text}',
        ip_address=ip_address
    )


def log_filter_applied(user, filter_type, filter_details, ip_address=None):
    """Log filter application activity."""
    return log_activity(
        user=user,
        action_type='Filter - Applied',
        subject_type='system',
        subject_name=filter_type,
        description=f'Applied filter: {filter_type} - {filter_details}',
        ip_address=ip_address
    )


def log_column_visibility_changed(user, page, columns, ip_address=None):
    """Log column visibility change activity."""
    return log_activity(
        user=user,
        action_type='Column - Visibility Changed',
        subject_type='system',
        subject_name=f'{page} columns',
        description=f'Changed column visibility on {page}: {", ".join(columns)}',
        ip_address=ip_address
    )


def log_login(user, ip_address=None, success=True):
    """Log user login activity."""
    if success:
        return log_activity(
            user=user,
            action_type='System - Login',
            subject_type='account',
            subject_id=user.id if hasattr(user, 'id') else None,
            subject_name=user.username if hasattr(user, 'username') else 'Unknown',
            description='User logged in successfully',
            ip_address=ip_address
        )
    else:
        if not hasattr(user, 'id'):
            return None
        return log_activity(
            user=user,
            action_type='System - Failed Login',
            subject_type='account',
            subject_name=user.username if hasattr(user, 'username') else 'Unknown',
            description='Failed login attempt',
            ip_address=ip_address
        )


def log_logout(user, ip_address=None):
    """Log user logout activity."""
    return log_activity(
        user=user,
        action_type='System - Logout',
        subject_type='account',
        subject_id=user.id if hasattr(user, 'id') else None,
        subject_name=user.username if hasattr(user, 'username') else 'Unknown',
        description='User logged out',
        ip_address=ip_address
    )
