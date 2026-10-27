"""Public verification vectors; no private test keys are stored here.

W3C Data Integrity EdDSA Cryptosuites v1.0, B.3, Examples 29–39.
https://www.w3.org/TR/2025/REC-vc-di-eddsa-20250515/#representation-eddsa-jcs-2022
Copyright W3C, licensed under https://www.w3.org/copyright/document-license/
"""

import copy
from hashlib import sha256

import pytest

from local_store import SkillError
from verification import jcs_hash, verify_proof

PUBLIC = 'z6MkrJVnaZkeFzdQyMZu1cgjg7k1pZZ6pvBQ7XJPt4swbTQ2'
METHOD = 'did:key:' + PUBLIC + '#' + PUBLIC
CONTEXT = ['https://www.w3.org/ns/credentials/v2', 'https://www.w3.org/ns/credentials/examples/v2']
DOCUMENT = {'@context': CONTEXT, 'id': 'urn:uuid:58172aac-d8ba-11ed-83dd-0b3aef56cc33',
    'type': ['VerifiableCredential', 'AlumniCredential'], 'name': 'Alumni Credential',
    'description': 'A minimum viable example of an Alumni Credential.',
    'issuer': 'https://vc.example/issuers/5678', 'validFrom': '2023-01-01T00:00:00Z',
    'credentialSubject': {'id': 'did:example:abcdefgh', 'alumniOf': 'The School of Examples'}}
PROOF = {'type': 'DataIntegrityProof', 'cryptosuite': 'eddsa-jcs-2022',
    'created': '2023-02-24T23:36:38Z', 'verificationMethod': METHOD,
    'proofPurpose': 'assertionMethod', '@context': CONTEXT}
SIGNATURE = 'z2HnFSSPPBzR36zdDgK8PbEHeXbR56YF24jwMpt3R1eHXQzJDMWS93FCzpvJpwTWd3GAVFuUfjoJdcnTMuVor51aX'


def issuer():
    return {'id': 'did:key:' + PUBLIC, 'assertionMethod': [METHOD],
        'verificationMethod': [{'id': METHOD, 'type': 'Multikey',
            'controller': 'did:key:' + PUBLIC, 'publicKeyMultibase': PUBLIC}]}


def test_published_jcs_hashes_and_signature():
    assert jcs_hash(DOCUMENT).hex() == '59b7cb6251b8991add1ce0bc83107e3db9dbbab5bd2c28f687db1a03abc92f19'
    assert jcs_hash(PROOF).hex() == '66ab154f5c2890a140cb8388a22a160454f80575f6eae09e5a097cabe539a1db'
    signed = {**DOCUMENT, 'proof': {**PROOF, 'proofValue': SIGNATURE}}
    verify_proof(signed, issuer())
    tampered = copy.deepcopy(signed)
    tampered['credentialSubject']['alumniOf'] = 'Another School'
    with pytest.raises(SkillError, match='signature verification failed'):
        verify_proof(tampered, issuer())


def test_jcs_utf16_property_order():
    # UTF-16 orders the astral key before U+E000; Python code-point sorting does not.
    expected = '{"a":"value","😀":"astral","\ue000":"bmp"}'.encode()
    assert jcs_hash({'\ue000': 'bmp', '😀': 'astral', 'a': 'value'}) == sha256(expected).digest()


@pytest.mark.parametrize('value', [1.2, 2**54, {'nested': [float('nan')]}])
def test_non_profile_numbers_rejected(value):
    with pytest.raises(SkillError):
        jcs_hash(value)
