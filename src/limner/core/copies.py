"""Copies of a job's prompt and image into the caller's return_dir (ADR-0004 section 6).

Every operation runs relative to the one folder descriptor opened at the start, so a link swapped into the
path afterwards can't redirect a write; nothing at a taken name is ever replaced, followed or blocked on.
"""
import errno
import os
import re
import secrets
import stat
from pathlib import Path

from limner.core.writeonce import _current_umask
from limner.providers import VALID_PROVIDERS

WRITTEN, IDENTICAL, SKIPPED, FAILED = "written", "identical", "skipped: exists", "failed"

_VERSION = r"v[0-9]{2,}"
_NAME = re.compile(
    rf"{_VERSION}\.txt|{_VERSION}_(?:{'|'.join(map(re.escape, VALID_PROVIDERS))})_[0-9]{{8}}T[0-9]{{6}}Z-[0-9a-f]{{4}}\.png"
)
# O_NOFOLLOW_ANY refuses a link at any component of return_dir; elsewhere only the last one is checked.
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW_ANY", os.O_NOFOLLOW)
_READ_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
# What the open reports for a link, a folder, a pipe with no reader or a socket: something other than a file
# is there.
_NOT_A_FILE = {errno.ELOOP, errno.EISDIR, errno.ENXIO, errno.EOPNOTSUPP}


def _token(error: BaseException) -> str:
    # A fixed token, never the message: OS messages carry paths.
    code = getattr(error, "errno", None)
    return errno.errorcode.get(code, type(error).__name__) if code else type(error).__name__


def _write(folder: int, name: str, data: bytes) -> bool:
    """True when the copy was created; False when the name was already taken."""
    tmp = f".{name}.{secrets.token_hex(4)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
    try:
        try:
            # O_EXCL creates 0600; give the copy the mode a plain create would, as write_once does.
            os.fchmod(fd, 0o666 & ~_current_umask())
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
        try:
            os.link(tmp, name, src_dir_fd=folder, dst_dir_fd=folder, follow_symlinks=False)
        except FileExistsError:
            return False
        return True
    finally:
        try:
            os.unlink(tmp, dir_fd=folder)
        except OSError:
            pass


def _compare(folder: int, name: str, data: bytes) -> str:
    try:
        fd = os.open(name, _READ_FLAGS, dir_fd=folder)
    except OSError as e:
        if e.errno in _NOT_A_FILE:
            return SKIPPED
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(data):
            return SKIPPED
        # Bounded: a file that grew after the size check can't compare equal.
        chunks, left = [], len(data) + 1
        while left > 0:
            chunk = os.read(fd, left)
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        return IDENTICAL if b"".join(chunks) == data else SKIPPED
    finally:
        os.close(fd)


def _copy_one(folder: int, name: str, data: bytes) -> tuple[str, str | None]:
    try:
        if _write(folder, name, data):
            return WRITTEN, None
        return _compare(folder, name, data), None
    except Exception as e:
        return FAILED, _token(e)


def copy_files(return_dir: Path, files: list[tuple[str, bytes]]) -> list[dict]:
    """One {path, result, detail} record per file, in order; detail is a fixed token for the terminal only."""
    outcomes: list[tuple[str, str | None] | None] = [
        None if _NAME.fullmatch(name) else (FAILED, "invalid name") for name, _ in files
    ]
    if any(outcome is None for outcome in outcomes):
        try:
            folder = os.open(return_dir, _DIR_FLAGS)
        except (OSError, ValueError) as e:
            outcomes = [outcome or (FAILED, _token(e)) for outcome in outcomes]
        else:
            try:
                outcomes = [outcome or _copy_one(folder, name, data)
                            for outcome, (name, data) in zip(outcomes, files)]
            finally:
                os.close(folder)
    return [
        {"path": str(Path(return_dir) / name), "result": result, "detail": detail}
        for (name, _), (result, detail) in zip(files, outcomes)
    ]


def bind_copies(return_dir: Path):
    """The copy function run_job receives: bound to one validated folder, opened afresh on each call."""
    return_dir = Path(return_dir)
    return lambda files: copy_files(return_dir, files)
