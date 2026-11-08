"""Cloud compatibility checked in an isolated subprocess, not the live server."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CloudHostingTests(unittest.TestCase):
    def test_vercel_mode(self):
        code = r'''
import json
import tempfile
from pathlib import Path
import app as web
import services
assert services.CLOUD_DEMO
assert services.ROOT == Path(tempfile.gettempdir()) / 'enigma-lab'
assert not (services.ROOT / '.session-secret').exists()
assert web.app.config['SESSION_COOKIE_SECURE']
c = web.app.test_client()
base = 'https://enigma-test.vercel.app'
remote = {'REMOTE_ADDR': '192.0.2.1'}
r = c.get('/', base_url=base, environ_overrides=remote)
assert r.status_code == 200, r.data
assert b'Public demonstration' in r.data
r = c.get('/college', base_url=base, environ_overrides=remote)
assert r.status_code == 200
r = c.get('/api/health', base_url=base, environ_overrides=remote)
assert r.get_json()['storage'] == 'temporary-per-instance'
assert c.get('/api/health', base_url='https://evil.example', environ_overrides=remote).status_code == 400
for task, payload in [
    ('classical', {'message':'HELLO','key':'3'}),
    ('rsa', {'message':'HELLO WORLD'}),
    ('signatures', {'message':'Fictional document'}),
]:
    r=c.post('/api/tasks/'+task+'/run', json=payload, base_url=base,
             headers={'Origin':base}, environ_overrides=remote)
    assert r.status_code == 200, r.data
    d=r.get_json()
    if task=='rsa': assert d['recovery_matches'] and d['wrong_key_rejected']
    if task=='signatures': assert d['original_verified'] and not d['altered_document_verified'] and not d['wrong_key_verified']
assert c.post('/api/tasks/classical/run', json={'key':'3'}, base_url=base,
              headers={'Origin':'https://evil.example'}, environ_overrides=remote).status_code==403
r=c.post('/api/college/login', json={'user_id':'s001'}, base_url=base,
         headers={'Origin':base}, environ_overrides=remote)
assert r.status_code==200, r.data
assert c.get_cookie('session', domain='enigma-test.vercel.app').secure
r=c.get('/api/college/grades',base_url=base,environ_overrides=remote)
assert r.status_code==200, r.data
assert len(r.get_json()['rows'])==5
print('Cloud startup, pages, exact hosts, origin protection, secure cookies, crypto and college checks passed.')
'''
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, VERCEL='1', VERCEL_URL='enigma-test.vercel.app',
                       VERCEL_PROJECT_PRODUCTION_URL='enigma-test.vercel.app',
                       ENIGMA_SECRET_KEY='fictional-test-only-not-for-deployment-0123456789',
                       TMP=folder, TEMP=folder, TMPDIR=folder)
            env.pop('VERCEL_BRANCH_URL', None)
            env.pop('ENIGMA_PUBLIC_HOST', None)
            result = subprocess.run([sys.executable, '-c', code],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
