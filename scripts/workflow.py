"""One persisted registration, reconciled against server status on every resume."""

import hashlib
import json
from pathlib import Path
import time
import uuid

from local_store import SkillError, read_private, save_state
from protocol import (GatewayError, NETWORK, ORIGIN, PARTICIPANT, RAIL, SERVICE_TITLE,
                      UnknownOutcome, display_name, identifier, load_key, public_key,
                      registration_path, require, sign_challenge, timestamp, utcnow)
from verification import verify_registration

PENDING = {'created', 'awaiting_payment', 'detected', 'confirming', 'verified'}


def initial_state(name, key_file):
    name = display_name(name)
    key = load_key(key_file)
    public = public_key(key)
    return {'schema_version': 1, 'environment': 'staging', 'base_url': ORIGIN,
            'operation_id': str(uuid.uuid4()), 'display_name': name,
            'participant_type': PARTICIPANT, 'key_file': str(Path(key_file)),
            'controller_public_key': public,
            'public_key_fingerprint': hashlib.sha256(key.public_key().public_bytes_raw()).hexdigest(),
            'quote_request': {'display_name': name, 'participant_type': PARTICIPANT,
                              'controller_public_key': public, 'preferred_payment_option': RAIL},
            'quote_idempotency_key': str(uuid.uuid4()), 'quote_attempts': 0,
            'test_payment_attempted': False, 'challenge_request_attempted': False,
            'proof_attempted': False, 'issuance_attempted': False}


def load_state(path):
    state = json.loads(read_private(path))
    require(state['schema_version'] == 1 and state['environment'] == 'staging'
            and state['base_url'] == ORIGIN and state['participant_type'] == PARTICIPANT,
            'Unsupported operation state or environment.')
    require(display_name(state['display_name']) == state['display_name'], 'Saved display name is not normalized.')
    require(state['quote_request'] == {
        'display_name': state['display_name'], 'participant_type': PARTICIPANT,
        'controller_public_key': state['controller_public_key'], 'preferred_payment_option': RAIL},
        'Saved quote body does not match the operation.')
    if 'registration_intent_id' in state:
        identifier(state['registration_intent_id'], 'did_intent')
        identifier(state['payment_intent_id'], 'payment_intent')
        require(state['quote']['registration_intent_id'] == state['registration_intent_id']
                and state['quote']['payment_intent_id'] == state['payment_intent_id'],
                'Saved intent IDs do not match the quote.')
    return state


class Workflow:
    def __init__(self, gateway, path, state, *, now=utcnow, sleep=time.sleep):
        self.gateway, self.path, self.state = gateway, path, state
        self.now, self.sleep = now, sleep

    def save(self):
        save_state(self.path, self.state)

    def stage(self, name):
        self.state['stage'] = name
        self.save()

    def result(self, outcome, stage, next_action):
        result = {'outcome': outcome, 'environment': 'staging', 'stage': stage,
                  'next_action': next_action}
        for field in ('operation_id', 'registration_intent_id', 'payment_intent_id'):
            if field in self.state:
                result[field] = self.state[field]
        if 'issued_result' in self.state:
            result['did'] = self.state['issued_result'].get('did')
        return result

    def progress(self, *, for_execution=False):
        s = self.state
        result = self.gateway.request('GET', registration_path(s['registration_intent_id']))
        require(result['registration_intent_id'] == s['registration_intent_id']
                and result['display_name'] == s['display_name']
                and result['participant_type'] == PARTICIPANT
                and result['controller']['public_key'] == s['controller_public_key']
                and result['controller']['wallet_address'] is None,
                'Registration status does not match the saved operation.')
        payment = result['payment']
        require(payment and payment['payment_intent_id'] == s['payment_intent_id']
                and payment['payment_option'] == RAIL, 'Registration payment mismatch.')
        if for_execution:
            require(result['status'] in ('awaiting_payment', 'paid', 'issued'),
                    'Registration is closed, under review, or has an unsupported status.')
            require(result['controller']['proof_status'] in ('pending', 'verified'),
                    'Controller proof is rejected or has an unsupported status.')
        return result

    def payment(self):
        s = self.state
        result = self.gateway.request('GET', '/v1/payments/' + s['payment_intent_id'])
        require(result['payment_intent_id'] == s['payment_intent_id']
                and result['registration_intent_id'] == s['registration_intent_id']
                and result['payment_option'] == RAIL and result['network'] == NETWORK
                and result['asset'] == 'DMD'
                and result['amount_due'] == s['quote']['selected_payment_option']['amount'],
                'Payment status does not match the saved quote.')
        return result

    def quote(self):
        s = self.state
        require(s['quote_attempts'] < 2, 'Quote outcome remains unknown after its single replay.')
        self.stage('quote')
        s['quote_attempts'] += 1
        self.save()
        quote = self.gateway.request('POST', '/v1/dids/registration-quotes',
                                     body=s['quote_request'], idempotency_key=s['quote_idempotency_key'])
        # Preserve the returned quote before validation; malformed responses must not
        # cause a new logical registration on resume.
        s['quote'] = quote
        self.save()
        identifier(quote['registration_intent_id'], 'did_intent')
        identifier(quote['payment_intent_id'], 'payment_intent')
        rail = quote['selected_payment_option']
        require(quote['service'] == SERVICE_TITLE and rail['id'] == RAIL
                and rail['network'] == NETWORK and rail['asset'] == 'DMD'
                and quote['controller_proof_required'] is True,
                'Quote is outside the staging registration contract.')
        require(isinstance(rail['amount'], str) and isinstance(rail['amount_base_units'], str),
                'Quote monetary values must remain strings.')
        s['registration_intent_id'] = quote['registration_intent_id']
        s['payment_intent_id'] = quote['payment_intent_id']
        self.save()

    def run(self):
        s = self.state
        key = load_key(s['key_file'])
        require(public_key(key) == s['controller_public_key']
                and hashlib.sha256(key.public_key().public_bytes_raw()).hexdigest()
                == s['public_key_fingerprint'], 'Local key does not match this operation.')
        self.stage('discovery')
        self.gateway.discover()
        if 'issued_result' in s:
            return self.verify()
        if 'registration_intent_id' not in s:
            self.quote()
        progress = self.progress(for_execution=True)
        self.stage('payment')
        self.sleep(10)
        payment = self.payment()
        s['last_payment_status'] = payment['status']
        self.save()
        if payment['status'] not in PENDING | {'settled'}:
            return self.result('blocked', 'payment', 'Inspect abnormal payment status; do not repay.')
        if payment['status'] == 'awaiting_payment' and not s['test_payment_attempted']:
            require(self.now() < timestamp(s['quote']['expires_at']), 'Quote expired; do not pay.')
            s['test_payment_attempted'] = True
            self.save()
            try:
                paid = self.gateway.request('POST', '/v1/staging/test-payments',
                                            body={'payment_intent_id': s['payment_intent_id']})
                require(paid['payment_intent_id'] == s['payment_intent_id'], 'Test payment ID mismatch.')
            except UnknownOutcome:
                pass  # Reconcile without a second payment POST.
            except GatewayError as exc:
                if exc.status != 409:
                    raise
        if payment['status'] != 'settled':
            for _ in range(5):
                self.sleep(10)
                payment = self.payment()
                s['last_payment_status'] = payment['status']
                self.save()
                if payment['status'] == 'settled':
                    break
                if payment['status'] not in PENDING:
                    return self.result('blocked', 'payment', 'Inspect abnormal payment status; do not repay.')
            else:
                return self.result('pending', 'payment', 'Resume explicitly after settlement; do not repay.')
        progress = self.progress(for_execution=True)
        require(progress['payment']['status'] == 'settled', 'Registration has not observed settlement.')
        if progress['controller']['proof_status'] != 'verified':
            self.stage('controller_proof')
            if s['proof_attempted']:
                return self.result('blocked', 'proof', 'Proof was attempted but is not verified; diagnose before retrying.')
            if s['challenge_request_attempted'] and 'challenge' not in s:
                return self.result('blocked', 'challenge', 'Challenge response was lost; ask maintainer to reconcile.')
            if 'challenge' not in s or timestamp(s['challenge']['expires_at']) <= self.now():
                s['challenge_request_attempted'] = True
                self.save()
                # Delete an expired challenge before requesting a replacement so a
                # lost renewal response cannot cause another challenge on resume.
                s.pop('challenge', None)
                self.save()
                s['challenge'] = self.gateway.request('POST', registration_path(s['registration_intent_id'])
                                                      + '/controller-challenges', body={})
                self.save()
            signature = sign_challenge(s['challenge'], s['registration_intent_id'], key, now=self.now())
            s['proof_attempted'] = True
            self.save()
            try:
                proof = self.gateway.request('POST', registration_path(s['registration_intent_id'])
                    + '/controller-proofs', body={'challenge_id': s['challenge']['challenge_id'],
                                                 'signature': signature})
                require(proof['registration_intent_id'] == s['registration_intent_id']
                        and proof['status'] == 'verified', 'Controller proof was not verified.')
            except UnknownOutcome:
                pass
            except GatewayError as exc:
                if exc.status not in (409,):
                    raise
            progress = self.progress(for_execution=True)
            if progress['controller']['proof_status'] != 'verified':
                return self.result('blocked', 'proof', 'Controller proof remains unverified; inspect status.')
        require(progress['payment']['status'] == 'settled' and not progress['blockers'],
                'Registration prerequisites are not satisfied.')
        if 'issued_result' not in s:
            self.stage('issuance')
            s['issuance_attempted'] = True
            self.save()
            try:
                s['issued_result'] = self.gateway.request('POST', '/v1/dids/registrations',
                    body={'registration_intent_id': s['registration_intent_id']})
            except UnknownOutcome:
                # Repeat once only after checking authoritative prerequisites again.
                progress = self.progress(for_execution=True)
                require(progress['controller']['proof_status'] == 'verified'
                        and progress['payment']['status'] == 'settled' and not progress['blockers'],
                        'Issuance outcome unknown; prerequisites changed.')
                s['issued_result'] = self.gateway.request('POST', '/v1/dids/registrations',
                    body={'registration_intent_id': s['registration_intent_id']})
            self.save()
        return self.verify(payment=payment)

    def verify(self, *, payment=None):
        s = self.state
        require('issued_result' in s, 'No saved issued result to verify.')
        self.stage('verification')
        try:
            result = s['issued_result']
            payment = payment if payment is not None else self.payment()
            subject = self.gateway.request('GET', result['did_document_url'])
            issuer = self.gateway.request('GET', ORIGIN + '/.well-known/did.json')
            verified = verify_registration(result, s, payment, subject, issuer, now=self.now())
            s['verification'] = {'outcome': 'verified', 'checked_at': self.now().isoformat()}
            self.save()
            return verified
        except (SkillError, KeyError, TypeError, ValueError):
            s['verification'] = {'outcome': 'issued_unverified', 'checked_at': self.now().isoformat()}
            self.save()
            return self.result('issued_unverified', 'verification',
                               'Preserve the key and issued result; diagnose verification without registering again.')
