"""Verify the observed staging credential profile, not arbitrary DID methods."""

from hashlib import sha256
import base58
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from local_store import SkillError
from protocol import ISSUER, NETWORK, ORIGIN, PARTICIPANT, RAIL, SERVICE_TITLE, decode_multikey, identifier
from protocol import require, timestamp, utcnow


def authorized_key(document, method_id, purpose):
    require(method_id in document[purpose], 'Verification method is not authorized.')
    methods = [m for m in document['verificationMethod'] if m['id'] == method_id]
    require(len(methods) == 1, 'Verification method missing or ambiguous.')
    method = methods[0]
    require(method['type'] == 'Multikey' and method['controller'] == document['id'],
            'Invalid verification method controller or type.')
    return decode_multikey(method['publicKeyMultibase'])


def jcs_hash(value):
    # The Gateway profile rejects floats; do not silently accept rounded numbers.
    def check(item):
        if isinstance(item, float):
            raise SkillError('Floating-point values are outside the Gateway credential profile.')
        if isinstance(item, dict):
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
    check(value)
    try:
        return sha256(rfc8785.dumps(value)).digest()
    except (ValueError, TypeError):
        raise SkillError('Credential cannot be canonicalized.') from None


def verify_proof(credential, issuer_document):
    proof = credential['proof']
    require(isinstance(proof, dict) and proof['type'] == 'DataIntegrityProof'
            and proof['cryptosuite'] == 'eddsa-jcs-2022'
            and proof['proofPurpose'] == 'assertionMethod', 'Unsupported credential proof.')
    method = proof['verificationMethod']
    public = authorized_key(issuer_document, method, 'assertionMethod')
    require(isinstance(proof['proofValue'], str) and proof['proofValue'].startswith('z'),
            'Invalid credential signature encoding.')
    try:
        signature = base58.b58decode(proof['proofValue'][1:])
    except ValueError:
        raise SkillError('Invalid credential signature encoding.') from None
    require(len(signature) == 64, 'Invalid credential signature length.')
    document = {k: v for k, v in credential.items() if k != 'proof'}
    config = {k: v for k, v in proof.items() if k != 'proofValue'}
    context = document['@context']
    if '@context' not in config:
        config['@context'] = context
    else:
        a = context if isinstance(context, list) else [context]
        b = config['@context'] if isinstance(config['@context'], list) else [config['@context']]
        require(a[:len(b)] == b, 'Credential proof context is incompatible.')
        document['@context'] = config['@context']
    digest = jcs_hash(config) + jcs_hash(document)
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, digest)
    except InvalidSignature:
        raise SkillError('Credential signature verification failed.') from None


def verify_registration(result, state, payment, subject_document, issuer_document, *, now=None):
    now = now or utcnow()
    identity = identifier(result['identity_id'], 'identity')
    credential_id = identifier(result['credential_id'], 'credential')
    suffix = identity.rsplit('_', 1)[1]
    did = ISSUER + ':agents:' + suffix
    require(result['registration_intent_id'] == state['registration_intent_id']
            and result['status'] == 'issued' and result['did'] == did,
            'Issued identity does not match the registration.')
    require(result['did_document_url'] == ORIGIN + '/agents/' + suffix + '/did.json'
            and result['identity_url'] == ORIGIN + '/v1/dids/' + identity
            and result['credential_url'] == ORIGIN + '/v1/credentials/' + credential_id,
            'Issued result URLs do not match its identifiers.')
    require(subject_document['id'] == did and issuer_document['id'] == ISSUER,
            'Unexpected subject or issuer DID document.')
    multikey = state['controller_public_key'].removeprefix('ed25519:')
    controller_id = did + '#' + multikey
    require(authorized_key(subject_document, controller_id, 'authentication') == decode_multikey(multikey),
            'DID controller does not match the local key.')
    require(controller_id in subject_document['assertionMethod'], 'DID controller cannot assert claims.')
    credential = result['credential']
    require(credential['issuer']['id'] == ISSUER and credential['id'] == result['credential_url'],
            'Credential issuer or ID mismatch.')
    require(credential['@context'] == ['https://www.w3.org/ns/credentials/v2']
            and credential['type'] == ['VerifiableCredential', 'DebitMyDataRegistrationCredential'],
            'Unexpected registration credential type or context.')
    verify_proof(credential, issuer_document)
    subject = credential['credentialSubject']
    require(subject['id'] == did and subject['displayName'] == state['display_name']
            and subject['participantType'] == PARTICIPANT, 'Credential subject mismatch.')
    controller = subject['controller']
    require(controller['type'] == 'Multikey' and controller['publicKeyMultibase'] == multikey
            and controller['proofOfControl'] == 'ed25519_challenge_signature',
            'Credential controller mismatch.')
    registration = subject['registration']
    quote = state['quote']
    require(registration['registrationIntentId'] == state['registration_intent_id']
            and registration['service'] == SERVICE_TITLE
            and registration['commercialPrice'] == quote['commercial_price']
            and registration['termsVersion'] == quote['terms_version'],
            'Credential registration claims mismatch.')
    paid = registration['payment']
    require(payment['status'] == 'settled' and paid['status'] == 'settled'
            and paid['paymentIntentId'] == payment['payment_intent_id'] == state['payment_intent_id']
            and payment['registration_intent_id'] == state['registration_intent_id']
            and paid['paymentOption'] == payment['payment_option'] == RAIL
            and paid['network'] == payment['network'] == NETWORK
            and paid['asset'] == payment['asset'] == 'DMD'
            and paid['amount'] == payment['amount_received'], 'Credential payment claims mismatch.')
    require(isinstance(paid['outputs'], list) and bool(paid['outputs'])
            and all(isinstance(o, str) and o.rsplit(':', 1)[0] in payment['transactions']
                    and o.rsplit(':', 1)[-1].isdigit() for o in paid['outputs']),
            'Credential payment outputs mismatch.')
    require(subject['entitlements'] == result['entitlements'] == ['dmd_did_holder'],
            'Registration entitlement mismatch.')
    issued = timestamp(result['issued_at'])
    # Signed credential dates use whole seconds; the API retains microseconds.
    signed_issued = issued.replace(microsecond=0)
    require(timestamp(controller['verifiedAt']) <= issued <= now
            and timestamp(credential['validFrom']) == signed_issued
            and timestamp(credential['proof']['created']) == signed_issued,
            'Credential validity timestamps mismatch.')
    if 'validUntil' in credential:
        require(now < timestamp(credential['validUntil']), 'Credential expired.')
    return {'outcome': 'verified', 'environment': 'staging', 'did': did,
            'registration_intent_id': state['registration_intent_id'],
            'payment_intent_id': state['payment_intent_id'], 'credential_id': credential_id}
