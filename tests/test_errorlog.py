import json
import os
import stat

import pytest

from limner.core import config, errorlog


def _entries(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_the_log_path_inside_a_test_is_the_temporary_one(isolated_error_log, tmp_path_factory):
    assert config.resolve_log_file() == isolated_error_log
    assert tmp_path_factory.getbasetemp() in isolated_error_log.parents


def test_report_prints_the_line_on_standard_error_only(capsys):
    errorlog.report("Error: no such thing")
    captured = capsys.readouterr()
    assert captured.err == "Error: no such thing\n"
    assert captured.out == ""


def test_report_prints_one_printable_line(capsys):
    errorlog.report("Error: a\nb\x1bc")
    assert capsys.readouterr().err == "Error: a b c\n"


def test_report_appends_one_json_line_with_the_expected_fields(isolated_error_log):
    errorlog.note(mode="plain", provider="fal", job_id="j1", store="s")
    errorlog.report("Error: it broke", error_type="RuntimeError", receipt="r.run.json", where="x.py:3")
    [entry] = _entries(isolated_error_log)
    assert set(entry) == {"time", "mode", "provider", "job_id", "store", "error_type", "message",
                          "receipt", "where", "exit_code"}
    assert (entry["mode"], entry["provider"], entry["job_id"], entry["store"]) == ("plain", "fal", "j1", "s")
    assert (entry["error_type"], entry["message"], entry["receipt"]) == ("RuntimeError", "it broke", "r.run.json")
    assert (entry["where"], entry["exit_code"]) == ("x.py:3", 1)
    assert entry["time"].endswith("+00:00")


def test_report_without_noted_fields_logs_nulls_and_the_default_type(isolated_error_log):
    errorlog.report("Error: refused")
    [entry] = _entries(isolated_error_log)
    assert entry["error_type"] == "Refusal"
    assert [entry[k] for k in ("mode", "provider", "job_id", "store", "receipt", "where")] == [None] * 6


def test_reset_clears_the_noted_fields(isolated_error_log):
    errorlog.note(job_id="j1")
    errorlog.reset()
    errorlog.report("Error: refused")
    assert _entries(isolated_error_log)[0]["job_id"] is None


def test_the_logged_message_is_redacted_but_the_terminal_line_is_not(isolated_error_log, capsys):
    line = "Error: failed at https://example.com/x?key=abc FAL_KEY=supersecretvalue123"
    errorlog.report(line)
    assert "https://example.com" in capsys.readouterr().err
    message = _entries(isolated_error_log)[0]["message"]
    assert "example.com" not in message and "supersecretvalue123" not in message


def test_a_newline_in_a_message_stays_inside_one_json_string(isolated_error_log):
    errorlog.report("Error: first\nsecond")
    assert len(isolated_error_log.read_text().splitlines()) == 1
    assert _entries(isolated_error_log)[0]["message"] == "first\nsecond"


def test_a_second_entry_appends(isolated_error_log):
    errorlog.report("Error: one")
    errorlog.report("Error: two")
    assert [e["message"] for e in _entries(isolated_error_log)] == ["one", "two"]


def test_fail_logs_then_exits_with_code_1(isolated_error_log):
    with pytest.raises(SystemExit) as exc:
        errorlog.fail("Error: stop")
    assert exc.value.code == 1
    assert _entries(isolated_error_log)[0]["message"] == "stop"


def test_the_file_is_0600_and_a_new_folder_0700_even_under_a_loose_umask(isolated_error_log):
    old = os.umask(0)
    try:
        errorlog.report("Error: one")
    finally:
        os.umask(old)
    assert stat.S_IMODE(isolated_error_log.stat().st_mode) == 0o600
    assert stat.S_IMODE(isolated_error_log.parent.stat().st_mode) == 0o700


def test_an_unwritable_log_adds_one_note_and_keeps_the_original_line(isolated_error_log, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    monkeypatch.setattr(config, "resolve_log_file", lambda: blocker / "errors.log")
    errorlog.report("Error: original")
    err = capsys.readouterr().err.splitlines()
    assert err[0] == "Error: original"
    assert len(err) == 2 and err[1].startswith("Note: error log not written: ")


def test_a_symbolic_link_in_place_of_the_log_is_not_followed(isolated_error_log, tmp_path, capsys):
    target = tmp_path / "target.txt"
    target.write_text("untouched")
    isolated_error_log.parent.mkdir(exist_ok=True)
    isolated_error_log.symlink_to(target)
    errorlog.report("Error: one")
    assert target.read_text() == "untouched"
    assert "Note: error log not written: " in capsys.readouterr().err


def test_an_existing_log_with_group_or_other_bits_is_not_written(isolated_error_log, capsys):
    isolated_error_log.parent.mkdir(exist_ok=True)
    isolated_error_log.write_text("")
    isolated_error_log.chmod(0o644)
    errorlog.report("Error: one")
    assert isolated_error_log.read_text() == ""
    assert "Note: error log not written: " in capsys.readouterr().err


def test_a_failure_resolving_the_log_path_keeps_the_original_line_and_adds_one_note(monkeypatch, capsys):
    def broken():
        raise RuntimeError("no home folder")
    monkeypatch.setattr(config, "resolve_log_file", broken)
    errorlog.report("Error: original")
    err = capsys.readouterr().err.splitlines()
    assert err[0] == "Error: original"
    assert err[1] == "Note: error log not written: no home folder"
