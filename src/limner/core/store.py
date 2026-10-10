"""The store of originals, addressed by keys relative to its root.

Keys are what records hold, so a later S3 module can replace FileStore without touching its callers.
Only open_store knows that the root is a folder.
"""
from pathlib import Path
from typing import Protocol, runtime_checkable

from limner.core.writeonce import WriteOnceError, WriteOnceExists, write_once


class StoreError(Exception):
    pass


class KeyExists(StoreError):
    pass


@runtime_checkable
class Store(Protocol):
    """What every store provides. create raises KeyExists for a taken key and StoreError for anything else;
    error messages name the key, never a location, because they can end up in receipts."""

    location: str

    def create(self, key: str, data: bytes) -> None: ...

    def read(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def list(self, prefix: str) -> list[str]: ...


def _show(key: str) -> str:
    return repr(key[:40])


def _reason(error: Exception) -> str:
    # str(OSError) carries the absolute path; strerror doesn't.
    cause = error.__cause__ if isinstance(error, WriteOnceError) and error.__cause__ else error
    return getattr(cause, "strerror", None) or type(cause).__name__


def _check_key(key: str) -> list[str]:
    parts = key.split("/")
    if (
        not key
        or key.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or not key.isprintable()
        or "\\" in key
    ):
        raise StoreError(f"Invalid store key: {_show(key)}")
    return parts


class FileStore:
    def __init__(self, root: Path):
        self._root = root
        self.location = str(root)

    def _inside(self, path: Path) -> bool:
        return path.resolve().is_relative_to(self._root.resolve())

    def _path(self, key: str) -> Path:
        path = self._root.joinpath(*_check_key(key))
        if not self._inside(path):
            raise StoreError(f"Store key leaves the store: {_show(key)}")
        return path

    def create(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_once(path, data)
        except WriteOnceExists:
            raise KeyExists(key) from None
        except (WriteOnceError, OSError) as e:
            raise StoreError(f"Could not write {_show(key)}: {_reason(e)}") from e
        # A link created inside the folders after the check would show up here.
        if not self._inside(path):
            raise StoreError(f"Store key leaves the store: {_show(key)}")

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as e:
            raise StoreError(f"Could not read {_show(key)}: {_reason(e)}") from e

    def exists(self, key: str) -> bool:
        """True when anything occupies the key, including a folder or a broken link."""
        path = self._path(key)
        return path.exists() or path.is_symlink()

    def list(self, prefix: str) -> list[str]:
        """Every file key under prefix, at any depth, never following links out of the store."""
        base = self._root.joinpath(*_check_key(prefix.rstrip("/"))) if prefix.strip("/") else self._root
        if not base.is_dir() or not self._inside(base):
            return []
        return sorted(
            p.relative_to(self._root).as_posix()
            for p in base.rglob("*")
            if p.is_file() and self._inside(p)
        )


def open_store(root: Path, must_exist: bool) -> FileStore:
    root = Path(root)
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise StoreError("The store root must be a plain folder, not a link or a file.")
    if must_exist and not root.is_dir():
        raise StoreError("The store root does not exist.")
    return FileStore(root)
