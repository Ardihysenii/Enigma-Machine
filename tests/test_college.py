"""Fictional college access demonstration; isolated temporary storage."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app as web


class CollegeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch('services.ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        web.STATES.clear()
        self.addCleanup(web.STATES.clear)
        self.client = web.app.test_client()

    def login(self, user='s001', client=None):
        response = (client or self.client).post('/api/college/login', json={'user_id': user})
        self.assertEqual(response.status_code, 200)

    def policy(self, own=True, professor=True):
        response = self.client.post('/api/college/policy', json={'rules': {
            **dict.fromkeys(__import__('college').RULES, False), 'student_own_grades_only': own, 'block_student_professor_area': professor}})
        self.assertEqual(response.status_code, 200)

    def test_pages_and_main_panel_connected(self):
        self.assertEqual(self.client.get('/college').status_code, 200)
        html = self.client.get('/').get_data(as_text=True)
        for text in ('college-policy-panel', 'policy.js', 'policy.css', 'href="/college"'):
            self.assertIn(text, html)

    def test_requires_identity(self):
        for url in ('/api/college/grades', '/api/college/professor', '/college/professor'):
            self.assertEqual(self.client.get(url).status_code, 401)

    def test_unprotected_student_can_read_all_and_professor_area(self):
        self.login()
        data = self.client.get('/api/college/grades').get_json()
        self.assertEqual(data['mode'], 'unprotected')
        self.assertEqual(len(data['rows']), 5)
        self.assertEqual(self.client.get('/api/college/grades?student_id=s002').status_code, 200)
        self.assertEqual(self.client.get('/api/college/professor').status_code, 200)
        self.assertEqual(self.client.get('/college/professor').status_code, 200)

    def test_protected_student_actual_denials(self):
        self.login()
        self.policy()
        data = self.client.get('/api/college/grades').get_json()
        self.assertEqual(len(data['rows']), 1)
        self.assertTrue(all(row['student_id'] == 's001' for row in data['rows']))
        for url in ('/api/college/grades?student_id=all', '/api/college/grades?student_id=s002',
                    '/api/college/professor', '/college/professor'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/college/grades?student_id=s001').status_code, 200)

    def test_professor_retains_access(self):
        self.policy()
        self.login('p001')
        self.assertEqual(len(self.client.get('/api/college/grades').get_json()['rows']), 5)
        self.assertEqual(self.client.get('/api/college/professor').status_code, 200)
        self.assertEqual(self.client.get('/college/professor').status_code, 200)

    def test_rules_independent_and_can_be_disabled(self):
        self.login()
        self.policy(True, False)
        response = self.client.get('/api/college/professor')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(row['student_id'] == 's001' for row in response.get_json()['rows']))
        self.policy(False, True)
        self.assertEqual(len(self.client.get('/api/college/grades').get_json()['rows']), 5)
        self.assertEqual(self.client.get('/api/college/professor').status_code, 403)
        self.policy(False, False)
        self.assertEqual(self.client.get('/api/college/professor').status_code, 200)

    def test_session_isolation_and_persistence(self):
        self.login()
        self.policy()
        other = web.app.test_client()
        self.assertEqual(other.get('/api/college/status').get_json()['mode'], 'unprotected')
        self.assertIsNone(other.get('/api/college/status').get_json()['actor'])
        web.STATES.clear()
        restored = self.client.get('/api/college/status').get_json()
        self.assertEqual(restored['mode'], 'partial')
        self.assertIsNone(restored['actor'])

    def test_audit_records_actual_denial(self):
        self.login()
        self.policy()
        self.client.get('/api/college/professor')
        events = self.client.get('/api/college/audit').get_json()['events']
        self.assertTrue(any(event['action'] == 'professor_area_denied' and not event['allowed'] for event in events))

    def test_bad_policy_and_identity_are_rejected(self):
        self.assertEqual(self.client.post('/api/college/login', json={'user_id': 'admin'}).status_code, 400)
        for rules in ({}, {'student_own_grades_only': 'true', 'block_student_professor_area': True}):
            self.assertEqual(self.client.post('/api/college/policy', json={'rules': rules}).status_code, 400)
        self.login()
        self.assertEqual(self.client.get('/api/college/grades?role=professor').status_code, 400)
        self.assertEqual(self.client.get('/api/college/grades?student_id=s001&student_id=s002').status_code, 400)

    def test_corrupt_policy_fails_closed(self):
        self.login()
        with self.client.session_transaction() as session:
            folder = self.root / session['lab']
        (folder / 'college-policy.json').write_text(json.dumps({'rules': {}}), encoding='utf-8')
        web.STATES.clear()
        self.assertEqual(self.client.get('/api/college/grades').status_code, 503)

    def test_logout_revokes_selected_identity(self):
        self.login()
        self.assertEqual(self.client.post('/api/college/logout', json={}).status_code, 200)
        self.assertEqual(self.client.get('/api/college/grades').status_code, 401)

    def set_rules(self, **enabled):
        import college
        rules = {**college.RULES, **enabled}
        response = self.client.post('/api/college/policy', json={'rules': rules})
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def edit(self, course='Siguria e informacionit', student='s001', grade=6):
        return self.client.post('/api/college/grades/update', json={
            'student_id': student, 'course': course, 'grade': grade})

    def test_student_edit_before_and_after_control(self):
        self.login()
        self.assertEqual(self.edit().status_code, 200)
        self.assertEqual(self.client.get('/api/college/grades').get_json()['rows'][0]['grade'], 6)
        self.set_rules(block_student_grade_edit=True)
        self.assertEqual(self.edit(grade=5).status_code, 403)
        self.assertEqual(self.client.get('/api/college/grades').get_json()['rows'][0]['grade'], 6)
        events = self.client.get('/api/college/audit').get_json()['events']
        self.assertTrue(any(e['action'] == 'grade_update_denied' for e in events))

    def test_own_grades_rule_also_prevents_other_student_edit(self):
        self.login()
        self.set_rules(student_own_grades_only=True)
        self.assertEqual(self.edit(student='s002').status_code, 403)
        self.assertEqual(self.edit().status_code, 200)

    def test_single_course_professor_access_and_removed_account(self):
        self.login('p001')
        self.set_rules(professor_assigned_courses_only=True)
        for url in ('/api/college/grades', '/api/college/professor'):
            rows = self.client.get(url).get_json()['rows']
            self.assertEqual(len(rows), 5)
            self.assertEqual(len({row['student_id'] for row in rows}), 5)
            self.assertTrue(all(row['course'] == 'Siguria e informacionit' for row in rows))
        self.assertEqual(self.edit(course='Programim').status_code, 400)
        self.assertEqual(self.edit().status_code, 200)
        self.assertEqual(self.client.post('/api/college/login', json={'user_id': 'p002'}).status_code, 400)
        data = self.client.get('/api/college/status').get_json()
        self.assertEqual(len(data['users']), 6)
        self.assertEqual(data['courses'], ['Siguria e informacionit'])

    def test_audit_access_before_after_and_professor(self):
        self.login()
        self.assertEqual(self.client.get('/api/college/audit').status_code, 200)
        self.set_rules(audit_professor_only=True)
        response = self.client.get('/api/college/audit')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('events', response.get_json())
        self.login('p001')
        response = self.client.get('/api/college/audit')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(e['action'] == 'audit_access_denied' for e in response.get_json()['events']))

    def test_polling_does_not_prevent_session_expiry(self):
        with patch('college.time.monotonic', return_value=1000):
            self.login()
            self.set_rules(session_inactivity_timeout=True)
        with patch('college.time.monotonic', return_value=1020):
            self.assertIsNotNone(self.client.get('/api/college/status').get_json()['actor'])
            self.client.get('/api/college/policy')
        with patch('college.time.monotonic', return_value=1031):
            data = self.client.get('/api/college/status').get_json()
            self.assertIsNone(data['actor'])
            self.assertTrue(data['session_expired'])
            self.assertEqual(self.edit().status_code, 401)
            self.assertEqual(self.client.get('/api/college/grades').status_code, 401)
            self.login()
            self.assertEqual(self.client.get('/api/college/grades').status_code, 200)

    def test_explicit_activity_renews_session(self):
        with patch('college.time.monotonic', return_value=1000):
            self.login()
            self.set_rules(session_inactivity_timeout=True)
        with patch('college.time.monotonic', return_value=1020):
            self.assertEqual(self.client.get('/api/college/grades').status_code, 200)
        with patch('college.time.monotonic', return_value=1040):
            self.assertIsNotNone(self.client.get('/api/college/status').get_json()['actor'])
        with patch('college.time.monotonic', return_value=1051):
            self.assertIsNone(self.client.get('/api/college/status').get_json()['actor'])

    def test_all_six_rules_and_grade_validation(self):
        import college
        data = self.set_rules(**dict.fromkeys(college.RULES, True))
        self.assertEqual(data['mode'], 'protected')
        self.assertEqual(data['active_count'], 6)
        self.login('p001')
        for grade in (True, '8', 4, 11, 7.5):
            self.assertEqual(self.edit(grade=grade).status_code, 400)
        self.assertEqual(self.edit().status_code, 200)

    def test_legacy_policy_migrates_without_erasing_rules(self):
        self.login()
        with self.client.session_transaction() as session:
            folder = self.root / session['lab']
        (folder / 'college-policy.json').write_text(json.dumps({'rules': {
            'student_own_grades_only': True, 'block_student_professor_area': False},
            'updated_at': None}), encoding='utf-8')
        web.STATES.clear()
        rules = self.client.get('/api/college/status').get_json()['rules']
        self.assertEqual(len(rules), 6)
        self.assertTrue(rules['student_own_grades_only'])
        self.assertFalse(rules['block_student_grade_edit'])

    def test_grade_edits_are_session_isolated(self):
        self.login()
        self.assertEqual(self.edit(grade=5).status_code, 200)
        other = web.app.test_client()
        self.login(client=other)
        self.assertEqual(other.get('/api/college/grades').get_json()['rows'][0]['grade'], 9)

    def test_five_named_students_and_new_student_permissions(self):
        data = self.client.get('/api/college/status').get_json()
        students = [user for user in data['users'] if user['role'] == 'student']
        self.assertEqual([user['name'] for user in students], ['Ardi', 'Arditi', 'Donarti', 'Albi', 'Enes'])
        for identifier in ('s004', 's005'):
            self.login(identifier)
            self.assertEqual(len(self.client.get('/api/college/grades?student_id=' + identifier).get_json()['rows']), 1)
            self.assertEqual(self.edit(student=identifier).status_code, 200)
            self.set_rules(student_own_grades_only=True, block_student_grade_edit=True)
            rows = self.client.get('/api/college/grades').get_json()['rows']
            self.assertTrue(all(row['student_id'] == identifier for row in rows))
            self.assertEqual(self.client.get('/api/college/grades?student_id=s001').status_code, 403)
            self.assertEqual(self.edit(student=identifier).status_code, 403)
            self.set_rules()


if __name__ == '__main__':
    unittest.main()
