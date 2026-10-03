import pytest
from datetime import datetime
from pathlib import Path
from limner.core.metadata import parse_header, write_output_metadata


def test_parse_header_extracts_provider():
    content = "# provider: fal\n---\nMy prompt"
    header, prompt = parse_header(content)
    assert header["provider"] == "fal"


def test_parse_header_extracts_images():
    content = "# images: a.png, b.png\n---\nMy prompt"
    header, prompt = parse_header(content)
    assert header["images"] == "a.png, b.png"


def test_parse_header_extracts_prompt_below_separator():
    content = "# provider: gemini\n---\nMy actual prompt\nline two"
    header, prompt = parse_header(content)
    assert prompt == "My actual prompt\nline two"


def test_parse_header_no_header_returns_full_content():
    content = "Plain prompt with no header."
    header, prompt = parse_header(content)
    assert header == {}
    assert prompt == "Plain prompt with no header."


def test_parse_header_multiple_fields():
    content = "# provider: openai\n# images: shot.png\n---\nPrompt here"
    header, prompt = parse_header(content)
    assert header["provider"] == "openai"
    assert header["images"] == "shot.png"
    assert prompt == "Prompt here"


def test_write_output_metadata_appends_to_header(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: gemini\n---\nMy prompt")
    out = tmp_path / "v01_gemini_2026-06-04_14-30-00.png"
    write_output_metadata(f, out, datetime(2026, 6, 4, 14, 30, 0))
    content = f.read_text()
    assert "# output: v01_gemini_2026-06-04_14-30-00.png" in content
    assert "# timestamp: 2026-06-04T14:30:00" in content
    assert "My prompt" in content


def test_write_output_metadata_preserves_prompt(tmp_path):
    f = tmp_path / "v01.txt"
    f.write_text("# provider: gemini\n---\nOriginal prompt text")
    out = tmp_path / "out.png"
    write_output_metadata(f, out, datetime(2026, 6, 4, 12, 0, 0))
    _, prompt = parse_header(f.read_text())
    assert prompt == "Original prompt text"


def test_write_output_metadata_noop_without_header(tmp_path):
    f = tmp_path / "plain.txt"
    original = "Plain prompt"
    f.write_text(original)
    write_output_metadata(f, tmp_path / "out.png", datetime.now())
    assert f.read_text() == original
