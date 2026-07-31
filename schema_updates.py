"""Small idempotent schema compatibility updates for existing BITCRM databases."""
from sqlalchemy import inspect, text

from extensions import db


COLUMN_UPDATES = {
    'sales_leads': {
        'follow_up': 'TEXT',
        'is_deleted': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'deleted_at': 'TIMESTAMP NULL',
        'deleted_by_id': 'INTEGER NULL',
    },
    'pipeline': {
        'is_deleted': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'deleted_at': 'TIMESTAMP NULL',
        'deleted_by_id': 'INTEGER NULL',
    },
    'tasks': {
        'sales_lead_id': 'INTEGER NULL',
        'sales_activity_id': 'INTEGER NULL',
        'completion_notes': 'TEXT NULL',
        'completed_at': 'TIMESTAMP NULL',
        'completed_by_id': 'INTEGER NULL',
        'is_deleted': 'BOOLEAN NOT NULL DEFAULT FALSE',
        'deleted_at': 'TIMESTAMP NULL',
        'deleted_by_id': 'INTEGER NULL',
    },
    'sales_activities': {
        'completion_notes': 'TEXT NULL',
    },
    'activity_logs': {
        'old_values': 'TEXT NULL',
        'new_values': 'TEXT NULL',
        'extra_data': 'TEXT NULL',
    },
}


def ensure_sales_activity_columns():
    """Add missing columns before ORM queries touch an existing database."""
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    for table_name, columns in COLUMN_UPDATES.items():
        if table_name not in tables:
            continue
        existing = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name, ddl_type in columns.items():
            if column_name in existing:
                continue
            db.session.execute(text(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl_type}'
            ))
            db.session.commit()
            existing.add(column_name)
