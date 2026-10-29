# Staging helper setup and commands

The M2 implementation and reviewer guide have merged. One approved registration
completed with verified DID and credential; see [the report](../docs/m2-validation.md).
The examples below are instructions, not authorization for another live test.

## Install locally

Requirements: Python 3.12 or later, POSIX filesystem permissions and `flock` (macOS/Linux).
Validated on macOS with Python 3.14.7; Linux and Windows have not been tested.

For a project-local Codex installation, run these commands from the project where
you want to use the skill. The destination must not already exist:

```sh
mkdir -p .agents/skills
git clone https://github.com/DebitMyData-PoW/debitmydata-skill.git .agents/skills/debitmydata-skill
cd .agents/skills/debitmydata-skill
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/debitmydata.py --help
```

Start a new Codex session in the enclosing project after installation. Confirm that
`debitmydata-skill` appears in its available skills, then try:

> Use $debitmydata-skill to check staging DID registration availability. Discovery only;
> do not create a key, quote, payment or registration.

Discovery makes read-only requests to staging. Skill discovery and fully offline
behavior validation are recorded separately in [the M3 report](../docs/m3-validation.md).
Installing the skill does not authorize a registration. Keep private run files outside
the enclosing project if it is a Git checkout, not just outside the skill subdirectory.

If you already have a checkout and only need its Python dependencies, run from that
skill directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/debitmydata.py --help
```

For offline tests, install `requirements-dev.txt` and run `.venv/bin/python -m pytest -q`.
Tests use mock transports and temporary keys; they do not call staging. No Gateway
server, wallet, API key, blockchain node or `.env` file is needed.

Create a dedicated run directory outside all Git checkouts using `mkdir -m 700`.
Substitute its absolute path for `/absolute/private-run` below. It must be owned by
the current user. The helper creates private files with mode 0600, refuses key/state
overwrite and symlinks, and serializes writers with a sibling `.lock` file. Do not
delete the lock file while another command might be running. Its presence alone does
not mean a process is still running: the operating system owns the lock lifetime.

## Commands

```sh
# Read-only: no key, quote or registration is created.
.venv/bin/python scripts/debitmydata.py discover

# Only when the user requests creation of a controller key.
.venv/bin/python scripts/debitmydata.py new-key --key-file /absolute/private-run/controller.pem

# Only for a requested registration with an agreed staging operation budget.
.venv/bin/python scripts/debitmydata.py register --display-name "Example Agent" --key-file /absolute/private-run/controller.pem --state-file /absolute/private-run/registration.json

.venv/bin/python scripts/debitmydata.py status --state-file /absolute/private-run/registration.json
.venv/bin/python scripts/debitmydata.py resume --state-file /absolute/private-run/registration.json
.venv/bin/python scripts/debitmydata.py verify --state-file /absolute/private-run/registration.json
```

When invoked from another directory, use absolute paths to `.venv/bin/python` and
`scripts/debitmydata.py`. Do not interpolate untrusted values into a shell command;
pass arguments safely through the host's execution API.

`register` exclusively creates a new state file. `resume` uses the existing key,
idempotency key and intent IDs and rechecks server state. Never delete state to force
a retry. `status` only sends GET requests. `verify` checks an already saved issued
result using GETs and local cryptography; it never issues or pays. It records the
new verification outcome locally.

The state file includes the issued credential/result, so no separate `--result-file`
argument is required. It contains the key's path and public key, never private key
bytes or persisted controller signatures. Keep the controller key after completion.
Losing it does not authorize generating another key for the same registration.

The helper's settlement wait is six payment-status checks total per registration
invocation, with a 10-second delay before each check. Verification uses the settlement
response already observed in that invocation; standalone `verify` fetches current
payment status. Pending results require explicit resume; there is no self-scheduling.
Track the approved operation's total across invocations: resume/verify does not grant a
fresh budget. The 26 October smoke test used three checks across register and resume;
its one-registration authorization is now consumed.

## Results and recovery

Successful discovery/key commands and verified registration return exit code 0.
Pending, blocked and issued-but-unverified outcomes return exit code 2. Read the JSON
outcome, stage, IDs and next action; never infer a failed mutation from a timeout.
Errors omit private paths and provider response bodies. No secret should be pasted
into a chat or included in public evidence.

Quote replay preserves the exact body/key and is limited to one replay. A test payment
is attempted at most once per operation, even after a lost response. Uncertain proof
and issuance outcomes reconcile server status. Lost challenge responses stop because
the API has no challenge lookup. A saved expired challenge can be renewed once per
invocation; invalid or already-attempted unverified proofs stop for diagnosis.

HTTP 429/503 stops without automatic retry, rather than sleeping beyond the bounded
operation budget. A verification failure preserves the issued result and returns
`issued_unverified`; do not pay or register again. Consult [the recovery contract](registration.md).
