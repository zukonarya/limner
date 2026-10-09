import io
import subprocess
import sys

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
