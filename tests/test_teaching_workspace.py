"""Teacher workspace contracts, using only a mocked database (no live data)."""
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
import portal
from portal_policy import RULE_IDS


TEACHER = '00000000-0000-0000-0000-000000000001'
STUDENT = '00000000-0000-0000-0000-000000000002'
COURSE = '00000000-0000-0000-0000-000000000003'
OTHER = '00000000-0000-0000-0000-000000000004'


class TeachingWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, CLOUD_DEMO=False)
        self.app.register_blueprint(portal.portal)
        self.client = self.app.test_client()
        self.csrf = 'a' * 43
        self.client.set_cookie('enigma_portal_csrf', self.csrf)
        self.actor = dict(id=TEACHER, name='Lab Teacher', email='teacher@test.invalid', role='professor')
        self.rules = dict.fromkeys(RULE_IDS, True)
        self.assigned = True
        self.course_exists = True
        self.student_exists = True
        self.enrolled = True
        self.assignments = []
        self.calls = []
        self.connection = MagicMock()
        self.connection.execute.side_effect = self.execute
        self.audit = MagicMock()
        self.patches = [
            patch('portal.database'),
            patch('portal.current_actor', side_effect=lambda *a, **kw: self.actor),
            patch('portal.policy', side_effect=lambda c: {'rules': self.rules}),
            patch('portal.audit', self.audit),
        ]
        for item in self.patches:
            result = item.start()
            self.addCleanup(item.stop)
            if item is self.patches[0]:
                result.return_value.__enter__.return_value = self.connection

    def execute(self, query, params=()):
        self.calls.append((query, params))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        if query.startswith('SELECT 1 FROM teaching_assignments'):
            result.fetchone.return_value = {'exists': 1} if self.assigned else None
        elif query.startswith('SELECT 1 FROM courses'):
            result.fetchone.return_value = {'exists': 1} if self.course_exists else None
        elif query.startswith('SELECT id FROM users WHERE'):
            result.fetchone.return_value = {'id': STUDENT} if self.student_exists else None
        elif query.startswith('SELECT user_id FROM teaching_assignments'):
            result.fetchall.return_value = [{'user_id': user} for user in self.assignments]
        elif query.startswith('SELECT id,name,email FROM users'):
            result.fetchall.return_value = [{'id': STUDENT, 'name': 'Lab Student', 'email': 'student@test.invalid'}]
        elif 'WHERE NOT EXISTS(SELECT 1 FROM teaching_assignments' in query:
            result.fetchall.return_value = [{'id': COURSE, 'code': 'LAB101', 'title': 'Lab Course'}]
        elif query.startswith('SELECT 1 FROM enrollments'):
            result.fetchone.return_value = {'exists': 1} if self.enrolled else None
        return result

    def post(self, path, data):
        return self.client.post('/api/portal/' + path, json=data, headers={'X-CSRF-Token': self.csrf})

    def queries(self, text):
        return [(q, p) for q, p in self.calls if text in q]

    def grade(self, **changes):
        return self.post('grades', dict(studentId=STUDENT, courseId=COURSE, grade=8, **changes))

    def test_teacher_directory_contains_only_public_student_fields(self):
        response = self.client.get('/api/portal/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['teachingStudents'], [{'id': STUDENT, 'name': 'Lab Student', 'email': 'student@test.invalid'}])
        query = self.queries('SELECT id,name,email FROM users')[0][0]
        self.assertIn("role='student' AND active", query)
        self.assertEqual(response.json['unassignedCourses'][0]['id'], COURSE)

    def test_admin_has_directory_and_unassigned_courses(self):
        self.actor['role'] = 'admin'
        response = self.client.get('/api/portal/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['teachingStudents']), 1)
        self.assertEqual(len(response.json['unassignedCourses']), 1)

    def test_student_never_gets_directory_even_when_all_switches_off(self):
        self.actor.update(role='student', id=STUDENT)
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.rules = dict.fromkeys(RULE_IDS, enabled)
                self.calls.clear()
                response = self.client.get('/api/portal/dashboard')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['teachingStudents'], [])
                self.assertEqual(response.json['unassignedCourses'], [])
                self.assertFalse(self.queries('SELECT id,name,email FROM users'))
                self.assertFalse(self.queries('WHERE NOT EXISTS(SELECT 1 FROM teaching_assignments'))

    def test_existing_grade_visibility_filters_follow_switches(self):
        for role, restriction in (('student', 'student_own_grades_only'), ('professor', 'professor_assigned_courses_only')):
            self.actor['role'] = role
            for enabled in (True, False):
                with self.subTest(role=role, enabled=enabled):
                    self.rules[restriction] = enabled
                    self.calls.clear()
                    response = self.client.get('/api/portal/dashboard')
                    self.assertEqual(response.status_code, 200)
                    query, params = self.queries('FROM enrollments e JOIN users')[0]
                    self.assertEqual(bool(params), enabled)
                    self.assertEqual('WHERE e.student_id=%s' in query, enabled and role == 'student')
                    self.assertEqual('WHERE EXISTS(SELECT 1 FROM teaching_assignments' in query, enabled and role == 'professor')

    def test_enrollment_accepts_exact_student_id(self):
        response = self.post('teaching/enrollments', {'studentId': STUDENT, 'courseId': COURSE})
        self.assertEqual(response.status_code, 200, response.json)
        query, params = self.queries('SELECT id FROM users WHERE')[0]
        self.assertIn("id=%s AND role='student' AND active", query)
        self.assertEqual(params, (STUDENT,))
        self.assertEqual(self.queries('INSERT INTO enrollments')[0][1], (STUDENT, COURSE))

    def test_enrollment_preserves_legacy_email(self):
        response = self.post('teaching/enrollments', {'studentEmail': ' Student@Test.Invalid ', 'courseId': COURSE})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.queries('SELECT id FROM users WHERE')[0][1], ('student@test.invalid',))

    def test_enrollment_rejects_unassigned_teacher_even_with_switches_off(self):
        self.assigned = False
        self.rules = dict.fromkeys(RULE_IDS, False)
        response = self.post('teaching/enrollments', {'studentId': STUDENT, 'courseId': COURSE})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.queries('INSERT INTO enrollments'))

    def test_enrollment_rejects_inactive_or_nonstudent_account(self):
        self.student_exists = False
        for data in ({'studentId': STUDENT}, {'studentEmail': 'student@test.invalid'}):
            with self.subTest(data=data):
                response = self.post('teaching/enrollments', dict(data, courseId=COURSE))
                self.assertEqual(response.status_code, 400)
        self.assertFalse(self.queries('INSERT INTO enrollments'))

    def test_enrollment_rejects_missing_course(self):
        self.course_exists = False
        response = self.post('teaching/enrollments', {'studentId': STUDENT, 'courseId': COURSE})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.queries('INSERT INTO enrollments'))

    def test_enrollment_requires_one_exact_selector(self):
        for data in ({'courseId': COURSE}, {'studentId': STUDENT, 'studentEmail': 'student@test.invalid', 'courseId': COURSE},
                     {'studentId': STUDENT, 'courseId': COURSE, 'role': 'student'}, {'studentId': 'invalid', 'courseId': COURSE}):
            with self.subTest(data=data):
                self.assertEqual(self.post('teaching/enrollments', data).status_code, 400)
        self.assertFalse(self.queries('INSERT INTO enrollments'))

    def test_student_cannot_manage_teaching_even_with_switches_off(self):
        self.actor.update(role='student', id=STUDENT)
        self.rules = dict.fromkeys(RULE_IDS, False)
        for path, data in (('teaching/enrollments', {'studentId': STUDENT, 'courseId': COURSE}), ('teaching/assignments', {'courseId': COURSE})):
            with self.subTest(path=path):
                self.assertEqual(self.post(path, data).status_code, 403)
        self.assertFalse(self.queries('INSERT INTO'))

    def test_teaching_actions_always_require_csrf(self):
        for path in ('teaching/enrollments', 'teaching/assignments'):
            with self.subTest(path=path):
                self.assertEqual(self.client.post('/api/portal/' + path, json={}).status_code, 403)
        self.assertFalse(self.calls)

    def test_claim_unassigned_course_takes_shared_lock_before_checks(self):
        response = self.post('teaching/assignments', {'courseId': COURSE})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['courseId'], COURSE)
        self.assertEqual(self.calls[0][0], 'SELECT pg_advisory_xact_lock(74420301)')
        self.assertEqual(self.queries('INSERT INTO teaching_assignments')[0][1], (TEACHER, COURSE))
        self.assertFalse(self.queries('INSERT INTO courses'))

    def test_claim_own_course_is_idempotent(self):
        self.assignments = [TEACHER]
        for _ in range(2):
            self.assertEqual(self.post('teaching/assignments', {'courseId': COURSE}).status_code, 200)
        self.assertTrue(all('ON CONFLICT DO NOTHING' in q for q, _ in self.queries('INSERT INTO teaching_assignments')))

    def test_claim_rejects_another_teachers_course(self):
        for owners in ([OTHER], [TEACHER, OTHER]):
            with self.subTest(owners=owners):
                self.assignments = owners
                self.assertEqual(self.post('teaching/assignments', {'courseId': COURSE}).status_code, 403)
        self.assertFalse(self.queries('INSERT INTO teaching_assignments'))

    def test_claim_missing_course_does_not_create_course(self):
        self.course_exists = False
        self.assertEqual(self.post('teaching/assignments', {'courseId': COURSE}).status_code, 400)
        self.assertFalse(self.queries('INSERT INTO'))

    def test_claim_rejects_invalid_or_extra_fields(self):
        for data in ({}, {'courseId': 'invalid'}, {'courseId': COURSE, 'userId': OTHER}):
            with self.subTest(data=data):
                self.assertEqual(self.post('teaching/assignments', data).status_code, 400)
        self.assertFalse(self.calls)

    def test_admin_can_explicitly_claim_existing_unassigned_course(self):
        self.actor['role'] = 'admin'
        self.assertEqual(self.post('teaching/assignments', {'courseId': COURSE}).status_code, 200)
        self.assertEqual(self.queries('INSERT INTO teaching_assignments')[0][1], (TEACHER, COURSE))

    def test_admin_cannot_claim_somebody_elses_course(self):
        self.actor['role'] = 'admin'
        self.assignments = [OTHER]
        self.assertEqual(self.post('teaching/assignments', {'courseId': COURSE}).status_code, 403)
        self.assertFalse(self.queries('INSERT INTO teaching_assignments'))

    def test_grade_insert_and_update_keep_existing_upsert(self):
        for grade in (5, 10):
            with self.subTest(grade=grade):
                response = self.post('grades', {'studentId': STUDENT, 'courseId': COURSE, 'grade': grade})
                self.assertEqual(response.status_code, 200, response.json)
                query, params = self.queries('INSERT INTO grades')[-1]
                self.assertIn('ON CONFLICT(student_id,course_id) DO UPDATE SET grade=excluded.grade', query)
                self.assertEqual(params, (STUDENT, COURSE, grade, TEACHER))

    def test_grade_rejects_unassigned_teacher_with_switch_on(self):
        self.assigned = False
        self.assertEqual(self.grade().status_code, 403)
        self.assertFalse(self.queries('INSERT INTO grades'))

    def test_grade_allows_unassigned_teacher_only_when_existing_switch_off(self):
        self.assigned = False
        self.rules['professor_assigned_courses_only'] = False
        self.assertEqual(self.grade().status_code, 200)

    def test_grade_requires_existing_student_enrollment(self):
        self.enrolled = False
        self.assertEqual(self.grade().status_code, 400)
        self.assertFalse(self.queries('INSERT INTO grades'))

    def test_student_grade_edit_block_preserved(self):
        self.actor.update(role='student', id=STUDENT)
        self.assertEqual(self.grade().status_code, 403)
        self.assertFalse(self.queries('INSERT INTO grades'))

    def test_student_own_grade_scope_preserved_when_edit_enabled(self):
        self.actor.update(role='student', id=OTHER)
        self.rules['block_student_grade_edit'] = False
        self.assertEqual(self.grade().status_code, 403)
        self.rules['student_own_grades_only'] = False
        self.assertEqual(self.grade().status_code, 200)

    def test_grade_validation_preserved(self):
        for grade in (True, 4, 11, 8.5, '8', None):
            with self.subTest(grade=grade):
                self.assertEqual(self.post('grades', {'studentId': STUDENT, 'courseId': COURSE, 'grade': grade}).status_code, 400)
        self.assertFalse(self.queries('INSERT INTO grades'))


if __name__ == '__main__':
    unittest.main()
