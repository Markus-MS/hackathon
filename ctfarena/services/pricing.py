from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from flask import current_app

from ctfarena.db import get_setting, set_setting


DYNAMIC_RATE_SETTING = "dynamic_model_rates"

@lru_cache(maxsize=1)
def _load_static_rates(path: str) -> dict[str, dict[str, float]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_rate_table() -> dict[str, dict[str, float]]:
    return _load_static_rates(str(current_app.config["MODEL_RATE_FILE"])) | _load_dynamic_rates()


def _load_dynamic_rates() -> dict[str, dict[str, float]]:
    raw_value = get_setting(DYNAMIC_RATE_SETTING, "{}") or "{}"
    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}

    rates: dict[str, dict[str, float]] = {}
    for rate_key, rate in payload.items():
        if not isinstance(rate_key, str) or not isinstance(rate, dict):
            continue
        normalized = _normalize_rate(rate)
        if normalized is not None:
            rates[rate_key] = normalized
    return rates


def _normalize_rate(rate: dict[str, object]) -> dict[str, float] | None:
    try:
        return {
            "input_per_million": float(rate.get("input_per_million", 0.0)),
            "output_per_million": float(rate.get("output_per_million", 0.0)),
            "cached_input_per_million": float(rate.get("cached_input_per_million", 0.0)),
            "reasoning_per_million": float(rate.get("reasoning_per_million", 0.0)),
        }
    except (TypeError, ValueError):
        return None


def upsert_dynamic_rates(rates: dict[str, dict[str, float]]) -> None:
    if not rates:
        return

    merged = _load_dynamic_rates()
    for rate_key, rate in rates.items():
        normalized = _normalize_rate(rate)
        if normalized is not None:
            merged[rate_key] = normalized
    set_setting(DYNAMIC_RATE_SETTING, json.dumps(merged, sort_keys=True))


def get_rate(rate_key: str) -> dict[str, float]:
    rates = get_rate_table()
    if rate_key not in rates:
        raise KeyError(f"Unknown rate key: {rate_key}")
    return rates[rate_key]


def estimate_cost(
    rate_key: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    rates = get_rate(rate_key)
    total = (
        (input_tokens / 1_000_000) * rates["input_per_million"]
        + (output_tokens / 1_000_000) * rates["output_per_million"]
        + (cached_input_tokens / 1_000_000) * rates["cached_input_per_million"]
        + (reasoning_tokens / 1_000_000) * rates.get("reasoning_per_million", 0.0)
    )
    return round(total, 4)
