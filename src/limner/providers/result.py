from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass
class ProviderResult:
    image: bytes
    endpoint: str | None = None
    model: str | None = None
    settings_sent: dict = field(default_factory=dict)
    provider_response: dict = field(default_factory=dict)


def provider_response(request_id=None, seed=None, model_version=None, usage=None) -> dict:
    return {
        "request_id": request_id,
        "seed": seed,
        "model_version": model_version,
        "usage": usage.model_dump(mode="json") if isinstance(usage, BaseModel) else usage,
    }
