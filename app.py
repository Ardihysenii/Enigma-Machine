"""ENIGMA loopback-only educational laboratory, not a production service."""
import secrets
import json
import threading
import time
from flask import Flask, jsonify, render_template, request, send_file, session
from services import ROOT, TASKS, run_task

# Keep the signing secret local so this browser can reload its analysis after restart.
# This is a lab session secret, never a production credential or submitted artifact.
ROOT.mkdir(parents=True, exist_ok=True)
secret_file = ROOT / '.session-secret'
try:
    with secret_file.open('xb') as output:
        output.write(secrets.token_bytes(32))
except FileExistsError:
    pass
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=32 * 1024, SECRET_KEY=secret_file.read_bytes(),
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                  TRUSTED_HOSTS=['127.0.0.1', 'localhost'])
STATES = {}
LOCK = threading.RLock()


def lab_state():
    now = time.monotonic()
    for identifier in list(STATES):
        if now - STATES[identifier]['last_seen'] > 3600:
            del STATES[identifier]
    identifier = session.get('lab')
    if identifier not in STATES:
        if len(STATES) >= 100:
            raise ValueError('Too many active laboratory sessions. Restart the local server.')
        if not isinstance(identifier, str) or len(identifier) != 48 or any(c not in '0123456789abcdef' for c in identifier):
            identifier = secrets.token_hex(24)
        session['lab'] = identifier
        # Restore non-secret records only; private token keys/PIN hashes never persist.
        audit_path = ROOT / identifier / 'audit.json'
        try:
            records = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else []
            if not isinstance(records, list):
                records = []
        except (OSError, ValueError):
            records = []
        STATES[identifier] = {'id': identifier, 'downloads': {}, 'audit': records[-100:]}

    STATES[identifier]['last_seen'] = now
    return STATES[identifier]


@app.before_request
def local_request_only():
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify(error='This laboratory accepts loopback requests only.'), 403
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if (origin and origin != request.host_url.rstrip('/')) or request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(error='Cross-origin operations are not allowed.'), 403


@app.after_request
def security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
    return response


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/api/health')
def health():
    return jsonify(status='ok', application='ENIGMA', mode='local-learning-laboratory',
                   cryptography_implemented=True)


@app.get('/api/tasks')
def tasks():
    return jsonify(tasks=TASKS)


@app.post('/api/tasks/<task_id>/run')
def execute(task_id):
    if task_id not in TASKS:
        return jsonify(error='Unknown task.'), 404
    if not request.is_json:
        return jsonify(error='Send a JSON object.'), 415
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error='Send a valid JSON object.'), 400
    message = payload.get('message', '')
    if not isinstance(message, str) or len(message) > 2000:
        return jsonify(error='Message must be text, at most 2,000 characters.'), 400
    try:
        with LOCK:
            return jsonify(run_task(task_id, payload, lab_state()))
    except ValueError as exc:
        return jsonify(status='invalid_input', error=str(exc)), 400
    except OSError:
        return jsonify(status='storage_error', error='Local laboratory files could not be written or read. Check folder access.'), 500


@app.get('/api/download/<token>')
def download(token):
    with LOCK:
        state = STATES.get(session.get('lab'), {})
        if time.monotonic() - state.get('last_seen', 0) > 3600:
            return jsonify(error='Laboratory session expired.'), 404
        entry = state.get('downloads', {}).get(token)
        if not entry or not entry[0].is_file():
            return jsonify(error='Download unavailable in this session.'), 404
        return send_file(entry[0], as_attachment=True, download_name=entry[1], mimetype='application/octet-stream')


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error='Request exceeds the 32 KB laboratory limit.'), 413


# Share the active application state without importing a second app when run as a script.
app.extensions['enigma_lab'] = {'state': lab_state, 'lock': LOCK}
from college import college
app.register_blueprint(college)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)
