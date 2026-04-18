from __future__ import annotations

import os
import sqlite3

from ctfarena.db import get_setting, set_setting


SECRET_KEYS = {
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "deepseek_api_key",
}

DEFAULT_SETTINGS = {
    "solver_image": "ctfarena-solver:local",
    "solver_network": "bridge",
    "runner_max_parallel_runs": os.environ.get("CTF_ARENA_MAX_PARALLEL_RUNS", "1"),
    "solver_max_turns": "8",
    "solver_command_timeout_seconds": "20",
    "solver_llm_timeout_seconds": "90",
    "solver_extra_env": "",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "google_api_key": "",
    "deepseek_api_key": "",
}

NON_EMPTY_SETTINGS = {
    "solver_image",
    "solver_network",
    "runner_max_parallel_runs",
    "solver_max_turns",
    "solver_command_timeout_seconds",
    "solver_llm_timeout_seconds",
}

PROVIDER_KEY_SETTING = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google": "google_api_key",
    "deepseek": "deepseek_api_key",
}


def seed_defaults(db: sqlite3.Connection) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        db.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (key, value),
        )
    db.commit()


def get_all() -> dict[str, str]:
    return {key: get_setting(key, value) or "" for key, value in DEFAULT_SETTINGS.items()}


def update(values: dict[str, str]) -> None:
    for key in DEFAULT_SETTINGS:
        if key in SECRET_KEYS and values.get(key) == "__KEEP__":
            continue
        value = values.get(key, DEFAULT_SETTINGS[key]).strip()
        if key in NON_EMPTY_SETTINGS and not value:
            value = DEFAULT_SETTINGS[key]
        set_setting(key, value)


def positive_int(key: str) -> int:
    try:
        value = get_setting(key, DEFAULT_SETTINGS[key]) or DEFAULT_SETTINGS[key]
        return max(1, int(value))
    except (TypeError, ValueError):
        return max(1, int(DEFAULT_SETTINGS[key]))


def max_parallel_runs() -> int:
    return positive_int("runner_max_parallel_runs")


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "configured"
    return f"{value[:4]}...{value[-4:]}"


def provider_api_key(provider: str) -> str:
    key_name = PROVIDER_KEY_SETTING.get(provider.lower())
    if key_name is None:
        return ""
    return get_setting(key_name, "") or ""


def set_provider_api_key(provider: str, api_key: str) -> bool:
    key_name = PROVIDER_KEY_SETTING.get(provider.lower())
    if key_name is None:
        return False
    set_setting(key_name, api_key.strip())
    return True
