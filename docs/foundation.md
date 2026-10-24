# Milestone 1 foundation

Status: ready for maintainer review after the checks recorded in
[foundation-validation.md](foundation-validation.md). Runtime helpers are not implemented.
This document makes implementation decisions; the live integration is not yet validated.

## Scope and milestone gates

| Milestone | Deliverable | Gate |
| --- | --- | --- |
| M1 | Skill scaffold, contract, local state/recovery design, test plan and source review | Valid structure, reconciled sources and reviewable decisions; maintainer feedback pending |
| M2 | REST client, local keys/signing, verification and offline tests | Agreed minimal staging run resolves DID and verifies credential |
| M3 | Codex behavior checks, installation/troubleshooting docs and handover | Clean setup, agreed tests/evidence and resolved in-scope review feedback |

V1 is Codex-first staging DID registration only. It excludes production payments,
wallet custody/provisioning, USDC/x402, Dump A Meme, other services, Gateway development,
deployment, independent MCP implementation, bulk testing and scheduled operation.

The maintainer owns Gateway behavior, availability and merge decisions. The skill
contributor owns client instructions/helpers, tests and evidence. Backend defects are
reported rather than silently worked around by weakening validation.

## Source baseline — 23 October 2026

| Source | Observed baseline |
| --- | --- |
| Skill repository | `8913bc778167d78823dfbd042627d234e122206c` on `main`; README and .gitignore only |
| Gateway reference | `a0ad5d92c8aacb024d0e4b2d107da5074a8e0042` on `main` |
| Staging OpenAPI | Version `0.6.0`; SHA-256 `5dfa0344453426ece594d47f0187f70b91f87e1b13bf9646dc3bcb0d9af04b56` |
| Public discovery/payment options | Expected issuer `did:web:staging-api.debitmydata.io`; native rail enabled on `dmd:regtest` |

Read-only retrieval is evidence of those responses, not proof of an end-to-end run or
that the deployed server exactly matches the source commit. Record fresh baselines if
the contract changes during implementation.

Sources:

- [Original skill requirements](https://github.com/DebitMyData-PoW/debitmydata-skill/blob/8913bc778167d78823dfbd042627d234e122206c/README.md)
- [Live OpenAPI](https://staging-api.debitmydata.io/openapi.json)
- [Demo helper](https://github.com/DebitMyData-PoW/agent-gateway/blob/a0ad5d92c8aacb024d0e4b2d107da5074a8e0042/scripts/demo_agent.py)
- [Gateway cryptography](https://github.com/DebitMyData-PoW/agent-gateway/blob/a0ad5d92c8aacb024d0e4b2d107da5074a8e0042/src/dmd_gateway/identity/crypto.py)
- [Credential construction](https://github.com/DebitMyData-PoW/agent-gateway/blob/a0ad5d92c8aacb024d0e4b2d107da5074a8e0042/src/dmd_gateway/identity/credentials.py)
- [Controller proofs](https://github.com/DebitMyData-PoW/agent-gateway/blob/a0ad5d92c8aacb024d0e4b2d107da5074a8e0042/src/dmd_gateway/services/controller_proofs.py)
- [Idempotency](https://github.com/DebitMyData-PoW/agent-gateway/blob/a0ad5d92c8aacb024d0e4b2d107da5074a8e0042/src/dmd_gateway/services/idempotency.py)
- [Staging guide](https://github.com/DebitMyData-PoW/agent-gateway/blob/a0ad5d92c8aacb024d0e4b2d107da5074a8e0042/docs/staging.md)
- [W3C EdDSA cryptosuites](https://www.w3.org/TR/2025/REC-vc-di-eddsa-20250515/#eddsa-jcs-2022)
- [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785)

## Reconciliation and implementation decisions

1. The browser/PDF guide uses hosted key-generation/signing helpers. The skill README
   overrides that example for this client: keys and signatures stay local; only test
   payment uses a staging shortcut. Eight README stages versus nine browser stages is
   grouping of signing/proof and verification, not a missing operation.
2. The PDF suggests leaving Idempotency-Key empty. The agent client will use it because
   the live API documents exact quote replay; a repeat after a timeout must not create
   another intent. Persist the exact request and key before the POST.
3. Native test payment is the sole currently observed enabled rail. Discovery marketing
   text mentions other rails; it is not evidence they work. Price stays quote-driven.
4. `next_action: prove_wallet_control` names the controller-proof step in existing
   examples. V1 proves an Ed25519 controller key, not ownership of a payment wallet.
5. The demo's `sign` fallback trims a trailing newline from raw text. The skill will
   accept the JSON challenge and sign its exact message, with binding checks first.
6. `verify-credential` imports Gateway crypto modules and resolves an issuer taken from
   the credential. Do not treat this demo as the complete client trust policy: enforce
   fixed staging issuer/origin, assertion-key authorization, subject and run binding.
7. Gateway JCS code rejects floats and unsafe integers; monetary values are strings.
   Use an established canonicalization library compatible with the observed profile,
   not `json.dumps(sort_keys=True)` or a copied handwritten implementation.
8. A malformed proof and a well-encoded wrong proof differ: malformed encoding leaves
   the challenge open; a wrong signature consumes it. The client stops and diagnoses
   either case instead of guessing retries from HTTP 422 alone.

## Runtime and reuse decision

Use Python 3.12+ and a small CLI, initially in `scripts/debitmydata.py`. It is deliberately
absent in this foundation, so there are no dummy commands implying working execution.
Split modules only if signing/verification or transport complexity warrants it.

Planned dependency roles: `cryptography` for Ed25519/PEM; `httpx` for bounded REST requests
and mock transport; established RFC 8785 and base58 codecs for proof encoding. Candidate
packages `rfc8785` and `base58` require version/license/compatibility review in M2 before
pinning. Use `pytest` for offline behavior tests. No Gateway service, database, blockchain
node, MCP dependency or wallet SDK is needed for this client.

At the inspected commits, neither repository includes a tracked LICENSE/COPYING file
and the Gateway pyproject does not declare a license. No upstream implementation is
copied into this foundation. Default plan: implement protocol integration using reviewed
libraries and the published standards. Ask the maintainer to clarify intended licensing
before vendoring any Gateway helper. Do not add a license on the client's behalf.

The exact verifier approach is `eddsa-jcs-2022` only: validate proof suite/purpose and
issuer-authorized Multikey, apply the suite's proof configuration/context rules and JCS,
hash proof and document separately, and verify Ed25519 over their concatenation. Add
independent known-answer tests and run/subject binding checks. This is not a general
verifiable-credential engine or a claim of complete standards conformance.

## Planned CLI surface (not implemented)

| Command | Responsibility |
| --- | --- |
| `discover` | Read service and rail metadata only; no key or run-state creation |
| `new-key --key-file PATH` | Create local Ed25519 key exclusively; return public key only |
| `register --display-name NAME --key-file PATH --state-file PATH` | Start one requested staging operation, saving IDs and exact quote body before progressing |
| `status --state-file PATH` | Read authoritative status for saved IDs; no POSTs |
| `resume --state-file PATH` | Reconcile and continue the same requested operation within the finite recovery policy |
| `verify --state-file PATH --result-file PATH` | Verify saved issued result against expected run and staging documents; never pay/register |

Do not add a configurable production base URL, infinite retry switch or batch mode.
Only implemented/tested commands will be advertised when the M1 capability gate is removed.

## Local operation record

Caller supplies an absolute state-file path outside any Git checkout. A single operation
uses one controller key, one quote idempotency key and one registration/payment pair.
Use versioned JSON with these fields:

| Group | Fields and purpose |
| --- | --- |
| Identity | `schema_version`, `operation_id`, `environment`, `base_url`, `display_name`, `participant_type` |
| Key reference | `key_file`, `controller_public_key`, SHA-256 fingerprint of raw public bytes; never private bytes |
| Quote | Exact `quote_request`, `quote_idempotency_key`, `quote_attempted`, IDs and quote expiry/result |
| Progress | `registration_intent_id`, `payment_intent_id`, last observed states and check time |
| Ambiguity | `test_payment_attempted`, `challenge_request_attempted`, `proof_attempted`, `issuance_attempted`; written before each corresponding POST |
| Challenge | Challenge ID, exact message and expiry in restricted local state for same-operation reconciliation; no private key or signature persistence |
| Issuance | DID/identity/credential IDs and external result-file reference, if returned |
| Bounds | Payment-check count and challenge-renewal count for the invocation; do not auto-reset by self-invoking |

Store both state and optional result in the user-owned run directory outside the repo.
Create private files with exclusive creation for new operations; atomic replacement for
updates and a single-writer lock protect against partial/concurrent local writes. Proposed
initial support is POSIX (directory 0700, private files 0600). Reject symlink/private-file
permission problems and refuse key overwrite. No broad OS compatibility claim before tests.

On resume, verify local key/public-key association and fixed origin first, then refresh
server status. Unknown/missing IDs after a lost POST are not permission to repeat a payment
or challenge. Retain keys after completion; documented deletion is an operator decision.

## PR review questions and external gates

- Confirm one successful staging registration as the M2 smoke-test budget. Any additional
  live run will need a specific reason and agreement; all failure matrices remain offline.
- Confirm up to six payment-status checks, at least 10 seconds apart, then return pending.
  This is a proposed bounded wait, not an exception silently inferred from “no loops”.
- Confirm the staging issuer/network and descriptive signature-encoding response are the
  intended v1 contract, and notify us of API changes before M2 validation.
- Clarify repository/helper licensing if the team wants code reuse rather than the
  independent protocol client described above.

None of these pending decisions authorizes a live registration in M1. Offline M2 work
can proceed independently; the staging budget must be resolved before consuming test coins.
