"""
Cross-database migration script for pipeline.m1-m12.

Unified target:
- Database columns use NUMERIC(15,4)
- Python values stay as float via SQLAlchemy `asdecimal=False`

Run:
    python fix_m1_m12_columns.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import inspect, text

from app import app
from extensions import db


TARGET_COLUMNS = [f"m{i}" for i in range(1, 13)]
TARGET_SQLITE_TYPE = "NUMERIC"
TARGET_DECIMAL_TYPE = "NUMERIC(15,4)"


def get_existing_column_names():
    inspector = inspect(db.engine)
    return {column["name"] for column in inspector.get_columns("pipeline")}


def migrate_postgresql():
    statements = []
    for column in TARGET_COLUMNS:
        statements.append(
            f"ALTER COLUMN {column} TYPE {TARGET_DECIMAL_TYPE} "
            f"USING ROUND(COALESCE({column}, 0)::numeric, 4)"
        )

    sql = "ALTER TABLE pipeline\n" + ",\n".join(statements) + ";"
    db.session.execute(text(sql))


def migrate_sqlite():
    existing_columns = get_existing_column_names()
    missing_columns = [column for column in TARGET_COLUMNS if column not in existing_columns]
    if missing_columns:
        raise RuntimeError(f"Missing pipeline columns: {', '.join(missing_columns)}")

    db.session.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        db.session.execute(text(
            f"""
            CREATE TABLE pipeline__tmp (
                id INTEGER PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                company VARCHAR(200),
                industry VARCHAR(100),
                position VARCHAR(100),
                email VARCHAR(120),
                mobile_number VARCHAR(50),
                owner_id INTEGER NOT NULL,
                sales_lead_id INTEGER,
                product VARCHAR(200),
                tcv_usd FLOAT,
                contract_term_yrs INTEGER,
                mrc_usd FLOAT,
                otc_usd FLOAT,
                gp_margin FLOAT,
                gp FLOAT,
                mg VARCHAR(50),
                est_sign_date DATE,
                est_act_date DATE,
                award_date DATE,
                proposal_sent_date DATE,
                win_rate FLOAT,
                stage VARCHAR(50),
                level VARCHAR(50),
                date_added DATE,
                stuckpoint TEXT,
                comments TEXT,
                follow_up TEXT,
                m1 {TARGET_SQLITE_TYPE},
                m2 {TARGET_SQLITE_TYPE},
                m3 {TARGET_SQLITE_TYPE},
                m4 {TARGET_SQLITE_TYPE},
                m5 {TARGET_SQLITE_TYPE},
                m6 {TARGET_SQLITE_TYPE},
                m7 {TARGET_SQLITE_TYPE},
                m8 {TARGET_SQLITE_TYPE},
                m9 {TARGET_SQLITE_TYPE},
                m10 {TARGET_SQLITE_TYPE},
                m11 {TARGET_SQLITE_TYPE},
                m12 {TARGET_SQLITE_TYPE},
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY(owner_id) REFERENCES users (id),
                FOREIGN KEY(sales_lead_id) REFERENCES sales_leads (id)
            )
            """
        ))

        all_columns = [
            "id", "name", "company", "industry", "position", "email", "mobile_number",
            "owner_id", "sales_lead_id", "product", "tcv_usd", "contract_term_yrs",
            "mrc_usd", "otc_usd", "gp_margin", "gp", "mg", "est_sign_date", "est_act_date",
            "award_date", "proposal_sent_date", "win_rate", "stage", "level", "date_added",
            "stuckpoint", "comments", "follow_up", "m1", "m2", "m3", "m4", "m5", "m6",
            "m7", "m8", "m9", "m10", "m11", "m12", "created_at", "updated_at"
        ]
        select_columns = []
        for column in all_columns:
            if column in TARGET_COLUMNS:
                select_columns.append(f"ROUND(COALESCE({column}, 0), 4) AS {column}")
            else:
                select_columns.append(column)

        db.session.execute(text(
            f"""
            INSERT INTO pipeline__tmp ({", ".join(all_columns)})
            SELECT {", ".join(select_columns)}
            FROM pipeline
            """
        ))
        db.session.execute(text("DROP TABLE pipeline"))
        db.session.execute(text("ALTER TABLE pipeline__tmp RENAME TO pipeline"))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pipeline_sales_lead_id ON pipeline (sales_lead_id)"
        ))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pipeline_est_sign_date ON pipeline (est_sign_date)"
        ))
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_pipeline_stage ON pipeline (stage)"
        ))
        db.session.execute(text("PRAGMA foreign_keys=ON"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        db.session.execute(text("PRAGMA foreign_keys=ON"))
        raise


def main():
    with app.app_context():
        dialect = db.engine.dialect.name

        try:
            if dialect == "postgresql":
                migrate_postgresql()
            elif dialect == "sqlite":
                migrate_sqlite()
            else:
                raise RuntimeError(f"Unsupported database dialect: {dialect}")

            db.session.commit()
            print(f"✅ m1-m12 unified to {TARGET_DECIMAL_TYPE} on {dialect}")
        except Exception as exc:
            db.session.rollback()
            print(f"❌ Migration failed on {dialect}: {exc}")
            raise


if __name__ == "__main__":
    main()
