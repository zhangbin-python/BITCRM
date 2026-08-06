import os
import tempfile
import unittest
from datetime import date

from app import create_app
from extensions import db
from models import Pipeline, SalesLead, Task, User


class ReadOnlyPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.temp_dir.name, 'readonly.db')

        class TestConfig:
            TESTING = True
            SECRET_KEY = 'readonly-test-secret'
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SQLALCHEMY_ENGINE_OPTIONS = {}
            CACHE_TYPE = 'SimpleCache'
            UPLOAD_FOLDER = os.path.join(self.temp_dir.name, 'uploads')
            EXCEL_TEMPLATES_FOLDER = os.path.join(self.temp_dir.name, 'templates')

        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        owner = User(username='Owner', role='sales')
        owner.set_password('password')
        reviewer = User(username='Reviewer', role='readonly')
        reviewer.set_password('password')
        db.session.add_all([owner, reviewer])
        db.session.flush()
        self.owner_id = owner.id

        db.session.add_all([
            SalesLead(
                name='Visible Contact', company='Visible Company',
                owner_id=self.owner_id, leads_status='Qualified', date_added=date.today(),
            ),
            Pipeline(
                name='Visible Opportunity', company='Visible Company',
                owner_id=self.owner_id, stage='1) Prospecting', date_added=date.today(),
            ),
            Task(
                content='Visible Task', owner_id=self.owner_id,
                due_date=date.today(), status='In Progress',
            ),
        ])
        db.session.commit()

        self.client = self.app.test_client()
        response = self.client.post(
            '/login', data={'username': 'Reviewer', 'password': 'password'},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        self.temp_dir.cleanup()

    def test_readonly_can_view_business_modules_but_not_admin_modules(self):
        paths = {
            '/dashboard': None,
            '/leads/': '/leads/?show_unqualified=true',
            '/pipeline/': None,
            '/tasks/': None,
            '/sales-activities/': None,
        }
        for path, request_path in paths.items():
            response = self.client.get(request_path or path)
            self.assertEqual(response.status_code, 200, path)
            if path == '/leads/':
                self.assertIn('Visible Company', response.get_data(as_text=True))
            elif path in ('/pipeline/', '/tasks/'):
                self.assertIn('Visible Company' if path == '/pipeline/' else 'Visible Task', response.get_data(as_text=True))

        for path in ('/admin/users', '/admin/login-logs'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertEqual(response.location, '/dashboard')

    def test_readonly_business_writes_are_forbidden_but_personal_preferences_work(self):
        write_requests = (
            ('/leads/add', {'name': 'Blocked'}),
            ('/pipeline/add', {'name': 'Blocked'}),
            ('/tasks/add', {'content': 'Blocked'}),
            ('/sales-activities/add', {'company': 'Blocked'}),
        )
        for path, data in write_requests:
            response = self.client.post(path, data=data)
            self.assertEqual(response.status_code, 403, path)

        lead = SalesLead.query.first()
        response = self.client.post(
            f'/api/leads/{lead.id}/quick-update',
            json={'field': 'name', 'value': 'Blocked'},
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            '/api/column-preferences/leads',
            json={'columns': ['company'], 'order': []},
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            '/api/dashboard/filters',
            json={'owners': [self.owner_id], 'stages': [], 'date_range': {}},
        )
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
