import io
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from limner.providers.result import ProviderError


# ── Gemini ──────────────────────────────────────────────────────────────────

def _make_gemini_response(image_bytes: bytes, text: str = "") -> MagicMock:
    """Build a mock Gemini API response containing one image part."""
    image_part = MagicMock()
    image_part.text = None
    image_part.inline_data = MagicMock()
    image_part.inline_data.data = image_bytes

    text_part = MagicMock()
    text_part.text = text
    text_part.inline_data = None

    response = MagicMock()
    response.candidates[0].content.parts = [text_part, image_part] if text else [image_part]
    response.response_id = "resp-1"
    response.model_version = "model-v1"
    response.usage_metadata = None
    return response


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_text_only_passes_string_contents(mock_client_cls, tmp_path):
    mock_client = mock_client_cls.return_value
    mock_client.models.generate_content.return_value = _make_gemini_response(b"PNG_BYTES")

    from limner.providers.gemini import generate
    result = generate("A logo prompt", [])

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["contents"] == "A logo prompt"
    assert isinstance(result.image, bytes)


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_with_images_passes_list_contents(mock_client_cls, tmp_path):
    mock_client = mock_client_cls.return_value
    mock_client.models.generate_content.return_value = _make_gemini_response(b"PNG_BYTES")

    img = tmp_path / "shot.png"
    img.write_bytes(b"fake_png")

    from limner.providers.gemini import generate
    result = generate("A composition prompt", [img])

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    contents = call_kwargs["contents"]
    assert isinstance(contents, list)
    assert contents[-1] == "A composition prompt"
    assert len(contents) == 2  # 1 image part + text
    assert isinstance(result.image, bytes)


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_raises_on_no_image_in_response(mock_client_cls):
    mock_client = mock_client_cls.return_value
    response = MagicMock(response_id="resp-1", model_version="model-v1", usage_metadata=None)
    text_part = MagicMock()
    text_part.text = "some text"
    text_part.inline_data = None
    response.candidates[0].content.parts = [text_part]
    mock_client.models.generate_content.return_value = response

    from limner.providers.gemini import generate
    with pytest.raises(ProviderError) as exc:
        generate("prompt", [])
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert "No image returned" in str(exc.value.__cause__)
    assert exc.value.provider_response["request_id"] == "resp-1"
    assert exc.value.provider_response["model_version"] == "model-v1"
    assert exc.value.model == "gemini-3-pro-image"


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_blocked_response_with_no_candidates_raises_provider_error(mock_client_cls):
    response = MagicMock(candidates=[], response_id="resp-2", model_version="model-v1", usage_metadata=None)
    mock_client_cls.return_value.models.generate_content.return_value = response
    from limner.providers.gemini import generate
    with pytest.raises(ProviderError) as exc:
        generate("prompt", [])
    assert str(exc.value.__cause__) == "No image returned in Gemini response."
    assert exc.value.provider_response["request_id"] == "resp-2"


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_default_aspect_ratio_is_square(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_client.models.generate_content.return_value = _make_gemini_response(b"PNG_BYTES")

    from limner.providers.gemini import generate
    generate("prompt", [])

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.image_config.aspect_ratio == "1:1"
    assert config.image_config.image_size == "1K"


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_aspect_ratio_reaches_request_config(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_client.models.generate_content.return_value = _make_gemini_response(b"PNG_BYTES")

    from limner.providers.gemini import generate
    generate("prompt", [], aspect_ratio="16:9")

    config = mock_client.models.generate_content.call_args.kwargs["config"]
    assert config.image_config.aspect_ratio == "16:9"
    assert config.image_config.image_size == "1K"


# ── fal.ai ──────────────────────────────────────────────────────────────────

@patch("limner.providers.fal.fal_client")
def test_fal_uploads_each_image_and_calls_subscribe(mock_fal, tmp_path):
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    img_a.write_bytes(b"fake")
    img_b.write_bytes(b"fake")

    mock_fal.upload_file.side_effect = ["https://cdn.fal/a.png", "https://cdn.fal/b.png"]
    mock_fal.subscribe.return_value = {
        "images": [{"url": "https://cdn.fal/output.png"}]
    }

    import urllib.request
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read.return_value = b"OUTPUT_PNG_BYTES"

        from limner.providers.fal import generate
        result = generate("A marketing prompt", [img_a, img_b])

    assert mock_fal.upload_file.call_count == 2
    subscribe_kwargs = mock_fal.subscribe.call_args
    assert subscribe_kwargs[0][0] == "fal-ai/flux-2-pro/edit"
    assert "https://cdn.fal/a.png" in subscribe_kwargs[1]["arguments"]["image_urls"]
    assert "https://cdn.fal/b.png" in subscribe_kwargs[1]["arguments"]["image_urls"]
    assert result.image == b"OUTPUT_PNG_BYTES"


@patch("limner.providers.fal.fal_client")
def test_fal_passes_prompt_in_arguments(mock_fal, tmp_path):
    mock_fal.upload_file.return_value = "https://cdn.fal/a.png"
    mock_fal.subscribe.return_value = {"images": [{"url": "https://cdn.fal/out.png"}]}

    img = tmp_path / "a.png"
    img.write_bytes(b"fake")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read.return_value = b"bytes"

        from limner.providers.fal import generate
        generate("My prompt text", [img])

    args = mock_fal.subscribe.call_args[1]["arguments"]
    assert args["prompt"] == "My prompt text"


def _fal_arguments(tmp_path, **kwargs):
    img = tmp_path / "a.png"
    img.write_bytes(b"fake")
    with patch("limner.providers.fal.fal_client") as mock_fal, \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_fal.upload_file.return_value = "https://cdn.fal/a.png"
        mock_fal.subscribe.return_value = {"images": [{"url": "https://cdn.fal/out.png"}]}
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read.return_value = b"bytes"

        from limner.providers.fal import generate
        generate("p", [img], **kwargs)
    return mock_fal.subscribe.call_args[1]["arguments"]


@pytest.mark.parametrize("ratio,size", [
    ("1:1", "square_hd"),
    ("4:3", "landscape_4_3"),
    ("3:4", "portrait_4_3"),
    ("16:9", "landscape_16_9"),
    ("9:16", "portrait_16_9"),
    ("2:2", "square_hd"),
    ("32:18", "landscape_16_9"),
])
def test_fal_maps_ratio_to_image_size(tmp_path, ratio, size):
    assert _fal_arguments(tmp_path, aspect_ratio=ratio)["image_size"] == size


def test_fal_without_ratio_sends_no_image_size(tmp_path):
    assert _fal_arguments(tmp_path) == {
        "prompt": "p",
        "image_urls": ["https://cdn.fal/a.png"],
        "output_format": "png",
    }


import base64

# ── OpenAI ───────────────────────────────────────────────────────────────────

@patch("limner.providers.openai_provider.OpenAI")
def test_openai_calls_images_edit_with_file_objects(mock_openai_cls, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"fake_png")

    raw = b"OUTPUT_PNG_BYTES"
    mock_client = mock_openai_cls.return_value
    mock_result = MagicMock()
    mock_result.data[0].b64_json = base64.b64encode(raw).decode()
    mock_result.usage = None
    mock_client.images.edit.return_value = mock_result

    from limner.providers.openai_provider import generate
    result = generate("A marketing prompt", [img])

    call_kwargs = mock_client.images.edit.call_args.kwargs
    assert call_kwargs["model"] == "gpt-image-2"
    assert call_kwargs["prompt"] == "A marketing prompt"
    assert result.image == raw


@patch("limner.providers.openai_provider.OpenAI")
def test_openai_passes_list_for_multiple_images(mock_openai_cls, tmp_path):
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    img_a.write_bytes(b"fake")
    img_b.write_bytes(b"fake")

    raw = b"OUTPUT"
    mock_client = mock_openai_cls.return_value
    mock_result = MagicMock()
    mock_result.data[0].b64_json = base64.b64encode(raw).decode()
    mock_result.usage = None
    mock_client.images.edit.return_value = mock_result

    from limner.providers.openai_provider import generate
    generate("prompt", [img_a, img_b])

    call_kwargs = mock_client.images.edit.call_args.kwargs
    assert isinstance(call_kwargs["image"], list)
    assert len(call_kwargs["image"]) == 2


@patch("limner.providers.openai_provider.OpenAI")
def test_openai_returns_decoded_bytes(mock_openai_cls, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"fake")

    raw = b"\x89PNG\r\n"
    mock_client = mock_openai_cls.return_value
    mock_result = MagicMock()
    mock_result.data[0].b64_json = base64.b64encode(raw).decode()
    mock_result.usage = None
    mock_client.images.edit.return_value = mock_result

    from limner.providers.openai_provider import generate
    result = generate("prompt", [img])
    assert result.image == raw


# ── Receipt metadata ─────────────────────────────────────────────────────────

import json
import typing

from google.genai import types as genai_types
from openai.types.images_response import ImagesResponse, Usage as OpenAIUsage


def _model_fields(model):
    return sorted(model.model_fields)


def _inner(model, name):
    ann = model.model_fields[name].annotation
    return next(a for a in (typing.get_args(ann) or (ann,)) if hasattr(a, "model_fields"))


def test_openai_usage_field_set_is_pinned():
    # A field added by an SDK upgrade fails here so it gets reviewed.
    assert _model_fields(OpenAIUsage) == [
        "input_tokens", "input_tokens_details", "output_tokens",
        "output_tokens_details", "total_tokens",
    ]
    for name in ("input_tokens_details", "output_tokens_details"):
        assert _model_fields(_inner(OpenAIUsage, name)) == ["image_tokens", "text_tokens"]


def test_gemini_usage_field_set_is_pinned():
    usage = genai_types.GenerateContentResponseUsageMetadata
    assert _model_fields(usage) == [
        "cache_tokens_details", "cached_content_token_count", "candidates_token_count",
        "candidates_tokens_details", "prompt_token_count", "prompt_tokens_details",
        "thoughts_token_count", "tool_use_prompt_token_count",
        "tool_use_prompt_tokens_details", "total_token_count", "traffic_type",
    ]


@patch("limner.providers.openai_provider.OpenAI")
def test_openai_metadata_serialises_usage_with_nested_details(mock_openai_cls, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"fake")
    usage = OpenAIUsage(
        input_tokens=10, output_tokens=20, total_tokens=30,
        input_tokens_details={"image_tokens": 4, "text_tokens": 6},
        output_tokens_details={"image_tokens": 20, "text_tokens": 0},
    )
    mock_result = MagicMock()
    mock_result.data[0].b64_json = base64.b64encode(b"x").decode()
    mock_result.usage = usage
    mock_result._request_id = "req-oa"
    mock_openai_cls.return_value.images.edit.return_value = mock_result

    from limner.providers.openai_provider import generate
    result = generate("secret prompt", [img])

    assert result.endpoint == "images.edit"
    assert result.model == "gpt-image-2"
    assert result.settings_sent == {"output_format": "png"}
    assert result.provider_response == {
        "request_id": "req-oa", "seed": None, "model_version": None,
        "usage": usage.model_dump(mode="json"),
    }
    assert result.provider_response["usage"]["input_tokens_details"] == {
        "image_tokens": 4, "text_tokens": 6,
    }
    json.dumps(result.provider_response)


@patch("limner.providers.openai_provider.OpenAI")
def test_openai_metadata_is_null_when_missing(mock_openai_cls, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"fake")
    mock_result = ImagesResponse(created=1, data=[{"b64_json": base64.b64encode(b"x").decode()}])
    mock_openai_cls.return_value.images.edit.return_value = mock_result

    from limner.providers.openai_provider import generate
    result = generate("p", [img])

    assert result.provider_response == {
        "request_id": None, "seed": None, "model_version": None, "usage": None,
    }


@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_metadata(mock_client_cls):
    usage = genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=5, total_token_count=9,
        prompt_tokens_details=[{"modality": "TEXT", "token_count": 5}],
    )
    response = _make_gemini_response(b"PNG_BYTES", text="a note")
    response.usage_metadata = usage
    mock_client_cls.return_value.models.generate_content.return_value = response

    from limner.providers.gemini import generate
    result = generate("secret prompt", [], aspect_ratio="16:9")

    assert result.endpoint == "models.generate_content"
    assert result.model == "gemini-3-pro-image"
    assert result.settings_sent["image_config"] == {"aspect_ratio": "16:9", "image_size": "1K"}
    assert "secret prompt" not in json.dumps(result.settings_sent)
    assert result.provider_response == {
        "request_id": "resp-1", "seed": None, "model_version": "model-v1",
        "usage": usage.model_dump(mode="json"),
    }
    assert result.provider_response["usage"]["prompt_tokens_details"][0]["token_count"] == 5
    json.dumps(result.provider_response)


def _fal_run(tmp_path, subscribe_result, request_id="req-fal"):
    img = tmp_path / "a.png"
    img.write_bytes(b"fake")

    def subscribe(application, arguments, on_enqueue=None):
        if request_id is not None:
            on_enqueue(request_id)
        return subscribe_result

    with patch("limner.providers.fal.fal_client") as mock_fal, \
         patch("urllib.request.urlopen") as mock_urlopen:
        mock_fal.upload_file.return_value = "https://cdn.fal/a.png"
        mock_fal.subscribe.side_effect = subscribe
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value.read.return_value = b"bytes"

        from limner.providers.fal import generate
        return generate("secret prompt", [img], aspect_ratio="1:1")


def test_fal_metadata_has_request_id_and_seed(tmp_path):
    result = _fal_run(tmp_path, {"images": [{"url": "https://cdn.fal/o.png"}], "seed": 42})

    assert result.endpoint == "fal-ai/flux-2-pro/edit"
    assert result.model is None
    assert result.settings_sent == {"output_format": "png", "image_size": "square_hd"}
    assert result.provider_response == {
        "request_id": "req-fal", "seed": 42, "model_version": None, "usage": None,
    }


def test_fal_metadata_is_null_when_missing(tmp_path):
    result = _fal_run(tmp_path, {"images": [{"url": "https://cdn.fal/o.png"}]}, request_id=None)

    assert result.provider_response == {
        "request_id": None, "seed": None, "model_version": None, "usage": None,
    }


# ── Failure metadata ─────────────────────────────────────────────────────────

@patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
@patch("limner.providers.gemini.genai.Client")
def test_gemini_failure_raises_provider_error(mock_client_cls, tmp_path):
    original = RuntimeError("quota exceeded")
    mock_client_cls.return_value.models.generate_content.side_effect = original
    from limner.providers.gemini import generate
    with pytest.raises(ProviderError) as exc:
        generate("p", [], aspect_ratio="16:9")
    assert exc.value.__cause__ is original
    assert exc.value.endpoint == "models.generate_content"
    assert exc.value.model == "gemini-3-pro-image"
    assert exc.value.settings_sent["image_config"]["aspect_ratio"] == "16:9"


@patch("limner.providers.openai_provider.OpenAI")
def test_openai_failure_raises_provider_error(mock_openai_cls, tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"fake")
    original = RuntimeError("rate limited")
    mock_openai_cls.return_value.images.edit.side_effect = original
    from limner.providers.openai_provider import generate
    with pytest.raises(ProviderError) as exc:
        generate("p", [img])
    assert exc.value.__cause__ is original
    assert (exc.value.endpoint, exc.value.model) == ("images.edit", "gpt-image-2")
    assert exc.value.settings_sent == {"output_format": "png"}


def test_fal_failure_carries_queued_request_id(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"fake")
    original = RuntimeError("job failed")

    def subscribe(application, arguments, on_enqueue=None):
        on_enqueue("req-fal")
        raise original

    with patch("limner.providers.fal.fal_client") as mock_fal:
        mock_fal.upload_file.return_value = "https://cdn.fal/a.png"
        mock_fal.subscribe.side_effect = subscribe
        from limner.providers.fal import generate
        with pytest.raises(ProviderError) as exc:
            generate("p", [img], aspect_ratio="1:1")
    assert exc.value.__cause__ is original
    assert exc.value.endpoint == "fal-ai/flux-2-pro/edit"
    assert exc.value.model is None
    assert exc.value.settings_sent == {"output_format": "png", "image_size": "square_hd"}
    assert exc.value.provider_response["request_id"] == "req-fal"


def test_composite_failure_raises_provider_error(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    from limner.providers.composite import generate
    with pytest.raises(ProviderError) as exc:
        generate("p", [bad])
    assert exc.value.endpoint == "local"
