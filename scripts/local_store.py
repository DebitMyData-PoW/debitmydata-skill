"""POSIX-only private files and single-writer operation records."""

import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
from contextlib import contextmanager


class SkillError(Exception):
    """A fixed diagnostic safe to display without response bodies or key paths."""


def private_path(value):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise SkillError('Use an absolute private-file path without parent traversal.')
    # macOS /tmp and /var are system aliases. Resolve only the parent, then reject
    # user-controlled aliases beneath it and Git checkout ancestors.
    parent = path.parent.resolve(strict=True)
    for ancestor in (parent, *parent.parents):
        if (ancestor / '.git').exists():
            raise SkillError('Private files must be outside Git checkouts.')
    for ancestor in (path.parent, *path.parent.parents):
        if ancestor.is_symlink() and str(ancestor) not in ('/tmp', '/var'):
            raise SkillError('Private paths must not contain symlinks.')
    info = parent.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise SkillError('The private run directory must be owned by you with mode 0700.')
    return parent / path.name


def _check_file(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise SkillError('Private files must be regular, singly linked, owned by you, and mode 0600.')


def read_private(value):
    path = private_path(value)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        _check_file(stream.fileno())
        data = stream.read(1_048_577)
    if len(data) > 1_048_576:
        raise SkillError('Private file exceeds the size limit.')
    return data


def write_private(value, data, *, replace=False):
    path = private_path(value)
    if replace:
        read_private(path)  # Refuse symlinks, shared permissions and hard links.
        fd, temporary = tempfile.mkstemp(prefix='.dmd-', dir=path.parent)
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        temporary = None
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def operation_lock(value):
    path = private_path(value)
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        _check_file(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SkillError('This operation is already running.') from None
        yield
    finally:
        os.close(fd)  # Keep lock inode: unlinking permits racing independent locks.


def save_state(path, state, *, replace=True):
    write_private(path, json.dumps(state, ensure_ascii=False, allow_nan=False).encode(),
                  replace=replace)
