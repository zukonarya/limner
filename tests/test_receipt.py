import time
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from importlib.metadata import version

import pytest

from limner.core.receipt import (
    build_receipt,
    redact_error,
    new_job_id,
    serialise_receipt,
    sha256_text,
    write_receipt,
)
from limner.core.writeonce import WriteOnceError

JOB_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{4}$")
FIELDS = {
    "schema_version", "job_id", "mode", "status", "error", "project", "phase", "version",
    "provider", "endpoint", "model", "settings_sent", "prompt_file", "prompt_sha256",
    "references", "provider_response", "started_at", "finished_at", "duration_s", "image",
    "caller_copies", "limner_version",
}


def make(**overrides):
    start = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    kwargs = dict(
        job_id="20260102T030405Z-abcd",
        status="succeeded",
        provider="fal",
        prompt="a red circle",
        started_at=start,
        finished_at=start + timedelta(seconds=2),
        duration_s=2.0,
    )
    kwargs.update(overrides)
    return build_receipt(**kwargs)


def test_job_id_matches_pattern():
    assert JOB_ID.match(new_job_id())


def test_job_id_uses_utc_time():
    tz = timezone(timedelta(hours=5))
    job_id = new_job_id(datetime(2026, 1, 2, 8, 4, 5, tzinfo=tz))
    assert job_id.startswith("20260102T030405Z-")


def test_receipt_has_every_field_with_plain_run_defaults():
    r = make()
    assert set(r) == FIELDS
    assert r["schema_version"] == "1"
    assert r["mode"] == "live"
    assert r["project"] is None and r["phase"] is None and r["version"] is None
    assert r["caller_copies"] == []
    assert r["prompt_file"] is None
    assert r["error"] is None and r["image"] is None
    assert r["settings_sent"] == {}
    assert r["references"] == []
    assert r["provider_response"] == {
        "request_id": None, "seed": None, "model_version": None, "usage": None,
    }
    assert r["limner_version"] == version("limner")


def test_receipt_timestamps_are_utc_iso_with_offset():
    r = make(started_at=datetime(2026, 1, 2, 8, 4, 5, tzinfo=timezone(timedelta(hours=5))))
    assert r["started_at"] == "2026-01-02T03:04:05+00:00"
    assert r["finished_at"] == "2026-01-02T03:04:07+00:00"


def test_receipt_hashes_prompt_and_references(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"AAA")
    b.write_bytes(b"BBB")
    r = make(prompt="héllo", references=[a, b], prompt_file="p.txt")
    assert r["prompt_sha256"] == hashlib.sha256("héllo".encode()).hexdigest()
    assert r["prompt_sha256"] == sha256_text("héllo")
    assert r["references"] == [
        {"stored": str(a), "sha256": hashlib.sha256(b"AAA").hexdigest()},
        {"stored": str(b), "sha256": hashlib.sha256(b"BBB").hexdigest()},
    ]
    assert r["prompt_file"] == "p.txt"


def test_receipt_keeps_provider_response_fields():
    r = make(provider_response={"request_id": "req-1", "usage": {"n": 3}})
    assert r["provider_response"]["request_id"] == "req-1"
    assert r["provider_response"]["usage"] == {"n": 3}
    assert r["provider_response"]["seed"] is None


def test_serialise_roundtrips_as_json():
    r = make(status="failed", error={"type": "RuntimeError", "message": "boom"})
    assert json.loads(serialise_receipt(r)) == r


def test_write_receipt_writes_once(tmp_path):
    target = tmp_path / "x.run.json"
    r = make()
    write_receipt(target, r)
    assert json.loads(target.read_text()) == r
    with pytest.raises(WriteOnceError):
        write_receipt(target, r)


@pytest.mark.parametrize("message, leaked", [
    ("job 550e8400-e29b-41d4-a716-446655440000:abcdef0123456789 failed", "abcdef0123456789"),
    ('{"api_key": "sk-proj-abc"}', "sk-proj-abc"),
    ("{'token': 'abc def'}", "abc def"),
    ('{"password":"hunter2"}', "hunter2"),
    ("secret=hunter2", "hunter2"),
    ('api_key = "abc"', "abc"),
    ("authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("GEMINI_API_KEY=AIzaSyA12345 invalid", "AIzaSyA12345"),
    ("key=AIzaSyShort1", "AIzaSyShort1"),
    ('FAL_KEY: "abc"', "abc"),
    ("X_API_TOKEN=abc123", "abc123"),
    ("client_secret=abc123", "abc123"),
])
def test_redact_error_hides_credentials(message, leaked):
    redacted = redact_error(message)
    assert leaked not in redacted


def test_redact_error_removes_whole_uuid_secret_pair():
    assert redact_error("job 550e8400-e29b-41d4-a716-446655440000:abcdef0123456789 failed") == "job [redacted] failed"


@pytest.mark.parametrize("message, expected", [
    ("monkey business", "monkey business"),
    ("Invalid key format", "Invalid key [redacted]"),
    ("keyboard: missing", "keyboard: missing"),
])
def test_redact_error_leaves_ordinary_text(message, expected):
    assert redact_error(message) == expected


@pytest.mark.parametrize("url", [
    "https://example.com/api?a=(b)&sig=SECRET",
    'https://example.com/api?a="b"&sig=SECRET',
    "https://example.com/api?a='b'&sig=SECRET",
])
def test_redact_error_removes_whole_url(url):
    assert "SECRET" not in redact_error(f"failed {url}")


@pytest.mark.parametrize("message", ["key_" * 25000, "a_" * 50000])
def test_redact_error_is_fast_on_pathological_input(message):
    start = time.perf_counter()
    redact_error(message)
    assert time.perf_counter() - start < 1
