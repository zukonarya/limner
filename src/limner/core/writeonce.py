import os
import tempfile
from pathlib import Path


class WriteOnceError(OSError):
    pass


def _current_umask() -> int:
    # The umask can only be read by setting it; restore it immediately.
    mask = os.umask(0)
    os.umask(mask)
    return mask


def write_once(path: Path, data: bytes) -> None:
    """Create `path` with `data`, complete or absent, never replacing an existing file."""
    path = Path(path)
    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        tmp = Path(tmp_name)
        with os.fdopen(fd, "wb") as f:
            # mkstemp always creates 0600; give the file the mode a plain open() would, as before U1a.
            os.fchmod(f.fileno(), 0o666 & ~_current_umask())
            f.write(data)
        # link() fails if the target exists; rename() would silently replace it.
        os.link(tmp, path)
    except FileExistsError:
        raise WriteOnceError(f"Refusing to overwrite existing file: {path}") from None
    except OSError as e:
        raise WriteOnceError(f"Could not write {path}: {e}") from e
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
