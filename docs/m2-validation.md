# Milestone 2 implementation and validation

Status: offline implementation under review; **M2 is not complete**. The agreed live
registration smoke test is still pending. No test payment or DID registration has been
performed by this change.

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

The live OpenAPI now reports **0.7.0**, SHA-256
`6909749f0f2ae6f1a97d56243ff59062b311b1751be94bcfa9814dcb801fa083`.
The inspected upstream update is `5d067565fb1e234c01083d21c282d2ff8b5c2620`.
Compared with the M1 source baseline, it adds Base/USDC x402 payment behavior, optional
issuance/payment response fields and payment-option metadata. Identity/crypto and controller
proof source did not change in that comparison. The existing DMD branch retains its flow.
This skill still selects only `dmd_pow_native` on `dmd:regtest`; x402 remains outside scope.
Source inspection and schema comparison do not prove the deployed implementation matches Git.

The quote response's `service` is the display title, while discovery uses `did_registration`.
This difference is asserted in the implementation fixture. The response contract is not
inferred from OpenAPI field types alone.

## Dependencies and reuse

Direct dependencies are pinned in `requirements.txt`: cryptography 46.0.3 (Apache-2.0 OR
BSD-3-Clause), httpx 0.28.1 (BSD-3-Clause), base58 2.1.1 (MIT), rfc8785 0.1.4 (Apache-2.0).
pytest 8.4.2 (MIT) is a development dependency. Installed metadata was checked. These are
dependency license observations, not a license grant for this repository. No Gateway
implementation is vendored; integration code was written for the documented protocol.

## Remaining acceptance gates

1. Resolve the maintainer's proposed budget: one successful staging registration and at most
   six settlement checks spaced 10 seconds apart. PR #1 has no review/comments as of this check.
2. After approval, perform the Codex-driven smoke test, preserve its key/state privately and
   record sanitized IDs, versions, timestamps, DID/controller resolution and verified credential.
3. Diagnose any integration failure without automatically creating another registration.
4. Submit/review the implementation PR with an honest distinction between offline and live evidence.

M3 clean-session Codex behavioral exercises and final installation/handover review remain
separate work. No production, wallet provisioning, DumpAMeme, MCP-client or general VC-engine
support is claimed.
