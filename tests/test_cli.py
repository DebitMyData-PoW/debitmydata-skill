import json

import httpx
import pytest

import debitmydata
from protocol import Gateway
from workflow import initial_state
from test_workflow import FakeGateway


def test_cli_discovery_does_not_create_local_files(private_dir, monkeypatch, capsys):
    # Synthetic metadata only: no key is required for discovery.
    fake = FakeGateway({})
    monkeypatch.setattr(debitmydata, 'Gateway', lambda: Gateway(transport=httpx.MockTransport(fake)))
    before = set(private_dir.iterdir())
    assert debitmydata.main(['discover']) == 0
    assert json.loads(capsys.readouterr().out)['environment'] == 'staging'
    assert set(private_dir.iterdir()) == before
    assert all(call[0] == 'GET' for call in fake.calls)


def test_cli_missing_key_redacts_path(private_dir, capsys):
    state = private_dir / 'state.json'
    assert debitmydata.main(['register', '--display-name', 'Test', '--key-file',
                            str(private_dir / 'secret-location.pem'), '--state-file', str(state)]) == 2
    output = capsys.readouterr().out
    assert json.loads(output)['outcome'] == 'blocked'
    assert 'secret-location' not in output
    assert not state.exists()


def test_cli_key_output_contains_only_public_key(private_dir, capsys):
    path = private_dir / 'controller.pem'
    assert debitmydata.main(['new-key', '--key-file', str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert set(output) == {'controller_public_key'}
    assert output['controller_public_key'].startswith('ed25519:z6Mk')


@pytest.mark.parametrize('name', ['', '\n', 'a\x00b', 'x' * 101])
def test_invalid_display_name_rejected_before_key_read(private_dir, name):
    from local_store import SkillError
    with pytest.raises(SkillError, match='display name'):
        initial_state(name, private_dir / 'absent-key.pem')
