import os
import tempfile
import unittest

from app import create_app
from extensions import db
from models import User


class AdminUsersTooltipTests(unittest.TestCase):
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

        User.query.delete()
        db.session.commit()

        admin = User(username='Admin', email='admin@test.local', role='admin')
        admin.set_password('bitcrm')
        sales = User(username='Sales', email='sales@test.local', role='sales')
        sales.set_password('bitcrm')
        db.session.add_all([admin, sales])
        db.session.commit()

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

    def test_admin_user_actions_have_hover_tooltips(self):
        response = self.client.get('/admin/users')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('data-bs-toggle="tooltip"', html)
        for label in ('Edit User', 'Deactivate User', 'Reset Password'):
            self.assertIn(f'title="{label}"', html)
            self.assertIn(f'aria-label="{label}"', html)


if __name__ == '__main__':
    unittest.main()
