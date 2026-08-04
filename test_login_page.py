import os
import tempfile
import unittest

from app import create_app
from extensions import db


class LoginPageTests(unittest.TestCase):
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
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()
        self.temp_dir.cleanup()

    def test_login_page_has_responsive_branded_layout_in_both_languages(self):
        english = self.client.get('/set-language/en?next=/login', follow_redirects=True)
        self.assertEqual(english.status_code, 200)
        english_html = english.get_data(as_text=True)
        self.assertIn('class="login-page"', english_html)
        self.assertIn('Turn every customer interaction into forward momentum.', english_html)
        self.assertIn('Welcome back', english_html)
        self.assertIn('aria-controls="password"', english_html)
        self.assertIn('id="loginSubmit"', english_html)

        chinese = self.client.get('/set-language/zh?next=/login', follow_redirects=True)
        self.assertEqual(chinese.status_code, 200)
        chinese_html = chinese.get_data(as_text=True)
        self.assertIn('让每一次客户互动，都推动业务向前。', chinese_html)
        self.assertIn('欢迎回来', chinese_html)
        self.assertIn('企业级安全访问', chinese_html)
        self.assertIn('aria-current="true">中文</a>', chinese_html)


if __name__ == '__main__':
    unittest.main()
