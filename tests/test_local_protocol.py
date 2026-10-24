import base64
from datetime import datetime, timezone
import os

import httpx
import pytest

from local_store import SkillError, operation_lock, read_private, save_state, write_private
from protocol import (Gateway, GatewayError, ORIGIN, UnknownOutcome, decode_multikey,
                      load_key, new_key, public_key, sign_challenge)

RID = 'dmd_did_intent_' + '0' * 26
NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def challenge(key):
    controller = public_key(key)
    return {
        'challenge_id': 'dmd_challenge_' + '1' * 26, 'registration_intent_id': RID,
        'controller': controller, 'signature_algorithm': 'ed25519',
        'signature_encoding': 'base64url (base64 and hex are also accepted)',
        'expires_at': '2026-10-24T00:05:00Z',
        'proof_url': ORIGIN + '/v1/dids/registrations/' + RID + '/controller-proofs',
        'message': '\n'.join(['DebitMyData controller proof', 'Audience: ' + ORIGIN,
            'Purpose: did_registration', 'Registration: ' + RID, 'Controller: ' + controller,
            'Nonce: nonce-with-spaces  ', 'Issued: 2026-10-24T00:00:00Z',
            'Expires: 2026-10-24T00:05:00Z'])}


def test_key_roundtrip_and_no_overwrite(private_dir, capsys):
    path = private_dir / 'controller.pem'
    pub = new_key(path)
    original = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    key = load_key(path)
    assert decode_multikey(pub.removeprefix('ed25519:')) == key.public_key().public_bytes_raw()
    with pytest.raises(FileExistsError):
        new_key(path)
    assert path.read_bytes() == original
    assert capsys.readouterr().out == ''


def test_exact_challenge_signature(private_dir):
    path = private_dir / 'key.pem'
    new_key(path)
    key = load_key(path)
    value = challenge(key)
    signature = sign_challenge(value, RID, key, now=NOW)
    assert '=' not in signature
    raw = base64.urlsafe_b64decode(signature + '==')
    assert len(raw) == 64
    key.public_key().verify(raw, value['message'].encode())


@pytest.mark.parametrize('field,value', [
    ('registration_intent_id', 'wrong'), ('controller', 'wrong'),
    ('signature_algorithm', 'rsa'), ('signature_encoding', 'hex'),
    ('proof_url', 'https://evil.example/proof'), ('expires_at', '2026-10-23T00:00:00Z'),
    ('message', 'unrelated message')])
def test_challenge_binding_rejected(private_dir, field, value):
    path = private_dir / 'key.pem'
    new_key(path)
    key = load_key(path)
    c = challenge(key)
    c[field] = value
    with pytest.raises(SkillError):
        sign_challenge(c, RID, key, now=NOW)


def test_permissions_symlinks_hardlinks_and_repo(private_dir):
    p = private_dir / 'state.json'
    write_private(p, b'{}')
    p.chmod(0o644)
    with pytest.raises(SkillError):
        read_private(p)
    p.chmod(0o600)
    alias = private_dir / 'alias'
    alias.symlink_to(p)
    with pytest.raises(OSError):
        read_private(alias)
    os.link(p, private_dir / 'hardlink')
    with pytest.raises(SkillError):
        read_private(p)
    (private_dir / 'hardlink').unlink()
    (private_dir / '.git').mkdir()
    with pytest.raises(SkillError):
        read_private(p)


def test_atomic_state_and_lock(private_dir):
    p = private_dir / 'state.json'
    save_state(p, {'stage': 'new'}, replace=False)
    with operation_lock(p):
        with pytest.raises(SkillError, match='already running'):
            with operation_lock(p):
                pytest.fail('second writer acquired lock')
        save_state(p, {'stage': 'quoted'})
    assert read_private(p) == b'{"stage": "quoted"}'
    assert p.stat().st_mode & 0o777 == 0o600
    with operation_lock(p):
        pass


@pytest.mark.parametrize('url', [
    'https://evil.example/v1/discovery', '//evil.example/v1/discovery',
    ORIGIN + '@evil.example/v1/discovery', ORIGIN + ':443/v1/discovery',
    '/v1/staging/test-agent-keys', '/v1/staging/test-signatures',
    '/v1/../staging/test-payments', '/v1/%64iscovery', '/v1/discovery?extra=1'])
def test_transport_refuses_out_of_scope_before_network(url):
    def unexpected(request):
        pytest.fail('out-of-scope request reached transport')
    gateway = Gateway(transport=httpx.MockTransport(unexpected))
    try:
        with pytest.raises(SkillError):
            gateway.request('GET', url)
    finally:
        gateway.close()


def test_redirect_not_followed_and_error_redacted():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': 'https://evil.example'},
                              text='private upstream diagnostic')
    gateway = Gateway(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(GatewayError) as error:
            gateway.request('GET', '/v1/discovery')
        assert len(calls) == 1
        assert 'private upstream' not in str(error.value)
    finally:
        gateway.close()


def test_timeout_is_unknown_and_not_retried():
    calls = []
    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout('secret-path')
    gateway = Gateway(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(UnknownOutcome) as error:
            gateway.request('POST', '/v1/dids/registration-quotes', body={})
        assert len(calls) == 1
        assert 'secret-path' not in str(error.value)
    finally:
        gateway.close()
