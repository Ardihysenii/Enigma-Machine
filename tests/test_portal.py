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
            connection.execute("UPDATE sessions SET last_seen=now()-interval '31 minutes' WHERE user_id=%s",(actor['id'],))
        self.assertEqual(client.get('/api/portal/dashboard').status_code,401)
        self.assertEqual(self.post(client,'signin',{'email':actor['email'],'password':'A-long-test-password-123'}).status_code,200)
        with self.db() as connection:
            connection.execute("UPDATE sessions SET expires_at=now()-interval '1 minute' WHERE user_id=%s",(actor['id'],))
        self.assertIsNone(client.get('/api/portal/session').json['actor'])

    def test_fictional_policy_cannot_grant_portal_privileges(self):
        student,actor=self.signup('isolation')
        rules=dict.fromkeys(('student_own_grades_only','block_student_professor_area','block_student_grade_edit','professor_assigned_courses_only','session_inactivity_timeout','audit_professor_only'),False)
        self.assertEqual(student.post('/api/college/policy',json={'rules':rules}).status_code,200)
        self.assertEqual(student.get('/api/portal/administration').status_code,403)
        self.assertEqual(student.get('/api/portal/session').json['actor']['role'],'student')


if __name__=='__main__':
    unittest.main()
