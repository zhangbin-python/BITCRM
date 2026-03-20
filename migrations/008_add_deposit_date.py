import os
import sys

from sqlalchemy import inspect, text

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

from app import create_app
from extensions import db


def main():
    app = create_app()

    with app.app_context():
        inspector = inspect(db.engine)
        columns = {column['name'] for column in inspector.get_columns('pipeline')}

        if 'deposit_date' in columns:
            print('deposit_date already exists, skipped')
            return

        db.session.execute(text('ALTER TABLE pipeline ADD COLUMN deposit_date DATE'))
        db.session.commit()
        print('deposit_date added successfully')


if __name__ == '__main__':
    main()
