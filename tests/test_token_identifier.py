"""Public token identifier: stable, non-secret, and scoped to authenticated actor."""
import hashlib
import unittest
from unittest.mock import MagicMock
import portal


class TokenIdentifierTests(unittest.TestCase):
    def test_no_actor_does_not_read_an_enrollment(self):
        db = MagicMock()
        self.assertIsNone(portal.public_token_id(db, None))
        db.execute.assert_not_called()

    def test_account_without_token_has_no_identifier(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        self.assertIsNone(portal.public_token_id(db, {'id': 'staff'}))

    def test_identifier_is_stable_decimal_public_key_fingerprint(self):
        db = MagicMock()
        public = 'fictional public PEM'
        db.execute.return_value.fetchone.return_value = {'public_key': public}
        actor = {'id': 'student-one'}
        first = portal.public_token_id(db, actor)
        self.assertEqual(first, str(int(hashlib.sha256(public.encode()).hexdigest(), 16)))
        self.assertTrue(first.isdecimal())
        self.assertEqual(first, portal.public_token_id(db, actor))
        self.assertEqual(db.execute.call_args.args[1], ('student-one',))
        db.execute.return_value.fetchone.return_value = {'public_key': 'different key'}
        self.assertNotEqual(first, portal.public_token_id(db, actor))
