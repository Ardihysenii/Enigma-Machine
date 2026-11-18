"""Teacher-only, disposable RSA-PSS document/drawing demonstration. No storage."""
import base64
import binascii
import hashlib
import json
import math
import re
import secrets
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import jsonify, request
import portal as p


def canonical(payload, require_drawing=False):
    if not isinstance(payload, dict) or set(payload) != {'version', 'document', 'drawing'} or type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('Unsupported document format.')
    document, strokes = payload['document'], payload['drawing']
    if not isinstance(document, str) or not document.strip() or len(document) > 2000:
        raise ValueError('Enter a fictional document of 1–2000 characters.')
    try:
        document.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Enter valid Unicode text.') from None
    if not isinstance(strokes, list) or len(strokes) > 40:
        raise ValueError('Use at most 40 drawing strokes.')
    count = 0
    for stroke in strokes:
        if not isinstance(stroke, list) or len(stroke) < 2:
            raise ValueError('Each stroke needs at least two points.')
        count += len(stroke)
        for point in stroke:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError('Invalid drawing point.')
            for value, limit in zip(point, (800, 240)):
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= limit:
                    raise ValueError('Drawing point outside the signature pad.')
    if count > 800 or (require_drawing and count < 2):
        raise ValueError('Draw a fictional signature using 2–800 points.')
    # Normalize coordinates so equivalent JSON numeric encodings verify identically.
    normalized = dict(version=1, document=document, drawing=[[[float(x), float(y)] for x,y in stroke] for stroke in strokes])
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def scheme():
    return padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)


def make_bundle(payload):
    content = canonical(payload, require_drawing=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return dict(payload=payload, signature=base64.b64encode(private.sign(content, scheme(), hashes.SHA256())).decode(), publicKey=pem.decode(), publicKeyFingerprint=hashlib.sha256(der).hexdigest(), algorithm='RSA-2048 / PSS / SHA-256 / 32-byte salt')


def check_bundle(data):
    if not isinstance(data, dict) or set(data) != {'payload', 'signature', 'publicKey', 'test'}:
        raise ValueError('Submit the document, drawing, signature, public key and test.')
    content = canonical(data['payload'])
    if data['test'] not in ('normal', 'wrong_key'):
        raise ValueError('Choose a supported verification test.')
    if not isinstance(data['signature'], str) or len(data['signature']) != 344 or not isinstance(data['publicKey'], str) or len(data['publicKey']) > 2000:
        raise ValueError('Invalid signature or public key.')
    try:
        signature = base64.b64decode(data['signature'], validate=True)
        public = serialization.load_pem_public_key(data['publicKey'].encode())
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise ValueError('Invalid signature or public key encoding.') from None
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size != 2048 or len(signature) != 256:
        raise ValueError('Use the disposable RSA-2048 demo key and signature.')
    if data['test'] == 'wrong_key':
        public = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    try:
        public.verify(signature, content, scheme(), hashes.SHA256())
        return True
    except InvalidSignature:
        return False


@p.endpoint(('professor',))
def authorize_legacy(connection, actor):
    cookie = request.cookies.get(p.cookie_name('csrf'), '')
    header = request.headers.get('X-CSRF-Token', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', cookie) or not secrets.compare_digest(cookie, header):
        return jsonify(error='Refresh the teacher workspace before signing.'), 403
    return None


def register(blueprint):
    @blueprint.post('/api/portal/signatures/sign')
    @p.endpoint(('professor',))
    def sign_document(connection, actor):
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'payload'}:
            raise ValueError('Submit a document and drawing payload only.')
        result = make_bundle(data['payload'])
        p.audit(connection, actor, 'document_demo_signed', True)
        return jsonify(**result, teacher=p.actor_json(actor), simulation=True)

    @blueprint.post('/api/portal/signatures/verify')
    @p.endpoint(('professor',))
    def verify_document(connection, actor):
        valid = check_bundle(request.get_json(silent=True))
        p.audit(connection, actor, 'document_demo_verified', valid)
        return jsonify(verified=valid, simulation=True, identityTrusted=False)
