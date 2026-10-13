import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from limner.core import job as job_module
from limner.core.job import JobError, run_job
from limner.core.order import parse_order
from limner.core.store import StoreError, open_store
from limner.providers.result import ProviderError, ProviderResult

JOB_ID = "20261013T120000Z-abcd"


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "ref.png").write_bytes(b"png-bytes")
    return workspace.resolve()


@pytest.fixture
def store(tmp_path):
    return open_store(tmp_path / "store", must_exist=False)


@pytest.fixture(autouse=True)
def fixed_job_id(monkeypatch):
    monkeypatch.setattr(job_module, "new_job_id", lambda now: JOB_ID)


def _order(ws, store, **changes):
    order = {
        "schema_version": "1", "action": "send", "project": "demo-site", "phase": "01-nav",
        "prompt": "A blue square", "adjustments": [], "references": [{"source": "ref.png", "label": "logo"}],
        "provider": "fal", "routing_rule": "R1", "settings": {}, "approval": "yes", "return_dir": "out",
        "cost_estimate": {"amount_usd": 0.04, "basis": "one image"}, "caller_name": "demo-caller",
    }
    order.update(changes)
    return parse_order(json.dumps(order).encode(), ws, store)


def _json(store, key):
    return json.loads(store.read(key))


SESSION = "demo-site/sessions/01-nav"


def test_test_job_writes_every_original_under_the_adr_names(ws, store):
    written = run_job(store, _order(ws, store), "test", None)
    assert written == [
        ("Prompt", f"{SESSION}/v01.txt"),
        ("Reference", "demo-site/references/ref.png"),
        ("Order", f"{SESSION}/v01_job-{JOB_ID}.order.json"),
        ("Image", f"{SESSION}/v01_fal_{JOB_ID}.png"),
        ("Receipt", f"{SESSION}/v01_fal_{JOB_ID}.run.json"),
    ]
    assert store.exists("demo-site/.versions/v01")
    assert store.read(f"{SESSION}/v01.txt") == b"A blue square"
    assert store.read("demo-site/references/ref.png") == b"png-bytes"


def test_receipt_in_store_mode(ws, store):
    run_job(store, _order(ws, store), "test", None)
    receipt = _json(store, f"{SESSION}/v01_fal_{JOB_ID}.run.json")
    assert (receipt["mode"], receipt["status"], receipt["project"], receipt["phase"]) == (
        "test", "succeeded", "demo-site", "01-nav")
    assert (receipt["version"], receipt["prompt_file"], receipt["image"]) == (
        "v01", "v01.txt", f"v01_fal_{JOB_ID}.png")
    assert receipt["references"] == [
        {"stored": "references/ref.png", "sha256": hashlib.sha256(b"png-bytes").hexdigest()}]
    assert receipt["prompt_sha256"] == hashlib.sha256(store.read(f"{SESSION}/v01.txt")).hexdigest()
    assert receipt["caller_copies"] == []


def test_order_form_holds_resolved_paths_cli_fields_and_version(ws, store):
    run_job(store, _order(ws, store), "test", None)
    form = _json(store, f"{SESSION}/v01_job-{JOB_ID}.order.json")
    assert form["references"] == [{"source": str(ws / "ref.png"), "label": "logo"}]
    assert form["return_dir"] == str(ws / "out")
    assert form["caller_workspace"] == str(ws)
    assert (form["job_id"], form["version"], form["caller_name"]) == (JOB_ID, 1, "demo-caller")
    assert form["received_at"] == _json(store, f"{SESSION}/v01_fal_{JOB_ID}.run.json")["started_at"]


def test_numbering_continues_across_phases_and_after_legacy_versions(ws, store):
    store.create("demo-site/sessions/00-legacy/v17.txt", b"old")
    run_job(store, _order(ws, store), "test", None)
    written = run_job(store, _order(ws, store, phase="02-hero"), "test", None)
    assert store.exists("demo-site/sessions/01-nav/v18.txt")
    assert written[0] == ("Prompt", "demo-site/sessions/02-hero/v19.txt")


def test_existing_version_with_the_same_prompt_adds_a_job(ws, store, monkeypatch):
    run_job(store, _order(ws, store), "test", None)
    monkeypatch.setattr(job_module, "new_job_id", lambda now: "20261013T120001Z-beef")
    written = run_job(store, _order(ws, store, version=1), "test", None)
    assert [label for label, _ in written] == ["Order", "Image", "Receipt"]
    assert store.list("demo-site/.versions/") == ["demo-site/.versions/v01"]


def test_a_failing_reservation_ends_the_job_without_a_receipt(ws, store, monkeypatch):
    order = _order(ws, store)
    real_create = store.create
    calls = []

    def create(key, data):
        calls.append(key)
        if "/.versions/" in key:
            raise StoreError("disk full")
        real_create(key, data)

    monkeypatch.setattr(store, "create", create)
    with pytest.raises(JobError) as exc:
        run_job(store, order, "test", None)
    assert exc.value.written == [] and len(calls) == 1
    assert store.list("") == []


def test_a_failing_prompt_write_keeps_the_reservation_and_writes_no_receipt(ws, store):
    store.create(f"{SESSION}/v01.txt/blocker", b"")
    order = _order(ws, store)
    with pytest.raises(JobError) as exc:
        run_job(store, order, "test", None)
    assert exc.value.written == []
    assert store.exists("demo-site/.versions/v01")
    assert not [k for k in store.list("demo-site/") if k.endswith(".run.json")]


def test_order_form_collision_stops_before_the_provider(ws, store):
    store.create("demo-site/sessions/01-nav/v01.txt", b"A blue square")
    store.create(f"{SESSION}/v01_job-{JOB_ID}.order.json", b"{}")
    generate = MagicMock()
    with pytest.raises(JobError, match="job id"):
        run_job(store, _order(ws, store, version=1), "live", generate)
    generate.assert_not_called()
    assert not [k for k in store.list(SESSION) if k.endswith((".run.json", ".png"))]


def test_provider_error_leaves_the_originals_and_a_failed_receipt(ws, store):
    original = RuntimeError("quota exceeded api_key=sk-secret")
    error = ProviderError(original, endpoint="fal-ai/edit", model="m-1")
    error.__cause__ = original
    with pytest.raises(JobError) as exc:
        run_job(store, _order(ws, store), "live", MagicMock(side_effect=error))
    assert [label for label, _ in exc.value.written] == ["Prompt", "Reference", "Order", "Receipt"]
    receipt = _json(store, exc.value.written[-1][1])
    assert (receipt["status"], receipt["endpoint"], receipt["image"]) == ("failed", "fal-ai/edit", None)
    assert receipt["error"]["type"] == "RuntimeError" and "sk-secret" not in receipt["error"]["message"]
    assert receipt["references"][0]["stored"] == "references/ref.png"


def test_live_job_sends_temporary_copies_and_removes_them(ws, store):
    seen = {}

    def generate(prompt, images, **extra):
        seen.update(prompt=prompt, extra=extra, names=[p.name for p in images],
                    data=[Path(p).read_bytes() for p in images], paths=images)
        return ProviderResult(image=b"image-bytes", endpoint="fal-ai/edit", model="m-1",
                              settings_sent={"aspect_ratio": "16:9"})

    run_job(store, _order(ws, store, settings={"aspect_ratio": "16:9"}), "live", generate)
    assert seen["prompt"] == "A blue square" and seen["extra"] == {"aspect_ratio": "16:9"}
    assert seen["names"] == ["ref.png"] and seen["data"] == [b"png-bytes"]
    assert not any(Path(p).exists() for p in seen["paths"])
    assert store.read(f"{SESSION}/v01_fal_{JOB_ID}.png") == b"image-bytes"
    receipt = _json(store, f"{SESSION}/v01_fal_{JOB_ID}.run.json")
    assert (receipt["mode"], receipt["settings_sent"]) == ("live", {"aspect_ratio": "16:9"})


def test_a_reused_reference_is_not_reported_as_written(ws, store):
    store.create("demo-site/references/ref.png", b"png-bytes")
    written = run_job(store, _order(ws, store), "test", None)
    assert "Reference" not in [label for label, _ in written]


def test_no_written_file_holds_the_absolute_store_root(ws, store, tmp_path):
    run_job(store, _order(ws, store), "test", None)
    root = str((tmp_path / "store").resolve()).encode()
    for key in store.list(""):
        assert root not in store.read(key), key


def test_an_unexpected_error_after_the_prompt_still_ends_with_a_failed_receipt(ws, store, monkeypatch):
    def no_space(*args, **kwargs):
        raise OSError("no space left")

    monkeypatch.setattr(job_module.tempfile, "TemporaryDirectory", no_space)
    with pytest.raises(JobError) as exc:
        run_job(store, _order(ws, store), "live", MagicMock())
    assert [label for label, _ in exc.value.written] == ["Prompt", "Reference", "Order", "Receipt"]
    receipt = _json(store, exc.value.written[-1][1])
    assert (receipt["status"], receipt["error"]["type"]) == ("failed", "OSError")
