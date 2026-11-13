import pytest
from pathlib import Path
from limner.core.validation import (
    TEXT_ONLY_NOTICE, get_api_key, missing_key_message, text_only_notice, validate_images, validate_provider,
)
from limner.core import validation

# --- validate_images ---

def test_validate_images_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        validate_images([tmp_path / "nonexistent.png"], "gemini")
    assert exc.value.code == 1


def test_validate_images_unsupported_extension_exits(tmp_path):
    f = tmp_path / "file.bmp"
    f.write_bytes(b"fake")
    with pytest.raises(SystemExit) as exc:
        validate_images([f], "gemini")
    assert exc.value.code == 1


def test_validate_images_valid_png_passes(tmp_path):
    f = tmp_path / "shot.png"
    f.write_bytes(b"fake")
    validate_images([f], "gemini")  # must not raise


def test_validate_images_valid_jpg_passes(tmp_path):
    f = tmp_path / "shot.jpg"
    f.write_bytes(b"fake")
    validate_images([f], "fal")


def test_validate_images_webp_rejected_by_fal(tmp_path):
    f = tmp_path / "shot.webp"
    f.write_bytes(b"fake")
    with pytest.raises(SystemExit) as exc:
        validate_images([f], "fal")
    assert exc.value.code == 1


def test_validate_images_webp_accepted_by_openai(tmp_path):
    f = tmp_path / "shot.webp"
    f.write_bytes(b"fake")
    validate_images([f], "openai")  # must not raise


def test_validate_images_empty_list_passes():
    validate_images([], "gemini")  # text-only — must not raise


def test_validate_images_composite_requires_a_reference(capsys):
    with pytest.raises(SystemExit) as exc:
        validate_images([], "composite")
    assert exc.value.code == 1
    assert "reference image" in capsys.readouterr().err


@pytest.mark.parametrize("provider", ["fal", "openai"])
def test_validate_images_fal_and_openai_run_text_only(provider):
    validate_images([], provider)  # both have a text route; must not raise


# --- text-only notice ---

@pytest.mark.parametrize("provider", ["fal", "openai"])
def test_text_only_notice_for_fal_and_openai_without_images(provider):
    assert text_only_notice(provider, []) == TEXT_ONLY_NOTICE
    assert TEXT_ONLY_NOTICE == "No reference images; running the text-only route."


@pytest.mark.parametrize("provider,images", [
    ("fal", [Path("ref.png")]),
    ("openai", [Path("ref.png")]),
    ("gemini", []),
    ("composite", []),
])
def test_text_only_notice_is_none_otherwise(provider, images):
    assert text_only_notice(provider, images) is None


def test_validate_provider_unknown_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        validate_provider("dalle")
    assert exc.value.code == 1
    assert "unknown provider 'dalle'" in capsys.readouterr().err


def test_validate_provider_known_passes():
    validate_provider("composite")


# --- get_api_key ---

def test_get_api_key_missing_gemini_exits(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        get_api_key("gemini")
    assert exc.value.code == 1


def test_get_api_key_missing_fal_exits(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        get_api_key("fal")
    assert exc.value.code == 1


def test_get_api_key_missing_openai_exits(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        get_api_key("openai")
    assert exc.value.code == 1


def test_get_api_key_returns_value(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    assert get_api_key("gemini") == "test-key-123"


# --- missing_key_message ---

def test_missing_key_message_names_the_key_file_that_exists(tmp_path, monkeypatch):
    key_file = tmp_path / ".env"
    key_file.write_text("")
    monkeypatch.setattr(validation, "resolve_env_file", lambda: key_file)
    message = missing_key_message("FAL_KEY")
    assert message.startswith("Error: FAL_KEY is not set")
    assert str(key_file) in message


def test_missing_key_message_says_when_the_key_file_does_not_exist(tmp_path, monkeypatch):
    key_file = tmp_path / ".env"
    monkeypatch.setattr(validation, "resolve_env_file", lambda: key_file)
    message = missing_key_message("FAL_KEY")
    assert message.startswith("Error: FAL_KEY is not set")
    assert "does not exist" in message
    assert str(key_file) in message


def test_missing_key_message_says_when_no_key_file_is_known(monkeypatch):
    monkeypatch.setattr(validation, "resolve_env_file", lambda: None)
    message = missing_key_message("FAL_KEY")
    assert message.startswith("Error: FAL_KEY is not set")
    assert "no key file" in message
    assert "environment" in message


def test_get_api_key_prints_the_message_and_no_other_key_value(tmp_path, monkeypatch, capsys):
    key_file = tmp_path / ".env"
    key_file.write_text("")
    monkeypatch.setattr(validation, "resolve_env_file", lambda: key_file)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("FAL_KEY", "sentinel-secret-value")
    with pytest.raises(SystemExit) as exc:
        get_api_key("gemini")
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert missing_key_message("GEMINI_API_KEY") in captured.err
    assert "sentinel-secret-value" not in captured.out + captured.err
