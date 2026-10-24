"""Fixed staging contract, local Ed25519 operations and bounded HTTP transport."""

import base64
import json
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

import base58
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from local_store import SkillError, read_private, write_private

ORIGIN = 'https://staging-api.debitmydata.io'
ISSUER = 'did:web:staging-api.debitmydata.io'
RAIL = 'dmd_pow_native'
NETWORK = 'dmd:regtest'
SERVICE = 'did_registration'
SERVICE_TITLE = 'DebitMyData Agentic DID Registration'
PARTICIPANT = 'autonomous_agent'
ULID = r'[0-9A-HJKMNP-TV-Z]{26}'


def require(condition, message):
    if not condition:
        raise SkillError(message)


def identifier(value, kind):
    require(isinstance(value, str) and re.fullmatch('dmd_' + kind + '_' + ULID, value),
            'Invalid or mismatched Gateway identifier.')
    return value


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(result.tzinfo is not None, 'Timestamp must include a timezone.')
        return result
    except (ValueError, TypeError, AttributeError):
        raise SkillError('Invalid Gateway timestamp.') from None


def utcnow():
    return datetime.now(timezone.utc)


def display_name(value):
    if isinstance(value, str):
        value = value.strip()
    require(isinstance(value, str) and 1 <= len(value) <= 100
            and not re.search(r'[\x00-\x1f\x7f]', value), 'Invalid display name.')
    return value


def public_key(key):
    raw = key.public_key().public_bytes_raw()
    return 'ed25519:z' + base58.b58encode(b'\xed\x01' + raw).decode('ascii')


def new_key(path):
    key = Ed25519PrivateKey.generate()
    data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    write_private(path, data)
    return public_key(key)


def load_key(path):
    try:
        key = serialization.load_pem_private_key(read_private(path), password=None)
    except (ValueError, TypeError):
        raise SkillError('Cannot load the local controller key.') from None
    require(isinstance(key, Ed25519PrivateKey), 'Controller key must be Ed25519.')
    return key


def decode_multikey(value):
    require(isinstance(value, str) and value.startswith('z'), 'Unsupported public key encoding.')
    try:
        raw = base58.b58decode(value[1:])
    except ValueError:
        raise SkillError('Invalid public key encoding.') from None
    require(len(raw) == 34 and raw[:2] == b'\xed\x01', 'Invalid Ed25519 public key.')
    return raw[2:]


def registration_path(rid):
    return '/v1/dids/registrations/' + identifier(rid, 'did_intent')


def sign_challenge(challenge, rid, key, *, now=None):
    now = now or utcnow()
    controller = public_key(key)
    identifier(challenge['challenge_id'], 'challenge')
    require(challenge['registration_intent_id'] == rid and challenge['controller'] == controller,
            'Challenge does not match this registration and controller.')
    require(challenge['signature_algorithm'] == 'ed25519' and challenge['signature_encoding'] in
            ('base64url', 'base64url (base64 and hex are also accepted)'),
            'Unsupported challenge signature contract.')
    require(challenge['proof_url'] == ORIGIN + registration_path(rid) + '/controller-proofs',
            'Challenge proof URL does not match this operation.')
    expiry = timestamp(challenge['expires_at'])
    require(now < expiry, 'Controller challenge expired.')
    message = challenge['message']
    require(isinstance(message, str), 'Invalid challenge message.')
    lines = message.split('\n')
    expected = ['DebitMyData controller proof', 'Audience: ' + ORIGIN,
                'Purpose: did_registration', 'Registration: ' + rid, 'Controller: ' + controller]
    require(len(lines) == 8 and lines[:5] == expected and lines[5].startswith('Nonce: ')
            and bool(lines[5][7:]) and lines[6].startswith('Issued: ')
            and lines[7].startswith('Expires: '), 'Unrecognized or mismatched challenge message.')
    require(timestamp(lines[7][9:]) == expiry and timestamp(lines[6][8:]) <= now < expiry,
            'Challenge message timestamps do not match.')
    return base64.urlsafe_b64encode(key.sign(message.encode('utf-8'))).decode().rstrip('=')


class GatewayError(SkillError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'Gateway HTTP {status}; reconcile operation status before retrying.')


class UnknownOutcome(SkillError):
    pass


class Gateway:
    def __init__(self, *, transport=None):
        self.client = httpx.Client(timeout=httpx.Timeout(20, connect=5), follow_redirects=False,
                                   trust_env=False, transport=transport)

    def close(self):
        self.client.close()

    def request(self, method, path, *, body=None, idempotency_key=None):
        url = ORIGIN + path if path.startswith('/') and not path.startswith('//') else path
        parts = urlsplit(url)
        require(parts.scheme == 'https' and parts.netloc == 'staging-api.debitmydata.io'
                and not parts.fragment and not parts.username and '%' not in parts.path
                and '\\' not in url and '..' not in parts.path.split('/'),
                'Only the fixed staging origin is allowed.')
        patterns = {
            'GET': [r'/v1/discovery', r'/v1/payment-options',
                    r'/v1/payments/dmd_payment_intent_' + ULID,
                    r'/v1/dids/registrations/dmd_did_intent_' + ULID,
                    r'/\.well-known/did\.json', r'/agents/' + ULID + r'/did\.json'],
            'POST': [r'/v1/dids/registration-quotes', r'/v1/staging/test-payments',
                     r'/v1/dids/registrations',
                     r'/v1/dids/registrations/dmd_did_intent_' + ULID + r'/controller-(challenges|proofs)']}
        require(any(re.fullmatch(p, parts.path) for p in patterns.get(method, [])),
                'Endpoint is outside the staging DID workflow.')
        require(not parts.query or (parts.path == '/v1/payment-options'
                                    and parts.query == 'service=did_registration'),
                'Unexpected query parameters.')
        headers = {'Accept': 'application/json'}
        if idempotency_key:
            require(bool(re.fullmatch(r'[A-Za-z0-9._:-]{16,128}', idempotency_key)),
                    'Invalid quote idempotency key.')
            headers['Idempotency-Key'] = idempotency_key
        try:
            with self.client.stream(method, url, json=body, headers=headers) as response:
                if response.status_code not in (200, 201):
                    raise GatewayError(response.status_code)
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    require(len(data) <= 1_048_576, 'Gateway response exceeds size limit.')
                result = json.loads(data)
                require(isinstance(result, dict), 'Expected a Gateway JSON object.')
                return result
        except httpx.TransportError:
            raise UnknownOutcome('Network outcome unknown; inspect saved operation status.') from None
        except (ValueError, UnicodeError):
            raise UnknownOutcome('Invalid Gateway JSON; operation outcome may be unknown.') from None

    def discover(self):
        discovery = self.request('GET', '/v1/discovery')
        options = self.request('GET', '/v1/payment-options?service=did_registration')
        require(discovery['credential_issuer'] == {
            'did': ISSUER, 'did_document_url': ORIGIN + '/.well-known/did.json'},
            'Unexpected staging issuer.')
        require(any(o['id'] == SERVICE and o['accepting_payments'] is True
                    for o in discovery['offers']), 'DID registration is unavailable.')
        require(any(o['id'] == RAIL and o['network'] == NETWORK and o['asset'] == 'DMD'
                    and o['status'] == 'enabled' for o in options['supported_payment_options']),
                'Native DMD test rail is unavailable.')
        return {'environment': 'staging', 'issuer': ISSUER, 'payment_option': RAIL,
                'network': NETWORK, 'commercial_fee': options['commercial_fee']}
