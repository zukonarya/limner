import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_store_root(tmp_path, monkeypatch):
    """Keeps every test away from the live store that code/.env names; load_dotenv never overrides a set value."""
    root = tmp_path / "live-store"
    monkeypatch.setenv("LIMNER_STORE_DIR", str(root))
    return root


@pytest.fixture
def prompt_file_with_header(tmp_path):
    """A .txt prompt file with a full metadata header."""
    f = tmp_path / "v01.txt"
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    img_a.write_bytes(b"fake")
    img_b.write_bytes(b"fake")
    f.write_text(
        "# provider: gemini\n"
        "# images: a.png, b.png\n"
        "---\n"
        "A marketing image prompt."
    )
    return f


@pytest.fixture
def prompt_file_plain(tmp_path):
    """A .txt prompt file with no header."""
    f = tmp_path / "v01.txt"
    f.write_text("A plain prompt with no header.")
    return f
