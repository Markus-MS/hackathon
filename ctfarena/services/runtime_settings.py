from __future__ import annotations

import os
import sqlite3

from ctfarena.db import get_setting, set_setting


DEFAULT_SENTRY_DSN = (
    "https://f271196a290a90a866d33acb56d25eed@o4511239870939136.ingest.de.sentry.io/4511240223653968"
)


SECRET_KEYS = {
    "openai_api_key",
    "anthropic_api_key",
    "google_api_key",
    "deepseek_api_key",
    "openrouter_api_key",
    "sentry_browser_dsn",
}

DEFAULT_SETTINGS = {
    "solver_image": "ctfarena-solver:local",
    "solver_network": "bridge",
    "runner_max_parallel_runs": os.environ.get("CTF_ARENA_MAX_PARALLEL_RUNS", "1"),
    "solver_max_turns": "8",
    "solver_command_timeout_seconds": "20",
    "solver_llm_timeout_seconds": "90",
    "solver_grace_period_seconds": "300",
    "solver_extra_env": "",
    "opencode_config_dir": "",
    "opencode_data_dir": "",
    "sentry_enabled": "1",
    "sentry_browser_enabled": "0",
    "sentry_browser_dsn": DEFAULT_SENTRY_DSN,
    "sentry_traces_sample_rate": "0.95",
    "sentry_profiles_sample_rate": "0.5",
    "sentry_replays_session_sample_rate": "0.1",
    "sentry_replays_on_error_sample_rate": "1.0",
    "sentry_debug_mode_default": "0",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "google_api_key": "",
    "deepseek_api_key": "",
    "openrouter_api_key": "",
}

NON_EMPTY_SETTINGS = {
    "solver_image",
    "solver_network",
    "runner_max_parallel_runs",
    "solver_max_turns",
    "solver_command_timeout_seconds",
    "solver_llm_timeout_seconds",
    "solver_grace_period_seconds",
    "sentry_enabled",
    "sentry_browser_enabled",
    "sentry_traces_sample_rate",
    "sentry_profiles_sample_rate",
    "sentry_replays_session_sample_rate",
    "sentry_replays_on_error_sample_rate",
    "sentry_debug_mode_default",
}

PROVIDER_KEY_SETTING = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google": "google_api_key",
    "deepseek": "deepseek_api_key",
    "openrouter": "openrouter_api_key",
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


def enabled(key: str) -> bool:
    value = (get_setting(key, DEFAULT_SETTINGS[key]) or DEFAULT_SETTINGS[key]).strip().lower()
    return value in {"1", "true", "yes", "on"}


def sample_rate(key: str) -> float:
    try:
        value = float(get_setting(key, DEFAULT_SETTINGS[key]) or DEFAULT_SETTINGS[key])
    except (TypeError, ValueError):
        value = float(DEFAULT_SETTINGS[key])
    return min(1.0, max(0.0, value))


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
