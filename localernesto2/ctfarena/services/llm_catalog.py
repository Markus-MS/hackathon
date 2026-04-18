from __future__ import annotations

from decimal import Decimal, InvalidOperation

import requests

from ctfarena.telemetry import metric_count, start_span


class LLMCatalogError(RuntimeError):
    pass


def list_model_catalog(provider: str, api_key: str, *, timeout: int = 15) -> list[dict[str, object]]:
    provider = provider.lower().strip()
    if provider == "openai":
        return [{"id": model_id} for model_id in _list_openai_models(api_key=api_key, timeout=timeout)]
    if provider == "openrouter":
        return _list_openrouter_models(api_key=api_key, timeout=timeout)
    raise LLMCatalogError(
        f"Model loading is not implemented for {provider}. Type the model name manually."
    )


def list_models(provider: str, api_key: str, *, timeout: int = 15) -> list[str]:
    return [str(item["id"]) for item in list_model_catalog(provider, api_key, timeout=timeout)]


def _list_openai_models(*, api_key: str, timeout: int) -> list[str]:
    with start_span(
        op="provider.catalog",
        name="provider.openai.list_models",
        attributes={"provider": "openai"},
    ):
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    if not response.ok:
        metric_count("ctfarena.provider.catalog.error", 1, tags={"provider": "openai"})
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
    metric_count("ctfarena.provider.catalog.success", 1, tags={"provider": "openai"})
    return llm_models or model_ids


def _list_openrouter_models(*, api_key: str, timeout: int) -> list[dict[str, object]]:
    response = requests.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    if not response.ok:
        raise LLMCatalogError(_openrouter_error_message(response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMCatalogError("OpenRouter returned a non-JSON model list.") from exc

    items = payload.get("data")
    if not isinstance(items, list):
        raise LLMCatalogError("OpenRouter returned an unexpected model list shape.")

    catalog: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id or not _looks_like_openrouter_llm(item):
            continue
        try:
            rate_card = openrouter_rate_card(model_id, item.get("pricing"))
        except LLMCatalogError:
            continue
        catalog.append(
            {
                "id": model_id,
                "name": str(item.get("name") or model_id),
                "pricing": rate_card,
            }
        )
    catalog.sort(key=lambda item: str(item["id"]))
    return catalog


def openrouter_rate_card(model_id: str, pricing: object) -> dict[str, float]:
    if not isinstance(pricing, dict):
        raise LLMCatalogError(f"OpenRouter did not return pricing for {model_id}.")
    return {
        "input_per_million": _price_to_per_million(pricing.get("prompt")),
        "output_per_million": _price_to_per_million(pricing.get("completion")),
        "cached_input_per_million": 0.0,
        "reasoning_per_million": 0.0,
    }


def _price_to_per_million(value: object) -> float:
    try:
        return float(Decimal(str(value or "0")) * Decimal("1000000"))
    except (InvalidOperation, ValueError):
        return 0.0


def _looks_like_openrouter_llm(item: dict[str, object]) -> bool:
    architecture = item.get("architecture")
    if isinstance(architecture, dict):
        modality = str(architecture.get("modality") or "").lower()
        if modality and not modality.startswith("text->"):
            return False
        output_modalities = architecture.get("output_modalities")
        if isinstance(output_modalities, list) and "text" not in {
            str(value).lower() for value in output_modalities
        }:
            return False
    return True


def _openai_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"OpenAI model lookup failed with HTTP {response.status_code}."

    error = payload.get("error")
    if isinstance(error, dict) and error.get("message"):
        return f"OpenAI model lookup failed: {error['message']}"
    return f"OpenAI model lookup failed with HTTP {response.status_code}."


def _openrouter_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"OpenRouter model lookup failed with HTTP {response.status_code}."

    error = payload.get("error")
    if isinstance(error, dict) and error.get("message"):
        return f"OpenRouter model lookup failed: {error['message']}"
    if isinstance(payload.get("message"), str) and payload["message"].strip():
        return f"OpenRouter model lookup failed: {payload['message']}"
    return f"OpenRouter model lookup failed with HTTP {response.status_code}."


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
