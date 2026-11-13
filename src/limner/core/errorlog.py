"""Prints error lines on standard error and appends one redacted JSON line per error to a local log.

What is known about the current job (mode, provider, job id, store) is remembered once with note(), so
the many failure sites need no extra arguments; reset() clears it at the start of every run.
"""
import json
import os
import stat
import sys

from limner.core import config
from limner.core.receipt import redact_error, utc_now

_context: dict = {}


def printable(text) -> str:
    # One line, printable only: the agent reads labelled lines, so no text may forge one.
    return "".join(c if c.isprintable() else " " for c in str(text))


def reset() -> None:
    _context.clear()


def note(**fields) -> None:
    _context.update(fields)


def report(line: str, *, error_type: str = "Refusal", receipt: str | None = None, where: str | None = None) -> None:
    print(printable(line), file=sys.stderr)
    entry = {
        "time": utc_now().isoformat(),
        "mode": _context.get("mode"),
        "provider": _context.get("provider"),
        "job_id": _context.get("job_id"),
        "store": _context.get("store"),
        "error_type": error_type,
        "message": redact_error(line.removeprefix("Error: ")),
        "receipt": receipt,
        "where": where,
        "exit_code": 1,
    }
    try:
        _append(json.dumps(entry) + "\n")
    except Exception as e:
        # Whatever stops the log (a full disk, a refused file, no home folder) must never hide the real error.
        print(f"Note: error log not written: {e}", file=sys.stderr)


def fail(line: str, **kwargs) -> None:
    report(line, **kwargs)
    sys.exit(1)


def _append(text: str) -> None:
    path = config.resolve_log_file()
    existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not existed:
        # mkdir's mode is filtered by the umask, so the owner-only mode is set explicitly.
        path.parent.chmod(0o700)
    # O_NOFOLLOW: a link planted where the log belongs must not redirect the write.
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise OSError("the log file is not a private regular file owned by you")
        os.write(fd, text.encode())
    finally:
        os.close(fd)
