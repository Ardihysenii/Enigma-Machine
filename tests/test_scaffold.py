"""Loopback API and infrastructure contracts for the functional laboratory."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app as web


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch('services.ROOT', Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        app_root_patch = patch('app.ROOT', Path(self.temp.name))
        app_root_patch.start()
        self.addCleanup(app_root_patch.stop)
        web.STATES.clear()
        self.addCleanup(web.STATES.clear)
        self.client = web.app.test_client()

    def test_home_and_assets(self):
        for path in ['/', '/static/app.js', '/static/style.css']:
            with self.subTest(path=path), self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)

    def test_health_reports_implemented(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'ok')
        self.assertTrue(response.get_json()['cryptography_implemented'])

    def test_six_task_contracts(self):
        data = self.client.get('/api/tasks').get_json()['tasks']
        self.assertEqual(set(data), {'analysis', 'classical', 'rsa', 'signatures', 'packaging', 'authentication'})
        self.assertTrue(all(task['implemented'] for task in data.values()))

    def test_invalid_task(self):
        self.assertEqual(self.client.post('/api/tasks/unknown/run', json={}).status_code, 404)

    def test_input_validation(self):
        url = '/api/tasks/classical/run'
        self.assertEqual(self.client.post(url, data='plain text').status_code, 415)
        for payload in [[], None, 'text', 7, {'message': 7}, {'message': 'x' * 2001}]:
            with self.subTest(payload_type=type(payload).__name__):
                response = self.client.post(url, data=json.dumps(payload), content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(url, data='{broken', content_type='application/json').status_code, 400)

    def test_unpaired_surrogate_json_rejected(self):
        # json.dumps escapes these invalid Unicode scalar values on the wire.
        for value in [chr(0xD800), chr(0xDC00), 'before' + chr(0xD800) + 'after']:
            for task, field in [('rsa', 'message'), ('signatures', 'message'), ('classical', 'message'), ('packaging', 'password'), ('authentication', 'identity'), ('analysis', 'assets')]:
                with self.subTest(task=task, codepoint=repr(value)):
                    payload = {field: value}
                    if task == 'authentication':
                        payload.update(action='enroll', pin='1234')
                    response = self.client.post('/api/tasks/' + task + '/run', data=json.dumps(payload), content_type='application/json')
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json()['status'], 'invalid_input')

    def test_request_limit(self):
        response = self.client.post('/api/tasks/classical/run', json={'message': 'x' * 40000})
        self.assertEqual(response.status_code, 413)
        self.assertIn('32 KB', response.get_json()['error'])

    def test_origin_restrictions(self):
        url = '/api/tasks/classical/run'
        payload = {'message': 'ABC', 'key': '3'}
        for headers in [{'Origin': 'https://evil.example'}, {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post(url, json=payload, headers=headers).status_code, 403)
        self.assertEqual(self.client.post(url, json=payload, headers={'Origin': 'http://localhost'}).status_code, 200)
        self.assertEqual(self.client.post(url, json=payload).status_code, 200)

    def test_non_loopback_and_untrusted_host_rejected(self):
        self.assertEqual(self.client.get('/api/health', environ_overrides={'REMOTE_ADDR': '192.0.2.1'}).status_code, 403)
        self.assertEqual(self.client.get('/api/health', headers={'Host': 'evil.example'}).status_code, 400)
        self.assertEqual(self.client.get('/api/health', environ_overrides={'REMOTE_ADDR': '::1'}).status_code, 200)

    def test_security_headers(self):
        for path in ['/', '/api/health', '/api/download/missing']:
            with self.subTest(path=path), self.client.get(path) as response:
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
                self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])


if __name__ == '__main__':
    unittest.main()
