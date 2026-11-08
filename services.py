"""Local educational operations. Never use real identities or credentials here."""
import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).resolve().parent / 'lab-material'
TASKS = {k: {'name': v, 'implemented': True} for k, v in {
    'analysis': 'Security requirements', 'classical': 'Classical cipher',
    'rsa': 'RSA encryption', 'signatures': 'Digital signatures',
    'packaging': 'Protected keys & certificates', 'authentication': 'Token authentication & audit'
}.items()}


def text(p, name, default='', limit=2000):
    value = p.get(name, default)
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{name} must be text of at most {limit} characters.')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError(f'{name} must contain valid Unicode text.') from None
    return value


def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def pss():
    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH)


def verifies(public, signature, data):
    try:
        public.verify(signature, data, pss(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def analysis(p, state):
    action = text(p, 'action', 'save')
    # A random browser-session identifier isolates saved fictional analyses.
    path = ROOT / state['id'] / 'analysis.json'
    if action == 'load':
        if not path.exists():
            raise ValueError('No analysis has been saved for this browser session.')
        return {'analysis': json.loads(path.read_text(encoding='utf-8')), 'saved': True}
    if action != 'save':
        raise ValueError('Choose save or load.')
    fields = ['assets', 'roles', 'threats', 'confidentiality', 'integrity', 'availability', 'audit_evidence']
    result = {field: text(p, field).strip() for field in fields}
    if any(not value for value in result.values()):
        raise ValueError('Complete every analysis field before saving.')
    if len([line for line in result['threats'].splitlines() if line.strip()]) < 3:
        raise ValueError('Enter at least three threats, one per line, with controls.')
    result['saved_at'] = datetime.now(timezone.utc).isoformat()
    atomic_json(path, result)
    return {'analysis': result, 'saved': True, 'note': 'Saved locally for this browser session. Fictional information only.'}


def classical(p, state):
    message = text(p, 'message')
    cipher = text(p, 'cipher', 'caesar')
    operation = text(p, 'operation', 'encrypt')
    key = text(p, 'key')
    if operation not in ('encrypt', 'decrypt') or cipher not in ('caesar', 'vigenere'):
        raise ValueError('Choose Caesar/Vigenere and encrypt/decrypt.')
    if cipher == 'caesar':
        try:
            if not key.strip() or len(key) > 10:
                raise ValueError()
            shift = int(key) % 26
        except ValueError:
            raise ValueError('Caesar key must be an integer of at most 10 characters.') from None
        shifts = [shift]
    else:
        if not key or any(not ('A' <= c <= 'Z' or 'a' <= c <= 'z') for c in key):
            raise ValueError('Vigenere key must contain only A-Z letters.')
        shifts = [ord(c) - 65 for c in key.upper()]
    output, steps = [], []
    position = 0
    for c in message:
        upper = c.upper() if c.isascii() else c
        if len(upper) == 1 and 'A' <= upper <= 'Z':
            n, k = ord(upper) - 65, shifts[position % len(shifts)]
            value = (n + k if operation == 'encrypt' else n - k) % 26
            letter = chr(value + 65)
            output.append(letter)
            steps.append({'input': upper, 'value': n, 'key': k, 'calculation': f'({n} {"+" if operation == "encrypt" else "-"} {k}) mod 26 = {value}', 'output': letter})
            position += 1
        else:
            output.append(c)
    result = ''.join(output)
    inverse, position = [], 0
    for c in result:
        if 'A' <= c <= 'Z':
            k = shifts[position % len(shifts)]
            n = ord(c) - 65
            inverse.append(chr((n - k if operation == 'encrypt' else n + k) % 26 + 65))
            position += 1
        else:
            inverse.append(c)
    normalized = ''.join(c.upper() if c.isascii() else c for c in message)
    recovered = ''.join(inverse)
    return {'round_trip': recovered, 'recovery_matches': recovered == normalized,
            'ciphertext': result if operation == 'encrypt' else normalized,
            'plaintext': normalized if operation == 'encrypt' else result, 'cipher': cipher, 'operation': operation, 'key': key, 'input': message, 'output': result, 'steps': steps,
            'policy': 'ASCII letters become uppercase; all other characters are preserved and do not advance the key.',
            'weakness': 'Caesar has only 26 shifts; repeating-key Vigenere leaks patterns. Neither protects real records.',
            'key_management': 'Classical and modern symmetric ciphers share a secret key; modern symmetric keys require secure random generation and exchange. RSA shares a public key and protects a private key.'}


def rsa_demo(p, state):
    message = text(p, 'message').encode('utf-8')
    if len(message) > 190:
        raise ValueError('RSA-2048 OAEP/SHA-256 accepts at most 190 UTF-8 bytes. Use a short message.')
    private = keypair()
    encrypted = private.public_key().encrypt(message, oaep())
    recovered = private.decrypt(encrypted, oaep())
    wrong_rejected = False
    try:
        keypair().decrypt(encrypted, oaep())
    except ValueError:
        wrong_rejected = True
    return {'algorithm': 'RSA-2048 / OAEP / SHA-256', 'ciphertext_base64': base64.b64encode(encrypted).decode(),
            'recovered': recovered.decode('utf-8'), 'recovery_matches': recovered == message,
            'wrong_key_rejected': wrong_rejected, 'max_message_bytes': 190,
            'explanation': 'A fresh disposable 2048-bit key is generated per run. The public key encrypts; the private key decrypts and is not returned or saved. 2048 bits is a conventional laboratory baseline, not a guarantee for every long-term use.'}


def signatures(p, state):
    data = text(p, 'message').encode('utf-8')
    private = keypair()
    signature = private.sign(data, pss(), hashes.SHA256())
    return {'algorithm': 'RSA-PSS / SHA-256', 'signature_base64': base64.b64encode(signature).decode(),
            'document_sha256': hashlib.sha256(data).hexdigest(),
            'original_verified': verifies(private.public_key(), signature, data),
            'altered_document_verified': verifies(private.public_key(), signature, data + b' [altered]'),
            'wrong_key_verified': verifies(keypair().public_key(), signature, data),
            'explanation': 'A signature checks integrity and possession of a matching private key; it does not encrypt the document or independently prove a person\'s identity.'}


def packaging(p, state):
    password = text(p, 'password', limit=128)
    if len(password) < 12:
        raise ValueError('Use a disposable laboratory password of 12-128 characters.')
    secret = password.encode('utf-8')
    private = keypair()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ENIGMA disposable laboratory certificate')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=7)).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(private, hashes.SHA256()))
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(secret))
    bundle = pkcs12.serialize_key_and_certificates(b'enigma-lab', private, cert, None, serialization.BestAvailableEncryption(secret))
    restored = serialization.load_pem_private_key(pem, password=secret)
    restored12, cert12, _ = pkcs12.load_key_and_certificates(bundle, secret)
    wrong = b'deliberately-wrong-' + secrets.token_hex(16).encode('ascii')
    failures = []
    for loader, value in [(serialization.load_pem_private_key, pem), (pkcs12.load_key_and_certificates, bundle)]:
        try:
            loader(value, wrong)
            failures.append(False)
        except ValueError:
            failures.append(True)
    identifier = secrets.token_hex(16)
    folder = ROOT / state['id']
    folder.mkdir(parents=True, exist_ok=True)
    files = {'private-key.pem': pem, 'bundle.p12': bundle, 'certificate.pem': cert.public_bytes(serialization.Encoding.PEM)}
    links = {}
    for filename, data in files.items():
        path = folder / (identifier + '-' + filename)
        path.write_bytes(data)
        token = secrets.token_urlsafe(24)
        state['downloads'][token] = (path, filename)
        links[filename] = '/api/download/' + token
    public = private.public_key().public_numbers()
    return {'downloads': links, 'pkcs8_recovered': restored.public_key().public_numbers() == public,
            'pkcs12_recovered': restored12.public_key().public_numbers() == public and cert12.fingerprint(hashes.SHA256()) == cert.fingerprint(hashes.SHA256()),
            'wrong_password_rejected_pkcs8': failures[0], 'wrong_password_rejected_pkcs12': failures[1],
            'certificate_sha256': cert.fingerprint(hashes.SHA256()).hex(), 'valid_until': cert.not_valid_after_utc.isoformat(),
            'standards': {'PKCS #1': 'RSA key format and algorithms', 'PKCS #8': 'Private-key storage; encrypted here', 'PKCS #11': 'Interface for cryptographic tokens; not implemented by this simulation', 'PKCS #12': 'Password-protected key and certificate bundle'},
            'warning': 'Self-signed test certificate: not trusted identity evidence. Only encrypted private-key artifacts are saved. Keep your disposable password locally; it is not saved. Downloads require this browser session. Server restart discards access links.'}


def audit(state, event, success):
    state['audit'].append({'timestamp': datetime.now(timezone.utc).isoformat(), 'event': event, 'success': success, 'mode': 'software simulation'})
    state['audit'] = state['audit'][-100:]
    atomic_json(ROOT / state['id'] / 'audit.json', state['audit'])


def authentication(p, state):
    action = text(p, 'action', 'authenticate')
    identity = text(p, 'identity', limit=80).strip()
    pin = text(p, 'pin', limit=12)
    if action == 'audit':
        return {'audit': state['audit'], 'mode': 'Software smart-card simulation — not hardware or PKCS #11'}
    if action == 'enroll':
        if state.get('token'):
            raise ValueError('A token is already enrolled in this session. Restart the server or use a separate browser session for a new lab.')
        if not identity or not pin.isascii() or not pin.isdigit() or not 4 <= len(pin) <= 12:
            raise ValueError('Provide a fictional identity and a disposable PIN containing 4-12 ASCII digits.')
        state['token'] = {'identity': identity, 'pin_hash': generate_password_hash(pin), 'key': keypair(), 'failures': 0}
        audit(state, 'token_enrolled', True)
        return {'enrolled': True, 'mode': 'Software smart-card simulation', 'note': 'PIN hash and private key remain in server memory. Restart resets enrollment. This is not real hardware protection.'}
    token = state.get('token')
    if not token:
        raise ValueError('Enroll a fictional identity and disposable PIN first.')
    if action == 'challenge':
        nonce = secrets.token_bytes(32)
        state['challenge'] = {'bytes': nonce, 'expires': time.monotonic() + 60}
        audit(state, 'challenge_issued', True)
        return {'challenge_base64': base64.b64encode(nonce).decode(), 'expires_in_seconds': 60, 'note': 'One use only. Select Authenticate to consume it.'}
    if action != 'authenticate':
        raise ValueError('Unknown authentication action.')
    challenge = state.pop('challenge', None)
    if challenge is None or challenge['expires'] < time.monotonic():
        audit(state, 'challenge_missing_or_expired', False)
        return {'authenticated': False, 'reason': 'Request a fresh challenge. Challenges expire after 60 seconds and are consumed on every attempt.', 'audit': state['audit']}
    if token['failures'] >= 5:
        audit(state, 'token_locked', False)
        return {'authenticated': False, 'reason': 'Laboratory token locked after five consecutive failed attempts. Restart the server to reset.', 'audit': state['audit']}
    pin_matches = check_password_hash(token['pin_hash'], pin)
    if identity != token['identity'] or not pin_matches:
        token['failures'] += 1
        audit(state, 'identity_or_pin_rejected', False)
        return {'authenticated': False, 'reason': 'Identity or PIN rejected.', 'audit': state['audit']}
    test = text(p, 'test', 'normal')
    if test not in ('normal', 'altered', 'wrong_key'):
        raise ValueError('Choose normal, altered, or wrong_key.')
    data = challenge['bytes']
    signature = token['key'].sign(data, pss(), hashes.SHA256())
    public = keypair().public_key() if test == 'wrong_key' else token['key'].public_key()
    valid = verifies(public, signature, data + b'altered' if test == 'altered' else data)
    token['failures'] = 0 if valid else token['failures'] + 1
    audit(state, 'challenge_verified' if valid else 'signature_rejected', valid)
    return {'authenticated': valid, 'test': test, 'signature_verified': valid, 'audit': state['audit'],
            'mode': 'Software smart-card simulation', 'limits': 'No secure element, hardware PIN enforcement, PKCS #11 device, trusted identity proofing, or production access control. Audit files are local evidence, not tamper-proof logs.'}


HANDLERS = {'analysis': analysis, 'classical': classical, 'rsa': rsa_demo, 'signatures': signatures, 'packaging': packaging, 'authentication': authentication}


def run_task(task_id, payload, state):
    return {'status': 'ok', 'task': task_id, **HANDLERS[task_id](payload, state)}
