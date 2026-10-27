# Registration contract and recovery

Status: contract implemented by the M2 helpers, tested offline and verified in one
approved staging registration. Source versions and implementation changes are recorded in
[the M2 report](../docs/m2-validation.md); the original baseline is in
[foundation.md](../docs/foundation.md).

## Fixed v1 context

| Field | Value |
| --- | --- |
| API origin | `https://staging-api.debitmydata.io` |
| Expected issuer DID | `did:web:staging-api.debitmydata.io` |
| Issuer document | `https://staging-api.debitmydata.io/.well-known/did.json` |
| Service | `did_registration` |
| Participant | `autonomous_agent` |
| Payment option / network | `dmd_pow_native` / `dmd:regtest` |
| Controller | Agent-generated Ed25519 key |

Discovery may mention future payment rails or say `accepting_payments: true`. On this
origin that describes staging availability, not real-payment readiness. Require the
specific test rail from payment options and quote; stop if it is absent or changes.

## REST progression

All paths below are relative to the fixed API origin. Validate opaque intent IDs
before using them in a path; do not accept a server-supplied arbitrary URL as a command.

| Stage | Request | Required result before proceeding |
| --- | --- | --- |
| Discover | `GET /v1/discovery` | DID service and expected issuer available |
| Rail | `GET /v1/payment-options?service=did_registration` | Enabled native DMD test rail |
| Quote | `POST /v1/dids/registration-quotes` | HTTP 201; registration/payment IDs, expected rail/network and unexpired quote |
| Test payment | `POST /v1/staging/test-payments` | HTTP 201 or reconciliation of an already-paid/uncertain outcome; response alone is not settlement |
| Settlement | `GET /v1/payments/{payment_intent_id}` | Same registration/payment IDs and `status: settled` |
| Challenge | `POST /v1/dids/registrations/{registration_intent_id}/controller-challenges` | HTTP 201; matching controller and registration, supported signature format, future expiry |
| Proof | `POST /v1/dids/registrations/{registration_intent_id}/controller-proofs` | HTTP 201 with `status: verified`, or verified controller status after reconciliation |
| Issue | `POST /v1/dids/registrations` | HTTP 201 for new issuance or 200 for the same already-issued registration |
| Resume/status | `GET /v1/dids/registrations/{registration_intent_id}` | Current controller/payment status, blockers, identity/DID if issued |
| Verify | Fetch returned `did_document_url` and the fixed issuer document | Correct subject/controller and valid credential proof bound to the same run |

Quote body: `display_name`, `participant_type`, `controller_public_key`,
`preferred_payment_option`. Display name is 1–100 characters and excludes ASCII control
characters. Do not send wallet fields, metadata or extra attributes without a defined use.
The helper strips leading/trailing whitespace before validating and saving the name,
matching Gateway normalization. Discovery identifies the service as `did_registration`,
but the quote's `service` field contains `DebitMyData Agentic DID Registration`.

Save a random UUID as `Idempotency-Key` before sending the quote. Its documented pattern
is `[A-Za-z0-9._:-]{16,128}`. Retry with the same key and exact body; a changed body gives
`422 idempotency_key_reused`. `409 request_in_progress` means the earlier request has not
finished, not that a new quote is needed.

Test-payment body: `payment_intent_id`. Proof body: `challenge_id`, `signature`.
Issuance body: `registration_intent_id`.

Quote and challenge durations are currently 15 and 5 minutes respectively. Use the
actual `expires_at` responses rather than a fresh local timer. Treat uncertain clock
alignment conservatively. Carry monetary strings/base-unit strings exactly; do not
calculate or round them using binary floating point.

## Controller key and challenge proof

- Private key: local Ed25519 key in PKCS8 PEM, never transmitted or committed.
- Public key: `ed25519:` + `z` + base58btc encoding of `0xed01 || public_key_bytes`,
  with exactly 32 public-key bytes. The `z` is the multibase prefix.
- Sign the JSON response's `message` as exact UTF-8 bytes, preserving all whitespace.
  Do not use the demo's raw-text/newline-trimming fallback in the skill.
- Before signing, check `registration_intent_id`, `controller`, `signature_algorithm`
  (`ed25519`), expiry and the message's audience/purpose/registration/controller binding.
  Expected audience is the fixed staging origin and purpose is `did_registration`.
  Validate without changing the bytes being signed; reject unfamiliar message layouts.
- Emit unpadded base64url of the 64-byte signature.
- The Gateway's signed challenge timestamps have whole-second precision, while JSON
  `expires_at` retains microseconds. Require the signed expiry to equal the JSON expiry
  truncated to seconds, and stop at the earlier signed deadline. Preserve message bytes.
- The current `signature_encoding` response is the descriptive string
  `base64url (base64 and hex are also accepted)`, not the literal `base64url` alone.
  Support this documented response while emitting only unpadded base64url; stop on an
  unrecognized encoding contract.
- Construct the proof endpoint from the known origin and registration ID; validate
  `proof_url` against that expected URL rather than following arbitrary destinations.

Do not call `/v1/staging/test-agent-keys` or `/v1/staging/test-signatures`. They are
browser demo conveniences, not skill shortcuts. The controller key is not a wallet.

## DID and credential verification requirements

The observed Gateway issues a `DataIntegrityProof` with cryptosuite `eddsa-jcs-2022`,
Ed25519 Multikey, and proof purpose `assertionMethod`. Credential proof signatures use
multibase base58btc; they are distinct from the controller proof's base64url signature.

The implementation must:

1. Validate the returned DID, document/credential IDs and URLs against the staging
   origin and expected identifier relationships. Refuse redirects to other origins.
2. Resolve the subject document and match its ID and authorized controller key to the
   locally selected key. Do not accept an unrelated key merely present in the document.
3. Resolve the expected issuer document from the fixed URL, match its DID, and ensure
   the proof's verification method is controlled by that issuer and authorized for
   `assertionMethod`. Validate key codec, length and proof purpose/suite.
4. Verify the credential's cryptographic proof using a reviewed JCS/Ed25519 path:
   canonicalized proof configuration and unsigned credential are SHA-256 hashed
   separately, then concatenated in proof-hash/document-hash order for verification.
   Follow the suite's context/proof-configuration rules; ordinary sorted JSON is not JCS.
5. Bind credential subject ID, display name, participant type, controller key,
   registration intent, payment intent/rail/network and settled claim to the saved run
   and authoritative API results. Check credential ID and returned `dmd_did_holder`
   entitlement. Validate applicable validity timestamps.
   Signed `validFrom` and proof `created` must equal API `issued_at` truncated to seconds;
   still require the full-precision API issuance time not to be in the future.
6. Report issuance separately from verification if any resolution, signature or binding
   check fails. No automatic new payment or registration to repair verification.

This verifies a staging registration credential. It is not proof of a human identity,
access to other DebitMyData services, independent trust in the issuer or production
readiness. No remote JSON-LD context loading is needed for the observed JCS suite.

## Recovery decisions

Server status is authoritative; use registration progress as well as payment status.
The client must not blindly retry all POSTs or treat all HTTP 409/422 errors alike.

| Event | Decision |
| --- | --- |
| Lost quote response | Replay exact request with saved idempotency key once; stop pending if still uncertain/in progress. |
| Changed payload with same key | Stop; never silently replace the key to bypass a conflict. |
| Quote expires before payment | Stop and offer a deliberate new attempt; no automatic quote/payment loop. |
| Test payment already paid/not awaiting payment | Check status; never interpret a conflict as settlement or a reason to pay again. |
| Lost test-payment response | Reconcile payment and registration status; if still uncertain, stop. No automatic second POST. |
| `created`, `awaiting_payment`, `detected`, `confirming`, `verified` | Pending; no proof/issuance progression until settled. Use only reviewed, capped read-only checks. |
| `settled` | Continue with the same registration intent. |
| Failed, expired, under/overpaid, reorged, reversed, refunded, disputed or unknown state | Stop and report; no financial remediation or re-payment. |
| Expired challenge | Refresh registration status; if eligible, at most one new challenge per invocation. Stop on a second expiry. |
| Wrong or malformed proof | Stop and diagnose locally. A wrong signature consumes the challenge; malformed encoding currently leaves it open. Neither warrants blind retries. |
| Lost proof response / already-used challenge | Read controller proof status; proceed only if verified. Otherwise stop with the observed blocker. |
| Lost challenge response | No challenge GET exists in the observed contract. Stop with an ambiguous-challenge outcome rather than create challenges repeatedly. |
| Lost issuance response | Read registration status; repeat issuance once for the same intent only when reconciliation warrants it. HTTP 200 returns the same issued result. |
| 429 | Respect Retry-After within the operation budget or return pending; no retry storm. |
| Test wallet unavailable / service down | Stop with sanitized diagnostics for the maintainer; do not reset the chain or email automatically. |
| Issued but verification fails | Report `issued_unverified`, preserve key/IDs/result, and diagnose without another registration. |

Tyler approved one DMD regtest registration with at most six payment-status checks,
at least 10 seconds apart. It completed on 26 October using three checks in total,
including resume. That approval is consumed. Future live tests require a new agreed
budget. The helper caps each invocation at six checks; the operator must also enforce
the total authorized budget across resume/verify invocations. No self-rescheduling or
batch runs. See [the test plan](../docs/test-plan.md).

## Output contract

Planned outcomes: `pending`, `blocked`, `issued_unverified`, `verified`.
Include environment, registration/payment IDs when known, last observed server state,
DID if issued, verification result and recommended next step. A network timeout is an
unknown outcome, not proof that the mutation failed. Keep private keys, raw debug dumps
and local filesystem details out of client-facing evidence.
