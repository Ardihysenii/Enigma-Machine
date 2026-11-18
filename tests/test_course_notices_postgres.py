"""Opt-in ONLY: ENIGMA_NOTICE_TEST_DSN must target a disposable test database.

Never uses DATABASE_URL/ENIGMA_DATABASE_URL. Creates a random schema inside one
transaction, rolls it all back (including DDL), and never seeds production tables.
Run: python -m unittest discover -s tests -p test_course_notices_postgres.py -v
"""
import os
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from flask import Flask, Blueprint
import portal
import course_notices as notices


@unittest.skipUnless(os.environ.get('ENIGMA_NOTICE_TEST_DSN'), 'Set ENIGMA_NOTICE_TEST_DSN to an explicitly disposable PostgreSQL database.')
class DisposablePostgresTests(unittest.TestCase):
    def test_real_migration_persistence_scopes_and_retry(self):
        dsn=os.environ['ENIGMA_NOTICE_TEST_DSN']
        connection=psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5)
        self.addCleanup(connection.close)
        self.addCleanup(connection.rollback)
        schema='notice_test_'+uuid.uuid4().hex
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        connection.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
        connection.execute("SET LOCAL statement_timeout='5s'")
        connection.execute('''CREATE TABLE schema_versions(version integer PRIMARY KEY);
            INSERT INTO schema_versions VALUES(1),(2),(3);
            CREATE TABLE users(id uuid PRIMARY KEY,name varchar(100),role text,active boolean);
            CREATE TABLE courses(id uuid PRIMARY KEY,code varchar(24),title text);
            CREATE TABLE teaching_assignments(user_id uuid,course_id uuid,PRIMARY KEY(user_id,course_id));
            CREATE TABLE enrollments(student_id uuid,course_id uuid,PRIMARY KEY(student_id,course_id));
            CREATE TABLE grades(sentinel text);
            INSERT INTO grades VALUES('unchanged');''', prepare=False)
        teacher,student,course,other=[str(uuid.uuid4()) for _ in range(4)]
        connection.execute("INSERT INTO users VALUES(%s,'Lab Teacher','professor',true),(%s,'Lab Student','student',true)",(teacher,student))
        connection.execute("INSERT INTO courses VALUES(%s,'LAB101','Lab'),(%s,'LAB102','Other')",(course,other))
        connection.execute('INSERT INTO teaching_assignments VALUES(%s,%s)',(teacher,course))
        connection.execute('INSERT INTO enrollments VALUES(%s,%s)',(student,course))
        notices.ensure_notice_schema(connection); notices.ensure_notice_schema(connection)
        self.assertEqual(connection.execute('SELECT count(*) AS n FROM schema_versions WHERE version=4').fetchone()['n'],1)
        self.assertEqual(connection.execute('SELECT * FROM grades').fetchone()['sentinel'],'unchanged')
        app=Flask(__name__);app.config.update(TESTING=True,CLOUD_DEMO=False)
        bp=Blueprint('notice_pg',__name__);bp.before_request(portal.protect_mutations)
        notices.register(bp);app.register_blueprint(bp)
        client=app.test_client();csrf='a'*43;client.set_cookie('enigma_portal_csrf',csrf)
        actor=dict(id=teacher,name='Lab Teacher',email='teacher@test.invalid',role='professor')
        @contextmanager
        def database():
            yield connection
        def post(path,data):
            return client.post('/api/portal/notices'+path,json=data,headers={'X-CSRF-Token':csrf})
        content=dict(courseId=course,title='Fictional exam',requestId=str(uuid.uuid4()),
            payload=dict(version=1,document='Fictional exam at 10:00.',drawing=[[[10,20],[30,40]]]))
        with patch('portal.database',database),patch('portal.current_actor',side_effect=lambda *a,**kw:actor),patch('portal.audit'):
            first=post('',content);self.assertEqual(first.status_code,201,first.json)
            identifier=first.json['notice']['id']
            self.assertEqual(post('',content).status_code,200)
            self.assertEqual(post('',dict(content,title='Conflict')).status_code,409)
            self.assertEqual(connection.execute('SELECT count(*) AS n FROM course_notices').fetchone()['n'],1)
            actor.update(id=student,role='student')
            self.assertEqual(client.get('/api/portal/notices/'+identifier).json,first.json)
            self.assertTrue(post('/'+identifier+'/verify',{'test':'original'}).json['verified'])
            changed=dict(content['payload'],document='Temporary edit')
            self.assertFalse(post('/'+identifier+'/verify',{'test':'current','payload':changed}).json['verified'])
            self.assertFalse(post('/'+identifier+'/verify',{'test':'wrong_key'}).json['verified'])
            self.assertEqual(client.get('/api/portal/notices/'+identifier).json,first.json)
            connection.execute('DELETE FROM enrollments WHERE student_id=%s',(student,))
            self.assertEqual(client.get('/api/portal/notices/'+identifier).status_code,404)
            self.assertEqual(post('/'+identifier+'/verify',{'test':'original'}).status_code,404)
            self.assertEqual(client.get('/api/portal/notices').json['notices'],[])
            self.assertEqual(post('',content).status_code,403)
        self.assertEqual(connection.execute('SELECT * FROM grades').fetchone()['sentinel'],'unchanged')
        connection.rollback()
        self.assertIsNone(connection.execute('SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname=%s',(schema,)).fetchone())


if __name__=='__main__':
    unittest.main()
