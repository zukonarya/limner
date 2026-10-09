from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class ProviderResult:
    image: bytes
    endpoint: str | None = None
    model: str | None = None
    settings_sent: dict = field(default_factory=dict)
    provider_response: dict = field(default_factory=dict)


class ProviderError(Exception):
    """A failed provider call, carrying what was called so the failed receipt can record it."""

    def __init__(self, cause, endpoint=None, model=None, settings_sent=None, provider_response=None):
        super().__init__(str(cause))
        self.endpoint = endpoint
        self.model = model
        self.settings_sent = settings_sent or {}
        self.provider_response = provider_response or {}


def provider_response(request_id=None, seed=None, model_version=None, usage=None) -> dict:
    return {
        "request_id": request_id,
        "seed": seed,
        "model_version": model_version,
        "usage": usage.model_dump(mode="json") if isinstance(usage, BaseModel) else usage,
    }
