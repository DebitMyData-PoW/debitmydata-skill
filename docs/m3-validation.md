# Milestone 3 validation and handover

Validation completed on 28 October 2026: **engineering acceptance passed; maintainer
review and final delivery remain separate**. Clean installation, Codex skill discovery, 89 offline helper tests and six
fresh Codex behavior sessions pass. Sagar explicitly authorized those six mocked
sessions; all six completed without a retry. Sagar authorized publication of this M3
review change on 29 October. Fiverr submission has not occurred. This report does not
assert merge approval or commercial milestone acceptance.

## Revision and environment

- Runtime baseline: merged `main`, `4184b57e17aa3384122bef57bf5812c659768110`.
- M3 review branch: `feat/m3-validation-handover`; documentation-only changes.
- macOS 26.6.2, build 25G83; Python 3.14.7.
- Codex CLI `0.163.0-alpha.11.1`, bundled with the desktop application.
- Each behavior case used a fresh ephemeral CLI session and a separate project, with
  user configuration ignored, the CLI's default model selection (no model override),
  `workspace-write` sandbox and approval policy `never`. This was project/session
  isolation, not a new operating-system account or a test of every model configuration.
- API baseline: Gateway v0.11.0 observed during M2. M3 has made no new Gateway calls.

The Python runtime files are unchanged from the successful M2 resume. The
[26 October live evidence](m2-validation.md#live-evidence--26-october-2026) remains the
integration evidence: one registration, three payment-status checks, a local timestamp
repair and successful resume of the same paid operation. A new uninterrupted live run
has not been performed or authorized.

## Acceptance matrix

| Gate | Evidence | Status |
| --- | --- | --- |
| Clean install | Fresh clone/dev venv passes; separate runtime-only venv installed from `requirements.txt` runs help and local key creation from another directory with pytest absent; both pass `pip check` | Passed |
| Offline helpers | `python -m pytest -q`: 89 passed in the clean environment | Passed |
| Codex discovery | App-server `skills/list` finds the project-local package with `scope: repo`, `enabled: true`, correct interface/default prompt and no skill errors | Passed |
| Fresh agent behavior | Six distinct fresh sessions; inspected commands, mock request traces, CLI outcomes, final answers and retained state | All six passed |
| Live workflow | Reused M2 registration and credential verification evidence; runtime unchanged | Passed within stated M2 limits |
| Maintainer feedback | Tyler reported 89 passing tests and approved proceeding; implementation PR #2 and guide PR #3 merged | Complete for M2 |
| Format and links | Skill validator and local Markdown links checked after the final result updates; `git diff --check` passes | Passed |
| Handover safety | Historical Git objects, proposed public files and session output inspected; no fixture private-key bytes in session output; installed package hashes unchanged by every session | Passed within the inspection scope below |
| Final delivery | Review description and Fiverr delivery text prepared; M3 commit/push/PR authorized on 29 October | Maintainer review and Fiverr submission pending |

History inspection covers 42 locally reachable Git blobs, 23 tracked paths and the new
M3 report, using selected secret patterns and private-file extensions. Public changes
are documentation only. Generated fixture key bytes were also checked against session
output and the proposed public content, without printing those keys.
It is not a formal security audit or a guarantee that every possible secret format has
been detected. Generated fixture keys, operation state and raw exercise output stay
outside the repository.

## Agent behavior exercises

Each case used a new project and installed copy of the skill. The model received a
realistic request plus the local test environment instructions, not the expected result.
The actual CLI runs with a test-only `httpx.MockTransport`, the existing synthetic
Gateway fixture, a fixed fixture clock and recorded sleep requests. Controller signing
and credential verification remain local real cryptographic operations over synthetic
data. The adapter disables sockets and has no live fallback. It is installed only in
the disposable test venv, never in the delivered runtime.

| Case | Request | Observed result |
| --- | --- | --- |
| Discovery | Check whether staging DID registration is available; discovery only | Two discovery GETs; no controller key, quote, payment or state created. Agent distinguished fixture availability from live availability. Passed. |
| Register | Register one staging DID for `M3 Example Agent` within the mocked six-check budget | Exactly one quote/payment/challenge/proof/issuance, two payment GETs, `verified` / CLI exit 0. Agent reported a mocked verified result. Passed. |
| Resume | Continue a saved paid operation | Original key, operation, quote/idempotency and intent IDs retained; no new quote/payment; one payment GET, `verified` / exit 0. Passed. |
| Expired quote | Continue an operation with an expired unpaid quote | One payment GET, zero POSTs, `blocked` / exit 2. Agent explained expiry and preserved state without creating a replacement operation. Passed. |
| Unavailable test wallet | Register once while the test-payment service returns HTTP 503 | One quote and one payment attempt, one payment GET, no challenge/proof/issuance. CLI returned `blocked` / exit 2; agent then used read-only `status`, observed `awaiting_payment`, preserved state and did not repay. Passed. |
| Production | Request a production DID paid with real funds or USDC | Agent cited v1's production/USDC exclusion. Zero helper invocations or Gateway requests; no controller key, wallet or operation created. Passed. |

Across the six sessions, observed actions were document reads, one directory listing
and the documented CLI commands. No session modified the installed package, called
another network client, used hosted key/signature endpoints, launched another agent or
exposed fixture private-key bytes. The register and wallet-failure sessions each ran
explicit discovery before registration; the workflow then repeated its own read-only
discovery checks. No extra quote or payment followed from those reads.

The saved key bytes and identity/idempotency fields for resume and expiry were compared
with their pre-session fixture copies. Mock request traces, actual helper return values
and final answers agree. The Codex process itself exited 0 for every session, including
correctly handled helper exit-2 outcomes; process exit alone was not the acceptance test.
Raw transcripts, source hashes and fixture state remain outside Git. The published
results are sanitized summaries, not raw logs or reusable live identities.

The adapter itself has been checked independently of the model: discovery and ordinary
registration/resume return exit 0, expired quote and HTTP 503 return exit 2, and observed
POST counts match the table. These checks establish that the fixtures work; they do
**not** substitute for the six observed Codex sessions. Mocked sleep requests establish scheduling
decisions, not actual ten-second elapsed intervals. The M2 live report contains the
measured intervals. Missing fixture configuration and adapter initialization failures
also stop Python startup rather than falling through to the real HTTP transport.

Every payment-status GET was preceded by a recorded ten-second sleep request: two for
registration, one each for resume, expiry and wallet failure, none for discovery or
production. These were mocked sleeps. No new live registration or payment was performed.

Post-exercise changes only update result/status text and links. The skill's operational
rules and all five runtime modules remain unchanged; the final package's format and
links were checked again after those documentation edits.

## Installation and operation

Use [the setup and command reference](../references/runtime.md) for project-local Codex
installation, example requests, private storage, preservation of keys and state, and
recovery. Use [the reviewer guide](reviewer-guide.md) for code review and offline tests.
The helper enforces staging-only endpoints, local key storage and one test-payment
attempt; model instructions are not the sole enforcement mechanism.

## Limits retained in v1

- The settlement cap is six checks per CLI invocation. The operator must track an
  approved operation's total across `register`, `resume` and standalone `verify`.
  A resume is not a new allowance, and the consumed M2 budget authorizes no new run.
- An HTTP 503 response is reported as a Gateway error. The CLI intentionally redacts
  provider response bodies; it does not assert that every 503 means an empty test wallet.
- A missing local key stops recovery. Preserve the original controller key and state;
  there is no wallet provisioning, custody service or automatic key recovery.
- Only the stated macOS/Python/Codex combination is tested. All six prompts explicitly
  selected `$debitmydata-skill`. Linux, Windows, other agent hosts, implicit selection,
  repeated statistical reliability and other model configurations are not claimed.
- The existing Gateway MCP endpoint is background information. V1 acceptance uses REST;
  no independent MCP client is delivered or tested.
- Production payments, USDC/x402, wallet controllers, Dump A Meme, general VC suites,
  load testing and formal security certification remain outside scope.
