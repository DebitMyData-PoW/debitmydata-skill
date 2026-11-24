# Installing the DebitMyData skill

The skill installs inside a project, where Codex (or another agent that supports skills) finds it.

## What you need

Python 3.12 or later, and macOS or Linux (POSIX file permissions and `flock`). It was validated on
macOS and on Ubuntu 24.04; Windows has not been tested. No wallet, API key, node or `.env` file is
needed for staging.

## Install

From the project where you want to use the skill (the destination must not already exist):

```sh
mkdir -p .agents/skills
git clone https://github.com/DebitMyData-PoW/debitmydata-skill.git .agents/skills/debitmydata
cd .agents/skills/debitmydata
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/debitmydata.py --help
```

Then start a new Codex session in that project, check that `debitmydata` is among its skills, and
begin with a discovery-only request:

> Use the DebitMyData skill to check staging DID registration availability. Do not create a
> key, quote, payment or registration.

Installing the skill does not authorize a registration. A registration needs a display name, a
private folder outside any Git checkout (`mkdir -m 700`), and an agreed number of operations on
staging. Keep the agent's key and the operation's state there, for recovery.

## Using it

[references/runtime.md](references/runtime.md) gives the prompts for registering, checking,
resuming and verifying a DID-LLM, every command, and what each result means.

## Updating

```sh
cd .agents/skills/debitmydata && git pull
.venv/bin/python -m pip install -r requirements.txt
```

Then start a fresh Codex session.

## Tests

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The tests use stand-in transports and temporary keys: they make no request and need no server,
wallet or key.
