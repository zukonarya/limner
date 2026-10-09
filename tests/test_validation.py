import pytest
from pathlib import Path
from limner.core.validation import validate_images, validate_provider, get_api_key

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


@pytest.mark.parametrize("provider", ["fal", "openai", "composite"])
def test_validate_images_requires_reference_for_edit_providers(provider, capsys):
    with pytest.raises(SystemExit) as exc:
        validate_images([], provider)
    assert exc.value.code == 1
    assert "reference image" in capsys.readouterr().out


def test_validate_provider_unknown_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        validate_provider("dalle")
    assert exc.value.code == 1
    assert "unknown provider 'dalle'" in capsys.readouterr().out


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
