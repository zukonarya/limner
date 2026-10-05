import pytest
from limner.core.metadata import parse_header


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


def test_parse_header_hash_first_line_without_separator_is_prompt():
    content = "#1A2B3C is the brand colour"
    assert parse_header(content) == ({}, content)


def test_parse_header_non_comment_line_before_separator_is_prompt():
    content = "# provider: fal\nnot a comment\n---\nBody"
    header, prompt = parse_header(content)
    assert header == {}
    assert prompt == content


def test_parse_header_only_first_separator_ends_header():
    header, prompt = parse_header("# provider: fal\n---\nTop\n---\nBottom")
    assert header == {"provider": "fal"}
    assert prompt == "Top\n---\nBottom"


def test_parse_header_old_output_keys_still_parse():
    header, _ = parse_header("# provider: fal\n# output: a.png\n# timestamp: 2026-01-01T00:00:00\n---\nP")
    assert header["output"] == "a.png"
    assert header["timestamp"] == "2026-01-01T00:00:00"


def test_parse_header_blank_lines_before_separator_allowed():
    header, prompt = parse_header("# provider: fal\n\n---\nP")
    assert header == {"provider": "fal"}
    assert prompt == "P"


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_parse_header_alternate_line_endings(newline):
    content = newline.join(["# provider: fal", "# images: a.png", "---", "line one", "line two"])
    header, prompt = parse_header(content)
    assert header == {"provider": "fal", "images": "a.png"}
    assert prompt == "line one\nline two"


def test_parse_header_separator_with_trailing_text_is_not_separator():
    content = "# provider: fal\n--- \nBody"
    assert parse_header(content) == ({}, content)
