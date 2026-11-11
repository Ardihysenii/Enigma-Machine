"""Portal checks. Integration tests use a fresh, isolated PostgreSQL schema."""
import hashlib
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import patch, MagicMock

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
    def test_signup_persists_selected_role(self):
        from flask import jsonify
        application.app.config.update(TESTING=True, CLOUD_DEMO=False)
        for role in ('student', 'professor'):
            client = application.app.test_client()
            csrf = 'a' * 43
            client.set_cookie('enigma_portal_csrf', csrf)
            connection = MagicMock()
            connection.execute.return_value.fetchone.return_value = {'id': str(uuid.uuid4())}
            with patch('portal.database') as database, patch('portal.limit_row', return_value=False), patch('portal.limit_failure'), patch('portal.audit'), patch('portal.auth_response', side_effect=lambda c,a: jsonify(actor=a)):
                database.return_value.__enter__.return_value = connection
                response = client.post('/api/portal/signup', json={'name':'Lab Account', 'email':'lab@example.test', 'password':'Disposable-password-123', 'role':role}, headers={'X-CSRF-Token':csrf})
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['actor']['role'], role)
            inserts = [c for c in connection.execute.call_args_list if 'INSERT INTO users' in c.args[0]]
            self.assertEqual(inserts[0].args[1][-1], role)

    def test_teacher_course_is_automatically_assigned(self):
        application.app.config.update(TESTING=True, CLOUD_DEMO=False)
        client = application.app.test_client()
        csrf = 'a' * 43
        client.set_cookie('enigma_portal_csrf', csrf)
        actor = {'id':str(uuid.uuid4()), 'name':'Teacher', 'email':'teacher@example.test', 'role':'professor'}
        course = str(uuid.uuid4())
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = {'id':course}
        with patch('portal.database') as database, patch('portal.current_actor', return_value=actor), patch('portal.audit'):
            database.return_value.__enter__.return_value = connection
            response = client.post('/api/portal/courses', json={'code':'SEC101', 'title':'Information Security'}, headers={'X-CSRF-Token':csrf})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['courseId'], course)
        assignments = [c for c in connection.execute.call_args_list if 'INSERT INTO teaching_assignments' in c.args[0]]
        self.assertEqual(assignments[0].args[1], (actor['id'], course))

    def test_signup_rejects_admin_and_unsupported_roles_before_database(self):
        application.app.config.update(TESTING=True, CLOUD_DEMO=False)
        client = application.app.test_client()
        csrf = 'a' * 43
        client.set_cookie('enigma_portal_csrf', csrf)
        for role in ('admin', 'teacher', '', None, [], {}):
            response = client.post('/api/portal/signup', json={'name':'Lab Account', 'email':'lab@example.test', 'password':'Disposable-password-123', 'role':role}, headers={'X-CSRF-Token':csrf})
            self.assertEqual(response.status_code, 400, response.json)

    def test_signup_form_has_student_and_teacher_but_not_admin(self):
        html = application.app.test_client().get('/college').get_data(as_text=True)
        form = html.split('<form id="signup-form">', 1)[1].split('</form>', 1)[0]
        self.assertIn('value="student"', form)
        self.assertIn('value="professor"', form)
        self.assertNotIn('value="admin"', form)
        self.assertIn('id="teacher-enrollment-form"', html)

    def test_teacher_actions_always_require_csrf(self):
        client = application.app.test_client()
        for route in ('courses', 'teaching/enrollments'):
            self.assertEqual(client.post('/api/portal/'+route, json={}).status_code, 403)

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

    def test_real_activity_renews_session_without_polling_or_signout_regressions(self):
        client, actor = self.signup('activity-session')
        with self.db() as connection:
            connection.execute("UPDATE sessions SET last_seen=now()-interval '10 seconds',expires_at=now()+interval '1 hour' WHERE user_id=%s", (actor['id'],))
            before = connection.execute('SELECT last_seen,expires_at FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone()
        self.assertEqual(client.get('/api/portal/dashboard?poll=1').status_code, 200)
        with self.db() as connection:
            self.assertEqual(connection.execute('SELECT last_seen,expires_at FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone(), before)
        self.assertEqual(self.post(client, 'activity', {}).status_code, 200)
        cookie = client.get_cookie('enigma_portal_session')
        self.assertIsNotNone(cookie)
        with self.db() as connection:
            after = connection.execute('SELECT last_seen,expires_at FROM sessions WHERE user_id=%s', (actor['id'],)).fetchone()
        self.assertGreater(after[0], before[0])
        self.assertGreater((after[1]-after[0]).total_seconds(), 29*24*3600)
        self.assertEqual(self.post(client, 'signout', {}).status_code, 200)
        self.assertIsNone(client.get_cookie('enigma_portal_session'))
        self.assertEqual(self.post(client, 'activity', {}).status_code, 401)

    def test_database_teacher_can_connect_existing_course_and_select_existing_students(self):
        teacher, actor = self.signup('existing-roster-teacher')
        student, account = self.signup('existing-roster-student')
        course = str(uuid.uuid4())
        with self.db() as connection:
            connection.execute("UPDATE users SET role='professor' WHERE id=%s", (actor['id'],))
            connection.execute('INSERT INTO courses(id,code,title) VALUES(%s,%s,%s)', (course, 'EX'+uuid.uuid4().hex[:10], 'Existing database course'))
        dashboard = teacher.get('/api/portal/dashboard').json
        self.assertIn(account['id'], [str(u['id']) for u in dashboard['teachingStudents']])
        self.assertIn(course, [str(c['id']) for c in dashboard['unassignedCourses']])
        self.assertEqual(self.post(teacher, 'teaching/assignments', {'courseId':course}).status_code, 200)
        self.assertEqual(self.post(teacher, 'teaching/assignments', {'courseId':course}).status_code, 200)
        self.assertEqual(self.post(teacher, 'teaching/enrollments', {'studentId':account['id'], 'courseId':course}).status_code, 200)
        for grade in (7, 10):
            response = self.post(teacher, 'grades', {'studentId':account['id'], 'courseId':course, 'grade':grade})
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(student.get('/api/portal/dashboard').json['rows'][0]['grade'], grade)
        self.assertEqual(student.get('/api/portal/dashboard').json['teachingStudents'], [])
        self.assertEqual(student.get('/api/portal/dashboard').json['unassignedCourses'], [])
        self.assertEqual(self.post(student, 'teaching/assignments', {'courseId':course}).status_code, 403)

    def test_teacher_signup_course_enrollment_and_grade_workflow(self):
        self.controls(session_inactivity_timeout=False)
        teacher = application.app.test_client()
        email = 'teacher-'+uuid.uuid4().hex+'@test.invalid'
        response = self.post(teacher, 'signup', {'name':'Lab Teacher', 'email':email, 'password':'A-long-test-password-123', 'role':'professor'})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['actor']['role'], 'professor')
        self.assertEqual(teacher.get('/api/portal/administration').status_code, 403)
        student, actor = self.signup('new-enrolled')
        other, other_actor = self.signup('new-other')
        code = 'LAB'+uuid.uuid4().hex[:10]
        response = self.post(teacher, 'courses', {'code':code, 'title':'Teacher course'})
        self.assertEqual(response.status_code, 200, response.json)
        course = response.json['courseId']
        dashboard = teacher.get('/api/portal/dashboard').json
        self.assertIn(course, [str(c['id']) for c in dashboard['teachingCourses']])
        for account in (actor, other_actor):
            enrolled = self.post(teacher, 'teaching/enrollments', {'studentEmail':account['email'], 'courseId':course})
            self.assertEqual(enrolled.status_code, 200, enrolled.json)
        self.assertEqual(self.post(teacher, 'grades', {'studentId':actor['id'], 'courseId':course, 'grade':9}).status_code, 200)
        rows = student.get('/api/portal/dashboard').json['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['grade'], 9)
        self.assertEqual(str(rows[0]['studentId']), actor['id'])
        self.assertEqual(self.post(student, 'grades', {'studentId':actor['id'], 'courseId':course, 'grade':10}).status_code, 403)
        self.assertEqual(self.post(student, 'courses', {'code':'DENIED', 'title':'Denied course'}).status_code, 403)
        self.assertEqual(self.post(student, 'teaching/enrollments', {'studentEmail':other_actor['email'], 'courseId':course}).status_code, 403)
        self.controls(student_own_grades_only=False)
        self.assertEqual(len([r for r in student.get('/api/portal/dashboard').json['rows'] if str(r['courseId']) == course]), 2)
        self.controls(student_own_grades_only=True)
        self.assertEqual(len(student.get('/api/portal/dashboard').json['rows']), 1)
        unassigned = str(uuid.uuid4())
        with self.db() as connection:
            connection.execute('INSERT INTO courses(id,code,title) VALUES(%s,%s,%s)', (unassigned,'U'+uuid.uuid4().hex[:10],'Another teacher course'))
        self.assertEqual(self.post(teacher, 'teaching/enrollments', {'studentEmail':actor['email'], 'courseId':unassigned}).status_code, 403)
        self.assertEqual(self.post(teacher, 'grades', {'studentId':actor['id'], 'courseId':unassigned, 'grade':9}).status_code, 403)

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
        self.controls(session_inactivity_timeout=False)
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
