"""Database-backed fictional college accounts with explicit educational lab controls."""
import hashlib
import os
import re
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from portal_policy import policy, validate_rules, IDLE_SECONDS
from flask import Blueprint, current_app, jsonify, render_template, request, g
from werkzeug.security import check_password_hash, generate_password_hash

portal = Blueprint('portal', __name__)
SESSION_HOURS = 24 * 30
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(24))


def configured():
    return bool(current_app.config.get('PORTAL_DATABASE_URL') or os.environ.get('ENIGMA_DATABASE_URL') or os.environ.get('DATABASE_URL'))


@contextmanager
def database():
    dsn = current_app.config.get('PORTAL_DATABASE_URL') or os.environ.get('ENIGMA_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not dsn:
        raise RuntimeError('database_not_configured')
    schema = current_app.config.get('PORTAL_SCHEMA', 'enigma_portal')
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
        raise RuntimeError('invalid_schema')
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as connection:
        connection.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
        connection.execute("SET LOCAL statement_timeout = '8s'")
        yield connection


def cookie_name(kind):
    return ('__Host-' if current_app.config.get('CLOUD_DEMO') else '') + 'enigma_portal_' + kind


def set_cookie(response, kind, value, seconds):
    response.set_cookie(cookie_name(kind), value, max_age=seconds, secure=bool(current_app.config.get('CLOUD_DEMO')),
                        httponly=True, samesite='Strict', path='/')


def csrf_token():
    token = request.cookies.get(cookie_name('csrf'), '')
    return token if re.fullmatch(r'[A-Za-z0-9_-]{43}', token) else secrets.token_urlsafe(32)


def actor_json(row):
    return {key: str(row[key]) if key == 'id' else row[key] for key in ('id', 'name', 'email', 'role')}


def audit(connection, actor, action, allowed, target=None):
    connection.execute('INSERT INTO audit_events(actor_id,actor_name,action,allowed,target) VALUES(%s,%s,%s,%s,%s)',
                       (actor['id'] if actor else None, actor['name'] if actor else 'Visitor', action, allowed, str(target)[:254] if target else None))


def valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Select a valid account or course.')


def read_payload(fields):
    if not request.is_json:
        raise ValueError('Send a JSON object.')
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != set(fields):
        raise ValueError('The submitted fields are incomplete or unsupported.')
    return data


def email_value(value):
    if not isinstance(value, str):
        raise ValueError('Enter a valid email address.')
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}', value):
        raise ValueError('Enter a valid email address.')
    return value


def name_value(value, limit=100):
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= limit or any(ord(char) < 32 for char in value):
        raise ValueError(f'Enter a name between 2 and {limit} characters.')
    return value.strip()


def password_value(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ValueError('Use a password between 12 and 128 characters.')
    return value


def current_actor(connection, touch=False):
    token = request.cookies.get(cookie_name('session'), '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{64}', token):
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    idle_enabled = policy(connection)['rules']['session_inactivity_timeout']
    # Once expiry is observed, revoke the persisted token permanently. A later
    # lab-policy change must never bring this session back to life.
    connection.execute('''DELETE FROM sessions WHERE token_hash=%s AND
        (expires_at<=now() OR (%s AND last_seen<=now()-(%s * interval '1 second')))''',
        (digest, idle_enabled, IDLE_SECONDS))
    row = connection.execute('''SELECT u.id,u.name,u.email,u.role FROM sessions s JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=%s AND u.active AND s.expires_at>now()
        AND (NOT %s OR s.last_seen>now()-(%s * interval '1 second')) ''',
        (digest, idle_enabled, IDLE_SECONDS)).fetchone()
    if row and touch:
        connection.execute("UPDATE sessions SET last_seen=now(),expires_at=now()+(%s * interval '1 hour') WHERE token_hash=%s", (SESSION_HOURS, digest))
        g.portal_session_touched = True
    return row


def auth_response(connection, actor):
    old = request.cookies.get(cookie_name('session'), '')
    if old:
        connection.execute('DELETE FROM sessions WHERE token_hash=%s', (hashlib.sha256(old.encode()).hexdigest(),))
    # Expiry/revocation are checked in PostgreSQL, not trusted from a client claim.
    connection.execute("DELETE FROM sessions WHERE expires_at<=now() OR (%s AND last_seen<=now()-(%s * interval '1 second'))",
                       (policy(connection)['rules']['session_inactivity_timeout'], IDLE_SECONDS))
    token = secrets.token_urlsafe(48)
    connection.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)',
                       (hashlib.sha256(token.encode()).hexdigest(), actor['id'], datetime.now(timezone.utc)+timedelta(hours=SESSION_HOURS)))
    csrf = secrets.token_urlsafe(32)
    response = jsonify(actor=actor_json(actor), csrfToken=csrf, configured=True)
    set_cookie(response, 'session', token, SESSION_HOURS*3600)
    set_cookie(response, 'csrf', csrf, SESSION_HOURS*3600)
    return response


def endpoint(roles=None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                with database() as connection:
                    actor = current_actor(connection, touch=not (request.endpoint in ('portal.dashboard', 'portal.professor_area') and request.args.get('poll') == '1'))
                    if not actor:
                        return jsonify(error='Sign in to continue.'), 401
                    if roles and actor['role'] not in roles:
                        audit(connection, actor, 'access_denied', False, request.path)
                        return jsonify(error='Your role does not allow this action.'), 403
                    return fn(connection, actor, *args, **kwargs)
            except ValueError as error:
                return jsonify(error=str(error)), 400
            except (psycopg.Error, RuntimeError):
                return jsonify(error='The account database is unavailable. Please retry shortly.'), 503
        return wrapped
    return decorate


@portal.before_request
def protect_mutations():
    if not request.path.startswith('/api/portal/') or request.method != 'POST':
        return None
    cookie = request.cookies.get(cookie_name('csrf'), '')
    header = request.headers.get('X-CSRF-Token', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', cookie) or not secrets.compare_digest(cookie, header):
        return jsonify(error='Refresh the page before submitting this form.'), 403
    return None


@portal.after_request
def renew_portal_cookie(response):
    # Only actual authenticated activity renews the browser's persisted cookie.
    # Never undo explicit signout, and never renew from policy/session polling.
    if getattr(g, 'portal_session_touched', False) and request.endpoint != 'portal.signout' and response.status_code < 400:
        token = request.cookies.get(cookie_name('session'), '')
        if re.fullmatch(r'[A-Za-z0-9_-]{64}', token):
            set_cookie(response, 'session', token, SESSION_HOURS * 3600)
            csrf = request.cookies.get(cookie_name('csrf'), '')
            if re.fullmatch(r'[A-Za-z0-9_-]{43}', csrf):
                set_cookie(response, 'csrf', csrf, SESSION_HOURS * 3600)
    return response


@portal.post('/api/portal/activity')
@endpoint()
def record_activity(connection, actor):
    read_payload(())
    return jsonify(status='ok')


@portal.get('/college')
@portal.get('/college/')
def college_home():
    return render_template('portal.html')


@portal.get('/api/portal/session')
def session_status():
    csrf = csrf_token()
    actor = None
    ready = configured()
    if ready:
        try:
            with database() as connection:
                actor = current_actor(connection)
                # Detect a missing policy migration even for a fresh visitor.
                policy(connection)
                connection.execute('SELECT version FROM schema_versions WHERE version=1').fetchone()
        except (psycopg.Error, RuntimeError):
            return jsonify(error='The account database is unavailable. Please retry shortly.', configured=False), 503
    response = jsonify(actor=actor_json(actor) if actor else None, csrfToken=csrf, configured=ready)
    set_cookie(response, 'csrf', csrf, SESSION_HOURS*3600)
    return response


@portal.get('/api/portal/policy')
@portal.post('/api/portal/policy')
def lab_policy():
    # Deliberately available to the lab operator without account authentication.
    # POST is still protected by the blueprint's double-submit CSRF check.
    try:
        rules = validate_rules(read_payload(('rules',))['rules']) if request.method == 'POST' else None
        with database() as connection:
            if rules is not None:
                connection.execute('UPDATE lab_policy SET rules=%s,revision=revision+1,updated_at=now() WHERE singleton=true', (Jsonb(rules),))
                connection.execute("INSERT INTO audit_events(actor_name,action,allowed,target) VALUES('Lab operator (demo)','lab_policy_changed',true,%s)",
                                   (','.join(key + '=' + str(value).lower() for key, value in rules.items())[:254],))
            return jsonify(policy(connection))
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (psycopg.Error, RuntimeError):
        return jsonify(error='The account database is unavailable. Please retry shortly.'), 503


def limit_key(prefix, identity):
    return hashlib.sha256((prefix + ':' + identity).encode()).hexdigest()


def limit_row(connection, key):
    connection.execute('INSERT INTO login_limits(key_hash) VALUES(%s) ON CONFLICT DO NOTHING', (key,))
    row = connection.execute('SELECT * FROM login_limits WHERE key_hash=%s FOR UPDATE', (key,)).fetchone()
    now = datetime.now(timezone.utc)
    if row['locked_until'] and row['locked_until'] > now:
        return True
    if now-row['window_started'] > timedelta(minutes=15):
        connection.execute('UPDATE login_limits SET failures=0,window_started=now(),locked_until=NULL WHERE key_hash=%s', (key,))
    return False


def limit_failure(connection, key, threshold=8):
    connection.execute("UPDATE login_limits SET failures=failures+1,locked_until=CASE WHEN failures+1 >= %s THEN now()+interval '15 minutes' ELSE locked_until END WHERE key_hash=%s", (threshold, key))


@portal.post('/api/portal/signup')
def signup():
    try:
        # Teacher self-registration is intentional for this fictional lab only.
        raw = request.get_json(silent=True) if request.is_json else None
        fields = ('name','email','password','role') if isinstance(raw, dict) and 'role' in raw else ('name','email','password')
        data = read_payload(fields)
        role = data.get('role', 'student')
        if role not in ('student', 'professor'):
            raise ValueError('Choose Student or Teacher.')
        name, email, password = name_value(data['name']), email_value(data['email']), password_value(data['password'])
        with database() as connection:
            key = limit_key('signup', request.remote_addr or 'unknown')
            if limit_row(connection, key):
                return jsonify(error='Too many account requests. Please try again later.'), 429
            limit_failure(connection, key, 12)
            actor = {'id': str(uuid.uuid4()), 'name': name, 'email': email, 'role': role}
            row = connection.execute('''INSERT INTO users(id,name,email,password_hash,role)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING RETURNING id''',
                (actor['id'], name, email, generate_password_hash(password), role)).fetchone()
            if not row:
                audit(connection, None, 'signup_rejected', False)
                return jsonify(error='Unable to create that account. Try signing in or use another address.'), 409
            audit(connection, actor, 'account_created', True, role)
            return auth_response(connection, actor)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (psycopg.Error, RuntimeError):
        return jsonify(error='The account database is unavailable. Please retry shortly.'), 503


@portal.post('/api/portal/signin')
def signin():
    try:
        data = read_payload(('email','password'))
        email = email_value(data['email'])
        password = data['password']
        if not isinstance(password, str) or len(password)>128:
            raise ValueError('Enter your email and password.')
        with database() as connection:
            keys = sorted([limit_key('email', email), limit_key('ip', request.remote_addr or 'unknown')])
            if any([limit_row(connection, key) for key in keys]):
                return jsonify(error='Too many sign-in attempts. Please try again later.'), 429
            actor = connection.execute('SELECT * FROM users WHERE email=%s', (email,)).fetchone()
            valid = check_password_hash(actor['password_hash'] if actor else DUMMY_PASSWORD_HASH, password)
            if not valid or not actor or not actor['active']:
                for key in keys:
                    limit_failure(connection, key, 8 if key == limit_key('email', email) else 40)
                audit(connection, None, 'signin_failed', False)
                return jsonify(error='Email or password is incorrect.'), 401
            connection.execute('UPDATE login_limits SET failures=0,locked_until=NULL,window_started=now() WHERE key_hash=%s', (limit_key('email', email),))
            audit(connection, actor, 'signed_in', True)
            return auth_response(connection, actor)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except (psycopg.Error, RuntimeError):
        return jsonify(error='The account database is unavailable. Please retry shortly.'), 503


@portal.post('/api/portal/signout')
@endpoint()
def signout(connection, actor):
    read_payload(())
    token = request.cookies.get(cookie_name('session'), '')
    connection.execute('DELETE FROM sessions WHERE token_hash=%s', (hashlib.sha256(token.encode()).hexdigest(),))
    audit(connection, actor, 'signed_out', True)
    response = jsonify(status='ok', actor=None, csrfToken=csrf_token())
    response.delete_cookie(cookie_name('session'), path='/', secure=bool(current_app.config.get('CLOUD_DEMO')), httponly=True, samesite='Strict')
    return response


@portal.get('/api/portal/dashboard')
@endpoint()
def dashboard(connection, actor):
    return dashboard_response(connection, actor)


@portal.get('/api/portal/professor')
@endpoint()
def professor_area(connection, actor):
    if actor['role'] == 'student' and policy(connection)['rules']['block_student_professor_area']:
        audit(connection, actor, 'access_denied', False, request.path)
        return jsonify(error='Your role does not allow this action.'), 403
    return dashboard_response(connection, actor)


def dashboard_response(connection, actor):
    controls = policy(connection)
    rules = controls['rules']
    condition, params = '', []
    if actor['role'] == 'student' and rules['student_own_grades_only']:
        condition, params = 'WHERE e.student_id=%s', [actor['id']]
    elif actor['role'] == 'professor' and rules['professor_assigned_courses_only']:
        condition, params = 'WHERE EXISTS(SELECT 1 FROM teaching_assignments a WHERE a.user_id=%s AND a.course_id=e.course_id)', [actor['id']]
    rows = connection.execute('''SELECT e.student_id AS "studentId", u.name AS "studentName", u.email AS "studentEmail",
        c.id AS "courseId",c.code AS "courseCode",c.title AS "courseTitle",g.grade
        FROM enrollments e JOIN users u ON u.id=e.student_id JOIN courses c ON c.id=e.course_id
        LEFT JOIN grades g ON g.student_id=e.student_id AND g.course_id=e.course_id ''' + condition + ' ORDER BY c.code,u.name', params).fetchall()
    if actor['role'] == 'admin' or (actor['role'] == 'student' and not rules['student_own_grades_only']) or (actor['role'] == 'professor' and not rules['professor_assigned_courses_only']):
        courses = connection.execute('SELECT id,code,title FROM courses ORDER BY code').fetchall()
    elif actor['role'] == 'professor':
        courses = connection.execute('SELECT c.id,c.code,c.title FROM courses c JOIN teaching_assignments a ON a.course_id=c.id WHERE a.user_id=%s ORDER BY c.code', (actor['id'],)).fetchall()
    else:
        courses = connection.execute('SELECT c.id,c.code,c.title FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE e.student_id=%s ORDER BY c.code', (actor['id'],)).fetchall()
    teaching_students, unassigned_courses = [], []
    if actor['role'] in ('professor', 'admin'):
        teaching_students = connection.execute("SELECT id,name,email FROM users WHERE role='student' AND active ORDER BY name,email").fetchall()
        unassigned_courses = connection.execute('''SELECT c.id,c.code,c.title FROM courses c
            WHERE NOT EXISTS(SELECT 1 FROM teaching_assignments a WHERE a.course_id=c.id)
            ORDER BY c.code''').fetchall()
    return jsonify(actor=actor_json(actor), rows=rows, courses=courses, policy=controls,
                   teachingStudents=teaching_students, unassignedCourses=unassigned_courses,
                   teachingCourses=connection.execute('SELECT c.id,c.code,c.title FROM courses c JOIN teaching_assignments a ON a.course_id=c.id WHERE a.user_id=%s ORDER BY c.code', (actor['id'],)).fetchall() if actor['role']=='professor' else [],
                   capabilities={'manageGrades':actor['role'] in ('professor','admin') or not rules['block_student_grade_edit'],'administer':actor['role']=='admin','readAudit':actor['role'] in ('professor','admin') or not rules['audit_professor_only']})


@portal.post('/api/portal/grades')
@endpoint()
def save_grade(connection, actor):
    rules = policy(connection)['rules']
    if actor['role'] == 'student' and rules['block_student_grade_edit']:
        audit(connection, actor, 'grade_update_denied', False)
        return jsonify(error='Your role does not allow this action.'), 403
    data = read_payload(('studentId','courseId','grade'))
    student, course, grade = valid_uuid(data['studentId']), valid_uuid(data['courseId']), data['grade']
    if type(grade) is not int or not 5<=grade<=10:
        raise ValueError('The grade must be a whole number from 5 to 10.')
    if actor['role'] == 'student' and rules['student_own_grades_only'] and student != str(actor['id']):
        audit(connection, actor, 'grade_update_denied', False, student)
        return jsonify(error='You may only edit your own grades.'), 403
    if actor['role'] == 'professor' and rules['professor_assigned_courses_only'] and not connection.execute('SELECT 1 FROM teaching_assignments WHERE user_id=%s AND course_id=%s', (actor['id'],course)).fetchone():
        audit(connection, actor, 'grade_update_denied', False, course)
        return jsonify(error='You are not assigned to that course.'), 403
    if not connection.execute("SELECT 1 FROM enrollments e JOIN users u ON u.id=e.student_id WHERE e.student_id=%s AND e.course_id=%s AND u.role='student'",(student,course)).fetchone():
        raise ValueError('Enroll the student in this course before entering a grade.')
    connection.execute('''INSERT INTO grades(student_id,course_id,grade,updated_by) VALUES(%s,%s,%s,%s)
        ON CONFLICT(student_id,course_id) DO UPDATE SET grade=excluded.grade,updated_by=excluded.updated_by,updated_at=now()''',(student,course,grade,actor['id']))
    audit(connection,actor,'grade_saved',True,student+'/'+course+'/'+str(grade))
    return jsonify(status='ok')


@portal.get('/api/portal/administration')
@endpoint(('admin',))
def administration(connection, actor):
    return jsonify(users=connection.execute('SELECT id,name,email,role,active FROM users ORDER BY name').fetchall(),
                   courses=connection.execute('SELECT id,code,title FROM courses ORDER BY code').fetchall(),
                   assignments=connection.execute('SELECT user_id AS "userId",course_id AS "courseId" FROM teaching_assignments').fetchall(),
                   enrollments=connection.execute('SELECT student_id AS "studentId",course_id AS "courseId" FROM enrollments').fetchall())


@portal.post('/api/portal/roles')
@endpoint(('admin',))
def set_role(connection, actor):
    data=read_payload(('userId','role'))
    identifier,role=valid_uuid(data['userId']),data['role']
    if role not in ('student','professor','admin'):
        raise ValueError('Select a supported role.')
    connection.execute('SELECT pg_advisory_xact_lock(74420301)')
    target=connection.execute('SELECT id,role FROM users WHERE id=%s FOR UPDATE',(identifier,)).fetchone()
    if not target:
        raise ValueError('Account not found.')
    if str(actor['id'])==identifier and role!='admin':
        raise ValueError('Use another administrator to change your own role.')
    if target['role']=='admin' and role!='admin' and connection.execute("SELECT count(*) AS count FROM users WHERE role='admin' AND active").fetchone()['count']<=1:
        raise ValueError('Keep at least one active administrator.')
    connection.execute('UPDATE users SET role=%s WHERE id=%s',(role,identifier))
    if role!='professor':
        connection.execute('DELETE FROM teaching_assignments WHERE user_id=%s',(identifier,))
    if role!='student':
        # Retain historical enrollment/grades; visibility and edit checks use current role.
        pass
    connection.execute('DELETE FROM sessions WHERE user_id=%s',(identifier,)) if role!=target['role'] else None
    audit(connection,actor,'role_assigned',True,identifier+'/'+role)
    return jsonify(status='ok')


@portal.post('/api/portal/courses')
@endpoint(('admin','professor'))
def add_course(connection, actor):
    data=read_payload(('code','title'))
    code=data['code'].strip().upper() if isinstance(data['code'],str) else ''
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{1,23}',code):
        raise ValueError('Use a course code of 2–24 letters, digits, underscores or hyphens.')
    title=name_value(data['title'],160)
    row=connection.execute('INSERT INTO courses(id,code,title) VALUES(%s,%s,%s) ON CONFLICT(code) DO NOTHING RETURNING id',(str(uuid.uuid4()),code,title)).fetchone()
    if not row:
        raise ValueError('That course code already exists.')
    if actor['role'] == 'professor':
        connection.execute('INSERT INTO teaching_assignments(user_id,course_id) VALUES(%s,%s)', (actor['id'], row['id']))
    audit(connection,actor,'course_created',True,code)
    return jsonify(status='ok', courseId=str(row['id']))


@portal.post('/api/portal/assignments')
@endpoint(('admin',))
def assign_professor(connection, actor):
    data=read_payload(('userId','courseId'))
    connection.execute('SELECT pg_advisory_xact_lock(74420301)')
    user,course=valid_uuid(data['userId']),valid_uuid(data['courseId'])
    if not connection.execute("SELECT 1 FROM users WHERE id=%s AND role='professor' AND active",(user,)).fetchone() or not connection.execute('SELECT 1 FROM courses WHERE id=%s',(course,)).fetchone():
        raise ValueError('Choose an active professor and an existing course.')
    connection.execute('INSERT INTO teaching_assignments(user_id,course_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(user,course))
    audit(connection,actor,'professor_assigned',True,user+'/'+course)
    return jsonify(status='ok')


@portal.post('/api/portal/enrollments')
@endpoint(('admin',))
def enroll_student(connection, actor):
    data=read_payload(('studentId','courseId'))
    student,course=valid_uuid(data['studentId']),valid_uuid(data['courseId'])
    if not connection.execute("SELECT 1 FROM users WHERE id=%s AND role='student' AND active",(student,)).fetchone() or not connection.execute('SELECT 1 FROM courses WHERE id=%s',(course,)).fetchone():
        raise ValueError('Choose an active student and an existing course.')
    connection.execute('INSERT INTO enrollments(student_id,course_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(student,course))
    audit(connection,actor,'student_enrolled',True,student+'/'+course)
    return jsonify(status='ok')


@portal.get('/api/portal/audit')
@endpoint()
def read_audit(connection, actor):
    if actor['role'] == 'student' and policy(connection)['rules']['audit_professor_only']:
        audit(connection, actor, 'access_denied', False, request.path)
        return jsonify(error='Your role does not allow this action.'), 403
    if actor['role']=='admin':
        rows=connection.execute('SELECT id,timestamp,actor_name AS "actorName",action,allowed,target FROM audit_events ORDER BY id DESC LIMIT 100').fetchall()
    else:
        rows=connection.execute('SELECT id,timestamp,actor_name AS "actorName",action,allowed,target FROM audit_events WHERE actor_id=%s ORDER BY id DESC LIMIT 100',(actor['id'],)).fetchall()
    return jsonify(events=rows)


@portal.post('/api/portal/teaching/assignments')
@endpoint(('professor','admin'))
def teaching_assignment(connection, actor):
    data = read_payload(('courseId',))
    course = valid_uuid(data['courseId'])
    # Serialize explicit claims with role changes; never claim courses on signup.
    connection.execute('SELECT pg_advisory_xact_lock(74420301)')
    if not connection.execute('SELECT 1 FROM courses WHERE id=%s', (course,)).fetchone():
        raise ValueError('Choose an existing course.')
    assignments = connection.execute('SELECT user_id FROM teaching_assignments WHERE course_id=%s', (course,)).fetchall()
    if any(str(row['user_id']) != str(actor['id']) for row in assignments):
        audit(connection, actor, 'teaching_assignment_denied', False, course)
        return jsonify(error='That course is already assigned to another teacher.'), 403
    connection.execute('INSERT INTO teaching_assignments(user_id,course_id) VALUES(%s,%s) ON CONFLICT DO NOTHING', (actor['id'], course))
    audit(connection, actor, 'professor_assigned', True, str(actor['id'])+'/'+course)
    return jsonify(status='ok', courseId=course)


@portal.post('/api/portal/teaching/enrollments')
@endpoint(('professor','admin'))
def teaching_enrollment(connection, actor):
    # Accept exactly one supported student selector, never arbitrary extra fields.
    if not request.is_json:
        raise ValueError('Send a JSON object.')
    data = request.get_json(silent=True)
    if isinstance(data, dict) and set(data) == {'studentId', 'courseId'}:
        data = read_payload(('studentId','courseId'))
        selector, value = 'id', valid_uuid(data['studentId'])
    else:
        data = read_payload(('studentEmail','courseId'))
        selector, value = 'email', email_value(data['studentEmail'])
    course = valid_uuid(data['courseId'])
    # Roster management stays assigned-only even with grade switches OFF.
    if actor['role'] == 'professor' and not connection.execute(
        'SELECT 1 FROM teaching_assignments WHERE user_id=%s AND course_id=%s', (actor['id'], course)).fetchone():
        audit(connection, actor, 'enrollment_denied', False, course)
        return jsonify(error='You can only enroll students in a course assigned to you.'), 403
    if not connection.execute('SELECT 1 FROM courses WHERE id=%s', (course,)).fetchone():
        raise ValueError('Choose an existing course.')
    # selector is one of the two hard-coded identifiers above, not user SQL.
    student = connection.execute("SELECT id FROM users WHERE " + selector + "=%s AND role='student' AND active", (value,)).fetchone()
    if not student:
        raise ValueError('No active student account matches that ' + ('email. Ask the student to create an account first.' if selector == 'email' else 'student ID.'))
    connection.execute('INSERT INTO enrollments(student_id,course_id) VALUES(%s,%s) ON CONFLICT DO NOTHING', (student['id'], course))
    audit(connection, actor, 'student_enrolled', True, str(student['id'])+'/'+course)
    return jsonify(status='ok')
