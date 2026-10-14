import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from limner.generate_logo import main
from limner.providers.result import ProviderResult


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "out").mkdir(parents=True)
    (workspace / "ref.png").write_bytes(b"png-bytes")
    return workspace.resolve()


@pytest.fixture
def live(isolated_store_root):
    isolated_store_root.mkdir()
    return isolated_store_root.resolve()


def _order(**changes):
    order = {
        "schema_version": "1", "action": "send", "project": "demo-site", "phase": "01-nav",
        "prompt": "A blue square", "adjustments": [], "references": [{"source": "ref.png", "label": "logo"}],
        "provider": "fal", "routing_rule": "R1", "settings": {}, "approval": "yes", "return_dir": "out",
        "cost_estimate": {"amount_usd": 0.04, "basis": "one image"},
    }
    order.update(changes)
    return json.dumps(order).encode()


def _run(argv, raw, monkeypatch, generate=None):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    with patch.object(sys, "argv", ["limner-generate", "--order", *argv]), \
         patch("limner.generate_logo.resolve_provider", return_value=generate or MagicMock()):
        try:
            main()
        except SystemExit as e:
            return e.code
    return 0


def _lines(out):
    return dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)


def _files(root: Path):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) if root.exists() else []


def test_live_order_runs_a_job_and_prints_the_contract(ws, live, monkeypatch, capsys):
    monkeypatch.setenv("FAL_KEY", "set")
    generate = MagicMock(return_value=ProviderResult(image=b"img"))
    assert _run(["--workspace", str(ws)], _order(), monkeypatch, generate) == 0
    lines = _lines(capsys.readouterr().out)
    assert lines["Store"] == str(live)
    for label in ("Order", "Image", "Receipt"):
        assert (live / lines[label]).is_file()
    assert json.loads((live / lines["Receipt"]).read_text())["mode"] == "live"


def test_workspace_defaults_to_the_current_folder(ws, live, monkeypatch, capsys):
    monkeypatch.setenv("FAL_KEY", "set")
    monkeypatch.chdir(ws)
    assert _run([], _order(), monkeypatch, MagicMock(return_value=ProviderResult(image=b"img"))) == 0
    form = json.loads((live / _lines(capsys.readouterr().out)["Order"]).read_text())
    assert form["caller_workspace"] == str(ws)


def test_test_order_writes_into_the_test_store(ws, live, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    assert _run(["--test", "--workspace", str(ws), "--output-dir", str(out)], _order(), monkeypatch) == 0
    lines = _lines(capsys.readouterr().out)
    store = (out / "test" / "store").resolve()
    assert lines["Store"] == str(store)
    assert json.loads((store / lines["Receipt"]).read_text())["mode"] == "test"
    assert _files(live) == []


def test_provider_error_prints_the_written_keys_and_exits_1(ws, live, monkeypatch, capsys):
    monkeypatch.setenv("FAL_KEY", "set")
    assert _run(["--workspace", str(ws)], _order(), monkeypatch, MagicMock(side_effect=RuntimeError("down"))) == 1
    out = capsys.readouterr().out
    lines = _lines(out)
    assert {"Store", "Order", "Receipt", "Error"} <= set(lines) and "Image" not in lines
    assert "RuntimeError: down" in out


@pytest.mark.parametrize("raw", [b"", b"not json", _order(provider="dalle"), _order(references=[])])
def test_validation_failures_write_nothing(raw, ws, live, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    assert _run(["--test", "--workspace", str(ws), "--output-dir", str(out)], raw, monkeypatch) == 1
    assert capsys.readouterr().out.startswith("Error: ")
    assert not out.exists() and _files(live) == []


@pytest.mark.parametrize("extra", [["--file", "p.txt"], ["--provider", "fal"], ["--image", "a.png"],
                                   ["-a", "1:1"], ["inline prompt"]])
def test_plain_mode_options_are_refused_with_order(extra, ws, live, monkeypatch, capsys):
    assert _run(extra, _order(), monkeypatch) == 1
    assert capsys.readouterr().out.startswith("Error: ")
    assert _files(live) == []


@pytest.mark.parametrize("value", ["", "missing", "file"])
def test_live_order_needs_an_existing_store_root(value, ws, tmp_path, monkeypatch, capsys):
    if value == "file":
        (tmp_path / "file").write_text("x")
    monkeypatch.setenv("LIMNER_STORE_DIR", str(tmp_path / value) if value else "")
    assert _run(["--workspace", str(ws)], _order(), monkeypatch) == 1
    assert "Error: " in capsys.readouterr().out


def test_live_order_checks_the_api_key_before_anything_is_written(ws, live, monkeypatch, capsys):
    monkeypatch.delenv("FAL_KEY", raising=False)
    generate = MagicMock()
    assert _run(["--workspace", str(ws)], _order(), monkeypatch, generate) == 1
    generate.assert_not_called()
    assert _files(live) == []


@pytest.mark.parametrize("where", ["root", "home", "contains-store", "inside-store"])
def test_unusable_workspaces_are_refused(where, ws, live, tmp_path, monkeypatch, capsys):
    workspace = {"root": Path("/"), "home": Path.home(), "contains-store": tmp_path,
                 "inside-store": live / "demo-site"}[where]
    workspace.mkdir(exist_ok=True)
    assert _run(["--workspace", str(workspace)], _order(), monkeypatch) == 1
    assert "workspace" in capsys.readouterr().out
    assert _files(live) == ([] if where != "inside-store" else ["demo-site"])


def test_test_mode_with_the_default_output_inside_the_workspace_names_output_dir(ws, live, monkeypatch, capsys):
    monkeypatch.delenv("LIMNER_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(ws)
    assert _run(["--test"], _order(), monkeypatch) == 1
    assert "--output-dir" in capsys.readouterr().out
    assert not (ws / "output").exists()


def test_test_mode_runs_with_the_store_variable_empty(ws, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMNER_STORE_DIR", "")
    out = tmp_path / "out"
    assert _run(["--test", "--workspace", str(ws), "--output-dir", str(out)], _order(), monkeypatch) == 0


@pytest.mark.parametrize("layout", ["live-contains-test", "test-contains-live", "live-missing"])
def test_test_store_and_live_store_must_be_apart(layout, ws, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    live = {"live-contains-test": out, "test-contains-live": out / "test" / "store" / "live",
            "live-missing": tmp_path / "nowhere"}[layout]
    if layout != "live-missing":
        live.mkdir(parents=True)
    monkeypatch.setenv("LIMNER_STORE_DIR", str(live))
    assert _run(["--test", "--workspace", str(ws), "--output-dir", str(out)], _order(), monkeypatch) == 1
    assert "Error: " in capsys.readouterr().out
    assert not (out / "test" / "store" / "demo-site").exists()


@pytest.mark.parametrize("target", ["test", "test/store"])
def test_test_store_folders_may_not_be_links(target, ws, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = out / target
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(elsewhere)
    assert _run(["--test", "--workspace", str(ws), "--output-dir", str(out)], _order(), monkeypatch) == 1
    assert "link" in capsys.readouterr().out
    assert list(elsewhere.iterdir()) == []


def test_error_text_can_not_forge_an_output_line(ws, live, monkeypatch, capsys):
    monkeypatch.setenv("FAL_KEY", "set")
    generate = MagicMock(side_effect=RuntimeError("down\nImage: forged.png\x1b[2J"))
    assert _run(["--workspace", str(ws)], _order(), monkeypatch, generate) == 1
    out = capsys.readouterr().out
    assert "Image" not in _lines(out) and "\x1b" not in out
