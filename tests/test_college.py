"""Retired dashboard compatibility and Task 01 wiring contracts.

Actual ON/OFF permission tests live in test_portal.py against isolated PostgreSQL.
"""
import unittest
import app as web


class UnifiedCollegeTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_single_account_dashboard(self):
        self.assertEqual(self.client.get('/college').status_code, 200)
        for path in ('/college/demo', '/college/demo/', '/college/professor', '/college/demo/professor'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers['Location'], '/college')

    def test_old_identity_and_record_apis_are_retired(self):
        for method, path, payload in (
            ('post', '/api/college/login', {'user_id': 's001'}),
            ('post', '/api/college/policy', {'rules': {}}),
            ('post', '/api/college/grades/update', {'grade': 10}),
            ('get', '/api/college/status', None),
            ('get', '/api/college/grades', None),
            ('get', '/api/college/professor', None),
            ('get', '/api/college/audit', None),
        ):
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, json=payload) if method == 'post' else self.client.get(path)
                self.assertEqual(response.status_code, 410)
                self.assertNotIn('rows', response.json)
                self.assertNotIn('users', response.json)
                self.assertEqual(response.json['portal'], '/college')

    def test_task_one_targets_the_signed_in_portal(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('college-policy-panel', html)
        self.assertIn('Open signed-in college portal', html)
        self.assertNotIn('href="/college/demo"', html)
        self.assertNotIn('Switchable teaching demo', html)
        response = self.client.get('/static/policy.js')
        source = response.get_data(as_text=True)
        response.close()
        self.assertIn('/api/portal', source)
        self.assertIn('X-CSRF-Token', source)
        self.assertNotIn('/api/college/', source)


if __name__ == '__main__':
    unittest.main()
