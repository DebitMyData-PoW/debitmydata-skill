# Milestone 2 implementation and validation

Status: **M2 implementation, live acceptance and technical review complete**.
Implementation [PR #2](https://github.com/DebitMyData-PoW/debitmydata-skill/pull/2) and
reviewer-guide [PR #3](https://github.com/DebitMyData-PoW/debitmydata-skill/pull/3)
merged on 27 October 2026. In the message supplied by Sagar, Tyler reported reviewing
the scripts, tests and reviewer guide, with all 89 offline tests passing on his side.
That is maintainer feedback supplied in the conversation, not a formal GitHub review
record or confirmation of Fiverr delivery acceptance.
One DMD regtest registration completed with a verified DID and credential on 26 October.
The first invocation stopped before signing because the client's timestamp comparison
rejected fractional API timestamps. After an offline-tested fix, the same operation resumed
successfully, preserving its key, quote, payment and challenge. This was not a second
registration or an uninterrupted run of the final code.

Foundation PR #1 merged as `29206196c2307ee557e8cf77f3d5c02b5489a673`.
The base implementation is `0cc08849d292f97ea9ecbf33c1d6ee085d7f3346`; this revision
adds timestamp fixes, regression tests and the completed validation evidence. On 27 October
the user authorized committing/pushing these updates and reopening implementation
[PR #2](https://github.com/DebitMyData-PoW/debitmydata-skill/pull/2), which had previously
been closed at their request. PR #2 subsequently merged as
`3a996397253ba8510a520096db75d836b2fa9509`; PR #3 merged as
`4184b57e17aa3384122bef57bf5812c659768110`.

Tyler explicitly approved one complete DMD regtest registration and at most six payment-status
checks, at least 10 seconds apart, in the message supplied by the user on 26 October.
This superseded the earlier pending test gate. The single approved registration is now
complete; remaining unused checks do not authorize another registration.

## Implemented

- CLI: discovery, local Ed25519 key creation, registration, status, resume and verification.
- Private POSIX files, exclusive key/state creation, atomic state updates and single-writer locks.
- Fixed staging origin/endpoints, no redirects or environment proxy inheritance, bounded HTTP
  timeouts and response size, sanitized diagnostics, no hosted key/signature endpoints.
- Persisted quote idempotency; one payment attempt; bounded settlement checks; local exact-message
  proof signing; reconciliation and stop behavior for uncertain requests.
- DID/controller matching, issuer-authorized `eddsa-jcs-2022` verification and registration,
  payment, entitlement and timestamp binding. Issuance and verification are distinct outcomes.

Implementation adjustments from M1: helpers are split into local storage, protocol,
workflow and verification modules behind one CLI. The issued result lives in the same
restricted state file; `verify` needs only `--state-file`, avoiding duplicate result-file
coordination. HTTP 429 returns blocked immediately with no retry. The initial settlement
status read counts toward the six-check cap. No scheduling or batch interface exists.

## Evidence — 24 October 2026

- 83 offline pytest cases passed on macOS / Python 3.14.7, including a fresh virtual
  environment installed from `requirements-dev.txt` using locally cached packages.
- Official skill format validation, Python compilation and whitespace checks passed;
  all 20 local Markdown links resolve. These are separate from runtime evidence.
- Full synthetic registration and resume pass with exactly one quote/payment/challenge/proof/
  issuance on the ordinary path. Lost quote, payment, proof and issuance responses are exercised.
- Negative cases cover unavailable/out-of-scope requests, closed registrations, x402 quotes,
  pending/abnormal payment states, wrong keys, expired quotes/challenges, lost challenges,
  prior unverified proofs, HTTP 409/422/429/503 and credential tampering or incorrect bindings.
- Public W3C EdDSA JCS examples 29–39 match both published hashes and the published signature.
  No private vector key is included. UTF-16 property ordering and forbidden numeric values
  are checked separately. Synthetic credential signing does not call the production verifier
  or its canonicalization helper.
- Read-only `discover` passed against staging, returning the expected issuer and DMD regtest
  rail. This proves discovery only, not payment or registration.

## Contract refresh

Tyler reported v0.10.0, but the live OpenAPI retrieved on 26 October reports **0.11.0**,
SHA-256 `7276d18204debdcaa02bb4d230d09334499f6623f7fd571750a15f62ed6f32ff`.
The inspected upstream source is `c59188fee2053470d7b2925ee3ca38da1a4f055f`.
The prior M2 baseline was v0.7.0 at `5d067565fb1e234c01083d21c282d2ff8b5c2620`.

Compared with v0.7.0, the API adds wallet controller/network fields, `still_to_prove`,
donation discovery and a nullable purchase/registration association on payment responses.
The challenge selector now optionally accepts Ed25519 or EVM controllers; omitted selection
still chooses the sole declared Ed25519 key. Proof signature length limits broaden for
wallets. Issuance accepts an omitted intent only for x402 discovery; this client continues
to send its saved intent explicitly. Staging docs also accept forms, while agents still
send JSON. New quote limits return 429, already handled by stopping without retry.

Source comparison preserves the Ed25519 challenge text/encoding, DMD quote/payment flow,
key-only DID document and registration credential profile. Existing client checks require
non-null matching registration/payment IDs and omit all wallet fields. The request/response
additions did not require a new DMD flow. The live test uncovered a pre-existing client
timestamp precision bug; its fix is described below. USDC/x402, wallet controllers,
donations and pricing services are outside v1. Schema/source inspection alone does not prove deployment behavior.

The quote response's `service` is the display title, while discovery uses `did_registration`.
This difference is asserted in the implementation fixture. The response contract is not
inferred from OpenAPI field types alone.

## Dependencies and reuse

Direct dependencies are pinned in `requirements.txt`: cryptography 46.0.3 (Apache-2.0 OR
BSD-3-Clause), httpx 0.28.1 (BSD-3-Clause), base58 2.1.1 (MIT), rfc8785 0.1.4 (Apache-2.0).
pytest 8.4.2 (MIT) is a development dependency. Installed metadata was checked. These are
dependency license observations, not a license grant for this repository. No Gateway
implementation is vendored; integration code was written for the documented protocol.

## Live evidence — 26 October 2026

Host: macOS, Python 3.14.7. API: v0.11.0 in both OpenAPI and live discovery.
Only the fixed staging origin, native DMD regtest rail and locally generated Ed25519
controller were used. The quote was USD 25.00, payable with 25.00000000 **test DMD**;
this is observed staging data, not a production price or exchange-rate guarantee.

| Evidence | Observed result |
| --- | --- |
| Started / verified (UTC) | 16:37:45 / 16:40:01 |
| Registration intent | `dmd_did_intent_01M5WH6FP8SM1YGVTSZ0H32KDA` |
| Payment intent | `dmd_payment_intent_01M5WH6FP8AG6GQA9QRS96RWX2` |
| Credential | `dmd_credential_01M5WHAJ7HG2WS1AKC68YQ1DPN` |
| DID | `did:web:staging-api.debitmydata.io:agents:01M5WHAJ7HTH4G0KEAYTCF0802` |
| Quote / test payment / challenge / proof / issuance POSTs | Exactly one each across both invocations |
| Payment-status GETs | Three total; awaiting_payment, settled, settled |
| Spacing between payment GET starts | 10.920 seconds, 110.545 seconds |
| Other reads | Two discovery, two payment-options, five registration-progress, one subject DID, one issuer DID |
| Controller proof | Gateway returned verified; the same saved challenge was signed locally |
| DID resolution | Subject DID and authorized controller key matched the saved local public key |
| Credential | Issuer-authorized Ed25519/JCS signature and registration/payment/controller/entitlement/timestamp bindings verified |
| Final CLI outcome | `verified`, exit code 0 |

[Resolved subject DID document](https://staging-api.debitmydata.io/agents/01M5WHAJ7HTH4G0KEAYTCF0802/did.json).
The private run directory is outside Git with mode 0700; controller key and state files
are mode 0600. Key bytes never entered tool output, logs, API requests or this report.
Raw responses and a sanitized request timeline are retained privately. A local observation
harness called the CLI without replacing its HTTP or crypto implementation, prohibited a
second initial invocation, and guarded the cumulative six-check/10-second budget across
register and resume. No hosted key/signature endpoints, production endpoints or real funds
were used. No further network checks were needed after successful verification.

### Timestamp repair and regression evidence

The challenge text ended with `Expires: 2026-10-26T16:43:09Z`, while JSON `expires_at`
was `2026-10-26T16:43:09.400395Z`. Gateway source truncates signed dates to whole seconds,
whereas its API timestamps retain microseconds. The original exact comparison stopped
before proof submission. The same representation difference applies to credential
`validFrom` / proof `created` versus API `issued_at`.

The fix compares signed dates with the API time truncated to seconds, without changing
the signed message or credential. Signing stops at the earlier whole-second expiry;
verification still rejects future full-precision issuance times and wrong-second dates.
Two new regression cases failed before the fix; all **89 offline tests pass** afterward
in both the project environment and the separate clean environment. Official skill-format
validation, all 21 local Markdown links and whitespace checks also pass.
Six added cases cover exact-byte signing with fractional response expiry, wrong-second
expiry, the fractional tail after signed expiry, and precise issuance with matching or
mismatched signed dates. This is a client integration fix, not evidence of a v0.11 regression.

Runtime file hashes for the successful resume (SHA-256), on top of base commit `0cc0884`:

| File | Hash |
| --- | --- |
| `scripts/protocol.py` | `57263372019e521814cbf8ff0b5d90220a25f63fa998b534dd7af6af69a1cac1` |
| `scripts/verification.py` | `9f8efaf8cf87e31d57507e778d1ad5f855d25f27c0e1c8f19d15d9decea33613` |
| `scripts/workflow.py` | `70653be13270012349ca764fd9c73818764d6f894c267c29146b3dc2619091f1` |
| `scripts/local_store.py` | `82976dbe97550701cfe6ec9730fa23164d88c45a40a632dae191cc277c8ed675` |
| `scripts/debitmydata.py` | `c9e30d7184cd720083f53025b1de2af8531fb39db3686b48e507caeee62174cf` |

## Delivery boundary

Technical review is complete with no requested implementation changes in Tyler's supplied
response. Fiverr submission and commercial acceptance remain separate from this evidence.
[M3 clean-session Codex exercises and final installation/handover](m3-validation.md) are
tracked separately. No production, wallet provisioning, DumpAMeme, MCP-client or general VC-engine
support is claimed. A new uninterrupted live registration was deliberately not performed;
that would require another agreed test budget.
