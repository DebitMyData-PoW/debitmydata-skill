# Tyler's implementation and testing guide

This guide explains the M2 implementation and how to review it from a fresh checkout.
Start with offline tests and read-only discovery. A new staging registration is a separate,
explicit test decision because staging test coins are limited.

Review: [PR #2](https://github.com/DebitMyData-PoW/debitmydata-skill/pull/2).
The validated implementation revision is `74204404492bca80c1c08e1bba1c50747a0b5d35`.
The API baseline observed on 26 October 2026 was **v0.11.0**. Later Gateway releases may
require another contract comparison; this version is an observation, not a live guarantee.

## 1. What is implemented

The skill gives Codex instructions for choosing the next action. A Python CLI performs
the HTTP requests, local signing, private state handling and verification. It uses the
existing REST Gateway; no new backend or MCP server is introduced.

| File | Responsibility |
| --- | --- |
| [SKILL.md](../SKILL.md) | Agent instructions, scope, authorization and stopping rules |
| [agents/openai.yaml](../agents/openai.yaml) | Codex skill display metadata and starter prompt |
| [scripts/debitmydata.py](../scripts/debitmydata.py) | CLI commands, JSON results and exit codes |
| [scripts/protocol.py](../scripts/protocol.py) | Fixed staging endpoints, discovery, key encoding and challenge signing |
| [scripts/local_store.py](../scripts/local_store.py) | Private files, exclusive creation, atomic state writes and operation locks |
| [scripts/workflow.py](../scripts/workflow.py) | Quote, payment, proof, issuance and recovery decisions |
| [scripts/verification.py](../scripts/verification.py) | DID/controller checks and Ed25519/JCS credential verification |
| [tests/](../tests/) | Offline transport, workflow, storage and cryptographic regression tests |

The workflow is:

1. Discover the DID service and enabled `dmd_pow_native` rail on `dmd:regtest`.
2. Load the locally generated Ed25519 key and save the exact quote request/idempotency key.
3. Obtain the quote, check current status, and attempt its staging test payment once.
4. Wait for `settled`, using at most six payment-status reads per invocation, each preceded
   by a 10-second delay. `verified` payment status is not sufficient.
5. Validate the controller challenge, sign its exact UTF-8 message locally and submit proof.
6. Confirm the prerequisites and request issuance for the same registration intent.
7. Resolve the subject and issuer DID documents, match the controller, and verify the
   credential signature plus its registration, payment, entitlement and timestamp claims.

The recovery model preserves the original key, IDs and state, then checks server status
before deciding whether to continue or stop. It does not restart registration after an error.
An Ed25519 controller key is not a payment wallet. No wallet, API key, real DMD, blockchain
node or `.env` file is needed for this staging version.

Production, USDC/x402, wallet controllers, donations, DumpAMeme and a separately tested
MCP client are outside this implementation. Protocol detail is in the
[registration reference](../references/registration.md).

## 2. Get the review branch and install dependencies

Use a fresh directory on macOS or Linux with Python 3.12+. The recorded test host was
macOS with Python 3.14.7; Windows support is not claimed. These commands use Git and Python:

```sh
git clone https://github.com/DebitMyData-PoW/debitmydata-skill.git debitmydata-skill-review
cd debitmydata-skill-review
git fetch origin pull/2/head
git switch --detach FETCH_HEAD
git rev-parse HEAD

python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/debitmydata.py --help
```

This checks out the PR head rather than `main`. Record the printed commit with your results;
the PR may advance beyond the validated revision. `requirements-dev.txt` includes the runtime
dependencies and pytest. Run the following commands from this checkout unless stated otherwise.

## 3. Run the offline tests first

```sh
.venv/bin/python -m pytest -q
```

Expected at revision `7420440`: **89 passed**. Tests use mock HTTP transports and temporary
keys; they do not contact staging or consume test coins. Dependency installation does
require access to the package source.

The suite covers full registration, recovery after lost responses, no duplicate payment,
wrong keys, expired/mismatched challenges, unsupported rails, status-check limits, HTTP
errors, private-file handling and credential tampering. Public W3C proof vectors provide
an independent cryptographic check alongside synthetic Gateway fixtures.

The timestamp regression can be reviewed separately:

```sh
.venv/bin/python -m pytest -q -k 'exact_challenge_signature or challenge_precision or credential_seconds'
```

Expected at that revision: seven selected cases pass. The Gateway signs whole-second dates
but returns fractional API timestamps. The fix compares the corresponding precision without
changing signed bytes, extending challenge expiry or accepting a different issuance second.

## 4. Check staging discovery without creating anything

```sh
.venv/bin/python scripts/debitmydata.py discover
```

This makes two GET requests: discovery and DID payment options. Expect JSON identifying
`environment: staging`, issuer `did:web:staging-api.debitmydata.io`, payment option
`dmd_pow_native` and network `dmd:regtest`, with exit code 0. Read the returned fee rather
than assuming a fixed amount. This command creates no key, quote, payment or DID.

If discovery is blocked or the expected rail is absent, stop before registration and
check the [Gateway docs](https://staging-api.debitmydata.io/docs).

## 5. Optional: authorize one new staging registration

The previously approved registration is already complete; its budget is consumed.
Tyler can authorize a separate reviewer test, specifying one registration and a total
payment-status budget. The commands below are instructions for that authorized test,
not a request to run another registration automatically.

For a six-check total budget, run `register` once and stop on any non-success outcome.
The CLI caps each invocation, but does not persist a cumulative check count across
invocations or expose a smaller-cap flag. Do not automatically call `resume` or `verify`
afterward. Any continuation needs an explicitly reviewed budget and, when necessary,
external request counting that enforces the remaining allowance.

Create one durable private directory outside every Git checkout. The example uses your
home directory; choose another location if your home directory itself is under Git.
Run this setup once, remember the directory, and keep the same shell variable for recovery:

```sh
DMD_REVIEW_RUN="$(mktemp -d "$HOME/dmd-review.XXXXXX")"
chmod 700 "$DMD_REVIEW_RUN"

.venv/bin/python scripts/debitmydata.py new-key \
  --key-file "$DMD_REVIEW_RUN/controller.pem"
```

`new-key` creates a mode-0600 private key locally and prints only its public key. It refuses
to overwrite a key. The next command performs the entire registration and verification:

```sh
.venv/bin/python scripts/debitmydata.py register \
  --display-name "Tyler-Skill-Review-01" \
  --key-file "$DMD_REVIEW_RUN/controller.pem" \
  --state-file "$DMD_REVIEW_RUN/registration.json"
```

Allow the command to finish. It can spend approximately a minute on the bounded settlement
wait, plus network request time. Do not start another copy while it is running.

Success is JSON with `outcome: verified`, `environment: staging`, the DID, registration ID,
payment ID and credential ID, with exit code 0. Verification happens inside `register`;
there is no need to call `verify` again after success. No private key is transmitted.
Keep the private key and state afterward; do not attach either file to a PR or message.

## 6. Interpret results and investigate safely

| Result | Meaning and next action |
| --- | --- |
| `verified` | DID/controller and credential checks passed; record the sanitized result and stop |
| `pending` | Settlement or a request outcome remains uncertain; preserve state and inspect before continuing |
| `blocked` | A prerequisite, response or local validation failed; diagnose without starting another registration |
| `issued_unverified` from registration/verification | Issuance is saved, but verification did not pass; preserve the result and investigate |

`pending`, `blocked` and `issued_unverified` return exit code 2. A timeout does not mean a
mutation failed. Do not delete state, replace the key, repay, or generate another quote
to bypass an error. The state file contains the issued credential when available; there
is no separate `--result-file` argument.

To inspect an existing operation without submitting another mutation:

```sh
.venv/bin/python scripts/debitmydata.py status \
  --state-file "$DMD_REVIEW_RUN/registration.json"
```

`status` reads registration progress, not the payment-status endpoint. It reports payment
and proof status but does not verify cryptography. It can therefore return
`issued_unverified` even when an earlier `register` verified successfully; that status
output alone does not indicate a new verification failure.

The following are alternative follow-up commands, not a sequence to run by default:

```sh
# Only after reviewing the failure and authorizing the continuation budget:
.venv/bin/python scripts/debitmydata.py resume \
  --state-file "$DMD_REVIEW_RUN/registration.json"

# Only for a saved issued result and an authorized additional payment-status read:
.venv/bin/python scripts/debitmydata.py verify \
  --state-file "$DMD_REVIEW_RUN/registration.json"
```

`resume` can continue mutations on the same operation. `verify` makes only GET requests
and records verification locally, but uses one additional payment-status read. Preserve
at least 10 seconds between payment reads when that is the agreed policy. The full recovery
rules and file-permission requirements are in [runtime instructions](../references/runtime.md).

## 7. Review through Codex

Open the checkout in Codex and use this initial prompt:

> Read SKILL.md and docs/reviewer-guide.md. Explain the staging DID implementation,
> run the offline tests, and perform read-only discovery. Do not create a controller key,
> quote, payment or registration. Report the commit, test results and discovery outcome.

If you choose a new live test, provide its display name, private run directory and explicit
budget in a separate instruction. For example:

> I authorize one staging DMD regtest registration named Tyler-Skill-Review-01, using a
> new local Ed25519 controller key outside Git. Use at most six payment-status checks,
> at least 10 seconds apart. Run the registration command once. Stop on a non-success
> outcome; do not resume, verify again or create another registration without my review.
> Report the sanitized outcome and preserve the key and state locally.

This exercises the checkout's instructions and helper; formal clean-session skill
installation, invocation and behavior testing are tracked in the
[M3 acceptance report](m3-validation.md).

## 8. What to send back in the review

- Commit, OS, Python version, command tested and offline test summary.
- For an authorized live run: UTC times, public intent IDs, final outcome and DID if issued.
  Include payment-check counts only if measured; the normal CLI does not print a request trace.
- Any mismatch in request/response fields, controller proof, credential bindings or recovery.
- Sanitized error text and the expected behavior; exclude keys, `.env`, raw state and private paths.

Existing evidence is in [M2 validation](m2-validation.md): one registration completed on
26 October with one quote/payment/challenge/proof/issuance and three payment-status reads,
spaced 10.920 and 110.545 seconds. It resumed the same paid operation after the timestamp
fix; it was not an uninterrupted run of the final code. A repeat run is not required merely
to obtain cleaner evidence. Maintainer review and client acceptance remain separate from
the recorded technical results.
