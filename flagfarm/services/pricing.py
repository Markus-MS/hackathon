from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from flask import current_app


@lru_cache(maxsize=1)
def _load_rates(path: str) -> dict[str, dict[str, float]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_rate_table() -> dict[str, dict[str, float]]:
    return _load_rates(str(current_app.config["MODEL_RATE_FILE"]))


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
