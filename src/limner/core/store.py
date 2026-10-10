"""The store of originals, addressed by keys relative to its root.

Keys are what records hold, so a later S3 module can replace FileStore without touching its callers.
Only open_store knows that the root is a folder.
"""
from pathlib import Path

from limner.core.writeonce import WriteOnceError, WriteOnceExists, write_once


class StoreError(Exception):
    pass


class KeyExists(StoreError):
    pass


def _check_key(key: str) -> list[str]:
    parts = key.split("/")
    if not key or key.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise StoreError(f"Invalid store key: {key[:40]!r}")
    return parts


class FileStore:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = self.root.joinpath(*_check_key(key))
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError(f"Store key leaves the store: {key[:40]!r}")
        return path

    def create(self, key: str, data: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_once(path, data)
        except WriteOnceExists:
            raise KeyExists(key) from None
        except (WriteOnceError, OSError) as e:
            raise StoreError(f"Could not write {key}: {e}") from e
        # A link created inside the folders after the check would show up here.
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError(f"Store key leaves the store: {key[:40]!r}")

    def read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as e:
            raise StoreError(f"Could not read {key}: {e}") from e

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str) -> list[str]:
        """Every file key under prefix, at any depth."""
        base = self.root.joinpath(*_check_key(prefix.rstrip("/"))) if prefix.strip("/") else self.root
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self.root).as_posix() for p in base.rglob("*") if p.is_file())


def open_store(root: Path, must_exist: bool) -> FileStore:
    root = Path(root)
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise StoreError(f"The store root {root} must be a plain folder, not a link or a file.")
    if must_exist and not root.is_dir():
        raise StoreError(f"The store root {root} does not exist.")
    return FileStore(root)
