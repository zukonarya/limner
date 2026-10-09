import pytest
import sys
from limner.providers import resolve_provider, VALID_PROVIDERS


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
from limner.generate_logo import resolve_config


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


from limner.generate_logo import build_output_path


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

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from limner.providers.result import ProviderResult
from limner.generate_logo import resolve_aspect_ratio, parse_args, main


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
    argv = ["limner-generate", "-a", "16:9", "--provider", provider, "prompt"]
    with patch.object(sys, "argv", argv), \
         patch("limner.generate_logo.resolve_provider", return_value=generate), \
         patch("limner.generate_logo.get_api_key"):
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
    argv = ["limner-generate", "-a", "3:2", "--provider", "fal", "--image", str(img), "prompt"]
    with patch.object(sys, "argv", argv), \
         patch("limner.providers.fal.fal_client") as mock_fal, \
         patch("limner.generate_logo.get_api_key"):
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
    generate = MagicMock(return_value=ProviderResult(image=b"PNG"))
    argv = ["limner-generate", "-a", "32:18", "--provider", "fal", "--image", str(img),
            "--output-dir", str(tmp_path), "prompt"]
    with patch.object(sys, "argv", argv), \
         patch("limner.generate_logo.validate_images"), \
         patch("limner.generate_logo.resolve_provider", return_value=generate), \
         patch("limner.generate_logo.get_api_key"):
        main()
    generate.assert_called_with("prompt", [img], aspect_ratio="16:9")


def test_main_passes_ratio_only_when_set(tmp_path):
    generate = MagicMock(return_value=ProviderResult(image=b"PNG"))
    base = ["limner-generate", "--output-dir", str(tmp_path), "prompt"]
    with patch("limner.generate_logo.resolve_provider", return_value=generate), \
         patch("limner.generate_logo.get_api_key"):
        with patch.object(sys, "argv", base[:1] + ["-a", "16:9"] + base[1:]):
            main()
        generate.assert_called_with("prompt", [], aspect_ratio="16:9")
        base[2] = str(tmp_path / "second")
        with patch.object(sys, "argv", base):
            main()
        generate.assert_called_with("prompt", [])


def test_help_lists_aspect_ratio(capsys):
    with patch.object(sys, "argv", ["limner-generate", "--help"]):
        with pytest.raises(SystemExit) as exc:
            parse_args()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "-a W:H" in out
    assert "--aspect-ratio W:H" in out


# ── Run receipt ─────────────────────────────────────────────────────────────


def _run(argv, generate):
    with patch.object(sys, "argv", ["limner-generate", *argv]), \
         patch("limner.generate_logo.resolve_provider", return_value=generate), \
         patch("limner.generate_logo.get_api_key"):
        main()


def _prompt_file(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_bytes(b"# provider: gemini\n---\nA blue square\n")
    return f


def test_success_writes_image_and_receipt(tmp_path):
    f = _prompt_file(tmp_path)
    result = ProviderResult(image=b"PNG", endpoint="local", settings_sent={"n": 1})
    _run(["--file", str(f)], MagicMock(return_value=result))
    [image] = tmp_path.glob("*.png")
    receipt = json.loads(image.with_suffix(".run.json").read_text())
    assert image.read_bytes() == b"PNG"
    assert receipt["status"] == "succeeded"
    assert receipt["image"] == image.name
    assert receipt["prompt_file"] == "v01.txt"
    assert receipt["endpoint"] == "local"


def test_inline_prompt_receipt_has_null_prompt_file(tmp_path):
    _run(["--output-dir", str(tmp_path), "A blue square"], MagicMock(return_value=ProviderResult(image=b"PNG")))
    [receipt_path] = tmp_path.glob("*.run.json")
    assert json.loads(receipt_path.read_text())["prompt_file"] is None


def test_provider_error_writes_failed_receipt_and_exits_nonzero(tmp_path, capsys):
    f = _prompt_file(tmp_path)
    with pytest.raises(SystemExit) as exc:
        _run(["--file", str(f)], MagicMock(side_effect=RuntimeError("quota exceeded")))
    assert exc.value.code != 0
    assert "quota exceeded" in capsys.readouterr().out
    assert not list(tmp_path.glob("*.png"))
    [receipt_path] = tmp_path.glob("*.run.json")
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "failed"
    assert receipt["image"] is None
    assert receipt["error"] == {"type": "RuntimeError", "message": "quota exceeded"}
    assert receipt_path.name.startswith("v01_gemini_")


def test_prompt_file_unchanged_after_run(tmp_path):
    f = _prompt_file(tmp_path)
    before = f.read_bytes()
    _run(["--file", str(f)], MagicMock(return_value=ProviderResult(image=b"PNG")))
    assert f.read_bytes() == before
    with pytest.raises(SystemExit):
        _run(["--file", str(f)], MagicMock(side_effect=RuntimeError("boom")))
    assert f.read_bytes() == before


@pytest.mark.parametrize("taken_suffix", [".png", ".run.json"])
def test_taken_name_refused_before_provider_call(tmp_path, taken_suffix):
    f = _prompt_file(tmp_path)
    generate = MagicMock(return_value=ProviderResult(image=b"PNG"))
    with patch("limner.generate_logo.utc_now", return_value=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)):
        taken = tmp_path / f"v01_gemini_{datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc).astimezone():%Y-%m-%d_%H-%M-%S}{taken_suffix}"
        taken.write_bytes(b"original")
        with pytest.raises(SystemExit) as exc:
            _run(["--file", str(f)], generate)
    assert exc.value.code != 0
    generate.assert_not_called()
    assert taken.read_bytes() == b"original"
    assert len(list(tmp_path.iterdir())) == 2


def test_receipt_write_failure_keeps_image_and_exits_nonzero(tmp_path, capsys):
    from limner.core.writeonce import WriteOnceError

    f = _prompt_file(tmp_path)
    with patch("limner.generate_logo.write_receipt", side_effect=WriteOnceError("disk full")):
        with pytest.raises(SystemExit) as exc:
            _run(["--file", str(f)], MagicMock(return_value=ProviderResult(image=b"PNG")))
    assert exc.value.code != 0
    assert "disk full" in capsys.readouterr().out
    assert len(list(tmp_path.glob("*.png"))) == 1


def test_receipt_error_message_is_redacted_but_terminal_is_not(tmp_path, capsys):
    f = _prompt_file(tmp_path)
    secret = "sk-proj-FAKEFAKEFAKEFAKEFAKE1234"
    url = "https://storage.example.com/out.png?X-Signature=abcdef123456"
    error = RuntimeError(f"request to {url} failed with key {secret}")
    with pytest.raises(SystemExit):
        _run(["--file", str(f)], MagicMock(side_effect=error))
    assert secret in capsys.readouterr().out
    [receipt_path] = tmp_path.glob("*.run.json")
    text = receipt_path.read_text()
    assert secret not in text and "FAKEFAKE" not in text
    assert "storage.example.com" not in text and "X-Signature" not in text


def test_failed_receipt_records_what_was_called_and_the_original_error(tmp_path, capsys):
    from limner.providers.result import ProviderError

    f = _prompt_file(tmp_path)
    original = RuntimeError("quota exceeded")
    error = ProviderError(original, endpoint="models.example", model="m-1", settings_sent={"n": 1},
                          provider_response={"request_id": "req-1"})
    error.__cause__ = original
    with pytest.raises(SystemExit):
        _run(["--file", str(f)], MagicMock(side_effect=error))
    assert "RuntimeError: quota exceeded" in capsys.readouterr().out
    [receipt_path] = tmp_path.glob("*.run.json")
    receipt = json.loads(receipt_path.read_text())
    assert (receipt["endpoint"], receipt["model"], receipt["settings_sent"]) == ("models.example", "m-1", {"n": 1})
    assert receipt["provider_response"]["request_id"] == "req-1"
    assert receipt["error"] == {"type": "RuntimeError", "message": "quota exceeded"}
