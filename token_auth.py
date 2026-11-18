"""Persisted educational software token. Not a hardware authenticator / PKCS #11.

All identity decisions come from a session or a password-verified pending ticket.
Locks and one-use challenge consumption live in PostgreSQL, not worker memory.
"""
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timezone
from functools import wraps

import psycopg
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import jsonify, request, current_app
from werkzeug.security import generate_password_hash, check_password_hash


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def pin_value(value):
    if not isinstance(value, str) or not 4 <= len(value) <= 128 or '\x00' in value:
        raise ValueError('Use a disposable PIN/passphrase of 4–128 characters; a long passphrase is safer.')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Enter a valid Unicode PIN/passphrase.')
    return value


def generate_token(pin):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.BestAvailableEncryption(pin.encode()))
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return public.decode(), private.decode()


def signed_check(private_blob, public_blob, pin, nonce, test='normal'):
    key = serialization.load_pem_private_key(private_blob.encode(), password=pin.encode())
    pad = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)
    signature = key.sign(nonce.encode(), pad, hashes.SHA256())
    public = serialization.load_pem_public_key(public_blob.encode())
    if test == 'wrong_key':
        public = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    try:
        public.verify(signature, (nonce + ('-altered' if test == 'altered' else '')).encode(), pad, hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def pending_response(connection, actor):
    # Password verification (or successful signup) is the ONLY caller of this helper.
    connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (actor['id'],))
    connection.execute('DELETE FROM token_pending WHERE user_id=%s', (actor['id'],))
    ticket = secrets.token_urlsafe(48)
    connection.execute("INSERT INTO token_pending(ticket_hash,user_id,expires_at) VALUES(%s,%s,now()+interval '5 minutes')", (digest(ticket), actor['id']))
    old = request.cookies.get(p.cookie_name('session'), '')
    if old:
        connection.execute('DELETE FROM sessions WHERE token_hash=%s', (digest(old),))
    row = connection.execute('SELECT status FROM software_tokens WHERE user_id=%s', (actor['id'],)).fetchone()
    csrf = secrets.token_urlsafe(32)
    response = jsonify(actor=None, pending=True, pendingActor=p.actor_json(actor), tokenStatus=row['status'] if row else 'not_enrolled', csrfToken=csrf, configured=True)
    p.set_cookie(response, 'pending', ticket, 300)
    p.set_cookie(response, 'csrf', csrf, 300)
    response.delete_cookie(p.cookie_name('session'), path='/', secure=bool(current_app.config.get('CLOUD_DEMO')), httponly=True, samesite='Strict')
    return response


def token_endpoint(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            with p.database() as connection:
                # A pending flow always takes precedence over an old session.
                raw = request.cookies.get(p.cookie_name('pending'), '')
                pending = None
                actor = None
                if re.fullmatch(r'[A-Za-z0-9_-]{64}', raw):
                    pending = connection.execute('''SELECT t.ticket_hash,u.id,u.name,u.email,u.role FROM token_pending t
                        JOIN users u ON u.id=t.user_id WHERE t.ticket_hash=%s AND t.expires_at>now() AND u.active
                        ''', (digest(raw),)).fetchone()
                    actor = pending
                if not actor:
                    actor = p.current_actor(connection)
                if not actor:
                    return jsonify(error='Sign in with your password first. Pending verification expires after five minutes.'), 401
                # Serialize all token operations for an identity, even initial enrollment.
                owner = connection.execute('SELECT id,name,email,role FROM users WHERE id=%s AND active FOR UPDATE', (actor['id'],)).fetchone()
                if not owner:
                    return jsonify(error='Account unavailable.'), 401
                if pending:
                    # Lock in the same user -> ticket order as password sign-in.
                    still_pending = connection.execute('SELECT ticket_hash FROM token_pending WHERE ticket_hash=%s AND user_id=%s AND expires_at>now() FOR UPDATE', (pending['ticket_hash'], owner['id'])).fetchone()
                    if not still_pending:
                        return jsonify(error='Pending verification expired or already completed. Sign in again.'), 401
                if pending and owner['role'] != 'student':
                    return jsonify(error='Account permissions changed. Sign in again.'), 401
                return fn(connection, owner, pending, *args, **kwargs)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except (psycopg.Error, RuntimeError):
            return jsonify(error='Token database unavailable. Ask the operator to apply schema version 3.'), 503
    return wrapped


def target_user(connection, actor, pending, data):
    identifier = p.valid_uuid(data.get('userId', actor['id']))
    if identifier != str(actor['id']):
        if pending or actor['role'] != 'admin':
            return None
        return connection.execute("SELECT id,name,email,role FROM users WHERE id=%s AND active AND role='student' FOR UPDATE", (identifier,)).fetchone()
    return actor


def status_row(connection, user):
    row = connection.execute('SELECT status,failures,created_at FROM software_tokens WHERE user_id=%s', (user['id'],)).fetchone()
    return dict(p.actor_json(user), tokenStatus=row['status'] if row else 'not_enrolled', failures=row['failures'] if row else 0)


def register(blueprint):
    global p
    import portal as p
    @blueprint.get('/api/portal/token/status')
    @token_endpoint
    def token_status(connection, actor, pending):
        users = [actor]
        if actor['role'] == 'admin' and not pending:
            users += connection.execute("SELECT id,name,email,role FROM users WHERE active AND role='student' AND id<>%s ORDER BY name,email", (actor['id'],)).fetchall()
        return jsonify(users=[status_row(connection, u) for u in users], pending=bool(pending), canManage=actor['role']=='admin' and not pending)

    @blueprint.post('/api/portal/token/enroll')
    @token_endpoint
    def token_enroll(connection, actor, pending):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) not in ({'pin'}, {'pin','userId'}):
            raise ValueError('Submit only a PIN/passphrase and optional authorized account selection.')
        pin = pin_value(data['pin'])
        target = target_user(connection, actor, pending, data)
        if not target:
            p.audit(connection, actor, 'token_enroll_denied', False)
            return jsonify(error='Only administrators may enroll another active student.'), 403
        if connection.execute('SELECT 1 FROM software_tokens WHERE user_id=%s', (target['id'],)).fetchone():
            return jsonify(error='A token is already enrolled. Enrollment cannot replace or unlock it.'), 409
        public, private = generate_token(pin)
        connection.execute('''INSERT INTO software_tokens(user_id,public_key,private_key_encrypted,pin_hash)
            VALUES(%s,%s,%s,%s)''', (target['id'],public,private,generate_password_hash(pin)))
        p.audit(connection, actor, 'token_enrolled', True, target['id'])
        return jsonify(status='enrolled', tokenStatus='active', pending=bool(pending), simulation=True)

    @blueprint.post('/api/portal/token/challenge')
    @token_endpoint
    def token_challenge(connection, actor, pending):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) not in (set(), {'userId'}):
            raise ValueError('Unsupported challenge fields.')
        target = target_user(connection, actor, pending, data)
        if not target:
            return jsonify(error='This account selection is not allowed.'), 403
        token = connection.execute('SELECT status FROM software_tokens WHERE user_id=%s', (target['id'],)).fetchone()
        if not token or token['status'] != 'active':
            return jsonify(error='Enroll an active token first; locked tokens require operator recovery.'), 409
        # Supersede old challenges for this identity and context. Each challenge is
        # bound to either the pending ticket or the exact authenticated session.
        context = pending['ticket_hash'] if pending else digest(request.cookies.get(p.cookie_name('session'), ''))
        connection.execute('DELETE FROM token_challenges WHERE user_id=%s AND context_hash=%s', (target['id'], context))
        identifier, nonce = str(uuid.uuid4()), secrets.token_urlsafe(32)
        connection.execute("INSERT INTO token_challenges(id,user_id,context_hash,nonce,expires_at) VALUES(%s,%s,%s,%s,now()+interval '60 seconds')", (identifier,target['id'],context,nonce))
        p.audit(connection, actor, 'token_challenge', True, target['id'])
        return jsonify(challengeId=identifier, challenge=nonce, expiresIn=60, simulation=True)

    @blueprint.post('/api/portal/token/verify')
    @token_endpoint
    def token_verify(connection, actor, pending):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) not in ({'pin','challengeId','test'}, {'pin','challengeId','test','userId'}):
            raise ValueError('Submit PIN, challengeId and test only (plus authorized account selection).')
        pin, identifier, test = pin_value(data['pin']), p.valid_uuid(data['challengeId']), data['test']
        if test not in ('normal','altered','wrong_key'):
            raise ValueError('Select a supported signature test.')
        target = target_user(connection, actor, pending, data)
        if not target:
            return jsonify(error='This account selection is not allowed.'), 403
        context = pending['ticket_hash'] if pending else digest(request.cookies.get(p.cookie_name('session'), ''))
        challenge = connection.execute('''DELETE FROM token_challenges WHERE id=%s AND user_id=%s AND context_hash=%s
            RETURNING nonce,expires_at''', (identifier,target['id'],context)).fetchone()
        # DELETE is atomic and takes a row lock. It commits even on a rejected attempt.
        if not challenge or challenge['expires_at'] <= datetime.now(timezone.utc):
            p.audit(connection, actor, 'token_challenge_rejected', False, target['id'])
            return jsonify(authenticated=False, error='Challenge expired or consumed. Request a fresh challenge.'), 409
        token = connection.execute('SELECT * FROM software_tokens WHERE user_id=%s FOR UPDATE', (target['id'],)).fetchone()
        if not token or token['status'] != 'active':
            return jsonify(authenticated=False, error='Token unavailable or locked.'), 423
        valid_pin = check_password_hash(token['pin_hash'], pin)
        valid = valid_pin and signed_check(token['private_key_encrypted'], token['public_key'], pin, challenge['nonce'], test)
        if not valid:
            connection.execute("UPDATE software_tokens SET failures=failures+1,status=CASE WHEN failures+1>=5 THEN 'locked' ELSE status END WHERE user_id=%s", (target['id'],))
            p.audit(connection, actor, 'token_verification_failed', False, target['id'])
            return jsonify(authenticated=False, signature_verified=False, error='PIN or signature rejected. Five failures lock the token.'), 401
        connection.execute('UPDATE software_tokens SET failures=0 WHERE user_id=%s', (target['id'],))
        p.audit(connection, actor, 'token_verified', True, target['id'])
        if pending:
            connection.execute('DELETE FROM token_pending WHERE ticket_hash=%s', (pending['ticket_hash'],))
            connection.execute('DELETE FROM token_challenges WHERE context_hash=%s', (pending['ticket_hash'],))
            response = p.auth_response(connection, actor)
            response.delete_cookie(p.cookie_name('pending'), path='/', secure=bool(current_app.config.get('CLOUD_DEMO')), httponly=True, samesite='Strict')
            return response
        # Demonstrating a student's token must NEVER impersonate that student.
        return jsonify(authenticated=True, signature_verified=True, simulation=True, sessionIssued=False)

    @blueprint.get('/api/portal/token/audit')
    @token_endpoint
    def token_audit(connection, actor, pending):
        if actor['role']=='admin' and not pending:
            rows = connection.execute("SELECT timestamp,actor_name,action,allowed,target FROM audit_events WHERE action LIKE 'token_%' ORDER BY id DESC LIMIT 100").fetchall()
        else:
            rows = connection.execute("SELECT timestamp,actor_name,action,allowed,target FROM audit_events WHERE action LIKE 'token_%' AND (actor_id=%s OR target=%s) ORDER BY id DESC LIMIT 100", (actor['id'],str(actor['id']))).fetchall()
        return jsonify(events=rows)
