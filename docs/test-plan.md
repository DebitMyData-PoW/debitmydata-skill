# Acceptance test plan

Status: planned M2/M3 tests, not executed results. Foundation-only checks are recorded
separately in [foundation-validation.md](foundation-validation.md).

## M1 acceptance

- Dedicated clean checkout and feature branch; preserve original README requirements.
- Record immutable source baselines and live OpenAPI hash/version.
- Document key/signature/credential encoding, local storage, authoritative status,
  idempotency and finite recovery, with no undocumented runtime claims.
- Valid SKILL.md/YAML and resolvable local references. The scaffold clearly refuses
  execution until helpers are implemented; no API or wallet credentials are requested.
- No runtime helper, private key, `.env`, wallet, generated challenge or run state in Git.
- Review PR includes the pending staging budget, polling and reuse questions.

Maintainer review/acceptance is separate from contributor validation or PR creation.

## M2/M3 behavioral matrix

| ID | Scenario | Observable acceptance | Environment |
| --- | --- | --- | --- |
| K1 | Generate/reuse key | Correct codec and 32-byte public key; no private bytes in output; existing key never overwritten | Local temporary directory |
| K2 | Wrong/missing key on resume | No API mutation; explicit mismatch/blocker | Local + mocked HTTP |
| K3 | Local key/state safety | POSIX permissions, exclusive creation, symlink refusal, atomic state update and same-state concurrency rejection | Local temporary directory |
| C1 | Discovery request | GETs only; no key, quote, payment or run creation | Mocked HTTP |
| C2 | Invalid name/rail/origin/URL | No unauthorized request; fixed staging origin and test rail enforced including redirects | Mocked HTTP |
| Q1 | Quote response lost | Exact same body/key replay; no second logical quote; finite stop on repeated uncertainty/in-progress | Mocked HTTP |
| Q2 | Expired quote / changed body | No payment or automatic new quote; explicit new-attempt guidance | Mocked HTTP |
| P1 | Payment accepted but response lost | Reconcile state; no second test-payment POST | Mocked HTTP |
| P2 | Already paid/not awaiting payment | Inspect actual payment state; conflict is not assumed settled | Mocked HTTP |
| P3 | Pending statuses | No progression for verified/confirming; capped spaced GETs; returns pending without self-rescheduling | Mocked clock + HTTP |
| P4 | Abnormal status / wallet down | Stop, retain IDs, no remediation/re-payment or automatic maintainer email | Mocked HTTP |
| S1 | Valid challenge | Exact UTF-8 bytes including whitespace; Ed25519 signature valid and unpadded base64url | Local crypto known-answer case |
| S2 | Wrong audience/controller/intent/purpose/encoding | No signing or proof POST | Local + mocked HTTP |
| S3 | Challenge expiry / consumed proof | At most one renewal only when allowed; no blind repeat of consumed challenge | Mocked clock + HTTP |
| S4 | Lost challenge/proof response | Reconcile proof status; no uncontrolled new challenge; uncertain state reported honestly | Mocked HTTP |
| I1 | Settlement/proof prerequisite absent | No issuance call; report current blocker | Mocked HTTP |
| I2 | Lost issuance/already issued | Same registration intent; existing DID result recovered; no new quote/key/payment | Mocked HTTP |
| V1 | Valid credential | Verify suite/signature with issuer-authorized key and bind subject/controller/intent/payment/entitlement to run | Independently constructed synthetic fixture |
| V2 | Tampered credential/key/proof/context | Reject bad signature, unsupported suite, altered content and incorrect canonicalization | Local fixtures and known-answer vectors |
| V3 | Valid signature, wrong identity | Reject wrong issuer, subject, controller, registration/payment IDs, timestamps or entitlement | Local fixtures |
| V4 | Resolution/verification fails after issuance | `issued_unverified`; preserve result; no second registration/payment | Mocked HTTP |
| R1 | Interrupted workflow | Resume same IDs/key using fresh server state; checkpoints never treated as final proof | Mocked interruption at each boundary |
| A1 | User asks to register with M1 scaffold | Explain unavailable execution; no invented helper or mutation | Codex scaffold exercise |
| A2 | Implemented skill requests | Correct discovery-only, staging registration, status/resume and out-of-scope behavior | Codex with mocked helpers in M3 |
| H1 | Clean installation | Declared dependencies suffice; all helper references resolve | Fresh local environment in M3 |
| H2 | Handover safety | No tracked private keys/.env/wallet/state files; sanitized logs and PR diff | Local inspection |

Fixtures must be synthetic and labelled; generate temporary private test keys at test
time rather than commit them. Mock transport must have no live-network fallback. Use
independent signature/canonicalization vectors, not only a signer and verifier sharing
the same implementation. Tests must assert requests, outcomes and invariant violations,
not simply match documentation headings or implementation text.

## Minimal staging proposal — pending maintainer agreement

- Budget: one successful end-to-end registration using a locally generated test controller
  key. No real wallet/funds, hosted key helper or hosted signature helper.
- Wait proposal: first payment check after about 10 seconds, at least 10 seconds between
  checks, at most six per invocation. Stop pending at the cap; no automatic rerun.
- All negative, timeout, wrong-key, expiry, duplicate and retry cases run offline. Do not
  consume test coins to exercise a test matrix or to obtain a cleaner demo recording.
- Run only after local tests pass and the maintainer has agreed the budget/wait policy.
  If a failure requires another registration, stop, diagnose and obtain agreement first.
- Evidence: code/API versions, environment, timestamps, relevant IDs, stage outcomes,
  DID resolution/controller match and credential verification. No private bytes, local
  key paths or unnecessary raw response dumps in the public report.
- Pass: correct DID document resolves and credential verifies for the same registration
  and controller. HTTP success or a returned DID string alone is insufficient.
- Blocked: Gateway outage/defect, unavailable test coins, unresolved contract mismatch or
  unsuccessful verification. Capture the reason; do not mark the integration passed.

## Handover gate

M3 must distinguish format validation, offline helper tests, Codex behavior tests and
the single observed staging run. None substitutes for the others. Record failures and
limitations, the exact environment tested and the PR revision under test. Do not claim
production readiness, a security audit, general DID-method support or multi-host testing.
