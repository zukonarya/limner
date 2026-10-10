import os
from pathlib import Path

import pytest

from limner.core.config import resolve_store_root
from limner.core.store import KeyExists, Store, StoreError, open_store


def test_tests_never_see_a_real_store(tmp_path):
    assert resolve_store_root().is_relative_to(tmp_path.resolve())


def test_file_store_satisfies_the_store_interface(tmp_path):
    assert isinstance(open_store(tmp_path, must_exist=True), Store)


def test_store_root_unset_or_empty_is_none(monkeypatch):
    monkeypatch.setenv("LIMNER_STORE_DIR", "")
    assert resolve_store_root() is None
    monkeypatch.delenv("LIMNER_STORE_DIR")
    assert resolve_store_root() is None


def test_store_root_is_resolved(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    monkeypatch.setenv("LIMNER_STORE_DIR", str(tmp_path / "link"))
    assert resolve_store_root() == real


def test_create_read_exists_and_list(tmp_path):
    store = open_store(tmp_path, must_exist=True)
    store.create("p/sessions/01-a/v01.txt", b"hello")
    assert store.read("p/sessions/01-a/v01.txt") == b"hello"
    assert store.exists("p/sessions/01-a/v01.txt")
    assert not store.exists("p/sessions/01-a/v02.txt")
    store.create("p/references/x.png", b"img")
    assert sorted(store.list("p/")) == ["p/references/x.png", "p/sessions/01-a/v01.txt"]
    assert store.list("q/") == []


def test_create_never_replaces(tmp_path):
    store = open_store(tmp_path, must_exist=True)
    store.create("a.txt", b"one")
    with pytest.raises(KeyExists):
        store.create("a.txt", b"two")
    assert store.read("a.txt") == b"one"


def test_create_failure_other_than_exists_is_a_store_error(tmp_path):
    store = open_store(tmp_path, must_exist=True)
    store.create("dir/a.txt", b"x")
    os.chmod(tmp_path / "dir", 0o500)
    try:
        with pytest.raises(StoreError) as exc:
            store.create("dir/b.txt", b"y")
        assert not isinstance(exc.value, KeyExists)
    finally:
        os.chmod(tmp_path / "dir", 0o700)


@pytest.mark.parametrize("key", ["", "/abs.txt", "../x", "a/../b", "a//b", "./a", "a/.", "a\x00b", "a\nb", "a\\b"])
def test_bad_keys_are_refused(tmp_path, key):
    store = open_store(tmp_path, must_exist=True)
    with pytest.raises(StoreError):
        store.create(key, b"x")


def test_key_through_a_link_leaving_the_root_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    (root / "esc").symlink_to(tmp_path / "outside")
    store = open_store(root, must_exist=True)
    with pytest.raises(StoreError):
        store.create("esc/x.txt", b"x")
    assert list((tmp_path / "outside").iterdir()) == []


def test_missing_root_must_exist_is_refused(tmp_path):
    with pytest.raises(StoreError):
        open_store(tmp_path / "absent", must_exist=True)


def test_missing_test_root_reads_empty_and_is_created_on_write(tmp_path):
    store = open_store(tmp_path / "absent", must_exist=False)
    assert store.list("") == [] and not store.exists("a.txt")
    assert not (tmp_path / "absent").exists()
    store.create("p/a.txt", b"x")
    assert (tmp_path / "absent" / "p" / "a.txt").read_bytes() == b"x"


@pytest.mark.parametrize("kind", ["link", "file"])
def test_root_that_is_a_link_or_file_is_refused(tmp_path, kind):
    target = tmp_path / "t"
    target.mkdir()
    root = tmp_path / "root"
    if kind == "link":
        root.symlink_to(target)
    else:
        root.write_text("x")
    with pytest.raises(StoreError):
        open_store(root, must_exist=False)


def test_store_errors_name_the_key_not_the_path(tmp_path):
    store = open_store(tmp_path, must_exist=True)
    store.create("dir/a.txt", b"x")
    os.chmod(tmp_path / "dir", 0o500)
    try:
        with pytest.raises(StoreError) as exc:
            store.create("dir/b.txt", b"y")
    finally:
        os.chmod(tmp_path / "dir", 0o700)
    assert str(tmp_path) not in str(exc.value)
    assert "dir/b.txt" in str(exc.value)


def test_long_keys_are_cut_in_errors(tmp_path):
    store = open_store(tmp_path, must_exist=True)
    with pytest.raises(StoreError) as exc:
        store.read("x" * 500)
    assert len(str(exc.value)) < 120


def test_list_does_not_follow_links_out_of_the_store(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.txt").write_text("s")
    (root / "esc").symlink_to(tmp_path / "outside")
    store = open_store(root, must_exist=True)
    assert store.list("esc/") == []
    assert store.list("") == []


def test_exists_reports_anything_occupying_a_key(tmp_path):
    store = open_store(tmp_path, must_exist=True)
    (tmp_path / "folder").mkdir()
    (tmp_path / "broken").symlink_to(tmp_path / "nowhere")
    assert store.exists("folder") and store.exists("broken")
    with pytest.raises(StoreError):
        store.read("folder")


def test_location_is_for_display_only(tmp_path):
    assert open_store(tmp_path, must_exist=True).location == str(tmp_path)
