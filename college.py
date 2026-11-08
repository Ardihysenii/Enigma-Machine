"""Local fictional college lab. Identities and policies are operator-selected, not real login."""
import json
import time
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, jsonify, render_template, request, current_app
import services

college = Blueprint('college', __name__)
COURSES = ('Siguria e informacionit',)
USERS = {
    's001': {'id': 's001', 'name': 'Ardi', 'role': 'student'},
    's002': {'id': 's002', 'name': 'Arditi', 'role': 'student'},
    's003': {'id': 's003', 'name': 'Donarti', 'role': 'student'},
    's004': {'id': 's004', 'name': 'Albi', 'role': 'student'},
    's005': {'id': 's005', 'name': 'Enes', 'role': 'student'},
    'p001': {'id': 'p001', 'name': 'Profesori', 'role': 'professor', 'courses': [COURSES[0]]},
}
STUDENT_IDS = tuple(identifier for identifier, user in USERS.items() if user['role'] == 'student')
GRADES = [
    {'student_id': student, 'student': USERS[student]['name'], 'course': COURSES[0], 'grade': grade}
    for student, grade in [('s001', 9), ('s002', 7), ('s003', 10), ('s004', 8), ('s005', 9)]
]
RULES = dict.fromkeys(('student_own_grades_only', 'block_student_professor_area',
                      'block_student_grade_edit', 'professor_assigned_courses_only',
                      'session_inactivity_timeout', 'audit_professor_only'), False)
LEGACY_RULES = {'student_own_grades_only', 'block_student_professor_area'}
TIMEOUT_SECONDS = 30


def record(lab, demo, action, allowed, target=None):
    actor = USERS.get(demo['actor_id'])
    event = {'timestamp': datetime.now(timezone.utc).isoformat(), 'action': action,
             'allowed': allowed, 'actor_id': actor['id'] if actor else None,
             'role': actor['role'] if actor else 'lab_operator', 'target': target,
             'rules': dict(demo['policy']['rules'])}
    events = (demo['audit'] + [event])[-100:]
    services.atomic_json(services.ROOT / lab['id'] / 'college-audit.json', events)
    demo['audit'] = events


def context():
    lab = current_app.extensions['enigma_lab']['state']()
    if 'college' not in lab:
        folder = services.ROOT / lab['id']
        policy_path, audit_path = folder / 'college-policy.json', folder / 'college-audit.json'
        policy = {'rules': dict(RULES), 'updated_at': None}
        events = []
        if policy_path.exists():
            policy = json.loads(policy_path.read_text(encoding='utf-8'))
            if (not isinstance(policy, dict) or not isinstance(policy.get('rules'), dict)
                    or set(policy['rules']) not in (set(RULES), LEGACY_RULES)
                    or any(type(value) is not bool for value in policy['rules'].values())):
                raise ValueError('Invalid college policy.')
            # Migrate the known two-rule format without discarding its selected rules.
            policy['rules'] = {**RULES, **policy['rules']}
        if audit_path.exists():
            events = json.loads(audit_path.read_text(encoding='utf-8'))
            if not isinstance(events, list):
                raise ValueError('Invalid college audit.')
        lab['college'] = {'policy': policy, 'audit': events[-100:], 'actor_id': None,
                          'last_activity': None, 'expired': False,
                          'grades': [dict(row) for row in GRADES], 'revision': 0}
    demo = lab['college']
    if (demo['actor_id'] and demo['policy']['rules']['session_inactivity_timeout']
            and time.monotonic() - demo['last_activity'] >= TIMEOUT_SECONDS):
        record(lab, demo, 'session_expired', False, demo['actor_id'])
        demo['actor_id'] = None
        demo['last_activity'] = None
        demo['expired'] = True
    return lab, demo


def snapshot(demo):
    rules = demo['policy']['rules']
    count = sum(rules.values())
    remaining = None
    if rules['session_inactivity_timeout'] and demo['actor_id']:
        remaining = max(0, TIMEOUT_SECONDS - (time.monotonic() - demo['last_activity']))
    return {'rules': dict(rules), 'active_count': count, 'total_controls': len(RULES),
            'mode': 'unprotected' if count == 0 else 'protected' if count == len(RULES) else 'partial',
            'updated_at': demo['policy']['updated_at'], 'actor': USERS.get(demo['actor_id']),
            'simulation': True, 'session_expired': demo['expired'],
            'timeout_seconds': TIMEOUT_SECONDS, 'expires_in': remaining,
            'revision': demo['revision']}


def payload():
    if not request.is_json:
        return None, (jsonify(error='Send a JSON object.'), 415)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify(error='Send a valid JSON object.'), 400)
    return data, None


def signed_in(lab, demo, target):
    actor = USERS.get(demo['actor_id'])
    if not actor:
        record(lab, demo, 'login_required', False, target)
    else:
        # Only explicit resource operations count as activity. Status polling does not.
        demo['last_activity'] = time.monotonic()
    return actor


def missing_identity(demo):
    return jsonify(error='Sesioni skadoi pas 30 sekondave pa veprim. Kyçu përsëri.' if demo['expired']
                   else 'Zgjedh një identitet dhe kyçu.', **snapshot(demo)), 401


def protect_errors(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with current_app.extensions['enigma_lab']['lock']:
            try:
                return fn(*args, **kwargs)
            except (OSError, ValueError, KeyError, TypeError):
                return jsonify(error='College demo storage is unavailable or invalid. No access was granted.'), 503
    return wrapped


def visible_rows(demo, actor):
    rows = demo['grades']
    rules = demo['policy']['rules']
    if actor['role'] == 'student' and rules['student_own_grades_only']:
        rows = [row for row in rows if row['student_id'] == actor['id']]
    if actor['role'] == 'professor' and rules['professor_assigned_courses_only']:
        rows = [row for row in rows if row['course'] in actor['courses']]
    return [dict(row) for row in rows]


@college.get('/college')
@college.get('/college/')
def home():
    return render_template('college.html', initial_view='grades')


@college.get('/college/professor')
@protect_errors
def professor_page():
    lab, demo = context()
    actor = signed_in(lab, demo, 'professor_page')
    code = 200
    if not actor:
        code = 401
    elif actor['role'] == 'student' and demo['policy']['rules']['block_student_professor_area']:
        record(lab, demo, 'professor_page_denied', False, 'professor')
        code = 403
    return render_template('college.html', initial_view='professor'), code


@college.get('/api/college/status')
@protect_errors
def status():
    _, demo = context()
    return jsonify(status='ok', **snapshot(demo), users=list(USERS.values()), courses=list(COURSES))


@college.post('/api/college/login')
@protect_errors
def login():
    data, error = payload()
    if error:
        return error
    identifier = data.get('user_id')
    if not isinstance(identifier, str) or identifier not in USERS or set(data) != {'user_id'}:
        return jsonify(error='Choose one of the fictional demo identities.'), 400
    lab, demo = context()
    demo.update(actor_id=identifier, last_activity=time.monotonic(), expired=False)
    record(lab, demo, 'demo_identity_selected', True, identifier)
    return jsonify(status='ok', **snapshot(demo))


@college.post('/api/college/logout')
@protect_errors
def logout():
    data, error = payload()
    if error:
        return error
    lab, demo = context()
    record(lab, demo, 'demo_logout', True)
    demo.update(actor_id=None, last_activity=None, expired=False)
    return jsonify(status='ok', **snapshot(demo))


@college.get('/api/college/policy')
@protect_errors
def get_policy():
    _, demo = context()
    return jsonify(status='ok', **snapshot(demo))


@college.post('/api/college/policy')
@protect_errors
def set_policy():
    data, error = payload()
    if error:
        return error
    rules = data.get('rules')
    if (set(data) != {'rules'} or not isinstance(rules, dict) or set(rules) != set(RULES)
            or any(type(value) is not bool for value in rules.values())):
        return jsonify(error='Provide exactly the six supported rules as true/false values.'), 400
    lab, demo = context()
    policy = {'rules': dict(rules), 'updated_at': datetime.now(timezone.utc).isoformat()}
    services.atomic_json(services.ROOT / lab['id'] / 'college-policy.json', policy)
    was_timed = demo['policy']['rules']['session_inactivity_timeout']
    demo['policy'] = policy
    if rules['session_inactivity_timeout'] and not was_timed and demo['actor_id']:
        demo['last_activity'] = time.monotonic()
    record(lab, demo, 'policy_applied_by_lab_operator', True, 'task_01')
    return jsonify(status='ok', **snapshot(demo))


@college.get('/api/college/grades')
@protect_errors
def grades():
    lab, demo = context()
    actor = signed_in(lab, demo, 'grades')
    if not actor:
        return missing_identity(demo)
    target = request.args.get('student_id')
    if set(request.args) - {'student_id'} or len(request.args.getlist('student_id')) > 1:
        return jsonify(error='Unsupported or repeated query parameter.'), 400
    if target is not None and target not in ('all', *STUDENT_IDS):
        return jsonify(error='Unknown fictional student.'), 400
    restricted = actor['role'] == 'student' and demo['policy']['rules']['student_own_grades_only']
    if restricted and target not in (None, actor['id']):
        record(lab, demo, 'other_student_grades_denied', False, target)
        return jsonify(error='Qasja u refuzua: studenti sheh vetëm notat e veta.', reason='own_grades_only', **snapshot(demo)), 403
    rows = visible_rows(demo, actor)
    if target not in (None, 'all'):
        rows = [row for row in rows if row['student_id'] == target]
    record(lab, demo, 'grades_read', True, target or 'all')
    return jsonify(status='ok', rows=rows, **snapshot(demo), scope='own' if restricted or target == actor['id'] else 'assigned' if actor['role'] == 'professor' and demo['policy']['rules']['professor_assigned_courses_only'] else 'selected' if target not in (None, 'all') else 'all')


@college.get('/api/college/professor')
@protect_errors
def professor():
    lab, demo = context()
    actor = signed_in(lab, demo, 'professor')
    if not actor:
        return missing_identity(demo)
    if actor['role'] == 'student' and demo['policy']['rules']['block_student_professor_area']:
        record(lab, demo, 'professor_area_denied', False, 'professor')
        return jsonify(error='Qasja u refuzua: kjo zonë lejohet vetëm për profesorin.', reason='professor_only', **snapshot(demo)), 403
    record(lab, demo, 'professor_area_read', True, 'professor')
    return jsonify(status='ok', rows=visible_rows(demo, actor), **snapshot(demo))


@college.post('/api/college/grades/update')
@protect_errors
def update_grade():
    data, error = payload()
    if error:
        return error
    lab, demo = context()
    actor = signed_in(lab, demo, 'grade_update')
    if not actor:
        return missing_identity(demo)
    if (set(data) != {'student_id', 'course', 'grade'} or data.get('student_id') not in STUDENT_IDS
            or data.get('course') not in COURSES or type(data.get('grade')) is not int
            or not 5 <= data['grade'] <= 10):
        return jsonify(error='Zgjedh studentin, lëndën dhe një notë të plotë nga 5 deri 10.'), 400
    rules = demo['policy']['rules']
    reason = None
    if actor['role'] == 'student':
        if rules['block_student_grade_edit']:
            reason = 'Studentët nuk lejohen të ndryshojnë nota.'
        elif rules['student_own_grades_only'] and data['student_id'] != actor['id']:
            reason = 'Nuk lejohet ndryshimi i notave të një studenti tjetër.'
    elif rules['professor_assigned_courses_only'] and data['course'] not in actor['courses']:
        reason = 'Profesori mund të ndryshojë vetëm lëndën e caktuar.'
    target = data['student_id'] + ' / ' + data['course']
    if reason:
        record(lab, demo, 'grade_update_denied', False, target)
        return jsonify(error=reason, **snapshot(demo)), 403
    row = next(row for row in demo['grades'] if row['student_id'] == data['student_id'] and row['course'] == data['course'])
    old_grade = row['grade']
    # Persist the audit before mutating the in-memory fictional record.
    record(lab, demo, 'grade_updated', True, target + f' / {old_grade} -> {data["grade"]}')
    row['grade'] = data['grade']
    demo['revision'] += 1
    return jsonify(status='ok', previous_grade=old_grade, row=dict(row), **snapshot(demo))


@college.get('/api/college/audit')
@protect_errors
def audit():
    lab, demo = context()
    actor = signed_in(lab, demo, 'audit')
    if not actor:
        return missing_identity(demo)
    if demo['policy']['rules']['audit_professor_only'] and actor['role'] != 'professor':
        record(lab, demo, 'audit_access_denied', False, 'audit')
        return jsonify(error='Auditimi i kolegjit lejohet vetëm për profesorin.', **snapshot(demo)), 403
    record(lab, demo, 'audit_read', True, 'audit')
    return jsonify(status='ok', events=demo['audit'], **snapshot(demo))
