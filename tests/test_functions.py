"""Functional educational crypto tests; all artifacts live in temporary folders."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
import app as web
import services


class FunctionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        root_patch = patch('services.ROOT', self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        app_root_patch = patch('app.ROOT', Path(self.temp.name))
        app_root_patch.start()
        self.addCleanup(app_root_patch.stop)
        web.STATES.clear()
        self.addCleanup(web.STATES.clear)
        self.client = web.app.test_client()

    def run_task(self, task, payload, status=200, client=None):
        response = (client or self.client).post('/api/tasks/' + task + '/run', json=payload)
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        data = response.get_json()
        if status == 200:
            self.assertEqual(data['status'], 'ok')
            self.assertEqual(data['task'], task)
        return data

    def state(self):
        with self.client.session_transaction() as session:
            return web.STATES[session['lab']]

    def enroll(self):
        return self.run_task('authentication', {'action': 'enroll', 'identity': 'Fictional Alice', 'pin': '5831'})

    def challenge(self):
        return self.run_task('authentication', {'action': 'challenge'})

    def authenticate(self, **overrides):
        payload = {'action': 'authenticate', 'identity': 'Fictional Alice', 'pin': '5831'}
        payload.update(overrides)
        return self.run_task('authentication', payload)

    def analysis_payload(self):
        return {'assets': 'Fictional records', 'roles': 'Clerk; auditor',
                'threats': 'Theft: encryption\nTamper: signatures\nOutage: backup',
                'confidentiality': 'Restrict access', 'integrity': 'Verify signatures',
                'availability': 'Restore backups', 'audit_evidence': 'Access events'}

    def test_caesar_known_vector_and_recovery(self):
        encrypted = self.run_task('classical', {'message': 'Attack at dawn!', 'key': '3'})
        self.assertEqual(encrypted['output'], 'DWWDFN DW GDZQ!')
        self.assertEqual(len(encrypted['steps']), 12)
        self.assertEqual(encrypted['steps'][0]['value'], 0)
        recovered = self.run_task('classical', {'message': encrypted['output'], 'key': '3', 'operation': 'decrypt'})
        self.assertEqual(recovered['output'], 'ATTACK AT DAWN!')

    def test_caesar_modulo_negative_and_non_ascii_policy(self):
        for key, expected in [('29', 'DEF'), ('-1', 'ZAB'), ('26', 'ABC')]:
            with self.subTest(key=key):
                self.assertEqual(self.run_task('classical', {'message': 'abc', 'key': key})['output'], expected)
        self.assertEqual(self.run_task('classical', {'message': 'aéß🙂 z!', 'key': '1'})['output'], 'Béß🙂 A!')

    def test_vigenere_known_vector_and_recovery(self):
        payload = {'cipher': 'vigenere', 'key': 'LEMON', 'message': 'Attack at dawn!'}
        encrypted = self.run_task('classical', payload)
        self.assertEqual(encrypted['output'], 'LXFOPV EF RNHR!')
        payload.update(message=encrypted['output'], operation='decrypt')
        self.assertEqual(self.run_task('classical', payload)['output'], 'ATTACK AT DAWN!')

    def test_vigenere_nonletters_do_not_advance_key(self):
        data = self.run_task('classical', {'cipher': 'vigenere', 'key': 'BC', 'message': 'a-🙂éa a'})
        self.assertEqual(data['output'], 'B-🙂éC B')

    def test_classical_validation(self):
        for payload in [{'key': ''}, {'key': 'x'}, {'key': '12345678901'}, {'key': 3},
                        {'key': '3', 'operation': 'break'}, {'key': '3', 'cipher': 'unknown'},
                        {'cipher': 'vigenere', 'key': ''}, {'cipher': 'vigenere', 'key': 'AB1'},
                        {'cipher': 'vigenere', 'key': 'é'}]:
            with self.subTest(payload=payload):
                self.run_task('classical', payload, 400)

    def test_rsa_utf8_roundtrip_and_ciphertext_size(self):
        message = 'Fictional café 🙂'
        data = self.run_task('rsa', {'message': message})
        self.assertEqual(data['recovered'], message)
        self.assertTrue(data['recovery_matches'])
        self.assertTrue(data['wrong_key_rejected'])
        self.assertEqual(len(base64.b64decode(data['ciphertext_base64'], validate=True)), 256)
        self.assertEqual(data['max_message_bytes'], 190)
        self.assertNotIn('PRIVATE KEY', json.dumps(data))

    def test_rsa_byte_boundary(self):
        for message in ['a' * 190, 'é' * 95, '🙂' * 47 + 'aa', '']:
            with self.subTest(bytes=len(message.encode('utf-8'))):
                self.assertEqual(self.run_task('rsa', {'message': message})['recovered'], message)
        for message in ['a' * 191, 'é' * 96, '🙂' * 48]:
            with self.subTest(bytes=len(message.encode('utf-8'))):
                self.assertIn('190 UTF-8 bytes', self.run_task('rsa', {'message': message}, 400)['error'])

    def test_rsa_runs_use_fresh_keys(self):
        a = self.run_task('rsa', {'message': 'same'})
        b = self.run_task('rsa', {'message': 'same'})
        self.assertNotEqual(a['ciphertext_base64'], b['ciphertext_base64'])
        self.assertFalse(list(self.root.rglob('*')))

    def test_signature_real_verification_and_negative_cases(self):
        private = services.keypair()
        with patch('services.keypair', side_effect=[private, services.keypair()]):
            data = self.run_task('signatures', {'message': 'Document café'})
        signature = base64.b64decode(data['signature_base64'], validate=True)
        private.public_key().verify(signature, 'Document café'.encode(), services.pss(), hashes.SHA256())
        self.assertTrue(data['original_verified'])
        self.assertFalse(data['altered_document_verified'])
        self.assertFalse(data['wrong_key_verified'])
        self.assertFalse(services.verifies(private.public_key(), signature, b'changed'))
        self.assertFalse(services.verifies(services.keypair().public_key(), signature, 'Document café'.encode()))
        self.assertEqual(data['document_sha256'], hashlib.sha256('Document café'.encode()).hexdigest())
        self.assertFalse(list(self.root.rglob('*')))

    def test_packaging_reload_password_and_download_isolation(self):
        password = 'DISPOSABLE-test-5831'
        # Exercise artifact checks independently of the non-UTF8 regression below.
        with patch('services.secrets.token_bytes', side_effect=lambda n: b'A' * n if n == 16 else os.urandom(n)):
            data = self.run_task('packaging', {'password': password})
        for field in ['pkcs8_recovered', 'pkcs12_recovered', 'wrong_password_rejected_pkcs8', 'wrong_password_rejected_pkcs12']:
            self.assertTrue(data[field], field)
        self.assertNotIn(password, json.dumps(data))
        artifacts = {}
        outsider = web.app.test_client()
        for filename, link in data['downloads'].items():
            with self.client.get(link) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn(filename, response.headers['Content-Disposition'])
                artifacts[filename] = response.data
            with outsider.get(link) as response:
                self.assertEqual(response.status_code, 404)
        self.assertIn(b'BEGIN ENCRYPTED PRIVATE KEY', artifacts['private-key.pem'])
        key = serialization.load_pem_private_key(artifacts['private-key.pem'], password.encode())
        bundle_key, bundle_cert, _ = pkcs12.load_key_and_certificates(artifacts['bundle.p12'], password.encode())
        cert = x509.load_pem_x509_certificate(artifacts['certificate.pem'])
        self.assertEqual(key.public_key().public_numbers(), bundle_key.public_key().public_numbers())
        self.assertEqual(cert.public_key().public_numbers(), key.public_key().public_numbers())
        self.assertEqual(bundle_cert.fingerprint(hashes.SHA256()).hex(), data['certificate_sha256'])
        for loader, content in [(serialization.load_pem_private_key, artifacts['private-key.pem']), (pkcs12.load_key_and_certificates, artifacts['bundle.p12'])]:
            with self.assertRaises(ValueError):
                loader(content, b'wrong-password')
        self.assertEqual(len(list(self.root.rglob('*.*'))), 3)
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(password.encode(), path.read_bytes())
        self.state()['last_seen'] -= 3601
        with self.client.get(data['downloads']['private-key.pem']) as response:
            self.assertEqual(response.status_code, 404)

    def test_packaging_non_utf8_wrong_password_probe(self):
        # Production uses random bytes here: invalid UTF8 must not turn a valid
        # packaging request into an unhandled 500 response.
        with patch('services.secrets.token_bytes', return_value=b'\xff' * 16):
            data = self.run_task('packaging', {'password': 'DISPOSABLE-test-5831'})
        self.assertTrue(data['wrong_password_rejected_pkcs8'])
        self.assertTrue(data['wrong_password_rejected_pkcs12'])

    def test_packaging_password_validation(self):
        for password in ['', 'short', 'x' * 129, 123]:
            with self.subTest(password_type=type(password).__name__):
                self.run_task('packaging', {'password': password}, 400)
        self.assertFalse(list(self.root.rglob('*')))

    def test_analysis_save_load_and_session_isolation(self):
        payload = self.analysis_payload()
        saved = self.run_task('analysis', payload)
        self.assertTrue(saved['saved'])
        self.assertIn('saved_at', saved['analysis'])
        self.assertEqual(self.run_task('analysis', {'action': 'load'})['analysis'], saved['analysis'])
        path = self.root / self.state()['id'] / 'analysis.json'
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), saved['analysis'])
        self.run_task('analysis', {'action': 'load'}, 400, client=web.app.test_client())
        payload['assets'] = 'Updated fictional records'
        self.assertEqual(self.run_task('analysis', payload)['analysis']['assets'], payload['assets'])
        self.assertFalse(list(self.root.rglob('*.tmp')))

    def test_restart_restores_analysis_audit_not_token_or_downloads(self):
        saved = self.run_task('analysis', self.analysis_payload())['analysis']
        self.enroll()
        self.challenge()
        old_id = self.state()['id']
        old_audit = list(self.state()['audit'])
        # A fake download capability is sufficient to verify restart invalidation.
        artifact = self.root / old_id / 'fake-artifact.pem'
        artifact.write_bytes(b'fictional encrypted artifact')
        self.state()['downloads']['old-download-token'] = (artifact, 'fake-artifact.pem')
        web.STATES.clear()
        self.assertEqual(self.run_task('analysis', {'action': 'load'})['analysis'], saved)
        self.assertEqual(self.state()['id'], old_id)
        self.assertEqual(self.run_task('authentication', {'action': 'audit'})['audit'], old_audit)
        self.assertNotIn('token', self.state())
        self.assertNotIn('challenge', self.state())
        self.assertEqual(self.state()['downloads'], {})
        self.run_task('authentication', {'action': 'challenge'}, 400)
        self.run_task('authentication', {'action': 'authenticate', 'identity': 'Fictional Alice', 'pin': '5831'}, 400)
        with self.client.get('/api/download/old-download-token') as response:
            self.assertEqual(response.status_code, 404)
        self.run_task('analysis', {'action': 'load'}, 400, client=web.app.test_client())

    def test_classical_roundtrip_metadata(self):
        for cipher, key, message, encrypted in [('caesar', '3', 'Hello!', 'KHOOR!'), ('vigenere', 'LEMON', 'Attack at dawn!', 'LXFOPV EF RNHR!')]:
            with self.subTest(cipher=cipher):
                data = self.run_task('classical', {'cipher': cipher, 'key': key, 'message': message})
                self.assertTrue(data['recovery_matches'])
                self.assertEqual(data['round_trip'], message.upper())
                self.assertEqual(data['plaintext'], message.upper())
                self.assertEqual(data['ciphertext'], encrypted)
                data = self.run_task('classical', {'cipher': cipher, 'key': key, 'message': encrypted, 'operation': 'decrypt'})
                self.assertTrue(data['recovery_matches'])
                self.assertEqual(data['round_trip'], encrypted)
                self.assertEqual(data['plaintext'], message.upper())
                self.assertEqual(data['ciphertext'], encrypted)

    def test_analysis_validation(self):
        self.run_task('analysis', {'action': 'load'}, 400)
        for overrides in [{'action': 'delete'}, {'assets': '  '}, {'roles': 3}, {'threats': 'one\ntwo'}, {'threats': 'one\n\n   \ntwo'}, {'audit_evidence': 'x' * 2001}]:
            with self.subTest(overrides=overrides):
                payload = self.analysis_payload()
                payload.update(overrides)
                self.run_task('analysis', payload, 400)
        self.assertFalse(list(self.root.rglob('*')))

    def test_authentication_requires_enrollment_and_valid_pin(self):
        self.run_task('authentication', {'action': 'challenge'}, 400)
        for identity, pin in [('', '1234'), ('Fictional', '123'), ('Fictional', '1234567890123'), ('Fictional', '１２３４'), ('Fictional', 'abcd')]:
            with self.subTest(identity=identity, pin=pin):
                self.run_task('authentication', {'action': 'enroll', 'identity': identity, 'pin': pin}, 400)
        self.assertTrue(self.enroll()['enrolled'])
        self.run_task('authentication', {'action': 'enroll', 'identity': 'Other', 'pin': '1234'}, 400)
        self.assertNotEqual(self.state()['token']['pin_hash'], '5831')

    def test_authentication_success_and_challenge_reuse(self):
        self.enroll()
        challenge = self.challenge()
        self.assertEqual(len(base64.b64decode(challenge['challenge_base64'])), 32)
        self.assertEqual(challenge['expires_in_seconds'], 60)
        data = self.authenticate()
        self.assertTrue(data['authenticated'])
        self.assertTrue(data['signature_verified'])
        self.assertFalse(self.authenticate()['authenticated'])
        self.assertEqual(self.state()['audit'][-1]['event'], 'challenge_missing_or_expired')

    def test_authentication_wrong_pin_identity_and_consumed_challenge(self):
        self.enroll()
        for overrides in [{'pin': '0000'}, {'identity': 'Other fictional identity'}]:
            with self.subTest(overrides=overrides):
                self.challenge()
                self.assertFalse(self.authenticate(**overrides)['authenticated'])
                self.assertFalse(self.authenticate()['authenticated'])
        self.assertEqual(self.state()['token']['failures'], 2)
        self.challenge()
        self.assertTrue(self.authenticate()['authenticated'])
        self.assertEqual(self.state()['token']['failures'], 0)

    def test_authentication_expiry_and_challenge_replacement(self):
        self.enroll()
        first = self.challenge()
        self.assertNotEqual(first['challenge_base64'], self.challenge()['challenge_base64'])
        self.state()['challenge']['expires'] = -1
        self.assertFalse(self.authenticate()['authenticated'])
        self.assertNotIn('challenge', self.state())

    def test_authentication_altered_and_wrong_key_rejected(self):
        self.enroll()
        for mode in ['altered', 'wrong_key']:
            with self.subTest(mode=mode):
                self.challenge()
                data = self.authenticate(test=mode)
                self.assertFalse(data['authenticated'])
                self.assertFalse(data['signature_verified'])
                self.assertEqual(data['audit'][-1]['event'], 'signature_rejected')
        self.assertEqual(self.state()['token']['failures'], 2)

    def test_authentication_lockout_after_five_failures(self):
        self.enroll()
        for _ in range(5):
            self.challenge()
            self.assertFalse(self.authenticate(pin='0000')['authenticated'])
        self.challenge()
        data = self.authenticate()
        self.assertFalse(data['authenticated'])
        self.assertIn('locked', data['reason'])
        self.assertEqual(data['audit'][-1]['event'], 'token_locked')
        self.assertEqual(self.state()['token']['failures'], 5)

    def test_authentication_audit_persistence_isolation_and_no_credentials(self):
        enrolled = self.enroll()
        self.challenge()
        verified = self.authenticate()
        data = self.run_task('authentication', {'action': 'audit'})
        self.assertEqual([event['event'] for event in data['audit']], ['token_enrolled', 'challenge_issued', 'challenge_verified'])
        self.assertTrue(all(event['success'] for event in data['audit']))
        self.assertTrue(all('timestamp' in event for event in data['audit']))
        path = self.root / self.state()['id'] / 'audit.json'
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), data['audit'])
        serialized = json.dumps([enrolled, verified, data]) + path.read_text(encoding='utf-8')
        for secret in ['5831', 'Fictional Alice', self.state()['token']['pin_hash'], 'PRIVATE KEY']:
            self.assertNotIn(secret, serialized)
        other = web.app.test_client()
        self.assertEqual(self.run_task('authentication', {'action': 'audit'}, client=other)['audit'], [])
        self.run_task('authentication', {'action': 'challenge'}, 400, client=other)

    def test_authentication_validation_and_audit_limit(self):
        self.enroll()
        self.run_task('authentication', {'action': 'bogus'}, 400)
        self.challenge()
        self.run_task('authentication', {'action': 'authenticate', 'identity': 'Fictional Alice', 'pin': '5831', 'test': 'bogus'}, 400)
        self.assertFalse(self.authenticate()['authenticated'])
        for index in range(105):
            services.audit(self.state(), 'test_event_' + str(index), True)
        self.assertEqual(len(self.state()['audit']), 100)
        self.assertEqual(self.state()['audit'][-1]['event'], 'test_event_104')
        self.assertEqual(len(json.loads((self.root / self.state()['id'] / 'audit.json').read_text())), 100)


if __name__ == '__main__':
    unittest.main()

