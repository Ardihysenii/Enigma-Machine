"""Bounded notice tests; real RSA, fake DB, no external account access."""
import copy
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from flask import Flask, Blueprint
import portal
import course_notices as notices

TEACHER = '00000000-0000-0000-0000-000000000001'
STUDENT = '00000000-0000-0000-0000-000000000002'
COURSE = '00000000-0000-0000-0000-000000000003'
OTHER = '00000000-0000-0000-0000-000000000004'
RETRY = '00000000-0000-0000-0000-000000000005'


def payload():
    return dict(version=1, document='Fictional exam: 10:00. Café.', drawing=[[[10, 20], [30, 40]]])


class NoticeCryptoTests(unittest.TestCase):
    def setUp(self):
        self.row = notices.sign_notice(dict(id=OTHER, course_id=COURSE, teacher_id=TEACHER,
            course_code='LAB101', teacher_name='Lab Teacher', title='Exam',
            published_at=datetime.now(timezone.utc), payload=payload()))

    def test_real_original_text_drawing_wrong_key_and_no_mutation(self):
        before = copy.deepcopy(self.row)
        self.assertTrue(notices.verify_notice(self.row, 'original'))
        for field, value in [('document', 'Different fictional notice'), ('drawing', [[[1,2],[3,4]]]), ('drawing', [])]:
            changed = payload(); changed[field] = value
            self.assertFalse(notices.verify_notice(self.row, 'current', changed))
        self.assertFalse(notices.verify_notice(self.row, 'wrong_key'))
        self.assertEqual(self.row, before)
        self.assertTrue(notices.verify_notice(self.row, 'original'))
        self.assertNotIn('PRIVATE KEY', str(self.row))

    def test_all_metadata_is_signed(self):
        for key, value in [('id', RETRY), ('course_id', OTHER), ('teacher_id', OTHER),
                           ('course_code', 'DIFFERENT'), ('teacher_name', 'Another Teacher'),
                           ('title', 'Different title'), ('published_at', datetime(2000,1,1,tzinfo=timezone.utc))]:
            changed = dict(self.row); changed[key] = value
            with self.subTest(key=key):
                self.assertFalse(notices.verify_notice(changed, 'original'))

    def test_normalization_and_fresh_keys(self):
        changed = payload(); changed['drawing'] = [[[10.0,20.0],[30.0,40.0]]]
        self.assertTrue(notices.verify_notice(self.row, 'current', changed))
        self.assertNotEqual(self.row['public_key'], notices.sign_notice(dict(self.row))['public_key'])


class NoticeApiTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__); app.config.update(TESTING=True, CLOUD_DEMO=False)
        bp = Blueprint('notice_test', __name__)
        bp.before_request(portal.protect_mutations)
        notices.register(bp); app.register_blueprint(bp)
        self.app = app; self.client = app.test_client()
        self.csrf = 'a' * 43; self.client.set_cookie('enigma_portal_csrf', self.csrf)
        self.actor = dict(id=TEACHER, name='Lab Teacher', email='teacher@test.invalid', role='professor')
        self.assigned = True; self.enrolled = True; self.rows = []; self.calls = []
        self.connection = MagicMock(); self.connection.execute.side_effect = self.execute
        self.audit = MagicMock()
        for item in (patch('portal.database'), patch('portal.current_actor', side_effect=lambda *a,**kw:self.actor),
                     patch('portal.audit', self.audit), patch('portal.policy', side_effect=AssertionError('Notice APIs must not consult policy'))):
            result = item.start(); self.addCleanup(item.stop)
            if item.attribute == 'database':
                result.return_value.__enter__.return_value = self.connection

    def execute(self, query, params=(), **kwargs):
        self.calls.append((query, params))
        result = MagicMock(); result.fetchone.return_value = None; result.fetchall.return_value = []
        if query.startswith('SELECT version'):
            result.fetchone.return_value = {'version': 4}
        elif query.startswith('SELECT id,name FROM users'):
            result.fetchone.return_value = dict(id=TEACHER, name='Lab Teacher')
        elif query.startswith('SELECT c.id,c.code FROM courses'):
            result.fetchone.return_value = {'id': COURSE, 'code': 'LAB101'} if self.assigned and params[1] == COURSE else None
        elif query.startswith('INSERT INTO course_notices'):
            columns = query.split('(',1)[1].split(')',1)[0].split(',')
            self.rows.append({key:(value.obj if key=='payload' else value) for key,value in zip(columns,params)})
        elif query.startswith('SELECT * FROM course_notices'):
            result.fetchone.return_value = next((row for row in self.rows if row['teacher_id']==params[0] and row['request_id']==params[1]), None)
        elif 'FROM course_notices n WHERE' in query:
            permitted = self.assigned if self.actor['role']=='professor' else self.enrolled
            rows = self.rows if permitted else []
            if 'n.id=%s' in query:
                result.fetchone.return_value = next((row for row in rows if row['id']==params[0]), None)
            else:
                if 'AND n.course_id=%s' in query:
                    rows = [row for row in rows if row['course_id']==params[1]]
                result.fetchall.return_value = rows[:100]
        elif query.startswith('SELECT c.id,c.code,c.title'):
            permitted = self.assigned if self.actor['role']=='professor' else self.enrolled
            result.fetchall.return_value = [dict(id=COURSE,code='LAB101',title='Lab Course')] if permitted else []
        return result

    def post(self, path='', data=None, csrf=True):
        return self.client.post('/api/portal/notices'+path, json=data,
            headers={'X-CSRF-Token':self.csrf} if csrf else {})

    def publish(self, **changes):
        return self.post(data=dict(dict(courseId=COURSE, title='Exam notice', payload=payload(), requestId=RETRY), **changes))

    def test_publish_detail_list_and_verify_do_not_expose_private_keys(self):
        response = self.publish(); self.assertEqual(response.status_code,201,response.json)
        notice = response.json['notice']; identifier = notice['id']
        self.assertEqual(self.client.get('/api/portal/notices/'+identifier).json['notice'], notice)
        self.assertEqual(len(self.client.get('/api/portal/notices').json['notices']), 1)
        r = self.post('/'+identifier+'/verify', {'test':'original'})
        self.assertEqual(r.status_code,200,r.json); self.assertTrue(r.json['verified']); self.assertFalse(r.json['identityTrusted'])
        self.assertNotIn('PRIVATE KEY', str(notice)); self.assertNotIn('privateKey', notice)
        self.assertTrue(any('LIMIT 100' in q for q,_ in self.calls))
        for args in self.audit.call_args_list:
            self.assertNotIn(payload()['document'], str(args))
            self.assertNotIn('drawing', str(args))

    def test_idempotent_retry_and_conflicting_request(self):
        first = self.publish(); retry = self.publish()
        self.assertEqual(retry.status_code,200,retry.json); self.assertEqual(first.json,retry.json)
        self.assertEqual(len(self.rows),1)
        self.assertEqual(self.publish(title='Different notice').status_code,409)
        self.assertEqual(self.publish(courseId=OTHER).status_code,403)
        self.assertEqual(len(self.rows),1)

    def test_student_enrolled_read_and_verify_but_not_publish(self):
        identifier = self.publish().json['notice']['id']; self.actor.update(id=STUDENT,role='student')
        self.assertEqual(self.client.get('/api/portal/notices/'+identifier).status_code,200)
        self.assertTrue(self.post('/'+identifier+'/verify',{'test':'original'}).json['verified'])
        self.assertEqual(self.publish().status_code,403)
        self.enrolled=False
        self.assertEqual(self.client.get('/api/portal/notices/'+identifier).status_code,404)
        self.assertEqual(self.post('/'+identifier+'/verify',{'test':'original'}).status_code,404)
        self.assertEqual(self.client.get('/api/portal/notices').json['notices'],[])
        self.assertEqual(self.client.get('/api/portal/notices/courses').json['courses'],[])
        self.assertTrue(any('e.student_id=%s' in q for q,_ in self.calls))

    def test_unassigned_professor_cannot_publish_read_or_verify(self):
        identifier = self.publish().json['notice']['id']; self.assigned=False
        self.assertEqual(self.publish(requestId=OTHER).status_code,403)
        self.assertEqual(self.client.get('/api/portal/notices/'+identifier).status_code,404)
        self.assertEqual(self.post('/'+identifier+'/verify',{'test':'original'}).status_code,404)
        self.assertEqual(self.client.get('/api/portal/notices').json['notices'],[])

    def test_admin_and_anonymous_denied_every_route(self):
        for actor, code in [(dict(self.actor,role='admin'),403),(None,401)]:
            self.actor=actor
            for path in ['', '/courses', '/'+OTHER]:
                self.assertEqual(self.client.get('/api/portal/notices'+path).status_code,code)
            self.assertEqual(self.publish().status_code,code)
            self.assertEqual(self.post('/'+OTHER+'/verify',{'test':'original'}).status_code,code)
        self.assertEqual(self.calls,[])

    def test_csrf_and_no_mutation_endpoints(self):
        self.assertEqual(self.post(data={},csrf=False).status_code,403)
        self.assertEqual(self.post('/'+OTHER+'/verify',{'test':'original'},csrf=False).status_code,403)
        self.assertEqual(self.client.delete('/api/portal/notices/'+OTHER).status_code,405)
        self.assertEqual(self.client.put('/api/portal/notices/'+OTHER,json={}).status_code,405)
        self.assertEqual(self.calls,[])

    def test_current_uses_only_stored_signature_and_never_changes_original(self):
        identifier = self.publish().json['notice']['id']; before=copy.deepcopy(self.rows)
        changed=payload(); changed['document']='Changed fictional notice'
        self.assertFalse(self.post('/'+identifier+'/verify',{'test':'current','payload':changed}).json['verified'])
        self.assertFalse(self.post('/'+identifier+'/verify',{'test':'wrong_key'}).json['verified'])
        self.assertTrue(self.post('/'+identifier+'/verify',{'test':'original'}).json['verified'])
        self.assertEqual(self.rows,before)
        for data in ({'test':'original','publicKey':'replacement'}, {'test':'original','payload':payload()},
                     {'test':'current'}, {'test':'wrong_key','signature':'replacement'}):
            self.assertEqual(self.post('/'+identifier+'/verify',data).status_code,400)

    def test_uuid_filter_and_validation(self):
        self.publish()
        self.assertEqual(len(self.client.get('/api/portal/notices?courseId='+COURSE).json['notices']),1)
        self.assertEqual(self.client.get('/api/portal/notices?courseId='+OTHER).json['notices'],[])
        self.assertEqual(self.client.get('/api/portal/notices?courseId=invalid').status_code,400)
        self.assertEqual(self.client.get('/api/portal/notices/invalid').status_code,400)
        for changes in ({'courseId':'bad'}, {'requestId':'bad'}, {'title':''}, {'payload':dict(payload(),drawing=[])}):
            self.assertEqual(self.publish(**changes).status_code,400)
        self.assertEqual(self.client.get('/api/portal/notices/courses').json['courses'][0]['id'],COURSE)


class NoticeMigrationTests(unittest.TestCase):
    def test_additive_marker_lock_recheck_and_no_process_cache(self):
        connection=MagicMock()
        connection.execute.return_value.fetchone.side_effect=[None,None]
        notices.ensure_notice_schema(connection)
        queries=[call.args[0] for call in connection.execute.call_args_list]
        self.assertIn('WHERE version=4',queries[0]);self.assertIn('pg_advisory_xact_lock',queries[1])
        self.assertEqual(queries[0],queries[2]); self.assertIn('CREATE TABLE IF NOT EXISTS course_notices',queries[3])
        self.assertIn('VALUES(4)',queries[4])
        for forbidden in ('ALTER TABLE','DROP ','DELETE ','UPDATE ','SET search_path','public.'):
            self.assertNotIn(forbidden,notices.NOTICE_DDL)
        connection.reset_mock();connection.execute.return_value.fetchone.side_effect=[{'version':4}]
        notices.ensure_notice_schema(connection); self.assertEqual(connection.execute.call_count,1)
        connection.reset_mock();connection.execute.return_value.fetchone.side_effect=[None,{'version':4}]
        notices.ensure_notice_schema(connection); self.assertEqual(connection.execute.call_count,3)


if __name__=='__main__':
    unittest.main()
