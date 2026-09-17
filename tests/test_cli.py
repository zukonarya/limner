import pytest
import sys
from providers import resolve_provider, VALID_PROVIDERS


def test_resolve_provider_unknown_exits():
    with pytest.raises(SystemExit) as exc:
        resolve_provider("badvalue")
    assert exc.value.code == 1


def test_resolve_provider_returns_callable():
    fn = resolve_provider("gemini")
    assert callable(fn)


def test_valid_providers_contains_all_known_providers():
    assert set(VALID_PROVIDERS) == {"gemini", "fal", "openai", "composite"}


import types as builtin_types
from pathlib import Path
from generate_logo import resolve_config


def _make_args(provider=None, file=None, prompt=None, images=None):
    ns = builtin_types.SimpleNamespace()
    ns.provider = provider
    ns.file = file
    ns.prompt = prompt
    ns.images = images or []
    return ns


def test_default_provider_is_gemini_when_no_flag_and_no_header(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("Plain prompt")
    args = _make_args(file=f)
    provider, images, prompt, _ = resolve_config(args)
    assert provider == "gemini"


def test_header_provider_used_when_no_flag(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: fal\n---\nMy prompt")
    args = _make_args(file=f)
    provider, _, _, _ = resolve_config(args)
    assert provider == "fal"


def test_cli_provider_overrides_header(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: gemini\n---\nMy prompt")
    args = _make_args(provider="openai", file=f)
    provider, _, _, _ = resolve_config(args)
    assert provider == "openai"


def test_cli_images_override_header_images(tmp_path):
    f = tmp_path / "v01.txt"
    c = tmp_path / "c.png"
    c.write_bytes(b"fake")
    f.write_text("# images: a.png, b.png\n---\nPrompt")
    args = _make_args(file=f, images=[c])
    _, images, _, _ = resolve_config(args)
    assert images == [c]


def test_header_images_loaded_when_no_cli_images(tmp_path):
    f = tmp_path / "v01.txt"
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"fake")
    b.write_bytes(b"fake")
    f.write_text("# images: a.png, b.png\n---\nPrompt")
    args = _make_args(file=f)
    _, images, _, _ = resolve_config(args)
    assert len(images) == 2
    assert images[0].name == "a.png"
    assert images[1].name == "b.png"


def test_multiple_image_flags_collected_in_order(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("Prompt")
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"fake")
    b.write_bytes(b"fake")
    args = _make_args(file=f, images=[a, b])
    _, images, _, _ = resolve_config(args)
    assert images == [a, b]


def test_prompt_text_extracted_from_below_separator(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: gemini\n---\nActual prompt text")
    args = _make_args(file=f)
    _, _, prompt, _ = resolve_config(args)
    assert prompt == "Actual prompt text"
    assert "#" not in prompt


from generate_logo import build_output_path


def test_output_path_with_file_contains_provider_and_stem(tmp_path):
    f = tmp_path / "v01.txt"
    path = build_output_path(f, "gemini", "2026-06-04_14-30-00", tmp_path)
    assert path.name == "v01_gemini_2026-06-04_14-30-00.png"
    assert path.parent == tmp_path


def test_output_path_without_file_uses_output_dir(tmp_path):
    path = build_output_path(None, "fal", "2026-06-04_14-30-00", tmp_path)
    assert path.name == "fal_2026-06-04_14-30-00.png"
    assert path.parent == tmp_path


def test_output_path_provider_in_filename_for_each_provider(tmp_path):
    f = tmp_path / "v01.txt"
    for provider in VALID_PROVIDERS:
        path = build_output_path(f, provider, "2026-06-04_12-00-00", tmp_path)
        assert provider in path.name
