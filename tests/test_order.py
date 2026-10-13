import json
import os

import pytest

from limner.core.order import MAX_ORDER_BYTES, OrderError, parse_fields, parse_order
from limner.core.store import open_store



@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "ref.png").write_bytes(b"png-bytes")
    return workspace


@pytest.fixture
def store(tmp_path):
    return open_store(tmp_path / "store", must_exist=False)


def _order(**changes):
    order = {
        "schema_version": "1",
        "action": "send",
        "project": "demo-site",
        "phase": "01-nav",
        "prompt": "A blue square",
        "adjustments": [],
        "references": [{"source": "ref.png", "label": "logo"}],
        "provider": "fal",
        "routing_rule": "R1",
        "settings": {},
        "cost_estimate": {"amount_usd": 0.04, "basis": "one image"},
        "approval": "yes",
        "return_dir": "out",
    }
    for key, value in changes.items():
        if value is ...:
            order.pop(key)
        else:
            order[key] = value
    return json.dumps(order).encode()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[1, 2]",
        b"\xff\xfe",
        b'{"a": 1, "a": 2}',
        b'{"amount": NaN}',
        b'{"adjustments": [{"rule": "r", "rule": "s", "before": "a", "after": "b"}]}',
        b'{"version": ' + b"9" * 5000 + b"}",
        b"[" * 100_000,
        b'{"prompt": "\\ud800"}',
    ],
    ids=["empty", "text", "list", "not utf8", "duplicate", "nan", "nested duplicate", "huge int", "deep", "surrogate"],
)
def test_malformed_input_is_refused(raw):
    with pytest.raises(OrderError):
        parse_fields(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "2"},
        {"action": "draft"},
        {"project": ...},
        {"routing_rule": ...},
        {"routing_rule": 7},
        {"approval": ...},
        {"adjustments": {}},
        {"settings": []},
        {"prompt": ""},
        {"approval": ""},
        {"surprise": 1},
        {"job_id": "x"},
        {"caller_workspace": "/x"},
        {"received_at": "now"},
        {"project": "Demo_Site"},
        {"phase": "nav"},
        {"caller_name": "Bad Name"},
        {"version": True},
        {"version": 0},
        {"version": 1.5},
        {"parent_version": -1},
        {"adjustments": [{"rule": "r", "before": "a"}]},
        {"adjustments": [{"rule": "r", "before": "a", "after": 1}]},
        {"feedback_on_parent": {"user_verdict": "ok"}},
        {"references": [{"source": "ref.png"}]},
        {"references": "ref.png"},
        {"cost_estimate": {"amount_usd": -1, "basis": "b"}},
        {"cost_estimate": {"amount_usd": True, "basis": "b"}},
        {"cost_estimate": {"amount_usd": 1}},
        {"user_words": 5},
    ],
)
def test_invalid_fields_are_refused(changes):
    with pytest.raises(OrderError):
        parse_fields(_order(**changes))


def test_valid_fields_are_returned():
    fields = parse_fields(_order(caller_name="demo-caller", version=2, user_words="blue"))
    assert fields["project"] == "demo-site" and fields["version"] == 2


def test_error_messages_carry_no_control_characters():
    with pytest.raises(OrderError) as exc:
        parse_fields(_order(project="\x1b[31mevil"))
    assert "\x1b" not in str(exc.value)


def test_size_cap_refuses_an_otherwise_valid_order():
    padded = _order(user_words="x" * MAX_ORDER_BYTES)
    with pytest.raises(OrderError, match="1 MB"):
        parse_fields(padded)


def test_lone_surrogate_anywhere_is_refused():
    with pytest.raises(OrderError, match="UTF-8"):
        parse_fields(_order(prompt="ok", user_words="\ud800"))


def test_whitespace_prompt_is_not_empty():
    assert parse_fields(_order(prompt=" "))["prompt"] == " "


# ── References, paths and the store ─────────────────────────────────────────


def _parse(raw, ws, store):
    return parse_order(raw, ws.resolve(), store)


def test_valid_order_is_returned_with_held_bytes(ws, store):
    order = _parse(_order(caller_name="demo-caller", settings={"aspect_ratio": "16:9"}), ws, store)
    assert order.project == "demo-site" and order.phase == "01-nav"
    assert order.version is None and order.caller_name == "demo-caller"
    assert order.aspect_ratio == "16:9"
    [ref] = order.references
    assert (ref.name, ref.label, ref.data) == ("ref.png", "logo", b"png-bytes")
    assert ref.source == (ws / "ref.png").resolve()
    assert order.return_dir == (ws / "out").resolve()


@pytest.mark.parametrize(
    "changes",
    [
        {"settings": {"seed": 1}},
        {"settings": {"aspect_ratio": 16}},
        {"settings": {"aspect_ratio": "2:1"}},
        {"provider": "dalle"},
        {"references": []},
        {"settings": {"aspect_ratio": None}},
        {"settings": {"aspect_ratio": "9" * 5000 + ":1"}},
        {"references": [{"source": "x\u0000/ref.png", "label": "x"}]},
        {"references": [{"source": "d" * 5000 + "/ref.png", "label": "x"}]},
        {"return_dir": "o\u0000ut"},
        {"return_dir": "d" * 5000},
        {"references": [{"source": "ref.png", "label": "x"}] * 21},
    ],
    ids=["seed", "number", "unsupported", "provider", "no refs", "null ratio", "huge ratio", "nul source",
         "long source", "nul return", "long return", "too many refs"],
)
def test_invalid_settings_and_provider_are_refused(changes, ws, store):
    with pytest.raises(OrderError):
        _parse(_order(**changes), ws, store)


def test_gemini_may_run_without_references(ws, store):
    assert _parse(_order(provider="gemini", references=[]), ws, store).references == ()


def test_reference_outside_the_workspace_is_refused(ws, store, tmp_path):
    (tmp_path / "elsewhere.png").write_bytes(b"x")
    with pytest.raises(OrderError):
        _parse(_order(references=[{"source": str(tmp_path / "elsewhere.png"), "label": "x"}]), ws, store)


def test_reference_link_pointing_outside_is_refused(ws, store, tmp_path):
    (tmp_path / "secret.png").write_bytes(b"x")
    (ws / "link.png").symlink_to(tmp_path / "secret.png")
    with pytest.raises(OrderError):
        _parse(_order(references=[{"source": "link.png", "label": "x"}]), ws, store)


@pytest.mark.parametrize("make", ["missing", "folder", "fifo", "bad name", "bad type"])
def test_bad_reference_files_are_refused(make, ws, store):
    source = {"missing": "gone.png", "folder": "dir.png", "fifo": "pipe.png", "bad name": "my photo.png",
              "bad type": "ref.gif"}[make]
    if make == "folder":
        (ws / "dir.png").mkdir()
    if make == "fifo":
        os.mkfifo(ws / "pipe.png")
    if make == "bad name":
        (ws / "my photo.png").write_bytes(b"x")
    if make == "bad type":
        (ws / "ref.gif").write_bytes(b"x")
    with pytest.raises(OrderError):
        _parse(_order(references=[{"source": source, "label": "x"}]), ws, store)


def test_oversized_reference_is_refused(ws, store, monkeypatch):
    monkeypatch.setattr("limner.core.order.MAX_REFERENCE_BYTES", 4)
    with pytest.raises(OrderError):
        _parse(_order(), ws, store)


@pytest.mark.parametrize("return_dir", ["missing", "ref.png", "/tmp"])
def test_bad_return_dir_is_refused(return_dir, ws, store):
    with pytest.raises(OrderError):
        _parse(_order(return_dir=return_dir), ws, store)


def test_existing_version_must_match_phase_and_prompt(ws, store):
    store.create("demo-site/sessions/01-nav/v03.txt", b"A blue square")
    assert _parse(_order(version=3), ws, store).version == 3
    with pytest.raises(OrderError):
        _parse(_order(version=3, prompt="A red square"), ws, store)
    with pytest.raises(OrderError):
        _parse(_order(version=3, phase="02-hero"), ws, store)
    with pytest.raises(OrderError):
        _parse(_order(version=4), ws, store)


def test_parent_version_must_exist_and_be_lower(ws, store):
    store.create("demo-site/sessions/01-nav/v03.txt", b"A blue square")
    assert _parse(_order(parent_version=3), ws, store).parent_version == 3
    with pytest.raises(OrderError):
        _parse(_order(parent_version=7), ws, store)
    with pytest.raises(OrderError):
        _parse(_order(version=3, parent_version=3), ws, store)


def test_stored_reference_conflict_is_refused(ws, store):
    store.create("demo-site/references/ref.png", b"other bytes")
    with pytest.raises(OrderError):
        _parse(_order(), ws, store)


def test_order_carries_workspace_hashes_and_frozen_fields(ws, store):
    order = _parse(_order(), ws, store)
    assert order.workspace == ws.resolve()
    assert order.references[0].sha256 == __import__("hashlib").sha256(b"png-bytes").hexdigest()
    with pytest.raises(TypeError):
        order.fields["project"] = "other"


def test_repeated_reference_is_read_once(ws, store, monkeypatch):
    opened = []
    real_open = os.open
    monkeypatch.setattr(os, "open", lambda path, *a, **k: opened.append(path) or real_open(path, *a, **k))
    order = _parse(_order(references=[{"source": "ref.png", "label": "x"}] * 3), ws, store)
    assert len(order.references) == 3 and len(opened) == 1


@pytest.mark.parametrize("other_bytes", [b"2", b"1"])
def test_references_differing_only_in_case_are_refused(ws, store, other_bytes):
    (ws / "a").mkdir()
    (ws / "b").mkdir()
    (ws / "a" / "x.png").write_bytes(b"1")
    (ws / "b" / "X.png").write_bytes(other_bytes)
    refs = [{"source": "a/x.png", "label": "1"}, {"source": "b/X.png", "label": "2"}]
    with pytest.raises(OrderError, match="case"):
        _parse(_order(references=refs), ws, store)


def test_stored_case_variant_is_refused_even_with_equal_bytes(ws, store):
    store.create("demo-site/references/REF.png", b"png-bytes")
    with pytest.raises(OrderError, match="clashes"):
        _parse(_order(), ws, store)
