from limner.core.errorlog import fail

VALID_PROVIDERS = ["gemini", "fal", "openai", "composite"]


def resolve_provider(name: str):
    if name not in VALID_PROVIDERS:
        fail(f"Error: unknown provider '{name}'. Valid: {', '.join(VALID_PROVIDERS)}")
    if name == "gemini":
        from .gemini import generate
    elif name == "fal":
        from .fal import generate
    elif name == "openai":
        from .openai_provider import generate
    elif name == "composite":
        from .composite import generate
    return generate
