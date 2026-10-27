#!/usr/bin/env python3
"""Staging-only DID registration CLI. No wallet or real funds are used."""

import argparse
import json
import sys

from local_store import SkillError, operation_lock, save_state
from protocol import Gateway, UnknownOutcome, new_key
from workflow import Workflow, initial_state, load_state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('discover')
    key = sub.add_parser('new-key')
    key.add_argument('--key-file', required=True)
    register = sub.add_parser('register')
    register.add_argument('--display-name', required=True)
    register.add_argument('--key-file', required=True)
    register.add_argument('--state-file', required=True)
    for command in ('status', 'resume', 'verify'):
        sub.add_parser(command).add_argument('--state-file', required=True)
    args = parser.parse_args(argv)
    gateway = None
    flow = None

    def failure(outcome, message):
        if flow:
            result = flow.result(outcome, flow.state.get('stage', 'local_validation'),
                                 'Preserve the operation state; inspect status before any retry.')
        else:
            result = {'outcome': outcome, 'environment': 'staging'}
        result['message'] = message
        print(json.dumps(result))
        return 2

    try:
        if args.command == 'new-key':
            result = {'controller_public_key': new_key(args.key_file)}
        else:
            gateway = Gateway()
            if args.command == 'discover':
                result = gateway.discover()
            else:
                with operation_lock(args.state_file):
                    if args.command == 'register':
                        state = initial_state(args.display_name, args.key_file)
                        save_state(args.state_file, state, replace=False)
                    else:
                        state = load_state(args.state_file)
                    flow = Workflow(gateway, args.state_file, state)
                    if args.command == 'status':
                        if 'registration_intent_id' not in state:
                            result = flow.result('pending', 'quote', 'No saved IDs; resume the same operation.')
                        else:
                            progress = flow.progress()
                            outcome = 'issued_unverified' if progress['did'] else 'pending'
                            result = flow.result(outcome, 'status', 'Use resume to continue or verify an issued result.')
                            result['payment_status'] = progress['payment']['status']
                            result['registration_status'] = progress['status']
                            result['controller_proof_status'] = progress['controller']['proof_status']
                            result['did'] = progress['did']
                    elif args.command == 'verify':
                        result = flow.verify()
                    else:
                        result = flow.run()
        print(json.dumps(result))
        return 0 if result.get('outcome') in (None, 'verified') else 2
    except UnknownOutcome as exc:
        return failure('pending', str(exc))
    except SkillError as exc:
        return failure('blocked', str(exc))
    except (OSError, KeyError, TypeError, ValueError):
        return failure('blocked', 'Invalid local file or Gateway response; preserve state and inspect configuration.')
    finally:
        if gateway:
            gateway.close()


if __name__ == '__main__':
    sys.exit(main())
