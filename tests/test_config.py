from pathlib import Path

from config import resolve_output_dir


def test_explicit_override_wins_over_env_and_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGO_OUTPUT_DIR", str(tmp_path / "from_env"))
    override = tmp_path / "from_override"
    result = resolve_output_dir(override)
    assert result == override


def test_env_var_used_when_no_override(tmp_path, monkeypatch):
    env_dir = tmp_path / "from_env"
    monkeypatch.setenv("LOGO_OUTPUT_DIR", str(env_dir))
    result = resolve_output_dir(None)
    assert result == env_dir


def test_cwd_relative_default_when_neither_set(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGO_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result == tmp_path / "output"


def test_empty_string_env_var_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGO_OUTPUT_DIR", "")
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result == tmp_path / "output"


def test_whitespace_only_env_var_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGO_OUTPUT_DIR", "   ")
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result == tmp_path / "output"


def test_relative_env_var_resolved_to_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGO_OUTPUT_DIR", "relative_output")
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result.is_absolute()
    assert result == tmp_path / "relative_output"


def test_relative_override_resolved_to_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(Path("relative_override"))
    assert result.is_absolute()
    assert result == tmp_path / "relative_override"


def test_tilde_expanded_in_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LOGO_OUTPUT_DIR", "~/from_tilde")
    result = resolve_output_dir(None)
    assert result == tmp_path / "from_tilde"


def test_tilde_expanded_in_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = resolve_output_dir(Path("~/from_tilde_override"))
    assert result == tmp_path / "from_tilde_override"


def test_result_is_always_absolute(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGO_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result.is_absolute()


def test_resolver_does_not_create_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGO_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert not result.exists()
