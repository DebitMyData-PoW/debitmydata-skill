import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


@pytest.fixture
def private_dir(tmp_path):
    tmp_path.chmod(0o700)
    return tmp_path
