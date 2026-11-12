import os
from pathlib import Path

import limner.core.config as config
from limner.core.config import load_keys, resolve_env_file, resolve_output_dir


def test_explicit_override_wins_over_env_and_default(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", str(tmp_path / "from_env"))
    override = tmp_path / "from_override"
    result = resolve_output_dir(override)
    assert result == override


def test_env_var_used_when_no_override(tmp_path, monkeypatch):
    env_dir = tmp_path / "from_env"
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", str(env_dir))
    result = resolve_output_dir(None)
    assert result == env_dir


def test_cwd_relative_default_when_neither_set(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMNER_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result == tmp_path / "output"


def test_empty_string_env_var_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", "")
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result == tmp_path / "output"


def test_whitespace_only_env_var_treated_as_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", "   ")
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result == tmp_path / "output"


def test_padded_env_var_is_trimmed(tmp_path, monkeypatch):
    env_dir = tmp_path / "from_env"
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", f"  {env_dir}\t ")
    result = resolve_output_dir(None)
    assert result == env_dir


def test_embedded_space_in_env_var_preserved(tmp_path, monkeypatch):
    env_dir = tmp_path / "my output"
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", f" {env_dir} ")
    result = resolve_output_dir(None)
    assert result == env_dir


def test_relative_env_var_resolved_to_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", "relative_output")
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
    monkeypatch.setenv("LIMNER_OUTPUT_DIR", "~/from_tilde")
    result = resolve_output_dir(None)
    assert result == tmp_path / "from_tilde"


def test_tilde_expanded_in_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    result = resolve_output_dir(Path("~/from_tilde_override"))
    assert result == tmp_path / "from_tilde_override"


def test_result_is_always_absolute(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMNER_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert result.is_absolute()


def test_resolver_does_not_create_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("LIMNER_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    result = resolve_output_dir(None)
    assert not result.exists()


def test_test_dir_is_test_under_output_dir_and_not_created(tmp_path):
    from limner.core.config import resolve_test_dir

    assert resolve_test_dir(tmp_path) == tmp_path / "test"
    assert not (tmp_path / "test").exists()


def test_test_dir_keeps_a_linked_last_part_unresolved(tmp_path):
    from limner.core.config import resolve_test_dir

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "test").symlink_to(elsewhere)
    assert resolve_test_dir(tmp_path).is_symlink()


# --- key file ---

KEY_VAR = "LIMNER_TEST_KEY_VAR"


def _unset(monkeypatch):
    # python-dotenv writes straight into os.environ; setting then deleting makes teardown remove it again.
    monkeypatch.setenv(KEY_VAR, "placeholder")
    monkeypatch.delenv(KEY_VAR)


def test_resolve_env_file_names_env_beside_pyproject_whatever_the_cwd(tmp_path, monkeypatch):
    before = resolve_env_file()
    monkeypatch.chdir(tmp_path)
    after = resolve_env_file()
    assert after == before
    assert after.name == ".env"
    assert (after.parent / "pyproject.toml").is_file()


def test_resolve_env_file_is_none_without_pyproject_beside_src(tmp_path, monkeypatch):
    fake = tmp_path / "lib" / "src" / "limner" / "core" / "config.py"
    fake.parent.mkdir(parents=True)
    monkeypatch.setattr(config, "__file__", str(fake))
    assert resolve_env_file() is None


def test_load_keys_without_argument_uses_resolved_file_not_the_current_folder(tmp_path, monkeypatch):
    key_file = tmp_path / "keys" / ".env"
    key_file.parent.mkdir()
    key_file.write_text(f"{KEY_VAR}=from-key-file\n")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / ".env").write_text(f"{KEY_VAR}=from-cwd\n")
    monkeypatch.setattr(config, "resolve_env_file", lambda: key_file)
    monkeypatch.chdir(cwd)
    _unset(monkeypatch)
    assert load_keys() == key_file
    assert os.environ[KEY_VAR] == "from-key-file"


def test_load_keys_sets_a_variable_from_the_given_file(tmp_path, monkeypatch):
    key_file = tmp_path / ".env"
    key_file.write_text(f"{KEY_VAR}=from-file\n")
    _unset(monkeypatch)
    load_keys(key_file)
    assert os.environ[KEY_VAR] == "from-file"


def test_load_keys_keeps_a_variable_already_in_the_environment(tmp_path, monkeypatch):
    key_file = tmp_path / ".env"
    key_file.write_text(f"{KEY_VAR}=from-file\n")
    monkeypatch.setenv(KEY_VAR, "from-env")
    load_keys(key_file)
    assert os.environ[KEY_VAR] == "from-env"


def test_load_keys_with_a_missing_file_sets_nothing_and_prints_nothing(tmp_path, monkeypatch, capsys):
    _unset(monkeypatch)
    missing = tmp_path / "nope.env"
    assert load_keys(missing) == missing
    assert KEY_VAR not in os.environ
    assert capsys.readouterr() == ("", "")


def test_load_keys_with_no_known_key_file_returns_none_and_prints_nothing(monkeypatch, capsys):
    monkeypatch.setattr(config, "resolve_env_file", lambda: None)
    assert load_keys() is None
    assert capsys.readouterr() == ("", "")
