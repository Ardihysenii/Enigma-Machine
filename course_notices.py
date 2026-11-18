"""Persisted fictional course notices; no private-key storage or mutation API.

Teacher identity is application provenance, not independently certified identity.
All SQL uses the connection's validated search_path; only notice routes migrate.
"""
import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import jsonify, request
from psycopg.types.json import Jsonb

ALGORITHM = 'RSA-2048 / PSS / SHA-256 / 32-byte salt'
# No CASCADE: deleting an account/course must not silently delete signed history.
NOTICE_DDL = """
CREATE TABLE IF NOT EXISTS course_notices (
  id uuid PRIMARY KEY,
  course_id uuid NOT NULL REFERENCES courses(id),
  teacher_id uuid NOT NULL REFERENCES users(id),
  request_id uuid NOT NULL,
  request_hash char(64) NOT NULL,
  course_code varchar(24) NOT NULL,
  teacher_name varchar(100) NOT NULL,
  title varchar(160) NOT NULL,
  published_at timestamptz NOT NULL,
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  signature text NOT NULL,
  public_key text NOT NULL,
  public_key_fingerprint char(64) NOT NULL,
  algorithm text NOT NULL,
  UNIQUE(teacher_id,request_id)
);
CREATE INDEX IF NOT EXISTS course_notices_course_time ON course_notices(course_id,published_at DESC,id DESC);
"""


def ensure_notice_schema(connection):
    if connection.execute('SELECT version FROM schema_versions WHERE version=4').fetchone():
        return
    connection.execute('SELECT pg_catalog.pg_advisory_xact_lock(74420307)')
    if connection.execute('SELECT version FROM schema_versions WHERE version=4').fetchone():
        return
    connection.execute(NOTICE_DDL, prepare=False)
    connection.execute('INSERT INTO schema_versions(version) VALUES(4) ON CONFLICT DO NOTHING')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def normalized_payload(payload, require_drawing=False):
    # Lazy import avoids the legacy signature module's portal import cycle.
    from teacher_signatures import canonical
    return json.loads(canonical(payload, require_drawing=require_drawing))


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def signed_bytes(row, payload=None):
    """Domain separated envelope binds every displayed identity/notice field."""
    return encoded(dict(domain='enigma-course-notice-v1', id=str(row['id']),
                        courseId=str(row['course_id']), courseCode=row['course_code'],
                        teacherId=str(row['teacher_id']), teacherName=row['teacher_name'],
                        title=row['title'], publishedAt=timestamp(row['published_at']),
                        payload=normalized_payload(row['payload'] if payload is None else payload)))


def sign_notice(row):
    from teacher_signatures import scheme
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    try:
        public = private.public_key()
        row['signature'] = base64.b64encode(private.sign(signed_bytes(row), scheme(), hashes.SHA256())).decode('ascii')
        row['public_key'] = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
        der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        row['public_key_fingerprint'] = hashlib.sha256(der).hexdigest()
        row['algorithm'] = ALGORITHM
    finally:
        # Never serialize, return, log or retain a private key. Python cannot
        # promise physical memory zeroization; dropping references is best effort.
        del private
    return row


def verify_notice(row, test, payload=None):
    from teacher_signatures import scheme
    public = serialization.load_pem_public_key(row['public_key'].encode('ascii'))
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size != 2048:
        raise ValueError('Stored notice key is invalid.')
    if test == 'wrong_key':
        public = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    content = signed_bytes(row, payload if test == 'current' else None)
    try:
        public.verify(base64.b64decode(row['signature'], validate=True), content, scheme(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def summary(row):
    return dict(id=str(row['id']), title=row['title'], courseId=str(row['course_id']),
                courseCode=row['course_code'], teacherName=row['teacher_name'], publishedAt=timestamp(row['published_at']))


def detail(row):
    return dict(summary(row), payload=row['payload'], signature=row['signature'], publicKey=row['public_key'],
                publicKeyFingerprint=row['public_key_fingerprint'], algorithm=row['algorithm'])


def scope(actor, column):
    # Roles are also enforced by portal.endpoint. Never consult lab switches.
    if actor['role'] == 'professor':
        return 'EXISTS(SELECT 1 FROM teaching_assignments a WHERE a.user_id=%s AND a.course_id=' + column + ')'
    if actor['role'] == 'student':
        return 'EXISTS(SELECT 1 FROM enrollments e WHERE e.student_id=%s AND e.course_id=' + column + ')'
    raise ValueError('Your role does not allow this action.')


def register(blueprint):
    import portal as p

    def find_notice(connection, actor, identifier):
        identifier = p.valid_uuid(identifier)
        return connection.execute('SELECT n.* FROM course_notices n WHERE n.id=%s AND ' + scope(actor, 'n.course_id'),
                                  (identifier, actor['id'])).fetchone()

    @blueprint.get('/api/portal/notices/courses')
    @p.endpoint(('professor', 'student'))
    def notice_courses(connection, actor):
        ensure_notice_schema(connection)
        rows = connection.execute('SELECT c.id,c.code,c.title FROM courses c WHERE ' + scope(actor, 'c.id') + ' ORDER BY c.code', (actor['id'],)).fetchall()
        return jsonify(courses=[dict(id=str(row['id']), code=row['code'], title=row['title']) for row in rows])

    @blueprint.get('/api/portal/notices')
    @p.endpoint(('professor', 'student'))
    def list_notices(connection, actor):
        course = p.valid_uuid(request.args['courseId']) if 'courseId' in request.args else None
        ensure_notice_schema(connection)
        query = 'SELECT n.* FROM course_notices n WHERE ' + scope(actor, 'n.course_id')
        params = [actor['id']]
        if course:
            query += ' AND n.course_id=%s'
            params.append(course)
        rows = connection.execute(query + ' ORDER BY n.published_at DESC,n.id DESC LIMIT 100', params).fetchall()
        return jsonify(notices=[summary(row) for row in rows])

    @blueprint.get('/api/portal/notices/<notice_id>')
    @p.endpoint(('professor', 'student'))
    def get_notice(connection, actor, notice_id):
        ensure_notice_schema(connection)
        row = find_notice(connection, actor, notice_id)
        if not row:
            return jsonify(error='Notice not found in your courses.'), 404
        return jsonify(notice=detail(row))

    @blueprint.post('/api/portal/notices')
    @p.endpoint(('professor',))
    def publish_notice(connection, actor):
        data = p.read_payload(('courseId', 'title', 'payload', 'requestId'))
        course, retry = p.valid_uuid(data['courseId']), p.valid_uuid(data['requestId'])
        title = p.name_value(data['title'], 160)
        content = normalized_payload(data['payload'], require_drawing=True)
        digest = hashlib.sha256(encoded(dict(courseId=course, title=title, payload=content))).hexdigest()
        ensure_notice_schema(connection)
        # Same lock as account-role/teaching changes; recheck after acquiring it.
        connection.execute('SELECT pg_catalog.pg_advisory_xact_lock(74420301)')
        teacher = connection.execute("SELECT id,name FROM users WHERE id=%s AND role='professor' AND active", (actor['id'],)).fetchone()
        assigned = connection.execute('SELECT c.id,c.code FROM courses c JOIN teaching_assignments a ON a.course_id=c.id WHERE a.user_id=%s AND c.id=%s', (actor['id'], course)).fetchone()
        if not teacher or not assigned:
            p.audit(connection, actor, 'notice_publish_denied', False, course)
            return jsonify(error='You may publish only to a course assigned to you.'), 403
        existing = connection.execute('SELECT * FROM course_notices WHERE teacher_id=%s AND request_id=%s', (actor['id'], retry)).fetchone()
        if existing:
            if existing['request_hash'] != digest:
                return jsonify(error='This request ID was already used for different notice content.'), 409
            return jsonify(notice=detail(existing)), 200
        row = dict(id=str(uuid.uuid4()), course_id=course, teacher_id=str(actor['id']), request_id=retry, request_hash=digest,
                   course_code=assigned['code'], teacher_name=teacher['name'], title=title,
                   published_at=datetime.now(timezone.utc), payload=content)
        sign_notice(row)
        columns = ('id', 'course_id', 'teacher_id', 'request_id', 'request_hash', 'course_code', 'teacher_name', 'title', 'published_at',
                   'payload', 'signature', 'public_key', 'public_key_fingerprint', 'algorithm')
        connection.execute('INSERT INTO course_notices (' + ','.join(columns) + ') VALUES (' + ','.join(['%s'] * len(columns)) + ')',
                           tuple(Jsonb(row[key]) if key == 'payload' else row[key] for key in columns))
        p.audit(connection, actor, 'course_notice_published', True, row['id'])
        return jsonify(notice=detail(row)), 201

    @blueprint.post('/api/portal/notices/<notice_id>/verify')
    @p.endpoint(('professor', 'student'))
    def verify_course_notice(connection, actor, notice_id):
        data = request.get_json(silent=True) if request.is_json else None
        if not isinstance(data, dict) or not isinstance(data.get('test'), str) or data['test'] not in ('original', 'current', 'wrong_key'):
            raise ValueError('Choose original, current or wrong_key verification.')
        expected = {'test', 'payload'} if data['test'] == 'current' else {'test'}
        if set(data) != expected:
            raise ValueError('Only current verification accepts a temporary payload; signature and public key are stored.')
        content = normalized_payload(data['payload']) if data['test'] == 'current' else None
        ensure_notice_schema(connection)
        row = find_notice(connection, actor, notice_id)
        if not row:
            return jsonify(error='Notice not found in your courses.'), 404
        valid = verify_notice(row, data['test'], content)
        p.audit(connection, actor, 'course_notice_verified', valid, row['id'])
        return jsonify(verified=valid, test=data['test'], identityTrusted=False, noticeId=str(row['id']))
