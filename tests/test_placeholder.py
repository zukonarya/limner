import io
import subprocess
import sys

from unittest.mock import patch

import pytest
from PIL import Image

from limner.core.placeholder import render_placeholder


@pytest.mark.parametrize(
    "ratio, size",
    [
        (None, (1024, 1024)),
        ("16:9", (1024, 576)),
        ("9:16", (576, 1024)),
        ("4:3", (1024, 768)),
        ("1920:1080", (1024, 576)),
        ("100:1", (1024, 10)),
        ("1:100", (10, 1024)),
        ("5000:1", (1024, 1)),
    ],
)
def test_placeholder_size_follows_ratio(ratio, size):
    image = Image.open(io.BytesIO(render_placeholder("fal", ratio)))
    assert image.format == "PNG"
    assert image.size == size


def test_aspect_module_imports_no_provider_sdk():
    code = (
        "import sys, limner.core.aspect, limner.core.placeholder; "
        "print('limner.providers.fal' in sys.modules or 'fal_client' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_the_placeholder_is_marked_with_the_word_test_and_the_provider():
    with patch("limner.core.placeholder.ImageDraw.Draw") as draw:
        render_placeholder("fal")
    assert draw.return_value.text.call_args.args[1] == "TEST fal"
    marked = Image.open(io.BytesIO(render_placeholder("fal")))
    assert any(low != high for low, high in marked.getextrema())
