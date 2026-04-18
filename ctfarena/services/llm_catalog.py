from __future__ import annotations

import requests


class LLMCatalogError(RuntimeError):
    pass


def list_models(provider: str, api_key: str, *, timeout: int = 15) -> list[str]:
    provider = provider.lower().strip()
    if provider == "openai":
        return _list_openai_models(api_key=api_key, timeout=timeout)
    raise LLMCatalogError(
        f"Model loading is not implemented for {provider}. Type the model name manually."
    )


def _list_openai_models(*, api_key: str, timeout: int) -> list[str]:
    response = requests.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    if not response.ok:
        raise LLMCatalogError(_openai_error_message(response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMCatalogError("OpenAI returned a non-JSON model list.") from exc

    items = payload.get("data")
    if not isinstance(items, list):
        raise LLMCatalogError("OpenAI returned an unexpected model list shape.")

    model_ids = sorted(
        {
            str(item.get("id"))
            for item in items
            if isinstance(item, dict) and item.get("id")
        }
    )
    llm_models = [model_id for model_id in model_ids if _looks_like_openai_llm(model_id)]
    return llm_models or model_ids


def _openai_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"OpenAI model lookup failed with HTTP {response.status_code}."

    error = payload.get("error")
    if isinstance(error, dict) and error.get("message"):
        return f"OpenAI model lookup failed: {error['message']}"
    return f"OpenAI model lookup failed with HTTP {response.status_code}."


def _looks_like_openai_llm(model_id: str) -> bool:
    lowered = model_id.lower()
    excluded_fragments = {
        "audio",
        "dall-e",
        "embedding",
        "image",
        "moderation",
        "realtime",
        "speech",
        "transcribe",
        "tts",
        "whisper",
    }
    if any(fragment in lowered for fragment in excluded_fragments):
        return False
    return lowered.startswith(("chatgpt-", "codex-", "gpt-", "o"))
