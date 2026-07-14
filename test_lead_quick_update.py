import os
import tempfile
import unittest

from app import create_app
from extensions import db
from models import Pipeline, SalesLead, User


class LeadQuickUpdateTests(unittest.TestCase):
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

    def _create_lead(self, status):
        lead = SalesLead(
            name='Status Change Lead',
            owner_id=self.admin_id,
            leads_status=status,
        )
        db.session.add(lead)
        db.session.commit()
        return lead.id

    def test_non_qualified_status_change_does_not_create_pipeline(self):
        lead_id = self._create_lead('Waiting for Response')

        response = self.client.post(
            f'/api/leads/{lead_id}/quick-update',
            json={
                'field': 'leads_status',
                'value': 'Waiting to be Contacted',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        lead = db.session.get(SalesLead, lead_id)
        self.assertEqual(lead.leads_status, 'Waiting to be Contacted')
        self.assertIsNone(lead.pipeline)
        self.assertEqual(Pipeline.query.count(), 0)

    def test_qualified_status_change_creates_pipeline(self):
        lead_id = self._create_lead('Waiting to be Contacted')

        response = self.client.post(
            f'/api/leads/{lead_id}/quick-update',
            json={
                'field': 'leads_status',
                'value': 'Qualified',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['success'])
        lead = db.session.get(SalesLead, lead_id)
        self.assertEqual(lead.leads_status, 'Qualified')
        self.assertIsNotNone(lead.pipeline)
        self.assertEqual(lead.pipeline.stage, '2) Lead Qualified')
        self.assertEqual(Pipeline.query.count(), 1)


if __name__ == '__main__':
    unittest.main()
