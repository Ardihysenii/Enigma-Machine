"""Portal checks. Integration tests use a fresh, isolated PostgreSQL schema."""
import hashlib
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from werkzeug.security import generate_password_hash
import app as application
from portal_policy import RULE_IDS, validate_rules
from psycopg.types.json import Jsonb


class PortalPolicyValidation(unittest.TestCase):
    def test_exact_boolean_shape(self):
        good = dict.fromkeys(RULE_IDS, True)
        self.assertEqual(validate_rules(good), good)
        for value in (None, [], {}, dict(good, extra=True), dict(good, student_own_grades_only=1),
                      dict(good, audit_professor_only='false')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_rules(value)


class PortalWithoutDatabase(unittest.TestCase):
    def test_setup_is_honest_and_mutations_require_csrf(self):
        with patch.dict(os.environ, {}, clear=True):
            application.app.config.update(TESTING=True,PORTAL_DATABASE_URL=None)
            client=application.app.test_client()
            result=client.get('/api/portal/session')
            self.assertEqual(result.status_code,200)
            self.assertFalse(result.json['configured'])
            self.assertIsNone(result.json['actor'])
            self.assertEqual(client.post('/api/portal/signup',json={}).status_code,403)


@unittest.skipUnless(os.environ.get('ENIGMA_TEST_DATABASE_URL'),'Set ENIGMA_TEST_DATABASE_URL for isolated PostgreSQL tests.')
class PortalDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn=os.environ['ENIGMA_TEST_DATABASE_URL']
        cls.schema='enigma_test_'+uuid.uuid4().hex
        migration=(Path(__file__).resolve().parents[1]/'database'/'schema.sql').read_text().replace('enigma_portal',cls.schema)
        with psycopg.connect(cls.dsn) as connection:
            connection.execute(migration,prepare=False)
        application.app.config.update(TESTING=True,CLOUD_DEMO=False,PORTAL_DATABASE_URL=cls.dsn,PORTAL_SCHEMA=cls.schema)
        cls.admin_id=str(uuid.uuid4())
        with cls.db() as connection:
            connection.execute("INSERT INTO users(id,name,email,password_hash,role) VALUES(%s,'Test Administrator','admin@test.invalid',%s,'admin')",(cls.admin_id,generate_password_hash('A-long-test-password-123')))

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(cls.dsn) as connection:
            # Only the unique schema this test class created is removed.
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        application.app.config.pop('PORTAL_DATABASE_URL',None)
        application.app.config.pop('PORTAL_SCHEMA',None)

    @classmethod
    def db(cls):
        connection=psycopg.connect(cls.dsn)
        connection.execute(sql.SQL('SET search_path TO {}, pg_catalog').format(sql.Identifier(cls.schema)))
        return connection

    def setUp(self):
        application.app.config.update(TESTING=True,CLOUD_DEMO=False,PORTAL_DATABASE_URL=self.dsn,PORTAL_SCHEMA=self.schema)
        self.client=application.app.test_client()
        # Each test starts default-on; never mutate a deployed schema.
        with self.db() as connection:
            connection.execute('UPDATE lab_policy SET rules=%s', (Jsonb(dict.fromkeys(RULE_IDS, True)),))
            connection.execute('DELETE FROM login_limits')

    def controls(self, **overrides):
        rules = self.client.get('/api/portal/policy').json['rules']
        rules.update(overrides)
        response = self.post(self.client, 'policy', {'rules': rules})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def records(self):
        student, s = self.signup('policy-student')
        other, o = self.signup('policy-other')
        professor, p = self.signup('policy-professor')
        courses = [str(uuid.uuid4()), str(uuid.uuid4())]
        with self.db() as connection:
            connection.execute("UPDATE users SET role='professor' WHERE id=%s", (p['id'],))
            for identifier in courses:
                connection.execute('INSERT INTO courses(id,code,title) VALUES(%s,%s,%s)', (identifier, 'P'+identifier[:12], 'Policy course'))
                for user in (s, o):
                    connection.execute('INSERT INTO enrollments(student_id,course_id) VALUES(%s,%s)', (user['id'], identifier))
            connection.execute('INSERT INTO teaching_assignments(user_id,course_id) VALUES(%s,%s)', (p['id'], courses[0]))
        return student, s, other, o, professor, p, courses

    def post(self,client,path,data):
        csrf=client.get('/api/portal/session').json['csrfToken']
        return client.post('/api/portal/'+path,json=data,headers={'X-CSRF-Token':csrf})

    def signup(self,label):
        client=application.app.test_client()
        email=label+'-'+uuid.uuid4().hex[:10]+'@test.invalid'
        response=self.post(client,'signup',{'name':'Test '+label,'email':email,'password':'A-long-test-password-123'})
        self.assertEqual(response.status_code,200,response.json)
        return client,response.json['actor']

    def admin(self):
        client=application.app.test_client()
        response=self.post(client,'signin',{'email':'admin@test.invalid','password':'A-long-test-password-123'})
        self.assertEqual(response.status_code,200,response.json)
        return client

    def test_signup_student_only_and_no_plaintext_tokens(self):
        client,actor=self.signup('student')
        self.assertEqual(actor['role'],'student')
        self.assertEqual(client.get('/api/portal/administration').status_code,403)
        cookie=client.get_cookie('enigma_portal_session')
        self.assertTrue(cookie.http_only)
        with self.db() as connection:
            row=connection.execute('SELECT password_hash FROM users WHERE id=%s',(actor['id'],)).fetchone()
            self.assertNotEqual(row[0],'A-long-test-password-123')
            stored=connection.execute('SELECT token_hash FROM sessions WHERE user_id=%s',(actor['id'],)).fetchone()[0]
            self.assertEqual(stored,hashlib.sha256(cookie.value.encode()).hexdigest())
            self.assertNotEqual(stored,cookie.value)
        bad=self.post(self.client,'signup',{'name':'Student','email':'injected@test.invalid','password':'A-long-test-password-123','role':'admin'})
        self.assertEqual(bad.status_code,400)

    def test_signin_signout_revokes_token_and_csrf(self):
        client,actor=self.signup('login')
        token=client.get_cookie('enigma_portal_session').value
        self.assertEqual(self.post(client,'signout',{}).status_code,200)
        self.assertIsNone(client.get('/api/portal/session').json['actor'])
        client.set_cookie('enigma_portal_session',token)
        self.assertEqual(client.get('/api/portal/dashboard').status_code,401)
        wrong=self.post(client,'signin',{'email':actor['email'],'password':'not-the-right-password'})
        self.assertEqual(wrong.status_code,401)
        valid=self.post(client,'signin',{'email':actor['email'],'password':'A-long-test-password-123'})
        self.assertEqual(valid.status_code,200,valid.json)
        self.assertNotEqual(client.get_cookie('enigma_portal_session').value,token)
        self.assertEqual(client.post('/api/portal/signout',json={},headers={'X-CSRF-Token':'wrong'}).status_code,403)

    def test_admin_roles_course_scope_and_student_records(self):
        admin=self.admin()
        student,s=self.signup('enrolled')
        other,o=self.signup('otherstudent')
        professor,p=self.signup('professor')
        self.assertEqual(self.post(admin,'roles',{'userId':p['id'],'role':'professor'}).status_code,200)
        # Changing privilege revokes existing sessions.
        self.assertEqual(professor.get('/api/portal/dashboard').status_code,401)
        self.assertEqual(self.post(professor,'signin',{'email':p['email'],'password':'A-long-test-password-123'}).status_code,200)
        ids=[]
        for title in ('Assigned','Unassigned'):
            code='T'+uuid.uuid4().hex[:10].upper()
            self.assertEqual(self.post(admin,'courses',{'code':code,'title':title+' course'}).status_code,200)
            ids.append(next(row['id'] for row in admin.get('/api/portal/administration').json['courses'] if row['code']==code))
        for course in ids:
            for user in (s,o):
                self.assertEqual(self.post(admin,'enrollments',{'studentId':user['id'],'courseId':course}).status_code,200)
        self.assertEqual(self.post(admin,'assignments',{'userId':p['id'],'courseId':ids[0]}).status_code,200)
        allowed=self.post(professor,'grades',{'studentId':s['id'],'courseId':ids[0],'grade':9})
        self.assertEqual(allowed.status_code,200,allowed.json)
        self.assertEqual(self.post(professor,'grades',{'studentId':s['id'],'courseId':ids[1],'grade':7}).status_code,403)
        self.assertEqual(self.post(student,'grades',{'studentId':s['id'],'courseId':ids[0],'grade':10}).status_code,403)
        student_rows=student.get('/api/portal/dashboard').json['rows']
        self.assertTrue(student_rows)
        self.assertTrue(all(row['studentId']==s['id'] for row in student_rows))
        prof_rows=professor.get('/api/portal/dashboard').json['rows']
        self.assertTrue(all(row['courseId']==ids[0] for row in prof_rows))
        self.assertEqual(student.get('/api/portal/audit').status_code,403)
        self.assertEqual(professor.get('/api/portal/audit').status_code,200)
        self.assertTrue(admin.get('/api/portal/audit').json['events'])
        self.assertEqual(self.post(admin,'roles',{'userId':self.admin_id,'role':'student'}).status_code,400)
        self.assertEqual(self.post(admin,'grades',{'studentId':s['id'],'courseId':ids[0],'grade':True}).status_code,400)

    def test_inactivity_absolute_expiry_and_cross_worker_persistence(self):
        client,actor=self.signup('expiry')
        token=client.get_cookie('enigma_portal_session').value
        second=application.app.test_client()
        second.set_cookie('enigma_portal_session',token)
        self.assertEqual(second.get('/api/portal/session').json['actor']['id'],actor['id'])
        with self.db() as connection:
            connection.execute("UPDATE sessions SET last_seen=now()-interval '31 seconds' WHERE user_id=%s",(actor['id'],))
        self.assertEqual(client.get('/api/portal/dashboard').status_code,401)
        self.assertEqual(self.post(client,'signin',{'email':actor['email'],'password':'A-long-test-password-123'}).status_code,200)
        with self.db() as connection:
            connection.execute("UPDATE sessions SET expires_at=now()-interval '1 minute' WHERE user_id=%s",(actor['id'],))
        self.assertIsNone(client.get('/api/portal/session').json['actor'])

    def test_lab_policy_does_not_change_account_roles(self):
        student,actor=self.signup('isolation')
        rules=dict.fromkeys(('student_own_grades_only','block_student_professor_area','block_student_grade_edit','professor_assigned_courses_only','session_inactivity_timeout','audit_professor_only'),False)
        self.assertEqual(self.post(student,'policy',{'rules':rules}).status_code,200)
        self.assertEqual(student.get('/api/portal/administration').status_code,403)
        self.assertEqual(student.get('/api/portal/session').json['actor']['role'],'student')


    def test_policy_is_global_persisted_csrf_protected_and_audited(self):
        initial = self.client.get('/api/portal/policy')
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json['rules'], dict.fromkeys(RULE_IDS, True))
        self.assertTrue(initial.json['demo'])
        self.assertEqual(initial.json['active_count'], 6)
        self.assertEqual(initial.json['total_controls'], 6)
        self.assertEqual(self.client.post('/api/portal/policy', json={'rules': initial.json['rules']}).status_code, 403)
        result = self.controls(student_own_grades_only=False)
        self.assertEqual(result['revision'], initial.json['revision']+1)
        self.assertEqual(result['active_count'], 5)
        second = application.app.test_client()
        self.assertEqual(second.get('/api/portal/policy').json, result)
        with self.db() as connection:
            row = connection.execute("SELECT actor_id,actor_name FROM audit_events WHERE action='lab_policy_changed' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNone(row[0])
            self.assertIn('Lab operator', row[1])
        for payload in ({}, {'rules': {}}, {'rules': []}, {'rules': dict(result['rules'], audit_professor_only=0)},
                        {'rules': result['rules'], 'extra': True}, []):
            with self.subTest(payload=payload):
                self.assertEqual(self.post(self.client, 'policy', payload).status_code, 400)
        csrf = self.client.get('/api/portal/session').json['csrfToken']
        self.assertEqual(self.client.post('/api/portal/policy', data='{bad', content_type='application/json', headers={'X-CSRF-Token':csrf}).status_code, 400)
        self.assertEqual(second.get('/api/portal/policy').json, result)

    def test_student_view_edit_and_professor_area_switches_are_independent(self):
        student, s, other, o, professor, p, courses = self.records()
        own = {'studentId':s['id'], 'courseId':courses[0], 'grade':8}
        foreign = dict(own, studentId=o['id'])
        self.assertEqual(student.get('/api/portal/professor').status_code, 403)
        self.assertEqual(self.post(student, 'grades', own).status_code, 403)
        self.controls(block_student_professor_area=False)
        response = student.get('/api/portal/professor')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(r['studentId']==s['id'] for r in response.json['rows']))
        self.assertFalse(response.json['capabilities']['manageGrades'])
        self.controls(block_student_grade_edit=False)
        self.assertTrue(student.get('/api/portal/dashboard').json['capabilities']['manageGrades'])
        self.assertEqual(self.post(student, 'grades', own).status_code, 200)
        self.assertEqual(self.post(student, 'grades', foreign).status_code, 403)
        self.controls(student_own_grades_only=False)
        for route in ('dashboard', 'professor'):
            rows = student.get('/api/portal/'+route).json['rows']
            self.assertIn(o['id'], [r['studentId'] for r in rows])
        self.assertEqual(self.post(student, 'grades', foreign).status_code, 200)
        # Real database grades changed, not synthetic dashboard state.
        with self.db() as connection:
            self.assertEqual(connection.execute('SELECT grade,updated_by FROM grades WHERE student_id=%s AND course_id=%s', (o['id'], courses[0])).fetchone(), (8, uuid.UUID(s['id'])))
        self.controls(block_student_grade_edit=True)
        self.assertEqual(self.post(student, 'grades', foreign).status_code, 403)
        self.controls(student_own_grades_only=True, block_student_professor_area=True)
        self.assertEqual(student.get('/api/portal/professor').status_code, 403)
        self.assertTrue(all(r['studentId']==s['id'] for r in student.get('/api/portal/dashboard').json['rows']))

    def test_professor_course_scope_and_audit_toggle(self):
        student, s, other, o, professor, p, courses = self.records()
        foreign = {'studentId':s['id'], 'courseId':courses[1], 'grade':9}
        self.assertEqual(self.post(professor, 'grades', foreign).status_code, 403)
        self.assertTrue(all(r['courseId']==courses[0] for r in professor.get('/api/portal/dashboard').json['rows']))
        self.assertEqual(student.get('/api/portal/audit').status_code, 403)
        self.controls(professor_assigned_courses_only=False, audit_professor_only=False)
        self.assertEqual(self.post(professor, 'grades', foreign).status_code, 200)
        for route in ('dashboard', 'professor'):
            result = professor.get('/api/portal/'+route).json
            self.assertIn(courses[1], [r['courseId'] for r in result['rows']])
            self.assertIn(courses[1], [r['id'] for r in result['courses']])
        self.assertTrue(student.get('/api/portal/dashboard').json['capabilities']['readAudit'])
        self.assertEqual(student.get('/api/portal/audit').status_code, 200)
        self.controls(professor_assigned_courses_only=True, audit_professor_only=True)
        self.assertEqual(self.post(professor, 'grades', foreign).status_code, 403)
        self.assertEqual(student.get('/api/portal/audit').status_code, 403)

    def test_disabled_controls_never_bypass_auth_csrf_admin_or_revocation(self):
        student, actor = self.signup('protected')
        self.controls(**dict.fromkeys(RULE_IDS, False))
        anonymous = application.app.test_client()
        for route in ('dashboard', 'professor', 'audit', 'administration'):
            self.assertEqual(anonymous.get('/api/portal/'+route).status_code, 401)
        self.assertEqual(self.post(anonymous, 'grades', {}).status_code, 401)
        self.assertEqual(student.get('/api/portal/administration').status_code, 403)
        for route in ('roles','courses','assignments','enrollments'):
            self.assertEqual(self.post(student, route, {}).status_code, 403)
        self.assertEqual(student.post('/api/portal/grades', json={}).status_code, 403)
        self.assertEqual(student.get('/api/portal/session').json['actor']['role'], 'student')
        token = student.get_cookie('enigma_portal_session').value
        self.assertEqual(self.post(student, 'signout', {}).status_code, 200)
        student.set_cookie('enigma_portal_session', token)
        self.assertEqual(student.get('/api/portal/dashboard').status_code, 401)
        self.assertEqual(self.post(student, 'signin', {'email':actor['email'], 'password':'A-long-test-password-123'}).status_code, 200)
        admin = self.admin()
        self.assertEqual(self.post(admin, 'roles', {'userId':actor['id'], 'role':'professor'}).status_code, 200)
        self.assertEqual(student.get('/api/portal/dashboard').status_code, 401)

    def test_polling_and_policy_reads_do_not_touch_activity(self):
        client, actor = self.signup('polling')
        self.controls(block_student_professor_area=False)
        with self.db() as connection:
            connection.execute("UPDATE sessions SET last_seen=now()-interval '10 seconds' WHERE user_id=%s", (actor['id'],))
            before = connection.execute('SELECT last_seen FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone()[0]
        for route in ('session','policy','dashboard?poll=1','professor?poll=1'):
            self.assertEqual(client.get('/api/portal/'+route).status_code, 200)
        with self.db() as connection:
            self.assertEqual(connection.execute('SELECT last_seen FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone()[0], before)
        self.assertEqual(client.get('/api/portal/dashboard').status_code, 200)
        with self.db() as connection:
            self.assertGreater(connection.execute('SELECT last_seen FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone()[0], before)
            connection.execute("UPDATE sessions SET last_seen=now()-interval '31 seconds' WHERE user_id=%s", (actor['id'],))
        self.assertEqual(client.get('/api/portal/dashboard?poll=1').status_code, 401)
        self.assertIsNone(client.get('/api/portal/session').json['actor'])

    def test_idle_off_keeps_old_sessions_during_login_cleanup_but_not_absolute_expiry(self):
        client, actor = self.signup('idle-off')
        self.controls(session_inactivity_timeout=False)
        with self.db() as connection:
            connection.execute("UPDATE sessions SET last_seen=now()-interval '2 hours' WHERE user_id=%s", (actor['id'],))
        # Another login must not delete an idle session while the idle rule is off.
        self.admin()
        self.assertEqual(client.get('/api/portal/session').json['actor']['id'], actor['id'])
        self.assertEqual(client.get('/api/portal/dashboard?poll=1').status_code, 200)
        with self.db() as connection:
            connection.execute("UPDATE sessions SET expires_at=now()-interval '1 second' WHERE user_id=%s", (actor['id'],))
        self.assertEqual(client.get('/api/portal/dashboard').status_code, 401)
        self.assertIsNone(client.get('/api/portal/session').json['actor'])
        self.admin()
        with self.db() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone()[0], 0)


    def test_observed_idle_expiry_permanently_revokes_cookie_before_rule_off(self):
        client, actor = self.signup('idle-revoked')
        token = client.get_cookie('enigma_portal_session').value
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db() as connection:
            connection.execute("UPDATE sessions SET last_seen=now()-interval '31 seconds' WHERE token_hash=%s", (digest,))
        self.assertIsNone(client.get('/api/portal/session').json['actor'])
        with self.db() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM sessions WHERE token_hash=%s', (digest,)).fetchone())
        self.controls(session_inactivity_timeout=False)
        # Explicitly replay the exact same cookie after weakening the idle rule.
        replay = application.app.test_client()
        replay.set_cookie('enigma_portal_session', token)
        for current in (client, replay):
            self.assertEqual(current.get('/api/portal/dashboard').status_code, 401)
            self.assertIsNone(current.get('/api/portal/session').json['actor'])

    def test_observed_absolute_expiry_permanently_revokes_cookie(self):
        client, actor = self.signup('absolute-revoked')
        token = client.get_cookie('enigma_portal_session').value
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db() as connection:
            connection.execute("UPDATE sessions SET expires_at=now()-interval '1 second' WHERE token_hash=%s", (digest,))
        self.assertEqual(client.get('/api/portal/dashboard?poll=1').status_code, 401)
        with self.db() as connection:
            self.assertIsNone(connection.execute('SELECT 1 FROM sessions WHERE token_hash=%s', (digest,)).fetchone())
        self.controls(session_inactivity_timeout=False)
        replay = application.app.test_client()
        replay.set_cookie('enigma_portal_session', token)
        self.assertEqual(replay.get('/api/portal/dashboard').status_code, 401)

    def test_fresh_session_detects_missing_policy_migration(self):
        # Only rename the table in this class's UUID-named disposable schema.
        # Always restore it, including on assertion failure.
        with self.db() as connection:
            connection.execute('ALTER TABLE lab_policy RENAME TO lab_policy_missing')
        try:
            fresh = application.app.test_client()
            self.assertIsNone(fresh.get_cookie('enigma_portal_session'))
            response = fresh.get('/api/portal/session')
            self.assertEqual(response.status_code, 503)
            self.assertFalse(response.json['configured'])
        finally:
            with self.db() as connection:
                connection.execute('ALTER TABLE lab_policy_missing RENAME TO lab_policy')
        self.assertEqual(application.app.test_client().get('/api/portal/session').status_code, 200)


if __name__=='__main__':
    unittest.main()
