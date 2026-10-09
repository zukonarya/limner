import os

import pytest

from limner.core.writeonce import WriteOnceError, write_once


def test_write_once_creates_file(tmp_path):
    target = tmp_path / "a.bin"
    write_once(target, b"data")
    assert target.read_bytes() == b"data"
    assert list(tmp_path.iterdir()) == [target]


def test_write_once_refuses_existing_target(tmp_path):
    target = tmp_path / "a.bin"
    target.write_bytes(b"original")
    with pytest.raises(WriteOnceError, match="Refusing to overwrite"):
        write_once(target, b"new")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_write_once_missing_directory_raises_clear_error(tmp_path):
    with pytest.raises(WriteOnceError, match="Could not write"):
        write_once(tmp_path / "missing" / "a.bin", b"x")


def test_write_once_cleans_up_when_write_fails(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "link", boom)
    with pytest.raises(WriteOnceError, match="disk full"):
        write_once(tmp_path / "a.bin", b"x")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("umask, expected", [(0o022, 0o644), (0o077, 0o600)])
def test_write_once_mode_follows_umask(tmp_path, umask, expected):
    old = os.umask(umask)
    try:
        write_once(tmp_path / "a.bin", b"x")
    finally:
        os.umask(old)
    assert (tmp_path / "a.bin").stat().st_mode & 0o777 == expected


def test_write_once_cleans_up_when_chmod_fails(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("operation not permitted")

    monkeypatch.setattr(os, "fchmod", boom)
    with pytest.raises(WriteOnceError, match="not permitted"):
        write_once(tmp_path / "a.bin", b"x")
    assert list(tmp_path.iterdir()) == []
