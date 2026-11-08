"""Presentation layout contract and actual classical trace vectors."""
import unittest
import app as web


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_live_machine_tables_and_existing_workspaces_are_present(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for identifier in ('navigation', 'task-form', 'alphabet', 'cipher-stage',
                           'cipher-evidence', 'cipher-calculations', 'cipher-calculation-body',
                           'trace-play', 'trace-prev', 'trace-next', 'trace-speed',
                           'cipher-narration', 'presentation-toggle', 'college-policy-panel'):
            self.assertIn('id="' + identifier + '"', html)
        self.assertIn('not a simulation of the historical Enigma rotor machine', html)

    def test_presentation_assets_load_locally(self):
        for filename in ('style.css', 'cipher-presentation.css', 'cipher-presentation.js', 'app.js'):
            response = self.client.get('/static/' + filename)
            self.assertEqual(response.status_code, 200)
            response.close()
        self.assertIn("script-src 'self'", self.client.get('/').headers['Content-Security-Policy'])

    def run_cipher(self, message, key, cipher='caesar', operation='encrypt'):
        response = self.client.post('/api/tasks/classical/run', json={
            'message': message, 'key': key, 'cipher': cipher, 'operation': operation})
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_caesar_presentation_demo(self):
        data = self.run_cipher('HELLO WORLD', '3')
        self.assertEqual(data['output'], 'KHOOR ZRUOG')
        self.assertEqual(data['steps'][0], {'input': 'H', 'value': 7, 'key': 3,
                                          'calculation': '(7 + 3) mod 26 = 10', 'output': 'K'})
        self.assertEqual(len(data['steps']), 10)
        self.assertTrue(data['recovery_matches'])

    def test_vigenere_presentation_and_inverse(self):
        encrypted = self.run_cipher('ATTACK AT DAWN', 'LEMON', 'vigenere')
        self.assertEqual(encrypted['output'], 'LXFOPV EF RNHR')
        self.assertEqual([step['key'] for step in encrypted['steps']][:6], [11, 4, 12, 14, 13, 11])
        decrypted = self.run_cipher(encrypted['output'], 'LEMON', 'vigenere', 'decrypt')
        self.assertEqual(decrypted['output'], 'ATTACK AT DAWN')
        self.assertIn(' - ', decrypted['steps'][0]['calculation'])

    def test_wrap_and_preserved_characters(self):
        self.assertEqual(self.run_cipher('XYZ', '3')['output'], 'ABC')
        data = self.run_cipher('! ë 😀', '3')
        self.assertEqual(data['output'], '! ë 😀')
        self.assertEqual(data['steps'], [])
        self.assertTrue(data['recovery_matches'])


if __name__ == '__main__':
    unittest.main()
