import io

import pytest
from PIL import Image

from logo_generator.providers import resolve_provider

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_composite_resolves_and_renders_png(tmp_path):
    source = tmp_path / "screenshot.png"
    Image.new("RGB", (100, 60), (40, 90, 160)).save(source)

    generate = resolve_provider("composite")
    result = generate("ignored prompt", [source])

    assert result.startswith(PNG_SIGNATURE)
    with Image.open(io.BytesIO(result)) as decoded:
        assert decoded.format == "PNG"
        assert decoded.size == (1440, 900)


def test_composite_without_images_raises_value_error():
    generate = resolve_provider("composite")

    with pytest.raises(ValueError, match="at least one --image"):
        generate("ignored prompt", [])
