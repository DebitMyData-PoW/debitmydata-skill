"""Synthetic Gateway transport: never falls back to the network."""

import base64
from datetime import datetime, timezone
from hashlib import sha256
import json

import base58
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from local_store import SkillError, save_state
from protocol import Gateway, NETWORK, ORIGIN, ISSUER, RAIL, UnknownOutcome, new_key, public_key
from workflow import Workflow, initial_state, load_state

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
DATE = NOW.isoformat()
EXPIRY = '2026-10-24T00:05:00+00:00'
RID = 'dmd_did_intent_' + '0' * 26
PID = 'dmd_payment_intent_' + '1' * 26
CID = 'dmd_credential_' + '2' * 26
IID = 'dmd_identity_' + '3' * 26
DID = ISSUER + ':agents:' + '3' * 26
CHID = 'dmd_challenge_' + '4' * 26


def resign(credential, key):
    """Independent fixture signer for ASCII/string-only data (no production helper)."""
    unsigned = {k: v for k, v in credential.items() if k != 'proof'}
    proof = {k: v for k, v in credential['proof'].items() if k != 'proofValue'}
    config = dict(proof)
    config.setdefault('@context', unsigned['@context'])
    # For this deliberately restricted fixture domain, sorted compact ASCII JSON is
    # canonical. Separate standard vectors test the production JCS implementation.
    def digest(value):
        return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).digest()
    proof['proofValue'] = 'z' + base58.b58encode(key.sign(digest(config) + digest(unsigned))).decode()
    credential['proof'] = proof


class FakeGateway:
    def __init__(self, state):
        self.state = state
        self.calls = []
        self.paid = False
        self.proved = False
        self.issued = False
        self.payment_status = None
        self.registration_status = None
        self.proof_status = None
        self.fault = None
        self.issuer_key = Ed25519PrivateKey.generate()
        self.issuer_multikey = public_key(self.issuer_key).removeprefix('ed25519:')
        self.quote = {'registration_intent_id': RID, 'payment_intent_id': PID,
            'service': 'DebitMyData Agentic DID Registration', 'commercial_price': {'currency': 'USD', 'amount': '25.00'},
            'selected_payment_option': {'id': RAIL, 'network': NETWORK, 'asset': 'DMD',
                'amount': '12.50000000', 'amount_base_units': '1250000000'},
            'controller_proof_required': True, 'expires_at': EXPIRY, 'terms_version': 'v1'}

    def document(self, did, multikey):
        method = did + '#' + multikey
        return {'id': did, 'verificationMethod': [{'id': method, 'type': 'Multikey',
                'controller': did, 'publicKeyMultibase': multikey}],
                'assertionMethod': [method], 'authentication': [method]}

    def issued_result(self):
        subject = {'id': DID, 'displayName': self.state['display_name'], 'participantType': 'autonomous_agent',
            'controller': {'type': 'Multikey', 'publicKeyMultibase': self.state['controller_public_key'][8:],
                'proofOfControl': 'ed25519_challenge_signature', 'verifiedAt': DATE},
            'registration': {'service': 'DebitMyData Agentic DID Registration', 'registrationIntentId': RID,
                'commercialPrice': self.quote['commercial_price'], 'termsVersion': 'v1',
                'payment': {'paymentIntentId': PID, 'paymentOption': RAIL, 'asset': 'DMD',
                    'network': NETWORK, 'amount': '12.50000000', 'outputs': ['txid:0'], 'status': 'settled'}},
            'entitlements': ['dmd_did_holder']}
        credential = {'@context': ['https://www.w3.org/ns/credentials/v2'],
            'id': ORIGIN + '/v1/credentials/' + CID,
            'type': ['VerifiableCredential', 'DebitMyDataRegistrationCredential'],
            'issuer': {'id': ISSUER, 'name': 'DebitMyData'}, 'validFrom': DATE,
            'credentialSubject': subject,
            'proof': {'type': 'DataIntegrityProof', 'cryptosuite': 'eddsa-jcs-2022',
                'proofPurpose': 'assertionMethod', 'verificationMethod': ISSUER + '#' + self.issuer_multikey,
                'created': DATE}}
        resign(credential, self.issuer_key)
        return {'registration_intent_id': RID, 'status': 'issued', 'identity_id': IID,
            'did': DID, 'did_document_url': ORIGIN + '/agents/' + '3' * 26 + '/did.json',
            'identity_url': ORIGIN + '/v1/dids/' + IID, 'credential_id': CID,
            'credential_url': credential['id'], 'credential': credential,
            'entitlements': ['dmd_did_holder'], 'issued_at': DATE}

    def __call__(self, request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body, dict(request.headers)))
        stage = path.rsplit('/', 1)[-1]
        fail = self.fault == stage
        if fail:
            self.fault = None
        if path == '/v1/discovery':
            result = {'credential_issuer': {'did': ISSUER, 'did_document_url': ORIGIN + '/.well-known/did.json'},
                      'offers': [{'id': 'did_registration', 'accepting_payments': True}]}
        elif path == '/v1/payment-options':
            result = {'commercial_fee': {'currency': 'USD', 'amount': '25.00'},
                      'supported_payment_options': [{'id': RAIL, 'network': NETWORK, 'asset': 'DMD', 'status': 'enabled'}]}
        elif path == '/v1/dids/registration-quotes':
            assert body == self.state['quote_request']
            assert request.headers['Idempotency-Key'] == self.state['quote_idempotency_key']
            result = self.quote
        elif path == '/v1/staging/test-payments':
            assert not self.paid, 'duplicate payment'
            assert body == {'payment_intent_id': PID}
            self.paid = True
            result = {'payment_intent_id': PID}
        elif path == '/v1/payments/' + PID:
            result = {'payment_intent_id': PID, 'registration_intent_id': RID,
                'payment_option': RAIL, 'network': NETWORK, 'asset': 'DMD',
                'status': self.payment_status or ('settled' if self.paid else 'awaiting_payment'),
                'amount_due': '12.50000000', 'amount_received': '12.50000000' if self.paid else '0.00000000',
                'transactions': ['txid'] if self.paid else []}
        elif path == '/v1/dids/registrations/' + RID:
            result = {'registration_intent_id': RID, 'display_name': self.state['display_name'],
                'status': self.registration_status or ('issued' if self.issued else 'paid' if self.paid else 'awaiting_payment'),
                'participant_type': 'autonomous_agent', 'controller': {
                    'public_key': self.state['controller_public_key'], 'wallet_address': None,
                    'proof_status': self.proof_status or ('verified' if self.proved else 'pending')},
                'payment': {'payment_intent_id': PID, 'payment_option': RAIL,
                            'status': self.payment_status or ('settled' if self.paid else 'awaiting_payment')},
                'blockers': [] if self.paid and self.proved else ['prerequisite'],
                'did': DID if self.issued else None, 'identity_id': IID if self.issued else None}
        elif stage == 'controller-challenges':
            assert self.paid
            controller = self.state['controller_public_key']
            message = '\n'.join(['DebitMyData controller proof', 'Audience: ' + ORIGIN,
                'Purpose: did_registration', 'Registration: ' + RID, 'Controller: ' + controller,
                'Nonce: random-nonce', 'Issued: ' + DATE, 'Expires: ' + EXPIRY])
            self.message = message
            result = {'challenge_id': CHID, 'registration_intent_id': RID, 'controller': controller,
                'message': message, 'signature_algorithm': 'ed25519', 'signature_encoding': 'base64url',
                'expires_at': EXPIRY, 'proof_url': ORIGIN + '/v1/dids/registrations/' + RID + '/controller-proofs'}
        elif stage == 'controller-proofs':
            assert body['challenge_id'] == CHID
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            raw_key = base58.b58decode(self.state['controller_public_key'][9:])[2:]
            Ed25519PublicKey.from_public_bytes(raw_key).verify(
                base64.urlsafe_b64decode(body['signature'] + '=='), self.message.encode())
            self.proved = True
            result = {'registration_intent_id': RID, 'status': 'verified'}
        elif path == '/v1/dids/registrations':
            assert self.paid and self.proved
            assert body == {'registration_intent_id': RID}
            self.issued = True
            result = self.issued_result()
        elif path == '/.well-known/did.json':
            result = self.document(ISSUER, self.issuer_multikey)
        elif path == '/agents/' + '3' * 26 + '/did.json':
            result = self.document(DID, self.state['controller_public_key'][8:])
        else:
            pytest.fail('Unexpected request ' + path)
        if fail:
            raise httpx.ReadTimeout('simulated lost response')
        return httpx.Response(201 if request.method == 'POST' else 200, json=result)


@pytest.fixture
def operation(private_dir):
    key = private_dir / 'key.pem'
    new_key(key)
    state = initial_state('Test Agent', key)
    path = private_dir / 'state.json'
    save_state(path, state, replace=False)
    fake = FakeGateway(state)
    gateway = Gateway(transport=httpx.MockTransport(fake))
    sleeps = []
    flow = Workflow(gateway, path, state, now=lambda: NOW, sleep=sleeps.append)
    yield flow, fake, sleeps
    gateway.close()


def resume(flow):
    return Workflow(flow.gateway, flow.path, load_state(flow.path), now=flow.now, sleep=flow.sleep)


def post_count(fake, suffix):
    return sum(method == 'POST' and path.endswith(suffix) for method, path, _, _ in fake.calls)


def test_full_registration_and_resume(operation):
    flow, fake, sleeps = operation
    result = flow.run()
    assert result['outcome'] == 'verified'
    assert result['did'] == DID
    assert resume(flow).run()['outcome'] == 'verified'
    for stage in ('registration-quotes', 'test-payments', 'controller-challenges', 'controller-proofs', 'registrations'):
        assert post_count(fake, stage) == 1
    assert all(s == 10 for s in sleeps)


@pytest.mark.parametrize('fault', ['test-payments', 'controller-proofs', 'registrations'])
def test_lost_mutation_response_reconciled(operation, fault):
    flow, fake, _ = operation
    fake.fault = fault
    assert flow.run()['outcome'] == 'verified'
    assert post_count(fake, 'test-payments') == 1
    assert post_count(fake, 'controller-proofs') == 1
    assert post_count(fake, 'registrations') == (2 if fault == 'registrations' else 1)


def test_lost_quote_replays_same_key_and_body(operation):
    flow, fake, _ = operation
    fake.fault = 'registration-quotes'
    with pytest.raises(UnknownOutcome):
        flow.run()
    assert resume(flow).run()['outcome'] == 'verified'
    quotes = [call for call in fake.calls if call[1].endswith('registration-quotes')]
    assert len(quotes) == 2 and quotes[0][2:] == quotes[1][2:]


def test_lost_challenge_stops_without_another_creation(operation):
    flow, fake, _ = operation
    fake.fault = 'controller-challenges'
    with pytest.raises(UnknownOutcome):
        flow.run()
    result = resume(flow).run()
    assert result['outcome'] == 'blocked' and result['stage'] == 'challenge'
    assert post_count(fake, 'controller-challenges') == 1
    assert post_count(fake, 'controller-proofs') == 0


@pytest.mark.parametrize('status', ['created', 'detected', 'confirming', 'verified'])
def test_pending_never_proves_and_checks_are_capped(operation, status):
    flow, fake, sleeps = operation
    fake.payment_status = status
    result = flow.run()
    assert result['outcome'] == 'pending'
    assert len(sleeps) == 6
    assert sum('/v1/payments/' in c[1] for c in fake.calls) == 6
    assert post_count(fake, 'controller-proofs') == 0


@pytest.mark.parametrize('status', ['failed', 'expired', 'underpaid', 'overpaid', 'reorged',
                                   'reversed', 'refunded', 'disputed', 'unknown'])
def test_abnormal_payment_never_repays(operation, status):
    flow, fake, _ = operation
    fake.payment_status = status
    assert flow.run()['outcome'] == 'blocked'
    assert post_count(fake, 'test-payments') == 0
    assert post_count(fake, 'controller-challenges') == 0


def test_wrong_key_on_resume_has_no_network_calls(operation, private_dir):
    flow, fake, _ = operation
    other = private_dir / 'other.pem'
    new_key(other)
    flow.state['key_file'] = str(other)
    with pytest.raises(SkillError, match='does not match'):
        flow.run()
    assert fake.calls == []


def test_expired_quote_never_pays(operation):
    flow, fake, _ = operation
    fake.quote['expires_at'] = '2026-10-23T00:00:00Z'
    with pytest.raises(SkillError, match='Quote expired'):
        flow.run()
    assert post_count(fake, 'test-payments') == 0


@pytest.mark.parametrize('status', ['rejected', 'cancelled', 'expired', 'under_review', 'unknown'])
def test_closed_registration_never_pays(operation, status):
    flow, fake, _ = operation
    fake.registration_status = status
    with pytest.raises(SkillError, match='Registration is closed'):
        flow.run()
    assert post_count(fake, 'test-payments') == 0


def test_x402_quote_is_out_of_scope(operation):
    flow, fake, _ = operation
    fake.quote['selected_payment_option'].update(id='usdc_base_x402', network='eip155:84532', asset='USDC')
    with pytest.raises(SkillError, match='outside the staging'):
        flow.run()
    assert post_count(fake, 'test-payments') == 0


@pytest.mark.parametrize('status', ['rejected', 'unknown'])
def test_rejected_controller_does_not_pay(operation, status):
    flow, fake, _ = operation
    fake.proof_status = status
    with pytest.raises(SkillError, match='Controller proof is rejected'):
        flow.run()
    assert post_count(fake, 'test-payments') == 0


def test_unknown_payment_remains_pending_without_repayment(operation):
    flow, fake, _ = operation
    flow.quote()
    flow.state['test_payment_attempted'] = True
    flow.save()
    assert resume(flow).run()['outcome'] == 'pending'
    assert post_count(fake, 'test-payments') == 0


@pytest.mark.parametrize('status', [409, 422, 429, 503])
def test_quote_error_does_not_pay_or_create_new_key(operation, status):
    flow, fake, _ = operation
    def handler(request):
        if request.url.path.endswith('registration-quotes'):
            return httpx.Response(status, json={'error': 'untrusted provider message'},
                                  headers={'Retry-After': '120'})
        return fake(request)
    gateway = Gateway(transport=httpx.MockTransport(handler))
    flow.gateway = gateway
    try:
        from protocol import GatewayError
        with pytest.raises(GatewayError):
            flow.run()
        assert post_count(fake, 'test-payments') == 0
        assert load_state(flow.path)['quote_idempotency_key'] == flow.state['quote_idempotency_key']
    finally:
        gateway.close()


def test_expired_saved_challenge_renews_once(operation):
    flow, fake, _ = operation
    flow.quote()
    fake.paid = True
    flow.state['test_payment_attempted'] = True
    flow.state['challenge_request_attempted'] = True
    flow.state['challenge'] = {'expires_at': '2026-10-23T00:00:00Z'}
    flow.save()
    assert flow.run()['outcome'] == 'verified'
    assert post_count(fake, 'controller-challenges') == 1


def test_wrong_proof_is_not_resubmitted(operation):
    flow, fake, _ = operation
    flow.quote()
    fake.paid = True
    flow.state['test_payment_attempted'] = True
    flow.state['proof_attempted'] = True
    flow.save()
    result = resume(flow).run()
    assert result['outcome'] == 'blocked' and result['stage'] == 'proof'
    assert post_count(fake, 'controller-proofs') == 0
    assert post_count(fake, 'controller-challenges') == 0


@pytest.mark.parametrize('endpoint,status', [('test-payments', 503), ('controller-proofs', 422)])
def test_failed_mutation_is_not_repeated_on_resume(operation, endpoint, status):
    flow, fake, _ = operation
    attempts = []
    def handler(request):
        if request.method == 'POST' and request.url.path.endswith(endpoint):
            attempts.append(request)
            return httpx.Response(status, json={'detail': 'provider diagnostics must remain private'})
        return fake(request)
    gateway = Gateway(transport=httpx.MockTransport(handler))
    flow.gateway = gateway
    try:
        from protocol import GatewayError
        with pytest.raises(GatewayError):
            flow.run()
        assert resume(flow).run()['outcome'] in ('blocked', 'pending')
        assert len(attempts) == 1
    finally:
        gateway.close()


def test_modified_saved_quote_body_rejected(operation):
    flow, fake, _ = operation
    flow.state['quote_request']['display_name'] = 'Changed name'
    flow.save()
    with pytest.raises(SkillError, match='Saved quote body'):
        load_state(flow.path)
    assert fake.calls == []


@pytest.mark.parametrize('tamper', ['signature', 'subject', 'issuer', 'controller', 'intent', 'payment',
                                  'entitlement', 'timestamp', 'context', 'authorization'])
def test_verification_failure_preserves_issued_result(operation, tamper):
    flow, fake, _ = operation
    assert flow.run()['outcome'] == 'verified'
    state = load_state(flow.path)
    credential = state['issued_result']['credential']
    subject = credential['credentialSubject']
    if tamper == 'signature':
        credential['proof']['proofValue'] = 'z' + base58.b58encode(b'\0' * 64).decode()
    elif tamper == 'subject':
        subject['id'] += 'wrong'
    elif tamper == 'issuer':
        credential['issuer']['id'] = 'did:web:evil.example'
    elif tamper == 'controller':
        subject['controller']['publicKeyMultibase'] = fake.issuer_multikey
    elif tamper == 'intent':
        subject['registration']['registrationIntentId'] += 'wrong'
    elif tamper == 'payment':
        subject['registration']['payment']['amount'] = '1'
    elif tamper == 'entitlement':
        subject['entitlements'] = ['admin']
    elif tamper == 'timestamp':
        credential['validFrom'] = '2030-01-01T00:00:00Z'
    elif tamper == 'context':
        credential['proof']['@context'] = ['https://evil.example']
    elif tamper == 'authorization':
        credential['proof']['verificationMethod'] += 'unauthorized'
    if tamper != 'signature':
        resign(credential, fake.issuer_key)  # A valid signature is insufficient.
    save_state(flow.path, state)
    check = resume(flow)
    assert check.verify()['outcome'] == 'issued_unverified'
    assert 'issued_result' in load_state(flow.path)
    assert post_count(fake, 'test-payments') == 1
    assert post_count(fake, 'registrations') == 1
