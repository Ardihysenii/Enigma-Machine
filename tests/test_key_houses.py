"""Disposable lab tests; no private material or passwords printed."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import services


class KeyHousesTests(unittest.TestCase):
    def test_containers_and_house_locks(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(services, 'ROOT', Path(directory)):
            state = {'id': 'test-houses', 'downloads': {}}
            result = services.packaging({'password': 'disposable-test-only'}, state)
            self.assertTrue(result['pkcs8_recovered'])
            self.assertTrue(result['pkcs12_recovered'])
            self.assertTrue(result['wrong_password_rejected_pkcs8'])
            self.assertTrue(result['wrong_password_rejected_pkcs12'])
            self.assertEqual(len(result['house_public_keys']), 3)
            artifacts = {name: path.read_bytes() for path, name in state['downloads'].values()}
            self.assertTrue(artifacts['private-key.pem'].startswith(b'-----BEGIN ENCRYPTED PRIVATE KEY-----'))
            for fmt, artifact in [('pkcs8', artifacts['private-key.pem'].decode()),
                                  ('pkcs12', base64.b64encode(artifacts['bundle.p12']).decode())]:
                payload = dict(action='open', format=fmt, artifact=artifact,
                               password='disposable-test-only', public_key=result['house_public_keys'][0])
                opened = services.packaging(payload, state)
                self.assertTrue(opened['opened'])
                if fmt == 'pkcs12':
                    self.assertTrue(opened['certificate_matches'])
                for public in result['house_public_keys'][1:]:
                    self.assertFalse(services.packaging(dict(payload, public_key=public), state)['opened'])
                with self.assertRaisesRegex(ValueError, 'Incorrect password'):
                    services.packaging(dict(payload, password='wrong'), state)
                with self.assertRaisesRegex(ValueError, 'Incorrect password'):
                    services.packaging(dict(payload, artifact='broken'), state)
                with self.assertRaisesRegex(ValueError, 'Invalid house public key'):
                    services.packaging(dict(payload, public_key='broken'), state)
                self.assertNotIn('disposable-test-only', str(opened))


if __name__ == '__main__':
    unittest.main()
