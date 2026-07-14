import os
import re
import tempfile
import unittest
from datetime import date, timedelta

from app import create_app
from extensions import db
from models import Pipeline, User


class PipelineFollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, 'test_bitcrm.db')

        class TestConfig:
            TESTING = True
            SECRET_KEY = 'test-secret'
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SQLALCHEMY_ENGINE_OPTIONS = {}
            CACHE_TYPE = 'SimpleCache'
            UPLOAD_FOLDER = os.path.join(self.temp_dir.name, 'uploads')
            EXCEL_TEMPLATES_FOLDER = os.path.join(self.temp_dir.name, 'templates')

        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()

        admin = User(username='Admin', role='admin')
        admin.set_password('bitcrm')
        db.session.add(admin)
        db.session.commit()

        self.admin_id = admin.id
        self.client = self.app.test_client()
        response = self.client.post(
            '/login',
            data={'username': 'Admin', 'password': 'bitcrm'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        self.temp_dir.cleanup()

    def test_pipeline_add_saves_initial_followup_and_stuckpoint(self):
        response = self.client.post(
            '/pipeline/add',
            data={
                'name': 'Initial Contact',
                'company': 'Followup Test Company',
                'owner_id': str(self.admin_id),
                'mrc_usd': '0',
                'otc_usd': '0',
                'contract_term_yrs': '1',
                'gp_margin': '0',
                'win_rate': '0',
                'stage': '1) Prospecting',
                'level': 'Stretch',
                'follow_up': 'Initial discovery call completed',
                'stuckpoint': 'Waiting for budget confirmation',
            },
        )

        self.assertEqual(response.status_code, 302)
        pipeline = Pipeline.query.filter_by(company='Followup Test Company').one()
        self.assertIsNotNone(pipeline.follow_up)
        self.assertRegex(
            pipeline.follow_up,
            re.compile(
                r'^Follow-up, \d{4}-\d{2}-\d{2} \d{2}:\d{2}: '
                r'Initial discovery call completed$'
            ),
        )
        self.assertEqual(pipeline.stuckpoint, 'Waiting for budget confirmation')
        self.assertEqual(pipeline.get_followup_display(), 'Today')

    def test_no_followup_displays_inclusive_days_since_pipeline_creation(self):
        expectations = [
            (date.today(), 'No follow-up · Day 1', 'bg-success'),
            (date.today() - timedelta(days=10), 'No follow-up · Day 11', 'bg-warning'),
            (date.today() - timedelta(days=30), 'No follow-up · Day 31', 'bg-danger'),
        ]

        for date_added, display, color in expectations:
            with self.subTest(date_added=date_added):
                pipeline = Pipeline(
                    name='No Follow-up',
                    owner_id=self.admin_id,
                    date_added=date_added,
                )
                self.assertEqual(pipeline.get_followup_display(), display)
                self.assertEqual(pipeline.get_followup_color_class(), color)


if __name__ == '__main__':
    unittest.main()
