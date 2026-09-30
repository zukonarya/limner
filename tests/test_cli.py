import pytest
import sys
from logo_generator.providers import resolve_provider, VALID_PROVIDERS


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
from logo_generator.generate_logo import resolve_config


def _make_args(provider=None, file=None, prompt=None, images=None, aspect_ratio=None):
    ns = builtin_types.SimpleNamespace()
    ns.provider = provider
    ns.file = file
    ns.prompt = prompt
    ns.images = images or []
    ns.aspect_ratio = aspect_ratio
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


from logo_generator.generate_logo import build_output_path


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


# ── Aspect ratio ────────────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch
from logo_generator.generate_logo import resolve_aspect_ratio, parse_args, main


def test_aspect_ratio_unset_by_default(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("Plain prompt")
    assert resolve_aspect_ratio(_make_args(file=f), "gemini") is None


def test_aspect_ratio_from_header(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# aspect_ratio: 16:9\n---\nPrompt")
    assert resolve_aspect_ratio(_make_args(file=f), "gemini") == "16:9"


def test_aspect_ratio_header_whitespace_trimmed(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# aspect_ratio:   4:3  \n---\nPrompt")
    assert resolve_aspect_ratio(_make_args(file=f), "gemini") == "4:3"


def test_aspect_ratio_flag_overrides_header(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# aspect_ratio: 16:9\n---\nPrompt")
    args = _make_args(file=f, aspect_ratio="9:16")
    assert resolve_aspect_ratio(args, "gemini") == "9:16"


def test_aspect_ratio_flag_with_inline_prompt():
    args = _make_args(prompt="inline", aspect_ratio="3:2")
    assert resolve_aspect_ratio(args, "gemini") == "3:2"


@pytest.mark.parametrize("bad", ["wide", "16-9", "0:9", "16:0", "16:", ":9", "1.5:2", "-1:2", "16:9:1", ""])
def test_aspect_ratio_malformed_exits(bad, capsys):
    with pytest.raises(SystemExit) as exc:
        resolve_aspect_ratio(_make_args(prompt="p", aspect_ratio=bad), "gemini")
    assert exc.value.code == 1
    assert "positive integers" in capsys.readouterr().out


def test_malformed_header_ratio_exits(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# aspect_ratio: wide\n---\nPrompt")
    with pytest.raises(SystemExit):
        resolve_aspect_ratio(_make_args(file=f), "gemini")


@pytest.mark.parametrize("provider", ["openai", "composite"])
def test_aspect_ratio_rejected_for_non_gemini_before_provider_call(provider, capsys):
    generate = MagicMock()
    argv = ["logo-generate", "-a", "16:9", "--provider", provider, "prompt"]
    with patch.object(sys, "argv", argv), \
         patch("logo_generator.generate_logo.resolve_provider", return_value=generate), \
         patch("logo_generator.generate_logo.get_api_key"):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    assert provider in capsys.readouterr().out
    generate.assert_not_called()


def test_header_ratio_rejected_for_non_gemini_provider(tmp_path, capsys):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: openai\n# aspect_ratio: 16:9\n---\nPrompt")
    with pytest.raises(SystemExit):
        resolve_aspect_ratio(_make_args(file=f, provider="openai"), "openai")
    assert "openai" in capsys.readouterr().out


@pytest.mark.parametrize("given,expected", [("16:9", "16:9"), ("2:2", "1:1"), ("32:18", "16:9")])
def test_fal_ratio_accepted_and_reduced(given, expected):
    args = _make_args(prompt="p", aspect_ratio=given)
    assert resolve_aspect_ratio(args, "fal") == expected


def test_fal_header_ratio_resolved(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: fal\n# aspect_ratio: 9:16\n---\nPrompt")
    assert resolve_aspect_ratio(_make_args(file=f), "fal") == "9:16"


def test_fal_cli_ratio_overrides_header(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: fal\n# aspect_ratio: 9:16\n---\nPrompt")
    args = _make_args(file=f, aspect_ratio="4:3")
    assert resolve_aspect_ratio(args, "fal") == "4:3"


def test_fal_unsupported_ratio_exits_before_upload(tmp_path, capsys):
    img = tmp_path / "ref.png"
    img.write_bytes(b"fake")
    argv = ["logo-generate", "-a", "3:2", "--provider", "fal", "--image", str(img), "prompt"]
    with patch.object(sys, "argv", argv), \
         patch("logo_generator.providers.fal.fal_client") as mock_fal, \
         patch("logo_generator.generate_logo.get_api_key"):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    for ratio in ("1:1", "4:3", "3:4", "16:9", "9:16"):
        assert ratio in out
    mock_fal.upload_file.assert_not_called()
    mock_fal.subscribe.assert_not_called()


def test_main_passes_reduced_fal_ratio(tmp_path):
    img = tmp_path / "ref.png"
    img.write_bytes(b"fake")
    generate = MagicMock(return_value=b"PNG")
    argv = ["logo-generate", "-a", "32:18", "--provider", "fal", "--image", str(img),
            "--output-dir", str(tmp_path), "prompt"]
    with patch.object(sys, "argv", argv), \
         patch("logo_generator.generate_logo.validate_images"), \
         patch("logo_generator.generate_logo.resolve_provider", return_value=generate), \
         patch("logo_generator.generate_logo.get_api_key"):
        main()
    generate.assert_called_with("prompt", [img], aspect_ratio="16:9")


def test_main_passes_ratio_only_when_set(tmp_path):
    generate = MagicMock(return_value=b"PNG")
    base = ["logo-generate", "--output-dir", str(tmp_path), "prompt"]
    with patch("logo_generator.generate_logo.resolve_provider", return_value=generate), \
         patch("logo_generator.generate_logo.get_api_key"):
        with patch.object(sys, "argv", base[:1] + ["-a", "16:9"] + base[1:]):
            main()
        generate.assert_called_with("prompt", [], aspect_ratio="16:9")
        with patch.object(sys, "argv", base):
            main()
        generate.assert_called_with("prompt", [])


def test_help_lists_aspect_ratio(capsys):
    with patch.object(sys, "argv", ["logo-generate", "--help"]):
        with pytest.raises(SystemExit) as exc:
            parse_args()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "-a W:H" in out
    assert "--aspect-ratio W:H" in out
