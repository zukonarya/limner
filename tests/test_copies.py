import errno
import os
import threading

import pytest

from limner.core import copies
from limner.core.copies import bind_copies

PROMPT = "v03.txt"
IMAGE = "v03_fal_20261015T101500Z-1a2b.png"


@pytest.fixture
def out(tmp_path):
    folder = tmp_path / "ws" / "out"
    folder.mkdir(parents=True)
    return folder.resolve()


def _run(out, files=None):
    return bind_copies(out)(files if files is not None else [(PROMPT, b"prompt"), (IMAGE, b"image")])


def _results(records):
    return [(r["result"], r["detail"]) for r in records]


def _leftovers(folder):
    return [p.name for p in folder.iterdir() if p.name.endswith(".tmp")]


def test_nothing_there_writes_both_with_the_plain_create_mode(out):
    old = os.umask(0o027)
    try:
        records = _run(out)
    finally:
        os.umask(old)
    assert _results(records) == [("written", None), ("written", None)]
    assert [r["path"] for r in records] == [str(out / PROMPT), str(out / IMAGE)]
    assert (out / PROMPT).read_bytes() == b"prompt" and (out / IMAGE).read_bytes() == b"image"
    assert all((out / n).stat().st_mode & 0o777 == 0o640 for n in (PROMPT, IMAGE))
    assert _leftovers(out) == []


def test_same_bytes_already_there_is_identical_and_untouched(out):
    target = out / PROMPT
    target.write_bytes(b"prompt")
    before = target.stat()
    assert _results(_run(out))[0] == ("identical", None)
    after = target.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


@pytest.mark.parametrize("existing", [b"other!", b"prom", b"prompt" * 10_000])
def test_a_different_file_is_kept(existing, out, monkeypatch):
    (out / PROMPT).write_bytes(existing)
    reads = []
    real_read = os.read
    monkeypatch.setattr(copies.os, "read", lambda fd, n: reads.append(n) or real_read(fd, n))
    assert _results(_run(out))[0] == ("skipped: exists", None)
    assert (out / PROMPT).read_bytes() == existing
    if len(existing) != len(b"prompt"):
        assert reads == []


@pytest.mark.parametrize("kind", ["folder", "pipe", "link-to-file", "link-to-pipe", "dangling-link"])
def test_anything_but_a_regular_file_is_skipped_unread(kind, out, tmp_path):
    target = out / PROMPT
    outside = tmp_path / "outside"
    if kind == "folder":
        target.mkdir()
    elif kind == "pipe":
        os.mkfifo(target)
    elif kind == "link-to-file":
        outside.write_bytes(b"prompt")
        target.symlink_to(outside)
    elif kind == "link-to-pipe":
        os.mkfifo(outside)
        target.symlink_to(outside)
    else:
        target.symlink_to(outside)
    result = []
    worker = threading.Thread(target=lambda: result.append(_run(out)), daemon=True)
    worker.start()
    worker.join(5)
    assert result, "the copy blocked"
    assert _results(result[0])[0] == ("skipped: exists", None)
    if kind == "link-to-file":
        assert outside.read_bytes() == b"prompt"
    if kind == "dangling-link":
        assert not outside.exists()


@pytest.mark.parametrize("content, expected", [
    (b"prompt", ("identical", None)),
    (b"theirs", ("skipped: exists", None)),
    (None, ("failed", "ENOENT")),
])
def test_losing_the_race_compares_once(content, expected, out, monkeypatch):
    def taken(src, dst, **kwargs):
        if content is not None:
            (out / dst).write_bytes(content)
        raise FileExistsError(errno.EEXIST, "File exists")
    monkeypatch.setattr(copies.os, "link", taken)
    assert _results(_run(out, [(PROMPT, b"prompt")])) == [expected]
    assert _leftovers(out) == []


@pytest.mark.parametrize("step, error", [
    ("link", OSError(errno.ENOTSUP, "Operation not supported: /Users/someone/out")),
    ("fchmod", OSError(errno.EPERM, "nope")),
    ("write", OSError(errno.ENOSPC, "No space left on device")),
])
def test_an_error_on_the_first_file_fails_only_that_file(step, error, out, monkeypatch):
    real = getattr(os, step)
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise error
        return real(*args, **kwargs)
    monkeypatch.setattr(copies.os, step, flaky)
    records = _run(out)
    assert _results(records) == [("failed", errno.errorcode[error.errno]), ("written", None)]
    assert not (out / PROMPT).exists() and (out / IMAGE).read_bytes() == b"image"
    assert _leftovers(out) == []


def test_an_error_without_errno_is_named_by_its_class(out, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("/Users/someone/secret path")
    monkeypatch.setattr(copies.os, "fchmod", boom)
    assert _results(_run(out, [(PROMPT, b"prompt")])) == [("failed", "ValueError")]
    assert _leftovers(out) == []


def test_return_dir_swapped_for_a_link_before_the_call_fails_both(out, tmp_path):
    copy = bind_copies(out)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    out.rename(tmp_path / "moved")
    out.symlink_to(elsewhere)
    assert _results(copy([(PROMPT, b"p"), (IMAGE, b"i")])) == [("failed", "ELOOP")] * 2
    assert list(elsewhere.iterdir()) == []


def test_return_dir_swapped_after_the_open_still_writes_into_the_opened_folder(out, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    moved = tmp_path / "moved"
    real_open = os.open

    def open_then_swap(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_DIRECTORY:
            out.rename(moved)
            out.symlink_to(elsewhere)
        return fd
    monkeypatch.setattr(copies.os, "open", open_then_swap)
    assert _results(_run(out)) == [("written", None), ("written", None)]
    assert list(elsewhere.iterdir()) == []
    assert sorted(p.name for p in moved.iterdir()) == [PROMPT, IMAGE]


@pytest.mark.parametrize("name", [
    "../x.txt", "a/b.png", "notes.md", "v01.txt\n", "v01\x00.txt", "", ".", "..", "V01.TXT",
    "v1.txt", "v03_dalle_20261015T101500Z-1a2b.png", "v03_fal_20261015T101500Z-1A2B.png",
])
def test_names_outside_the_adr_patterns_are_refused_untouched(name, out, monkeypatch):
    def no_fs(*args, **kwargs):
        raise AssertionError("file system touched")
    monkeypatch.setattr(copies.os, "open", no_fs)
    assert _results(_run(out, [(name, b"x")])) == [("failed", "invalid name")]
    assert list(out.iterdir()) == []


def test_three_digit_versions_are_valid_names(out):
    assert _results(_run(out, [("v100.txt", b"p"), ("v100_gemini_20261015T101500Z-0f0f.png", b"i")])) == [
        ("written", None), ("written", None)]


def test_a_socket_at_the_name_is_skipped(out):
    import socket
    # AF_UNIX paths are short; bind from inside the folder with a relative name.
    sock, cwd = socket.socket(socket.AF_UNIX), os.getcwd()
    os.chdir(out)
    try:
        sock.bind(PROMPT)
        assert _results(_run(out, [(PROMPT, b"prompt")])) == [("skipped: exists", None)]
    finally:
        os.chdir(cwd)
        sock.close()


def test_an_unusable_return_dir_fails_every_file_instead_of_raising(tmp_path):
    assert _results(bind_copies(str(tmp_path) + "\x00x")([(PROMPT, b"p")])) == [("failed", "ValueError")]
