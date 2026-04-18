from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration


FLAG_PATTERN = re.compile(r"flag\{.*?\}", re.IGNORECASE)
TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]
SENSITIVE_KEYS = {"authorization", "cookie", "x-api-key"}


def _scrub_string(value: str) -> str:
    value = FLAG_PATTERN.sub("[redacted-flag]", value)
    for pattern in TOKEN_PATTERNS:
        value = pattern.sub("[redacted-token]", value)
    return value


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item) for item in value)
    if isinstance(value, Mapping):
        cleaned: MutableMapping[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS or key.lower().endswith(
                ("_token", "_secret", "_password", "_key")
            ):
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = _scrub_value(item)
        return cleaned
    return value


def _scrub_event(event: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    return _scrub_value(event)


def init_sentry(*, component: str, release: str, environment: str) -> None:
    if not os.environ.get("SENTRY_DSN"):
        return

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        release=release,
        environment=environment,
        integrations=[
            FlaskIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        send_default_pii=False,
        traces_sample_rate=1.0,
        before_send=_scrub_event,
        before_send_transaction=_scrub_event,
    )
    sentry_sdk.set_tag("component", component)
