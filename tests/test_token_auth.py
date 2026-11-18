"""Token API contracts with a transactional-SQL fake + actual cryptography.
The fake is NOT evidence of PostgreSQL lock/concurrency semantics; use the opt-in
PostgreSQL suite for that. Never point tests at a production database.
"""
import hashlib
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from flask import jsonify
from cryptography.hazmat.primitives import serialization
from werkzeug.security import check_password_hash
import app as application
import token_auth as token


class Result:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows or []
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows


class TokenDB:
    """Deliberately rejects unknown queries so SQL contract drift is visible."""
    def __init__(self, users):
        self.users={str(u['id']):u for u in users}
        self.tokens={}
        self.challenges={}
        self.pending={}
        self.queries=[]
    def execute(self, query, params=()):
        q=' '.join(query.split());self.queries.append((q,params))
        if q.startswith('SELECT id,name,email,role FROM users WHERE id='):
            user=self.users.get(str(params[0]));return Result(user if user and ("role='student'" not in q or user['role']=='student') else None)
        if q.startswith('SELECT id,name,email,role FROM users WHERE active'):
            return Result(rows=[u for u in self.users.values() if u['role']=='student' and u['id']!=params[0]])
        if q.startswith('SELECT ticket_hash FROM token_pending'):
            row=self.pending.get(params[0]);return Result(row if row and row['id']==params[1] and row['expires_at']>datetime.now(timezone.utc) else None)
        if q.startswith('SELECT t.ticket_hash'):
            row=self.pending.get(params[0]);return Result(row if row and row['expires_at']>datetime.now(timezone.utc) else None)
        if 'FROM software_tokens WHERE user_id=' in q:
            return Result(self.tokens.get(str(params[0])))
        if q.startswith('INSERT INTO software_tokens'):
            self.tokens[str(params[0])]=dict(user_id=params[0],public_key=params[1],private_key_encrypted=params[2],pin_hash=params[3],status='active',failures=0);return Result()
        if q.startswith('DELETE FROM token_challenges WHERE user_id='):
            self.challenges={k:v for k,v in self.challenges.items() if not(v['user_id']==params[0] and v['context']==params[1])};return Result()
        if q.startswith('INSERT INTO token_challenges'):
            self.challenges[params[0]]=dict(user_id=params[1],context=params[2],nonce=params[3],expires_at=datetime.now(timezone.utc)+timedelta(seconds=60));return Result()
        if q.startswith('DELETE FROM token_challenges WHERE id='):
            row=self.challenges.get(params[0])
            if row and row['user_id']==params[1] and row['context']==params[2]:
                del self.challenges[params[0]];return Result(row)
            return Result()
        if q.startswith('UPDATE software_tokens SET failures=failures+1'):
            row=self.tokens[str(params[0])];row['failures']+=1
            if row['failures']>=5:row['status']='locked'
            return Result()
        if q.startswith('UPDATE software_tokens SET failures=0'):
            self.tokens[str(params[0])]['failures']=0;return Result()
        if q.startswith('DELETE FROM token_pending WHERE ticket_hash='):
            self.pending.pop(params[0],None);return Result()
        if q.startswith('DELETE FROM token_challenges WHERE context_hash='):
            self.challenges={k:v for k,v in self.challenges.items() if v['context']!=params[0]};return Result()
        raise AssertionError('Unhandled SQL: '+q)


def user(role='student'):
    return dict(id=str(uuid.uuid4()),name='Fictional '+role,email=role+'@test.invalid',role=role)


class TokenTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True,CLOUD_DEMO=False)
        self.actor=user();self.other=user();self.db=TokenDB([self.actor,self.other])
        self.client=application.app.test_client();self.csrf='a'*43
        self.client.set_cookie('enigma_portal_csrf',self.csrf)
        self.client.set_cookie('enigma_portal_session','s'*64)
        self.database=patch('portal.database');self.database.start().return_value.__enter__.return_value=self.db
        self.current=patch('portal.current_actor',side_effect=lambda c:self.actor);self.current.start()
        self.audit=patch('portal.audit');self.audit.start()
        self.addCleanup(patch.stopall)
    def post(self,route,body):
        return self.client.post('/api/portal/token/'+route,json=body,headers={'X-CSRF-Token':self.csrf})
    def enroll(self):
        response=self.post('enroll',{'pin':'long-test-passphrase'});self.assertEqual(response.status_code,200,response.json)
    def challenge(self,**extra):
        response=self.post('challenge',extra);self.assertEqual(response.status_code,200,response.json);return response.json['challengeId']
    def verify(self,identifier,pin='long-test-passphrase',test='normal',**extra):
        return self.post('verify',dict(pin=pin,challengeId=identifier,test=test,**extra))
    def test_rsa_and_pin_encrypted_pkcs8_no_plaintext_key(self):
        self.enroll();row=self.db.tokens[self.actor['id']]
        self.assertIn('BEGIN ENCRYPTED PRIVATE KEY',row['private_key_encrypted'])
        self.assertTrue(check_password_hash(row['pin_hash'],'long-test-passphrase'))
        self.assertNotIn('long-test-passphrase',repr(row))
        public=serialization.load_pem_public_key(row['public_key'].encode());self.assertEqual(public.key_size,2048)
        with self.assertRaises(ValueError):serialization.load_pem_private_key(row['private_key_encrypted'].encode(),password=b'wrong')
        result=self.verify(self.challenge());self.assertTrue(result.json['signature_verified']);self.assertFalse(result.json['sessionIssued'])
        self.assertNotIn('Set-Cookie',result.headers)
    def test_signature_negative_cases_consume_challenge_and_replay_rejected(self):
        self.enroll()
        for case in ('altered','wrong_key'):
            identifier=self.challenge();self.assertEqual(self.verify(identifier,test=case).status_code,401)
            self.assertEqual(self.verify(identifier).status_code,409)
        identifier=self.challenge();self.db.challenges[identifier]['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
        self.assertEqual(self.verify(identifier).status_code,409)
    def test_persistent_five_failure_lock_and_no_reenroll(self):
        self.enroll()
        for _ in range(5):self.assertEqual(self.verify(self.challenge(),pin='bad-pin').status_code,401)
        self.assertEqual(self.db.tokens[self.actor['id']]['status'],'locked')
        self.assertEqual(self.post('challenge',{}).status_code,409)
        self.assertEqual(self.post('enroll',{'pin':'new-passphrase'}).status_code,409)
    def test_student_and_professor_cannot_select_other_accounts(self):
        for role in ('student','professor'):
            self.actor['role']=role
            self.assertEqual(self.post('enroll',{'pin':'test-pin','userId':self.other['id']}).status_code,403)
            self.assertEqual(self.post('challenge',{'userId':self.other['id']}).status_code,403)
            data=self.client.get('/api/portal/token/status').json
            self.assertEqual(len(data['users']),1);self.assertFalse(data['canManage'])
    def test_admin_lists_and_enrolls_student_without_impersonation(self):
        self.actor['role']='admin'
        data=self.client.get('/api/portal/token/status').json;self.assertEqual(len(data['users']),2)
        self.assertEqual(self.post('enroll',{'pin':'other-passphrase','userId':self.other['id']}).status_code,200)
        response=self.verify(self.challenge(userId=self.other['id']),pin='other-passphrase',userId=self.other['id'])
        self.assertTrue(response.json['authenticated']);self.assertFalse(response.json['sessionIssued']);self.assertNotIn('Set-Cookie',response.headers)
    def test_challenges_bound_to_session(self):
        self.enroll();identifier=self.challenge();self.client.set_cookie('enigma_portal_session','z'*64)
        self.assertEqual(self.verify(identifier).status_code,409)
        self.client.set_cookie('enigma_portal_session','s'*64);self.assertEqual(self.verify(identifier).status_code,200)
    def test_pending_bound_to_user_and_only_verified_pending_issues_session(self):
        ticket='t'*64;ticket_hash=token.digest(ticket);self.client.set_cookie('enigma_portal_pending',ticket)
        self.db.pending[ticket_hash]=dict(self.actor,ticket_hash=ticket_hash,expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
        self.assertEqual(self.post('enroll',{'pin':'test-pin','userId':self.other['id']}).status_code,403)
        self.enroll();identifier=self.challenge()
        with patch('portal.auth_response',side_effect=lambda c,a:jsonify(actor=a)) as issue:
            self.assertEqual(self.verify(identifier,pin='wrong-pin').status_code,401);issue.assert_not_called()
            response=self.verify(self.challenge());self.assertEqual(response.json['actor']['id'],self.actor['id']);issue.assert_called_once()
        self.assertNotIn(ticket_hash,self.db.pending)
    def test_csrf_and_unknown_fields_are_rejected(self):
        self.assertEqual(self.client.post('/api/portal/token/enroll',json={'pin':'test'}).status_code,403)
        self.assertEqual(self.post('enroll',{'pin':'test','identity':'arbitrary'}).status_code,400)
    def test_missing_session_or_expired_pending_cannot_enroll(self):
        self.current.stop()
        with patch('portal.current_actor',return_value=None):
            self.assertEqual(self.post('enroll',{'pin':'test'}).status_code,401)
            ticket='t'*64;self.client.set_cookie('enigma_portal_pending',ticket)
            self.db.pending[token.digest(ticket)]=dict(self.actor,ticket_hash=token.digest(ticket),expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
            self.assertEqual(self.post('enroll',{'pin':'test'}).status_code,401)
    def test_atomic_sql_uses_locks_and_single_delete_returning(self):
        self.enroll();self.verify(self.challenge())
        queries=[q for q,_ in self.db.queries]
        self.assertTrue(any('FROM users' in q and 'FOR UPDATE' in q for q in queries))
        self.assertTrue(any(q.startswith('DELETE FROM token_challenges WHERE id=') and 'RETURNING' in q for q in queries))
        self.assertTrue(any('FROM software_tokens' in q and 'FOR UPDATE' in q for q in queries))

    def test_password_signin_routes_student_to_pending_and_staff_to_existing_session(self):
        from unittest.mock import MagicMock
        from werkzeug.security import generate_password_hash
        connection=MagicMock()
        account=dict(self.actor,password_hash=generate_password_hash('account-password-123'),active=True)
        connection.execute.return_value.fetchone.return_value=account
        with patch('portal.database') as database, patch('portal.limit_row',return_value=False), patch('portal.auth_response',side_effect=lambda c,a:jsonify(actor=a)) as issue, patch('token_auth.pending_response',side_effect=lambda c,a:jsonify(pending=True,actor=None)) as pending:
            database.return_value.__enter__.return_value=connection
            for role in ('student','professor','admin'):
                account['role']=role
                response=self.client.post('/api/portal/signin',json={'email':account['email'],'password':'account-password-123'},headers={'X-CSRF-Token':self.csrf})
                self.assertEqual(response.status_code,200,response.json)
                if role=='student':
                    self.assertTrue(response.json['pending']);issue.assert_not_called();pending.assert_called_once()
                else:self.assertEqual(response.json['actor']['role'],role)
            self.assertEqual(issue.call_count,2)

    def test_pending_ticket_cookie_is_httponly_and_only_hash_is_stored(self):
        from unittest.mock import MagicMock
        connection=MagicMock();connection.execute.return_value.fetchone.return_value=None
        with application.app.test_request_context('/api/portal/signin'):
            response=token.pending_response(connection,self.actor)
        self.assertIsNone(response.json['actor']);self.assertTrue(response.json['pending'])
        cookie=next(c for c in response.headers.getlist('Set-Cookie') if c.startswith('enigma_portal_pending='))
        self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        raw=cookie.split(';')[0].split('=',1)[1]
        insert=next(call for call in connection.execute.call_args_list if call.args[0].startswith('INSERT INTO token_pending'))
        self.assertEqual(insert.args[1][0],hashlib.sha256(raw.encode()).hexdigest())
        self.assertNotIn(raw,repr(connection.execute.call_args_list))


class AutoTokenSchemaTests(unittest.TestCase):
    def test_existing_marker_skips_ddl(self):
        from unittest.mock import MagicMock
        import portal
        connection=MagicMock();connection.execute.return_value.fetchone.return_value={'version':3}
        portal.ensure_token_schema(connection)
        self.assertEqual(connection.execute.call_count,1)

    def test_missing_marker_locks_rechecks_and_only_creates_additive_tables(self):
        from unittest.mock import MagicMock
        import portal
        connection=MagicMock();connection.execute.return_value.fetchone.side_effect=[None,None]
        portal.ensure_token_schema(connection)
        queries=[c.args[0] for c in connection.execute.call_args_list]
        self.assertIn('pg_advisory_xact_lock',queries[1])
        self.assertIn('schema_versions',queries[2])
        ddl=queries[3]
        for name in ('software_tokens','token_pending','token_challenges','token_verified_sessions'):
            self.assertIn('CREATE TABLE IF NOT EXISTS '+name,ddl)
        for forbidden in ('DELETE FROM','ALTER TABLE','DROP TABLE','CREATE SCHEMA'):
            self.assertNotIn(forbidden,ddl)
        self.assertIn('INSERT INTO schema_versions',queries[4])

    def test_second_worker_sees_committed_marker_after_lock(self):
        from unittest.mock import MagicMock
        import portal
        connection=MagicMock();connection.execute.return_value.fetchone.side_effect=[None,{'version':3}]
        portal.ensure_token_schema(connection)
        self.assertEqual(connection.execute.call_count,3)
