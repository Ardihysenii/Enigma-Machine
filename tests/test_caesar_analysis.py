"""Exhaustive search and conservative confidence tests; no external services."""
import unittest
from caesar_analysis import find_caesar_key, decrypt_shift
from services import classical
import app as application

class CaesarAnalysisTests(unittest.TestCase):
    def test_every_shift_is_tried_and_correct_key_ranks_first(self):
        messages = [
            'HELLO WORLD', 'ATTACK AT DAWN', 'THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG',
            'PLEASE MEET ME AT THE LIBRARY TOMORROW MORNING',
            'THIS IS A SECRET MESSAGE FOR THE STUDENTS IN OUR CLASS',
            'EVERY MESSAGE HAS A HIDDEN STORY',
            'INFORMATION SECURITY IS IMPORTANT FOR EVERY STUDENT',
            'THE MEETING HAS BEEN MOVED TO FRIDAY AFTERNOON',
        ]
        for plaintext in messages:
            for key in range(26):
                with self.subTest(plaintext=plaintext, key=key):
                    ciphertext = decrypt_shift(plaintext, -key)
                    result = find_caesar_key(ciphertext)
                    self.assertEqual(result['testedKeys'], 26)
                    self.assertEqual({r['key'] for r in result['candidates']}, set(range(26)))
                    self.assertEqual(result['best']['key'], key)
                    self.assertEqual(result['best']['plaintext'], plaintext)
    def test_unknown_key_does_not_require_or_use_the_entered_key(self):
        result = classical({'message':'KHOOR ZRUOG', 'cipher':'caesar', 'operation':'find_key', 'key':'nonsense'}, {})
        self.assertEqual(result['best']['key'], 3)
        self.assertEqual(result['best']['plaintext'], 'HELLO WORLD')
    def test_short_inputs_are_always_uncertain(self):
        for message in ('A', 'XYZ', 'KHOOR', 'HELLO WORLD', '123 A!?'):
            with self.subTest(message=message):
                self.assertEqual(find_caesar_key(message)['confidence'], 'uncertain')
    def test_punctuation_case_and_non_ascii_are_preserved_like_existing_cipher(self):
        original = 'Hello, world! 123\nCafé 🙂'
        encrypted = classical({'message':original, 'cipher':'caesar', 'operation':'encrypt', 'key':'5'}, {})['output']
        result = find_caesar_key(encrypted)
        candidate = next(r for r in result['candidates'] if r['key'] == 5)
        self.assertEqual(candidate['plaintext'], 'HELLO, WORLD! 123\nCAFé 🙂')
    def test_nonletters_and_invalid_inputs_are_rejected(self):
        for value in ('', '  ', '123!?🙂', 'éß', None, 7, 'A'*2001, '\ud800A'):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                find_caesar_key(value)
    def test_vigenere_search_is_not_misrepresented_as_caesar(self):
        with self.assertRaises(ValueError):
            find_caesar_key('ABC', 'vigenere')
    def test_known_key_operations_are_unchanged(self):
        for cipher, key, expected in [('caesar','3','KHOOR ZRUOG'), ('vigenere','LEMON','SIXZB HSDZQ')]:
            result = classical({'message':'HELLO WORLD','cipher':cipher,'operation':'encrypt','key':key}, {})
            self.assertEqual(result['output'], expected)
            self.assertTrue(result['recovery_matches'])
            self.assertNotIn('candidates', result)
    def test_api_returns_search_without_changing_existing_encryption(self):
        client = application.app.test_client()
        response = client.post('/api/tasks/classical/run', json={'message':'KHOOR ZRUOG','cipher':'caesar','operation':'find_key'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['best']['key'], 3)
        response = client.post('/api/tasks/classical/run', json={'message':'HELLO','cipher':'caesar','operation':'encrypt','key':'3'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['output'], 'KHOOR')
    def test_api_validates_search(self):
        client = application.app.test_client()
        for message in ('', '123', 'A'*2001):
            response = client.post('/api/tasks/classical/run', json={'message':message,'cipher':'caesar','operation':'find_key'})
            self.assertEqual(response.status_code, 400)
    def test_unspaced_text_still_lists_the_correct_result(self):
        plaintext = 'THEQUICKBROWNFOXJUMPSOVERTHELAZYDOG'
        result = find_caesar_key(decrypt_shift(plaintext, -17))
        self.assertEqual(result['best']['key'], 17)
    def test_stable_order_for_identical_requests(self):
        self.assertEqual(find_caesar_key('XYZ'), find_caesar_key('XYZ'))
    def test_large_input_is_bounded(self):
        result = find_caesar_key('KHOOR '*333)
        self.assertEqual(len(result['candidates']), 26)
        self.assertTrue(all(len(r['plaintext']) <= 2000 for r in result['candidates']))

if __name__ == '__main__':
    unittest.main()
